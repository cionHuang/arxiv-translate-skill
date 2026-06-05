---
name: arxiv-bilingual-pdf-translate
description: Translate arXiv papers or academic PDFs into Simplified Chinese with a required side-by-side bilingual PDF, using BabelDOC for PDF layout/rendering and Codex subagents for concurrent translation without external LLM APIs.
---

# arXiv Bilingual PDF Translate

Use this skill when the user asks to translate an arXiv paper, arXiv URL, LaTeX academic paper, or academic PDF into Simplified Chinese and wants a bilingual PDF. The primary output is always a side-by-side bilingual PDF; translated TeX or monolingual PDF outputs are secondary.

Do not use the older `arxiv-translate-skill` workflow. This skill uses BabelDOC for PDF layout preservation and Codex subagents for translation.

## Core Rule

Keep visual PDF layout work inside BabelDOC. Do not translate TeX and recompile as the main path, because TeX reflow cannot guarantee left/right page alignment. Use TeX source only for context, glossary, and optional secondary artifacts.

## Workflow

1. Prepare input:
   - Run `uv run python <skill_dir>/scripts/prepare_paper.py <arxiv-or-pdf>`.
   - Use the produced run directory for every later artifact.
2. Build glossary:
   - Merge user terms with any local `all_terms.csv` or `all_terms.json`.
   - If TeX source was downloaded, use it to identify titles, section names, symbols, and repeated technical terms.
3. Extract BabelDOC translation units:
   - Run `uv tool run --from BabelDOC python <skill_dir>/scripts/babeldoc_agent_bridge.py extract --pdf <run>/source.pdf --work-dir <run>/babeldoc_work --output-dir <run>/output --units <run>/translation_units.jsonl`.
   - This must not call any external LLM API.
4. Batch work:
   - Run `uv run python <skill_dir>/scripts/build_batches.py <run>/translation_units.jsonl --output-dir <run>/batches`.
5. Translate with subagents:
   - Spawn concurrent subagents with `multi_agent_v1.spawn_agent`.
   - Give each subagent exactly one `batches/batch_*.jsonl` plus the glossary/style instructions.
   - Require strict JSONL output with `unit_id`, `source_hash`, `translated_text`, and `notes`.
   - Do not ask subagents to edit the PDF or run BabelDOC.
6. Validate and merge:
   - Save each subagent result as `<run>/batch_results/batch_*.jsonl`.
   - Run `uv run python <skill_dir>/scripts/validate_translations.py <run>/translation_units.jsonl <run>/batch_results --write-completed <run>/translations.completed.jsonl`.
   - Re-run failed or missing batches only.
7. Render:
   - Run `uv tool run --from BabelDOC python <skill_dir>/scripts/babeldoc_agent_bridge.py render --pdf <run>/source.pdf --work-dir <run>/babeldoc_work --output-dir <run>/output --translations <run>/translations.completed.jsonl --no-mono`.
   - Confirm a `.dual.pdf` file exists in `<run>/output`.

## Subagent Prompt Contract

Read `references/translation-style.md` and `references/translation-contract.md` before dispatching translation batches. Every subagent must preserve placeholders exactly and output only JSONL.

Recommended dispatch size: 30-60 units per subagent, or lower if a batch contains long paragraphs.

## Failure Handling

- If validation reports missing IDs, reassign only those units.
- If placeholders are missing or altered, reassign that batch with a stricter prompt.
- If BabelDOC import fails, install or expose BabelDOC first; do not fall back to TeX recompilation as the bilingual PDF path. With uv tool installation, run the bridge through `uv tool run --from BabelDOC python`.
- If BabelDOC render fails on a specific PDF, retry with `--disable-rich-text-translate` or `--enhance-compatibility`.

## References

- Translation contract: `references/translation-contract.md`
- Translation style: `references/translation-style.md`
- BabelDOC bridge details: `references/babeldoc-bridge.md`
