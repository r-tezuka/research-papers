# research-papers

論文リストを OpenAlex で解決し、PDF URL とアブストラクトを取得するスクリプトを格納しています。

## セットアップ

[uv](https://docs.astral.sh/uv/) で仮想環境と依存を一括セットアップします。

```bash
uv sync
```

（未インストールなら: `curl -LsSf https://astral.sh/uv/install.sh | sh`）

以降は `uv run python ...` または `.venv` を有効化して `python ...` で実行できます。

## 使い方（SIGIR 2025 など会議論文集）

**1. 論文リストを作成（SIGIR 2025 Accepted ページから）**

```bash
uv run python build_sigir2025_paper_list.py -o sigir2025_accepted_papers.json
```

**2. 論文リストを OpenAlex で解決し、PDF/abstract まで一括で取得**

`accepted_papers` を入力に、OpenAlex 解決と PDF/abstract 取得を 1 件ずつ一連で行い、中間ファイルを出さずに結果 JSON を書き出します。

```bash
# 論文リスト → 取得結果 JSON
UNPAYWALL_EMAIL=your@email.com uv run python fetch_papers.py sigir2025_accepted_papers.json -o sigir2025.json
```

テスト時は `-n 5` で件数制限。`--no-enrich` で Unpaywall/Crossref/PDF をスキップし OpenAlex 由来の PDF/abstract のみにできます。  
`-j 5` で並列ワーカー数指定（OpenAlex 10/s・補完 API 5/s のレート制限を守るため 5 程度を推奨）。

**3. 取得結果を HTML で出力（ブラウザ翻訳用）**

JSON から title / section / abstract / PDF URL を表形式の HTML に出力します。他ジャーナル用の JSON でも入力・出力ファイルを指定して利用できます。

```bash
uv run python export_papers_html.py sigir2025.json -o sigir2025.html
```

`-n 10` で件数制限可能。出力した HTML をブラウザで開き、翻訳機能で日本語化できます。

## 注意

- 論文数が多い場合は取得に時間がかかります（API のレート制限のため）。429 が出た場合は日次予算または 100 req/s 制限を確認し、必要なら API キー利用や待機を検討してください。
