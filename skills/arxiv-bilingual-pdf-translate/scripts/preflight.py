#!/usr/bin/env python3
"""Check whether the project environment can run the PDF translation skill."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from glossary import find_project_root


SKILL_RELATIVE_PATH = Path("skills/arxiv-bilingual-pdf-translate/SKILL.md")
RUNTIME_DIRS = (".arxiv_work", "arxiv_outputs", ".agent_home", ".tmp")


def python_path(project_root: Path) -> Path:
    if os.name == "nt":
        return project_root / ".venv" / "Scripts" / "python.exe"
    return project_root / ".venv" / "bin" / "python"


def runtime_env(project_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("ARXIV_TRANSLATE_PROJECT_ROOT", str(project_root))
    env["HOME"] = str(project_root / ".agent_home")
    env["TMPDIR"] = str(project_root / ".tmp")
    env.setdefault("BABELDOC_DISABLE_COREML", "1")
    return env


def check_writable_dir(path: Path, create: bool) -> tuple[bool, str]:
    try:
        if create:
            path.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            return False, "missing"
        if not path.is_dir():
            return False, "not a directory"
        probe = path / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def run_import_check(project_root: Path, python: Path) -> tuple[bool, str]:
    env = runtime_env(project_root)
    for dirname in (".agent_home", ".tmp"):
        (project_root / dirname).mkdir(parents=True, exist_ok=True)
    command = [
        str(python),
        "-c",
        "import babeldoc.translator.translator; print('babeldoc ok')",
    ]
    try:
        result = subprocess.run(
            command,
            cwd=project_root,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    message = (result.stdout + result.stderr).strip()
    return result.returncode == 0, message or f"exit {result.returncode}"


def add_check(checks: list[dict], name: str, ok: bool, detail: str) -> None:
    checks.append({"name": name, "ok": ok, "detail": detail})


def run_preflight(project_root: Path, *, create_dirs: bool = True, skip_babeldoc_import: bool = False) -> dict:
    project_root = project_root.expanduser().resolve()
    checks: list[dict] = []

    skill_path = project_root / SKILL_RELATIVE_PATH
    add_check(checks, "project_root", project_root.exists(), str(project_root))
    add_check(checks, "skill_source", skill_path.exists(), str(skill_path))
    add_check(checks, "requirements", (project_root / "requirements.txt").exists(), "requirements.txt")
    add_check(checks, "glossary", (project_root / "glossary" / "terms.csv").exists(), "glossary/terms.csv")

    for dirname in RUNTIME_DIRS:
        ok, detail = check_writable_dir(project_root / dirname, create_dirs)
        add_check(checks, f"writable:{dirname}", ok, detail)

    python = python_path(project_root)
    add_check(checks, "venv_python", python.exists(), str(python))
    if python.exists() and not skip_babeldoc_import:
        ok, detail = run_import_check(project_root, python)
        add_check(checks, "babeldoc_import", ok, detail)
    elif skip_babeldoc_import:
        add_check(checks, "babeldoc_import", True, "skipped")

    ok = all(item["ok"] for item in checks)
    return {
        "ok": ok,
        "project_root": str(project_root),
        "python": str(python),
        "runtime_env": {
            "ARXIV_TRANSLATE_PROJECT_ROOT": str(project_root),
            "HOME": str(project_root / ".agent_home"),
            "TMPDIR": str(project_root / ".tmp"),
            "BABELDOC_DISABLE_COREML": os.environ.get("BABELDOC_DISABLE_COREML", "1"),
        },
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--no-create-dirs", action="store_true")
    parser.add_argument("--skip-babeldoc-import", action="store_true")
    args = parser.parse_args()

    project_root = args.project_root.resolve() if args.project_root else find_project_root(Path.cwd())
    result = run_preflight(
        project_root,
        create_dirs=not args.no_create_dirs,
        skip_babeldoc_import=args.skip_babeldoc_import,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
