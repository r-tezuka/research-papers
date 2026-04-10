#!/usr/bin/env python3
"""WWW 2024 accepted pages から論文リスト（title / section / doi）を抽出して JSON に保存する。"""

import argparse
import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import requests

TARGET_URLS: list[tuple[str, str]] = [
    ("https://www2024.thewebconf.org/accepted/research-tracks/", "research tracks"),
    ("https://www2024.thewebconf.org/accepted/industry/", "industry"),
    ("https://www2024.thewebconf.org/accepted/web4good/", "web4good"),
    ("https://www2024.thewebconf.org/accepted/short-papers/", "short papers"),
    ("https://www2024.thewebconf.org/accepted/demo/", "demo"),
    ("https://www2024.thewebconf.org/accepted/resource/", "resource"),
    ("https://www2024.thewebconf.org/accepted/health-day/", "health day"),
    ("https://www2024.thewebconf.org/accepted/history-web/", "history web"),
    ("https://www2024.thewebconf.org/accepted/phd-symposium/", "phd symposium"),
]
DEFAULT_SOURCE_URL = "https://www2024.thewebconf.org/accepted/"
DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
SKIP_PREFIXES = (
    "accepted papers",
    "the submission versions",
    "camera-ready versions",
    "free access in perpetuity",
)


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


def looks_like_paper_title(text: str) -> bool:
    """論文タイトルとして妥当そうな文字列かを簡易判定する。"""
    if not text:
        return False
    lower = text.lower()
    if any(lower.startswith(prefix) for prefix in SKIP_PREFIXES):
        return False
    if len(text) < 8:
        return False
    if text.count(" ") < 1:
        return False
    return True


class Www2024CardParser(HTMLParser):
    """WWW 2024 accepted page の card ブロックを解析するパーサー。"""

    def __init__(self, section: str) -> None:
        super().__init__()
        self.section = section
        self.records: list[dict] = []

        self._in_card = False
        self._card_depth = 0
        self._in_card_title = False
        self._capture_title = False

        self._title_parts: list[str] = []
        self._doi = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrd = {k: (v or "") for k, v in attrs}

        if not self._in_card and tag == "div":
            class_tokens = set((attrd.get("class") or "").split())
            if "card" in class_tokens:
                self._in_card = True
                self._card_depth = 1
                self._title_parts = []
                self._doi = ""
                return

        if self._in_card:
            self._card_depth += 1

            if tag == "div" and "card-title" in (attrd.get("class") or ""):
                self._in_card_title = True

            if self._in_card_title and tag == "strong":
                self._capture_title = True

            if tag == "a":
                href = html.unescape(attrd.get("href", ""))
                doi = extract_doi(href)
                if doi and not self._doi:
                    self._doi = doi

    def handle_endtag(self, tag: str) -> None:
        if self._in_card_title and tag == "strong":
            self._capture_title = False

        if self._in_card_title and tag == "div":
            self._in_card_title = False

        if self._in_card:
            self._card_depth -= 1
            if self._card_depth <= 0:
                self._finalize_card()
                self._in_card = False
                self._card_depth = 0

    def handle_data(self, data: str) -> None:
        if self._capture_title:
            text = normalize_space(html.unescape(data))
            if text:
                self._title_parts.append(text)

    def _finalize_card(self) -> None:
        title = normalize_space(" ".join(self._title_parts))
        if not looks_like_paper_title(title):
            return
        self.records.append({"title": title, "section": self.section, "doi": self._doi})


def fetch_html(url: str, timeout: int = 30) -> str:
    """指定 URL から HTML を取得する。"""
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def parse_page_records(html_text: str, section: str) -> list[dict]:
    """単一ページから論文候補レコードを抽出する。"""
    parser = Www2024CardParser(section=section)
    parser.feed(html_text)
    return parser.records


def build_records(timeout: int) -> list[dict]:
    """全対象 URL を巡回してレコードを抽出する。"""
    records: list[dict] = []
    seen_keys: set[str] = set()

    for url, section in TARGET_URLS:
        print(f"📡 Fetching {url}")
        html_text = fetch_html(url, timeout=timeout)
        page_records = parse_page_records(html_text, section)

        for rec in page_records:
            key = normalize_title_for_key(rec["title"])
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            records.append(rec)

    return records


def main() -> None:
    """WWW 2024 論文リストを JSON として保存する。"""
    parser = argparse.ArgumentParser(description="Build WWW 2024 accepted papers JSON from accepted pages")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/WWW-24/accepted_papers.json"),
        help="Output JSON path",
    )
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds")
    args = parser.parse_args()

    records = build_records(timeout=args.timeout)

    payload = {
        "conference_id": "www",
        "venue": "WWW",
        "year": 2024,
        "source_url": DEFAULT_SOURCE_URL,
        "dblp_query": "toc:db/conf/www/www2024.html",
        "papers": records,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✨ Parsed {len(records)} records -> {args.output}")


if __name__ == "__main__":
    main()
