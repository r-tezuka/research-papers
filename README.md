# research-papers

論文リストを OpenAlex で解決し、PDF URL とアブストラクトを取得するスクリプトを格納しています。

## セットアップ

[uv](https://docs.astral.sh/uv/) で仮想環境と依存を一括セットアップします。

```bash
uv sync
```

（未インストールなら: `curl -LsSf https://astral.sh/uv/install.sh | sh`）

以降は `uv run python scripts/...` または `.venv` を有効化して実行できます。スクリプトは `scripts/` 配下にあります（論文リスト生成: `scripts/list-builders/`、取得・出力: `scripts/`）。

## 使い方（SIGIR 2025 など会議論文集）

**1. 論文リストを作成（SIGIR 2025 Accepted ページから）**

```bash
uv run python scripts/list-builders/build_sigir2025_paper_list.py
```

省略時は `results/sigir2025_accepted_papers.json` に出力します。`-o` で別パス指定可。

**2. 論文リストを OpenAlex で解決し、PDF/abstract まで一括で取得**

`accepted_papers` を入力に、OpenAlex 解決と PDF/abstract 取得を 1 件ずつ一連で行い、中間ファイルを出さずに結果 JSON を書き出します。

```bash
# 論文リスト → 取得結果 JSON（省略時は results/ 内に出力）
UNPAYWALL_EMAIL=your@email.com uv run python scripts/fetch_papers.py results/sigir2025_accepted_papers.json -o results/sigir2025.json
```

テスト時は `-n 5` で件数制限。`--no-enrich` で Unpaywall/Crossref/PDF をスキップし OpenAlex 由来の PDF/abstract のみにできます。  
`-j 5` で並列ワーカー数指定（OpenAlex 10/s・補完 API 5/s のレート制限を守るため 5 程度を推奨）。

**3. 取得結果を HTML で出力（ブラウザ翻訳用）**

JSON から title / section / abstract / PDF URL を表形式の HTML に出力します。他ジャーナル用の JSON でも入力・出力ファイルを指定して利用できます。

```bash
uv run python scripts/export_papers_html.py results/sigir2025.json
```

省略時は `results/sigir2025.html` に出力。`-o` で別パス、`-n 10` で件数制限可能。出力した HTML をブラウザで開き、翻訳機能で日本語化できます。

## 注意

- 論文数が多い場合は取得に時間がかかります（API のレート制限のため）。429 が出た場合は日次予算または 100 req/s 制限を確認し、必要なら API キー利用や待機を検討してください。
