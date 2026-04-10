#!/usr/bin/env python3
"""SIGIR 2023 Accepted Papers 各ページから論文リストを抽出して JSON に保存する。"""

import argparse
import html
import json
import re
from pathlib import Path

import requests

DEFAULT_SOURCES = {
    "full papers": "https://sigir.org/sigir2023/program/accepted-papers/full-papers/",
    "short papers": "https://sigir.org/sigir2023/program/accepted-papers/short-papers/",
    "perspectives papers": "https://sigir.org/sigir2023/program/accepted-papers/perspectives-papers/",
    "reproducibility papers": "https://sigir.org/sigir2023/program/accepted-papers/reproducibility-papers/",
    "demo papers": "https://sigir.org/sigir2023/program/accepted-papers/demo-papers/",
    "resource papers": "https://sigir.org/sigir2023/program/accepted-papers/resource-papers/",
    "sirip - industrial track": "https://sigir.org/sigir2023/program/accepted-papers/sirip-industrial-track/",
    "doctoral consortium papers": "https://sigir.org/sigir2023/program/accepted-papers/doctoral-consortium-papers/",
}

DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
ENTRY_PATTERN = re.compile(
    r"<p>\s*<strong>\s*●\s*(.*?)\s*</strong>\s*<br\s*/?>\s*(.*?)\s*</p>",
    re.IGNORECASE | re.DOTALL,
)
TAG_PATTERN = re.compile(r"<[^>]+>")


def normalize_space(text: str) -> str:
    """連続空白を 1 つにし、前後空白を削る。"""
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_title_for_key(title: str) -> str:
    """重複排除のためタイトルを正規化する。"""
    key = normalize_space(title).lower()
    key = re.sub(r"[^\w\s]", "", key)
    return re.sub(r"\s+", " ", key).strip()


def extract_doi(text: str) -> str:
    """文字列中の DOI を抽出する。"""
    match = DOI_PATTERN.search(text or "")
    return match.group(0).lower() if match else ""


def strip_tags(text: str) -> str:
    """HTML タグを除去してプレーンテキストへ変換する。"""
    return normalize_space(html.unescape(TAG_PATTERN.sub(" ", text or "")))


def parse_records(html_text: str, section: str, seen_keys: set[str]) -> list[dict]:
    """1ページ分の HTML からレコードを抽出する。"""
    records: list[dict] = []
    for title_html, authors_html in ENTRY_PATTERN.findall(html_text):
        title = strip_tags(title_html)
        if not title:
            continue

        key = normalize_title_for_key(title)
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)

        author_text = strip_tags(authors_html)
        authors = [normalize_space(part) for part in author_text.split(",") if normalize_space(part)]

        records.append(
            {
                "title": title,
                "section": section,
                "doi": extract_doi(title),
                "authors": authors,
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
    """SIGIR 2023 accepted papers を JSON へ保存する。"""
    parser = argparse.ArgumentParser(description="Build SIGIR 2023 accepted papers JSON")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/SIGIR-23/accepted_papers.json"),
        help="Output JSON path",
    )
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds")
    args = parser.parse_args()

    all_records: list[dict] = []
    seen_keys: set[str] = set()

    for section, url in DEFAULT_SOURCES.items():
        print(f"📡 Fetching {url}")
        html_text = fetch_html(url, timeout=args.timeout)
        all_records.extend(parse_records(html_text, section, seen_keys))

    payload = {
        "conference_id": "sigir",
        "venue": "SIGIR",
        "year": 2023,
        "source_url": list(DEFAULT_SOURCES.values()),
        "dblp_query": "toc:db/conf/sigir/sigir2023.bht:",
        "papers": all_records,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✨ Parsed {len(all_records)} records -> {args.output}")


if __name__ == "__main__":
    main()
