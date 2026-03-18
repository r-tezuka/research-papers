# research-papers

会議論文 (SIGIR など) を DBLP・OpenAlex 等から収集し、広告関連論文を日本語要約するパイプラインです。

## セットアップ

[uv](https://docs.astral.sh/uv/) で仮想環境と依存を一括セットアップします。

```bash
uv sync
```

（未インストールなら: `curl -LsSf https://astral.sh/uv/install.sh | sh`）

`.env` に Gemini API キーを設定してください。

```
GEMINI_API_KEY=your_key_here
```

## パイプラインの実行手順

### ステップ 1: ビルダーの作成
`list-builders` 配下に該当カンファレンスの builder（論文名のリスト）を作る。
フォーマットは既存の実装を参考に、カンファレンスの accepted papers ページの URL を 良さげな AI Agent に渡して作ってもらう。

### ステップ 2: パイプラインの一括実行

builder を指定して、builder 実行から Markdown 出力まで一括で回せます。

例: 

```bash
uv run python scripts/run_pipeline.py \
  --builder scripts/list-builders/build_sigir2025_paper_list.py
```

## データフロー

```
conference builder (scripts/list-builders/*)
        ↓ run_pipeline.py または個別実行
DBLP + conference list
        ↓ pipeline/build_master_list.py
data/papers_master.jsonl
        ↓ pipeline/enrich_abstracts.py
data/papers_enriched.jsonl
        ↓ pipeline/filter_ad_papers.py
data/papers_filtered.jsonl
        ↓ pipeline/translate_filtered.py
data/papers_translated.jsonl
        ↓ pipeline/export_translated_markdown.py
data/papers_translated.md
```

## 注意

- `scripts/pipeline/enrich_abstracts.py` は DOI がない論文の abstract を補完できません。
- `scripts/pipeline/translate_filtered.py` は Gemini の無料枠・レート制限に注意してください。429 が出た場合は時間を空けて再実行すると、キャッシュ済みの翻訳はスキップされます。
- 旧実装は `scripts/sandbox/paper-translator.py` に保存しています。
