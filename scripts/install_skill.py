#!/usr/bin/env python3
"""Install the repository skill source into an agent-visible skills directory."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


SKILL_NAME = "arxiv-bilingual-pdf-translate"
SKILL_SOURCE = Path("skills") / SKILL_NAME
EXCLUDES = ("__pycache__", "*.pyc", ".DS_Store")


def find_project_root(start: Path) -> Path:
    current = start.expanduser().resolve()
    if current.is_file():
        current = current.parent
    for path in (current, *current.parents):
        if (path / SKILL_SOURCE / "SKILL.md").exists():
            return path
    return current


def target_path(project_root: Path, target: str, dest: Path | None) -> Path:
    if dest:
        return dest.expanduser().resolve()
    if target in {"agent-repo", "agents-repo"}:
        return project_root / ".agents" / "skills" / SKILL_NAME
    if target in {"agent-user", "codex-user"}:
        return Path.home() / ".agents" / "skills" / SKILL_NAME
    if target == "codex-home":
        return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "skills" / SKILL_NAME
    if target == "claude-repo":
        return project_root / ".claude" / "skills" / SKILL_NAME
    raise ValueError(f"unsupported target: {target}")


def ignore_patterns(_: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        if any(fnmatch.fnmatch(name, pattern) for pattern in EXCLUDES):
            ignored.add(name)
    return ignored


def git_commit(project_root: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def run_preflight(project_root: Path) -> tuple[bool, str]:
    script = project_root / SKILL_SOURCE / "scripts" / "preflight.py"
    result = subprocess.run(
        [sys.executable, str(script), "--project-root", str(project_root)],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
    )
    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0, output


def write_manifest(project_root: Path, destination: Path, target: str) -> None:
    manifest = {
        "skill": SKILL_NAME,
        "target": target,
        "source": str((project_root / SKILL_SOURCE).resolve()),
        "installed_to": str(destination.resolve()),
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(project_root),
    }
    (destination / ".install-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        choices=["agent-repo", "agent-user", "agents-repo", "codex-user", "codex-home", "claude-repo"],
        default="agent-repo",
    )
    parser.add_argument("--dest", type=Path, default=None, help="custom destination directory")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--force", action="store_true", help="replace an existing installed copy")
    parser.add_argument("--skip-preflight", action="store_true", help="copy without checking the local environment")
    args = parser.parse_args()

    project_root = args.project_root.resolve() if args.project_root else find_project_root(Path.cwd())
    source = project_root / SKILL_SOURCE
    if not (source / "SKILL.md").exists():
        print(f"skill source not found: {source}", file=sys.stderr)
        return 2

    if not args.skip_preflight:
        ok, output = run_preflight(project_root)
        if not ok:
            print(output, file=sys.stderr)
            print("preflight failed; run bootstrap.py before installing or pass --skip-preflight", file=sys.stderr)
            return 1

    destination = target_path(project_root, args.target, args.dest)
    if destination.exists():
        if not args.force:
            print(f"destination already exists: {destination}; pass --force to replace it", file=sys.stderr)
            return 1
        shutil.rmtree(destination)

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, ignore=ignore_patterns)
    write_manifest(project_root, destination, args.target)
    print(
        json.dumps(
            {
                "ok": True,
                "skill": SKILL_NAME,
                "target": args.target,
                "source": str(source.resolve()),
                "destination": str(destination.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
