#!/usr/bin/env python3
"""WWW 2023 accepted papers を抽出して JSON に保存する。"""

import argparse
import csv
import io
import json
import re
from pathlib import Path

import requests

DEFAULT_SOURCE_URL = "https://archives.iw3c2.org/www2023/program/accepted-papers/"
RESEARCH_CSV_URL = "https://archives.iw3c2.org/www2023/accepted/accepted_papers.csv"
INDUSTRY_CSV_URL = "https://archives.iw3c2.org/www2023/accepted/accepted_industry.csv"


def normalize_space(text: str) -> str:
    """連続空白を 1 つにし、前後空白を除去する。"""
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_title_for_key(title: str) -> str:
    """重複排除用のタイトル正規化キーを作る。"""
    key = normalize_space(title).lower()
    key = re.sub(r"[^\w\s]", "", key)
    return re.sub(r"\s+", " ", key).strip()


def fetch_csv_rows(url: str, timeout: int) -> list[dict[str, str]]:
    """CSV URL から行データを取得する。"""
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"

    text = response.text
    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict[str, str]] = []
    for row in reader:
        clean_row = {normalize_space(k): normalize_space(v) for k, v in row.items() if k is not None}
        rows.append(clean_row)
    return rows


def build_records(timeout: int) -> list[dict]:
    """Research/Industry の All Papers を抽出して統合する。"""
    records: list[dict] = []
    seen_keys: set[str] = set()

    print(f"📡 Fetching {RESEARCH_CSV_URL}")
    for row in fetch_csv_rows(RESEARCH_CSV_URL, timeout=timeout):
        title = normalize_space(row.get("title", ""))
        if not title:
            continue
        key = normalize_title_for_key(title)
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)

        records.append(
            {
                "title": title,
                "section": "research tracks",
                "doi": "",
            }
        )

    print(f"📡 Fetching {INDUSTRY_CSV_URL}")
    for row in fetch_csv_rows(INDUSTRY_CSV_URL, timeout=timeout):
        title = normalize_space(row.get("title", ""))
        if not title:
            continue
        key = normalize_title_for_key(title)
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)

        records.append(
            {
                "title": title,
                "section": "industry track",
                "doi": "",
            }
        )

    return records


def main() -> None:
    """WWW 2023 accepted papers を JSON として保存する。"""
    parser = argparse.ArgumentParser(description="Build WWW 2023 accepted papers JSON")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/WWW-23/accepted_papers.json"),
        help="Output JSON path",
    )
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds")
    args = parser.parse_args()

    records = build_records(timeout=args.timeout)

    payload = {
        "conference_id": "www",
        "venue": "WWW",
        "year": 2023,
        "source_url": DEFAULT_SOURCE_URL,
        "dblp_query": "toc:db/conf/www/www2023.html",
        "papers": records,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✨ Parsed {len(records)} records -> {args.output}")


if __name__ == "__main__":
    main()