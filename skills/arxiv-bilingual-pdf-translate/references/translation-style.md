# Academic Translation Style

Use polished Simplified Chinese suitable for reading a technical paper.

## Defaults

- Translate meaning, not word order.
- Keep sentences concise and natural.
- Prefer established technical terms from the glossary.
- Keep section titles short and noun-like when possible.
- Keep paper-specific named methods, benchmarks, datasets, and systems in English unless the glossary gives a Chinese form.

## Terminology

- Follow user terms first.
- Then follow `glossary_terms` attached to the current JSONL unit.
- Then follow the batch glossary file, when provided.
- If no term is given, choose one Chinese translation and use it consistently within the batch.
- Keep abbreviations such as LLM, CNN, MSE, GPU, API, and PDF unchanged unless the source defines a Chinese expansion.

## Math, Code, And References

- Do not translate formula symbols, code identifiers, filenames, URLs, command names, package names, or BibTeX keys.
- Do not translate the References/Bibliography section, reference entries, paper titles inside reference entries, venues, publisher information, DOI/arXiv identifiers, or URLs. Copy bibliography content unchanged unless the user explicitly requests translated references.
- Preserve references such as "Fig. 2", "Table 1", "Eq. (3)", "Section 4" in a Chinese sentence, for example "图 2", "表 1", "式 (3)", "第 4 节" when no placeholder prevents it.
- Do not reorder formula placeholders.

## Tone

- Use formal academic prose.
- Avoid marketing language.
- Avoid adding interpretation or commentary.
