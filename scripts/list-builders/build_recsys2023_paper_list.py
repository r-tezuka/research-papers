#!/usr/bin/env python3
"""RecSys 2023 Accepted Contributions ページから論文リストを抽出して JSON に保存する。"""

import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import requests

DEFAULT_URL = "https://recsys.acm.org/recsys23/accepted-contributions/"
DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)


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


class RecSys2023Parser(HTMLParser):
    """RecSys 2023 Accepted Contributions ページ向けパーサー。"""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[dict] = []

        self._tab_map: dict[str, str] = {}
        self._in_tabs_menu = False
        self._in_tab_anchor = False
        self._tab_anchor_target = ""
        self._tab_anchor_text_parts: list[str] = []

        self._active_content_id = ""
        self._active_content_div_depth = 0
        self._current_section = ""
        self._accordion_depth = 0

        self._in_item = False
        self._item_text_parts: list[str] = []
        self._capture_title = False

        self._seen_keys: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrd = {k: v for k, v in attrs if v is not None}

        if tag == "ul" and "tabs-menu" in (attrd.get("class") or ""):
            self._in_tabs_menu = True

        if self._in_tabs_menu and tag == "a":
            href = attrd.get("href", "")
            if href.startswith("#content-tab-"):
                self._in_tab_anchor = True
                self._tab_anchor_target = href.lstrip("#")
                self._tab_anchor_text_parts = []

        if tag == "div":
            content_id = attrd.get("id", "")
            css_class = attrd.get("class", "")
            if self._active_content_id:
                self._active_content_div_depth += 1
            elif content_id.startswith("content-tab-") and "tabs-content" in css_class:
                self._active_content_id = content_id
                self._active_content_div_depth = 1
                section = self._tab_map.get(content_id, "")
                self._current_section = normalize_space(section).lower()

        if tag == "ul" and "accordion" in (attrd.get("class") or "") and self._active_content_id:
            self._accordion_depth += 1

        if tag == "li" and self._accordion_depth > 0 and self._active_content_id:
            self._in_item = True
            self._capture_title = True
            self._item_text_parts = []

        if tag == "br" and self._in_item:
            self._capture_title = False

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_tab_anchor:
            tab_name = normalize_space("".join(self._tab_anchor_text_parts))
            if self._tab_anchor_target and tab_name:
                self._tab_map[self._tab_anchor_target] = tab_name
            self._in_tab_anchor = False
            self._tab_anchor_target = ""
            self._tab_anchor_text_parts = []

        if tag == "ul":
            if self._in_tabs_menu:
                self._in_tabs_menu = False
            elif self._accordion_depth > 0:
                self._accordion_depth -= 1

        if tag == "li" and self._in_item:
            raw_title = normalize_space("".join(self._item_text_parts))
            self._in_item = False
            self._capture_title = False
            self._item_text_parts = []

            if not raw_title:
                return

            title = normalize_space(DOI_PATTERN.sub("", raw_title))
            if not title:
                return

            key = normalize_title_for_key(title)
            if not key or key in self._seen_keys:
                return
            self._seen_keys.add(key)

            self.records.append(
                {
                    "title": title,
                    "section": self._current_section,
                    "doi": extract_doi(raw_title),
                }
            )

        if tag == "div" and self._active_content_id:
            self._active_content_div_depth -= 1
            if self._active_content_div_depth <= 0:
                self._active_content_id = ""
                self._active_content_div_depth = 0
                self._current_section = ""

    def handle_data(self, data: str) -> None:
        text = normalize_space(data)
        if not text:
            return

        if self._in_tab_anchor:
            self._tab_anchor_text_parts.append(text)

        if self._in_item and self._capture_title:
            self._item_text_parts.append(text)


def fetch_html(url: str, timeout: int = 30) -> str:
    """指定 URL から HTML を取得する。"""
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def parse_records(html: str) -> list[dict]:
    """HTML 文字列から accepted contributions を抽出する。"""
    parser = RecSys2023Parser()
    parser.feed(html)
    return parser.records


def main() -> None:
    """RecSys 2023 の accepted contributions を JSON へ保存する。"""
    parser = argparse.ArgumentParser(description="Build RecSys 2023 accepted papers JSON")
    parser.add_argument("--url", default=DEFAULT_URL, help="Accepted contributions page URL")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/RecSys-23/accepted_papers.json"),
        help="Output JSON path",
    )
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds")
    args = parser.parse_args()

    print(f"📡 Fetching {args.url}")
    html = fetch_html(args.url, args.timeout)
    records = parse_records(html)

    payload = {
        "conference_id": "recsys",
        "venue": "RecSys",
        "year": 2023,
        "source_url": args.url,
        "dblp_query": "toc:db/conf/recsys/recsys2023.bht:",
        "papers": records,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✨ Parsed {len(records)} records -> {args.output}")


if __name__ == "__main__":
    main()
