#!/usr/bin/env python3
"""No-network smoke test for the BabelDOC agent JSONL workflow."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from build_batches import build_batches
from validate_translations import validate


def write_jsonl(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")


def main() -> int:
    units = [
        {
            "unit_id": "u_alpha",
            "source_hash": "hash-alpha",
            "source_text": "Translate this text with {v0}.",
            "translation_input": "Translate this text with {v0}.",
            "placeholder_tokens": ["{v0}"],
            "context": {"call_type": "llm_translate"},
        },
        {
            "unit_id": "u_beta",
            "source_hash": "hash-beta",
            "source_text": "A second paragraph.",
            "translation_input": "A second paragraph.",
            "placeholder_tokens": [],
            "context": {"call_type": "llm_translate"},
        },
    ]

    with tempfile.TemporaryDirectory(prefix="arxiv-bilingual-pdf-smoke-") as tmp_name:
        tmp = Path(tmp_name)
        units_path = tmp / "translation_units.jsonl"
        batches_dir = tmp / "batches"
        results_dir = tmp / "batch_results"
        write_jsonl(units_path, units)

        manifest = build_batches(units_path, batches_dir, max_units=1, max_chars=120)
        if len(manifest) != 2:
            raise AssertionError(f"expected 2 batches, got {len(manifest)}")
        if not (batches_dir / "batch_manifest.json").exists():
            raise AssertionError("batch_manifest.json was not written")

        write_jsonl(
            results_dir / "batch_0001.jsonl",
            [
                {
                    "unit_id": "u_alpha",
                    "source_hash": "hash-alpha",
                    "translated_text": "使用 {v0} 翻译这段文本。",
                    "notes": "",
                }
            ],
        )
        write_jsonl(
            results_dir / "batch_0002.jsonl",
            [
                {
                    "unit_id": "u_beta",
                    "source_hash": "hash-beta",
                    "translated_text": "第二段。",
                    "notes": "",
                }
            ],
        )

        merged, errors, warnings = validate(units_path, results_dir)
        if errors:
            raise AssertionError(f"unexpected validation errors: {errors}")
        if len(merged) != 2:
            raise AssertionError(f"expected 2 merged translations, got {len(merged)}")

        bad_results = tmp / "bad_results"
        write_jsonl(
            bad_results / "batch_0001.jsonl",
            [
                {
                    "unit_id": "u_alpha",
                    "source_hash": "hash-alpha",
                    "translated_text": "占位符缺失。",
                    "notes": "",
                },
                {
                    "unit_id": "u_beta",
                    "source_hash": "hash-beta",
                    "translated_text": "第二段。",
                    "notes": "",
                },
            ],
        )
        _, bad_errors, _ = validate(units_path, bad_results)
        if not any("missing placeholder" in error for error in bad_errors):
            raise AssertionError("placeholder validation did not fail as expected")

    print(json.dumps({"ok": True, "warnings": len(warnings)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
