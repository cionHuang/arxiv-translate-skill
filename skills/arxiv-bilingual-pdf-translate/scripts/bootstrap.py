#!/usr/bin/env python3
"""Create and warm up the project-local environment for the translation skill."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def find_project_root(start: Path) -> Path:
    current = start.expanduser().resolve()
    if current.is_file():
        current = current.parent
    for path in (current, *current.parents):
        if (path / "requirements.txt").exists() and (path / "skills/arxiv-bilingual-pdf-translate/SKILL.md").exists():
            return path
    return current


def python_path(project_root: Path) -> Path:
    if os.name == "nt":
        return project_root / ".venv" / "Scripts" / "python.exe"
    return project_root / ".venv" / "bin" / "python"


def babeldoc_path(project_root: Path) -> Path:
    if os.name == "nt":
        return project_root / ".venv" / "Scripts" / "babeldoc.exe"
    return project_root / ".venv" / "bin" / "babeldoc"


def runtime_env(project_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["ARXIV_TRANSLATE_PROJECT_ROOT"] = str(project_root)
    env["HOME"] = str(project_root / ".agent_home")
    env["TMPDIR"] = str(project_root / ".tmp")
    env.setdefault("BABELDOC_DISABLE_COREML", "1")
    return env


def run(command: list[str], *, project_root: Path, env: dict[str, str]) -> dict:
    result = subprocess.run(
        command,
        cwd=project_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "ok": result.returncode == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--python", default="3.12", help="Python version for uv venv")
    parser.add_argument("--force-venv", action="store_true", help="run uv venv even when .venv already exists")
    parser.add_argument("--skip-warmup", action="store_true", help="skip BabelDOC asset warmup")
    args = parser.parse_args()

    project_root = args.project_root.resolve() if args.project_root else find_project_root(Path.cwd())
    env = runtime_env(project_root)
    for dirname in (".agent_home", ".tmp", ".arxiv_work", "arxiv_outputs"):
        (project_root / dirname).mkdir(parents=True, exist_ok=True)

    uv = shutil.which("uv")
    steps: list[dict] = []
    if not uv:
        payload = {"ok": False, "project_root": str(project_root), "error": "uv was not found on PATH", "steps": steps}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    venv_python = python_path(project_root)
    if args.force_venv or not venv_python.exists():
        steps.append(run([uv, "venv", "--python", args.python, ".venv"], project_root=project_root, env=env))
        if not steps[-1]["ok"]:
            print(json.dumps({"ok": False, "project_root": str(project_root), "steps": steps}, ensure_ascii=False, indent=2))
            return 1

    steps.append(
        run(
            [uv, "pip", "install", "--python", str(venv_python), "-r", "requirements.txt"],
            project_root=project_root,
            env=env,
        )
    )
    if not steps[-1]["ok"]:
        print(json.dumps({"ok": False, "project_root": str(project_root), "steps": steps}, ensure_ascii=False, indent=2))
        return 1

    steps.append(
        run(
            [str(venv_python), "-c", "import babeldoc.translator.translator; print('babeldoc ok')"],
            project_root=project_root,
            env=env,
        )
    )
    if not steps[-1]["ok"]:
        print(json.dumps({"ok": False, "project_root": str(project_root), "steps": steps}, ensure_ascii=False, indent=2))
        return 1

    warmup = babeldoc_path(project_root)
    if not args.skip_warmup and warmup.exists():
        steps.append(run([str(warmup), "--warmup"], project_root=project_root, env=env))
        if not steps[-1]["ok"]:
            print(json.dumps({"ok": False, "project_root": str(project_root), "steps": steps}, ensure_ascii=False, indent=2))
            return 1

    print(
        json.dumps(
            {
                "ok": True,
                "project_root": str(project_root),
                "python": str(venv_python),
                "warmup": not args.skip_warmup,
                "steps": steps,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
