# research-papers

OpenAlex API でジャーナル・年指定で論文情報を一括取得するスクリプトを格納しています。

## セットアップ

[uv](https://docs.astral.sh/uv/) で仮想環境と依存を一括セットアップします。

```bash
uv sync
```

（未インストールなら: `curl -LsSf https://astral.sh/uv/install.sh | sh`）

以降は `uv run python fetch_journal_works.py ...` または `.venv` を有効化して `python fetch_journal_works.py ...` で実行できます。

## 使い方

**ジャーナル名で検索する場合（名前で検索し、ヒットした先頭1件のジャーナルを使用）:**

```bash
uv run python fetch_journal_works.py -j "Nature" -y 2023
```

**OpenAlex のソースIDを既に知っている場合:**

```bash
uv run python fetch_journal_works.py -s S1983995261 -y 2023
```

**出力先ディレクトリを指定する場合（指定しなければ実行したディレクトリ）:**

```bash
uv run python fetch_journal_works.py -j "Science" -y 2022 -o ./output
```

出力ファイルは `ジャーナル名_西暦.json` の形式で、実行したディレクトリ（または `-o` で指定したディレクトリ）に保存されます。  
例: `Nature_2023.json`

## SIGIR 2025 など会議論文集の論文を OpenAlex で取得する場合

会議論文集は OpenAlex で Source として一括取得できないため、**論文リスト**と **OpenAlex 解決**の2段階で行います。

**1. 論文リストを作成（SIGIR 2025 Accepted ページから）**

```bash
uv run python build_sigir2025_paper_list.py -o sigir2025_accepted_papers.json
```

**2. 論文リストを OpenAlex で解決（タイトル検索 or DOI）**

```bash
uv run python fetch_works_from_openalex.py sigir2025_accepted_papers.json -o sigir2025_openalex.json
```

テスト時は `-n 5` で件数制限できます。リストの各エントリに `doi` があれば DOI で、なければタイトル検索で work を取得します。

**3. PDF URL とアブストラクトを付与（任意）**

OpenAlex の結果 JSON から PDF URL とアブストラクトを抽出し、不足分を Unpaywall / Crossref で補完します。

```bash
# OpenAlex から抽出のみ（外部 API を叩かない）
uv run python enrich_papers_pdf_abstract.py sigir2025_openalex.json -o sigir2025_enriched.json --no-enrich

# 不足分を Unpaywall・Crossref で補完（Unpaywall はメール推奨）
UNPAYWALL_EMAIL=your@email.com uv run python enrich_papers_pdf_abstract.py sigir2025_openalex.json -o sigir2025_enriched.json
```

出力の各要素には `pdf_url`・`abstract`・`pdf_source`・`abstract_source` が追加されます。テスト時は `-n 10` で件数制限できます。

## 注意

- ジャーナル名検索で複数候補がある場合、**先頭1件**が使われます。意図したジャーナルでない場合は [OpenAlex](https://openalex.org/) でソースIDを調べ、`-s` で指定してください。
- 論文数が多い年・ジャーナルでは取得に時間がかかります（API の負荷軽減のためリクエスト間に短い待機あり）。
