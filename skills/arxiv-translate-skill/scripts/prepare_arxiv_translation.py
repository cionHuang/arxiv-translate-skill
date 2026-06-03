#!/usr/bin/env python3
"""Prepare an arXiv LaTeX paper for local agent translation.

This script performs only deterministic work: download, parse, merge, split,
and package metadata for Codex/subagent translation. It never calls an LLM API.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
CORE_DIR = SCRIPT_DIR / "arxiv_translate_core"
sys.path.insert(0, str(CORE_DIR))

from step1_arxiv_downloader import ArxivDownloader  # noqa: E402
from step2_latex_parser import LaTeXParser  # noqa: E402
from step3_content_splitter import LaTeXContentSplitter, get_token_num  # noqa: E402


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "paper"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_terms() -> dict[str, str]:
    terms_path = CORE_DIR / "all_terms.json"
    if not terms_path.exists():
        return {}
    try:
        data = json.loads(terms_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except Exception:
        return {}
    return {}


def relevant_terms(text: str, terms: dict[str, str]) -> dict[str, str]:
    lower_text = text.lower()
    matched: dict[str, str] = {}
    for source, target in terms.items():
        if source.lower() in lower_text:
            matched[source] = target
    return dict(sorted(matched.items(), key=lambda item: item[0].lower()))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download and split an arXiv paper into a local translation package."
    )
    parser.add_argument("arxiv_input", help="arXiv ID or URL, for example 1812.10695")
    parser.add_argument(
        "--work-dir",
        default="arxiv_translate_work",
        help="Directory for generated translation packages.",
    )
    parser.add_argument(
        "--cache-dir",
        default="arxiv_cache",
        help="Directory for arXiv download cache.",
    )
    parser.add_argument(
        "--max-token-limit",
        type=int,
        default=800,
        help="Maximum approximate tokens per translation segment.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Force re-download instead of using cached arXiv sources.",
    )
    parser.set_defaults(download_original_pdf=True)
    parser.add_argument(
        "--download-original-pdf",
        action="store_true",
        help="Download the original arXiv PDF during preparation. This is the default.",
    )
    parser.add_argument(
        "--no-download-original-pdf",
        dest="download_original_pdf",
        action="store_false",
        help="Skip original PDF download. Bilingual merge may download it later or require --original-pdf.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()

    work_root = Path(args.work_dir).resolve()
    cache_dir = Path(args.cache_dir).resolve()
    work_root.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    downloader = ArxivDownloader(cache_dir=str(cache_dir))
    parsed, arxiv_id, _ = downloader.parse_arxiv_input(args.arxiv_input)
    package_name = safe_name(arxiv_id if parsed else args.arxiv_input)
    paper_dir = work_root / package_name
    paper_dir.mkdir(parents=True, exist_ok=True)

    success, extract_path, message = downloader.download_and_extract(
        args.arxiv_input, use_cache=not args.no_cache
    )
    if not success:
        print(json.dumps({"success": False, "error": message}, ensure_ascii=False))
        return 1

    original_pdf_path = ""
    original_pdf_error = ""
    if args.download_original_pdf:
        pdf_success, downloaded_pdf_path, pdf_message = downloader.download_arxiv_pdf(
            arxiv_id if parsed else args.arxiv_input,
            use_cache=not args.no_cache,
        )
        if pdf_success:
            original_pdf_path = str((paper_dir / "original.pdf").resolve())
            shutil_source = Path(downloaded_pdf_path)
            if shutil_source.resolve() != Path(original_pdf_path).resolve():
                shutil.copy2(shutil_source, original_pdf_path)
        else:
            original_pdf_error = pdf_message

    parser = LaTeXParser(work_dir=str(paper_dir / "parser_work"))
    success, merged_latex, message = parser.parse_and_merge(extract_path, add_chinese=True)
    if not success:
        print(json.dumps({"success": False, "error": message}, ensure_ascii=False))
        return 1

    merged_path = paper_dir / "merged_source.tex"
    merged_path.write_text(merged_latex, encoding="utf-8")

    splitter = LaTeXContentSplitter(max_token_limit=args.max_token_limit)
    segments, structure_info = splitter.split_content(merged_latex, project_folder=extract_path)
    if not segments:
        print(json.dumps({"success": False, "error": "No translatable segments found."}))
        return 1

    segments_dir = paper_dir / "segments"
    segments_dir.mkdir(parents=True, exist_ok=True)

    segment_records = []
    for index, text in enumerate(segments):
        segment_id = f"seg-{index + 1:04d}"
        segment_path = segments_dir / f"{segment_id}.tex"
        segment_path.write_text(text, encoding="utf-8")
        segment_records.append(
            {
                "segment_id": segment_id,
                "index": index,
                "source_hash": sha256_text(text),
                "path": str(segment_path),
                "char_count": len(text),
                "token_estimate": get_token_num(text),
            }
        )

    glossary = relevant_terms(merged_latex, load_terms())
    write_json(paper_dir / "glossary.json", glossary)
    structure_info_path = paper_dir / "structure_info.json"
    write_json(structure_info_path, structure_info or [])

    package = {
        "schema_version": 1,
        "arxiv_input": args.arxiv_input,
        "arxiv_id": arxiv_id if parsed else "",
        "source_dir": str(Path(extract_path).resolve()),
        "work_dir": str(paper_dir),
        "merged_latex_path": str(merged_path),
        "segments_dir": str(segments_dir),
        "segment_count": len(segment_records),
        "max_token_limit": args.max_token_limit,
        "glossary_path": str(paper_dir / "glossary.json"),
        "structure_info_path": str(structure_info_path),
        "original_pdf_path": original_pdf_path,
        "original_pdf_error": original_pdf_error,
        "segments": segment_records,
        "structure_info_count": len(structure_info or []),
    }
    package_path = paper_dir / "translation_package.json"
    write_json(package_path, package)

    template = {
        "schema_version": 1,
        "package_path": str(package_path),
        "translations": [
            {
                "segment_id": record["segment_id"],
                "source_hash": record["source_hash"],
                "translated_latex": "",
                "notes": "",
                "term_candidates": {},
            }
            for record in segment_records
        ],
    }
    write_json(paper_dir / "translations.template.json", template)

    print(
        json.dumps(
            {
                "success": True,
                "package_path": str(package_path),
                "segment_count": len(segment_records),
                "glossary_path": str(paper_dir / "glossary.json"),
                "original_pdf_path": original_pdf_path,
                "original_pdf_error": original_pdf_error,
                "translations_template": str(paper_dir / "translations.template.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
