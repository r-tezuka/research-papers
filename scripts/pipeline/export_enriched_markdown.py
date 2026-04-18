#!/usr/bin/env python3
"""Enriched JSONL をMarkdown形式に変換する。"""

import argparse
import html
from pathlib import Path

from common import load_jsonl


def build_front_matter(title: str) -> list[str]:
    """Markdown先頭のタイトルと区切りを作る。"""
    return [f"# {title}", "", "---", ""]


def build_entry(record: dict) -> str:
    """1論文分のJSONLレコードをMarkdownセクションへ変換する。"""
    title = html.unescape(record.get("title", "No Title"))
    doi = record.get("doi", "")
    venue = record.get("venue", "")
    section = record.get("section", "")
    abstract = (record.get("abstract") or "").strip()
    sources = record.get("sources", [])
    year = record.get("year", "")

    lines = [f"## {title}"]

    meta_items = []
    if doi:
        meta_items.append(f"**DOI**: https://doi.org/{doi}")
    if venue:
        meta_items.append(f"**Venue**: {venue}")
    if year:
        meta_items.append(f"**Year**: {year}")
    if section:
        meta_items.append(f"**Section**: {section}")
    if sources:
        meta_items.append(f"**Sources**: {', '.join(sources)}")

    if meta_items:
        lines.append("- " + "\n- ".join(meta_items))
    lines.append("")

    if abstract:
        lines.append("### 概要")
        lines.append(abstract)
    else:
        lines.append("### 概要")
        lines.append("*概要が取得されていません*")

    lines.extend(["", "---", ""])
    return "\n".join(lines)


def main() -> None:
    """Enriched JSONL をMarkdown文書へ変換する。"""
    parser = argparse.ArgumentParser(description="Export enriched papers JSONL to Markdown")
    parser.add_argument("--input", default="results/papers_enriched.jsonl", help="Input enriched JSONL file")
    parser.add_argument("--output", default="results/papers_enriched.md", help="Output Markdown path")
    parser.add_argument("--title", default="Enriched Papers", help="Document title")
    parser.add_argument("--sort-by", choices=["title", "section", "year", "venue"], default="section", help="Sort key")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_file():
        raise SystemExit(f"Input file not found: {args.input}")

    records = load_jsonl(args.input)
    if not records:
        print("❌ input is empty")
        return

    if args.sort_by == "title":
        records.sort(key=lambda item: (item.get("title", "").lower(), item.get("year", 0)))
    elif args.sort_by == "year":
        records.sort(key=lambda item: (item.get("year", 0), item.get("title", "").lower()))
    elif args.sort_by == "venue":
        records.sort(key=lambda item: (item.get("venue", ""), item.get("title", "").lower()))
    else:  # section
        records.sort(key=lambda item: (item.get("section", ""), item.get("title", "").lower()))

    parts = build_front_matter(args.title)
    parts.extend(build_entry(record) for record in records)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(parts), encoding="utf-8")
    print(f"✨ Wrote {args.output} ({len(records)} records)")


if __name__ == "__main__":
    main()
