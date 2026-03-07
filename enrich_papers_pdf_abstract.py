#!/usr/bin/env python3
"""
OpenAlex の結果 JSON から PDF URL とアブストラクトを抽出し、
不足分を Unpaywall / Crossref で補完して出力する。
"""

import argparse
import json
import os
import time
from pathlib import Path

import requests

REQUEST_DELAY = 0.3  # 外部 API のレート制限対策（秒）


def decode_abstract_inverted_index(inv: dict) -> str:
    """
    OpenAlex の abstract_inverted_index を平文に復元する。
    inv は { "word": [position, ...], ... } 形式。
    """
    if not inv or not isinstance(inv, dict):
        return ""
    pairs = []
    for word, positions in inv.items():
        for pos in positions:
            pairs.append((pos, word))
    pairs.sort(key=lambda x: x[0])
    return " ".join(w for _, w in pairs)


def extract_pdf_url(work: dict) -> str | None:
    """OpenAlex work から PDF URL を取得する（優先順: primary_location, oa_url, locations）。"""
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
    """OpenAlex work からアブストラクトを取得（abstract_inverted_index をデコード）。"""
    if not work:
        return ""
    inv = work.get("abstract_inverted_index")
    return decode_abstract_inverted_index(inv) if inv else ""


def get_doi_from_work(work: dict) -> str | None:
    """work から DOI を返す（https://doi.org/... または 10.xxxx/yyyy 形式）。"""
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


def process_entry(
    entry: dict,
    enrich_pdf: bool,
    enrich_abstract: bool,
    unpaywall_email: str | None,
) -> dict:
    """
    1エントリを処理し、pdf_url と abstract を付与した辞書を返す。
    """
    work = entry.get("openalex_work")
    out = {
        "list_entry": entry.get("list_entry", {}),
        "openalex_work": work,
        "pdf_url": None,
        "abstract": "",
        "pdf_source": None,
        "abstract_source": None,
    }

    # 既存の OpenAlex から抽出
    pdf_url = extract_pdf_url(work) if work else None
    abstract = extract_abstract_from_work(work) if work else ""

    if pdf_url:
        out["pdf_url"] = pdf_url
        out["pdf_source"] = "openalex"
    if abstract:
        out["abstract"] = abstract
        out["abstract_source"] = "openalex"

    doi = get_doi_from_work(work) if work else None
    if not doi:
        return out

    # 不足分を Unpaywall で補完
    if enrich_pdf and not out["pdf_url"]:
        time.sleep(REQUEST_DELAY)
        upw_pdf = fetch_unpaywall_pdf(doi, unpaywall_email)
        if upw_pdf:
            out["pdf_url"] = upw_pdf
            out["pdf_source"] = "unpaywall"

    # 不足分を Crossref で補完
    if enrich_abstract and not out["abstract"]:
        time.sleep(REQUEST_DELAY)
        cr_abstract = fetch_crossref_abstract(doi)
        if cr_abstract:
            out["abstract"] = cr_abstract
            out["abstract_source"] = "crossref"

    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OpenAlex 結果 JSON から PDF URL とアブストラクトを抽出・補完する"
    )
    parser.add_argument(
        "input_json",
        type=Path,
        help="fetch_works_from_openalex.py の出力 JSON",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="出力 JSON（省略時は input のベース名 + _enriched.json）",
    )
    parser.add_argument(
        "--no-enrich",
        action="store_true",
        help="OpenAlex からの抽出のみ行い、Unpaywall/Crossref を叩かない",
    )
    parser.add_argument(
        "--unpaywall-email",
        type=str,
        default=os.environ.get("UNPAYWALL_EMAIL", ""),
        help="Unpaywall API 用メール（未指定時は UNPAYWALL_EMAIL 環境変数、推奨）",
    )
    parser.add_argument(
        "-n", "--limit",
        type=int,
        default=None,
        help="処理する件数の上限（省略時は全件）",
    )
    args = parser.parse_args()

    if not args.input_json.exists():
        raise SystemExit(f"File not found: {args.input_json}")

    out_path = args.output or args.input_json.parent / (
        args.input_json.stem + "_enriched.json"
    )

    data = json.loads(args.input_json.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        data = data.get("results", data.get("papers", [data]))

    if args.limit is not None:
        data = data[: args.limit]
        print(f"Limiting to first {len(data)} entries.")

    enrich = not args.no_enrich
    email = (args.unpaywall_email or "").strip() or None
    if enrich and not email:
        print("Note: Unpaywall を利用する場合は --unpaywall-email または UNPAYWALL_EMAIL を指定するとよいです。")

    results = []
    for i, entry in enumerate(data):
        if (i + 1) % 50 == 0 or i == 0:
            print(f"Processing {i+1}/{len(data)}...", flush=True)
        results.append(
            process_entry(
                entry,
                enrich_pdf=enrich,
                enrich_abstract=enrich,
                unpaywall_email=email,
            )
        )

    out_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with_pdf = sum(1 for r in results if r.get("pdf_url"))
    with_abstract = sum(1 for r in results if r.get("abstract"))
    print(f"\nDone. PDF: {with_pdf}/{len(results)}, Abstract: {with_abstract}/{len(results)}. Wrote {out_path}")


if __name__ == "__main__":
    main()
