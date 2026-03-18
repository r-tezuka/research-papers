#!/usr/bin/env python3
import argparse
import re

from common import load_jsonl, write_jsonl


DEFAULT_KEYWORDS = ["ad", "ads", "advertising", "advertiser", "sponsored", "monetization", "bidding", "auction"]

# これらのフレーズに含まれる "ad" は広告とは無関係のため除外する
DEFAULT_EXCLUDE_PHRASES = ["ad hoc", "ad-hoc", "adhoc"]


def compile_pattern(keywords: list[str]) -> re.Pattern:
    """キーワード一覧から単語境界付きの検索用正規表現を作る。"""
    escaped = [re.escape(word) for word in keywords if word]
    return re.compile(r"\b(" + "|".join(escaped) + r")\b", re.IGNORECASE)


def compile_exclude_pattern(phrases: list[str]) -> re.Pattern:
    """除外フレーズ一覧から除去用の正規表現を作る。"""
    escaped = [re.escape(phrase) for phrase in phrases if phrase]
    return re.compile("|".join(escaped), re.IGNORECASE)


def is_ad_related(text: str, pattern: re.Pattern, exclude_pattern: re.Pattern | None = None) -> bool:
    """除外フレーズを取り除いてから広告関連キーワードを判定する。"""
    cleaned = exclude_pattern.sub(" ", text) if exclude_pattern else text
    return bool(pattern.search(cleaned or ""))


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
    parser.add_argument(
        "--exclude-phrases",
        default=",".join(DEFAULT_EXCLUDE_PHRASES),
        help="Comma-separated phrases to exclude before keyword matching (e.g. ad hoc)",
    )
    args = parser.parse_args()

    keywords = [item.strip() for item in args.keywords.split(",") if item.strip()]
    pattern = compile_pattern(keywords)

    exclude_phrases = [item.strip() for item in args.exclude_phrases.split(",") if item.strip()]
    exclude_pattern = compile_exclude_pattern(exclude_phrases) if exclude_phrases else None

    records = load_jsonl(args.input)
    if not records:
        print("❌ input is empty")
        return

    filtered = []
    for record in records:
        text = f"{record.get('title', '')}\n{record.get('abstract', '')}"
        if is_ad_related(text, pattern, exclude_pattern):
            record["is_ad_related"] = True
            filtered.append(record)

    write_jsonl(args.output, filtered)
    print(f"✨ Filtered {len(filtered)} / {len(records)} records. Wrote {args.output}")


if __name__ == "__main__":
    main()
