#!/usr/bin/env python3
"""WSDM 2023 ページから論文リスト（title / section / doi）を抽出して JSON に保存する。"""

import argparse
import html
import json
import re
from pathlib import Path

import requests

DEFAULT_URL = "https://www.wsdm-conference.org/2023/program/accepted-papers"
DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
SKIP_PREFIXES = (
    "copyright",
    "proceedings",
    "track chairs",
    "program committee",
    "call for",
    "menu",
    "imprint",
    "privacy",
    "cookie",
)
ARTICLE_PATTERN = re.compile(
    r'<article[^>]*data-history-node-id="64"[^>]*>(.*?)</article>',
    re.IGNORECASE | re.DOTALL,
)
H4_TITLE_PATTERN = re.compile(r"<h4[^>]*>(.*?)</h4>", re.IGNORECASE | re.DOTALL)
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")


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
    if text.count("(") > 3:
        return False
    return True


def normalize_title_for_key(title: str) -> str:
    """重複排除用のタイトル正規化キーを作る。"""
    key = normalize_space(title).lower()
    key = re.sub(r"[^\w\s]", "", key)
    return re.sub(r"\s+", " ", key).strip()


def clean_html_text(text: str) -> str:
    """HTML タグとエンティティを除去してテキスト化する。"""
    no_tags = HTML_TAG_PATTERN.sub(" ", text or "")
    return normalize_space(html.unescape(no_tags))


def extract_article_content(html_text: str) -> str:
    """Accepted papers の article 本文を抽出する。"""
    match = ARTICLE_PATTERN.search(html_text)
    return match.group(1) if match else html_text


def parse_titles_from_body(content_html: str) -> list[str]:
    """本文中の h4 タグからタイトル候補を抽出する。"""
    titles: list[str] = []
    seen_keys: set[str] = set()
    for raw in H4_TITLE_PATTERN.findall(content_html):
        title = clean_html_text(raw)
        if not looks_like_paper_title(title):
            continue
        key = normalize_title_for_key(title)
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        titles.append(title)
    return titles


def fetch_html(url: str, timeout: int = 30) -> str:
    """指定 URL から HTML を取得する。"""
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def parse_records(html_text: str) -> list[dict]:
    """HTML 文字列から論文候補レコードを抽出する。"""
    content_html = extract_article_content(html_text)
    if not content_html:
        return []

    titles = parse_titles_from_body(content_html)
    return [{"title": title, "section": "accepted papers", "doi": extract_doi(title)} for title in titles]


def main() -> None:
    """WSDM 2023 論文リストを JSON として保存する。"""
    parser = argparse.ArgumentParser(description="Build WSDM 2023 paper list JSON from web page")
    parser.add_argument("--url", default=DEFAULT_URL, help="WSDM 2023 paper list page URL")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/WSDM-23/accepted_papers.json"),
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
        "year": 2023,
        "source_url": args.url,
        "dblp_query": "toc:db/conf/wsdm/wsdm2023.bht:",
        "papers": records,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✨ Parsed {len(records)} records -> {args.output}")


if __name__ == "__main__":
    main()
