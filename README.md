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
uv run python scripts/pipeline/build_master_list.py \
  --conference-list results/sigir2025_accepted_papers.json \
  --output data/papers_master.jsonl
```

`build_master_list.py` のCLIは `--conference-list` と `--output` のみです（DBLP取得設定は内部デフォルトを使用）。

`--conference-list` は metadata + papers のオブジェクト形式が必須です。

```json
{
  "conference_id": "sigir",
  "venue": "SIGIR",
  "year": 2025,
  "dblp_query": "toc:db/conf/sigir/sigir2025.bht:",
  "papers": [
    {"title": "...", "section": "...", "doi": "..."}
  ]
}
```

実運用では、先に会議別ビルダーで `results/*.json` を作ってから `build_master_list.py` に渡します。

SIGIR 2025 の例:

```bash
uv run python scripts/list-builders/build_sigir2025_paper_list.py \
  --output results/sigir2025_accepted_papers.json

uv run python scripts/pipeline/build_master_list.py \
  --conference-list results/sigir2025_accepted_papers.json \
  --output data/papers_master.jsonl
```

KDD 2025 の例:

```bash
uv run python scripts/list-builders/build_kdd2025_paper_list.py \
  --output results/kdd2025_accepted_papers.json

uv run python scripts/pipeline/build_master_list.py \
  --conference-list results/kdd2025_accepted_papers.json \
  --output data/papers_master.jsonl
```

### ステップ 2: Abstract 補完

DOI を基に OpenAlex → Crossref → Semantic Scholar の順で未取得の abstract を補完します。

```bash
uv run python scripts/pipeline/enrich_abstracts.py \
  --input data/papers_master.jsonl \
  --output data/papers_enriched.jsonl
```

### ステップ 3: 広告関連論文を抽出

title + abstract をキーワードで検索し、広告関連論文だけを絞り込みます。

```bash
uv run python scripts/pipeline/filter_ad_papers.py \
  --input data/papers_enriched.jsonl \
  --output data/papers_filtered.jsonl
```

キーワードを変更する場合は `--keywords ad,advertising,sponsored,monetization` のように指定します。

### ステップ 4: Gemini で日本語要約

フィルタ済み論文を Gemini で翻訳します。`data/papers_translated.jsonl` がキャッシュを兼ねるため、再実行時は未翻訳分のみ処理します。

```bash
uv run python scripts/pipeline/translate_filtered.py \
  --input data/papers_filtered.jsonl \
  --output data/papers_translated.jsonl
```

API クォータを節約したい場合は `--limit 10` で件数を制限できます。

### ステップ 5: Markdown に出力

翻訳済み JSONL を Markdown ドキュメントに変換します。

```bash
uv run python scripts/pipeline/export_translated_markdown.py \
  --input data/papers_translated.jsonl \
  --output data/papers_translated.md \
  --title "SIGIR 2025 広告関連論文"
```

`--sort-by` で並び替え (title / section / year) を指定できます。

## 一括実行

builder を指定して、builder 実行から Markdown 出力まで一括で回せます。

```bash
uv run python scripts/run_pipeline.py \
  --builder scripts/list-builders/build_sigir2025_paper_list.py
```

KDD の例:

```bash
uv run python scripts/run_pipeline.py \
  --builder scripts/list-builders/build_kdd2025_paper_list.py
```

主なオプション:
- `--conference-list`: builder 出力 JSON の保存先を明示指定
- `--translate-model`: 翻訳モデルの指定
- `--translate-limit`: 翻訳対象件数の上限
- `--markdown-title`: Markdown タイトルの上書き

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
