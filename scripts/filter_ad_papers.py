#!/usr/bin/env python3
import argparse
import re

from common import load_jsonl, write_jsonl


DEFAULT_KEYWORDS = ["ad", "ads", "advertising", "advertiser", "sponsored", "monetization"]


def compile_pattern(keywords: list[str]) -> re.Pattern:
    """キーワード一覧から単語境界付きの検索用正規表現を作る。"""
    escaped = [re.escape(word) for word in keywords if word]
    return re.compile(r"\b(" + "|".join(escaped) + r")\b", re.IGNORECASE)


def is_ad_related(text: str, pattern: re.Pattern) -> bool:
    """タイトル+abstract文字列が広告関連かを正規表現で判定する。"""
    return bool(pattern.search(text or ""))


def main() -> None:
    """enriched JSONLから広告関連論文だけを抽出して保存する。"""
    parser = argparse.ArgumentParser(description="Filter ad-related papers by title + abstract")
    parser.add_argument("--input", default="data/papers_enriched.jsonl", help="Input JSONL")
    parser.add_argument("--output", default="data/papers_filtered.jsonl", help="Output JSONL")
    parser.add_argument(
        "--keywords",
        default=",".join(DEFAULT_KEYWORDS),
        help="Comma-separated keywords",
    )
    args = parser.parse_args()

    keywords = [item.strip() for item in args.keywords.split(",") if item.strip()]
    pattern = compile_pattern(keywords)

    records = load_jsonl(args.input)
    if not records:
        print("❌ input is empty")
        return

    filtered = []
    for record in records:
        text = f"{record.get('title', '')}\n{record.get('abstract', '')}"
        if is_ad_related(text, pattern):
            record["is_ad_related"] = True
            filtered.append(record)

    write_jsonl(args.output, filtered)
    print(f"✨ Filtered {len(filtered)} / {len(records)} records. Wrote {args.output}")


if __name__ == "__main__":
    main()
