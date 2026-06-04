# Workflow

Use this skill for arXiv papers with LaTeX source. Do not use it for scanned PDFs
or arbitrary PDF-only translation.

## Roles

- Main agent: owns glossary, translation style, segment assignment, consistency review, and final acceptance.
- Pipeline subagent: runs deterministic scripts for download, parsing, splitting, merging, and required PDF compilation.
- Translation subagents: translate assigned segments only. They must not change segment order, invent final terminology, or merge content.

## Default flow

1. Run `scripts/prepare_arxiv_translation.py <arxiv-id-or-url>` to download the arXiv source and original PDF, then create the translation package.
2. Read the generated `translation_package.json`, `glossary.json`, and segment files.
3. Main agent finalizes a locked glossary and style guide.
4. Assign segment files to translation subagents in batches.
5. Collect translations into a JSON file that follows `references/translation-contract.md`.
6. Run `scripts/merge_agent_translations.py <package> <translations>`.
7. Review root-level `article_summary.md`, plus `build/qa_warnings.json` and `build/translation_log.log`. The main agent must resolve hard format issues and decide whether QA warnings are acceptable.
8. Treat both `.tex` and PDF generation as required. Do not accept a normal translation run without a generated PDF.

## Quality policy

The main agent owns final translation quality. Enforce these rules before accepting
the merge:

- Formulas, variables, references, labels, numbering, dataset names, algorithm
  names, and English acronyms must be preserved.
- Figures, tables, algorithms, display math, TikZ/PGF drawings, and code/listing
  environments are indivisible anchor blocks. Do not split, reorder, change
  placement options, change sizing commands, or alter table structure. Caption
  and table text may be translated in place, but captions must remain a single
  LaTeX command argument with no blank lines or paragraph breaks.
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
return the translated `.tex` path under `build/`, `build/qa_warnings.json`, and `build/translation_log.log`,
but mark the translation run as failed until PDF generation is fixed.

The merge script compiles PDF by default. The default `--pdf-mode bilingual`
first compiles the translated Chinese PDF, then checks original and translated
page counts. If the counts match, it builds a landscape side-by-side PDF with
the original English PDF on the left and the Chinese translated PDF on the
right. If the counts differ, it keeps the Chinese-only PDF as the final PDF and
records the mismatch in `build/merge_report.json`, because page-level pairing
would misalign text and figures. Use `--pdf-mode translated` when only the
Chinese PDF is needed.

Bilingual PDF mode needs:

- `xelatex` for compiling the translated document and wrapper PDF.
- `pdfinfo` from `poppler-utils` for page counts.
- Access to the original English PDF. The prepare script downloads it by default
  and stores `original_pdf_path` in the package; pass `--original-pdf <path>` to
  override that local PDF.

`--allow-misaligned-bilingual` forces the old page-level side-by-side wrapper
when page counts differ. Treat it as a comparison/debugging output, not a
strictly aligned bilingual reading PDF.

`--no-compile-pdf` and `--allow-pdf-failure` are development diagnostics only.
Do not use them for normal translation delivery.

## Layout Policy

The default merge behavior is `--layout-mode preserve`. It keeps the original
paper's figure/table placement options, image sizing, table syntax, and float
structure. In preserve mode the merge step only applies minimal compile-safety
patches such as Chinese font support, optional decorative font-package guards,
and caption paragraph cleanup.

Use `--layout-mode repair` only when preserve mode compiles badly or produces
obvious clipping. Repair mode applies a flow-safe layout pass before PDF
compilation:

- insert `FloatBarrier` before section and subsection boundaries when available;
- load `flafter` when available to prevent floats from appearing before their source location;
- normalize figure/table/algorithm placements to `[!htbp]`;
- cap `includegraphics` height and preserve aspect ratio;
- wrap tabular-like blocks with `adjustbox` when available;
- shrink algorithm blocks with `\small` to reduce clipping risk.

## Output hygiene

After a normal merge, the paper root is cleaned by default. Keep only:

- final `.pdf`
- `article_summary.md`

Keep editable and diagnostic files under `build/`:

- translated `.tex`
- `qa_warnings.json`
- `translation_log.log`
- `merge_report.json`
- `package/` with the translation package, original PDF, segments, glossary, structure info, and translations JSON
- PDF compile files needed for debugging or recompilation

Use `--keep-intermediates` only for development diagnostics.
