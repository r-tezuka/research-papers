#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from pathlib import Path


def read_markdown_title(conference_list_path: Path) -> str:
    """Build markdown title from conference metadata when available."""
    try:
        payload = json.loads(conference_list_path.read_text(encoding="utf-8"))
    except Exception:
        return "広告関連論文"

    if not isinstance(payload, dict):
        return "広告関連論文"

    venue = str(payload.get("venue", "")).strip()
    year = payload.get("year")
    if venue and str(year).isdigit():
        return f"{venue} {year} 広告関連論文"
    return "広告関連論文"


def run_cmd(cmd: list[str]) -> None:
    """Run command and stop pipeline on failure."""
    print("$", " ".join(cmd))
    subprocess.run(cmd, check=True)


MASTER = "results/papers_master.jsonl"
ENRICHED = "results/papers_enriched.jsonl"
FILTERED = "results/papers_filtered.jsonl"
TRANSLATED = "results/papers_translated.jsonl"
MARKDOWN = "results/papers_translated.md"
CONFERENCE_LIST = "results/accepted_papers.json"
TRANSLATE_MODEL = "gemini-2.5-flash"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full paper pipeline from a specified builder")
    parser.add_argument("--builder", required=True, help="Path to builder script (e.g. scripts/list-builders/build_sigir2025_paper_list.py)")
    args = parser.parse_args()

    builder_path = Path(args.builder)
    if not builder_path.is_file():
        raise SystemExit(f"builder not found: {builder_path}")

    pipeline_dir = Path("scripts/pipeline")
    if not pipeline_dir.is_dir():
        raise SystemExit(f"pipeline directory not found: {pipeline_dir}")

    conference_list = Path(CONFERENCE_LIST)

    # Step 1: builder
    conference_list.parent.mkdir(parents=True, exist_ok=True)
    run_cmd([sys.executable, str(builder_path), "--output", str(conference_list)])

    # Step 2: build master
    run_cmd([sys.executable, str(pipeline_dir / "build_master_list.py"), "--conference-list", str(conference_list), "--output", MASTER])

    # Step 3: enrich
    run_cmd([sys.executable, str(pipeline_dir / "enrich_abstracts.py"), "--input", MASTER, "--output", ENRICHED])

    # Step 4: filter
    run_cmd([sys.executable, str(pipeline_dir / "filter_ad_papers.py"), "--input", ENRICHED, "--output", FILTERED])

    # Step 5: translate
    run_cmd([sys.executable, str(pipeline_dir / "translate_filtered.py"), "--input", FILTERED, "--output", TRANSLATED, "--model", TRANSLATE_MODEL])

    # Step 6: export markdown
    run_cmd([sys.executable, str(pipeline_dir / "export_translated_markdown.py"), "--input", TRANSLATED, "--output", MARKDOWN, "--title", read_markdown_title(conference_list)])

    print("Pipeline completed successfully.")


if __name__ == "__main__":
    main()
