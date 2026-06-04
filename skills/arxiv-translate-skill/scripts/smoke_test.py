#!/usr/bin/env python3
"""Run a no-network smoke test for the arxiv-translate-skill scripts."""

from __future__ import annotations

import hashlib
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
CORE_DIR = SCRIPT_DIR / "arxiv_translate_core"
sys.path.insert(0, str(CORE_DIR))

from step3_content_splitter import LaTeXContentSplitter  # noqa: E402
from agent_translation_backend import write_agent_artifacts  # noqa: E402


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run arxiv-translate-skill script smoke tests.")
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
    work_dir = Path(tempfile.mkdtemp(prefix="arxiv-translate-skill-test-"))
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
    package["package_path"] = str(package_path)
    agent_artifacts = write_agent_artifacts(
        package=package,
        glossary={"test": "测试"},
        structure_info=json.loads(structure_info_path.read_text(encoding="utf-8")),
        paper_dir=work_dir,
        batch_size=1,
    )
    package["translation_backend"] = agent_artifacts
    package_path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    translations_path.write_text(json.dumps(translations, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest_path = Path(agent_artifacts["manifest_path"])
    task_path = work_dir / "agent_tasks" / "batch-0001.md"
    if not manifest_path.exists() or not task_path.exists():
        print("Smoke test failed: agent task artifacts were not generated.")
        return 1
    task_text = task_path.read_text(encoding="utf-8")
    if "seg-0001" not in task_text or source_hash not in task_text or "```latex" not in task_text:
        print("Smoke test failed: agent task file is missing segment content or metadata.")
        return 1
    template_path = Path(agent_artifacts["translations_template_path"])
    template = json.loads(template_path.read_text(encoding="utf-8"))
    if template.get("translations", [{}])[0].get("segment_id") != "seg-0001":
        print("Smoke test failed: translations template does not contain the expected segment.")
        return 1

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

    output_dir = work_dir / "out"
    build_dir = output_dir / "build"
    tex_path = build_dir / "arxiv_smoke_translated.tex"
    content = tex_path.read_text(encoding="utf-8")
    if "\\label{sec:intro}" not in content or "这是一个测试" not in content:
        print("Smoke test failed: merged tex missing expected content. Work dir: <SMOKE_TEST_WORK_DIR>")
        return 1
    if "% arxiv-translate-skill layout safety" in content or "\\FloatBarrier" in content:
        print("Smoke test failed: repair layout patch was applied in default preserve mode.")
        return 1
    report_path = build_dir / "merge_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    if report.get("layout_mode") != "preserve":
        print("Smoke test failed: merge_report.json did not record preserve layout mode.")
        return 1
    summary_path = output_dir / "article_summary.md"
    summary = summary_path.read_text(encoding="utf-8") if summary_path.exists() else ""
    if "论文速览" not in summary or "章节目录" not in summary:
        print("Smoke test failed: article_summary.md missing expected content. Work dir: <SMOKE_TEST_WORK_DIR>")
        return 1

    output_entries = {path.name for path in output_dir.iterdir()}
    expected_entries = {
        "article_summary.md",
        "build",
    }
    if args.compile_pdf:
        expected_entries.add("arxiv_smoke_translated.pdf")
    if output_entries != expected_entries:
        print(
            "Smoke test failed: output directory contains unexpected entries: "
            + ", ".join(sorted(output_entries))
        )
        return 1

    required_build_entries = {
        "arxiv_smoke_translated.tex",
        "merge_report.json",
        "qa_warnings.json",
        "translation_log.log",
        "package",
    }
    build_entries = {path.name for path in build_dir.iterdir()}
    missing_build_entries = required_build_entries - build_entries
    if missing_build_entries:
        print(
            "Smoke test failed: build directory is missing expected entries: "
            + ", ".join(sorted(missing_build_entries))
        )
        return 1

    if args.compile_pdf and not (output_dir / "arxiv_smoke_translated.pdf").exists():
        print("Smoke test failed: compiled PDF was not generated. Work dir: <SMOKE_TEST_WORK_DIR>")
        return 1

    if args.compile_pdf:
        original_dir = work_dir / "original-pdf"
        original_dir.mkdir()
        original_tex = original_dir / "original_two_pages.tex"
        original_tex.write_text(
            "\\documentclass{article}\n\\begin{document}\nOriginal page one.\\newpage\nOriginal page two.\n\\end{document}\n",
            encoding="utf-8",
        )
        original_compile = subprocess.run(
            [
                args.engine,
                "-interaction=nonstopmode",
                "-file-line-error",
                original_tex.name,
            ],
            cwd=str(original_dir),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        original_pdf = original_tex.with_suffix(".pdf")
        if original_compile.returncode != 0 or not original_pdf.exists():
            print("Smoke test failed: could not create mismatch original PDF.")
            print(redact_local_paths(original_compile.stdout, work_dir))
            return 1

        bilingual_package = dict(package)
        bilingual_package["original_pdf_path"] = str(original_pdf)
        bilingual_package_path = work_dir / "translation_package_bilingual.json"
        bilingual_package_path.write_text(json.dumps(bilingual_package, ensure_ascii=False, indent=2), encoding="utf-8")
        bilingual_out = work_dir / "bilingual-out"
        bilingual_result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "merge_agent_translations.py"),
                str(bilingual_package_path),
                str(translations_path),
                "--output-dir",
                str(bilingual_out),
                "--strict",
                "--engine",
                args.engine,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if bilingual_result.returncode != 0:
            print("Smoke test failed: bilingual mismatch fallback command failed.")
            print(redact_local_paths(bilingual_result.stdout, work_dir))
            return bilingual_result.returncode
        bilingual_report_path = bilingual_out / "build" / "merge_report.json"
        bilingual_report = json.loads(bilingual_report_path.read_text(encoding="utf-8"))
        if bilingual_report.get("bilingual_alignment", "").split(":", 1)[0] != "skipped_page_mismatch":
            print("Smoke test failed: mismatched bilingual output was not guarded.")
            return 1
        if not (bilingual_out / "arxiv_smoke_translated.pdf").exists():
            print("Smoke test failed: mismatched bilingual fallback did not keep translated PDF.")
            return 1
        if (bilingual_out / "arxiv_smoke_translated_bilingual.pdf").exists():
            print("Smoke test failed: mismatched bilingual fallback produced a misleading bilingual PDF.")
            return 1

    splitter = LaTeXContentSplitter(max_token_limit=120)
    split_source = r"""\documentclass{article}
\begin{document}
\section{Introduction}
This paragraph should be translated.
\begin{table}
\caption[Short table title]{Detailed table caption with nested \textbf{important} words}
\begin{tabular}{ll}
Method & Score\\
\end{tabular}
\end{table}
\end{document}
"""
    split_segments, split_structure = splitter.split_content(split_source, str(work_dir / "splitter"))
    joined_segments = "\n".join(split_segments)
    if "Introduction" not in joined_segments:
        print("Smoke test failed: section title was not emitted as a translation segment.")
        return 1
    if "Detailed table caption" not in joined_segments or "Short table title" not in joined_segments:
        print("Smoke test failed: caption title was not emitted as a translation segment.")
        return 1
    preserved_text = "\n".join(item.get("content", "") for item in split_structure if item.get("type") == "preserve")
    if "Detailed table caption" in preserved_text:
        print("Smoke test failed: caption title remained in a preserve block.")
        return 1

    failure_dir = work_dir / "failure-case"
    failure_segments_dir = failure_dir / "segments"
    failure_segments_dir.mkdir(parents=True)
    failure_segment_path = failure_segments_dir / "seg-0001.tex"
    failure_segment_path.write_text(source, encoding="utf-8")
    failure_merged_source_path = failure_dir / "merged_source.tex"
    failure_merged_source_path.write_text(preamble + source + ending, encoding="utf-8")
    failure_structure_info_path = failure_dir / "structure_info.json"
    failure_structure_info_path.write_text(
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
    failure_package_path = failure_dir / "translation_package.json"
    failure_translations_path = failure_dir / "translations.json"
    failure_package = dict(package)
    failure_package.update(
        {
            "source_dir": str(failure_dir),
            "merged_latex_path": str(failure_merged_source_path),
            "structure_info_path": str(failure_structure_info_path),
            "segments_dir": str(failure_segments_dir),
            "segments": [
                {
                    "segment_id": "seg-0001",
                    "index": 0,
                    "source_hash": source_hash,
                    "path": str(failure_segment_path),
                }
            ],
        }
    )
    failure_package_path.write_text(json.dumps(failure_package, ensure_ascii=False, indent=2), encoding="utf-8")
    failure_translations_path.write_text(
        json.dumps({"schema_version": 1, "translations": []}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    failure_result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "merge_agent_translations.py"),
            str(failure_package_path),
            str(failure_translations_path),
            "--output-dir",
            str(failure_dir / "out"),
            "--no-compile-pdf",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if failure_result.returncode == 0:
        print("Smoke test failed: invalid merge unexpectedly succeeded.")
        return 1
    if not failure_package_path.exists() or not failure_translations_path.exists():
        print("Smoke test failed: failed merge removed input package or translations.")
        return 1

    print("Smoke test passed.")
    print("Work dir: <SMOKE_TEST_WORK_DIR>")
    print(f"Translated tex: {redact_local_paths(str(tex_path), work_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
