#!/usr/bin/env python3
"""ADKDD 2024 ページから論文リスト（title / section / doi）を抽出して JSON に保存する。"""

import argparse
import json
import re
from pathlib import Path

import requests

DEFAULT_URL = "https://www.adkdd.org/papers/2024"
WARMUP_PATTERN = re.compile(
    r'<script type="application/json" id="wix-warmup-data">(.*?)</script>',
    re.DOTALL,
)
DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)


def normalize_space(text: str) -> str:
    """連続空白を 1 つにし、前後空白を除去する。"""
    return re.sub(r"\s+", " ", text or "").strip()


def extract_doi(text: str) -> str:
    """文字列中の DOI を抽出する。見つからなければ空文字。"""
    match = DOI_PATTERN.search(text or "")
    return match.group(0).lower() if match else ""


def is_paper_tag(tag: str) -> bool:
    """Papers 相当のタグかを判定する。"""
    return "paper" in (tag or "").strip().lower()


def parse_records(html_text: str) -> list[dict]:
    """Wix warmup data から ADKDD 論文レコードを抽出する。"""
    match = WARMUP_PATTERN.search(html_text)
    if not match:
        return []

    warmup = json.loads(match.group(1))
    records: list[dict] = []
    seen_titles: set[str] = set()

    updates = warmup.get("platform", {}).get("ssrPropsUpdates", [])
    for update in updates:
        if not isinstance(update, dict):
            continue
        for value in update.values():
            if not isinstance(value, dict):
                continue
            rows = value.get("rows")
            if not isinstance(rows, list):
                continue

            for row in rows:
                if not isinstance(row, dict):
                    continue

                title = normalize_space(str(row.get("title", "")))
                if not title:
                    continue

                tag = normalize_space(str(row.get("tag", "")))
                if not is_paper_tag(tag):
                    continue

                key = title.lower()
                if key in seen_titles:
                    continue
                seen_titles.add(key)

                doi = extract_doi(title)
                if not doi:
                    doi = extract_doi(str(row.get("pdf", "")))

                records.append(
                    {
                        "title": title,
                        "section": "best paper" if "best" in tag.lower() else "paper",
                        "doi": doi,
                    }
                )

    return records


def fetch_html(url: str, timeout: int = 30) -> str:
    """指定 URL から HTML を取得する。"""
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def main() -> None:
    """ADKDD 2024 論文リストを JSON として保存する。"""
    parser = argparse.ArgumentParser(description="Build ADKDD 2024 paper list JSON from web page")
    parser.add_argument("--url", default=DEFAULT_URL, help="ADKDD 2024 papers page URL")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/ADKDD-24/accepted_papers.json"),
        help="Output JSON path",
    )
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds")
    args = parser.parse_args()

    print(f"📡 Fetching {args.url}")
    html_text = fetch_html(args.url, args.timeout)
    records = parse_records(html_text)

    payload = {
        "conference_id": "adkdd",
        "venue": "ADKDD",
        "year": 2024,
        "source_url": args.url,
        "dblp_query": "toc:db/conf/kdd/adkdd2024.bht:",
        "papers": records,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✨ Parsed {len(records)} records -> {args.output}")


if __name__ == "__main__":
    main()
