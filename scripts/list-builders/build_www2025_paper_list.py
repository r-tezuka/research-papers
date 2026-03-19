#!/usr/bin/env python3
"""WWW 2025 Accepted Papers PDF から論文リスト（title / doi）を抽出して JSON に保存する。"""

import argparse
import json
import re
from pathlib import Path

import fitz

DEFAULT_PDF_PATH = "local/3696410.pdf"


def extract_papers_from_pdf(pdf_path: str) -> list[dict]:
    """PDF の目次（7-61ページ）から論文情報を抽出する。"""
    papers = []
    seen_dois = set()
    
    try:
        pdf = fitz.open(pdf_path)
    except Exception as e:
        print(f"❌ Failed to open PDF: {e}")
        return []
    
    if len(pdf) < 61:
        print(f"⚠️ PDF has only {len(pdf)} pages (expected 61+)")
    
    # 目次: pages 7-61 (entire table of contents)
    for page_idx in range(7, min(61, len(pdf))):
        try:
            text = pdf[page_idx].get_text()
            lines = text.split('\n')
            
            for i, line in enumerate(lines):
                # DOI 行を検出
                if 'DOI: https://doi.org/10.1145/3696410' in line or re.search(r'10\.1145/3696410\.\d+', line):
                    doi_match = re.search(r'(10\.1145/3696410\.\d+)', line)
                    if not doi_match:
                        continue
                    
                    doi = doi_match.group(0)
                    if doi in seen_dois:
                        continue
                    
                    # タイトル行を後ろから探す
                    # bullet point で始まる行まで遡ってタイトルを取得
                    title_parts = []
                    for j in range(i - 1, -1, -1):
                        current_line = lines[j].strip()
                        
                        # 空行はスキップ
                        if not current_line:
                            continue
                        
                        # 著者情報行は含めない（複数著者が続く場合）
                        if '(' in current_line and ')' in current_line and len(current_line) > 50:
                            continue
                        
                        # 長すぎる（著者情報）はスキップ
                        if current_line.count(',') > 2 and current_line.count('(') > 1:
                            continue
                        
                        # タイトル行を追加
                        title_parts.insert(0, current_line)
                        
                        # bullet で始まる行は最初のタイトル行
                        if current_line.startswith('•'):
                            break
                    
                    if not title_parts:
                        continue
                    
                    # タイトル処理
                    full_title = ' '.join(title_parts).lstrip('•').strip()
                    # 目次の装飾ドット（... ページ番号）を削除
                    full_title = re.sub(r'\s*\.+\s*\d+\s*$', '', full_title).strip()
                    # 連続ドット（......）を削除
                    full_title = re.sub(r'\.{3,}', '', full_title).strip()
                    # 複数スペースを単一スペースに
                    full_title = re.sub(r'\s+', ' ', full_title).strip()
                    
                    if full_title and len(full_title) > 3:
                        papers.append({
                            'title': full_title,
                            'doi': doi
                        })
                        seen_dois.add(doi)
        except Exception as e:
            print(f"⚠️ Error processing page {page_idx + 1}: {e}")
            continue
    
    pdf.close()
    return papers


def main() -> None:
    """PDF から論文リストを抽出して JSON に保存する。"""
    parser = argparse.ArgumentParser(description="Extract WWW 2025 papers from PDF")
    parser.add_argument("--pdf", default=DEFAULT_PDF_PATH, help="Path to PDF file")
    parser.add_argument("--output", default="results/accepted_papers.json", help="Output JSON path")
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"❌ PDF not found: {args.pdf}")
        return

    print(f"📄 Extracting papers from {args.pdf}...")
    papers = extract_papers_from_pdf(args.pdf)

    if not papers:
        print("❌ No papers extracted")
        return

    # JSON 出力用のデータ構造を作成
    output_data = {
        "conference_id": "www",
        "venue": "WWW",
        "year": 2025,
        "dblp_query": "toc:db/conf/www/www2025.html",
        "papers": papers,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"✨ Extracted {len(papers)} papers. Wrote {args.output}")


if __name__ == "__main__":
    main()
