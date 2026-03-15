import hashlib
import html
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path


def normalize_doi(doi: str | None) -> str:
    """DOI文字列を正規化し、URL形式や大文字小文字の揺れを吸収する。"""
    if not doi:
        return ""
    value = doi.strip()
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value, flags=re.IGNORECASE)
    return value.lower()


def normalize_title(title: str | None) -> str:
    """タイトル比較用に、表記揺れの原因になりやすい記号や空白を正規化する。"""
    if not title:
        return ""
    value = html.unescape(title)
    value = unicodedata.normalize("NFKC", value)
    value = value.lower().strip()
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"[^\w\s]", "", value)
    return value


def build_paper_id(doi: str, title: str, year: int | None = None) -> str:
    """DOIがあればDOIベース、なければタイトル+年ベースで安定したIDを生成する。"""
    normalized_doi = normalize_doi(doi)
    if normalized_doi:
        return f"doi:{normalized_doi}"
    payload = f"{normalize_title(title)}::{year or ''}"
    return f"title:{hashlib.sha1(payload.encode('utf-8')).hexdigest()[:16]}"


def now_iso() -> str:
    """現在時刻をUTCのISO 8601形式で返す。"""
    return datetime.now(timezone.utc).isoformat()


def load_jsonl(path: str | Path) -> list[dict]:
    """JSONLファイルを読み込み、各行を辞書の配列として返す。"""
    file_path = Path(path)
    if not file_path.exists():
        return []
    records: list[dict] = []
    with file_path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def write_jsonl(path: str | Path, records: list[dict]) -> None:
    """辞書配列をJSONL形式で保存する。親ディレクトリがなければ作成する。"""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def merge_sources(existing: list[str] | None, incoming: list[str] | None) -> list[str]:
    """source一覧を重複なく結合し、出現順を保つ。"""
    values = []
    for source in (existing or []) + (incoming or []):
        if source and source not in values:
            values.append(source)
    return values


def merge_record(target: dict, incoming: dict) -> None:
    """不足している項目を補完しつつ、source情報を統合する。"""
    for field in ["title", "doi", "abstract", "venue", "year", "section"]:
        if not target.get(field) and incoming.get(field):
            target[field] = incoming[field]
    target["sources"] = merge_sources(target.get("sources"), incoming.get("sources"))


def deduplicate_records(records: list[dict]) -> list[dict]:
    """DOI優先で重複排除し、DOIなしレコードもタイトル+年で既存論文へ寄せて統合する。"""
    merged_by_doi: dict[str, dict] = {}
    merged_by_title: dict[str, dict] = {}

    for record in records:
        if not record.get("title") and not record.get("doi"):
            continue

        working = record.copy()
        doi_key = normalize_doi(working.get("doi"))
        if doi_key:
            working["doi"] = doi_key

        title_key = normalize_title(record.get("title"))
        year = record.get("year")
        title_year_key = f"title:{title_key}::{year or ''}"

        if doi_key:
            doi_map_key = f"doi:{doi_key}"
            if doi_map_key in merged_by_doi:
                merge_record(merged_by_doi[doi_map_key], working)
                continue

            if title_key and title_year_key in merged_by_title:
                merged = merged_by_title.pop(title_year_key)
                merge_record(merged, working)
                merged_by_doi[doi_map_key] = merged
            else:
                working["sources"] = merge_sources([], working.get("sources"))
                merged_by_doi[doi_map_key] = working
            continue

        if title_year_key in merged_by_title:
            merge_record(merged_by_title[title_year_key], working)
            continue

        matched_doi_key = None
        for doi_map_key, item in merged_by_doi.items():
            existing_title_key = normalize_title(item.get("title"))
            existing_year = item.get("year")
            if existing_title_key == title_key and (existing_year or "") == (year or ""):
                matched_doi_key = doi_map_key
                break

        if matched_doi_key:
            merge_record(merged_by_doi[matched_doi_key], working)
        else:
            working["sources"] = merge_sources([], working.get("sources"))
            merged_by_title[title_year_key] = working

    output = list(merged_by_doi.values()) + list(merged_by_title.values())
    for item in output:
        item["paper_id"] = build_paper_id(item.get("doi", ""), item.get("title", ""), item.get("year"))
    return output
