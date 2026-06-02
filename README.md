# ChinarXiv Local Translation Skill

[English](README.md) | [简体中文](README.zh-CN.md)

A Codex skill for translating arXiv/LaTeX academic papers into Simplified Chinese. It uses local Codex/subagents for translation and does not call external LLM APIs; bundled scripts only handle deterministic work such as downloading, parsing, splitting, merging, and PDF compilation.

## Features

- Input: arXiv ID, arXiv URL, or an arXiv LaTeX source paper that can be parsed.
- Translation: split the paper by LaTeX structure and translate segment batches with agents/subagents.
- Terminology and QA: the main agent owns glossary, translation style, consistency, and final checks.
- Required outputs: translated `.tex` and PDF. PDF compilation failure makes the translation run fail.
- Default PDF: bilingual side-by-side PDF with original English pages on the left and Chinese translated pages on the right.
- Clean output: by default, keep only translated `.tex`, final `.pdf`, `qa_warnings.json`, and `translation_log.log`.

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
  python3 "$VALIDATOR" skills/chinarxiv-translate
else
  echo "quick_validate.py not found; run smoke_test.py instead."
fi
```

No-network smoke test: validates `.tex` merging, output cleanup, and path redaction while explicitly skipping PDF compilation.

```bash
python3 skills/chinarxiv-translate/scripts/smoke_test.py
```

PDF smoke test: also validates local PDF compilation, builds a Chinese-only test PDF, and does not download the original English PDF.

```bash
python3 skills/chinarxiv-translate/scripts/smoke_test.py --compile-pdf
```

The PDF smoke test fails if the local machine is missing `xelatex`, `xeCJK`, or Chinese font support.

## Install in an Agent

Install or copy `skills/chinarxiv-translate/` into the agent's skills directory. For Codex, this is typically:

```text
$CODEX_HOME/skills/chinarxiv-translate/
```

Then invoke the skill by name in the conversation.

## Usage

- Basic translation: `Use the chinarxiv-translate skill to translate arXiv 1812.10695 into Simplified Chinese.`
  Feature: downloads arXiv LaTeX source, parses and splits the paper, coordinates agent translation, and produces translated `.tex` plus the default bilingual PDF.
- URL translation: `Use chinarxiv-translate to translate https://arxiv.org/abs/1812.10695 into Simplified Chinese.`
  Feature: extracts the paper ID from an arXiv URL, runs the same translation workflow, and delivers `.tex` plus PDF.
- Bilingual side-by-side PDF: `Use chinarxiv-translate to produce a bilingual side-by-side PDF for https://arxiv.org/abs/1812.10695.`
  Feature: places original English pages on the left and Chinese translated pages on the right for review.
- Chinese-only PDF: `Use chinarxiv-translate to translate arXiv 1812.10695 into a Chinese-only PDF.`
  Feature: produces a PDF containing only the Chinese translated document.
- Continue QA revision: `Continue the chinarxiv-translate workflow and fix the qa_warnings in qa_warnings.json.`
  Feature: revises the translation using QA items such as format-preservation risks, glossary misses, untranslated titles/captions, and layout warnings.

## Local Command Flow

Prepare an arXiv paper:

```bash
python3 skills/chinarxiv-translate/scripts/prepare_arxiv_translation.py 1812.10695
```

Translate the generated segment files using the translation contract:

```text
skills/chinarxiv-translate/references/translation-contract.md
```

Merge completed translations and build the default bilingual PDF:

```bash
python3 skills/chinarxiv-translate/scripts/merge_agent_translations.py \
  chinarxiv_work/1812.10695/translation_package.json \
  chinarxiv_work/1812.10695/translations.completed.json
```

Common PDF options:

- `--pdf-mode translated`: build a Chinese-only PDF.
- `--original-pdf <path>`: reuse a local original English PDF instead of downloading from arXiv.

Development diagnostics:

- `--keep-intermediates`: keep package, segment, compile, and temporary report files.
- `--no-compile-pdf`: skip PDF compilation for debugging only.
- `--allow-pdf-failure`: keep `.tex` even if PDF compilation fails, for debugging only.

## Output Files

After normal delivery, the output directory keeps only:

- `*_translated.tex`: translated Chinese LaTeX.
- `*_translated_bilingual.pdf` or `*_translated.pdf`: final PDF.
- `qa_warnings.json`: translation-quality review items such as untranslated titles/captions, glossary misses, acronym spacing, or image text that cannot be translated automatically.
- `translation_log.log`: total log with format-preservation warnings, PDF compile logs, and final artifact information.

Validation and log output redact local paths with placeholders such as `<SMOKE_TEST_WORK_DIR>` and `<HOME>` where possible.

## Skill Usage Model

- Main agent: glossary, translation rules, consistency, segment assignment, final acceptance.
- Pipeline subagent: runs scripts and reports generated paths/logs.
- Translation subagents: translate assigned segments and return JSON matching the translation contract.

## Skill Layout

```text
skills/chinarxiv-translate/
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
    └── chinarxiv_core/
```
