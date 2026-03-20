#!/usr/bin/env python3
import argparse
import os
import time

import deepl
from dotenv import load_dotenv

from common import build_paper_id, load_jsonl, now_iso, write_jsonl


def translate_text(translator: deepl.Translator, title: str, abstract: str) -> dict:
    """DeepL APIで論文タイトルと概要を日本語に翻訳する。"""
    # タイトルを翻訳
    title_result = translator.translate_text(title, target_lang="JA")
    translated_title = title_result.text if hasattr(title_result, 'text') else str(title_result)
    
    # 概要を翻訳（制限に達した場合はスキップ）
    translated_abstract = ""
    try:
        abstract_result = translator.translate_text(abstract, target_lang="JA")
        translated_abstract = abstract_result.text if hasattr(abstract_result, 'text') else str(abstract_result)
    except deepl.DocumentTranslationException as e:
        print(f"⚠️ Translation quota exceeded: {e}")
        return None
    
    return {
        'title_ja': translated_title,
        'abstract_ja': translated_abstract
    }


def load_cache_map(path: str) -> dict[str, dict]:
    """既存の翻訳済みJSONLを `paper_id` キーの辞書へ変換して再利用する。"""
    cache_records = load_jsonl(path)
    return {record.get("paper_id", ""): record for record in cache_records if record.get("paper_id")}


def main() -> None:
    """広告関連論文を翻訳し、結果を `papers_translated.jsonl` に集約して更新する。"""
    parser = argparse.ArgumentParser(description="Translate ad-filtered papers with DeepL")
    parser.add_argument("--input", default="results/papers_filtered.jsonl", help="Filtered input JSONL")
    parser.add_argument("--output", default="results/papers_translated.jsonl", help="Translated output JSONL")
    parser.add_argument("--sleep", type=float, default=1.0, help="Sleep seconds between API calls")
    parser.add_argument("--limit", type=int, default=0, help="Translate only first N records (0=all)")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv("DEEPL_API_KEY")
    if not api_key:
        raise SystemExit("❌ DEEPL_API_KEY is required. Set it in .env")

    records = load_jsonl(args.input)
    if not records:
        print("❌ input is empty")
        return

    if args.limit > 0:
        records = records[: args.limit]

    # DeepL Translator を初期化
    try:
        translator = deepl.Translator(api_key)
    except Exception as e:
        raise SystemExit(f"❌ DeepL API initialization failed: {e}")

    cache_map = load_cache_map(args.output)

    translated = []
    translated_count = 0
    cache_hit = 0

    for record in records:
        paper_id = record.get("paper_id") or build_paper_id(record.get("doi", ""), record.get("title", ""), record.get("year"))
        record["paper_id"] = paper_id

        cached = cache_map.get(paper_id)
        if cached and cached.get("translated_ja"):
            record["translated_ja"] = cached["translated_ja"]
            record["translation_model"] = "deepl"
            record["translation_cached"] = True
            translated.append(record)
            cache_hit += 1
            continue

        title = record.get("title", "")
        abstract = record.get("abstract", "") or "（内容取得不可）"

        try:
            result = translate_text(translator, title, abstract)
            if result is None:
                # クォータ超過
                break
            
            record["translated_ja"] = result
            record["translation_model"] = "deepl"
            record["translation_cached"] = False
            record["translated_at"] = now_iso()

            cache_map[paper_id] = record.copy()
            translated_count += 1
            time.sleep(args.sleep)
        except Exception as error:
            record["translation_error"] = str(error)
            print(f"⚠️  [{title[:60]}] 翻訳失敗: {error}")

        translated.append(record)

    for record in translated:
        cache_map[record["paper_id"]] = record.copy()

    write_jsonl(args.output, translated)

    print(
        f"✨ Wrote {args.output} ({len(translated)} records) | translated={translated_count}, cache_hit={cache_hit}"
    )


if __name__ == "__main__":
    main()
