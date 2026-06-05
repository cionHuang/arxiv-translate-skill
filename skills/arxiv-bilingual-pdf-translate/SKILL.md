---
name: arxiv-bilingual-pdf-translate
description: Translate arXiv papers or academic PDFs into Simplified Chinese with a required side-by-side bilingual PDF, using BabelDOC for PDF layout/rendering and Codex subagents for concurrent translation without external LLM APIs.
---

# arXiv Bilingual PDF Translate

Use this skill when the user asks to translate an arXiv paper, arXiv URL, or academic PDF into Simplified Chinese and wants a bilingual PDF. The normal output is always a side-by-side bilingual PDF.

## Core Rule

Keep visual PDF layout work inside BabelDOC. Do not translate TeX and recompile as the main path, because TeX reflow cannot guarantee left/right page alignment. Use TeX source only for context, glossary, and optional secondary artifacts.

## Environment Rule

Run from the project root and use the project-local `.venv/bin/python`.
Do not use `uv tool run --from BabelDOC` as the default path; that creates a separate tool environment and may trigger repeated PyPI downloads in sandboxed agent sessions.

The environment must pass:

```bash
.venv/bin/python -c "import babeldoc.translator.translator"
```

## Workflow

1. Prepare input:
   - Run `.venv/bin/python <skill_dir>/scripts/prepare_paper.py <arxiv-or-pdf>`.
   - Use the produced hidden work directory under `.arxiv_work/` for every later artifact.
2. Build glossary:
   - User-editable project terminology lives at `<project_root>/glossary/terms.csv`.
   - Do not ask the user to copy glossary files into the Codex skill directory.
   - `prepare_paper.py` snapshots the active glossary into `<run>/glossary.snapshot.csv` and records source files in `<run>/glossary.manifest.json`.
   - If the user edits `glossary/terms.csv` after a run has started, refresh the run with `.venv/bin/python <skill_dir>/scripts/glossary.py snapshot --run-dir <run>` and rebuild batches.
   - If TeX source was downloaded, use it only to suggest additional user terms; do not silently rewrite the project glossary.
3. Extract BabelDOC translation units:
   - Run `.venv/bin/python <skill_dir>/scripts/babeldoc_agent_bridge.py extract --pdf <run>/source.pdf --work-dir <run>/babeldoc_work --output-dir <run>/output --units <run>/translation_units.jsonl`.
   - This must not call any external LLM API.
4. Batch work:
   - Run `.venv/bin/python <skill_dir>/scripts/build_batches.py <run>/translation_units.jsonl --output-dir <run>/batches`.
   - The batch builder reads `<run>/glossary.snapshot.csv` automatically and injects only matched terms into each batch.
5. Translate with subagents:
   - Spawn concurrent subagents with `multi_agent_v1.spawn_agent`.
   - Give each subagent exactly one `batches/batch_*.jsonl`, its matching `batches/batch_*.glossary.md` when present, and the style instructions.
   - Require strict JSONL output with `unit_id`, `source_hash`, `translated_text`, and `notes`.
   - Do not ask subagents to edit the PDF or run BabelDOC.
6. Validate and merge:
   - Save each subagent result as `<run>/batch_results/batch_*.jsonl`.
   - Run `.venv/bin/python <skill_dir>/scripts/validate_translations.py <run>/translation_units.jsonl <run>/batch_results --write-completed <run>/translations.completed.jsonl`.
   - Re-run failed or missing batches only.
7. Render:
   - Run `.venv/bin/python <skill_dir>/scripts/babeldoc_agent_bridge.py render --pdf <run>/source.pdf --work-dir <run>/babeldoc_work --output-dir <run>/output --translations <run>/translations.completed.jsonl --no-mono`.
   - Confirm `final_output_files` reports a PDF under `arxiv_outputs/`.
   - Present only the final PDF path to the user. Do not present `.arxiv_work/` intermediate files unless debugging is requested.
   - The bridge disables BabelDOC's upstream watermark by default and adds this project's own notice to the rendered PDF. Use `--custom-notice "..."` to override the notice text, or `--no-custom-notice` only when the user explicitly requests no notice.

## Subagent Prompt Contract

Read `references/translation-style.md` and `references/translation-contract.md` before dispatching translation batches. Every subagent must preserve placeholders exactly and output only JSONL.

Recommended dispatch size: 30-60 units per subagent, or lower if a batch contains long paragraphs.
`build_batches.py` writes compact batches by default and sizes them by `translation_input`, not the repeated full BabelDOC prompt. Use `--full-source` only for debugging a problematic unit.

## Failure Handling

- If validation reports missing IDs, reassign only those units.
- If placeholders or BabelDOC rich-text tags are missing or altered, reassign that batch with a stricter prompt.
- If glossary terms look wrong, update `glossary/terms.csv`, refresh the run glossary snapshot, rebuild batches, and re-run affected batches.
- If BabelDOC import fails, install BabelDOC into the project-local `.venv` first; do not fall back to TeX recompilation as the bilingual PDF path.
- If BabelDOC render fails on a specific PDF, retry with `--disable-rich-text-translate` or `--enhance-compatibility`.
- If the custom notice cannot be added because PyMuPDF is unavailable, fix the BabelDOC environment; do not restore the upstream BabelDOC watermark.

## References

- Translation contract: `references/translation-contract.md`
- Translation style: `references/translation-style.md`
- BabelDOC bridge details: `references/babeldoc-bridge.md`
