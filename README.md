# arxiv-translate-skill

[English](README.md) | [简体中文](README.zh-CN.md)

Translate arXiv papers and academic PDFs into Simplified Chinese with a
layout-preserving side-by-side bilingual PDF. This project keeps PDF parsing,
layout, and rendering inside BabelDOC, while Codex, Claude Code, or another
agent platform translates BabelDOC JSONL units. The repository does not call an
LLM API directly.

## Features

- Input: arXiv ID, arXiv URL, or local academic PDF.
- User-facing output: one side-by-side bilingual PDF under `arxiv_outputs/`.
- Layout preservation: BabelDOC works from the original PDF, avoiding LaTeX
  recompilation, page reflow, and figure/table float drift.
- Agent translation: BabelDOC translation requests are extracted into JSONL
  units for local agents to translate.
- Validation: translation results are rejected before rendering when unit IDs,
  source hashes, placeholders, or required text fields are wrong.
- Optional TeX source: arXiv source can be downloaded for glossary/context.

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

## Glossary

Editable terminology lives in the project root:

```text
glossary/terms.csv
```

See [glossary/README.md](glossary/README.md) for the full glossary format and
commands.

Edit this file directly, or append terms with:

```bash
.venv/bin/python skills/arxiv-bilingual-pdf-translate/scripts/glossary.py add "attention mechanism" "注意力机制"
```

The skill reads the project-root glossary on each run and writes a reproducible
snapshot to `.arxiv_work/<paper>/glossary.snapshot.csv`. You do not need
to copy glossary files into the Codex skill directory after editing them.

Validate the active glossary:

```bash
.venv/bin/python skills/arxiv-bilingual-pdf-translate/scripts/glossary.py validate
```

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

1. Prepare `source.pdf` and optional arXiv source context under `.arxiv_work/`.
2. Extract BabelDOC translation units into `translation_units.jsonl`.
3. Split units into `batches/batch_*.jsonl`.
4. Translate batches with local agent subagents.
5. Validate and merge results into `translations.completed.jsonl`.
6. Render the final `.dual.pdf` with BabelDOC and publish it to `arxiv_outputs/`.

## Output Files

The output directory contains only final PDFs:

- `arxiv_outputs/<paper>.zh-CN.dual.pdf`

Intermediate run artifacts are kept under the hidden `.arxiv_work/<paper>/`
directory:

- `source.pdf`: original input PDF.
- `source_tex/`: optional arXiv source context when available.
- `glossary.snapshot.csv`: terminology snapshot used for this run.
- `glossary.manifest.json`: source files, checksum, and glossary warnings.
- `translation_units.jsonl`: BabelDOC translation requests recorded for agents.
- `batches/`: JSONL work batches for subagents.
- `batch_results/`: JSONL translation results returned by subagents.
- `translations.completed.jsonl`: validated merged translations.
- `output/*.dual.pdf`: internal rendered PDF copied to `arxiv_outputs/`.

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
    ├── glossary.py
    ├── validate_translations.py
    └── smoke_test.py
```

## License And Attribution

This project is released under the GNU General Public License v3.0. See
[LICENSE](LICENSE).

Open-source attribution:

- BabelDOC: used as the PDF parsing, layout preservation, and rendering engine.
  BabelDOC is distributed from <https://github.com/funstory-ai/BabelDOC> and is
  marked there as AGPL-3.0 licensed.
- GPT Academic: workflow inspiration for academic paper translation tooling.
  Repository: <https://github.com/binary-husky/gpt_academic>.
- kaixindelele/chinarxiv: original project inspiration. Repository:
  <https://github.com/kaixindelele/chinarxiv>.

See [NOTICE](NOTICE) for details.
