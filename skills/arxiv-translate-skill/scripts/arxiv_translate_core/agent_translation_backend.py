#!/usr/bin/env python3
"""File-contract backend for agent-based LaTeX translation.

This module is intentionally deterministic. It prepares task files for Codex,
Claude Code, or another coding agent, and validates the JSON shape that agents
write back. It does not call an LLM API.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


TRANSLATIONS_SCHEMA_VERSION = 1
DEFAULT_AGENT_BATCH_SIZE = 8


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_translations(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("translations"), list):
        return payload["translations"]
    raise ValueError("Translations file must be a list or an object with a translations list.")


def relative_display_path(path: Path, base_dir: Path) -> str:
    try:
        return str(path.resolve().relative_to(base_dir.resolve()))
    except ValueError:
        return str(path)


def glossary_hits(text: str, glossary: dict[str, str]) -> dict[str, str]:
    lower_text = text.lower()
    hits: dict[str, str] = {}
    for source, target in glossary.items():
        if source.lower() in lower_text:
            hits[source] = target
    return dict(sorted(hits.items(), key=lambda item: item[0].lower()))


def compact_latex_preview(text: str, limit: int = 900) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    head = compact[: limit // 2].rstrip()
    tail = compact[-limit // 2 :].lstrip()
    return f"{head} ... {tail}"


def segment_context(
    structure_info: list[dict[str, Any]],
    segment_index: int,
    *,
    window_items: int = 5,
) -> dict[str, str]:
    position = None
    for idx, item in enumerate(structure_info):
        if item.get("type") == "translate" and int(item.get("index", -1)) == segment_index:
            position = idx
            break

    if position is None:
        return {"before": "", "after": "", "window": ""}

    before_items = structure_info[max(0, position - window_items) : position]
    after_items = structure_info[position + 1 : position + 1 + window_items]
    before = "".join(str(item.get("content", "")) for item in before_items)
    after = "".join(str(item.get("content", "")) for item in after_items)
    window = before + str(structure_info[position].get("content", "")) + after
    return {
        "before": compact_latex_preview(before, 600),
        "after": compact_latex_preview(after, 600),
        "window": compact_latex_preview(window, 1200),
    }


def build_translation_template(package: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": TRANSLATIONS_SCHEMA_VERSION,
        "package_path": str(package.get("package_path", "")),
        "translations": [
            {
                "segment_id": record["segment_id"],
                "source_hash": record["source_hash"],
                "translated_latex": "",
                "notes": "",
                "term_candidates": {},
            }
            for record in package.get("segments", [])
        ],
    }


def write_translation_template(package: dict[str, Any], paper_dir: Path) -> str:
    template_path = paper_dir / "translations.template.json"
    write_json(template_path, build_translation_template(package))
    return str(template_path)


def validate_translation_contract(
    package: dict[str, Any],
    translations_payload: Any,
) -> tuple[list[dict[str, Any]], list[str]]:
    translations = normalize_translations(translations_payload)
    by_id = {str(item.get("segment_id")): item for item in translations}
    errors: list[str] = []

    for record in package.get("segments", []):
        segment_id = str(record.get("segment_id", ""))
        translation = by_id.get(segment_id)
        if not translation:
            errors.append(f"{segment_id}: missing translation")
            continue
        expected_hash = str(record.get("source_hash", ""))
        provided_hash = str(translation.get("source_hash", ""))
        if provided_hash != expected_hash:
            errors.append(f"{segment_id}: source_hash mismatch")
        translated = str(
            translation.get("translated_latex")
            or translation.get("translation")
            or ""
        )
        if not translated.strip():
            errors.append(f"{segment_id}: empty translated_latex")

    extra_ids = sorted(set(by_id) - {str(record.get("segment_id", "")) for record in package.get("segments", [])})
    for segment_id in extra_ids:
        errors.append(f"{segment_id}: translation is not present in package")

    return translations, errors


def render_agent_task(
    *,
    batch_id: str,
    records: list[dict[str, Any]],
    package: dict[str, Any],
    glossary: dict[str, str],
    structure_info: list[dict[str, Any]],
    paper_dir: Path,
) -> str:
    lines: list[str] = [
        f"# Agent Translation Task {batch_id}",
        "",
        "Translate the listed LaTeX segments into Simplified Chinese.",
        "Return JSON only, using an object with a `translations` list.",
        "Do not reorder, split, merge, or omit segments.",
        "Preserve `segment_id`, `source_hash`, LaTeX commands, labels, citations, equations, and environment structure.",
        "Use `references/translation-contract.md` as the authoritative contract.",
        "",
        "## Output Shape",
        "",
        "```json",
        json.dumps(
            {
                "schema_version": TRANSLATIONS_SCHEMA_VERSION,
                "translations": [
                    {
                        "segment_id": "seg-0001",
                        "source_hash": "copy-source-hash",
                        "translated_latex": "translated LaTeX fragment",
                        "notes": "",
                        "term_candidates": {},
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        "```",
        "",
        "## Package",
        "",
        f"- arxiv_input: {package.get('arxiv_input', '')}",
        f"- arxiv_id: {package.get('arxiv_id', '')}",
        f"- package_path: {relative_display_path(Path(str(package.get('package_path', ''))), paper_dir)}",
        "",
    ]

    if glossary:
        lines.extend(["## Locked Glossary", "", "```json", json.dumps(glossary, ensure_ascii=False, indent=2), "```", ""])

    lines.extend(["## Segments", ""])
    for record in records:
        segment_path = Path(str(record["path"]))
        source = segment_path.read_text(encoding="utf-8")
        context = segment_context(structure_info, int(record.get("index", -1)))
        terms = glossary_hits(source, glossary)
        lines.extend(
            [
                f"### {record['segment_id']}",
                "",
                f"- source_hash: `{record['source_hash']}`",
                f"- source_path: `{relative_display_path(segment_path, paper_dir)}`",
                f"- char_count: {record.get('char_count', len(source))}",
                f"- token_estimate: {record.get('token_estimate', '')}",
            ]
        )
        if terms:
            lines.extend(["- relevant_terms:", "```json", json.dumps(terms, ensure_ascii=False, indent=2), "```"])
        if context["before"] or context["after"]:
            lines.extend(
                [
                    "- nearby_context:",
                    "```text",
                    f"BEFORE: {context['before']}",
                    f"AFTER: {context['after']}",
                    "```",
                ]
            )
        lines.extend(["", "```latex", source, "```", ""])

    return "\n".join(lines).rstrip() + "\n"


def write_agent_artifacts(
    *,
    package: dict[str, Any],
    glossary: dict[str, str],
    structure_info: list[dict[str, Any]],
    paper_dir: Path,
    batch_size: int = DEFAULT_AGENT_BATCH_SIZE,
) -> dict[str, str]:
    batch_size = max(1, batch_size)
    tasks_dir = paper_dir / "agent_tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    template_path = Path(write_translation_template(package, paper_dir))

    task_records: list[dict[str, Any]] = []
    segments = list(package.get("segments", []))
    for batch_number, start in enumerate(range(0, len(segments), batch_size), start=1):
        batch = segments[start : start + batch_size]
        batch_id = f"batch-{batch_number:04d}"
        task_path = tasks_dir / f"{batch_id}.md"
        task_path.write_text(
            render_agent_task(
                batch_id=batch_id,
                records=batch,
                package=package,
                glossary=glossary,
                structure_info=structure_info,
                paper_dir=paper_dir,
            ),
            encoding="utf-8",
        )
        task_records.append(
            {
                "batch_id": batch_id,
                "path": str(task_path),
                "segment_ids": [record["segment_id"] for record in batch],
            }
        )

    manifest = {
        "schema_version": TRANSLATIONS_SCHEMA_VERSION,
        "backend": "agent_file_contract",
        "package_path": str(package.get("package_path", "")),
        "translations_template_path": str(template_path),
        "translations_completed_path": str(paper_dir / "translations.completed.json"),
        "batch_size": batch_size,
        "task_count": len(task_records),
        "segment_count": len(segments),
        "tasks": task_records,
    }
    manifest_path = tasks_dir / "manifest.json"
    write_json(manifest_path, manifest)

    return {
        "backend": "agent_file_contract",
        "tasks_dir": str(tasks_dir),
        "manifest_path": str(manifest_path),
        "translations_template_path": str(template_path),
        "translations_completed_path": str(paper_dir / "translations.completed.json"),
    }
