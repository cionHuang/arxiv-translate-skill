#!/usr/bin/env python3
"""Split BabelDOC translation units into subagent-sized JSONL batches."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable

from glossary import GlossaryTerm, find_project_root, load_terms_from_file, match_terms, terms_markdown


PLACEHOLDER_PATTERNS = [
    re.compile(r"\{v\d+\}"),
    re.compile(r"\{\{[^{}\n]{1,80}\}\}"),
    re.compile(r"<\|[^|\n]{1,80}\|>"),
    re.compile(r"</?b\d+>"),
    re.compile(r"@@[^@\s]{1,80}@@"),
]
REFERENCE_HEADER_RE = re.compile(r"^\s*(references|bibliography|参考文献)\s*$", re.IGNORECASE)
REFERENCE_ENTRY_START_RE = re.compile(r"^\s*(?:\[\d+\]|\d+\.)")
REFERENCE_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}[a-z]?\b")
REFERENCE_SOURCE_RE = re.compile(
    r"\b(?:doi|arxiv|proceedings|conference|journal|transactions|"
    r"workshop|symposium|press|vol\.|pp\.|pages?|isbn|https?://)\b",
    re.IGNORECASE,
)
RICH_TEXT_TAG_RE = re.compile(r"</?b\d+>")
AUTHOR_LIST_RE = re.compile(r"^[A-Z][A-Za-z'’.-]+(?:\s+[A-Z][A-Za-z'’.-]+)*,\s+.+?(?:,\s+and\s+|\s+and\s+)")
ET_AL_START_RE = re.compile(r"^[A-Z][A-Za-z'’-]+\s+et\s+al\.", re.IGNORECASE)
PERSON_NAME_SENTENCE_RE = re.compile(r"^[A-Z][a-zA-Z'’-]+(?:\s+[A-Z]\.){0,4}\s+[A-Z][a-zA-Z'’-]+$")
PROSE_START_RE = re.compile(
    r"^(?:we|our|this|these|in this|another|continuous|since|because|however|therefore|"
    r"consequently|specifically|finally|first|second|third|theorem|lemma|definition)\b",
    re.IGNORECASE,
)


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


def inferred_placeholders(text: str) -> list[str]:
    found: list[str] = []
    for pattern in PLACEHOLDER_PATTERNS:
        found.extend(pattern.findall(text))
    return list(dict.fromkeys(found))


def placeholder_tokens_for_unit(unit: dict) -> list[str]:
    existing = [str(token) for token in unit.get("placeholder_tokens") or [] if token]
    # source_text is often BabelDOC's full translator prompt and may contain
    # placeholder examples such as {v1}; only infer from the real work text.
    inferred = inferred_placeholders(work_text_for_unit(unit))
    return list(dict.fromkeys(existing + inferred))


def work_text_for_unit(unit: dict) -> str:
    text = unit.get("translation_input") or ""
    if text:
        return str(text)
    return str(unit.get("source_text") or "")


def glossary_text_for_unit(unit: dict) -> str:
    source_text = str(unit.get("source_text") or "")
    pieces = [work_text_for_unit(unit), source_text]
    for item in translation_items_from_request(source_text):
        pieces.append(str(item.get("input") or ""))
    return "\n".join(piece for piece in pieces if piece)


def strip_rich_text_tags(text: str) -> str:
    return RICH_TEXT_TAG_RE.sub("", text)


def starts_like_bibliography_author(text: str) -> bool:
    first_sentence = text.split(".", 1)[0].strip()
    if AUTHOR_LIST_RE.search(text[:180]):
        return True
    if ET_AL_START_RE.search(text):
        return True
    if len(first_sentence) <= 80 and PERSON_NAME_SENTENCE_RE.fullmatch(first_sentence):
        return True
    return False


def looks_like_reference(text: str) -> bool:
    compact = re.sub(r"\s+", " ", strip_rich_text_tags(text)).strip()
    if not compact:
        return False
    if REFERENCE_HEADER_RE.fullmatch(compact):
        return True
    if PROSE_START_RE.search(compact):
        return False

    has_year = bool(REFERENCE_YEAR_RE.search(compact))
    has_source = bool(REFERENCE_SOURCE_RE.search(compact))
    if REFERENCE_ENTRY_START_RE.search(compact):
        return has_year and (has_source or compact.count(".") >= 2)
    return starts_like_bibliography_author(compact) and (has_year or has_source)


def glossary_payload_for_unit(unit: dict, glossary_terms: list[GlossaryTerm]) -> list[dict]:
    if not glossary_terms:
        return []
    if looks_like_reference(work_text_for_unit(unit)):
        return []
    return [term.public_dict() for term in match_terms(glossary_terms, glossary_text_for_unit(unit))]


def compact_unit(unit: dict, glossary_terms: list[GlossaryTerm] | None = None) -> dict:
    source_text = str(unit.get("source_text") or "")
    work_text = work_text_for_unit(unit)
    translation_items = translation_items_from_request(source_text)
    output_mode = "json_array" if translation_items else "plain_text"
    is_reference = looks_like_reference(work_text)
    matched_terms = glossary_payload_for_unit(unit, glossary_terms or [])

    compact = {
        "unit_id": unit.get("unit_id"),
        "source_hash": unit.get("source_hash"),
        "translation_input": unit.get("translation_input") or "",
        "placeholder_tokens": placeholder_tokens_for_unit(unit),
        "output_mode": output_mode,
    }
    if matched_terms:
        compact["glossary_terms"] = matched_terms
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


def unit_for_batch(unit: dict, compact: bool, glossary_terms: list[GlossaryTerm]) -> dict:
    if compact:
        return compact_unit(unit, glossary_terms)
    full_unit = dict(unit)
    matched_terms = glossary_payload_for_unit(unit, glossary_terms)
    if matched_terms:
        full_unit["glossary_terms"] = matched_terms
    return full_unit


def batch_glossary_terms(units: list[dict], glossary_terms: list[GlossaryTerm]) -> list[GlossaryTerm]:
    if not glossary_terms:
        return []
    text = "\n".join(
        glossary_text_for_unit(unit)
        for unit in units
        if not looks_like_reference(work_text_for_unit(unit))
    )
    return match_terms(glossary_terms, text, limit=120)


def write_batch(
    output_dir: Path,
    index: int,
    units: list[dict],
    *,
    compact: bool,
    glossary_terms: list[GlossaryTerm],
) -> dict:
    path = output_dir / f"batch_{index:04d}.jsonl"
    batch_terms = batch_glossary_terms(units, glossary_terms)
    with path.open("w", encoding="utf-8") as handle:
        for unit in units:
            handle.write(
                json.dumps(
                    unit_for_batch(unit, compact, glossary_terms),
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            )
    glossary_path = None
    if batch_terms:
        glossary_path = output_dir / f"batch_{index:04d}.glossary.md"
        glossary_path.write_text(terms_markdown(batch_terms), encoding="utf-8")
    translation_chars = sum(len(work_text_for_unit(unit)) for unit in units)
    source_chars = sum(len(str(unit.get("source_text") or "")) for unit in units)
    summary = {
        "batch": path.name,
        "path": str(path),
        "units": len(units),
        "chars": translation_chars,
        "translation_chars": translation_chars,
        "source_chars": source_chars,
        "compact": compact,
        "glossary_terms": len(batch_terms),
    }
    if glossary_path:
        summary["glossary_path"] = str(glossary_path)
    return summary


def build_batches(
    units_path: Path,
    output_dir: Path,
    max_units: int,
    max_chars: int,
    *,
    compact: bool = True,
    glossary_terms: list[GlossaryTerm] | None = None,
) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    batch: list[dict] = []
    batch_chars = 0
    manifest: list[dict] = []
    active_glossary_terms = glossary_terms or []

    for unit in read_jsonl(units_path):
        text_len = len(work_text_for_unit(unit))
        would_exceed_units = len(batch) >= max_units
        would_exceed_chars = batch and batch_chars + text_len > max_chars
        if would_exceed_units or would_exceed_chars:
            manifest.append(
                write_batch(
                    output_dir,
                    len(manifest) + 1,
                    batch,
                    compact=compact,
                    glossary_terms=active_glossary_terms,
                )
            )
            batch = []
            batch_chars = 0
        batch.append(unit)
        batch_chars += text_len

    if batch:
        manifest.append(
            write_batch(
                output_dir,
                len(manifest) + 1,
                batch,
                compact=compact,
                glossary_terms=active_glossary_terms,
            )
        )

    manifest_path = output_dir / "batch_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def default_glossary_path(units_path: Path) -> Path | None:
    snapshot_path = units_path.parent / "glossary.snapshot.csv"
    if snapshot_path.exists():
        return snapshot_path
    project_root = find_project_root(Path.cwd())
    root_glossary = project_root / "glossary" / "terms.csv"
    if root_glossary.exists():
        return root_glossary
    return None


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
    parser.add_argument(
        "--glossary",
        type=Path,
        default=None,
        help="optional glossary CSV/JSON path; defaults to the run glossary snapshot when present",
    )
    args = parser.parse_args()

    glossary_path = args.glossary or default_glossary_path(args.units)
    glossary_terms: list[GlossaryTerm] = []
    glossary_warnings: list[str] = []
    if glossary_path:
        glossary_terms, glossary_warnings = load_terms_from_file(glossary_path)

    manifest = build_batches(
        args.units,
        args.output_dir,
        args.max_units,
        args.max_chars,
        compact=not args.full_source,
        glossary_terms=glossary_terms,
    )
    print(
        json.dumps(
            {
                "batches": len(manifest),
                "units": sum(item["units"] for item in manifest),
                "glossary": str(glossary_path) if glossary_path else None,
                "glossary_terms": len(glossary_terms),
                "glossary_warnings": glossary_warnings,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
