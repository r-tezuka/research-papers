#!/usr/bin/env python3
"""
SIGIR 2025 Accepted Papers ページから論文リスト（タイトル・著者・セクション）を抽出し、
JSON ファイルに保存する。
"""

import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import requests

ACCEPTED_PAPERS_URL = "https://sigir2025.dei.unipd.it/accepted-papers.html"


class Sigir2025Parser(HTMLParser):
    """SIGIR 2025 Accepted Papers ページ用の HTML パーサー。"""

    def __init__(self):
        super().__init__()
        self.papers: list[dict] = []
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
            c = attrd.get("class", "")
            if "accepted-paper-title" in c:
                self._in_title = True
            elif "accepted-paper-author" in c:
                self._in_author = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "h2":
            self._in_h2 = False
        elif tag == "span":
            self._in_title = False
            self._in_author = False
        elif tag == "li" and self._in_paper_item:
            if self._current_title.strip():
                authors = [
                    a.strip()
                    for a in self._current_author.split(",")
                    if a.strip()
                ]
                self.papers.append({
                    "title": self._current_title.strip(),
                    "section": self._current_section.strip(),
                    "authors": authors,
                })
            self._in_paper_item = False

    def handle_data(self, data: str) -> None:
        if self._in_h2:
            text = data.strip()
            if text and not text.upper().startswith("ACCEPTED"):
                self._current_section = text.lower()
        elif self._in_paper_item and self._in_title:
            self._current_title += data
        elif self._in_paper_item and self._in_author:
            self._current_author += data


def fetch_html(url: str, timeout: int = 30) -> str:
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


def parse_papers(html: str) -> list[dict]:
    parser = Sigir2025Parser()
    parser.feed(html)
    return parser.papers


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SIGIR 2025 Accepted Papers ページから論文リストを JSON に出力する"
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=Path("results/sigir2025_accepted_papers.json"),
        help="出力 JSON ファイルパス（デフォルト: results/sigir2025_accepted_papers.json）",
    )
    parser.add_argument(
        "-u", "--url",
        type=str,
        default=ACCEPTED_PAPERS_URL,
        help="Accepted Papers ページの URL",
    )
    args = parser.parse_args()

    print(f"Fetching {args.url} ...")
    html = fetch_html(args.url)
    papers = parse_papers(html)
    print(f"Parsed {len(papers)} papers.")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(papers, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
