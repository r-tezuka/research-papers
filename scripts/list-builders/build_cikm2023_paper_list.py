#!/usr/bin/env python3
"""CIKM 2023 accepted papers ページから論文リストを抽出して JSON に保存する。"""

import argparse
import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import requests

DEFAULT_URL = "https://uobevents.eventsair.com/cikm2023/accepted-papers"
DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
SECTION_MAP = {
    "full papers": "full research papers",
    "short papers": "short research reports",
    "applied research papers": "applied research papers",
    "resource papers": "resource papers",
    "demo papers": "demonstration papers",
    "doctoral consortium": "",
    "industry day": "",
    "tutorial proposals": "",
    "workshop proposals": "",
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
    """文字列中から DOI を抽出する。見つからなければ空文字。"""
    match = DOI_PATTERN.search(text or "")
    return match.group(0).lower() if match else ""


class Cikm2023Parser(HTMLParser):
    """CIKM 2023 accepted papers ページ向けの HTML パーサー。"""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[dict] = []

        self._current_section = ""

        self._in_p = False
        self._in_b = False
        self._heading_parts: list[str] = []

        self._in_row = False
        self._row_depth = 0
        self._in_td = False
        self._td_parts: list[str] = []
        self._cells: list[str] = []

        self._seen_keys: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "p":
            self._in_p = True
            self._heading_parts = []
        elif self._in_p and tag == "b":
            self._in_b = True

        if tag == "tr":
            self._in_row = True
            self._row_depth = 1
            self._cells = []
            return

        if self._in_row and tag == "tr":
            self._row_depth += 1

        if self._in_row and tag == "td":
            self._in_td = True
            self._td_parts = []

    def handle_endtag(self, tag: str) -> None:
        if self._in_b and tag == "b":
            self._in_b = False

        if self._in_p and tag == "p":
            heading = normalize_space(" ".join(self._heading_parts)).lower()
            mapped = SECTION_MAP.get(heading)
            if mapped is not None:
                self._current_section = mapped
            self._in_p = False
            self._heading_parts = []

        if self._in_td and tag == "td":
            cell_text = normalize_space(html.unescape(" ".join(self._td_parts)))
            self._cells.append(cell_text)
            self._in_td = False
            self._td_parts = []

        if self._in_row and tag == "tr":
            self._row_depth -= 1
            if self._row_depth <= 0:
                self._finalize_row()
                self._in_row = False
                self._row_depth = 0

    def handle_data(self, data: str) -> None:
        text = normalize_space(html.unescape(data))
        if not text:
            return

        if self._in_b:
            self._heading_parts.append(text)

        if self._in_td:
            self._td_parts.append(text)

    def _finalize_row(self) -> None:
        if not self._current_section:
            return
        if len(self._cells) < 2:
            return

        title = normalize_space(self._cells[1])
        if not title:
            return

        key = normalize_title_for_key(title)
        if not key or key in self._seen_keys:
            return
        self._seen_keys.add(key)

        doi = extract_doi(" ".join(self._cells))
        self.records.append(
            {
                "title": title,
                "section": self._current_section,
                "doi": doi,
            }
        )


def fetch_html(url: str, timeout: int = 30) -> str:
    """指定 URL から HTML を取得する。"""
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def parse_records(html_text: str) -> list[dict]:
    """HTML 文字列から論文候補レコードを抽出する。"""
    parser = Cikm2023Parser()
    parser.feed(html_text)
    return parser.records


def main() -> None:
    """CIKM 2023 論文リストを JSON として保存する。"""
    parser = argparse.ArgumentParser(description="Build CIKM 2023 accepted papers JSON from web page")
    parser.add_argument("--url", default=DEFAULT_URL, help="CIKM 2023 accepted papers page URL")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/CIKM-23/accepted_papers.json"),
        help="Output JSON path",
    )
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds")
    args = parser.parse_args()

    print(f"📡 Fetching {args.url}")
    html_text = fetch_html(args.url, timeout=args.timeout)
    records = parse_records(html_text)

    payload = {
        "conference_id": "cikm",
        "venue": "CIKM",
        "year": 2023,
        "source_url": args.url,
        "dblp_query": "toc:db/conf/cikm/cikm2023.bht:",
        "papers": records,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✨ Parsed {len(records)} records -> {args.output}")


if __name__ == "__main__":
    main()
