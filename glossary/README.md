# Glossary

[English](README.md) | [简体中文](README.zh-CN.md)

Edit `terms.csv` to control project-wide terminology for PDF translation.
The skill reads this file from the project root on each run, so you do not need
to copy glossary files into the Codex skill directory.

## Format

The glossary has only three columns:

```csv
source,target,case_sensitive
attention mechanism,注意力机制,false
ResNet,ResNet,true
```

- `source`: source term or phrase to match in the paper.
- `target`: required Simplified Chinese translation, or the unchanged English
  form when the term should not be translated.
- `case_sensitive`: use `true` only for terms where casing matters; otherwise use
  `false`.

You can also keep paper-specific files under `glossary/papers/`. A file named
after the run, for example `glossary/papers/1812.10695.csv`, is merged
automatically when present.

## Commands

Validate the active glossary:

```bash
.venv/bin/python skills/arxiv-bilingual-pdf-translate/scripts/glossary.py validate
```

List active terms:

```bash
.venv/bin/python skills/arxiv-bilingual-pdf-translate/scripts/glossary.py list
```

Append a term:

```bash
.venv/bin/python skills/arxiv-bilingual-pdf-translate/scripts/glossary.py add "attention mechanism" "注意力机制"
```
