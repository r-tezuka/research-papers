import os
import time
import re
import argparse
import requests
from google import genai
from dotenv import load_dotenv
from urllib.parse import quote

load_dotenv()

# --- 設定 ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OUTPUT_FILE = "sigir2025_ads_only.md"

# 診断リストで確認された有効なモデル名に変更
MODEL_NAME = "gemini-2.5-flash" 

client = genai.Client(api_key=GEMINI_API_KEY)

def is_ad_related(text):
    """広告関連の単語のみを抽出"""
    pattern = r'\b(ad|ads|advertising|advertiser|sponsored|monetization)\b'
    return bool(re.search(pattern, text, re.IGNORECASE))

def get_proceedings_metadata(proceedings_doi):
    doi_encoded = quote(proceedings_doi, safe='')
    url = f"https://api.crossref.org/works/{doi_encoded}"
    headers = {"User-Agent": "ResearchPaperTranslator/1.0 (mailto:test@example.com)"}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        message = response.json().get('message', {})
        title_list = message.get('title', [])
        title = title_list[0] if title_list else ""
        date_parts = (message.get('published-print') or message.get('published-online') or {}).get('date-parts', [])
        year = date_parts[0][0] if date_parts and date_parts[0] else None
        return {
            "title": title,
            "isbns": message.get('ISBN', []),
            "year": year,
        }
    except Exception as e:
        print(f"❌ DOIメタデータ取得失敗: {e}")
        return {"title": "", "isbns": [], "year": None}

def get_sigir_papers(proceedings_doi):
    print(f"📡 DOI:{proceedings_doi} の会議録から論文リストを取得中...")
    meta = get_proceedings_metadata(proceedings_doi)
    isbns = meta.get("isbns", [])
    url = "https://api.crossref.org/works"
    headers = {"User-Agent": "ResearchPaperTranslator/1.0 (mailto:test@example.com)"}

    # 1) relation 系フィルタ（親 DOI 関係）
    relation_params = {
        "filter": f"relation.type:is-part-of,relation.object:{proceedings_doi},type:proceedings-article",
        "rows": 1000,
        "select": "DOI,title,abstract",
    }
    try:
        relation_response = requests.get(url, params=relation_params, headers=headers, timeout=15)
        relation_response.raise_for_status()
        relation_items = relation_response.json().get('message', {}).get('items', [])
        if relation_items:
            print(f"ℹ️ relationフィルタで {len(relation_items)} 件取得")
            return relation_items
        print("ℹ️ relationフィルタで0件。ISBNフィルタを試行します。")
    except Exception as e:
        print(f"⚠️ relationフィルタ取得失敗: {e}")

    # 2) ISBN フィルタ
    if isbns:
        if len(isbns) > 1:
            print(f"ℹ️ 複数ISBNを検出: {isbns} / 先頭ISBNを使用します: {isbns[0]}")

        isbn = isbns[0]
        isbn_params = {
            "filter": f"isbn:{isbn},type:proceedings-article",
            "rows": 1000,
            "select": "DOI,title,abstract",
        }
        try:
            isbn_response = requests.get(url, params=isbn_params, headers=headers, timeout=15)
            isbn_response.raise_for_status()
            isbn_items = isbn_response.json().get('message', {}).get('items', [])
            if isbn_items:
                print(f"ℹ️ ISBNフィルタで {len(isbn_items)} 件取得")
                return isbn_items
            print("ℹ️ ISBNフィルタで0件。DOI由来タイトルで再検索します。")
        except Exception as e:
            print(f"⚠️ ISBNフィルタ取得失敗: {e}")
            print("ℹ️ DOI由来タイトルで再検索します。")
    else:
        print("ℹ️ ISBN が見つからなかったため、DOI由来タイトルで再検索します。")

    # 3) タイトル検索フォールバック
    title = meta.get("title", "")
    year = meta.get("year")
    fallback_params = {
        "query.container-title": title,
        "filter": "type:proceedings-article",
        "rows": 1000,
        "select": "DOI,title,abstract",
    }
    if year:
        fallback_params["filter"] = (
            f"type:proceedings-article,from-pub-date:{year}-01-01,until-pub-date:{year}-12-31"
        )

    try:
        fallback_response = requests.get(url, params=fallback_params, headers=headers, timeout=15)
        fallback_response.raise_for_status()
        return fallback_response.json().get('message', {}).get('items', [])
    except Exception as e:
        print(f"❌ リスト取得失敗: {e}")
        return []

def translate_paper(title, abstract):
    """Gemini 2.5 Flashによる翻訳呼び出し"""
    prompt = (
        f"あなたは情報検索とデジタル広告の専門家です。以下の論文を、日本の研究者向けに日本語で要約してください。\n\n"
        f"【タイトル】: {title}\n"
        f"【内容】: {abstract}\n\n"
        "出力形式:\n"
        "### [日本語タイトル]\n"
        "- **要約**: 3行程度の箇条書き"
    )
    
    try:
        # モデル名に gemini-2.5-flash を使用
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt
        )
        return response.text
    except Exception as e:
        print(f"❌ 翻訳エラー詳細: {e}")
        return f"⚠️ 翻訳失敗: {e}"

def main():
    parser = argparse.ArgumentParser(description="Proceedings DOI から Crossref で論文を取得し要約する")
    parser.add_argument("--doi", required=True, help="会議録 DOI (例: 10.1145/3726302)")
    args = parser.parse_args()

    works = get_sigir_papers(args.doi)
    if not works:
        print("論文が見つかりませんでした。")
        return

    print(f"✅ {len(works)} 件の論文から広告関連を抽出中...")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(f"# SIGIR '25 広告関連論文要約\n生成日: {time.strftime('%Y-%m-%d')}\n\n---\n")

        count = 0
        for work in works:
            title = work.get('title', ['No Title'])[0]
            abstract = work.get('abstract', '')
            doi = work.get('DOI')

            if is_ad_related(title + abstract):
                count += 1
                print(f"📝 [{count}] 翻訳中: {title[:50]}...")
                
                # 要約がない場合は補完
                if not abstract or len(abstract) < 100:
                    try:
                        ss_url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields=abstract"
                        abstract = requests.get(ss_url, timeout=10).json().get('abstract', '')
                    except:
                        pass
                
                result = translate_paper(title, abstract or "（内容取得不可）")
                f.write(f"## {title}\n- **DOI**: https://doi.org/{doi}\n\n{result}\n\n---\n")
                f.flush()
                # 無料枠のレート制限を考慮
                time.sleep(5) 

    print(f"✨ 完了！ {count} 件を '{OUTPUT_FILE}' に保存しました。")

if __name__ == "__main__":
    main()