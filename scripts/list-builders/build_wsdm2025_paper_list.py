#!/usr/bin/env python3
"""WSDM 2025 ページから論文リスト（title / section / doi）を抽出して JSON に保存する。"""

import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import requests

DEFAULT_URL = "https://www.wsdm-conference.org/2025/accepted-papers/"
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


def normalize_space(text: str) -> str:
    """連続空白を 1 つにし、前後空白を除去する。"""
    return re.sub(r"\s+", " ", text or "").strip()


def extract_doi(text: str) -> str:
    """文字列中の DOI を抽出する。見つからなければ空文字。"""
    match = DOI_PATTERN.search(text or "")
    return match.group(0).lower() if match else ""


def extract_paper_title(text: str) -> str:
    """論文タイトルと著者情報から、タイトルのみを抽出する。
    
    WSDM ウェブページでは、タイトルと著者情報が連結されている。
    パターン: タイトル + FirstName LastName (Institution); ...
    """
    import re
    
    # Strategy: Find where the author names begin
    # Author pattern: PascalCase Name (likely a person's name, not part of title)
    # followed by optional parentheses (institution) or semicolon and more authors
    
    # Look for the pattern: [A-Z][a-z]+ [A-Z][a-z]+ \( 
    # This is: FirstName LastName (Institution
    # But be careful not to split acronyms or proper nouns in titles
    
    # Key observation: Author sections usually start with a first name followed
    # by a last name, with an optional * or parentheses afterward
    # E.g., "Yoonhyuk Choi (Seoul..." or "jie wang (university..."
    
    # Look for the transition point - usually the first name (after title ends)
    # Titles typically end with a complete phrase with multiple words
    # Authors start with Name Surname (unless it's a lowercase name like "jie wang")
    
    # Match pattern: word(s) followed by a name-like pattern and opening paren or semicolon
    # The name pattern will have a capital letter followed by lowercase(s), space, repeat
    
    # More reliable pattern: look for where we have text ending with a capital letter
    # followed directly by another capital letter (author first name) without space
    # OR look for institution names in parentheses and backtrack
    
    # Try to find the first occurrence of "Name (Institution" or "name (" pattern
    # that looks like it starts the author section
    
    # Regex to find where author info likely starts
    # Pattern: any text, then a Name-like token (capital start) + possibly lowercase,
    # that's preceded by lowercase letter (end of title word), then we look for (
    
    # Find the transition point more carefully:
    # Authors often appear as: word(without space)-CapitalName or word CapitalName
    # Let's look for this pattern and find where it begins
    
    # Look for pattern like: "TitleText" + "PersonName(Institution" or close variant
    match = re.search(r'^(.+?)([A-Z][a-z]+\s+[A-Z][a-z]+\s*[\(\*;]|[a-z]+\s+[a-z]+\s*[\(\*;])', text)
    if match:
        title = match.group(1).strip()
        if len(title) > 12 and title.count(" ") >= 2:
            return title
    
    # Fallback: try splitting on opening parenthesis (institution markers)
    parts = text.split('(')
    if len(parts) > 1:
        title_candidate = parts[0].strip()
        # Remove any trailing author first name that got concatenated
        # Author names at end are typically: CapitalName or repeated pattern
        title_candidate = re.sub(r'\s+[A-Z][a-z]*(?:\s+[A-Z][a-z]*)?$', '', title_candidate)
        title_candidate = re.sub(r'\s+[a-z]+\s+[a-z]+$', '', title_candidate)  # lowercase names
        
        if len(title_candidate) > 12 and title_candidate.count(" ") >= 2:
            return title_candidate
    
    return text


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
    # Skip if it's mostly institution names in parentheses (author info)
    if text.count("(") > 3:
        return False
    return True


def normalize_title_for_key(title: str) -> str:
    """重複排除用のタイトル正規化キーを作る。"""
    key = normalize_space(title).lower()
    key = re.sub(r"[^\w\s]", "", key)
    return re.sub(r"\s+", " ", key).strip()


class WsdmPaperParser(HTMLParser):
    """WSDM 2025 向けの HTML パーサー。"""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[dict] = []
        self._current_section = ""
        self._capture_heading = False
        self._capture_item = False
        self._item_parts: list[str] = []
        self._seen_keys: set[str] = set()
        self._in_accepted_papers_section = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"h1", "h2", "h3", "h4"}:
            self._capture_heading = True
        elif tag in {"li", "p", "td", "div"}:
            self._capture_item = True
            self._item_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"h1", "h2", "h3", "h4"}:
            self._capture_heading = False
        elif tag in {"li", "p", "td", "div"} and self._capture_item:
            raw = normalize_space("".join(self._item_parts))
            self._capture_item = False
            if not raw:
                return

            # Only store if we're in the accepted papers section
            if not self._in_accepted_papers_section:
                return

            doi = extract_doi(raw)
            # Extract title from title+author string
            title = extract_paper_title(normalize_space(DOI_PATTERN.sub("", raw)))
            if not looks_like_paper_title(title):
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
        text = normalize_space(data)
        if not text:
            return
        if self._capture_heading:
            self._current_section = text.lower()
            # Mark that we've found the accepted papers section
            if "accepted papers" in self._current_section:
                self._in_accepted_papers_section = True
        elif self._capture_item and self._in_accepted_papers_section:
            self._item_parts.append(text)


def fetch_html(url: str, timeout: int = 30) -> str:
    """指定 URL から HTML を取得する。"""
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def parse_records(html: str) -> list[dict]:
    """HTML 文字列から論文候補レコードを抽出する。"""
    parser = WsdmPaperParser()
    parser.feed(html)
    return parser.records


def main() -> None:
    """WSDM 2025 論文リストを JSON として保存する。"""
    parser = argparse.ArgumentParser(description="Build WSDM 2025 paper list JSON from web page")
    parser.add_argument("--url", default=DEFAULT_URL, help="WSDM 2025 paper list page URL")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/WSDM-25/accepted_papers.json"),
        help="Output JSON path",
    )
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds")
    args = parser.parse_args()

    print(f"📡 Fetching {args.url}")
    html = fetch_html(args.url, args.timeout)
    records = parse_records(html)

    payload = {
        "conference_id": "wsdm",
        "venue": "WSDM",
        "year": 2025,
        "source_url": args.url,
        "dblp_query": "toc:db/conf/wsdm/wsdm2025.bht:",
        "papers": records,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✨ Parsed {len(records)} records -> {args.output}")


if __name__ == "__main__":
    main()
