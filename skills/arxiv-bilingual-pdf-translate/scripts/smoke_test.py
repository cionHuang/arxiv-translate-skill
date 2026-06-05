#!/usr/bin/env python3
"""No-network smoke test for the BabelDOC agent JSONL workflow."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from build_batches import build_batches
from babeldoc_agent_bridge import publish_final_outputs
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
            "source_text": (
                "Translate the following JSON.\n\n"
                "## Here is the input:\n"
                '[{"id":0,"input":"A second paragraph.","layout_label":"text"}]'
            ),
            "translation_input": "A second paragraph.",
            "placeholder_tokens": [],
            "context": {"call_type": "llm_translate"},
        },
        {
            "unit_id": "u_ref",
            "source_hash": "hash-ref",
            "source_text": "[1] Smith, J. and Doe, A. 2024. Efficient PDF Translation. Journal of Tests, pp. 1-9. doi:10.0000/test.",
            "translation_input": "[1] Smith, J. and Doe, A. 2024. Efficient PDF Translation. Journal of Tests, pp. 1-9. doi:10.0000/test.",
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
        if len(manifest) != 3:
            raise AssertionError(f"expected 3 batches, got {len(manifest)}")
        if not (batches_dir / "batch_manifest.json").exists():
            raise AssertionError("batch_manifest.json was not written")
        first_batch_line = (batches_dir / "batch_0002.jsonl").read_text(encoding="utf-8").strip()
        compact_item = json.loads(first_batch_line)
        if compact_item.get("output_mode") != "json_array":
            raise AssertionError("compact JSON-array output mode was not detected")
        if compact_item.get("translation_items", [{}])[0].get("id") != 0:
            raise AssertionError("translation_items were not extracted from source_text")
        reference_line = (batches_dir / "batch_0003.jsonl").read_text(encoding="utf-8").strip()
        reference_item = json.loads(reference_line)
        if reference_item.get("content_role") != "reference" or not reference_item.get("do_not_translate"):
            raise AssertionError("reference unit was not marked as do_not_translate")

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
                    "translated_text": '[{"id":0,"output":"第二段。"}]',
                    "notes": "",
                }
            ],
        )
        write_jsonl(
            results_dir / "batch_0003.jsonl",
            [
                {
                    "unit_id": "u_ref",
                    "source_hash": "hash-ref",
                    "translated_text": "[1] Smith, J. and Doe, A. 2024. Efficient PDF Translation. Journal of Tests, pp. 1-9. doi:10.0000/test.",
                    "notes": "",
                }
            ],
        )

        merged, errors, warnings = validate(units_path, results_dir)
        if errors:
            raise AssertionError(f"unexpected validation errors: {errors}")
        if len(merged) != 3:
            raise AssertionError(f"expected 3 merged translations, got {len(merged)}")

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
                    "translated_text": '[{"id":0,"output":"第二段。"}]',
                    "notes": "",
                },
                {
                    "unit_id": "u_ref",
                    "source_hash": "hash-ref",
                    "translated_text": "[1] Smith, J. and Doe, A. 2024. Efficient PDF Translation. Journal of Tests, pp. 1-9. doi:10.0000/test.",
                    "notes": "",
                },
            ],
        )
        _, bad_errors, _ = validate(units_path, bad_results)
        if not any("missing placeholder" in error for error in bad_errors):
            raise AssertionError("placeholder validation did not fail as expected")

        bad_reference_results = tmp / "bad_reference_results"
        write_jsonl(
            bad_reference_results / "batch_0001.jsonl",
            [
                {
                    "unit_id": "u_alpha",
                    "source_hash": "hash-alpha",
                    "translated_text": "使用 {v0} 翻译这段文本。",
                    "notes": "",
                },
                {
                    "unit_id": "u_beta",
                    "source_hash": "hash-beta",
                    "translated_text": '[{"id":0,"output":"第二段。"}]',
                    "notes": "",
                },
                {
                    "unit_id": "u_ref",
                    "source_hash": "hash-ref",
                    "translated_text": "[1] Smith, J. and Doe, A. 2024. 高效 PDF 翻译。测试期刊，pp. 1-9. doi:10.0000/test.",
                    "notes": "",
                },
            ],
        )
        _, reference_errors, _ = validate(units_path, bad_reference_results)
        if not any("reference/bibliography content must not be translated" in error for error in reference_errors):
            raise AssertionError("reference translation validation did not fail as expected")

        rendered_dir = tmp / "rendered"
        final_dir = tmp / "final"
        rendered_dir.mkdir()
        rendered_pdf = rendered_dir / "source.zh-CN.dual.pdf"
        rendered_pdf.write_bytes(b"%PDF-1.4\n% smoke placeholder\n")
        final_outputs = publish_final_outputs(rendered_dir, final_dir, run_name="smoke", lang_out="zh-CN")
        if final_outputs != [final_dir / "smoke.zh-CN.dual.pdf"]:
            raise AssertionError(f"unexpected final outputs: {final_outputs}")
        if not final_outputs[0].exists():
            raise AssertionError("final PDF was not published")

    print(json.dumps({"ok": True, "warnings": len(warnings)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
