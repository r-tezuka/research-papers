import os
import time
import re
import requests
from google import genai
from dotenv import load_dotenv

load_dotenv()

# --- 設定 ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CONFERENCE_TITLE = "Proceedings of the 48th International ACM SIGIR Conference on Research and Development in Information Retrieval"
OUTPUT_FILE = "sigir2025_ads_only.md"

# 診断リストで確認された有効なモデル名に変更
MODEL_NAME = "gemini-2.5-flash" 

client = genai.Client(api_key=GEMINI_API_KEY)

def is_ad_related(text):
    """広告関連の単語のみを抽出"""
    pattern = r'\b(ad|ads|advertising|advertiser|sponsored|monetization)\b'
    return bool(re.search(pattern, text, re.IGNORECASE))

def get_sigir_papers(title):
    print(f"📡 SIGIR '25 の論文リストを取得中...")
    url = "https://api.crossref.org/works"
    headers = {"User-Agent": "ResearchPaperTranslator/1.0 (mailto:test@example.com)"}
    params = {
        "query.container-title": title,
        "rows": 1000, # 大量に取得して後でフィルタリング
        "select": "DOI,title,abstract"
    }
    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json().get('message', {}).get('items', [])
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
    works = get_sigir_papers(CONFERENCE_TITLE)
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