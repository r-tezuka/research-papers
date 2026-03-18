import requests

from common import normalize_doi

DBLP_API_URL = "https://dblp.org/search/publ/api"


def default_dblp_query(conference_id: str, year: int) -> str:
    """会議IDと年から、DBLPの目次ベース既定クエリを組み立てる。"""
    return f"toc:db/conf/{conference_id.lower()}/{conference_id.lower()}{year}.bht:"


def extract_doi_from_hit(hit_info: dict) -> str:
    """DBLP hit から DOI を取り出す。`doi` がなければ `ee` も見る。"""
    doi = hit_info.get("doi")
    if doi:
        return normalize_doi(doi)

    ee = hit_info.get("ee")
    if isinstance(ee, list):
        for value in ee:
            normalized = normalize_doi(value)
            if normalized:
                return normalized
    elif isinstance(ee, str):
        return normalize_doi(ee)
    return ""


def fetch_dblp_records(query: str, fallback_query: str, year: int, timeout: int, rows: int) -> list[dict]:
    """DBLPから論文候補を取得し、必要ならフォールバッククエリも試す。"""

    def _fetch_once(q: str) -> list[dict]:
        params = {"q": q, "h": rows, "format": "json"}
        response = requests.get(DBLP_API_URL, params=params, timeout=timeout)
        response.raise_for_status()

        data = response.json()
        hits = data.get("result", {}).get("hits", {}).get("hit", [])
        if isinstance(hits, dict):
            hits = [hits]

        records: list[dict] = []
        for hit in hits:
            info = hit.get("info", {})
            title = info.get("title", "")
            if not title:
                continue
            records.append(
                {
                    "title": title,
                    "doi": extract_doi_from_hit(info),
                    "year": int(info.get("year", year)) if str(info.get("year", "")).isdigit() else year,
                    "venue": info.get("venue", ""),
                    "sources": ["dblp"],
                }
            )
        return records

    records = _fetch_once(query)
    if records:
        return records
    if fallback_query and fallback_query != query:
        return _fetch_once(fallback_query)
    return []
