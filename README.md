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

### ステップ 1: 論文マスター作成

DBLP と conference list (accepted papers JSON) を統合し、重複排除した master JSONL を作成します。

```bash
uv run python scripts/build_master_list.py \
  --conference sigir \
  --year 2025 \
  --conference-list results/sigir2025_accepted_papers.json \
  --output data/papers_master.jsonl
```

### ステップ 2: Abstract 補完

DOI を基に OpenAlex → Crossref → Semantic Scholar の順で未取得の abstract を補完します。

```bash
uv run python scripts/enrich_abstracts.py \
  --input data/papers_master.jsonl \
  --output data/papers_enriched.jsonl
```

### ステップ 3: 広告関連論文を抽出

title + abstract をキーワードで検索し、広告関連論文だけを絞り込みます。

```bash
uv run python scripts/filter_ad_papers.py \
  --input data/papers_enriched.jsonl \
  --output data/papers_filtered.jsonl
```

キーワードを変更する場合は `--keywords ad,advertising,sponsored,monetization` のように指定します。

### ステップ 4: Gemini で日本語要約

フィルタ済み論文を Gemini で翻訳します。`data/papers_translated.jsonl` がキャッシュを兼ねるため、再実行時は未翻訳分のみ処理します。

```bash
uv run python scripts/translate_filtered.py \
  --input data/papers_filtered.jsonl \
  --output data/papers_translated.jsonl
```

API クォータを節約したい場合は `--limit 10` で件数を制限できます。

### ステップ 5: Markdown に出力

翻訳済み JSONL を Markdown ドキュメントに変換します。

```bash
uv run python scripts/export_translated_markdown.py \
  --input data/papers_translated.jsonl \
  --output data/papers_translated.md \
  --title "SIGIR 2025 広告関連論文"
```

`--sort-by` で並び替え (title / section / year) を指定できます。

## データフロー

```
DBLP + conference list
        ↓ build_master_list.py
data/papers_master.jsonl
        ↓ enrich_abstracts.py
data/papers_enriched.jsonl
        ↓ filter_ad_papers.py
data/papers_filtered.jsonl
        ↓ translate_filtered.py
data/papers_translated.jsonl
        ↓ export_translated_markdown.py
data/papers_translated.md
```

## 注意

- `enrich_abstracts.py` は DOI がない論文の abstract を補完できません。
- `translate_filtered.py` は Gemini 無料枠の 1 日 20 リクエスト制限に注意してください。429 が出た場合は翌日以降に再実行すると、キャッシュ済みの翻訳はスキップされます。
- 旧実装は `scripts/sandbox/paper-translator.py` に保存しています。
