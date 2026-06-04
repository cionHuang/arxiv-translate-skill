# arxiv-translate-skill

[English](README.md) | [简体中文](README.zh-CN.md)

A Codex skill for translating arXiv/LaTeX academic papers into Simplified Chinese. It uses local Codex/subagents for translation and does not call external LLM APIs; bundled scripts only handle deterministic work such as downloading, parsing, splitting, merging, and PDF compilation.

## Features

- Input: arXiv ID, arXiv URL, or an arXiv LaTeX source paper that can be parsed.
- Downloading: the preparation step downloads both the arXiv LaTeX source and the original English PDF by default, and bilingual PDF merging reuses that local PDF before attempting any later network download.
- Translation: split the paper by LaTeX structure and translate segment batches with agents/subagents.
- Terminology and QA: the main agent owns glossary, translation style, consistency, and final checks.
- Layout policy: treats figures, tables, algorithms, display math, and code blocks as indivisible anchor blocks. Default `--layout-mode preserve` keeps original float placement and sizing; optional `--layout-mode repair` applies FloatBarrier/flafter, image/table size limits, and algorithm shrinkage when needed.
- Required outputs: translated `.tex` and PDF. PDF compilation failure makes the translation run fail.
- Default PDF: tries to build a bilingual side-by-side PDF only when original and translated page counts match; if they differ, it keeps the Chinese-only PDF as the final PDF and records the mismatch in `build/merge_report.json`.
- Article summary: emits `article_summary.md` for quick reading and follow-up AI/agent Q&A context.
- Clean output: by default, keep final PDFs and Markdown in the paper root, and keep compile-ready `.tex`, JSON, logs, and workflow/build files under `build/`.

## Requirements

Install Python dependencies:

```bash
pip install -r requirements.txt
```

PDF compilation requires a local LaTeX environment such as `xelatex` and Chinese font support. Bilingual side-by-side PDF output also requires `pdfinfo` from `poppler-utils`. On Ubuntu/Debian, a typical setup is:

```bash
sudo apt-get install -y texlive-xetex texlive-latex-recommended texlive-latex-extra texlive-lang-chinese poppler-utils fonts-noto-cjk
```

## Validation

Validate skill metadata:

```bash
VALIDATOR="${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py"
if [ -f "$VALIDATOR" ]; then
  python3 "$VALIDATOR" skills/arxiv-translate-skill
else
  echo "quick_validate.py not found; run smoke_test.py instead."
fi
```

No-network smoke test: validates `.tex` merging, output cleanup, and path redaction while explicitly skipping PDF compilation.

```bash
python3 skills/arxiv-translate-skill/scripts/smoke_test.py
```

PDF smoke test: also validates local PDF compilation, builds a Chinese-only test PDF, and does not download the original English PDF.

```bash
python3 skills/arxiv-translate-skill/scripts/smoke_test.py --compile-pdf
```

The PDF smoke test fails if the local machine is missing `xelatex`, `xeCJK`, or Chinese font support.

## Install in an Agent

Install or copy `skills/arxiv-translate-skill/` into the agent's skills directory. For Codex, this is typically:

```text
$CODEX_HOME/skills/arxiv-translate-skill/
```

Then invoke the skill by name in the conversation.

## Usage

- Basic translation: `Use the arxiv-translate-skill skill to translate arXiv 1812.10695 into Simplified Chinese.`
  Feature: downloads arXiv LaTeX source and original English PDF, parses and splits the paper, coordinates agent translation, and produces translated `.tex` plus the default bilingual PDF.
- URL translation: `Use arxiv-translate-skill to translate https://arxiv.org/abs/1812.10695 into Simplified Chinese.`
  Feature: extracts the paper ID from an arXiv URL, runs the same translation workflow, and delivers `.tex` plus PDF.
- Bilingual side-by-side PDF: `Use arxiv-translate-skill to produce a bilingual side-by-side PDF for https://arxiv.org/abs/1812.10695.`
  Feature: places original English pages on the left and Chinese translated pages on the right for review when page counts match. Use `--allow-misaligned-bilingual` only when a mismatched page-thumbnail comparison is acceptable.
- Chinese-only PDF: `Use arxiv-translate-skill to translate arXiv 1812.10695 into a Chinese-only PDF.`
  Feature: produces a PDF containing only the Chinese translated document.
- Continue QA revision: `Continue the arxiv-translate-skill workflow and fix the qa_warnings in build/qa_warnings.json.`
  Feature: revises the translation using QA items such as format-preservation risks, glossary misses, untranslated titles/captions, and layout warnings.

## Output Files

After normal delivery, the paper root keeps only final PDFs and Markdown:

- `*_translated_bilingual.pdf` or `*_translated.pdf`: final PDF. Bilingual output is skipped automatically when original and translated page counts differ, because page-level pairing would misalign text and figures.
- `article_summary.md`: compact paper overview with title, abstract, section outline, figure/table/algorithm captions, glossary hits, and QA status for quick reading or AI/agent Q&A.

The `build/` directory keeps editable and diagnostic files:

- `*_translated.tex`: translated Chinese LaTeX, kept with compile dependencies for quick edits and recompilation.
- `package/original.pdf`: cached original English PDF copied from the preparation step; bilingual PDF merging prefers this local file.
- `qa_warnings.json`: translation-quality review items such as untranslated titles/captions, glossary misses, acronym spacing, or image text that cannot be translated automatically.
- `translation_log.log`: total log with format-preservation warnings, PDF compile logs, and final artifact information.
- `merge_report.json`, `package/`, and PDF compile files needed for debugging or recompilation.

Validation and log output redact local paths with placeholders such as `<SMOKE_TEST_WORK_DIR>` and `<HOME>` where possible.

## License and Attribution

This project is released under the GNU General Public License v3.0. See [LICENSE](LICENSE).

Parts of the LaTeX/arXiv processing ideas and implementation patterns are adapted from or inspired by upstream projects:

- GPT Academic: <https://github.com/binary-husky/gpt_academic>
  License: GNU General Public License v3.0
- chinarxiv: <https://github.com/kaixindelele/chinarxiv>
  License: no explicit license file or GitHub-detected license was identified in the repository root at the time this attribution was written.
- Attribution and modification notes: see [NOTICE](NOTICE)

Copyright for upstream components remains with their respective authors and contributors. Copyright for modifications belongs to this project's contributors, subject to GPL-3.0.

## Skill Usage Model

- Main agent: glossary, translation rules, consistency, segment assignment, final acceptance.
- Pipeline subagent: runs scripts and reports generated paths/logs.
- Translation subagents: translate assigned segments and return JSON matching the translation contract.

## Skill Layout

```text
skills/arxiv-translate-skill/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── references/
│   ├── workflow.md
│   ├── translation-contract.md
│   └── local-testing.md
└── scripts/
    ├── prepare_arxiv_translation.py
    ├── merge_agent_translations.py
    ├── smoke_test.py
    └── arxiv_translate_core/
```
