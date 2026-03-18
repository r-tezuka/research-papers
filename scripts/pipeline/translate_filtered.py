#!/usr/bin/env python3
import argparse
import os
import time

from dotenv import load_dotenv
from google import genai

from common import build_paper_id, load_jsonl, now_iso, write_jsonl


def build_prompt(title: str, abstract: str) -> str:
    """翻訳モデルへ渡す要約指示プロンプトを組み立てる。"""
    return (
        "あなたは情報検索とデジタル広告の専門家です。以下の論文を、日本の研究者向けに日本語で要約してください。\n\n"
        f"【タイトル】: {title}\n"
        f"【内容】: {abstract}\n\n"
        "出力形式:\n"
        "### [日本語タイトル]\n"
        "- **要約**: 3行程度の箇条書き"
    )


def translate_text(client: genai.Client, model: str, title: str, abstract: str) -> str:
    """Gemini APIを呼び出し、1論文分の日本語要約を生成する。"""
    prompt = build_prompt(title, abstract)
    response = client.models.generate_content(model=model, contents=prompt)
    return response.text


def load_cache_map(path: str) -> dict[str, dict]:
    """既存の翻訳済みJSONLを `paper_id` キーの辞書へ変換して再利用する。"""
    cache_records = load_jsonl(path)
    return {record.get("paper_id", ""): record for record in cache_records if record.get("paper_id")}


def main() -> None:
    """広告関連論文を翻訳し、結果を `papers_translated.jsonl` に集約して更新する。"""
    parser = argparse.ArgumentParser(description="Translate ad-filtered papers with cache")
    parser.add_argument("--input", default="results/papers_filtered.jsonl", help="Filtered input JSONL")
    parser.add_argument("--output", default="results/papers_translated.jsonl", help="Translated output JSONL")
    parser.add_argument("--model", default="gemini-2.5-flash", help="Gemini model")
    parser.add_argument("--sleep", type=float, default=5.0, help="Sleep seconds between API calls")
    parser.add_argument("--limit", type=int, default=0, help="Translate only first N records (0=all)")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is required")

    records = load_jsonl(args.input)
    if not records:
        print("❌ input is empty")
        return

    if args.limit > 0:
        records = records[: args.limit]

    client = genai.Client(api_key=api_key)
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
            record["translation_model"] = cached.get("translation_model", args.model)
            record["translation_cached"] = True
            translated.append(record)
            cache_hit += 1
            continue

        title = record.get("title", "")
        abstract = record.get("abstract", "") or "（内容取得不可）"

        try:
            result = translate_text(client, args.model, title, abstract)
            record["translated_ja"] = result
            record["translation_model"] = args.model
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
