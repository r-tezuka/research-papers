#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

import requests

from common import deduplicate_records, normalize_doi, write_jsonl


DBLP_API_URL = "https://dblp.org/search/publ/api"


def default_dblp_query(conference: str, year: int) -> str:
    """会議名と年から、DBLPの目次ベース既定クエリを組み立てる。"""
    return f"toc:db/conf/{conference.lower()}/{conference.lower()}{year}.bht:"


def extract_doi_from_hit(hit_info: dict) -> str:
    """DBLPのhitからDOIを取り出し、`doi` と `ee` の両方に対応する。"""
    doi = hit_info.get("doi")
    if doi:
        return normalize_doi(doi)

    ee = hit_info.get("ee")
    if isinstance(ee, list):
        for value in ee:
            normalized = normalize_doi(value)
            if normalized:
                return normalized
    elif isinstance(ee, str):
        return normalize_doi(ee)
    return ""


def fetch_dblp_records(query: str, year: int, timeout: int, rows: int) -> list[dict]:
    """DBLP APIから論文候補を取得し、後段で扱いやすい共通形式へ整形する。"""
    params = {"q": query, "h": rows, "format": "json"}
    response = requests.get(DBLP_API_URL, params=params, timeout=timeout)
    response.raise_for_status()

    data = response.json()
    hits = data.get("result", {}).get("hits", {}).get("hit", [])
    if isinstance(hits, dict):
        hits = [hits]

    records: list[dict] = []
    for hit in hits:
        info = hit.get("info", {})
        title = info.get("title", "")
        if not title:
            continue
        records.append(
            {
                "title": title,
                "doi": extract_doi_from_hit(info),
                "year": int(info.get("year", year)) if str(info.get("year", "")).isdigit() else year,
                "venue": info.get("venue", ""),
                "sources": ["dblp"],
            }
        )
    return records


def load_conference_list(path: Path, year: int, venue: str) -> list[dict]:
    """手元のconference list JSONを読み込み、共通レコード形式に変換する。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    records: list[dict] = []
    if not isinstance(data, list):
        return records

    for item in data:
        title = item.get("title", "")
        if not title:
            continue
        records.append(
            {
                "title": title,
                "doi": normalize_doi(item.get("doi") or item.get("DOI") or ""),
                "year": year,
                "venue": venue,
                "section": item.get("section", ""),
                "sources": ["conference_list"],
            }
        )
    return records


def main() -> None:
    """DBLPとconference listを統合してmaster JSONLを生成する。"""
    parser = argparse.ArgumentParser(description="Build papers master list from DBLP and conference list")
    parser.add_argument("--conference", default="sigir", help="Conference short name (e.g., sigir)")
    parser.add_argument("--year", type=int, default=2025, help="Conference year")
    parser.add_argument("--dblp-query", default="", help="Custom DBLP query string")
    parser.add_argument("--conference-list", default="", help="Path to accepted papers JSON")
    parser.add_argument("--rows", type=int, default=1000, help="Number of DBLP rows to request")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds")
    parser.add_argument("--output", default="data/papers_master.jsonl", help="Output JSONL path")
    args = parser.parse_args()

    query = args.dblp_query or default_dblp_query(args.conference, args.year)

    print(f"📡 DBLP query: {query}")
    records = fetch_dblp_records(query, args.year, args.timeout, args.rows)
    if not records and not args.dblp_query:
        fallback_query = f"{args.conference} {args.year}"
        print(f"ℹ️ DBLP default query returned 0. fallback query: {fallback_query}")
        records = fetch_dblp_records(fallback_query, args.year, args.timeout, args.rows)
    print(f"✅ DBLP records: {len(records)}")

    if args.conference_list:
        conference_path = Path(args.conference_list)
        if conference_path.exists():
            site_records = load_conference_list(conference_path, args.year, args.conference.upper())
            records.extend(site_records)
            print(f"✅ Conference list records: {len(site_records)}")
        else:
            print(f"⚠️ conference list not found: {conference_path}")

    deduped = deduplicate_records(records)
    write_jsonl(args.output, deduped)
    print(f"✨ Master list wrote {len(deduped)} records to {args.output}")


if __name__ == "__main__":
    main()
