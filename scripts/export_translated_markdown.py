#!/usr/bin/env python3
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
    translation = (record.get("translated_ja") or "").strip()
    abstract = (record.get("abstract") or "").strip()

    lines = [f"## {title}"]
    if doi:
        lines.append(f"- **DOI**: https://doi.org/{doi}")
    if venue:
        lines.append(f"- **Venue**: {venue}")
    if section:
        lines.append(f"- **Section**: {section}")
    lines.append("")

    if translation:
        lines.append(translation)
    elif abstract:
        lines.append("### 未翻訳")
        lines.append(abstract)
    else:
        lines.append("### 未翻訳")
        lines.append("abstract も翻訳もありません。")

    lines.extend(["", "---", ""])
    return "\n".join(lines)


def main() -> None:
    """翻訳済みJSONLをMarkdown文書へ変換する。"""
    parser = argparse.ArgumentParser(description="Export translated papers JSONL to Markdown")
    parser.add_argument("--input", default="data/papers_translated.jsonl", help="Input translated JSONL")
    parser.add_argument("--output", default="data/papers_translated.md", help="Output Markdown path")
    parser.add_argument("--title", default="Translated Papers", help="Document title")
    parser.add_argument("--sort-by", choices=["title", "section", "year"], default="section", help="Sort key")
    args = parser.parse_args()

    records = load_jsonl(args.input)
    if not records:
        print("❌ input is empty")
        return

    if args.sort_by == "title":
        records.sort(key=lambda item: (item.get("title", "").lower(), item.get("year", 0)))
    elif args.sort_by == "year":
        records.sort(key=lambda item: (item.get("year", 0), item.get("title", "").lower()))
    else:
        records.sort(key=lambda item: (item.get("section", ""), item.get("title", "").lower()))

    parts = build_front_matter(args.title)
    parts.extend(build_entry(record) for record in records)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(parts), encoding="utf-8")
    print(f"✨ Wrote {args.output} ({len(records)} records)")


if __name__ == "__main__":
    main()
