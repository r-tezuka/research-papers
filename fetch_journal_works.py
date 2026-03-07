#!/usr/bin/env python3
"""
OpenAlex API で指定ジャーナルの指定年の論文を一括取得し、
実行ディレクトリに「ジャーナル名_西暦.json」で保存するスクリプト。
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests

OPENALEX_API = "https://api.openalex.org"
PER_PAGE = 200
REQUEST_DELAY = 0.15  # レート制限対策（秒）


def sanitize_filename(name: str) -> str:
    """ファイル名に使えない文字をアンダースコアに置換する。"""
    return re.sub(r'[<>:"/\\|?*\s]+', "_", name).strip("_") or "journal"


def search_source(journal_query: str) -> dict | None:
    """
    ジャーナル名またはISSNでソース（ジャーナル）を検索し、先頭1件を返す。
    """
    url = f"{OPENALEX_API}/sources"
    params = {"search": journal_query, "per_page": 1}
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results") or []
    if not results:
        return None
    return results[0]


def get_source_by_id(source_id: str) -> dict | None:
    """OpenAlex ソースID（Sで始まるIDまたは完全URL）でソースを1件取得。"""
    raw = source_id.strip()
    if raw.startswith("http"):
        url = raw
    else:
        if not raw.upper().startswith("S"):
            raw = f"S{raw}"
        url = f"{OPENALEX_API}/sources/{raw}"
    resp = requests.get(url, timeout=30)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def fetch_works_by_journal_and_year(source_openalex_id: str, year: int) -> list[dict]:
    """
    指定ソース（ジャーナル）・指定年の work を cursor で全件取得する。
    """
    # IDがURL形式の場合は末尾のS123456のような部分だけ使う
    sid = source_openalex_id
    if "/" in sid:
        sid = sid.rstrip("/").split("/")[-1]
    if not sid.upper().startswith("S"):
        sid = f"S{sid}"

    url = f"{OPENALEX_API}/works"
    all_results = []
    cursor = "*"

    while cursor:
        params = {
            "filter": f"primary_location.source.id:{sid},publication_year:{year}",
            "per_page": PER_PAGE,
            "cursor": cursor,
        }
        resp = requests.get(url, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results") or []
        all_results.extend(results)
        cursor = data.get("meta", {}).get("next_cursor")
        if cursor:
            time.sleep(REQUEST_DELAY)

    return all_results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OpenAlex で指定ジャーナルの指定年の論文を一括取得し JSON で保存する"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "-j", "--journal",
        type=str,
        help="ジャーナル名（検索でソースを1件取得）",
    )
    group.add_argument(
        "-s", "--source-id",
        type=str,
        help="OpenAlex ソースID（例: S1983995261）またはソースURL",
    )
    parser.add_argument(
        "-y", "--year",
        type=int,
        required=True,
        help="出版年（西暦）",
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=Path,
        default=Path("."),
        help="出力ディレクトリ（デフォルト: カレントディレクトリ）",
    )
    args = parser.parse_args()

    source = None
    if args.source_id:
        source = get_source_by_id(args.source_id)
        if not source:
            print(f"エラー: ソースID '{args.source_id}' が見つかりません。", file=sys.stderr)
            sys.exit(1)
    else:
        source = search_source(args.journal)
        if not source:
            print(f"エラー: ジャーナル '{args.journal}' に該当するソースが見つかりません。", file=sys.stderr)
            sys.exit(1)

    display_name = source.get("display_name") or "unknown"
    source_id = source.get("id", "").replace("https://openalex.org/", "")

    print(f"ジャーナル: {display_name} (ID: {source_id})")
    print(f"年: {args.year}")
    print("取得中...")

    works = fetch_works_by_journal_and_year(source_id, args.year)
    print(f"取得件数: {len(works)}")

    safe_name = sanitize_filename(display_name)
    out_path = args.output_dir / f"{safe_name}_{args.year}.json"
    out_path.write_text(json.dumps(works, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"保存しました: {out_path}")


if __name__ == "__main__":
    main()
