#!/usr/bin/env python3
"""
論文リスト（accepted_papers JSON）を入力に、
1件ごとに OpenAlex で解決し、PDF/abstract を取得して結果 JSON を出力する。
並列実行時はレート制限（OpenAlex 10/s、Unpaywall/Crossref 5/s 目安）を守る。
"""

import argparse
import io
import json
import os
import re
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

try:
    import pymupdf
except ImportError:
    pymupdf = None  # type: ignore[assignment]

OPENALEX_API = "https://api.openalex.org"
OPENALEX_DELAY = 0.2   # 直列時のレート制限対策（秒）
ENRICH_DELAY = 0.3     # 直列時 Unpaywall/Crossref 用
OPENALEX_MAX_PER_SEC = 10   # 並列時の OpenAlex レート制限
ENRICH_MAX_PER_SEC = 5      # 並列時の Unpaywall/Crossref レート制限


class RateLimiter:
    """スレッドセーフな「秒あたり最大 N 回」のレート制限。"""

    def __init__(self, max_per_sec: float) -> None:
        self.max_per_sec = max_per_sec
        self._timestamps: deque = deque()
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.time()
            while self._timestamps and self._timestamps[0] < now - 1:
                self._timestamps.popleft()
            while len(self._timestamps) >= self.max_per_sec:
                time.sleep(0.05)
                now = time.time()
                while self._timestamps and self._timestamps[0] < now - 1:
                    self._timestamps.popleft()
            self._timestamps.append(time.time())


def normalize_doi(doi: str) -> str:
    """DOI を https://doi.org/... 形式に正規化する。"""
    s = (doi or "").strip()
    if not s:
        return ""
    if s.startswith("http"):
        return s
    return f"https://doi.org/{s}"


def get_work_by_doi(doi: str, timeout: int = 30) -> dict | None:
    """DOI で work を1件取得する。"""
    doi_url = normalize_doi(doi)
    if not doi_url:
        return None
    url = f"{OPENALEX_API}/works/{doi_url}"
    resp = requests.get(url, timeout=timeout)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def search_work_by_title(title: str, year: int = 2025, timeout: int = 30) -> dict | None:
    """タイトル検索で work を1件取得する（先頭1件を返す）。"""
    url = f"{OPENALEX_API}/works"
    params = {
        "search": title[:200],
        "filter": f"publication_year:{year}",
        "per_page": 1,
    }
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results") or []
    if not results:
        return None
    return results[0]


def resolve_paper(
    entry: dict,
    year: int = 2025,
    openalex_limiter: RateLimiter | None = None,
) -> tuple[dict | None, str]:
    """
    論文リストの1エントリを OpenAlex で解決する。
    戻り値: (work または None, ステータス "doi" | "search" | "not_found")
    """
    def do_request(fn, *args, **kwargs):
        if openalex_limiter:
            openalex_limiter.wait()
        return fn(*args, **kwargs)

    doi = entry.get("doi") or entry.get("DOI")
    if doi:
        work = do_request(get_work_by_doi, doi)
        if work:
            if not openalex_limiter:
                time.sleep(OPENALEX_DELAY)
            return (work, "doi")
    title = entry.get("title", "").strip()
    if not title:
        return (None, "not_found")
    work = do_request(search_work_by_title, title, year)
    if work:
        if not openalex_limiter:
            time.sleep(OPENALEX_DELAY)
        return (work, "search")
    return (None, "not_found")


def decode_abstract_inverted_index(inv: dict) -> str:
    """OpenAlex の abstract_inverted_index を平文に復元する。"""
    if not inv or not isinstance(inv, dict):
        return ""
    pairs = []
    for word, positions in inv.items():
        for pos in positions:
            pairs.append((pos, word))
    pairs.sort(key=lambda x: x[0])
    return " ".join(w for _, w in pairs)


def extract_pdf_url(work: dict) -> str | None:
    """OpenAlex work から PDF URL を取得する。"""
    if not work:
        return None
    pl = work.get("primary_location") or {}
    if pl.get("pdf_url"):
        return pl["pdf_url"]
    oa = work.get("open_access") or {}
    if oa.get("oa_url"):
        return oa["oa_url"]
    for loc in work.get("locations") or []:
        if loc.get("pdf_url"):
            return loc["pdf_url"]
    return None


def extract_abstract_from_work(work: dict) -> str:
    """OpenAlex work からアブストラクトを取得する。"""
    if not work:
        return ""
    inv = work.get("abstract_inverted_index")
    return decode_abstract_inverted_index(inv) if inv else ""


def get_doi_from_work(work: dict) -> str | None:
    """work から DOI を返す。"""
    if not work:
        return None
    doi = work.get("doi")
    if doi:
        return doi.replace("https://doi.org/", "").strip()
    ids = work.get("ids") or {}
    doi_url = ids.get("doi")
    if doi_url:
        return doi_url.replace("https://doi.org/", "").strip()
    return None


def fetch_unpaywall_pdf(doi: str, email: str | None, timeout: int = 15) -> str | None:
    """Unpaywall API で DOI の OA PDF URL を取得する。"""
    if not doi or not doi.strip():
        return None
    doi_clean = doi.replace("https://doi.org/", "").strip()
    url = f"https://api.unpaywall.org/v2/{doi_clean}"
    params = {}
    if email:
        params["email"] = email
    try:
        resp = requests.get(url, params=params or None, timeout=timeout)
        if resp.status_code != 200:
            return None
        data = resp.json()
        best = data.get("best_oa_location")
        if best and best.get("url_for_pdf"):
            return best["url_for_pdf"]
        return None
    except Exception:
        return None


def fetch_crossref_abstract(doi: str, timeout: int = 15) -> str:
    """Crossref API で DOI のアブストラクトを取得する。"""
    if not doi or not doi.strip():
        return ""
    doi_clean = doi.replace("https://doi.org/", "").strip()
    url = f"https://api.crossref.org/works/{doi_clean}"
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code != 200:
            return ""
        data = resp.json()
        message = data.get("message") or {}
        abstract = message.get("abstract", "")
        if isinstance(abstract, str):
            return abstract.strip()
        return ""
    except Exception:
        return ""


# PDF からアブストラクトらしきテキストを抽出（1ページ目を対象、最大文字数）
PDF_ABSTRACT_MAX_CHARS = 2500
PDF_DOWNLOAD_TIMEOUT = 30
PDF_DOWNLOAD_MAX_BYTES = 5 * 1024 * 1024  # 5MB


def extract_abstract_from_pdf_url(pdf_url: str) -> str:
    """
    PDF の URL から1ページ目のテキストを取得し、Abstract セクションらしき部分を返す。
    pymupdf が未インストールの場合は空文字を返す。
    """
    if not pdf_url or not pdf_url.strip():
        return ""
    if pymupdf is None:
        return ""
    try:
        resp = requests.get(
            pdf_url,
            timeout=PDF_DOWNLOAD_TIMEOUT,
            stream=True,
            headers={"User-Agent": "research-papers/1.0 (mailto:optional@example.com)"},
        )
        resp.raise_for_status()
        content = b""
        for chunk in resp.iter_content(chunk_size=65536):
            content += chunk
            if len(content) > PDF_DOWNLOAD_MAX_BYTES:
                break
        if len(content) < 100:
            return ""
        doc = pymupdf.open(stream=io.BytesIO(content), filetype="pdf")
        if doc.page_count == 0:
            doc.close()
            return ""
        page = doc[0]
        text = page.get_text()
        doc.close()
        if not text or not text.strip():
            return ""
        text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        # 「Abstract」〜「Introduction」や「Keywords」の手前までを抽出
        abstract_match = re.search(r"\babstract\b", text, re.IGNORECASE)
        if abstract_match:
            start = abstract_match.end()
            tail = text[start:]
            end_match = re.search(
                r"\b(?:introduction|keywords|index terms|1\.\s|1\s+introduction)\b",
                tail,
                re.IGNORECASE,
            )
            if end_match:
                tail = tail[: end_match.start()]
            excerpt = tail.strip()
        else:
            excerpt = text[:PDF_ABSTRACT_MAX_CHARS]
        excerpt = re.sub(r"\n{3,}", "\n\n", excerpt).strip()
        if len(excerpt) > PDF_ABSTRACT_MAX_CHARS:
            excerpt = excerpt[:PDF_ABSTRACT_MAX_CHARS].rsplit(maxsplit=1)[0]
        return excerpt
    except Exception:
        return ""


def resolve_and_enrich_one(
    entry: dict,
    year: int,
    enrich_pdf: bool,
    enrich_abstract: bool,
    unpaywall_email: str | None,
    openalex_limiter: RateLimiter | None = None,
    enrich_limiter: RateLimiter | None = None,
) -> dict:
    """
    1件の論文について: OpenAlex 解決 → PDF/abstract 取得（不足分は Unpaywall/Crossref/PDF で補完）。
    戻り値は結果辞書（list_entry, openalex_work, resolved_via, pdf_url, abstract, pdf_source, abstract_source）。
    """
    out = {
        "list_entry": entry,
        "openalex_work": None,
        "resolved_via": "not_found",
        "pdf_url": None,
        "abstract": "",
        "pdf_source": None,
        "abstract_source": None,
    }

    work, status = resolve_paper(entry, year=year, openalex_limiter=openalex_limiter)
    out["openalex_work"] = work
    out["resolved_via"] = status

    if not work:
        return out

    pdf_url = extract_pdf_url(work)
    abstract = extract_abstract_from_work(work)
    if pdf_url:
        out["pdf_url"] = pdf_url
        out["pdf_source"] = "openalex"
    if abstract:
        out["abstract"] = abstract
        out["abstract_source"] = "openalex"

    doi = get_doi_from_work(work)
    if not doi:
        return out

    if enrich_pdf and not out["pdf_url"]:
        if enrich_limiter:
            enrich_limiter.wait()
        else:
            time.sleep(ENRICH_DELAY)
        upw_pdf = fetch_unpaywall_pdf(doi, unpaywall_email)
        if upw_pdf:
            out["pdf_url"] = upw_pdf
            out["pdf_source"] = "unpaywall"

    if enrich_abstract and not out["abstract"]:
        if enrich_limiter:
            enrich_limiter.wait()
        else:
            time.sleep(ENRICH_DELAY)
        cr_abstract = fetch_crossref_abstract(doi)
        if cr_abstract:
            out["abstract"] = cr_abstract
            out["abstract_source"] = "crossref"

    # abstract がまだ無く PDF URL がある場合は PDF 1ページ目から抽出を試行
    if enrich_abstract and not out["abstract"] and out["pdf_url"]:
        if enrich_limiter:
            enrich_limiter.wait()
        else:
            time.sleep(ENRICH_DELAY)
        pdf_abstract = extract_abstract_from_pdf_url(out["pdf_url"])
        if pdf_abstract:
            out["abstract"] = pdf_abstract
            out["abstract_source"] = "pdf"

    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="論文リスト（accepted_papers）を読み、OpenAlex で解決し PDF/abstract を取得して JSON を出力する"
    )
    parser.add_argument(
        "input_json",
        type=Path,
        help="論文リストの JSON（例: sigir2025_accepted_papers.json）",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="出力 JSON（省略時は input のベース名 + _enriched.json）",
    )
    parser.add_argument(
        "-y", "--year",
        type=int,
        default=2025,
        help="OpenAlex 検索時の出版年",
    )
    parser.add_argument(
        "--no-enrich",
        action="store_true",
        help="OpenAlex からの抽出のみ行い、Unpaywall/Crossref/PDF を叩かない",
    )
    parser.add_argument(
        "--unpaywall-email",
        type=str,
        default=os.environ.get("UNPAYWALL_EMAIL", ""),
        help="Unpaywall API 用メール（推奨: UNPAYWALL_EMAIL 環境変数）",
    )
    parser.add_argument(
        "-n", "--limit",
        type=int,
        default=None,
        help="処理する論文数の上限（省略時は全件）",
    )
    parser.add_argument(
        "-j", "--workers",
        type=int,
        default=1,
        metavar="N",
        help="並列ワーカー数（1=直列）。OpenAlex 10/s・補完 API 5/s を超えないよう 5 程度を推奨",
    )
    args = parser.parse_args()

    if not args.input_json.exists():
        raise SystemExit(f"File not found: {args.input_json}")

    out_path = args.output or args.input_json.parent / (
        args.input_json.stem + "_enriched.json"
    )

    papers = json.loads(args.input_json.read_text(encoding="utf-8"))
    if not isinstance(papers, list):
        papers = papers.get("papers", papers.get("results", [papers]))

    if args.limit is not None:
        papers = papers[: args.limit]
        print(f"Limiting to first {len(papers)} papers.")

    enrich = not args.no_enrich
    email = (args.unpaywall_email or "").strip() or None
    if enrich and not email:
        print("Note: Unpaywall 利用時は --unpaywall-email または UNPAYWALL_EMAIL を指定するとよいです。")

    workers = max(1, args.workers)
    openalex_limiter = RateLimiter(OPENALEX_MAX_PER_SEC) if workers > 1 else None
    enrich_limiter = RateLimiter(ENRICH_MAX_PER_SEC) if workers > 1 and enrich else None
    if workers > 1:
        print(f"Parallel: {workers} workers, OpenAlex <={OPENALEX_MAX_PER_SEC}/s, Enrich <={ENRICH_MAX_PER_SEC}/s")

    def process_one(index: int, entry: dict) -> tuple[int, dict]:
        result = resolve_and_enrich_one(
            entry,
            year=args.year,
            enrich_pdf=enrich,
            enrich_abstract=enrich,
            unpaywall_email=email,
            openalex_limiter=openalex_limiter,
            enrich_limiter=enrich_limiter,
        )
        return (index, result)

    results: list[dict | None] = [None] * len(papers)
    if workers <= 1:
        for i, entry in enumerate(papers):
            title = (entry.get("title") or "")[:50]
            print(f"[{i+1}/{len(papers)}] {title}...", end=" ", flush=True)
            _, result = process_one(i, entry)
            results[i] = result
            print(f"{result['resolved_via']} | PDF:{result['pdf_source'] or '-'} abstract:{result['abstract_source'] or '-'}")
    else:
        completed = 0
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_idx = {executor.submit(process_one, i, entry): i for i, entry in enumerate(papers)}
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    i, result = future.result()
                    results[i] = result
                    completed += 1
                    title = (result["list_entry"].get("title") or "")[:50]
                    print(f"[{completed}/{len(papers)}] {title}... {result['resolved_via']} | PDF:{result['pdf_source'] or '-'} abstract:{result['abstract_source'] or '-'}")
                except Exception as e:
                    print(f"[?] index {idx} failed: {e}")
                    results[idx] = {
                        "list_entry": papers[idx],
                        "openalex_work": None,
                        "resolved_via": "not_found",
                        "pdf_url": None,
                        "abstract": "",
                        "pdf_source": None,
                        "abstract_source": None,
                    }

    out_list = [r for r in results if r is not None]
    out_path.write_text(
        json.dumps(out_list, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    resolved = sum(1 for r in out_list if r.get("openalex_work"))
    with_pdf = sum(1 for r in out_list if r.get("pdf_url"))
    with_abstract = sum(1 for r in out_list if r.get("abstract"))
    print(f"\nDone. Resolved: {resolved}/{len(papers)}, PDF: {with_pdf}/{len(papers)}, Abstract: {with_abstract}/{len(papers)}. Wrote {out_path}")


if __name__ == "__main__":
    main()
