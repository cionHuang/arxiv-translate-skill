#!/usr/bin/env python3
"""Run a no-network smoke test for the ChinarXiv skill scripts."""

from __future__ import annotations

import hashlib
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run ChinarXiv script smoke tests.")
    parser.add_argument(
        "--compile-pdf",
        action="store_true",
        help="Also validate PDF compilation using a local LaTeX engine.",
    )
    parser.add_argument(
        "--engine",
        default="xelatex",
        choices=["xelatex", "pdflatex"],
        help="LaTeX engine used when --compile-pdf is set.",
    )
    return parser


def redact_local_paths(text: str, work_dir: Path) -> str:
    redacted = text.replace(str(work_dir), "<SMOKE_TEST_WORK_DIR>")
    home = str(Path.home())
    if home and home != "/":
        redacted = redacted.replace(home, "<HOME>")
    return redacted


def main() -> int:
    args = build_arg_parser().parse_args()
    work_dir = Path(tempfile.mkdtemp(prefix="chinarxiv-skill-test-"))
    segments_dir = work_dir / "segments"
    segments_dir.mkdir(parents=True)

    preamble = "\\documentclass{article}\n\\begin{document}\n"
    source = "\\section{Introduction}\nThis is a test with \\label{sec:intro}."
    ending = "\n\\end{document}\n"
    translated = "\\section{引言}\n这是一个测试，包含 \\label{sec:intro}。"

    segment_path = segments_dir / "seg-0001.tex"
    segment_path.write_text(source, encoding="utf-8")
    merged_source_path = work_dir / "merged_source.tex"
    merged_source_path.write_text(preamble + source + ending, encoding="utf-8")

    source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
    structure_info_path = work_dir / "structure_info.json"
    structure_info_path.write_text(
        json.dumps(
            [
                {"type": "preserve", "content": preamble, "index": -1},
                {"type": "translate", "content": source, "index": 0},
                {"type": "preserve", "content": ending, "index": -1},
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    package = {
        "schema_version": 1,
        "arxiv_id": "smoke",
        "source_dir": str(work_dir),
        "merged_latex_path": str(merged_source_path),
        "structure_info_path": str(structure_info_path),
        "segments": [
            {
                "segment_id": "seg-0001",
                "index": 0,
                "source_hash": source_hash,
                "path": str(segment_path),
            }
        ],
    }
    translations = {
        "schema_version": 1,
        "translations": [
            {
                "segment_id": "seg-0001",
                "source_hash": source_hash,
                "translated_latex": translated,
                "notes": "",
                "term_candidates": {},
            }
        ],
    }

    package_path = work_dir / "translation_package.json"
    translations_path = work_dir / "translations.json"
    package_path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    translations_path.write_text(json.dumps(translations, ensure_ascii=False, indent=2), encoding="utf-8")

    command = [
        sys.executable,
        str(SCRIPT_DIR / "merge_agent_translations.py"),
        str(package_path),
        str(translations_path),
        "--output-dir",
        str(work_dir / "out"),
        "--strict",
    ]
    if args.compile_pdf:
        command.extend(["--pdf-mode", "translated", "--engine", args.engine])
    else:
        command.append("--no-compile-pdf")

    result = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    print(redact_local_paths(result.stdout, work_dir))
    if result.returncode != 0:
        print("Smoke test failed. Work dir: <SMOKE_TEST_WORK_DIR>")
        return result.returncode

    tex_path = work_dir / "out" / "arxiv_smoke_translated.tex"
    content = tex_path.read_text(encoding="utf-8")
    if "\\label{sec:intro}" not in content or "这是一个测试" not in content:
        print("Smoke test failed: merged tex missing expected content. Work dir: <SMOKE_TEST_WORK_DIR>")
        return 1
    if "% chinarxiv layout safety" not in content or "\\FloatBarrier" not in content:
        print("Smoke test failed: layout safety patch was not applied. Work dir: <SMOKE_TEST_WORK_DIR>")
        return 1
    summary_path = work_dir / "out" / "article_summary.md"
    summary = summary_path.read_text(encoding="utf-8") if summary_path.exists() else ""
    if "论文速览" not in summary or "章节目录" not in summary:
        print("Smoke test failed: article_summary.md missing expected content. Work dir: <SMOKE_TEST_WORK_DIR>")
        return 1

    output_files = {path.name for path in (work_dir / "out").iterdir()}
    expected_files = {
        "article_summary.md",
        "arxiv_smoke_translated.tex",
        "qa_warnings.json",
        "translation_log.log",
    }
    if args.compile_pdf:
        expected_files.add("arxiv_smoke_translated.pdf")
    if output_files != expected_files:
        print(
            "Smoke test failed: output directory contains unexpected files: "
            + ", ".join(sorted(output_files))
        )
        return 1

    if args.compile_pdf and not (work_dir / "out" / "arxiv_smoke_translated.pdf").exists():
        print("Smoke test failed: compiled PDF was not generated. Work dir: <SMOKE_TEST_WORK_DIR>")
        return 1

    print("Smoke test passed.")
    print("Work dir: <SMOKE_TEST_WORK_DIR>")
    print(f"Translated tex: {redact_local_paths(str(tex_path), work_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
