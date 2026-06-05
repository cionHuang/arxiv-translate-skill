# Translation Contract

Subagents translate BabelDOC units, not full papers. They must return JSONL only.

## Input Unit

Each input line is a JSON object. Batches are compact by default, so `source_text`
may be omitted when the batch includes enough structured fields for translation.

```json
{
  "unit_id": "u_...",
  "source_hash": "sha256...",
  "source_text": "BabelDOC translation request; often a complete LLM prompt",
  "translation_input": "The extracted paragraph text to translate, when available",
  "placeholder_tokens": ["{v0}", "{v1}"],
  "output_mode": "json_array",
  "content_role": "reference",
  "do_not_translate": true,
  "glossary_terms": [
    {"source": "attention mechanism", "target": "注意力机制", "case_sensitive": false}
  ],
  "translation_items": [
    {"id": 0, "input": "text to translate", "layout_label": "text"}
  ],
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

- When `output_mode` is `json_array`, put a compact JSON array string in `translated_text`. Keep the same `id` values and output only `id` plus translated `output`.
- When `output_mode` is `plain_text`, put the translated text string in `translated_text`.
- If `source_text` is present, treat it as the authoritative request. If it is a full prompt asking for JSON, follow that prompt and put the prompt's required response in `translated_text`.
- Use `translation_input` as the human-readable text that needs translation.
- Use `translation_items` when present; it preserves BabelDOC paragraph IDs that must appear in JSON-array outputs.
- If `content_role` is `reference` or `do_not_translate` is true, copy the input text unchanged in the required output format.
- Follow `glossary_terms` exactly when those source terms appear in the unit. A target identical to the source means keep the term unchanged.
- Preserve every placeholder token exactly, including spelling, braces, brackets, case, and order.
- Preserve BabelDOC rich-text tags such as `<b1>` and `</b1>` exactly. Do not rename, reorder, remove, duplicate, or convert them.
- Preserve citation markers, equation references, footnote markers, and inline formula placeholders.
- Translate prose into Simplified Chinese.
- Keep symbols, variable names, model names, dataset names, method names, theorem numbers, and equation numbers unchanged unless the glossary says otherwise.
- Do not invent missing content.
- Do not merge or split JSONL records.
- If a unit is already Chinese or is only a formula/reference placeholder, copy it unchanged.
- Do not translate the References/Bibliography section or individual bibliography entries.

## Validation

The parent agent will reject results when:

- `unit_id` is missing or duplicated.
- `source_hash` does not match the input unit.
- `translated_text` is empty.
- Any placeholder token from the input is absent in the translation.
- Reference/bibliography content appears to have been translated into Chinese.
- The output is not valid JSONL.
