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
AGENT_SCOPE_TARGETS = {
    ("codex", "project"): "codex-project",
    ("codex", "user"): "codex-user",
    ("claude", "project"): "claude-project",
    ("claude", "user"): "claude-user",
}


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
    if target in {"agent-repo", "agents-repo", "codex-project"}:
        return project_root / ".agents" / "skills" / SKILL_NAME
    if target == "agent-user":
        return Path.home() / ".agents" / "skills" / SKILL_NAME
    if target in {"codex-user", "codex-home"}:
        return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "skills" / SKILL_NAME
    if target in {"claude-repo", "claude-project"}:
        return project_root / ".claude" / "skills" / SKILL_NAME
    if target == "claude-user":
        return Path.home() / ".claude" / "skills" / SKILL_NAME
    raise ValueError(f"unsupported target: {target}")


def target_from_mode(agent: str | None, scope: str | None, target: str | None) -> str:
    if target and (agent or scope):
        raise ValueError("--target cannot be combined with --agent/--scope")
    if scope and not agent:
        raise ValueError("--scope requires --agent; use --agent codex|claude --scope project|user")
    if target:
        return target
    if agent:
        return AGENT_SCOPE_TARGETS[(agent, scope or "project")]
    return "agent-repo"


def describe_modes(project_root: Path) -> list[dict]:
    modes: list[dict] = []
    for agent, scope in AGENT_SCOPE_TARGETS:
        target = AGENT_SCOPE_TARGETS[(agent, scope)]
        modes.append(
            {
                "agent": agent,
                "scope": scope,
                "target": target,
                "destination": str(target_path(project_root, target, None)),
            }
        )
    return modes


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


def run_bootstrap(project_root: Path) -> tuple[bool, str]:
    script = project_root / SKILL_SOURCE / "scripts" / "bootstrap.py"
    result = subprocess.run(
        [sys.executable, str(script), "--project-root", str(project_root)],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
    )
    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0, output


def write_manifest(
    project_root: Path,
    destination: Path,
    target: str,
    *,
    agent: str | None = None,
    scope: str | None = None,
) -> None:
    manifest = {
        "skill": SKILL_NAME,
        "target": target,
        "agent": agent,
        "scope": scope,
        "project_root": str(project_root.resolve()),
        "source": str((project_root / SKILL_SOURCE).resolve()),
        "installed_to": str(destination.resolve()),
        "runtime_python": str(project_root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")),
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(project_root),
    }
    (destination / ".install-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Common modes:
  Codex project:      --agent codex --scope project
  Codex user:         --agent codex --scope user
  Claude Code project: --agent claude --scope project
  Claude Code user:    --agent claude --scope user

Legacy --target values remain supported for scripts that already use them.
""",
    )
    parser.add_argument("--agent", choices=["codex", "claude"], default=None)
    parser.add_argument("--scope", choices=["project", "user"], default=None)
    parser.add_argument(
        "--target",
        choices=[
            "agent-repo",
            "agent-user",
            "agents-repo",
            "codex-project",
            "codex-user",
            "codex-home",
            "claude-project",
            "claude-repo",
            "claude-user",
        ],
        default=None,
        help="legacy explicit destination selector; prefer --agent/--scope",
    )
    parser.add_argument("--dest", type=Path, default=None, help="custom destination directory")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--force", action="store_true", help="replace an existing installed copy")
    parser.add_argument("--bootstrap", action="store_true", help="create/update the project .venv before installing")
    parser.add_argument("--skip-preflight", action="store_true", help="copy without checking the local environment")
    parser.add_argument("--list-modes", action="store_true", help="print Codex/Claude install modes and exit")
    args = parser.parse_args()

    project_root = args.project_root.resolve() if args.project_root else find_project_root(Path.cwd())
    if args.list_modes:
        print(json.dumps({"skill": SKILL_NAME, "modes": describe_modes(project_root)}, ensure_ascii=False, indent=2))
        return 0

    try:
        target = target_from_mode(args.agent, args.scope, args.target)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    source = project_root / SKILL_SOURCE
    if not (source / "SKILL.md").exists():
        print(f"skill source not found: {source}", file=sys.stderr)
        return 2

    if args.bootstrap:
        ok, output = run_bootstrap(project_root)
        if not ok:
            print(output, file=sys.stderr)
            print("bootstrap failed; fix the setup error and rerun install", file=sys.stderr)
            return 1

    if not args.skip_preflight:
        ok, output = run_preflight(project_root)
        if not ok:
            print(output, file=sys.stderr)
            print(
                "preflight failed; rerun with --bootstrap, run bootstrap.py first, or pass --skip-preflight",
                file=sys.stderr,
            )
            return 1

    destination = target_path(project_root, target, args.dest)
    if destination.exists():
        if not args.force:
            print(f"destination already exists: {destination}; pass --force to replace it", file=sys.stderr)
            return 1
        shutil.rmtree(destination)

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, ignore=ignore_patterns)
    write_manifest(project_root, destination, target, agent=args.agent, scope=args.scope or ("project" if args.agent else None))
    print(
        json.dumps(
            {
                "ok": True,
                "skill": SKILL_NAME,
                "agent": args.agent,
                "scope": args.scope or ("project" if args.agent else None),
                "target": target,
                "source": str(source.resolve()),
                "destination": str(destination.resolve()),
                "project_root": str(project_root.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
