# Translation Contract

Subagents translate BabelDOC units, not full papers. They must return JSONL only.

## Input Unit

Each input line is a JSON object:

```json
{
  "unit_id": "u_...",
  "source_hash": "sha256...",
  "source_text": "BabelDOC translation request; often a complete LLM prompt",
  "translation_input": "The extracted paragraph text to translate, when available",
  "placeholder_tokens": ["{v0}", "{v1}"],
  "context": {}
}
```

## Output Unit

Each output line must be:

```json
{
  "unit_id": "u_...",
  "source_hash": "same hash from input",
  "translated_text": "中文译文，完整保留占位符",
  "notes": ""
}
```

No Markdown fences, no explanation, no surrounding JSON array.

## Hard Requirements

- Treat `source_text` as the authoritative request. If it is a full prompt asking for JSON, follow that prompt and put the prompt's required response in `translated_text`.
- Use `translation_input` as the human-readable text that needs translation.
- Preserve every placeholder token exactly, including spelling, braces, brackets, case, and order.
- Preserve citation markers, equation references, footnote markers, and inline formula placeholders.
- Translate prose into Simplified Chinese.
- Keep symbols, variable names, model names, dataset names, method names, theorem numbers, and equation numbers unchanged unless the glossary says otherwise.
- Do not invent missing content.
- Do not merge or split JSONL records.
- If a unit is already Chinese or is only a formula/reference placeholder, copy it unchanged.

## Validation

The parent agent will reject results when:

- `unit_id` is missing or duplicated.
- `source_hash` does not match the input unit.
- `translated_text` is empty.
- Any placeholder token from the input is absent in the translation.
- The output is not valid JSONL.
