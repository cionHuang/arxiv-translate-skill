# Local Testing

## Validate the skill

```bash
VALIDATOR="${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py"
if [ -f "$VALIDATOR" ]; then
  python3 "$VALIDATOR" skills/chinarxiv-translate
else
  echo "quick_validate.py not found; skip this optional check and run smoke_test.py instead."
fi
```

## Prepare a short paper

For a no-network smoke test of the `.tex` merge path. The smoke-test console
output redacts local paths with placeholders such as `<SMOKE_TEST_WORK_DIR>`:

```bash
python3 skills/chinarxiv-translate/scripts/smoke_test.py
```

To validate local PDF compilation as well:

```bash
python3 skills/chinarxiv-translate/scripts/smoke_test.py --compile-pdf
```

The PDF smoke test builds a Chinese-only PDF and does not download the original
English PDF. It fails when the local TeX environment lacks `xelatex`, `xeCJK`,
or Chinese font support.

```bash
python3 skills/chinarxiv-translate/scripts/prepare_arxiv_translation.py 1812.10695
```

The command prints the `translation_package.json` path. Translate the generated
segment files with local Codex/subagents and save a completed translations JSON.

## Merge translations

```bash
python3 skills/chinarxiv-translate/scripts/merge_agent_translations.py \
  chinarxiv_work/1812.10695/translation_package.json \
  chinarxiv_work/1812.10695/translations.completed.json
```

Open `qa_warnings.json` and `translation_log.log` after every merge.
`qa_warnings.json` contains translation-quality review items such as missing
glossary terms, untranslated captions/table headers, acronym spacing, or figure
text embedded in images. `translation_log.log` contains format-preservation
warnings, PDF compile logs, and final artifact information.

## Required PDF compile

Default output is a bilingual side-by-side PDF: original English pages on the
left, Chinese translated pages on the right. The merge script compiles this PDF
by default and returns failure if PDF generation fails.

```bash
python3 skills/chinarxiv-translate/scripts/merge_agent_translations.py \
  chinarxiv_work/1812.10695/translation_package.json \
  chinarxiv_work/1812.10695/translations.completed.json
```

If the original arXiv PDF has already been downloaded, avoid network access with:

```bash
python3 skills/chinarxiv-translate/scripts/merge_agent_translations.py \
  chinarxiv_work/1812.10695/translation_package.json \
  chinarxiv_work/1812.10695/translations.completed.json \
  --original-pdf chinarxiv_work/1812.10695/arxiv_1812.10695_original.pdf
```

For a Chinese-only PDF:

```bash
python3 skills/chinarxiv-translate/scripts/merge_agent_translations.py \
  chinarxiv_work/1812.10695/translation_package.json \
  chinarxiv_work/1812.10695/translations.completed.json \
  --pdf-mode translated
```

By default, the merge output directory is cleaned and only the translated `.tex`,
final `.pdf`, `qa_warnings.json`, and `translation_log.log` are kept. Use
`--keep-intermediates`, `--no-compile-pdf`, and `--allow-pdf-failure` only for
development diagnostics.
