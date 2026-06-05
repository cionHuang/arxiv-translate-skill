#!/usr/bin/env python3
"""Agent-facing command wrapper for the arXiv bilingual PDF workflow."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from glossary import find_project_root


SCRIPT_DIR = Path(__file__).resolve().parent


def runtime_env(project_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["ARXIV_TRANSLATE_PROJECT_ROOT"] = str(project_root)
    env["HOME"] = str(project_root / ".agent_home")
    env["TMPDIR"] = str(project_root / ".tmp")
    env.setdefault("BABELDOC_DISABLE_COREML", "1")
    env.setdefault("LOKY_MAX_CPU_COUNT", str(os.cpu_count() or 4))
    for dirname in (".agent_home", ".tmp", ".arxiv_work", "arxiv_outputs"):
        (project_root / dirname).mkdir(parents=True, exist_ok=True)
    return env


def run(command: list[str], project_root: Path) -> int:
    result = subprocess.run(command, cwd=project_root, env=runtime_env(project_root), check=False)
    return result.returncode


def python_path(project_root: Path) -> Path:
    if os.name == "nt":
        return project_root / ".venv" / "Scripts" / "python.exe"
    return project_root / ".venv" / "bin" / "python"


def run_dir_from_arg(value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("preflight", help="check local project environment")

    prepare = subparsers.add_parser("prepare", help="prepare arXiv id/url or local PDF")
    prepare.add_argument("input")
    prepare.add_argument("--force", action="store_true")
    prepare.add_argument("--glossary", type=Path, default=None)

    extract = subparsers.add_parser("extract", help="extract BabelDOC translation units")
    extract.add_argument("--run-dir", required=True)
    extract.add_argument("--disable-rich-text-translate", action="store_true")
    extract.add_argument("--enhance-compatibility", action="store_true")

    batches = subparsers.add_parser("build-batches", help="build subagent JSONL batches")
    batches.add_argument("--run-dir", required=True)
    batches.add_argument("--max-units", type=int, default=80)
    batches.add_argument("--max-chars", type=int, default=60000)
    batches.add_argument("--full-source", action="store_true")

    validate = subparsers.add_parser("validate", help="validate and merge batch results")
    validate.add_argument("--run-dir", required=True)

    render = subparsers.add_parser("render", help="render final bilingual PDF")
    render.add_argument("--run-dir", required=True)
    render.add_argument("--with-mono", action="store_true")
    render.add_argument("--disable-rich-text-translate", action="store_true")
    render.add_argument("--enhance-compatibility", action="store_true")
    render.add_argument("--custom-notice", default=None)
    render.add_argument("--no-custom-notice", action="store_true")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    project_root = args.project_root.resolve() if args.project_root else find_project_root(Path.cwd())
    python = python_path(project_root)

    if args.command == "preflight":
        return run([sys.executable, str(SCRIPT_DIR / "preflight.py"), "--project-root", str(project_root)], project_root)

    if not python.exists():
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"project-local Python not found: {python}",
                    "hint": "Run python3 skills/arxiv-bilingual-pdf-translate/scripts/bootstrap.py first.",
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2

    if args.command == "prepare":
        command = [str(python), str(SCRIPT_DIR / "prepare_paper.py"), args.input]
        if args.force:
            command.append("--force")
        if args.glossary:
            command.extend(["--glossary", str(args.glossary)])
        return run(command, project_root)

    if args.command == "extract":
        run_dir = run_dir_from_arg(args.run_dir)
        command = [
            str(python),
            str(SCRIPT_DIR / "babeldoc_agent_bridge.py"),
            "extract",
            "--pdf",
            str(run_dir / "source.pdf"),
            "--work-dir",
            str(run_dir / "babeldoc_work"),
            "--output-dir",
            str(run_dir / "output"),
            "--units",
            str(run_dir / "translation_units.jsonl"),
        ]
        if args.disable_rich_text_translate:
            command.append("--disable-rich-text-translate")
        if args.enhance_compatibility:
            command.append("--enhance-compatibility")
        return run(command, project_root)

    if args.command == "build-batches":
        run_dir = run_dir_from_arg(args.run_dir)
        command = [
            str(python),
            str(SCRIPT_DIR / "build_batches.py"),
            str(run_dir / "translation_units.jsonl"),
            "--output-dir",
            str(run_dir / "batches"),
            "--max-units",
            str(args.max_units),
            "--max-chars",
            str(args.max_chars),
        ]
        if args.full_source:
            command.append("--full-source")
        return run(command, project_root)

    if args.command == "validate":
        run_dir = run_dir_from_arg(args.run_dir)
        command = [
            str(python),
            str(SCRIPT_DIR / "validate_translations.py"),
            str(run_dir / "translation_units.jsonl"),
            str(run_dir / "batch_results"),
            "--write-completed",
            str(run_dir / "translations.completed.jsonl"),
        ]
        return run(command, project_root)

    if args.command == "render":
        run_dir = run_dir_from_arg(args.run_dir)
        command = [
            str(python),
            str(SCRIPT_DIR / "babeldoc_agent_bridge.py"),
            "render",
            "--pdf",
            str(run_dir / "source.pdf"),
            "--work-dir",
            str(run_dir / "babeldoc_work"),
            "--output-dir",
            str(run_dir / "output"),
            "--translations",
            str(run_dir / "translations.completed.jsonl"),
        ]
        if not args.with_mono:
            command.append("--no-mono")
        if args.disable_rich_text_translate:
            command.append("--disable-rich-text-translate")
        if args.enhance_compatibility:
            command.append("--enhance-compatibility")
        if args.custom_notice is not None:
            command.extend(["--custom-notice", args.custom_notice])
        if args.no_custom_notice:
            command.append("--no-custom-notice")
        return run(command, project_root)

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
