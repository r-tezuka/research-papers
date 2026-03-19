#!/usr/bin/env python3
"""SIGIR 2025 Accepted Papers ページから論文リスト（title / section / doi）を抽出して JSON に保存する。"""

import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import requests

DEFAULT_URL = "https://sigir2025.dei.unipd.it/accepted-papers.html"
DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)


def extract_doi(text: str) -> str:
    """文字列中から DOI を抽出する。見つからなければ空文字。"""
    match = DOI_PATTERN.search(text or "")
    return match.group(0).lower() if match else ""


class Sigir2025Parser(HTMLParser):
    """SIGIR 2025 Accepted Papers ページ向けパーサー。"""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[dict] = []
        self._current_section = ""
        self._in_h2 = False
        self._in_paper_item = False
        self._in_title = False
        self._in_author = False
        self._current_title = ""
        self._current_author = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrd = dict((k, v) for k, v in attrs if v is not None)
        if tag == "h2" and "id" in attrd:
            self._in_h2 = True
            self._current_section = attrd.get("id", "").replace("-", " ")
        elif tag == "li" and attrd.get("class") == "accepted-paper-item":
            self._in_paper_item = True
            self._current_title = ""
            self._current_author = ""
        elif tag == "span":
            css_class = attrd.get("class", "")
            if "accepted-paper-title" in css_class:
                self._in_title = True
            elif "accepted-paper-author" in css_class:
                self._in_author = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "h2":
            self._in_h2 = False
        elif tag == "span":
            self._in_title = False
            self._in_author = False
        elif tag == "li" and self._in_paper_item:
            title = self._current_title.strip()
            if title:
                authors = [author.strip() for author in self._current_author.split(",") if author.strip()]
                self.records.append(
                    {
                        "title": title,
                        "section": self._current_section.strip().lower(),
                        "doi": extract_doi(title),
                        "authors": authors,
                    }
                )
            self._in_paper_item = False

    def handle_data(self, data: str) -> None:
        if self._in_h2:
            text = data.strip()
            if text and not text.upper().startswith("ACCEPTED"):
                self._current_section = text
        elif self._in_paper_item and self._in_title:
            self._current_title += data
        elif self._in_paper_item and self._in_author:
            self._current_author += data


def fetch_html(url: str, timeout: int = 30) -> str:
    """指定 URL から HTML を取得する。"""
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def parse_records(html: str) -> list[dict]:
    """HTML から SIGIR 論文レコードを抽出する。"""
    parser = Sigir2025Parser()
    parser.feed(html)
    return parser.records


def main() -> None:
    """SIGIR 2025 論文リストを JSON へ保存する。"""
    parser = argparse.ArgumentParser(description="Build SIGIR 2025 accepted papers JSON")
    parser.add_argument("--url", default=DEFAULT_URL, help="Accepted papers page URL")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/accepted_papers.json"),
        help="Output JSON path",
    )
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds")
    args = parser.parse_args()

    print(f"📡 Fetching {args.url}")
    html = fetch_html(args.url, args.timeout)
    records = parse_records(html)

    payload = {
        "conference_id": "sigir",
        "venue": "SIGIR",
        "year": 2025,
        "source_url": args.url,
        "dblp_query": "toc:db/conf/sigir/sigir2025.bht:",
        "papers": records,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✨ Parsed {len(records)} records -> {args.output}")


if __name__ == "__main__":
    main()
