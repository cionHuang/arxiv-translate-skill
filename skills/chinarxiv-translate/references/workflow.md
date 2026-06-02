# Workflow

Use this skill for arXiv papers with LaTeX source. Do not use it for scanned PDFs
or arbitrary PDF-only translation.

## Roles

- Main agent: owns glossary, translation style, segment assignment, consistency review, and final acceptance.
- Pipeline subagent: runs deterministic scripts for download, parsing, splitting, merging, and required PDF compilation.
- Translation subagents: translate assigned segments only. They must not change segment order, invent final terminology, or merge content.

## Default flow

1. Run `scripts/prepare_arxiv_translation.py <arxiv-id-or-url>`.
2. Read the generated `translation_package.json`, `glossary.json`, and segment files.
3. Main agent finalizes a locked glossary and style guide.
4. Assign segment files to translation subagents in batches.
5. Collect translations into a JSON file that follows `references/translation-contract.md`.
6. Run `scripts/merge_agent_translations.py <package> <translations>`.
7. Review `article_summary.md`, `qa_warnings.json`, and `translation_log.log`. The main agent must resolve hard format issues and decide whether QA warnings are acceptable.
8. Treat both `.tex` and PDF generation as required. Do not accept a normal translation run without a generated PDF.

## Quality policy

The main agent owns final translation quality. Enforce these rules before accepting
the merge:

- Formulas, variables, references, labels, numbering, dataset names, algorithm
  names, and English acronyms must be preserved.
- Abstract, Keywords, Introduction, Conclusion, Figure, Table, Section, Equation,
  captions, and table headers must be Chinese when rendered as visible text.
- First use of a technical term with acronym should use `中文全称（English Acronym）`;
  later uses must be consistent with the locked glossary.
- Author names, bibliography titles, journal names, and conference names should
  remain in their original language.
- Prefer standard mathematics, statistics, machine-learning, and domain-specific
  Chinese terminology.
- Use Chinese punctuation in Chinese sentences and put a space between Chinese
  text and English acronyms.
- The translation should read like a Chinese scientific paper, not translationese.
- Figure text embedded in images and unresolved layout problems must be surfaced
  as QA warnings.

## PDF policy

PDF generation is required for normal skill completion. If PDF compilation fails,
return the translated `.tex` path, `qa_warnings.json`, and `translation_log.log`,
but mark the translation run as failed until PDF generation is fixed.

The merge script compiles PDF by default. The default `--pdf-mode bilingual`
builds a landscape PDF
with the original English PDF on the left and the Chinese translated PDF on the
right. This is page-level side-by-side output. Use `--pdf-mode translated` when
only the Chinese PDF is needed.

Bilingual PDF mode needs:

- `xelatex` for compiling the translated document and wrapper PDF.
- `pdfinfo` from `poppler-utils` for page counts.
- Access to the original English PDF. By default the script downloads it from
  arXiv; pass `--original-pdf <path>` to use an existing local original PDF.

`--no-compile-pdf` and `--allow-pdf-failure` are development diagnostics only.
Do not use them for normal translation delivery.

## Output hygiene

After a normal merge, the output directory is cleaned by default. Keep only:

- translated `.tex`
- final `.pdf`
- `article_summary.md`
- `qa_warnings.json`
- `translation_log.log`

Use `--keep-intermediates` only for development diagnostics.
