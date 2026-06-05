#!/usr/bin/env python3
"""Load, validate, and snapshot user-editable translation glossaries."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SOURCE_ALIASES = ("source", "term", "english", "en", "原文")
TARGET_ALIASES = ("target", "translation", "chinese", "zh", "指定表达")
CASE_SENSITIVE_ALIASES = ("case_sensitive", "case-sensitive", "case sensitive", "大小敏感", "大小写敏感")
GLOSSARY_FIELDNAMES = ("source", "target", "case_sensitive")
FALSE_VALUES = {"0", "false", "no", "off", "n"}
TRUE_VALUES = {"1", "true", "yes", "on", "y"}
DEFAULT_GLOSSARY = Path("glossary/terms.csv")
LEGACY_GLOSSARIES = (Path("all_terms.csv"), Path("all_terms.json"))


@dataclass(frozen=True)
class GlossaryTerm:
    source: str
    target: str
    case_sensitive: bool = False
    source_file: str = ""
    source_line: int = 0

    def key(self) -> tuple[str, bool]:
        source = self.source if self.case_sensitive else self.source.lower()
        return source, self.case_sensitive

    def public_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "case_sensitive": self.case_sensitive,
        }

    def csv_row(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "case_sensitive": "true" if self.case_sensitive else "false",
        }


def parse_bool(value: object, *, default: bool = False) -> bool:
    if value is None:
        return default
    text = str(value).strip().lower()
    if not text:
        return default
    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False
    return default


def first_value(row: dict, names: Iterable[str]) -> str:
    lower_row = {str(key).strip().lower(): value for key, value in row.items()}
    for name in names:
        value = lower_row.get(name)
        if value is not None:
            return str(value).strip()
    return ""


def find_project_root(start: Path | None = None) -> Path:
    env_root = os.environ.get("ARXIV_TRANSLATE_PROJECT_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    current = (start or Path.cwd()).expanduser().resolve()
    if current.is_file():
        current = current.parent

    for path in (current, *current.parents):
        if (path / "requirements.txt").exists() and (path / "skills/arxiv-bilingual-pdf-translate/SKILL.md").exists():
            return path
        if (path / ".git").exists() and (path / "skills").exists():
            return path
    return current


def normalize_glossary_path(path: Path, project_root: Path) -> Path:
    path = path.expanduser()
    if not path.is_absolute():
        path = project_root / path
    if path.is_dir():
        path = path / "terms.csv"
    return path.resolve()


def default_glossary_paths(project_root: Path, run_name: str | None = None) -> list[Path]:
    paths = [project_root / DEFAULT_GLOSSARY]
    paths.extend(project_root / item for item in LEGACY_GLOSSARIES)
    if run_name:
        paths.append(project_root / "glossary" / "papers" / f"{run_name}.csv")
        paths.append(project_root / "glossary" / "papers" / f"{run_name}.json")
    return [path.resolve() for path in paths if path.exists()]


def resolve_glossary_paths(
    project_root: Path,
    *,
    explicit_path: Path | None = None,
    run_name: str | None = None,
) -> list[Path]:
    if explicit_path:
        return [normalize_glossary_path(explicit_path, project_root)]

    env_path = os.environ.get("ARXIV_TRANSLATE_GLOSSARY")
    if env_path:
        return [normalize_glossary_path(Path(item), project_root) for item in env_path.split(os.pathsep) if item.strip()]

    return default_glossary_paths(project_root, run_name)


def read_csv_terms(path: Path) -> tuple[list[GlossaryTerm], list[str]]:
    terms: list[GlossaryTerm] = []
    warnings: list[str] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return terms, [f"{path}: missing CSV header"]
        for line_number, row in enumerate(reader, 2):
            source = first_value(row, SOURCE_ALIASES)
            target = first_value(row, TARGET_ALIASES)
            if not source and not target:
                continue
            if not source or not target:
                warnings.append(f"{path}:{line_number}: source and target are both required")
                continue
            terms.append(
                GlossaryTerm(
                    source=source,
                    target=target,
                    case_sensitive=parse_bool(first_value(row, CASE_SENSITIVE_ALIASES), default=False),
                    source_file=str(path),
                    source_line=line_number,
                )
            )
    return terms, warnings


def iter_json_term_rows(data: object) -> Iterable[dict]:
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                yield item
    elif isinstance(data, dict):
        items = data.get("terms")
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    yield item
        else:
            for source, target in data.items():
                if isinstance(target, str):
                    yield {"source": source, "target": target}


def read_json_terms(path: Path) -> tuple[list[GlossaryTerm], list[str]]:
    terms: list[GlossaryTerm] = []
    warnings: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return terms, [f"{path}: invalid JSON: {exc}"]

    for index, row in enumerate(iter_json_term_rows(data), 1):
        source = first_value(row, SOURCE_ALIASES)
        target = first_value(row, TARGET_ALIASES)
        if not source or not target:
            warnings.append(f"{path}: term #{index}: source and target are both required")
            continue
        terms.append(
            GlossaryTerm(
                source=source,
                target=target,
                case_sensitive=parse_bool(first_value(row, CASE_SENSITIVE_ALIASES), default=False),
                source_file=str(path),
                source_line=index,
            )
        )
    return terms, warnings


def load_glossary(paths: Iterable[Path]) -> tuple[list[GlossaryTerm], list[str]]:
    by_key: dict[tuple[str, bool], GlossaryTerm] = {}
    order: list[tuple[str, bool]] = []
    warnings: list[str] = []

    for path in paths:
        if not path.exists():
            warnings.append(f"{path}: glossary file does not exist")
            continue
        if path.suffix.lower() == ".json":
            terms, file_warnings = read_json_terms(path)
        else:
            terms, file_warnings = read_csv_terms(path)
        warnings.extend(file_warnings)
        for term in terms:
            key = term.key()
            if key in by_key:
                previous = by_key[key]
                warnings.append(
                    f"{term.source_file}:{term.source_line}: overrides duplicate term "
                    f"from {previous.source_file}:{previous.source_line}: {term.source}"
                )
            else:
                order.append(key)
            by_key[key] = term

    return [by_key[key] for key in order if key in by_key], warnings


def glossary_digest(terms: Iterable[GlossaryTerm]) -> str:
    payload = json.dumps([term.public_dict() for term in terms], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_terms_csv(path: Path, terms: Iterable[GlossaryTerm]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=GLOSSARY_FIELDNAMES,
        )
        writer.writeheader()
        for term in terms:
            writer.writerow(term.csv_row())


def snapshot_glossary(
    *,
    project_root: Path,
    run_dir: Path,
    run_name: str | None = None,
    explicit_path: Path | None = None,
) -> dict:
    paths = resolve_glossary_paths(project_root, explicit_path=explicit_path, run_name=run_name)
    terms, warnings = load_glossary(paths)
    snapshot_path = run_dir / "glossary.snapshot.csv"
    manifest_path = run_dir / "glossary.manifest.json"
    write_terms_csv(snapshot_path, terms)

    manifest = {
        "snapshot": str(snapshot_path.resolve()),
        "terms": len(terms),
        "sha256": glossary_digest(terms),
        "source_files": [str(path) for path in paths],
        "warnings": warnings,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest["manifest"] = str(manifest_path.resolve())
    return manifest


def load_terms_from_file(path: Path) -> tuple[list[GlossaryTerm], list[str]]:
    return load_glossary([path])


def term_matches(term: GlossaryTerm, text: str) -> bool:
    if not term.source:
        return False
    if term.case_sensitive:
        return term.source in text
    return term.source.lower() in text.lower()


def match_terms(terms: Iterable[GlossaryTerm], text: str, *, limit: int = 40) -> list[GlossaryTerm]:
    matched: list[GlossaryTerm] = []
    seen: set[tuple[str, bool]] = set()
    for term in sorted(terms, key=lambda item: len(item.source), reverse=True):
        key = term.key()
        if key in seen:
            continue
        if term_matches(term, text):
            matched.append(term)
            seen.add(key)
        if len(matched) >= limit:
            break
    return matched


def terms_markdown(terms: Iterable[GlossaryTerm]) -> str:
    rows = list(terms)
    if not rows:
        return "# Batch Glossary\n\nNo matched glossary terms.\n"

    lines = [
        "# Batch Glossary",
        "",
        "Use these terms exactly when they appear in the batch.",
        "",
        "| Source | Target | Case sensitive |",
        "| --- | --- | --- |",
    ]
    for term in rows:
        lines.append(f"| {term.source} | {term.target} | {'true' if term.case_sensitive else 'false'} |")
    lines.append("")
    return "\n".join(lines)


def append_term(path: Path, term: GlossaryTerm) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=GLOSSARY_FIELDNAMES,
        )
        if not exists or path.stat().st_size == 0:
            writer.writeheader()
        writer.writerow(term.csv_row())


def print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="validate the active glossary")
    validate_parser.add_argument("--glossary", type=Path, default=None)

    list_parser = subparsers.add_parser("list", help="list active glossary terms")
    list_parser.add_argument("--glossary", type=Path, default=None)

    add_parser = subparsers.add_parser("add", help="append one term to glossary/terms.csv")
    add_parser.add_argument("source")
    add_parser.add_argument("target")
    add_parser.add_argument("--case-sensitive", action="store_true")
    add_parser.add_argument("--glossary", type=Path, default=None)

    snapshot_parser = subparsers.add_parser("snapshot", help="write a run glossary snapshot")
    snapshot_parser.add_argument("--run-dir", type=Path, required=True)
    snapshot_parser.add_argument("--run-name", default=None)
    snapshot_parser.add_argument("--glossary", type=Path, default=None)

    args = parser.parse_args()
    project_root = args.project_root.resolve() if args.project_root else find_project_root(Path.cwd())

    if args.command in {"validate", "list"}:
        paths = resolve_glossary_paths(project_root, explicit_path=args.glossary)
        terms, warnings = load_glossary(paths)
        if args.command == "list":
            print_json({"terms": [term.public_dict() for term in terms], "warnings": warnings})
        else:
            print_json({"ok": not warnings, "terms": len(terms), "paths": [str(path) for path in paths], "warnings": warnings})
            return 1 if warnings else 0
        return 0

    if args.command == "add":
        glossary_path = normalize_glossary_path(args.glossary or DEFAULT_GLOSSARY, project_root)
        append_term(
            glossary_path,
            GlossaryTerm(
                source=args.source,
                target=args.target,
                case_sensitive=args.case_sensitive,
            ),
        )
        print_json({"ok": True, "path": str(glossary_path), "source": args.source, "target": args.target})
        return 0

    if args.command == "snapshot":
        manifest = snapshot_glossary(
            project_root=project_root,
            run_dir=args.run_dir,
            run_name=args.run_name,
            explicit_path=args.glossary,
        )
        print_json(manifest)
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
