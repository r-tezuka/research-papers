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

## 注意

- ジャーナル名検索で複数候補がある場合、**先頭1件**が使われます。意図したジャーナルでない場合は [OpenAlex](https://openalex.org/) でソースIDを調べ、`-s` で指定してください。
- 論文数が多い年・ジャーナルでは取得に時間がかかります（API の負荷軽減のためリクエスト間に短い待機あり）。
