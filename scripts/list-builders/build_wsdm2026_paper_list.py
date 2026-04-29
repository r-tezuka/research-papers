#!/usr/bin/env python3
"""WSDM 2026 ページから論文リスト（title / section / doi）を抽出して JSON に保存する。"""

import argparse
import html
import json
import re
from pathlib import Path

import requests

DEFAULT_URL = "https://wsdm-conference.org/2026/index.php/accepted-papers/"
DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
SECTION_HEADING_PATTERN = re.compile(r"<h4[^>]*>\s*(Full Papers|Short Papers)\s*</h4>", re.IGNORECASE | re.DOTALL)
PARAGRAPH_PATTERN = re.compile(r"<p[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
SECTION_NAME_MAP = {
    "full papers": "full papers",
    "short papers": "short papers",
}
SKIP_PREFIXES = (
    "copyright",
    "proceedings",
    "call for",
    "full papers",
    "short papers",
)


def normalize_space(text: str) -> str:
    """連続空白を 1 つにし、前後空白を除去する。"""
    return re.sub(r"\s+", " ", text or "").strip()


def extract_doi(text: str) -> str:
    """文字列中の DOI を抽出する。見つからなければ空文字。"""
    match = DOI_PATTERN.search(text or "")
    return match.group(0).lower() if match else ""


def normalize_title_for_key(title: str) -> str:
    """重複排除用のタイトル正規化キーを作る。"""
    key = normalize_space(title).lower()
    key = re.sub(r"[^\w\s]", "", key)
    return re.sub(r"\s+", " ", key).strip()


def clean_html_text(text: str) -> str:
    """HTML タグとエンティティを除去してテキスト化する。"""
    no_tags = HTML_TAG_PATTERN.sub(" ", text or "")
    return normalize_space(html.unescape(no_tags))


def looks_like_paper_line(text: str) -> bool:
    """論文行として妥当そうな文字列かを簡易判定する。"""
    if not text:
        return False
    lower = text.lower()
    if any(lower.startswith(prefix) for prefix in SKIP_PREFIXES):
        return False
    if len(text) < 20:
        return False
    if ". " not in text:
        return False
    return True


def split_authors_and_title(text: str) -> tuple[str, str]:
    """`著者列. タイトル` 形式の行を分割する。"""
    if ". " not in text:
        return "", ""

    authors, title = text.rsplit(". ", 1)
    authors = normalize_space(authors)
    title = normalize_space(title)
    return authors, title


def parse_records(html_text: str) -> list[dict]:
    """HTML 文字列から論文候補レコードを抽出する。"""
    records: list[dict] = []
    seen_keys: set[str] = set()

    section_matches = list(SECTION_HEADING_PATTERN.finditer(html_text))
    for index, match in enumerate(section_matches):
        raw_section = clean_html_text(match.group(1))
        section = SECTION_NAME_MAP.get(normalize_space(raw_section).lower(), "")
        if not section:
            continue

        start = match.end()
        end = section_matches[index + 1].start() if index + 1 < len(section_matches) else len(html_text)
        section_html = html_text[start:end]

        for raw_paragraph in PARAGRAPH_PATTERN.findall(section_html):
            line = clean_html_text(raw_paragraph)
            if not looks_like_paper_line(line):
                continue

            _, title = split_authors_and_title(line)
            if not title:
                continue

            key = normalize_title_for_key(title)
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)

            records.append({"title": title, "section": section, "doi": extract_doi(line)})

    return records


def fetch_html(url: str, timeout: int = 30) -> str:
    """指定 URL から HTML を取得する。"""
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def main() -> None:
    """WSDM 2026 論文リストを JSON として保存する。"""
    parser = argparse.ArgumentParser(description="Build WSDM 2026 paper list JSON from web page")
    parser.add_argument("--url", default=DEFAULT_URL, help="WSDM 2026 paper list page URL")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/WSDM-26/accepted_papers.json"),
        help="Output JSON path",
    )
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds")
    args = parser.parse_args()

    print(f"📡 Fetching {args.url}")
    html_text = fetch_html(args.url, args.timeout)
    records = parse_records(html_text)

    payload = {
        "conference_id": "wsdm",
        "venue": "WSDM",
        "year": 2026,
        "source_url": args.url,
        "dblp_query": "toc:db/conf/wsdm/wsdm2026.bht:",
        "papers": records,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✨ Parsed {len(records)} records -> {args.output}")


if __name__ == "__main__":
    main()
