#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from common import deduplicate_records, normalize_doi, write_jsonl
from dblp_utils import default_dblp_query, fetch_dblp_records

DBLP_ROWS = 1000
DBLP_TIMEOUT = 30


def load_conference_bundle(path: Path) -> tuple[dict, list[dict]]:
    """conference list JSON を読み込み、必須メタ情報と論文配列を返す。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON in conference list: {path} ({exc})") from exc
    if not isinstance(data, dict):
        raise SystemExit("conference list must be an object with metadata + papers")

    papers = data.get("papers")
    if not isinstance(papers, list):
        raise SystemExit("conference list must contain `papers` as an array")

    conference_id = str(data.get("conference_id", "")).strip().lower()
    venue = str(data.get("venue", "")).strip()
    year = int(data.get("year", 0)) if str(data.get("year", "")).isdigit() else 0
    dblp_query = str(data.get("dblp_query", "")).strip()

    if not conference_id:
        raise SystemExit("conference list must contain non-empty `conference_id`")
    if not venue:
        raise SystemExit("conference list must contain non-empty `venue`")
    if year <= 0:
        raise SystemExit("conference list must contain valid numeric `year`")

    metadata = {
        "conference_id": conference_id,
        "venue": venue,
        "year": year,
        "dblp_query": dblp_query,
    }
    return metadata, papers


def load_conference_list(items: list[dict], year: int, venue: str) -> list[dict]:
    """conference list の論文配列を共通レコード形式に変換する。"""
    records: list[dict] = []
    for item in items:
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
    parser.add_argument("--conference-list", required=True, help="Path to accepted papers JSON")
    parser.add_argument("--output", default="results/papers_master.jsonl", help="Output JSONL path")
    args = parser.parse_args()

    conference_path = Path(args.conference_list)
    if not conference_path.is_file():
        raise SystemExit(f"conference list file not found: {conference_path}")

    metadata, conference_items = load_conference_bundle(conference_path)
    conference_id = metadata["conference_id"]
    venue = metadata["venue"]
    year = metadata["year"]

    default_query = metadata.get("dblp_query") or default_dblp_query(conference_id, year)
    fallback_query = f"{conference_id} {year}"
    query = default_query

    print(f"📡 DBLP query: {query}")
    records = fetch_dblp_records(query, fallback_query, year, DBLP_TIMEOUT, DBLP_ROWS)
    print(f"✅ DBLP records: {len(records)}")

    site_records = load_conference_list(conference_items, year, venue)
    records.extend(site_records)
    print(f"✅ Conference list records: {len(site_records)}")

    deduped = deduplicate_records(records)
    write_jsonl(args.output, deduped)
    print(f"✨ Master list wrote {len(deduped)} records to {args.output}")


if __name__ == "__main__":
    main()
