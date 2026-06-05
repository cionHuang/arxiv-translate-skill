# chinarxiv Agent Translation Skills

[English](README.md) | [简体中文](README.zh-CN.md)

Codex skills for translating arXiv papers and academic PDFs into Simplified
Chinese without bundled LLM API calls. The default workflow is
`arxiv-bilingual-pdf-translate`: it uses BabelDOC for PDF layout extraction and
rendering, while Codex/Claude Code subagents translate JSONL text units. The
older `arxiv-translate-skill` LaTeX workflow is kept for users who need editable
translated `.tex` output.

## Workflows

- `arxiv-bilingual-pdf-translate`: default layout-preserving bilingual PDF
  workflow. It starts from the original PDF, extracts BabelDOC translation
  units, sends JSONL batches to local agents, validates the returned JSONL, and
  lets BabelDOC render the final side-by-side `.dual.pdf`.
- `arxiv-translate-skill`: legacy LaTeX workflow. It downloads arXiv source,
  splits TeX segments, asks agents to translate LaTeX fragments, merges them
  into a translated `.tex`, and compiles a Chinese PDF. This remains useful for
  editable TeX output, but TeX reflow cannot guarantee figure/table alignment.

## Features

- Input: arXiv ID, arXiv URL, local academic PDF, or arXiv LaTeX source.
- No bundled LLM API calls: Codex, Claude Code, or another coding agent fills
  deterministic file-contract translation outputs.
- Layout preservation: BabelDOC owns visual PDF parsing and rendering in the
  default workflow, avoiding LaTeX float/page reflow for bilingual PDFs.
- Translation contract: JSONL units preserve `unit_id`, `source_hash`,
  placeholders, tags, references, and BabelDOC-requested output shape.
- Validation: scripts reject missing units, duplicate IDs, hash mismatches,
  empty translations, and placeholder loss before rendering.
- Legacy TeX path: still available when editable translated `.tex`,
  Chinese-only PDF, or LaTeX-level QA is required.

## Requirements

Use `uv` for Python environment and tool management. Do not install project
dependencies into the system Python.

```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt
```

BabelDOC-based PDF rendering should also be installed through `uv tool`:

```bash
uv tool install --python 3.12 BabelDOC
babeldoc --warmup
```

When running BabelDOC bridge scripts from this project, use the BabelDOC tool
environment so the package is importable:

```bash
uv tool run --from BabelDOC python <bridge-script> ...
```

The legacy LaTeX compilation path still requires a local LaTeX environment such
as `xelatex` and Chinese font support. Legacy bilingual side-by-side PDF output
also requires `pdfinfo` from `poppler-utils`. On Ubuntu/Debian, a typical setup
is:

```bash
sudo apt-get install -y texlive-xetex texlive-latex-recommended texlive-latex-extra texlive-lang-chinese poppler-utils fonts-noto-cjk
```

## Validation

Validate both skill metadata files:

```bash
VALIDATOR="${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py"
if [ -f "$VALIDATOR" ]; then
  uv run python "$VALIDATOR" skills/arxiv-bilingual-pdf-translate
  uv run python "$VALIDATOR" skills/arxiv-translate-skill
else
  echo "quick_validate.py not found; run smoke_test.py instead."
fi
```

No-network smoke tests: validate the BabelDOC JSONL file contract and the
legacy `.tex` merge path while skipping external downloads and PDF rendering.

```bash
uv run python skills/arxiv-bilingual-pdf-translate/scripts/smoke_test.py
uv run python skills/arxiv-translate-skill/scripts/smoke_test.py
```

Legacy PDF smoke test: also validates local LaTeX PDF compilation, builds a
Chinese-only test PDF, and does not download the original English PDF.

```bash
uv run python skills/arxiv-translate-skill/scripts/smoke_test.py --compile-pdf
```

The PDF smoke test exercises the legacy LaTeX path and fails if the local
machine is missing `xelatex`, `xeCJK`, or Chinese font support.

## Install in an Agent

Install or copy the required skill directories into the agent's skills
directory. For Codex, this is typically:

```text
$CODEX_HOME/skills/arxiv-bilingual-pdf-translate/
$CODEX_HOME/skills/arxiv-translate-skill/
```

Use `arxiv-bilingual-pdf-translate` by default for bilingual PDFs. Use
`arxiv-translate-skill` only when editable translated TeX is the priority.

## Usage

- Default bilingual PDF: `Use arxiv-bilingual-pdf-translate to translate arXiv 1812.10695 into a side-by-side Simplified Chinese bilingual PDF.`
  Feature: downloads or copies the source PDF, extracts BabelDOC translation
  units, dispatches JSONL batches to agents, validates results, and renders a
  layout-preserving `.dual.pdf`.
- Local PDF: `Use arxiv-bilingual-pdf-translate to translate ./paper.pdf into a side-by-side Chinese bilingual PDF.`
  Feature: uses the same BabelDOC PDF workflow without requiring arXiv source.
- Editable TeX: `Use arxiv-translate-skill to translate arXiv 1812.10695 and produce editable translated TeX.`
  Feature: runs the legacy LaTeX segment workflow and compiles a Chinese PDF
  when the local LaTeX environment is available.

## Output Files

The BabelDOC workflow writes run artifacts under `chinarxiv_runs/<paper>/`:

- `source.pdf`: original input PDF.
- `translation_units.jsonl`: BabelDOC translation requests recorded for agents.
- `batches/`: JSONL work batches for subagents.
- `batch_results/`: JSONL translation results returned by subagents.
- `translations.completed.jsonl`: validated merged translations.
- `output/*.dual.pdf`: final side-by-side bilingual PDF.

The legacy LaTeX workflow keeps final PDFs and Markdown in the paper root:

- `*_translated_bilingual.pdf` or `*_translated.pdf`: final PDF. Bilingual output is skipped automatically when original and translated page counts differ, because page-level pairing would misalign text and figures.
- `article_summary.md`: compact paper overview with title, abstract, section outline, figure/table/algorithm captions, glossary hits, and QA status for quick reading or AI/agent Q&A.

The legacy `build/` directory keeps editable and diagnostic files:

- `*_translated.tex`: translated Chinese LaTeX, kept with compile dependencies for quick edits and recompilation.
- `package/original.pdf`: cached original English PDF copied from the preparation step; bilingual PDF merging prefers this local file.
- `package/agent_tasks/`: generated agent task files for direct Codex/Claude Code translation.
- `package/translations.template.json`: JSON template that agents fill and save as `translations.completed.json`.
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
skills/arxiv-bilingual-pdf-translate/
├── SKILL.md
├── agents/
├── references/
└── scripts/
    ├── prepare_paper.py
    ├── babeldoc_agent_bridge.py
    ├── build_batches.py
    ├── validate_translations.py
    └── smoke_test.py

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
