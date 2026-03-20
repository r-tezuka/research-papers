#!/usr/bin/env python3
"""CIKM 2025 ページから論文リスト（title / section / doi）を抽出して JSON に保存する。"""

import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import requests

DEFAULT_URL = "https://cikm2025.org/program/accepted-papers"
DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)


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


class CikmPaperParser(HTMLParser):
    """CIKM 2025 向けの HTML パーサー。"""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[dict] = []
        self._in_table = False
        self._in_tr = False
        self._in_td = False
        self._current_row: list[str] = []
        self._cell_content: list[str] = []
        self._seen_keys: set[str] = set()
        self._skip_first_row = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._in_table = True
        elif tag == "tr" and self._in_table:
            self._in_tr = True
            self._current_row = []
            self._skip_first_row = False
        elif tag == "td" and self._in_tr:
            self._in_td = True
            self._cell_content = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "table":
            self._in_table = False
        elif tag == "tr" and self._in_tr:
            self._in_tr = False
            # Process row
            if len(self._current_row) >= 2:
                # Skip header row
                if self._current_row[1].lower() in ("title", "titles"):
                    return
                
                paper_id = self._current_row[0].strip()
                title = self._current_row[1].strip()
                
                if not title or not looks_like_paper_title(title):
                    return
                
                key = normalize_title_for_key(title)
                if key in self._seen_keys:
                    return
                self._seen_keys.add(key)
                
                doi = extract_doi(title)
                
                self.records.append({
                    "title": title,
                    "section": "accepted papers",
                    "doi": doi,
                })
        elif tag == "td" and self._in_td:
            self._in_td = False
            cell_text = normalize_space("".join(self._cell_content))
            self._current_row.append(cell_text)

    def handle_data(self, data: str) -> None:
        text = normalize_space(data)
        if not text:
            return
        if self._in_td:
            self._cell_content.append(text)


def fetch_html(url: str, timeout: int = 30) -> str:
    """指定 URL から HTML を取得する。"""
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def parse_records(html: str) -> list[dict]:
    """HTML 文字列から論文候補レコードを抽出する。"""
    parser = CikmPaperParser()
    parser.feed(html)
    return parser.records


def main() -> None:
    """CIKM 2025 論文リストを JSON として保存する。"""
    parser = argparse.ArgumentParser(description="Build CIKM 2025 paper list JSON from web page")
    parser.add_argument("--url", default=DEFAULT_URL, help="CIKM 2025 paper list page URL")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/CIKM-25/accepted_papers.json"),
        help="Output JSON path",
    )
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds")
    args = parser.parse_args()

    print(f"📡 Fetching {args.url}")
    html = fetch_html(args.url, args.timeout)
    records = parse_records(html)

    payload = {
        "conference_id": "cikm",
        "venue": "CIKM",
        "year": 2025,
        "source_url": args.url,
        "dblp_query": "toc:db/conf/cikm/cikm2025.bht:",
        "papers": records,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✨ Parsed {len(records)} records -> {args.output}")


if __name__ == "__main__":
    main()
