#!/usr/bin/env python3
"""CIKM 2024 frontmatter PDF から accepted papers を抽出して JSON に保存する。"""

import argparse
import json
import re
from pathlib import Path

import fitz

# proceedings をダウンロードして使う Ref：https://dl.acm.org/action/showFmPdf?doi=10.1145%2F3627673
DEFAULT_PDF_PATH = Path("local/3627673.fm.pdf")
DEFAULT_START_PAGE = 6
DEFAULT_END_PAGE = 69

ALL_SECTION_MAP = {
    "keynote talks": "",
    "full research papers": "full research papers",
    "short research papers": "short research reports",
    "short research reports": "short research reports",
    "applied research papers": "applied research papers",
    "resource papers": "resource papers",
    "demo papers": "demonstration papers",
    "demonstration papers": "demonstration papers",
    "phd symposium": "",
    "tutorial presentations": "",
    "industry day talks": "",
    "workshops": "",
}

BULLET_RE = re.compile(r"^[•●▪◦·]")


def normalize_space(text: str) -> str:
    """連続空白を 1 つにし、前後空白を除去する。"""
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_title_for_key(title: str) -> str:
    """重複排除用のタイトル正規化キーを作る。"""
    key = normalize_space(title).lower()
    key = re.sub(r"[^\w\s]", "", key)
    return re.sub(r"\s+", " ", key).strip()


def clean_title(raw: str) -> str:
    """目次行から装飾を除去してタイトルを得る。"""
    text = normalize_space(raw.lstrip("•").strip())
    text = re.sub(r"\.{3,}\s*\d+\s*$", "", text)
    text = re.sub(r"\s+\d+\s*$", "", text)
    text = re.sub(r"\.{2,}", " ", text)
    text = normalize_space(text)
    return text


def canonical_section(line: str) -> str | None:
    """目次セクション名を正規化する。非対象は空文字、非セクションは None。"""
    key = normalize_space(line).lower()
    if key in ALL_SECTION_MAP:
        return ALL_SECTION_MAP[key]
    return None


def is_bullet_line(line: str) -> bool:
    """目次の箇条書き行かを判定する。"""
    return bool(BULLET_RE.match(normalize_space(line)))


def looks_like_author_line(line: str) -> bool:
    """著者行らしいかを簡易判定する。"""
    text = normalize_space(line)
    if not text:
        return False
    if "(" in text and ")" in text:
        return True
    if re.fullmatch(r"[ivxlcdm]+", text.lower()):
        return True
    return False


def parse_pdf_records(pdf_path: Path, start_page: int, end_page: int) -> list[dict]:
    """PDF 目次から accepted papers のみ抽出する。ページは 1-indexed 指定。"""
    if start_page < 1 or end_page < start_page:
        raise ValueError("Invalid page range")

    records: list[dict] = []
    seen_keys: set[str] = set()
    current_section = ""

    with fitz.open(pdf_path) as doc:
        page_from = start_page - 1
        page_to = min(end_page - 1, len(doc) - 1)

        for page_idx in range(page_from, page_to + 1):
            lines = [normalize_space(line) for line in doc[page_idx].get_text("text").splitlines()]
            lines = [line for line in lines if line]

            i = 0
            while i < len(lines):
                line = lines[i]
                mapped = canonical_section(line)
                if mapped is not None:
                    current_section = mapped
                    i += 1
                    continue

                if not is_bullet_line(line):
                    i += 1
                    continue

                if not current_section:
                    i += 1
                    continue

                title_parts = [line]
                j = i + 1
                while j < len(lines):
                    nxt = lines[j]
                    nxt_section = canonical_section(nxt)
                    if nxt_section is not None:
                        break
                    if is_bullet_line(nxt):
                        break
                    if looks_like_author_line(nxt):
                        break
                    title_parts.append(nxt)
                    j += 1

                title = clean_title(" ".join(title_parts))
                title_key = normalize_title_for_key(title)
                if title and title_key and title_key not in seen_keys:
                    records.append(
                        {
                            "title": title,
                            "section": current_section,
                            "doi": "",
                        }
                    )
                    seen_keys.add(title_key)

                i = j

    return records


def main() -> None:
    """CIKM 2024 論文リストを JSON として保存する。"""
    parser = argparse.ArgumentParser(description="Build CIKM 2024 accepted papers JSON from frontmatter PDF")
    parser.add_argument(
        "--pdf",
        type=Path,
        default=DEFAULT_PDF_PATH,
        help="Frontmatter PDF path",
    )
    parser.add_argument(
        "--start-page",
        type=int,
        default=DEFAULT_START_PAGE,
        help="Start page of TOC range (1-indexed, inclusive)",
    )
    parser.add_argument(
        "--end-page",
        type=int,
        default=DEFAULT_END_PAGE,
        help="End page of TOC range (1-indexed, inclusive)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/CIKM-24/accepted_papers.json"),
        help="Output JSON path",
    )
    args = parser.parse_args()

    if not args.pdf.exists():
        raise SystemExit(f"PDF not found: {args.pdf}")

    print(f"📄 Parsing {args.pdf} pages {args.start_page}-{args.end_page}")
    records = parse_pdf_records(args.pdf, args.start_page, args.end_page)

    payload = {
        "conference_id": "cikm",
        "venue": "CIKM",
        "year": 2024,
        "dblp_query": "toc:db/conf/cikm/cikm2024.bht:",
        "papers": records,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✨ Parsed {len(records)} records -> {args.output}")


if __name__ == "__main__":
    main()
