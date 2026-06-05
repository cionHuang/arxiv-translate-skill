# arxiv-translate-skill

[English](README.md) | [简体中文](README.zh-CN.md)

Translate arXiv papers and academic PDFs into Simplified Chinese and produce a
layout-preserving side-by-side bilingual PDF. The left side keeps the original
English PDF layout; the right side contains the Chinese translation rendered by
BabelDOC.

This is a project-coupled Agent Skill. The skill can be installed into an
Agent Skills-compatible client, but the Python/BabelDOC environment is provided
by this repository. The end-to-end workflow has been tested in Codex only.
Other Agent Skills-compatible clients may need their own runtime verification.

## Requirements

- Python 3.12.
- `uv` on `PATH`.
- Network access during setup and when downloading arXiv papers.
- An agent client that can read Agent Skills and run local shell commands.
- Local subagent/parallel-agent support for faster batch translation.

## Setup

Run these commands from the repository root:

```bash
python3 skills/arxiv-bilingual-pdf-translate/scripts/bootstrap.py
.venv/bin/python skills/arxiv-bilingual-pdf-translate/scripts/arxiv_translate.py preflight
```

`bootstrap.py` creates `.venv`, installs pinned dependencies, prepares
project-local runtime directories, and warms BabelDOC assets. `preflight`
checks that the environment, glossary, and writable output directories are
ready.

## Install In Your Agent

Install the skill into the current repository's standard Agent Skills directory:

```bash
.venv/bin/python scripts/install_skill.py --target agent-repo --force
```

Install it into the user-level Agent Skills directory:

```bash
.venv/bin/python scripts/install_skill.py --target agent-user --force
```

Install it into a custom skill directory:

```bash
.venv/bin/python scripts/install_skill.py --dest /path/to/skills/arxiv-bilingual-pdf-translate --force
```

For the current Codex runtime that still reads `CODEX_HOME`, use:

```bash
.venv/bin/python scripts/install_skill.py --target codex-home --force
```

The install command copies the skill files only. It does not install BabelDOC or
create the Python environment, so run setup first.

## Use

After setup and installation, ask your agent from this repository root:

```text
Use arxiv-bilingual-pdf-translate to translate arXiv 1812.10695 into a side-by-side Simplified Chinese bilingual PDF.
```

Other supported inputs:

```text
Use arxiv-bilingual-pdf-translate to translate https://arxiv.org/abs/1812.10695 into a side-by-side Simplified Chinese bilingual PDF.
```

```text
Use arxiv-bilingual-pdf-translate to translate ./paper.pdf into a side-by-side Simplified Chinese bilingual PDF.
```

The final PDF is written to:

```text
arxiv_outputs/<paper>.zh-CN.dual.pdf
```

Intermediate files are kept under `.arxiv_work/` and are normally only useful
for debugging failed runs.

## Glossary

Edit project terminology here:

```text
glossary/terms.csv
```

The CSV columns are:

```text
source,target,case_sensitive
```

You can also append a term with:

```bash
.venv/bin/python skills/arxiv-bilingual-pdf-translate/scripts/glossary.py add "attention mechanism" "注意力机制"
```

Validate the active glossary:

```bash
.venv/bin/python skills/arxiv-bilingual-pdf-translate/scripts/glossary.py validate
```

## Troubleshooting

If the agent cannot run the skill, run:

```bash
.venv/bin/python skills/arxiv-bilingual-pdf-translate/scripts/arxiv_translate.py preflight
```

If BabelDOC import or asset loading fails, rerun setup:

```bash
python3 skills/arxiv-bilingual-pdf-translate/scripts/bootstrap.py
```

If rendering fails for a specific PDF, ask the agent to retry with enhanced
compatibility or rich-text translation disabled. The skill contains the retry
rules for those cases.

## License And Attribution

This project is released under the GNU General Public License v3.0. See
[LICENSE](LICENSE).

Open-source attribution:

- BabelDOC: PDF parsing, layout preservation, and rendering. Repository:
  <https://github.com/funstory-ai/BabelDOC>.
- GPT Academic: workflow inspiration. Repository:
  <https://github.com/binary-husky/gpt_academic>.
- kaixindelele/chinarxiv: original project inspiration. Repository:
  <https://github.com/kaixindelele/chinarxiv>.

See [NOTICE](NOTICE) for details.
