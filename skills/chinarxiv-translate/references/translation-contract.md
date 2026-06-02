# Translation Contract

Every translation worker receives one or more segment files and returns JSON.

## Input to each worker

- `segment_id`
- `source_hash`
- path or content of the source segment
- locked glossary from the main agent
- translation style guide from the main agent
- nearby section title or summary when available

## Worker output

Return a JSON object or list item:

```json
{
  "segment_id": "seg-0001",
  "source_hash": "sha256-from-package",
  "translated_latex": "translated LaTeX fragment",
  "notes": "optional uncertainty notes",
  "term_candidates": {
    "new source term": "suggested Chinese translation"
  }
}
```

The final translations file may be either:

```json
{
  "schema_version": 1,
  "translations": []
}
```

or a raw JSON array of translation objects.

## Hard rules

- Preserve LaTeX commands, environments, labels, citations, references, equations, variables, numbering, and table syntax.
- Treat figures, tables, algorithms, display math, TikZ/PGF drawings, and code/listing environments as indivisible anchor blocks. Preserve them exactly unless the main agent explicitly assigns a block-level edit.
- Preserve dataset names, benchmark names, algorithm names, model names, and English acronyms unless the locked glossary says otherwise.
- Translate prose and section titles into Simplified Chinese.
- Translate structural labels and structural text such as Abstract, Keywords, Introduction, Conclusion, Figure, Table, Section, and Equation when they appear as prose or headings.
- Translate figure captions, table captions, and table headers into Chinese.
- On first use of a professional term with a known acronym, use `中文全称（English Acronym）`; on later uses, keep the same short form chosen by the main agent.
- Do not translate author names, bibliography titles, journal names, conference names, publisher names, or citation keys.
- Prefer standard Chinese terminology used in mathematics, statistics, machine learning, and the paper's domain.
- Use Chinese punctuation in Chinese sentences. Put a space between Chinese text and English acronyms or dataset/model names.
- Avoid translationese. The result should read like a Chinese scientific paper, not a literal English-to-Chinese draft.
- Do not translate command names or citation keys.
- Do not reorder, split, merge, or omit segments.
- Use the locked glossary exactly. New terms are candidates only until the main agent accepts them.
- Mark uncertainty in `notes`; do not silently guess when a term is ambiguous.

## QA obligations

Before returning a segment, check for:

- Missing formulas, variables, citations, labels, references, or numbering.
- Untranslated English prose outside author metadata, references, acronyms, dataset names, and algorithm names.
- Inconsistent glossary terms or acronym expansions.
- Figure/table captions or table headers left in English.
- Chinese punctuation and spacing around English acronyms.
- Figure text embedded inside images or layout issues that cannot be fixed in LaTeX; record these in `notes` so the final merge report can surface QA warnings.
