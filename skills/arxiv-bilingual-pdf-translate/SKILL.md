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
   - Use the produced run directory for every later artifact.
2. Build glossary:
   - Merge user terms with any local `all_terms.csv` or `all_terms.json`.
   - If TeX source was downloaded, use it to identify titles, section names, symbols, and repeated technical terms.
3. Extract BabelDOC translation units:
   - Run `.venv/bin/python <skill_dir>/scripts/babeldoc_agent_bridge.py extract --pdf <run>/source.pdf --work-dir <run>/babeldoc_work --output-dir <run>/output --units <run>/translation_units.jsonl`.
   - This must not call any external LLM API.
4. Batch work:
   - Run `.venv/bin/python <skill_dir>/scripts/build_batches.py <run>/translation_units.jsonl --output-dir <run>/batches`.
5. Translate with subagents:
   - Spawn concurrent subagents with `multi_agent_v1.spawn_agent`.
   - Give each subagent exactly one `batches/batch_*.jsonl` plus the glossary/style instructions.
   - Require strict JSONL output with `unit_id`, `source_hash`, `translated_text`, and `notes`.
   - Do not ask subagents to edit the PDF or run BabelDOC.
6. Validate and merge:
   - Save each subagent result as `<run>/batch_results/batch_*.jsonl`.
   - Run `.venv/bin/python <skill_dir>/scripts/validate_translations.py <run>/translation_units.jsonl <run>/batch_results --write-completed <run>/translations.completed.jsonl`.
   - Re-run failed or missing batches only.
7. Render:
   - Run `.venv/bin/python <skill_dir>/scripts/babeldoc_agent_bridge.py render --pdf <run>/source.pdf --work-dir <run>/babeldoc_work --output-dir <run>/output --translations <run>/translations.completed.jsonl --no-mono`.
   - Confirm a `.dual.pdf` file exists in `<run>/output`.
   - The bridge disables BabelDOC's upstream watermark by default and adds this project's own notice to the rendered PDF. Use `--custom-notice "..."` to override the notice text, or `--no-custom-notice` only when the user explicitly requests no notice.

## Subagent Prompt Contract

Read `references/translation-style.md` and `references/translation-contract.md` before dispatching translation batches. Every subagent must preserve placeholders exactly and output only JSONL.

Recommended dispatch size: 30-60 units per subagent, or lower if a batch contains long paragraphs.
`build_batches.py` writes compact batches by default and sizes them by `translation_input`, not the repeated full BabelDOC prompt. Use `--full-source` only for debugging a problematic unit.

## Failure Handling

- If validation reports missing IDs, reassign only those units.
- If placeholders are missing or altered, reassign that batch with a stricter prompt.
- If BabelDOC import fails, install BabelDOC into the project-local `.venv` first; do not fall back to TeX recompilation as the bilingual PDF path.
- If BabelDOC render fails on a specific PDF, retry with `--disable-rich-text-translate` or `--enhance-compatibility`.
- If the custom notice cannot be added because PyMuPDF is unavailable, fix the BabelDOC environment; do not restore the upstream BabelDOC watermark.

## References

- Translation contract: `references/translation-contract.md`
- Translation style: `references/translation-style.md`
- BabelDOC bridge details: `references/babeldoc-bridge.md`
