#!/usr/bin/env python3
"""
論文リスト（JSON）を読み、各論文を OpenAlex API で検索して work を取得する。
DOI があれば filter=doi で取得、なければ search + publication_year:2025 で検索する。
"""

import argparse
import json
import time
from pathlib import Path

import requests

OPENALEX_API = "https://api.openalex.org"
REQUEST_DELAY = 0.2  # レート制限対策（秒）


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
    # OpenAlex: GET /works/{doi_url} で1件取得
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


def resolve_paper(entry: dict, year: int = 2025) -> tuple[dict | None, str]:
    """
    論文リストの1エントリを OpenAlex で解決する。
    戻り値: (work または None, ステータス "doi" | "search" | "not_found")
    """
    doi = entry.get("doi") or entry.get("DOI")
    if doi:
        work = get_work_by_doi(doi)
        if work:
            time.sleep(REQUEST_DELAY)
            return (work, "doi")
    title = entry.get("title", "").strip()
    if not title:
        return (None, "not_found")
    work = search_work_by_title(title, year=year)
    time.sleep(REQUEST_DELAY)
    if work:
        return (work, "search")
    return (None, "not_found")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="論文リスト JSON を読み、OpenAlex で work を解決して JSON に出力する"
    )
    parser.add_argument(
        "input_json",
        type=Path,
        help="論文リストの JSON ファイル（build_sigir2025_paper_list.py の出力）",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="出力 JSON ファイル（省略時は input のベース名 + _openalex.json）",
    )
    parser.add_argument(
        "-y", "--year",
        type=int,
        default=2025,
        help="検索時の出版年（デフォルト: 2025）",
    )
    parser.add_argument(
        "-n", "--limit",
        type=int,
        default=None,
        help="処理する論文数の上限（省略時は全件）",
    )
    args = parser.parse_args()

    if not args.input_json.exists():
        raise SystemExit(f"File not found: {args.input_json}")

    out_path = args.output or args.input_json.parent / (
        args.input_json.stem + "_openalex.json"
    )

    papers = json.loads(args.input_json.read_text(encoding="utf-8"))
    if not isinstance(papers, list):
        papers = papers.get("papers", papers.get("results", [papers]))

    if args.limit is not None:
        papers = papers[: args.limit]
        print(f"Limiting to first {len(papers)} papers.")

    results = []
    for i, entry in enumerate(papers):
        title = entry.get("title", "")[:50]
        print(f"[{i+1}/{len(papers)}] {title}...", end=" ", flush=True)
        work, status = resolve_paper(entry, year=args.year)
        if work:
            results.append({
                "list_entry": entry,
                "openalex_work": work,
                "resolved_via": status,
            })
            print(status)
        else:
            results.append({
                "list_entry": entry,
                "openalex_work": None,
                "resolved_via": "not_found",
            })
            print("not_found")

    out_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    found = sum(1 for r in results if r.get("openalex_work"))
    print(f"\nResolved {found}/{len(papers)} papers. Wrote {out_path}")


if __name__ == "__main__":
    main()
