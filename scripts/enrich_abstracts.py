#!/usr/bin/env python3
import argparse
import re
from urllib.parse import quote

import requests

from common import load_jsonl, now_iso, normalize_doi, write_jsonl


OPENALEX_WORKS_API = "https://api.openalex.org/works"


def decode_abstract_inverted_index(inverted_index: dict) -> str:
    """OpenAlexのinverted index形式abstractを通常の文章へ復元する。"""
    pairs = []
    for word, positions in (inverted_index or {}).items():
        for pos in positions:
            pairs.append((pos, word))
    pairs.sort(key=lambda item: item[0])
    return " ".join(word for _, word in pairs)


def strip_html_tags(text: str) -> str:
    """Crossref abstractに含まれるHTMLタグを除去する。"""
    return re.sub(r"<[^>]+>", "", text or "").strip()


def fetch_openalex_abstract(doi: str, timeout: int) -> tuple[str, str]:
    """OpenAlexからDOI指定でabstractを取得する。"""
    doi_url = f"https://doi.org/{normalize_doi(doi)}"
    url = f"{OPENALEX_WORKS_API}/{quote(doi_url, safe='')}"
    response = requests.get(url, timeout=timeout)
    if response.status_code == 404:
        return "", ""
    response.raise_for_status()
    data = response.json()
    abstract = decode_abstract_inverted_index(data.get("abstract_inverted_index") or {})
    return abstract, "openalex"


def fetch_crossref_abstract(doi: str, timeout: int) -> tuple[str, str]:
    """CrossrefからDOI指定でabstractを取得する。"""
    url = f"https://api.crossref.org/works/{quote(normalize_doi(doi), safe='')}"
    response = requests.get(url, timeout=timeout)
    if response.status_code == 404:
        return "", ""
    response.raise_for_status()
    message = response.json().get("message", {})
    abstract = strip_html_tags(message.get("abstract", ""))
    return abstract, "crossref"


def fetch_semantic_scholar_abstract(doi: str, timeout: int) -> tuple[str, str]:
    """Semantic ScholarからDOI指定でabstractを取得する。"""
    url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{quote(normalize_doi(doi), safe='')}"
    response = requests.get(url, params={"fields": "abstract"}, timeout=timeout)
    if response.status_code == 404:
        return "", ""
    response.raise_for_status()
    abstract = response.json().get("abstract", "")
    return abstract, "semantic_scholar"


def enrich_record(record: dict, timeout: int) -> dict:
    """abstract未取得レコードに対して、複数APIを順に試して補完する。"""
    if (record.get("abstract") or "").strip():
        return record

    doi = normalize_doi(record.get("doi", ""))
    if not doi:
        return record

    for fetcher in (fetch_openalex_abstract, fetch_crossref_abstract, fetch_semantic_scholar_abstract):
        try:
            abstract, source = fetcher(doi, timeout)
            if abstract:
                record["abstract"] = abstract
                record["abstract_source"] = source
                record["abstract_fetched_at"] = now_iso()
                return record
        except Exception:
            continue

    return record


def main() -> None:
    """master JSONLを読み込み、未取得abstractを補完したJSONLを書き出す。"""
    parser = argparse.ArgumentParser(description="Enrich papers with abstracts (missing only)")
    parser.add_argument("--input", default="data/papers_master.jsonl", help="Input JSONL")
    parser.add_argument("--output", default="data/papers_enriched.jsonl", help="Output JSONL")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout seconds")
    args = parser.parse_args()

    records = load_jsonl(args.input)
    if not records:
        print("❌ input is empty")
        return

    enriched = []
    updated = 0
    for record in records:
        before = (record.get("abstract") or "").strip()
        item = enrich_record(record, args.timeout)
        after = (item.get("abstract") or "").strip()
        if not before and after:
            updated += 1
        enriched.append(item)

    write_jsonl(args.output, enriched)
    print(f"✨ Enriched {updated} / {len(records)} records. Wrote {args.output}")


if __name__ == "__main__":
    main()
