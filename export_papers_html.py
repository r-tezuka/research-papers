#!/usr/bin/env python3
"""
論文取得結果 JSON から title, section, abstract, PDF URL を抽出し、
ブラウザ翻訳で使える HTML を出力する。
入力・出力ファイルは実行時に指定（他ジャーナルでも汎用）。
"""
import argparse
import html
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="論文 JSON から title / section / abstract / PDF URL を HTML で出力する（ブラウザ翻訳用）"
    )
    parser.add_argument(
        "input_json",
        type=Path,
        help="論文取得結果の JSON（fetch_papers の出力など）",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="出力 HTML ファイル（省略時は input のベース名 + .html）",
    )
    parser.add_argument(
        "-n", "--limit",
        type=int,
        default=None,
        help="出力する論文数の上限（省略時は全件）",
    )
    args = parser.parse_args()

    if not args.input_json.exists():
        raise SystemExit(f"File not found: {args.input_json}")

    out_path = args.output or args.input_json.with_suffix(".html")

    data = json.loads(args.input_json.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        data = data.get("results", data.get("papers", [data]))

    if args.limit is not None:
        data = data[: args.limit]

    rows = []
    for i, entry in enumerate(data, start=1):
        list_entry = entry.get("list_entry") or {}
        title = list_entry.get("title") or ""
        section = list_entry.get("section") or ""
        abstract = entry.get("abstract") or ""
        pdf_url = entry.get("pdf_url") or ""

        title_esc = html.escape(title)
        section_esc = html.escape(section)
        abstract_esc = html.escape(abstract)
        pdf_esc = html.escape(pdf_url)
        pdf_link = f'<a href="{pdf_esc}" target="_blank" rel="noopener">PDF</a>' if pdf_url else "—"

        rows.append(
            f"""<tr>
  <td class="num">{i}</td>
  <td class="title">{title_esc}</td>
  <td class="section">{section_esc}</td>
  <td class="abstract">{abstract_esc}</td>
  <td class="pdf">{pdf_link}</td>
</tr>"""
        )

    table_body = "\n".join(rows)
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Papers</title>
  <style>
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ccc; padding: 0.5rem; text-align: left; vertical-align: top; }}
    th {{ background: #eee; }}
    .num {{ text-align: right; white-space: nowrap; width: 2.5em; }}
    .title {{ font-weight: bold; min-width: 12em; }}
    .section {{ white-space: nowrap; }}
    .abstract {{ max-width: 40em; }}
    .pdf {{ white-space: nowrap; }}
  </style>
</head>
<body>
  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>Title</th>
        <th>Section</th>
        <th>Abstract</th>
        <th>PDF</th>
      </tr>
    </thead>
    <tbody>
{table_body}
    </tbody>
  </table>
</body>
</html>
"""

    out_path.write_text(html_content, encoding="utf-8")
    print(f"Wrote {out_path} ({len(data)} papers)")


if __name__ == "__main__":
    main()
