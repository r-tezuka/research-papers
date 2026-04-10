#!/usr/bin/env python3
"""KDD 2024 ページから論文リスト（title / section / doi）を抽出して JSON に保存する。"""

import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import requests

DEFAULT_URL = "https://kdd2024.kdd.org/research-track-papers/"
DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
SKIP_PREFIXES = (
    "copyright",
    "proceedings",
    "track chairs",
    "program committee",
    "call for",
)


def normalize_space(text: str) -> str:
    """連続空白を 1 つにし、前後空白を除去する。"""
    return re.sub(r"\s+", " ", text or "").strip()


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
    if len(text) < 12:
        return False
    if text.count(" ") < 2:
        return False
    return True


def normalize_title_for_key(title: str) -> str:
    """重複排除用のタイトル正規化キーを作る。"""
    key = normalize_space(title).lower()
    key = re.sub(r"[^\w\s]", "", key)
    return re.sub(r"\s+", " ", key).strip()


class KddPaperParser(HTMLParser):
    """KDD 2024 Research Track ページ向けの HTML パーサー。"""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[dict] = []
        self._current_section = "research track papers"
        self._seen_keys: set[str] = set()

        self._in_main = False
        self._main_depth = 0

        self._in_p = False
        self._p_parts: list[str] = []

        self._in_td = False
        self._td_parts: list[str] = []
        self._td_has_strong = False
        self._strong_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {k: (v or "") for k, v in attrs}

        if tag == "main" and attrs_dict.get("id", "") == "content":
            self._in_main = True
            self._main_depth = 1
            return

        if not self._in_main:
            return

        if tag == "main":
            self._main_depth += 1
            return

        if tag == "p":
            self._in_p = True
            self._p_parts = []
            return

        if tag == "td":
            self._in_td = True
            self._td_parts = []
            self._td_has_strong = False
            self._strong_depth = 0
            return

        if tag == "strong" and self._in_td:
            self._td_has_strong = True
            self._strong_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self._in_main and tag == "main":
            self._main_depth -= 1
            if self._main_depth <= 0:
                self._in_main = False
                self._main_depth = 0
            return

        if not self._in_main:
            return

        if tag == "p" and self._in_p:
            self._in_p = False
            p_text = normalize_space("".join(self._p_parts))
            if p_text:
                match = re.search(r"Theme:\s*(.*?)\s*Session Chair:", p_text, flags=re.IGNORECASE)
                if match:
                    section = normalize_space(match.group(1)).lower()
                    if section:
                        self._current_section = section
            return

        if tag == "strong" and self._in_td and self._strong_depth > 0:
            self._strong_depth -= 1
            return

        if tag == "td" and self._in_td:
            raw = normalize_space("".join(self._td_parts))
            self._in_td = False
            self._td_parts = []

            if not self._td_has_strong:
                return
            if not raw:
                return

            doi = extract_doi(raw)
            title = normalize_space(DOI_PATTERN.sub("", raw))
            if not looks_like_paper_title(title):
                return

            if title.lower().startswith("theme:") or "session chair:" in title.lower():
                return

            key = normalize_title_for_key(title)
            if key in self._seen_keys:
                return
            self._seen_keys.add(key)

            self.records.append(
                {
                    "title": title,
                    "section": self._current_section,
                    "doi": doi,
                }
            )

    def handle_data(self, data: str) -> None:
        if not self._in_main:
            return

        text = normalize_space(data)
        if not text:
            return

        if self._in_p:
            self._p_parts.append(text)

        if self._in_td and self._strong_depth > 0:
            self._td_parts.append(text)


def fetch_html(url: str, timeout: int = 30) -> str:
    """指定 URL から HTML を取得する。"""
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def parse_records(html: str) -> list[dict]:
    """HTML 文字列から論文候補レコードを抽出する。"""
    parser = KddPaperParser()
    parser.feed(html)
    return parser.records


def main() -> None:
    """KDD 2024 論文リストを JSON として保存する。"""
    parser = argparse.ArgumentParser(description="Build KDD 2024 paper list JSON from web page")
    parser.add_argument("--url", default=DEFAULT_URL, help="KDD 2024 paper list page URL")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/KDD-24/accepted_papers.json"),
        help="Output JSON path",
    )
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds")
    args = parser.parse_args()

    print(f"📡 Fetching {args.url}")
    html = fetch_html(args.url, args.timeout)
    records = parse_records(html)

    payload = {
        "conference_id": "kdd",
        "venue": "KDD",
        "year": 2024,
        "source_url": args.url,
        "dblp_query": "toc:db/conf/kdd/kdd2024.bht:",
        "papers": records,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✨ Parsed {len(records)} records -> {args.output}")


if __name__ == "__main__":
    main()
