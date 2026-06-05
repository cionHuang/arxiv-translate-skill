#!/usr/bin/env python3
"""Validate and merge subagent JSONL translation results."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable


PLACEHOLDER_PATTERNS = [
    re.compile(r"\{v\d+\}"),
    re.compile(r"\{\{[^{}\n]{1,80}\}\}"),
    re.compile(r"<\|[^|\n]{1,80}\|>"),
    re.compile(r"@@[^@\s]{1,80}@@"),
]
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
REFERENCE_HEADER_RE = re.compile(r"^\s*(references|bibliography|参考文献)\s*$", re.IGNORECASE)
REFERENCE_ENTRY_START_RE = re.compile(r"^\s*(?:\[\d+\]|\d+\.|[A-Z][a-zA-Z-]+,\s+[A-Z])")
REFERENCE_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}[a-z]?\b")
REFERENCE_SOURCE_RE = re.compile(
    r"\b(?:doi|arxiv|proceedings|conference|journal|transactions|"
    r"workshop|symposium|press|vol\.|pp\.|pages?|isbn|https?://)\b",
    re.IGNORECASE,
)
REFERENCE_AUTHOR_RE = re.compile(r"\b(?:et al\.|[A-Z][a-zA-Z-]+,\s+[A-Z]\.|[A-Z]\.\s+[A-Z][a-zA-Z-]+)")


def read_jsonl(path: Path) -> Iterable[tuple[int, dict]]:
    with path.open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield lineno, json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSONL: {exc}") from exc


def iter_result_files(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(item for item in path.glob("*.jsonl") if item.is_file())
    return [path]


def inferred_placeholders(text: str) -> list[str]:
    found: list[str] = []
    for pattern in PLACEHOLDER_PATTERNS:
        found.extend(pattern.findall(text))
    return list(dict.fromkeys(found))


def expected_translation_item_ids(source_text: str) -> list:
    marker = "## Here is the input:"
    if marker not in source_text:
        return []
    payload = source_text.split(marker, 1)[1].strip()
    try:
        items = json.loads(payload)
    except json.JSONDecodeError:
        return []
    if not isinstance(items, list):
        return []
    ids = []
    for item in items:
        if isinstance(item, dict) and "id" in item and "input" in item:
            ids.append(item.get("id"))
    return ids


def validate_json_array_output(translated: str, expected_ids: list, unit_id: str) -> list[str]:
    if not expected_ids:
        return []
    try:
        payload = json.loads(translated)
    except json.JSONDecodeError as exc:
        return [f"{unit_id}: translated_text must be a JSON array string: {exc}"]
    if not isinstance(payload, list):
        return [f"{unit_id}: translated_text must decode to a JSON array"]

    seen_ids = []
    errors: list[str] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            errors.append(f"{unit_id}: JSON array item {index} is not an object")
            continue
        if set(item) - {"id", "output"}:
            errors.append(f"{unit_id}: JSON array item {index} contains keys other than id/output")
        if "id" not in item:
            errors.append(f"{unit_id}: JSON array item {index} is missing id")
        else:
            seen_ids.append(item.get("id"))
        output = item.get("output")
        if not isinstance(output, str) or not output.strip():
            errors.append(f"{unit_id}: JSON array item {index} has empty output")

    if seen_ids != expected_ids:
        errors.append(f"{unit_id}: JSON array ids changed from {expected_ids!r} to {seen_ids!r}")
    return errors


def looks_like_reference(text: str) -> bool:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return False
    if REFERENCE_HEADER_RE.fullmatch(compact):
        return True

    signals = 0
    if REFERENCE_ENTRY_START_RE.search(compact):
        signals += 1
    if REFERENCE_YEAR_RE.search(compact):
        signals += 1
    if REFERENCE_SOURCE_RE.search(compact):
        signals += 1
    if REFERENCE_AUTHOR_RE.search(compact):
        signals += 1
    if compact.count(".") >= 3 and compact.count(",") >= 2:
        signals += 1
    return signals >= 3


def unit_text_for_reference_detection(unit: dict) -> str:
    return str(unit.get("translation_input") or unit.get("source_text") or "")


def load_units(units_path: Path) -> tuple[list[str], dict[str, dict]]:
    order: list[str] = []
    units: dict[str, dict] = {}
    for lineno, unit in read_jsonl(units_path):
        unit_id = unit.get("unit_id")
        if not unit_id:
            raise ValueError(f"{units_path}:{lineno}: missing unit_id")
        if unit_id in units:
            raise ValueError(f"{units_path}:{lineno}: duplicate unit_id: {unit_id}")
        if "placeholder_tokens" in unit:
            placeholders = unit.get("placeholder_tokens") or []
        else:
            placeholders = inferred_placeholders(unit.get("translation_input") or unit.get("source_text", ""))
        unit["placeholder_tokens"] = placeholders
        units[unit_id] = unit
        order.append(unit_id)
    return order, units


def validate(units_path: Path, results_path: Path) -> tuple[list[dict], list[str], list[str]]:
    order, units = load_units(units_path)
    results: dict[str, dict] = {}
    errors: list[str] = []
    warnings: list[str] = []

    for result_file in iter_result_files(results_path):
        for lineno, result in read_jsonl(result_file):
            unit_id = result.get("unit_id")
            if not unit_id:
                errors.append(f"{result_file}:{lineno}: missing unit_id")
                continue
            if unit_id not in units:
                errors.append(f"{result_file}:{lineno}: unknown unit_id: {unit_id}")
                continue
            if unit_id in results:
                errors.append(f"{result_file}:{lineno}: duplicate translated unit_id: {unit_id}")
                continue

            expected_hash = units[unit_id].get("source_hash")
            if result.get("source_hash") != expected_hash:
                errors.append(f"{result_file}:{lineno}: source_hash mismatch for {unit_id}")
                continue

            translated = result.get("translated_text")
            if not isinstance(translated, str) or not translated.strip():
                errors.append(f"{result_file}:{lineno}: empty translated_text for {unit_id}")
                continue

            for token in units[unit_id].get("placeholder_tokens", []):
                if token and token not in translated:
                    errors.append(f"{result_file}:{lineno}: missing placeholder {token!r} for {unit_id}")

            json_errors = validate_json_array_output(
                translated,
                expected_translation_item_ids(str(units[unit_id].get("source_text") or "")),
                unit_id,
            )
            for error in json_errors:
                errors.append(f"{result_file}:{lineno}: {error}")

            reference_text = unit_text_for_reference_detection(units[unit_id])
            if looks_like_reference(reference_text) and not CJK_RE.search(reference_text) and CJK_RE.search(translated):
                errors.append(f"{result_file}:{lineno}: reference/bibliography content must not be translated for {unit_id}")

            source_len = max(1, len(units[unit_id].get("source_text", "")))
            if len(translated) / source_len > 4.5:
                warnings.append(f"{result_file}:{lineno}: translated_text is unusually long for {unit_id}")

            results[unit_id] = {
                "unit_id": unit_id,
                "source_hash": expected_hash,
                "translated_text": translated,
                "notes": result.get("notes", ""),
            }

    missing = [unit_id for unit_id in order if unit_id not in results]
    for unit_id in missing:
        errors.append(f"missing translation for {unit_id}")

    merged = [results[unit_id] for unit_id in order if unit_id in results]
    return merged, errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("units", type=Path, help="translation_units.jsonl")
    parser.add_argument("results", type=Path, help="JSONL result file or directory of JSONL result files")
    parser.add_argument("--write-completed", type=Path, help="write merged translations.completed.jsonl here")
    args = parser.parse_args()

    try:
        merged, errors, warnings = validate(args.units, args.results)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)

    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1

    if args.write_completed:
        args.write_completed.parent.mkdir(parents=True, exist_ok=True)
        with args.write_completed.open("w", encoding="utf-8") as handle:
            for item in merged:
                handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")

    print(json.dumps({"ok": True, "translations": len(merged), "warnings": len(warnings)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
