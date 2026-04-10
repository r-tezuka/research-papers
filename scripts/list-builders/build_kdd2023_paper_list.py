#!/usr/bin/env python3
"""KDD 2023 TOC ページから論文リスト（title / section / doi）を抽出して JSON に保存する。"""

import argparse
import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import requests

DEFAULT_URL = "https://kdd.org/kdd2023/wp-content/uploads/2023/08/toc.html"
DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
SECTION_MAP = {
    "session: research track full papers": "research track full papers",
    "session: applied data track full papers": "applied data track full papers",
    "session: hands on tutorials": "",
    "session: lecture style tutorials": "",
    "session: workshop summaries": "",
}


def normalize_space(text: str) -> str:
    """連続空白を 1 つにし、前後空白を除去する。"""
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_title_for_key(title: str) -> str:
    """重複排除用のタイトル正規化キーを作る。"""
    key = normalize_space(title).lower()
    key = re.sub(r"[^\w\s]", "", key)
    return re.sub(r"\s+", " ", key).strip()


def extract_doi(text: str) -> str:
    """文字列中の DOI を抽出する。見つからなければ空文字。"""
    match = DOI_PATTERN.search(text or "")
    return match.group(0).lower() if match else ""


class Kdd2023Parser(HTMLParser):
    """KDD 2023 TOC HTML を解析するパーサー。"""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[dict] = []

        self._current_section = ""
        self._capture_h2 = False
        self._h2_parts: list[str] = []

        self._capture_title = False
        self._title_parts: list[str] = []
        self._current_doi = ""

        self._seen_keys: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {k: (v or "") for k, v in attrs}

        if tag == "h2":
            self._capture_h2 = True
            self._h2_parts = []
            return

        if tag == "a" and "DLtitleLink" in (attrs_dict.get("class") or ""):
            self._capture_title = True
            self._title_parts = []
            href = html.unescape(attrs_dict.get("href", ""))
            self._current_doi = extract_doi(href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "h2" and self._capture_h2:
            self._capture_h2 = False
            heading = normalize_space(" ".join(self._h2_parts)).lower()
            mapped = SECTION_MAP.get(heading)
            if mapped is not None:
                self._current_section = mapped
            return

        if tag == "a" and self._capture_title:
            self._capture_title = False
            title = normalize_space(" ".join(self._title_parts))
            if not self._current_section or not title:
                self._current_doi = ""
                return

            key = normalize_title_for_key(title)
            if not key or key in self._seen_keys:
                self._current_doi = ""
                return
            self._seen_keys.add(key)

            self.records.append(
                {
                    "title": title,
                    "section": self._current_section,
                    "doi": self._current_doi,
                }
            )
            self._current_doi = ""

    def handle_data(self, data: str) -> None:
        text = normalize_space(html.unescape(data))
        if not text:
            return

        if self._capture_h2:
            self._h2_parts.append(text)

        if self._capture_title:
            self._title_parts.append(text)


def fetch_html(url: str, timeout: int = 30) -> str:
    """指定 URL から HTML を取得する。"""
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def parse_records(html_text: str) -> list[dict]:
    """HTML 文字列から論文候補レコードを抽出する。"""
    parser = Kdd2023Parser()
    parser.feed(html_text)
    return parser.records


def main() -> None:
    """KDD 2023 論文リストを JSON として保存する。"""
    parser = argparse.ArgumentParser(description="Build KDD 2023 accepted papers JSON from TOC page")
    parser.add_argument("--url", default=DEFAULT_URL, help="KDD 2023 TOC page URL")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/KDD-23/accepted_papers.json"),
        help="Output JSON path",
    )
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds")
    args = parser.parse_args()

    print(f"📡 Fetching {args.url}")
    html_text = fetch_html(args.url, timeout=args.timeout)
    records = parse_records(html_text)

    payload = {
        "conference_id": "kdd",
        "venue": "KDD",
        "year": 2023,
        "source_url": args.url,
        "dblp_query": "toc:db/conf/kdd/kdd2023.bht:",
        "papers": records,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✨ Parsed {len(records)} records -> {args.output}")


if __name__ == "__main__":
    main()
