---
name: arxiv-translate-skill
description: Local Codex workflow for translating arXiv papers from LaTeX source into Simplified Chinese without external LLM APIs. Use when the user asks to translate an arXiv paper, arXiv ID/URL, or LaTeX academic paper locally; supports deterministic download/parse/split/merge scripts, local agent/subagent translation, glossary consistency, translated .tex output, required PDF compilation, and page-safe bilingual PDF generation when page counts match.
---

# arxiv-translate-skill

## Overview

Translate arXiv papers locally with Codex/subagents. Use bundled scripts for deterministic arXiv and LaTeX processing; use the current agent and subagents for translation. Do not call external LLM APIs.

Required outputs are a translated `.tex` file under `build/`, a final PDF in the paper root, and root-level `article_summary.md`. PDF generation is mandatory for normal skill completion. The default PDF policy tries bilingual side-by-side output only when original and translated page counts match; otherwise the Chinese-only PDF becomes the final PDF and the mismatch is recorded in `build/merge_report.json`. `article_summary.md` is a compact paper overview for quick reading and follow-up AI/agent Q&A context.

## Workflow

1. Read `references/workflow.md` for the full role model and PDF policy.
2. Run `scripts/prepare_arxiv_translation.py <arxiv-id-or-url>` to download both arXiv source and the original PDF, then create a translation package.
3. Read the generated `translation_package.json`, `glossary.json`, segment files, and `agent_tasks/manifest.json`.
4. Main agent finalizes the glossary and translation style before assigning work.
5. Give translation subagents the generated `agent_tasks/batch-*.md` files using `references/translation-contract.md`.
6. Save completed translations JSON as `translations.completed.json`.
7. Run `scripts/merge_agent_translations.py <package-json> <translations-json>` to produce the translated `.tex` under `build/`, required root-level PDF, root-level `article_summary.md`, `build/qa_warnings.json`, and `build/translation_log.log`.
8. Use `--pdf-mode translated` when a Chinese-only PDF is requested. `merge_agent_translations.py` automatically reuses `original_pdf_path` from the package for bilingual output; use `--original-pdf <path>` only to override it. Do not use `--allow-misaligned-bilingual` unless the user explicitly accepts page-level comparison with possible text/figure mismatch.

## Agent Responsibilities

- Main agent owns glossary, style guide, consistency, segment assignment, final merge acceptance, and format checks.
- Pipeline subagent may run the scripts, inspect logs, and report paths/status.
- Translation subagents translate assigned segments only and return contract-compliant JSON.
- No subagent may reorder segments, alter segment IDs, or decide final terminology.

## Translation Rules

- Preserve LaTeX commands, citation keys, labels, references, equations, variables, numbering, tables, and environments.
- Treat figures, tables, algorithms, display math, TikZ/PGF drawings, and code/listing environments as indivisible anchor blocks; do not split, reorder, change placement options, change sizing commands, or alter table structure unless the main agent explicitly requests it.
- Translate captions and table text in place only. Captions must remain a single `\caption{...}` argument with no blank lines or paragraph breaks.
- Preserve dataset names, algorithm names, author names, bibliography titles, venues, and English acronyms unless the locked glossary says otherwise.
- Translate academic prose, headings, structural labels, figure/table captions, and table headers into Simplified Chinese.
- First use of a technical term with acronym should be `中文全称（English Acronym）`; later uses must stay consistent.
- Use standard mathematics/statistics/machine-learning terminology, Chinese punctuation, and spaces between Chinese text and English acronyms.
- The translation should read like a Chinese scientific paper rather than a literal draft.
- Use the locked glossary exactly.
- Put uncertain terms in `term_candidates` or `notes`; do not silently invent final terminology.
- Keep `segment_id` and `source_hash` unchanged in worker output.
- Treat `build/qa_warnings.json` as required final review input, especially for untranslated figure text or layout issues.

## Resources

- `scripts/prepare_arxiv_translation.py`: download source and original PDF, parse, split, and package an arXiv LaTeX paper.
- `scripts/merge_agent_translations.py`: validate and merge translated segments; compile the required Chinese-only PDF or page-count-safe bilingual side-by-side PDF.
- `references/workflow.md`: end-to-end workflow, role model, and PDF policy.
- `references/translation-contract.md`: JSON contract for translation workers.
- `references/local-testing.md`: validation and local smoke-test commands.
