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

## Dependency Requirement

The command that runs `scripts/babeldoc_agent_bridge.py` must execute in an environment where BabelDOC is importable as a Python package with its internal translator API.

If BabelDOC was installed with uv tool, use:

```bash
uv tool run --from BabelDOC python <skill_dir>/scripts/babeldoc_agent_bridge.py ...
```

If BabelDOC was installed from source or in a virtual environment, run the bridge with that environment's Python. Do not use system Python; the bridge environment must pass `python -c "import babeldoc.translator.translator"`.

## Why Not CLI Only

The CLI currently expects an OpenAI-compatible translation provider. This skill needs a translator that reads Codex-produced JSON, so it uses BabelDOC internals through a local adapter rather than an API key.

## Compatibility Flags

Use these only when rendering fails or the produced PDF is not readable:

- `--disable-rich-text-translate`
- `--enhance-compatibility`
- `--skip-clean`

Keep `--use-alternating-pages-dual` disabled. The required output is side-by-side bilingual PDF.
