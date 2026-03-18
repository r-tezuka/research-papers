#!/usr/bin/env python3
import argparse
import re
from urllib.parse import quote

import requests

from common import load_jsonl, now_iso, normalize_doi, write_jsonl


OPENALEX_WORKS_API = "https://api.openalex.org/works"
SEMANTIC_SCHOLAR_BATCH_API = "https://api.semanticscholar.org/graph/v1/paper/batch"
CROSSREF_WORKS_API = "https://api.crossref.org/works"

OPENALEX_BATCH_SIZE = 50
SEMANTIC_SCHOLAR_BATCH_SIZE = 200
CROSSREF_BATCH_SIZE = 50


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


def chunked(items: list[str], size: int) -> list[list[str]]:
    """配列を固定長チャンクへ分割する。"""
    if size <= 0:
        return [items]
    return [items[i : i + size] for i in range(0, len(items), size)]


def fetch_openalex_batch(dois: list[str], timeout: int) -> dict[str, str]:
    """OpenAlexから複数DOIのabstractを一括取得する。"""
    if not dois:
        return {}

    doi_filter = "|".join(normalize_doi(doi) for doi in dois if normalize_doi(doi))
    if not doi_filter:
        return {}

    url = f"{OPENALEX_WORKS_API}?filter=doi:{quote(doi_filter, safe='|:./')}&per-page=200"
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()

    found: dict[str, str] = {}
    for work in response.json().get("results", []):
        doi_url = work.get("doi", "")
        doi = normalize_doi(doi_url)
        if not doi:
            continue
        abstract = decode_abstract_inverted_index(work.get("abstract_inverted_index") or {})
        if abstract:
            found[doi] = abstract
    return found


def fetch_semantic_scholar_batch(dois: list[str], timeout: int) -> dict[str, str]:
    """Semantic Scholarのbatch APIで複数DOIのabstractを一括取得する。"""
    if not dois:
        return {}

    ids = [f"DOI:{normalize_doi(doi)}" for doi in dois if normalize_doi(doi)]
    if not ids:
        return {}

    response = requests.post(
        SEMANTIC_SCHOLAR_BATCH_API,
        params={"fields": "abstract,externalIds"},
        json={"ids": ids},
        timeout=timeout,
    )
    response.raise_for_status()

    found: dict[str, str] = {}
    payload = response.json()
    for paper in payload if isinstance(payload, list) else []:
        if not isinstance(paper, dict):
            continue
        external_ids = paper.get("externalIds") or {}
        doi = normalize_doi(external_ids.get("DOI", ""))
        abstract = (paper.get("abstract") or "").strip()
        if doi and abstract:
            found[doi] = abstract
    return found


def fetch_crossref_batch(dois: list[str], timeout: int) -> dict[str, str]:
    """Crossrefのfilterで複数DOIのabstractを一括取得する。"""
    if not dois:
        return {}

    parts = [f"doi:{quote(normalize_doi(doi), safe='')}" for doi in dois if normalize_doi(doi)]
    if not parts:
        return {}

    url = f"{CROSSREF_WORKS_API}?filter={','.join(parts)}&rows={len(parts)}"
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()

    found: dict[str, str] = {}
    items = response.json().get("message", {}).get("items", [])
    for item in items:
        doi = normalize_doi(item.get("DOI", ""))
        abstract = strip_html_tags(item.get("abstract", ""))
        if doi and abstract:
            found[doi] = abstract
    return found


def apply_abstracts(records: list[dict], doi_to_indexes: dict[str, list[int]], found: dict[str, str], source: str) -> int:
    """取得したabstractをrecordsへ反映し、更新件数を返す。"""
    updated = 0
    fetched_at = now_iso()
    for doi, abstract in found.items():
        if not abstract:
            continue
        for idx in doi_to_indexes.get(doi, []):
            record = records[idx]
            if (record.get("abstract") or "").strip():
                continue
            record["abstract"] = abstract
            record["abstract_source"] = source
            record["abstract_fetched_at"] = fetched_at
            updated += 1
    return updated


def main() -> None:
    """master JSONLを読み込み、未取得abstractを補完したJSONLを書き出す。"""
    parser = argparse.ArgumentParser(description="Enrich papers with abstracts (missing only)")
    parser.add_argument("--input", default="results/papers_master.jsonl", help="Input JSONL")
    parser.add_argument("--output", default="results/papers_enriched.jsonl", help="Output JSONL")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout seconds")
    args = parser.parse_args()

    records = load_jsonl(args.input)
    if not records:
        print("❌ input is empty")
        return

    doi_to_indexes: dict[str, list[int]] = {}
    pending_dois: list[str] = []
    seen: set[str] = set()
    for idx, record in enumerate(records):
        if (record.get("abstract") or "").strip():
            continue
        doi = normalize_doi(record.get("doi", ""))
        if not doi:
            continue
        doi_to_indexes.setdefault(doi, []).append(idx)
        if doi not in seen:
            pending_dois.append(doi)
            seen.add(doi)

    if not pending_dois:
        write_jsonl(args.output, records)
        print(f"✨ Enriched 0 / {len(records)} records. Wrote {args.output}")
        return

    print(f"ℹ️ Pending DOI count: {len(pending_dois)}")

    updated = 0

    # 1) OpenAlex batch
    openalex_found: dict[str, str] = {}
    for chunk in chunked(pending_dois, OPENALEX_BATCH_SIZE):
        try:
            openalex_found.update(fetch_openalex_batch(chunk, args.timeout))
        except Exception:
            continue
    updated += apply_abstracts(records, doi_to_indexes, openalex_found, "openalex")
    remaining = [doi for doi in pending_dois if not (records[doi_to_indexes[doi][0]].get("abstract") or "").strip()]
    print(f"ℹ️ OpenAlex resolved: {len(openalex_found)} DOIs, remaining: {len(remaining)}")

    # 2) Semantic Scholar batch
    semantic_found: dict[str, str] = {}
    for chunk in chunked(remaining, SEMANTIC_SCHOLAR_BATCH_SIZE):
        try:
            semantic_found.update(fetch_semantic_scholar_batch(chunk, args.timeout))
        except Exception:
            continue
    updated += apply_abstracts(records, doi_to_indexes, semantic_found, "semantic_scholar")
    remaining = [doi for doi in remaining if not (records[doi_to_indexes[doi][0]].get("abstract") or "").strip()]
    print(f"ℹ️ Semantic Scholar resolved: {len(semantic_found)} DOIs, remaining: {len(remaining)}")

    # 3) Crossref multi-doi filter batch
    crossref_found: dict[str, str] = {}
    for chunk in chunked(remaining, CROSSREF_BATCH_SIZE):
        try:
            crossref_found.update(fetch_crossref_batch(chunk, args.timeout))
        except Exception:
            continue
    updated += apply_abstracts(records, doi_to_indexes, crossref_found, "crossref")

    write_jsonl(args.output, records)
    print(f"✨ Enriched {updated} / {len(records)} records. Wrote {args.output}")


if __name__ == "__main__":
    main()
