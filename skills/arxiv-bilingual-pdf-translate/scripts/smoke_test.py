#!/usr/bin/env python3
"""No-network smoke test for the BabelDOC agent JSONL workflow."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from build_batches import build_batches
from babeldoc_agent_bridge import publish_final_outputs
from glossary import load_terms_from_file, snapshot_glossary
from validate_translations import validate


def write_jsonl(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")


def read_batch_unit(batches_dir: Path, unit_id: str) -> dict:
    for path in sorted(batches_dir.glob("batch_*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if item.get("unit_id") == unit_id:
                return item
    raise AssertionError(f"unit not found in batches: {unit_id}")


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
                "Translate the following JSON.\n"
                "Do not alter placeholder examples such as {v1} in these instructions.\n\n"
                "## Here is the input:\n"
                '[{"id":0,"input":"A second paragraph.","layout_label":"text"}]'
            ),
            "translation_input": "A second paragraph.",
            "placeholder_tokens": [],
            "context": {"call_type": "llm_translate"},
        },
        {
            "unit_id": "u_cited_body",
            "source_hash": "hash-cited-body",
            "source_text": (
                "We compare Flow Matching with diffusion models on CIFAR-10 "
                "(Krizhevsky et al., 2009) and ImageNet (Deng et al., 2009). "
                "Song et al. (2020) shows strong baselines, but our objective improves training."
            ),
            "translation_input": (
                "We compare Flow Matching with diffusion models on CIFAR-10 "
                "(Krizhevsky et al., 2009) and ImageNet (Deng et al., 2009). "
                "Song et al. (2020) shows strong baselines, but our objective improves training."
            ),
            "placeholder_tokens": [],
            "context": {"call_type": "llm_translate"},
        },
        {
            "unit_id": "u_rich",
            "source_hash": "hash-rich",
            "source_text": "<b1>Flow Matching</b1> improves <b3>training</b3>.",
            "translation_input": "<b1>Flow Matching</b1> improves <b3>training</b3>.",
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
        glossary_source = tmp / "terms.csv"
        glossary_source.write_text(
            (
                "source,target,case_sensitive\n"
                "second paragraph,第二段,false\n"
                "Efficient PDF Translation,Efficient PDF Translation,true\n"
            ),
            encoding="utf-8",
        )
        glossary_manifest = snapshot_glossary(
            project_root=tmp,
            run_dir=tmp,
            explicit_path=glossary_source,
        )
        glossary_terms, glossary_warnings = load_terms_from_file(Path(glossary_manifest["snapshot"]))
        if glossary_warnings:
            raise AssertionError(f"unexpected glossary warnings: {glossary_warnings}")

        manifest = build_batches(units_path, batches_dir, max_units=1, max_chars=120, glossary_terms=glossary_terms)
        if len(manifest) != 5:
            raise AssertionError(f"expected 5 batches, got {len(manifest)}")
        if not (batches_dir / "batch_manifest.json").exists():
            raise AssertionError("batch_manifest.json was not written")
        compact_item = read_batch_unit(batches_dir, "u_beta")
        if compact_item.get("output_mode") != "json_array":
            raise AssertionError("compact JSON-array output mode was not detected")
        if compact_item.get("translation_items", [{}])[0].get("id") != 0:
            raise AssertionError("translation_items were not extracted from source_text")
        if compact_item.get("glossary_terms", [{}])[0].get("target") != "第二段":
            raise AssertionError("matched glossary terms were not injected into the batch item")
        if "{v1}" in compact_item.get("placeholder_tokens", []):
            raise AssertionError("prompt example placeholder leaked into batch placeholder_tokens")
        if not (batches_dir / "batch_0002.glossary.md").exists():
            raise AssertionError("batch glossary markdown was not written")
        cited_body_item = read_batch_unit(batches_dir, "u_cited_body")
        if cited_body_item.get("content_role") == "reference" or cited_body_item.get("do_not_translate"):
            raise AssertionError("citation-heavy body text was incorrectly marked as reference")
        rich_item = read_batch_unit(batches_dir, "u_rich")
        if "<b1>" not in rich_item.get("placeholder_tokens", []) or "</b1>" not in rich_item.get("placeholder_tokens", []):
            raise AssertionError("BabelDOC rich-text tags were not exposed as placeholders")
        reference_item = read_batch_unit(batches_dir, "u_ref")
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
                    "unit_id": "u_cited_body",
                    "source_hash": "hash-cited-body",
                    "translated_text": "我们在 CIFAR-10（Krizhevsky 等，2009）和 ImageNet（Deng 等，2009）上比较 Flow Matching 与扩散模型。Song 等（2020）展示了强基线，但我们的目标函数改进了训练。",
                    "notes": "",
                }
            ],
        )
        write_jsonl(
            results_dir / "batch_0004.jsonl",
            [
                {
                    "unit_id": "u_rich",
                    "source_hash": "hash-rich",
                    "translated_text": "<b1>Flow Matching</b1> 改进了 <b3>训练</b3>。",
                    "notes": "",
                }
            ],
        )
        write_jsonl(
            results_dir / "batch_0005.jsonl",
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
        if len(merged) != 5:
            raise AssertionError(f"expected 5 merged translations, got {len(merged)}")

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
                    "unit_id": "u_cited_body",
                    "source_hash": "hash-cited-body",
                    "translated_text": "我们在 CIFAR-10（Krizhevsky 等，2009）和 ImageNet（Deng 等，2009）上比较 Flow Matching 与扩散模型。Song 等（2020）展示了强基线，但我们的目标函数改进了训练。",
                    "notes": "",
                },
                {
                    "unit_id": "u_rich",
                    "source_hash": "hash-rich",
                    "translated_text": "<b1>Flow Matching</b1> 改进了 <b3>训练</b3>。",
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

        bad_extra_placeholder_results = tmp / "bad_extra_placeholder_results"
        write_jsonl(
            bad_extra_placeholder_results / "batch_0001.jsonl",
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
                    "translated_text": '[{"id":0,"output":"第二段。{v1}"}]',
                    "notes": "",
                },
                {
                    "unit_id": "u_cited_body",
                    "source_hash": "hash-cited-body",
                    "translated_text": "我们在 CIFAR-10（Krizhevsky 等，2009）和 ImageNet（Deng 等，2009）上比较 Flow Matching 与扩散模型。Song 等（2020）展示了强基线，但我们的目标函数改进了训练。",
                    "notes": "",
                },
                {
                    "unit_id": "u_rich",
                    "source_hash": "hash-rich",
                    "translated_text": "<b1>Flow Matching</b1> 改进了 <b3>训练</b3>。",
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
        _, extra_placeholder_errors, _ = validate(units_path, bad_extra_placeholder_results)
        if not any("unexpected placeholder tokens" in error for error in extra_placeholder_errors):
            raise AssertionError("unexpected placeholder validation did not fail as expected")

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
                    "unit_id": "u_cited_body",
                    "source_hash": "hash-cited-body",
                    "translated_text": "我们在 CIFAR-10（Krizhevsky 等，2009）和 ImageNet（Deng 等，2009）上比较 Flow Matching 与扩散模型。Song 等（2020）展示了强基线，但我们的目标函数改进了训练。",
                    "notes": "",
                },
                {
                    "unit_id": "u_rich",
                    "source_hash": "hash-rich",
                    "translated_text": "<b1>Flow Matching</b1> 改进了 <b3>训练</b3>。",
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

        bad_rich_results = tmp / "bad_rich_results"
        write_jsonl(
            bad_rich_results / "batch_0001.jsonl",
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
                    "unit_id": "u_cited_body",
                    "source_hash": "hash-cited-body",
                    "translated_text": "我们在 CIFAR-10（Krizhevsky 等，2009）和 ImageNet（Deng 等，2009）上比较 Flow Matching 与扩散模型。Song 等（2020）展示了强基线，但我们的目标函数改进了训练。",
                    "notes": "",
                },
                {
                    "unit_id": "u_rich",
                    "source_hash": "hash-rich",
                    "translated_text": "<b1>Flow Matching<b1> 改进了 <b3>训练</b3>。",
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
        _, rich_errors, _ = validate(units_path, bad_rich_results)
        if not any("BabelDOC rich-text tags changed" in error for error in rich_errors):
            raise AssertionError("rich-text tag validation did not fail as expected")

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
