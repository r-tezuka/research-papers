#!/usr/bin/env python3
"""SIGIR 2024 program papers 用の JSONL から論文リストを抽出して JSON に保存する。"""

import argparse
import json
import re
from pathlib import Path

import requests

DEFAULT_URL = "https://sigir-2024.github.io/program_papers.html"
DEFAULT_JSONL_URL = "https://sigir-2024.github.io/infofiles/sigir2024-papers.updated.v3.jsonl"
DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
GROUP_NAMES = {
    "dc": "doctoral consortium papers",
    "de": "demonstration papers",
    "fp": "full papers",
    "pp": "perspectives papers",
    "rr": "resource & reproducibility papers",
    "sp": "short papers",
    "si": "sirip 2024 (industry track)",
}


def extract_doi(text: str) -> str:
    """文字列中から DOI を抽出する。見つからなければ空文字。"""
    match = DOI_PATTERN.search(text or "")
    return match.group(0).lower() if match else ""


def fetch_jsonl(url: str, timeout: int) -> str:
    """指定 URL から JSONL テキストを取得する。"""
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def build_author_label(author: dict) -> str:
    """著者辞書を既存 builder と互換な表示文字列へ整形する。"""
    name = str(author.get("name", "")).strip()
    affiliation = str(author.get("affiliation", "")).strip()
    if name and affiliation:
        return f"{name} ({affiliation})"
    return name or affiliation


def parse_records(jsonl_text: str) -> list[dict]:
    """SIGIR 2024 JSONL から公開対象トラックのみを抽出する。"""
    records: list[dict] = []
    for line in jsonl_text.splitlines():
        line = line.strip()
        if not line:
            continue

        entry = json.loads(line)
        submission_id = str(entry.get("submssion_id", "")).strip()
        prefix = submission_id[:2].lower()
        section = GROUP_NAMES.get(prefix)
        if not section:
            continue

        title = str(entry.get("title", "")).strip()
        if not title:
            continue

        authors = [
            author_label
            for author_label in (build_author_label(author) for author in entry.get("authors", []))
            if author_label
        ]
        records.append(
            {
                "title": title,
                "section": section,
                "doi": extract_doi(title),
                "authors": authors,
            }
        )
    return records


def main() -> None:
    """SIGIR 2024 論文リストを JSON へ保存する。"""
    parser = argparse.ArgumentParser(description="Build SIGIR 2024 accepted papers JSON")
    parser.add_argument("--url", default=DEFAULT_URL, help="Accepted papers page URL")
    parser.add_argument("--jsonl-url", default=DEFAULT_JSONL_URL, help="JSONL data source URL")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/accepted_papers.json"),
        help="Output JSON path",
    )
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds")
    args = parser.parse_args()

    print(f"📡 Fetching {args.jsonl_url}")
    jsonl_text = fetch_jsonl(args.jsonl_url, args.timeout)
    records = parse_records(jsonl_text)

    payload = {
        "conference_id": "sigir",
        "venue": "SIGIR",
        "year": 2024,
        "source_url": args.url,
        "dblp_query": "toc:db/conf/sigir/sigir2024.bht:",
        "papers": records,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✨ Parsed {len(records)} records -> {args.output}")


if __name__ == "__main__":
    main()
