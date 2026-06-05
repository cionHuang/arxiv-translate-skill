# chinarxiv BabelDOC Agent Translator

[English](README.md) | [简体中文](README.zh-CN.md)

Translate arXiv papers and academic PDFs into Simplified Chinese with a
layout-preserving side-by-side bilingual PDF. This project keeps PDF parsing,
layout, and rendering inside BabelDOC, while Codex, Claude Code, or another
agent platform translates BabelDOC JSONL units. The repository does not call an
LLM API directly.

## Features

- Input: arXiv ID, arXiv URL, or local academic PDF.
- Output: side-by-side bilingual `.dual.pdf`.
- Layout preservation: BabelDOC works from the original PDF, avoiding LaTeX
  recompilation, page reflow, and figure/table float drift.
- Agent translation: BabelDOC translation requests are extracted into JSONL
  units for local agents to translate.
- Notice policy: the bridge disables BabelDOC's upstream watermark by default
  and adds this project's own repository/accuracy notice to rendered PDFs.
- Validation: translation results are rejected before rendering when unit IDs,
  source hashes, placeholders, or required text fields are wrong.
- Optional TeX source: arXiv source can be downloaded for glossary/context, but
  TeX recompilation is not part of the default workflow.

## Environment

Use a project-local `uv` environment. Do not install dependencies into the
system Python, and do not use `uv tool run --from BabelDOC` as the default
bridge command; that can create a separate temporary tool environment and may
trigger repeated PyPI downloads in sandboxed agent sessions.

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -c "import babeldoc.translator.translator; print('BabelDOC ok')"
.venv/bin/babeldoc --warmup
```

Run all repository scripts from the project root with `.venv/bin/python`.

## Validation

Validate the skill metadata:

```bash
VALIDATOR="${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py"
if [ -f "$VALIDATOR" ]; then
  .venv/bin/python "$VALIDATOR" skills/arxiv-bilingual-pdf-translate
else
  echo "quick_validate.py not found; run smoke_test.py instead."
fi
```

Run the no-network smoke test. This validates the JSONL batching and translation
contract without invoking BabelDOC rendering:

```bash
.venv/bin/python skills/arxiv-bilingual-pdf-translate/scripts/smoke_test.py
```

## Install In An Agent

Install or copy the skill directory into the agent's skills directory. For
Codex, this is typically:

```text
$CODEX_HOME/skills/arxiv-bilingual-pdf-translate/
```

The project-local `.venv` is separate from the skill directory. When invoking
the skill, run commands from the project root so `.venv/bin/python` is available.

## Usage

- arXiv paper:
  `Use arxiv-bilingual-pdf-translate to translate arXiv 1812.10695 into a side-by-side Simplified Chinese bilingual PDF.`
- arXiv URL:
  `Use arxiv-bilingual-pdf-translate to translate https://arxiv.org/abs/1812.10695 into a side-by-side Chinese bilingual PDF.`
- Local PDF:
  `Use arxiv-bilingual-pdf-translate to translate ./paper.pdf into a side-by-side Chinese bilingual PDF.`

The workflow is:

1. Prepare `source.pdf` and optional arXiv source context.
2. Extract BabelDOC translation units into `translation_units.jsonl`.
3. Split units into `batches/batch_*.jsonl`.
4. Translate batches with local agent subagents.
5. Validate and merge results into `translations.completed.jsonl`.
6. Render the final `.dual.pdf` with BabelDOC.

## Output Files

Run artifacts are written under `chinarxiv_runs/<paper>/`:

- `source.pdf`: original input PDF.
- `source_tex/`: optional arXiv source context when available.
- `translation_units.jsonl`: BabelDOC translation requests recorded for agents.
- `batches/`: JSONL work batches for subagents.
- `batch_results/`: JSONL translation results returned by subagents.
- `translations.completed.jsonl`: validated merged translations.
- `output/*.dual.pdf`: final side-by-side bilingual PDF.

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
```

## License And Attribution

This project is released under the GNU General Public License v3.0. See
[LICENSE](LICENSE).

This project uses BabelDOC as the PDF parsing and rendering engine and records
workflow inspiration from chinarxiv and GPT Academic in [NOTICE](NOTICE).
