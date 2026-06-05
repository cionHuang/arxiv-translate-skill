#!/usr/bin/env python3
"""Split BabelDOC translation units into subagent-sized JSONL batches."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable


REFERENCE_HEADER_RE = re.compile(r"^\s*(references|bibliography|参考文献)\s*$", re.IGNORECASE)
REFERENCE_ENTRY_START_RE = re.compile(r"^\s*(?:\[\d+\]|\d+\.|[A-Z][a-zA-Z-]+,\s+[A-Z])")
REFERENCE_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}[a-z]?\b")
REFERENCE_SOURCE_RE = re.compile(
    r"\b(?:doi|arxiv|proceedings|conference|journal|transactions|"
    r"workshop|symposium|press|vol\.|pp\.|pages?|isbn|https?://)\b",
    re.IGNORECASE,
)
REFERENCE_AUTHOR_RE = re.compile(r"\b(?:et al\.|[A-Z][a-zA-Z-]+,\s+[A-Z]\.|[A-Z]\.\s+[A-Z][a-zA-Z-]+)")


def read_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{lineno}: invalid JSONL: {exc}") from exc


def translation_items_from_request(text: str) -> list[dict]:
    marker = "## Here is the input:"
    if marker not in text:
        return []
    payload = text.split(marker, 1)[1].strip()
    try:
        items = json.loads(payload)
    except json.JSONDecodeError:
        return []
    if not isinstance(items, list):
        return []

    compact_items: list[dict] = []
    for item in items:
        if not isinstance(item, dict) or "input" not in item:
            continue
        compact = {
            "id": item.get("id"),
            "input": str(item.get("input", "")),
        }
        if "layout_label" in item:
            compact["layout_label"] = item.get("layout_label")
        compact_items.append(compact)
    return compact_items


def work_text_for_unit(unit: dict) -> str:
    text = unit.get("translation_input") or ""
    if text:
        return str(text)
    return str(unit.get("source_text") or "")


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


def compact_unit(unit: dict) -> dict:
    source_text = str(unit.get("source_text") or "")
    work_text = work_text_for_unit(unit)
    translation_items = translation_items_from_request(source_text)
    output_mode = "json_array" if translation_items else "plain_text"
    is_reference = looks_like_reference(work_text)

    compact = {
        "unit_id": unit.get("unit_id"),
        "source_hash": unit.get("source_hash"),
        "translation_input": unit.get("translation_input") or "",
        "placeholder_tokens": unit.get("placeholder_tokens") or [],
        "output_mode": output_mode,
    }
    if is_reference:
        compact["content_role"] = "reference"
        compact["do_not_translate"] = True

    if translation_items:
        compact["translation_items"] = translation_items
        if is_reference:
            compact["output_instruction"] = (
                "Reference/bibliography content: do not translate. Return translated_text as a compact JSON array "
                "string with the same ids and each output copied unchanged from the corresponding input."
            )
        else:
            compact["output_instruction"] = (
                "Return translated_text as a compact JSON array string with the same ids. "
                "Each item must contain id and output only."
            )
    else:
        if is_reference:
            compact["output_instruction"] = "Reference/bibliography content: do not translate; copy the text unchanged."
        else:
            compact["output_instruction"] = "Return translated_text as the translated text string."
        if not compact["translation_input"]:
            compact["source_text"] = source_text

    return compact


def unit_for_batch(unit: dict, compact: bool) -> dict:
    if compact:
        return compact_unit(unit)
    return unit


def write_batch(output_dir: Path, index: int, units: list[dict], *, compact: bool) -> dict:
    path = output_dir / f"batch_{index:04d}.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for unit in units:
            handle.write(json.dumps(unit_for_batch(unit, compact), ensure_ascii=False, separators=(",", ":")) + "\n")
    translation_chars = sum(len(work_text_for_unit(unit)) for unit in units)
    source_chars = sum(len(str(unit.get("source_text") or "")) for unit in units)
    return {
        "batch": path.name,
        "path": str(path),
        "units": len(units),
        "chars": translation_chars,
        "translation_chars": translation_chars,
        "source_chars": source_chars,
        "compact": compact,
    }


def build_batches(
    units_path: Path,
    output_dir: Path,
    max_units: int,
    max_chars: int,
    *,
    compact: bool = True,
) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    batch: list[dict] = []
    batch_chars = 0
    manifest: list[dict] = []

    for unit in read_jsonl(units_path):
        text_len = len(work_text_for_unit(unit))
        would_exceed_units = len(batch) >= max_units
        would_exceed_chars = batch and batch_chars + text_len > max_chars
        if would_exceed_units or would_exceed_chars:
            manifest.append(write_batch(output_dir, len(manifest) + 1, batch, compact=compact))
            batch = []
            batch_chars = 0
        batch.append(unit)
        batch_chars += text_len

    if batch:
        manifest.append(write_batch(output_dir, len(manifest) + 1, batch, compact=compact))

    manifest_path = output_dir / "batch_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("units", type=Path, help="translation_units.jsonl from babeldoc_agent_bridge.py extract")
    parser.add_argument("--output-dir", type=Path, default=Path("batches"))
    parser.add_argument("--max-units", type=int, default=80)
    parser.add_argument("--max-chars", type=int, default=60000)
    parser.add_argument(
        "--full-source",
        action="store_true",
        help="Write full BabelDOC source_text into every batch item. Default writes compact agent units.",
    )
    args = parser.parse_args()

    manifest = build_batches(args.units, args.output_dir, args.max_units, args.max_chars, compact=not args.full_source)
    print(json.dumps({"batches": len(manifest), "units": sum(item["units"] for item in manifest)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
