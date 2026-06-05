# BabelDOC Bridge

This skill treats BabelDOC as the PDF parsing, layout, and rendering engine. The bridge replaces only the translation engine.

## Modes

`extract` mode:

- Installs a custom translator object into BabelDOC.
- Records every translation request into `translation_units.jsonl`.
- Returns the original text to BabelDOC so extraction can finish without an LLM API.

`render` mode:

- Loads `translations.completed.jsonl`.
- Installs the same custom translator object.
- Looks up each incoming source text by SHA-256 hash and returns the prepared Chinese translation.
- BabelDOC writes the final side-by-side `.dual.pdf`.
- Disables BabelDOC's upstream watermark by default with `watermark_output_mode=no_watermark`.
- Adds this project's own notice to rendered PDFs with PyMuPDF when `--no-custom-notice` is not set.

## Dependency Requirement

The command that runs `scripts/babeldoc_agent_bridge.py` must execute in an environment where BabelDOC is importable as a Python package with its internal translator API.

Use the project-local `.venv` from the repository root:

```bash
.venv/bin/python <skill_dir>/scripts/babeldoc_agent_bridge.py ...
```

Do not use `uv tool run --from BabelDOC` as the default bridge command. It creates a separate tool environment and can repeatedly request PyPI access when the agent sandbox points uv caches at temporary directories.

The bridge environment must pass:

```bash
.venv/bin/python -c "import babeldoc.translator.translator"
```

## Why Not CLI Only

The CLI currently expects an OpenAI-compatible translation provider. This skill needs a translator that reads Codex-produced JSON, so it uses BabelDOC internals through a local adapter rather than an API key.

## Notice And Watermark Policy

The bridge does not keep BabelDOC's default translated-by-BabelDOC watermark,
because the text translation is produced by the user's agent workflow. The
default render behavior is:

- pass `watermark_output_mode=no_watermark` to BabelDOC when the installed
  version supports it;
- add a small project notice to the rendered PDF;
- allow `--custom-notice "..."` for project-specific wording;
- allow `--no-custom-notice` only when the user explicitly wants no notice.

The default notice says that PDF layout parsing/rendering uses BabelDOC, while
translation text is produced by the user's agent workflow and should be
verified.

## Compatibility Flags

Use these only when rendering fails or the produced PDF is not readable:

- `--disable-rich-text-translate`
- `--enhance-compatibility`
- `--skip-clean`

Keep `--use-alternating-pages-dual` disabled. The required output is side-by-side bilingual PDF.
