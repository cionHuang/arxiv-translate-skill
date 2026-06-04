#!/usr/bin/env python3
"""Merge local agent translations back into a translated LaTeX document."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import requests


SCRIPT_DIR = Path(__file__).resolve().parent
CORE_DIR = SCRIPT_DIR / "arxiv_translate_core"
sys.path.insert(0, str(CORE_DIR))

from step5_result_merger import LaTeXResultMerger  # noqa: E402
from agent_translation_backend import validate_translation_contract  # noqa: E402


PROTECTED_PATTERNS = [
    re.compile(r"\\(?:label|ref|eqref|autoref|cref|Cref)\s*\{[^{}]+\}"),
    re.compile(r"\\cite[a-zA-Z*]*\s*(?:\[[^\]]*\]){0,2}\s*\{[^{}]+\}"),
    re.compile(r"\\(?:begin|end)\s*\{[^{}]+\}"),
    re.compile(r"\\begin\{((?:equation|align|alignat|gather|multline|eqnarray|split)\*?)\}[\s\S]*?\\end\{\1\}"),
    re.compile(r"\\\[[\s\S]*?\\\]"),
    re.compile(r"\\\([\s\S]*?\\\)"),
    re.compile(r"(?<!\\)\$\$(?:\\.|[^$])*?(?<!\\)\$\$"),
    re.compile(r"(?<!\\)\$(?!\$)(?:\\.|[^$\n])*?(?<!\\)\$(?!\$)"),
]

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
ACRONYM_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,}(?:[-/][A-Z0-9]+)*\b")
DATASET_OR_ALGORITHM_RE = re.compile(
    r"\b(?:[A-Z][a-z]+[A-Za-z0-9]*[A-Z][A-Za-z0-9]*|[A-Z]{2,}\d{2,}|[A-Z]+-\d+)\b"
)
SECTION_TITLE_RE = re.compile(r"\\(?:section|subsection|subsubsection|paragraph)\*?\s*\{([^{}]+)\}")
CAPTION_RE = re.compile(r"\\caption(?:\[[^\]]*\])?\s*\{([^{}]*)\}")
TABULAR_RE = re.compile(r"\\begin\{tabular\}[\s\S]*?\\end\{tabular\}")
ENGLISH_PHRASE_RE = re.compile(r"\b[A-Za-z][A-Za-z-]*(?:\s+[A-Za-z][A-Za-z-]*){2,}\b")
CHINESE_LABELS_MARKER = "% arxiv-translate-skill Chinese structural labels"
LAYOUT_SAFETY_MARKER = "% arxiv-translate-skill layout safety"

STRUCTURAL_TITLE_TERMS = {
    "abstract",
    "keywords",
    "introduction",
    "background",
    "related work",
    "method",
    "methods",
    "methodology",
    "approach",
    "experiment",
    "experiments",
    "experimental results",
    "results",
    "discussion",
    "conclusion",
    "conclusions",
    "appendix",
}

SECTION_TITLE_TRANSLATIONS = {
    "abstract": "摘要",
    "keywords": "关键词",
    "introduction": "引言",
    "background": "背景",
    "related work": "相关工作",
    "method": "方法",
    "methods": "方法",
    "methodology": "方法",
    "approach": "方法",
    "experiment": "实验",
    "experiments": "实验",
    "experimental results": "实验结果",
    "results": "结果",
    "discussion": "讨论",
    "conclusion": "结论",
    "conclusions": "结论",
    "appendix": "附录",
    "acknowledgement": "致谢",
    "acknowledgements": "致谢",
    "acknowledgment": "致谢",
    "acknowledgments": "致谢",
    "funding": "经费资助",
    "availability of data and material": "数据和材料可用性",
    "availability of data and materials": "数据和材料可用性",
    "author s contributions": "作者贡献",
    "authors contributions": "作者贡献",
    "author contributions": "作者贡献",
    "authors information": "作者信息",
    "competing interests": "利益冲突",
}

DOCHEAD_TRANSLATIONS = {
    "research": "研究论文",
    "review": "综述",
    "case study": "案例研究",
    "methodology": "方法",
}

STRUCTURAL_REF_REPLACEMENTS = [
    (re.compile(r"\bSections?~(\\(?:ref|autoref|cref|Cref)\s*\{[^{}]+\})"), r"第~\1 节"),
    (re.compile(r"\bTables?~(\\(?:ref|autoref|cref|Cref)\s*\{[^{}]+\})"), r"表~\1"),
    (re.compile(r"\b(?:Fig\.|Figure|Figures)~(\\(?:ref|autoref|cref|Cref)\s*\{[^{}]+\})"), r"图~\1"),
    (re.compile(r"\b(?:Eq\.|Equation|Equations)~(\\(?:ref|eqref|autoref|cref|Cref)\s*\{[^{}]+\})"), r"式~\1"),
]

OPTIONAL_FONT_PACKAGES = {
    "XCharter",
}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def normalize_translations(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("translations"), list):
        return payload["translations"]
    raise ValueError("Translations file must be a list or an object with a translations list.")


def load_glossary(package: dict[str, Any]) -> dict[str, str]:
    glossary_path = package.get("glossary_path")
    if not glossary_path:
        return {}
    path = Path(glossary_path)
    if not path.exists():
        return {}
    payload = load_json(path)
    if not isinstance(payload, dict):
        return {}
    return {str(source): str(target) for source, target in payload.items() if str(source).strip()}


def collect_protected_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for pattern in PROTECTED_PATTERNS:
        tokens.extend(match.group(0) for match in pattern.finditer(text))
    return sorted(set(tokens))


def check_protected_tokens(source: str, translated: str, segment_id: str) -> list[str]:
    warnings: list[str] = []
    for token in collect_protected_tokens(source):
        if token not in translated:
            warnings.append(f"{segment_id}: missing protected token {token}")
    return warnings


def has_cjk(text: str) -> bool:
    return CJK_RE.search(text) is not None


def term_occurs(term: str, text: str) -> bool:
    if not term:
        return False
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._\-/']*", term):
        pattern = rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])"
        return re.search(pattern, text, re.IGNORECASE) is not None
    return term in text


def strip_latex_for_qa(text: str) -> str:
    stripped = text
    for pattern in PROTECTED_PATTERNS:
        stripped = pattern.sub(" ", stripped)
    stripped = re.sub(r"%.*", " ", stripped)
    stripped = re.sub(r"\\[a-zA-Z@]+\*?(?:\s*\[[^\]]*\])?", " ", stripped)
    stripped = re.sub(r"[{}\\_^~&#]", " ", stripped)
    return stripped


def collect_preserved_english_tokens(source: str) -> list[str]:
    tokens = set(ACRONYM_RE.findall(source))
    tokens.update(DATASET_OR_ALGORITHM_RE.findall(source))
    return sorted(token for token in tokens if len(token) > 1)


def check_quality_rules(
    source: str,
    translated: str,
    segment_id: str,
    glossary: dict[str, str],
) -> list[str]:
    qa_warnings: list[str] = []

    for token in collect_preserved_english_tokens(source):
        if token not in translated:
            qa_warnings.append(f"{segment_id}: QA preserved acronym/name may be missing: {token}")

    for title in SECTION_TITLE_RE.findall(translated):
        normalized_title = normalize_title(title)
        if normalized_title in STRUCTURAL_TITLE_TERMS and not has_cjk(title):
            qa_warnings.append(f"{segment_id}: QA structural section title may still be English: {title}")
        elif title_may_be_untranslated(title):
            qa_warnings.append(f"{segment_id}: QA section title may still be English: {title}")

    source_caption_count = len(CAPTION_RE.findall(source))
    translated_captions = CAPTION_RE.findall(translated)
    if source_caption_count and len(translated_captions) < source_caption_count:
        qa_warnings.append(f"{segment_id}: QA caption count changed from {source_caption_count} to {len(translated_captions)}")
    for caption in translated_captions:
        if re.search(r"[A-Za-z]{3,}", caption) and not has_cjk(caption):
            qa_warnings.append(f"{segment_id}: QA caption may not be translated: {caption[:80]}")

    for table in TABULAR_RE.findall(translated):
        plain_table = strip_latex_for_qa(table)
        if re.search(r"[A-Za-z]{3,}", plain_table) and not has_cjk(plain_table):
            qa_warnings.append(f"{segment_id}: QA table content may still contain untranslated headers")
            break

    missing_glossary_terms: list[str] = []
    for source_term, target_term in glossary.items():
        if len(source_term) < 4 or not target_term or not has_cjk(target_term):
            continue
        if term_occurs(source_term, source) and target_term not in translated:
            missing_glossary_terms.append(f"{source_term}->{target_term}")
    if missing_glossary_terms:
        qa_warnings.append(
            f"{segment_id}: QA locked glossary terms may be missing: "
            + "; ".join(missing_glossary_terms[:8])
        )

    if r"\includegraphics" in source:
        qa_warnings.append(
            f"{segment_id}: QA figure image text/layout is not translated automatically; inspect rendered PDF"
        )

    if not re.search(r"\\(?:bibitem|author|address|affiliation|orgname|email|fnm|snm|inits)\b|thebibliography", source):
        plain = strip_latex_for_qa(translated)
        match = ENGLISH_PHRASE_RE.search(plain)
        if match and has_cjk(translated):
            qa_warnings.append(f"{segment_id}: QA possible untranslated English phrase: {match.group(0)[:80]}")

    if re.search(r"[\u4e00-\u9fff][,.;:!?]|[,.;:!?][\u4e00-\u9fff]", translated):
        qa_warnings.append(f"{segment_id}: QA Chinese text may contain ASCII punctuation")

    if re.search(r"[\u4e00-\u9fff][A-Z]{2,}|[A-Z]{2,}[\u4e00-\u9fff]", translated):
        qa_warnings.append(f"{segment_id}: QA Chinese text and English acronym may need a separating space")

    return qa_warnings


def ensure_chinese_structural_labels(content: str) -> str:
    if CHINESE_LABELS_MARKER in content:
        return content

    label_support = rf"""
{CHINESE_LABELS_MARKER}
\makeatletter
\AtBeginDocument{{
  \providecommand{{\abstractname}}{{Abstract}}\renewcommand{{\abstractname}}{{摘要}}
  \providecommand{{\keywordsname}}{{Keywords}}\renewcommand{{\keywordsname}}{{关键词}}
  \providecommand{{\keywordname}}{{Keywords}}\renewcommand{{\keywordname}}{{关键词}}
  \expandafter\gdef\csname keyword@KWD\endcsname{{关键词}}
  \providecommand{{\figurename}}{{Figure}}\renewcommand{{\figurename}}{{图}}
  \providecommand{{\tablename}}{{Table}}\renewcommand{{\tablename}}{{表}}
  \providecommand{{\refname}}{{References}}\renewcommand{{\refname}}{{参考文献}}
  \providecommand{{\bibname}}{{Bibliography}}\renewcommand{{\bibname}}{{参考文献}}
  \providecommand{{\contentsname}}{{Contents}}\renewcommand{{\contentsname}}{{目录}}
  \providecommand{{\appendixname}}{{Appendix}}\renewcommand{{\appendixname}}{{附录}}
  \providecommand{{\algorithmname}}{{Algorithm}}\renewcommand{{\algorithmname}}{{算法}}
  \@ifpackageloaded{{algorithm2e}}{{
    \providecommand{{\algorithmcfname}}{{Algorithm}}\renewcommand{{\algorithmcfname}}{{算法}}
  }}{{
    \@ifundefined{{c@algorithm}}{{
      \@ifpackageloaded{{float}}{{
        \let\algorithm\relax
        \let\endalgorithm\relax
        \floatstyle{{ruled}}
        \newfloat{{algorithm}}{{tbp}}{{loa}}
      }}{{}}
    }}{{}}
    \@ifundefined{{floatname}}{{}}{{\floatname{{algorithm}}{{算法}}}}
  }}
}}
\makeatother
"""
    match = re.search(r"\\documentclass(?:\[[^\]]*\])?\{[^{}]+\}", content)
    if not match:
        return label_support + content
    insert_at = match.end()
    return content[:insert_at] + "\n" + label_support + content[insert_at:]


def ensure_layout_safety_support(content: str) -> str:
    if LAYOUT_SAFETY_MARKER in content:
        return content

    layout_support = rf"""
{LAYOUT_SAFETY_MARKER}
\IfFileExists{{placeins.sty}}{{\usepackage{{placeins}}}}{{\providecommand{{\FloatBarrier}}{{}}}}
\IfFileExists{{flafter.sty}}{{\usepackage{{flafter}}}}{{}}
\IfFileExists{{adjustbox.sty}}{{\usepackage{{adjustbox}}}}{{\newenvironment{{adjustbox}}[1]{{}}{{}}}}
\IfFileExists{{caption.sty}}{{\usepackage{{caption}}}}{{}}
\makeatletter
\AtBeginDocument{{
  \raggedbottom
  \setlength{{\textfloatsep}}{{8pt plus 2pt minus 2pt}}
  \setlength{{\floatsep}}{{8pt plus 2pt minus 2pt}}
  \setlength{{\intextsep}}{{8pt plus 2pt minus 2pt}}
  \@ifundefined{{FloatBarrier}}{{\providecommand{{\FloatBarrier}}{{}}}}{{}}
  \@ifundefined{{captionsetup}}{{}}{{
    \captionsetup{{font=small,labelfont=bf,skip=4pt}}
    \@ifpackageloaded{{subcaption}}{{\captionsetup[subfigure]{{font=footnotesize,skip=2pt}}}}{{}}
  }}
}}
\makeatother
"""
    match = re.search(r"\\documentclass(?:\[[^\]]*\])?\{[^{}]+\}", content)
    if not match:
        return layout_support + content
    insert_at = match.end()
    return content[:insert_at] + "\n" + layout_support + content[insert_at:]


def normalize_float_placements(content: str) -> str:
    def replace_begin(match: re.Match[str]) -> str:
        environment = match.group(1)
        return rf"\begin{{{environment}}}[!htbp]"

    return re.sub(
        r"\\begin\{(figure\*?|table\*?|algorithm\*?)\}(?:\s*\[[^\]]*\])?",
        replace_begin,
        content,
    )


def add_float_barriers(content: str) -> str:
    section_re = re.compile(r"(?m)^(\s*\\section\*?(?:\s*\[[^\]]*\])?\s*\{)")
    pieces: list[str] = []
    last = 0
    for match in section_re.finditer(content):
        prefix = content[max(0, match.start() - 80) : match.start()]
        pieces.append(content[last : match.start()])
        if "\\FloatBarrier" not in prefix:
            pieces.append("\\FloatBarrier\n")
        pieces.append(match.group(1))
        last = match.end()
    pieces.append(content[last:])
    return "".join(pieces)


def patch_includegraphics_limits(content: str) -> str:
    def merge_options(options: str) -> str:
        parts = [part.strip() for part in options.split(",") if part.strip()]
        keys = {part.split("=", 1)[0].strip() for part in parts}
        if "width" not in keys and "scale" not in keys:
            parts.append(r"width=\linewidth")
        if "height" not in keys:
            parts.append(r"height=0.72\textheight")
        if "keepaspectratio" not in keys:
            parts.append("keepaspectratio")
        return ",".join(parts)

    def replace_graphics(match: re.Match[str]) -> str:
        options = match.group(1)
        path = match.group(2)
        merged_options = merge_options(options or "")
        return rf"\includegraphics[{merged_options}]{{{path}}}"

    return re.sub(
        r"\\includegraphics(?:\s*\[([^\]]*)\])?\s*\{([^{}]+)\}",
        replace_graphics,
        content,
    )


def wrap_tabular_blocks(content: str) -> str:
    tabular_re = re.compile(
        r"\\begin\{(tabular|tabularx|tabulary|tblr)\}(?:\s*\[[^\]]*\])?[\s\S]*?\\end\{\1\}",
        re.DOTALL,
    )
    pieces: list[str] = []
    last = 0
    for match in tabular_re.finditer(content):
        prefix = content[max(0, match.start() - 120) : match.start()]
        block = match.group(0)
        pieces.append(content[last : match.start()])
        if r"\begin{adjustbox}" in prefix:
            pieces.append(block)
        else:
            pieces.append(
                "\\begin{adjustbox}{max width=\\textwidth,max totalheight=0.70\\textheight}\n"
                + block
                + "\n\\end{adjustbox}"
            )
        last = match.end()
    pieces.append(content[last:])
    return "".join(pieces)


def shrink_algorithm_blocks(content: str) -> str:
    algorithm_re = re.compile(r"(\\begin\{algorithm\*?\}(?:\s*\[[^\]]*\])?)([\s\S]*?\\end\{algorithm\*?\})")

    def replace_algorithm(match: re.Match[str]) -> str:
        begin = match.group(1)
        body = match.group(2)
        first_lines = body[:160]
        if re.search(r"\\(?:small|footnotesize|scriptsize)\b", first_lines):
            return match.group(0)
        algorithmic_start = body.find(r"\begin{algorithmic}")
        if algorithmic_start >= 0:
            return begin + body[:algorithmic_start] + "\n\\small\n" + body[algorithmic_start:]
        return begin + "\n\\small\n" + body

    return algorithm_re.sub(replace_algorithm, content)


def normalize_caption_paragraphs(content: str) -> str:
    caption_re = re.compile(r"\\caption(?:\s*\[[^\]]*\])?\s*\{")
    pieces: list[str] = []
    last = 0
    for match in caption_re.finditer(content):
        open_brace = match.end() - 1
        close_brace = find_matching_brace(content, open_brace)
        if close_brace is None:
            continue
        body = content[open_brace + 1 : close_brace]
        normalized = re.sub(r"\\par\b", " ", body)
        normalized = re.sub(r"[ \t]*\n[ \t]*", " ", normalized)
        normalized = re.sub(r"\s{2,}", " ", normalized).strip()
        pieces.append(content[last : open_brace + 1])
        pieces.append(normalized)
        pieces.append("}")
        last = close_brace + 1
    pieces.append(content[last:])
    return "".join(pieces)


def apply_layout_safety_patches(content: str) -> str:
    content = normalize_float_placements(content)
    content = add_float_barriers(content)
    content = patch_includegraphics_limits(content)
    content = wrap_tabular_blocks(content)
    content = shrink_algorithm_blocks(content)
    content = normalize_caption_paragraphs(content)
    return content

FLOAT_H_MARKER = "% arxiv-translate-skill float [H] anchoring"


def patch_float_placement_H(content: str) -> str:
    """Convert all figure/table float environments to [H] (HERE) placement.

    Adds \\usepackage{float} to the preamble and replaces every
    \\begin{figure}, \\begin{figure*}, \\begin{table}, \\begin{table*}
    placement option with [H]. Environments that already use [H] are
    left unchanged.
    """
    if FLOAT_H_MARKER in content:
        return content

    if r"\usepackage{float}" not in content:
        doc_match = re.search(
            r"\\documentclass(?:\[[^\]]*\])?\{[^{}]+\}", content
        )
        if doc_match:
            insert_at = doc_match.end()
            content = (
                content[:insert_at]
                + "\n\\IfFileExists{float.sty}{\\usepackage{float}}{}\n"
                + content[insert_at:]
            )

    # Replace placement options on float environments.
    # Order matters: first handle floats *with* an existing option, then
    # floats without any option, to avoid double-matching.
    for env in ("figure", "figure*", "table", "table*"):
        # Floats with an existing placement option  e.g. \\begin{figure}[!htbp]
        content = re.sub(
            r"\\begin{" + re.escape(env) + r"}\s*\[([^]]*)\]",
            r"\\begin{" + env + r"}[H]",
            content,
        )
        # Floats without a placement option  e.g. \\begin{figure}
        content = re.sub(
            r"\\begin{" + re.escape(env) + r"}(?!\s*\[)",
            r"\\begin{" + env + r"}[H]",
            content,
        )

    return content

def normalize_title(title: str) -> str:
    normalized = re.sub(r"[^A-Za-z ]+", " ", title).strip().lower()
    return re.sub(r"\s+", " ", normalized)


def title_may_be_untranslated(title: str) -> bool:
    if has_cjk(title):
        return False
    if not re.search(r"[A-Za-z]{3,}", title):
        return False
    compact = re.sub(r"[^A-Za-z0-9]+", "", title)
    return not (compact.isupper() and len(compact) <= 12)


def patch_visible_structural_terms(content: str) -> str:
    def replace_heading(match: re.Match[str]) -> str:
        command = match.group(1)
        title = match.group(2)
        translated = SECTION_TITLE_TRANSLATIONS.get(normalize_title(title))
        if translated:
            return f"{command}{{{translated}}}"
        return match.group(0)

    content = re.sub(
        r"(\\(?:section|subsection|subsubsection|paragraph)\*?\s*)\{([^{}]+)\}",
        replace_heading,
        content,
    )

    def replace_dochead(match: re.Match[str]) -> str:
        title = match.group(2)
        translated = DOCHEAD_TRANSLATIONS.get(normalize_title(title))
        if translated:
            return f"{match.group(1)}{{{translated}}}"
        return match.group(0)

    content = re.sub(r"(\\dochead\s*)\{([^{}]+)\}", replace_dochead, content)
    for pattern, replacement in STRUCTURAL_REF_REPLACEMENTS:
        content = pattern.sub(replacement, content)
    content = re.sub(r"([\u4e00-\u9fff])\s+(图|表|式)~", r"\1\2~", content)
    content = re.sub(r"([\u4e00-\u9fff])\s+(第~\\(?:ref|autoref|cref|Cref)\s*\{[^{}]+\} 节)", r"\1\2", content)
    content = re.sub(r"(第~\\(?:ref|autoref|cref|Cref)\s*\{[^{}]+\} 节)\s+([\u4e00-\u9fff])", r"\1\2", content)
    return content


def check_document_quality(content: str) -> list[str]:
    qa_warnings: list[str] = []
    for title in SECTION_TITLE_RE.findall(content):
        normalized_title = normalize_title(title)
        if normalized_title in SECTION_TITLE_TRANSLATIONS:
            continue
        if title_may_be_untranslated(title):
            qa_warnings.append(f"document: QA section title may still be English: {title}")

    structural_patterns = {
        "Section": re.compile(r"\bSections?~\\(?:ref|autoref|cref|Cref)\s*\{"),
        "Table": re.compile(r"\bTables?~\\(?:ref|autoref|cref|Cref)\s*\{"),
        "Figure": re.compile(r"\b(?:Fig\.|Figure|Figures)~\\(?:ref|autoref|cref|Cref)\s*\{"),
        "Equation": re.compile(r"\b(?:Eq\.|Equation|Equations)~\\(?:ref|eqref|autoref|cref|Cref)\s*\{"),
    }
    for label, pattern in structural_patterns.items():
        if pattern.search(content):
            qa_warnings.append(f"document: QA visible structural reference may still be English: {label}")

    return qa_warnings


def patch_latex_for_engine(content: str, engine: str, layout_mode: str = "preserve", float_placement: str = "preserve") -> str:
    """Patch translated LaTeX so Chinese text can render in the selected engine."""
    # A translated document may inherit source-only driver options. These are
    # usually wrong once we compile with XeLaTeX.
    if engine == "xelatex":
        content = re.sub(
            r"\\usepackage\s*\[\s*(?:pdftex|dvips|dvipdfm|dvipdfmx|xetex)\s*\]\s*\{graphicx\}",
            r"\\usepackage{graphicx}",
            content,
        )

    content = make_font_packages_optional(content)
    if layout_mode == "repair":
        content = ensure_layout_safety_support(content)
        content = apply_layout_safety_patches(content)
    else:
        content = normalize_caption_paragraphs(content)

    if float_placement == "H":
        content = patch_float_placement_H(content)

    if not has_cjk(content):
        return content

    content = ensure_chinese_structural_labels(content)

    if any(pkg in content for pkg in (r"\usepackage{ctex}", r"\usepackage[UTF8]{ctex}", r"\usepackage{xeCJK}")):
        return content

    if engine == "xelatex":
        cjk_support = r"""
\usepackage{xeCJK}
\IfFontExistsTF{Noto Serif CJK SC}{\setCJKmainfont{Noto Serif CJK SC}}{
  \IfFontExistsTF{Noto Sans CJK SC}{\setCJKmainfont{Noto Sans CJK SC}}{
    \IfFontExistsTF{WenQuanYi Micro Hei}{\setCJKmainfont{WenQuanYi Micro Hei}}{}
  }
}
\IfFontExistsTF{Noto Sans CJK SC}{\setCJKsansfont{Noto Sans CJK SC}}{}
"""
    else:
        cjk_support = "\n\\usepackage[UTF8]{ctex}\n"

    match = re.search(r"\\documentclass(?:\[[^\]]*\])?\{[^{}]+\}", content)
    if not match:
        return cjk_support + content

    insert_at = match.end()
    return content[:insert_at] + "\n" + cjk_support + content[insert_at:]


def make_font_packages_optional(content: str) -> str:
    """Allow known decorative font packages to be absent in minimal TeX installs."""

    def replace_package(match: re.Match[str]) -> str:
        command = match.group(1)
        options = match.group(2) or ""
        package_names = [name.strip() for name in match.group(3).split(",")]
        if len(package_names) != 1:
            return match.group(0)

        package_name = package_names[0]
        if package_name not in OPTIONAL_FONT_PACKAGES:
            return match.group(0)

        return rf"\IfFileExists{{{package_name}.sty}}{{{command}{options}{{{package_name}}}}}{{}}"

    return re.sub(
        r"(\\(?:usepackage|RequirePackage))(\s*\[[^\]]*\])?\s*\{([^{}]+)\}",
        replace_package,
        content,
    )


def patch_compile_tree_for_optional_packages(compile_dir: Path) -> None:
    for pattern in ("*.tex", "*.sty", "*.cls"):
        for path in compile_dir.glob(f"**/{pattern}"):
            try:
                original = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            patched = make_font_packages_optional(original)
            if patched != original:
                path.write_text(patched, encoding="utf-8")


def log_has_render_failure(log_text: str) -> str | None:
    if "Undefined control sequence" in log_text:
        return "LaTeX log contains Undefined control sequence"
    if "Runaway argument" in log_text:
        return "LaTeX log contains Runaway argument"
    if "Paragraph ended before" in log_text:
        return "LaTeX log contains paragraph-ended-before error"
    if "Extra }, or forgotten \\endgroup" in log_text:
        return "LaTeX log contains unbalanced group error"
    if re.search(r"^! LaTeX Error:", log_text, re.MULTILINE):
        return "LaTeX log contains LaTeX Error"
    if re.search(r"^! Package .* Error:", log_text, re.MULTILINE):
        return "LaTeX log contains package error"
    if re.search(r"Missing character: There is no [\u4e00-\u9fff]", log_text):
        return "LaTeX log contains missing CJK characters"
    if "Fatal error" in log_text or "Emergency stop" in log_text:
        return "LaTeX log contains fatal error"
    return None


def log_has_final_reference_failure(log_text: str) -> str | None:
    if "Package natbib Warning: There were undefined citations" in log_text:
        return "LaTeX final pass contains undefined citations"
    if re.search(r"Package natbib Warning: Citation `[^`]+'.*undefined", log_text):
        return "LaTeX final pass contains undefined citations"
    if "LaTeX Warning: There were undefined references" in log_text:
        return "LaTeX final pass contains undefined references"
    return None


def seed_bibliography_output(compile_dir: Path, compile_tex: Path) -> tuple[bool, list[str]]:
    """Reuse arXiv-provided .bbl files with the translated job name."""
    target_bbl = compile_dir / f"{compile_tex.stem}.bbl"
    if target_bbl.exists():
        return True, [f"Using existing bibliography file {target_bbl.name}"]

    bbl_files = sorted(path for path in compile_dir.glob("*.bbl") if path.name != target_bbl.name)
    if not bbl_files:
        return False, []

    source_bbl = bbl_files[0]
    shutil.copy2(source_bbl, target_bbl)
    return True, [f"Copied bibliography file {source_bbl.name} -> {target_bbl.name}"]


def run_bibliography_tool(compile_dir: Path, compile_tex: Path, seeded_bbl: bool) -> list[str]:
    logs: list[str] = []
    aux_path = compile_dir / f"{compile_tex.stem}.aux"
    if not aux_path.exists():
        return logs

    if seeded_bbl:
        logs.append("Skipped BibTeX/Biber because an arXiv-provided .bbl was reused.")
        return logs

    biber = shutil.which("biber")
    bcf_path = compile_dir / f"{compile_tex.stem}.bcf"
    if biber and bcf_path.exists():
        result = subprocess.run(
            [biber, compile_tex.stem],
            cwd=str(compile_dir),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=300,
            check=False,
        )
        logs.append(result.stdout)
        return logs

    bibtex = shutil.which("bibtex")
    if bibtex is None:
        return logs

    aux_text = aux_path.read_text(encoding="utf-8", errors="replace")
    if "\\bibdata" not in aux_text and not list(compile_dir.glob("*.bib")):
        return logs

    result = subprocess.run(
        [bibtex, compile_tex.stem],
        cwd=str(compile_dir),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=300,
        check=False,
    )
    logs.append(result.stdout)
    return logs


def try_compile_pdf(tex_path: Path, source_dir: Path | None, engine: str) -> tuple[bool, str]:
    executable = shutil.which(engine)
    if executable is None:
        return False, f"{engine} not found"

    compile_dir = tex_path.parent / "pdf_compile"
    if compile_dir.exists():
        shutil.rmtree(compile_dir)
    compile_dir.mkdir(parents=True)

    if source_dir and source_dir.exists():
        def ignore_compile_tree(directory: str, names: list[str]) -> set[str]:
            ignored = set()
            for name in names:
                child = Path(directory) / name
                if child.resolve() == compile_dir.resolve() or is_relative_to(compile_dir, child):
                    ignored.add(name)
            return ignored

        shutil.copytree(source_dir, compile_dir, dirs_exist_ok=True, ignore=ignore_compile_tree)

    compile_tex = compile_dir / tex_path.name
    compile_tex.write_text(tex_path.read_text(encoding="utf-8"), encoding="utf-8")
    patch_compile_tree_for_optional_packages(compile_dir)
    seeded_bbl, bibliography_setup_logs = seed_bibliography_output(compile_dir, compile_tex)

    command = [
        executable,
        "-interaction=nonstopmode",
        "-file-line-error",
        compile_tex.name,
    ]

    logs: list[str] = bibliography_setup_logs[:]

    result = subprocess.run(
        command,
        cwd=str(compile_dir),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=300,
        check=False,
    )
    logs.append(result.stdout)
    logs.extend(run_bibliography_tool(compile_dir, compile_tex, seeded_bbl))

    for _ in range(2):
        result = subprocess.run(
            command,
            cwd=str(compile_dir),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=300,
            check=False,
        )
        logs.append(result.stdout)

    pdf_path = compile_dir / f"{compile_tex.stem}.pdf"
    log_path = compile_dir / "compile.log"
    log_text = "\n\n".join(logs)
    log_path.write_text(log_text, encoding="utf-8")

    if pdf_path.exists():
        render_failure = log_has_render_failure(log_text)
        if render_failure:
            return False, f"{render_failure}; log: {log_path}"
        final_reference_failure = log_has_final_reference_failure(logs[-1] if logs else "")
        if final_reference_failure:
            return False, f"{final_reference_failure}; log: {log_path}"
        final_pdf = tex_path.with_suffix(".pdf")
        shutil.copy2(pdf_path, final_pdf)
        return True, str(final_pdf)

    return False, str(log_path)


def pdf_page_count(pdf_path: Path) -> int:
    executable = shutil.which("pdfinfo")
    if executable is None:
        raise RuntimeError("pdfinfo not found; install poppler-utils to build bilingual PDFs")
    result = subprocess.run(
        [executable, str(pdf_path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stdout.strip() or f"pdfinfo failed for {pdf_path}")
    match = re.search(r"^Pages:\s+(\d+)\s*$", result.stdout, re.MULTILINE)
    if not match:
        raise RuntimeError(f"Unable to read page count from {pdf_path}")
    return int(match.group(1))


def download_arxiv_pdf(arxiv_id: str, output_path: Path) -> Path:
    if not arxiv_id:
        raise RuntimeError("package has no arxiv_id; cannot download original PDF")
    url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    response = requests.get(
        url,
        headers={"User-Agent": "arxiv-translate-skill/1.0"},
        timeout=90,
    )
    response.raise_for_status()
    if not response.content.startswith(b"%PDF"):
        raise RuntimeError(f"downloaded arXiv response is not a PDF: {url}")
    output_path.write_bytes(response.content)
    return output_path


def resolve_original_pdf(package: dict[str, Any], original_pdf_arg: str, build_dir: Path) -> Path:
    if original_pdf_arg:
        original_pdf = Path(original_pdf_arg).resolve()
        if not original_pdf.exists():
            raise RuntimeError(f"original PDF not found: {original_pdf}")
        return original_pdf

    package_original_pdf = package.get("original_pdf_path")
    if package_original_pdf:
        original_pdf = Path(str(package_original_pdf)).resolve()
        if original_pdf.exists():
            return original_pdf

    arxiv_id = str(package.get("arxiv_id", ""))
    original_pdf = build_dir / (f"arxiv_{arxiv_id}_original.pdf" if arxiv_id else "original.pdf")
    if not original_pdf.exists():
        original_pdf = download_arxiv_pdf(arxiv_id, original_pdf)
    return original_pdf


def latex_path(path: Path) -> str:
    return str(path).replace("\\", "/")


def build_bilingual_side_by_side_pdf(
    original_pdf: Path,
    translated_pdf: Path,
    output_pdf: Path,
    work_dir: Path,
    engine: str,
) -> tuple[bool, str]:
    executable = shutil.which(engine)
    if executable is None:
        return False, f"{engine} not found"

    original_pages = pdf_page_count(original_pdf)
    translated_pages = pdf_page_count(translated_pdf)
    max_pages = max(original_pages, translated_pages)

    side_tex = work_dir / "bilingual_side_by_side.tex"
    original_name = "original.pdf"
    translated_name = "translated.pdf"
    shutil.copy2(original_pdf, work_dir / original_name)
    shutil.copy2(translated_pdf, work_dir / translated_name)

    page_blocks: list[str] = []
    for page in range(1, max_pages + 1):
        left = (
            rf"\includegraphics[page={page},width=\linewidth,height=0.93\textheight,keepaspectratio]{{{original_name}}}"
            if page <= original_pages
            else r"\centering\Large 原文无对应页"
        )
        right = (
            rf"\includegraphics[page={page},width=\linewidth,height=0.93\textheight,keepaspectratio]{{{translated_name}}}"
            if page <= translated_pages
            else r"\centering\Large 译文无对应页"
        )
        page_blocks.append(
            rf"""
\noindent
\begin{{minipage}}[t]{{0.49\linewidth}}
\centering\small English p.{page}/{original_pages}\par\vspace{{2mm}}
{left}
\end{{minipage}}\hfill
\begin{{minipage}}[t]{{0.49\linewidth}}
\centering\small 中文 p.{page}/{translated_pages}\par\vspace{{2mm}}
{right}
\end{{minipage}}
\newpage
"""
        )

    side_tex.write_text(
        r"""\documentclass[a4paper,landscape]{article}
\usepackage[margin=7mm]{geometry}
\usepackage{graphicx}
\usepackage{xeCJK}
\IfFontExistsTF{Noto Serif CJK SC}{\setCJKmainfont{Noto Serif CJK SC}}{
  \IfFontExistsTF{Noto Sans CJK SC}{\setCJKmainfont{Noto Sans CJK SC}}{
    \IfFontExistsTF{WenQuanYi Micro Hei}{\setCJKmainfont{WenQuanYi Micro Hei}}{}
  }
}
\pagestyle{empty}
\begin{document}
"""
        + "\n".join(page_blocks)
        + "\n\\end{document}\n",
        encoding="utf-8",
    )

    built_pdf = work_dir / "bilingual_side_by_side.pdf"
    for stale_pdf in (built_pdf, output_pdf):
        if stale_pdf.exists():
            stale_pdf.unlink()

    logs: list[str] = []
    for _ in range(2):
        result = subprocess.run(
            [
                executable,
                "-interaction=nonstopmode",
                "-file-line-error",
                side_tex.name,
            ],
            cwd=str(work_dir),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=300,
            check=False,
        )
        logs.append(result.stdout)

    log_text = "\n\n".join(logs)
    (work_dir / "bilingual_compile.log").write_text(log_text, encoding="utf-8")
    if built_pdf.exists():
        render_failure = log_has_render_failure(log_text)
        if render_failure:
            return False, f"{render_failure}; log: {work_dir / 'bilingual_compile.log'}"
        shutil.copy2(built_pdf, output_pdf)
        return True, str(output_pdf)

    return False, str(work_dir / "bilingual_compile.log")


def merge_with_structure(
    structure_info_path: Path,
    translated_segments: list[str],
    original_segments: list[str],
) -> str:
    structure_info = load_json(structure_info_path)
    if not isinstance(structure_info, list):
        raise ValueError("structure_info must be a list")

    parts: list[str] = []
    for item in structure_info:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "preserve":
            parts.append(str(item.get("content", "")))
            continue
        if item_type == "translate":
            index = int(item.get("index", -1))
            if 0 <= index < len(translated_segments) and translated_segments[index].strip():
                parts.append(translated_segments[index])
            elif 0 <= index < len(original_segments):
                parts.append(original_segments[index])
            continue
        parts.append(str(item.get("content", "")))

    return "".join(parts)


def read_text_if_exists(path: Path | None) -> str:
    if path is None or not path.exists() or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"[unable to read log {path.name}: {exc}]"


def redact_log_text(text: str, roots: list[Path]) -> str:
    redacted = text
    for root in roots:
        if root:
            redacted = redacted.replace(str(root.resolve()), f"<{root.name or 'ROOT'}>")
    home = str(Path.home())
    if home and home != "/":
        redacted = redacted.replace(home, "<HOME>")
    return redacted


def write_qa_warnings(path: Path, qa_warnings: list[str]) -> None:
    write_json(
        path,
        {
            "count": len(qa_warnings),
            "qa_warnings": qa_warnings,
        },
    )


def write_total_log(
    path: Path,
    *,
    success: bool,
    tex_path: Path | None,
    pdf_path: Path | None,
    summary_path: Path | None = None,
    pdf_mode: str | None,
    pdf_success: bool,
    pdf_result: str | None,
    translated_pdf_result: str | None,
    original_pdf_result: str | None,
    merge_message: str,
    warnings: list[str],
    qa_warnings: list[str],
    errors: list[str],
    segment_count: int,
    compile_dir: Path | None,
    redact_roots: list[Path],
    layout_mode: str | None = None,
) -> None:
    translated_compile_log = read_text_if_exists(compile_dir / "compile.log" if compile_dir else None)
    bilingual_compile_log = read_text_if_exists(compile_dir / "bilingual_compile.log" if compile_dir else None)
    lines = [
        "arxiv-translate-skill translation log",
        f"success: {success}",
        f"tex: {tex_path.name if tex_path else ''}",
        f"pdf: {pdf_path.name if pdf_path else ''}",
        f"summary: {summary_path.name if summary_path else ''}",
        f"pdf_mode: {pdf_mode or ''}",
        f"layout_mode: {layout_mode or ''}",
        f"pdf_success: {pdf_success}",
        f"pdf_result: {pdf_result or ''}",
        f"translated_pdf_result: {Path(translated_pdf_result).name if translated_pdf_result else ''}",
        f"original_pdf_result: {Path(original_pdf_result).name if original_pdf_result else ''}",
        f"merge_message: {merge_message}",
        f"segment_count: {segment_count}",
        "",
        "errors:",
        *(f"- {item}" for item in errors),
        "",
        "warnings:",
        *(f"- {item}" for item in warnings),
        "",
        "qa_warnings:",
        *(f"- {item}" for item in qa_warnings),
        "",
        "translated_pdf_compile_log:",
        translated_compile_log.strip(),
        "",
        "bilingual_pdf_compile_log:",
        bilingual_compile_log.strip(),
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(redact_log_text("\n".join(lines), redact_roots), encoding="utf-8")


def find_matching_brace(text: str, open_brace_index: int) -> int | None:
    depth = 0
    escaped = False
    for index in range(open_brace_index, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


def iter_latex_command_args(content: str, command: str) -> list[str]:
    args: list[str] = []
    pattern = re.compile(rf"\\{re.escape(command)}\*?(?:\s*\[[^\]]*\])?\s*\{{")
    for match in pattern.finditer(content):
        open_brace = match.end() - 1
        close_brace = find_matching_brace(content, open_brace)
        if close_brace is not None:
            args.append(content[open_brace + 1 : close_brace])
    return args


def first_latex_command_arg(content: str, command: str) -> str:
    args = iter_latex_command_args(content, command)
    return args[0] if args else ""


def extract_abstract(content: str) -> str:
    match = re.search(r"\\begin\{abstract\}([\s\S]*?)\\end\{abstract\}", content)
    if match:
        return match.group(1)
    return first_latex_command_arg(content, "abstract")


def latex_to_summary_text(text: str, max_chars: int = 900) -> str:
    cleaned = re.sub(r"(?<!\\)%.*", " ", text)
    replacements = [
        (r"\\(?:cite|citep|citet|citealp|ref|eqref|autoref|cref|Cref|label)\*?(?:\s*\[[^\]]*\])*\s*\{[^{}]*\}", " "),
        (r"\\url\s*\{([^{}]*)\}", r"\1"),
        (r"\\(?:textbf|textit|emph|texttt|textsc|mathrm|mathbf)\s*\{([^{}]*)\}", r"\1"),
    ]
    previous = None
    while previous != cleaned:
        previous = cleaned
        for pattern, replacement in replacements:
            cleaned = re.sub(pattern, replacement, cleaned)
    cleaned = re.sub(r"\\[a-zA-Z@]+\*?(?:\s*\[[^\]]*\])?", " ", cleaned)
    cleaned = re.sub(r"[{}\\_^&#]", " ", cleaned)
    cleaned = cleaned.replace("~", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > max_chars:
        return cleaned[: max_chars - 1].rstrip() + "…"
    return cleaned


def extract_section_outline(content: str, max_items: int = 24) -> list[tuple[str, str]]:
    outline: list[tuple[str, str]] = []
    pattern = re.compile(r"\\(section|subsection|subsubsection)\*?(?:\s*\[[^\]]*\])?\s*\{")
    for match in pattern.finditer(content):
        close_brace = find_matching_brace(content, match.end() - 1)
        if close_brace is None:
            continue
        title = latex_to_summary_text(content[match.end() : close_brace], max_chars=120)
        if title:
            outline.append((match.group(1), title))
        if len(outline) >= max_items:
            break
    return outline


def extract_caption_items(content: str, max_items: int = 18) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    pattern = re.compile(r"\\caption(?:\s*\[[^\]]*\])?\s*\{")
    for match in pattern.finditer(content):
        close_brace = find_matching_brace(content, match.end() - 1)
        if close_brace is None:
            continue
        prefix = content[max(0, match.start() - 600) : match.start()]
        env_matches = list(re.finditer(r"\\begin\{(figure\*?|table\*?|algorithm\*?)\}", prefix))
        env = env_matches[-1].group(1).rstrip("*") if env_matches else "caption"
        label = {"figure": "图", "table": "表", "algorithm": "算法"}.get(env, "标题")
        caption = latex_to_summary_text(content[match.end() : close_brace], max_chars=180)
        if caption:
            items.append((label, caption))
        if len(items) >= max_items:
            break
    return items


def write_article_summary(
    path: Path,
    *,
    package: dict[str, Any],
    merged_content: str,
    glossary: dict[str, str],
    qa_warnings: list[str],
    warnings: list[str],
    tex_path: Path,
    pdf_path: Path | None,
    segment_count: int,
) -> None:
    title = latex_to_summary_text(first_latex_command_arg(merged_content, "title"), max_chars=180)
    abstract = latex_to_summary_text(extract_abstract(merged_content), max_chars=1200)
    outline = extract_section_outline(merged_content)
    captions = extract_caption_items(merged_content)
    glossary_items = list(glossary.items())[:30]

    lines = [
        "# 论文速览",
        "",
        "## 基本信息",
        f"- arXiv ID: {package.get('arxiv_id') or '未知'}",
        f"- 标题: {title or '未提取到标题'}",
        f"- 翻译 TeX: {tex_path.name}",
        f"- PDF: {pdf_path.name if pdf_path else '未生成'}",
        f"- 翻译片段数: {segment_count}",
        f"- QA 警告数: {len(qa_warnings)}",
        f"- 格式保护警告数: {len(warnings)}",
        "",
        "## 摘要",
        abstract or "未提取到摘要。",
        "",
        "## 章节目录",
    ]
    if outline:
        for level, heading in outline:
            indent = "  " if level == "subsection" else "    " if level == "subsubsection" else ""
            lines.append(f"{indent}- {heading}")
    else:
        lines.append("- 未提取到章节标题。")

    lines.extend(["", "## 图表与算法"])
    if captions:
        for label, caption in captions:
            lines.append(f"- {label}: {caption}")
    else:
        lines.append("- 未提取到图表或算法标题。")

    lines.extend(["", "## 术语表"])
    if glossary_items:
        for source, target in glossary_items:
            lines.append(f"- {source}: {target}")
        if len(glossary) > len(glossary_items):
            lines.append(f"- 另有 {len(glossary) - len(glossary_items)} 个术语未在此展开。")
    else:
        lines.append("- 未命中项目术语表。")

    lines.extend(
        [
            "",
            "## Agent 问答上下文",
            "- 优先依据翻译后的 TeX/PDF 回答论文内容问题。",
            "- 本文件用于快速定位标题、摘要、章节、图表、算法和术语，不替代完整论文。",
            "- 如 QA 警告数大于 0，回答前应优先查看 `qa_warnings.json`。",
        ]
    )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def copy_path_if_exists(source: Path | None, destination: Path) -> None:
    if source is None or not source.exists():
        return
    if source.resolve() == destination.resolve():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)
    else:
        shutil.copy2(source, destination)


def stage_package_artifacts(
    *,
    build_dir: Path,
    package: dict[str, Any],
    package_path: Path,
    translations_path: Path,
) -> None:
    package_dir = build_dir / "package"
    package_dir.mkdir(parents=True, exist_ok=True)

    staged_package = dict(package)
    staged_package["work_dir"] = str(package_dir)

    merged_source_path = Path(str(package.get("merged_latex_path", ""))) if package.get("merged_latex_path") else None
    staged_merged_source = package_dir / "merged_source.tex"
    copy_path_if_exists(merged_source_path, staged_merged_source)
    if merged_source_path and merged_source_path.exists():
        staged_package["merged_latex_path"] = str(staged_merged_source)

    glossary_path = Path(str(package.get("glossary_path", ""))) if package.get("glossary_path") else None
    staged_glossary = package_dir / "glossary.json"
    copy_path_if_exists(glossary_path, staged_glossary)
    if glossary_path and glossary_path.exists():
        staged_package["glossary_path"] = str(staged_glossary)

    structure_info_path = Path(str(package.get("structure_info_path", ""))) if package.get("structure_info_path") else None
    staged_structure_info = package_dir / "structure_info.json"
    copy_path_if_exists(structure_info_path, staged_structure_info)
    if structure_info_path and structure_info_path.exists():
        staged_package["structure_info_path"] = str(staged_structure_info)

    segments_dir = Path(str(package.get("segments_dir", ""))) if package.get("segments_dir") else None
    staged_segments_dir = package_dir / "segments"
    copy_path_if_exists(segments_dir, staged_segments_dir)
    if segments_dir and segments_dir.exists():
        staged_package["segments_dir"] = str(staged_segments_dir)
        staged_segments = []
        for record in package.get("segments", []):
            staged_record = dict(record)
            source_path = Path(str(record.get("path", "")))
            if source_path.name:
                staged_record["path"] = str(staged_segments_dir / source_path.name)
            staged_segments.append(staged_record)
        staged_package["segments"] = staged_segments

    copy_path_if_exists(translations_path, package_dir / "translations.json")
    copy_path_if_exists(package_path.parent / "translations.template.json", package_dir / "translations.template.json")

    original_pdf_path = Path(str(package.get("original_pdf_path", ""))) if package.get("original_pdf_path") else None
    staged_original_pdf = package_dir / "original.pdf"
    copy_path_if_exists(original_pdf_path, staged_original_pdf)
    if original_pdf_path and original_pdf_path.exists():
        staged_package["original_pdf_path"] = str(staged_original_pdf)

    source_dir = Path(str(package.get("source_dir", ""))) if package.get("source_dir") else None
    copy_path_if_exists(source_dir / "debug_log.html" if source_dir else None, package_dir / "debug_log.html")
    write_json(package_dir / "translation_package.json", staged_package)


def remove_path_if_output_child(path: Path | None, output_dir: Path, keep_paths: set[Path]) -> None:
    if path is None:
        return
    resolved = path.resolve()
    if resolved in keep_paths or not is_relative_to(resolved, output_dir):
        return
    if resolved.is_dir():
        shutil.rmtree(resolved, ignore_errors=True)
    elif resolved.exists():
        resolved.unlink()


def make_keep_paths(*paths: Path | str | None) -> set[Path]:
    keep_paths: set[Path] = set()
    for path in paths:
        if path:
            keep_paths.add(Path(str(path)).resolve())
    return keep_paths


def cleanup_output_dir(
    *,
    output_dir: Path,
    keep_paths: set[Path],
    package: dict[str, Any],
    package_path: Path,
    translations_path: Path,
    report_path: Path,
    translated_pdf_result: str | None,
    original_pdf_result: str | None,
) -> None:
    arxiv_id = str(package.get("arxiv_id", "") or "")
    candidates: list[Path | None] = [
        report_path,
        output_dir / "pdf_compile",
        output_dir / "parser_work",
        output_dir / "segments",
        output_dir / "article_summary.md",
        output_dir / "debug_log.html",
        output_dir / "merge_report.json",
        output_dir / "qa_warnings.json",
        output_dir / "translation_log.log",
        output_dir / "translated.tex",
        output_dir / "translations.template.json",
        output_dir / "translations.json",
        output_dir / "original.pdf",
        package_path,
        translations_path,
        Path(translated_pdf_result) if translated_pdf_result else None,
        Path(original_pdf_result) if original_pdf_result else None,
    ]
    if arxiv_id:
        candidates.extend(
            [
                output_dir / f"arxiv_{arxiv_id}_translated.tex",
                output_dir / f"arxiv_{arxiv_id}_original.pdf",
            ]
        )
    for key in ("segments_dir", "glossary_path", "structure_info_path", "merged_latex_path"):
        if package.get(key):
            candidates.append(Path(str(package[key])))

    for candidate in candidates:
        remove_path_if_output_child(candidate, output_dir, keep_paths)


def cleanup_generated_artifacts(
    *,
    output_dir: Path,
    keep_paths: set[Path],
    package: dict[str, Any],
    package_path: Path,
    translations_path: Path,
    report_path: Path,
    translated_pdf_result: str | None,
    original_pdf_result: str | None,
) -> None:
    cleanup_output_dir(
        output_dir=output_dir,
        keep_paths=keep_paths,
        package=package,
        package_path=package_path,
        translations_path=translations_path,
        report_path=report_path,
        translated_pdf_result=translated_pdf_result,
        original_pdf_result=original_pdf_result,
    )
    package_dir = package_path.parent
    if package_dir.resolve() != output_dir.resolve() and is_relative_to(package_dir, output_dir):
        cleanup_output_dir(
            output_dir=package_dir,
            keep_paths=keep_paths,
            package=package,
            package_path=package_path,
            translations_path=translations_path,
            report_path=report_path,
            translated_pdf_result=translated_pdf_result,
            original_pdf_result=original_pdf_result,
        )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Merge translated segments produced by Codex/subagents."
    )
    parser.add_argument("package_json", help="Path to translation_package.json")
    parser.add_argument("translations_json", help="Path to completed translations JSON")
    parser.add_argument("--output-dir", default="", help="Output directory for final files.")
    parser.set_defaults(compile_pdf=True, pdf_required=True)
    parser.add_argument(
        "--compile-pdf",
        action="store_true",
        help="Compile a PDF. This is the default and is kept for compatibility.",
    )
    parser.add_argument(
        "--no-compile-pdf",
        dest="compile_pdf",
        action="store_false",
        help="Development-only: skip PDF compilation and only write translated .tex.",
    )
    parser.add_argument(
        "--pdf-required",
        action="store_true",
        help="Require PDF compilation to succeed. This is the default.",
    )
    parser.add_argument(
        "--allow-pdf-failure",
        dest="pdf_required",
        action="store_false",
        help="Development-only: keep the .tex result even if PDF compilation fails.",
    )
    parser.add_argument(
        "--engine",
        default="xelatex",
        choices=["xelatex", "pdflatex"],
        help="Local LaTeX engine for required PDF compilation.",
    )
    parser.add_argument(
        "--layout-mode",
        default="preserve",
        choices=["preserve", "repair"],
        help=(
            "LaTeX layout handling. preserve keeps original figure/table placement "
            "and sizing; repair applies FloatBarrier, size limits, and table wrapping."
        ),
    )
    parser.add_argument(
        "--float-placement",
        default="preserve",
        choices=["preserve", "H"],
        help=(
            "Float placement strategy. preserve keeps original placement options; "
            "H anchors all figures/tables at their source positions with [H]."
        ),
    )
    parser.add_argument(
        "--pdf-mode",
        default="bilingual",
        choices=["bilingual", "translated"],
        help="PDF output mode. Default: bilingual side-by-side.",
    )
    parser.add_argument(
        "--original-pdf",
        default="",
        help="Existing original English PDF for bilingual mode. Overrides original_pdf_path from the package.",
    )
    parser.add_argument(
        "--allow-misaligned-bilingual",
        action="store_true",
        help=(
            "Force page-level bilingual PDF output even when original and translated "
            "page counts differ. This is mainly for visual comparison and can be misaligned."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if protected LaTeX tokens are missing from translations.",
    )
    parser.add_argument(
        "--keep-intermediates",
        action="store_true",
        help="Development-only: keep package, segment, report, and compile intermediate files.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()

    package_path = Path(args.package_json).resolve()
    translations_path = Path(args.translations_json).resolve()
    package = load_json(package_path)
    translations_payload = load_json(translations_path)
    translations, contract_errors = validate_translation_contract(package, translations_payload)
    by_id = {str(item.get("segment_id")): item for item in translations}
    glossary = load_glossary(package)

    output_dir = Path(args.output_dir).resolve() if args.output_dir else package_path.parent
    build_dir = output_dir / "build"
    output_dir.mkdir(parents=True, exist_ok=True)
    build_dir.mkdir(parents=True, exist_ok=True)
    stage_package_artifacts(
        build_dir=build_dir,
        package=package,
        package_path=package_path,
        translations_path=translations_path,
    )

    translated_segments: list[str] = []
    original_segments: list[str] = []
    warnings: list[str] = []
    qa_warnings: list[str] = []
    errors: list[str] = contract_errors[:]

    for record in package["segments"]:
        segment_id = record["segment_id"]
        source_path = Path(record["path"])
        source = source_path.read_text(encoding="utf-8")
        original_segments.append(source)

        translation = by_id.get(segment_id)
        if not translation:
            translated_segments.append("")
            continue

        translated = str(
            translation.get("translated_latex")
            or translation.get("translation")
            or ""
        )

        warnings.extend(check_protected_tokens(source, translated, segment_id))
        qa_warnings.extend(check_quality_rules(source, translated, segment_id, glossary))
        translated_segments.append(translated)

    if args.strict and warnings:
        errors.extend(warnings)

    merged_tex_path = build_dir / (
        f"arxiv_{package.get('arxiv_id')}_translated.tex"
        if package.get("arxiv_id")
        else "translated.tex"
    )
    report_path = build_dir / "merge_report.json"
    qa_warnings_path = build_dir / "qa_warnings.json"
    total_log_path = build_dir / "translation_log.log"
    summary_path = output_dir / "article_summary.md"
    redact_roots = [output_dir, package_path.parent]
    if package.get("source_dir"):
        redact_roots.append(Path(str(package["source_dir"])))

    if errors:
        write_qa_warnings(qa_warnings_path, qa_warnings)
        write_total_log(
            total_log_path,
            success=False,
            tex_path=merged_tex_path if merged_tex_path.exists() else None,
            pdf_path=None,
            pdf_mode=args.pdf_mode if args.compile_pdf else None,
            pdf_success=False,
            pdf_result=None,
            translated_pdf_result=None,
            original_pdf_result=None,
            merge_message="Validation failed before merge.",
            warnings=warnings,
            qa_warnings=qa_warnings,
            errors=errors,
            segment_count=len(translated_segments),
            compile_dir=None,
            redact_roots=redact_roots,
            layout_mode=args.layout_mode,
        )
        write_json(
            report_path,
            {
                "success": False,
                "layout_mode": args.layout_mode,
                "errors": errors,
                "warnings": warnings,
                "qa_warnings": qa_warnings,
            },
        )
        print(
            json.dumps(
                {
                    "success": False,
                    "qa_warnings_path": str(qa_warnings_path),
                    "log_path": str(total_log_path),
                },
                ensure_ascii=False,
            )
        )
        return 1

    structure_info_path = (
        Path(package["structure_info_path"])
        if package.get("structure_info_path")
        else None
    )

    if structure_info_path and structure_info_path.exists():
        merged_content = merge_with_structure(
            structure_info_path,
            translated_segments,
            original_segments,
        )
        merge_message = "Merged with saved structure_info."
    else:
        merged_source = Path(package["merged_latex_path"]).read_text(encoding="utf-8")
        merger = LaTeXResultMerger()
        success, merged_content, merge_message = merger.merge_translated_segments(
            translated_segments=translated_segments,
            original_segments=original_segments,
            original_full_content=merged_source,
            llm_model="local-agent",
            allow_format_fix=True,
        )
        if not success:
            errors = [merge_message]
            write_qa_warnings(qa_warnings_path, qa_warnings)
            write_total_log(
                total_log_path,
                success=False,
                tex_path=merged_tex_path if merged_tex_path.exists() else None,
                pdf_path=None,
                pdf_mode=args.pdf_mode if args.compile_pdf else None,
                pdf_success=False,
                pdf_result=None,
                translated_pdf_result=None,
                original_pdf_result=None,
                merge_message=merge_message,
                warnings=warnings,
                qa_warnings=qa_warnings,
                errors=errors,
                segment_count=len(translated_segments),
                compile_dir=None,
                redact_roots=redact_roots,
                layout_mode=args.layout_mode,
            )
            write_json(
                report_path,
                {
                    "success": False,
                    "layout_mode": args.layout_mode,
                    "errors": errors,
                    "warnings": warnings,
                    "qa_warnings": qa_warnings,
                },
            )
            print(
                json.dumps(
                    {
                        "success": False,
                        "qa_warnings_path": str(qa_warnings_path),
                        "log_path": str(total_log_path),
                    },
                    ensure_ascii=False,
                )
            )
            return 1

    merged_content = patch_latex_for_engine(merged_content, args.engine, args.layout_mode, args.float_placement)
    merged_content = patch_visible_structural_terms(merged_content)
    qa_warnings.extend(check_document_quality(merged_content))
    merged_tex_path.write_text(merged_content, encoding="utf-8")

    pdf_result = None
    translated_pdf_result = None
    original_pdf_result = None
    original_pdf_pages = None
    translated_pdf_pages = None
    bilingual_alignment = None
    pdf_success = False
    compile_dir = None
    if args.compile_pdf:
        source_dir = Path(package["source_dir"]) if package.get("source_dir") else None
        translated_success, translated_pdf_result = try_compile_pdf(merged_tex_path, source_dir, args.engine)
        compile_dir = merged_tex_path.parent / "pdf_compile"
        if translated_success and args.pdf_mode == "translated":
            final_translated_pdf = output_dir / Path(str(translated_pdf_result)).name
            if Path(str(translated_pdf_result)).resolve() != final_translated_pdf.resolve():
                shutil.copy2(Path(str(translated_pdf_result)), final_translated_pdf)
            pdf_success = True
            pdf_result = str(final_translated_pdf)
        elif translated_success and args.pdf_mode == "bilingual":
            try:
                original_pdf = resolve_original_pdf(package, args.original_pdf, build_dir)
                original_pdf_result = str(original_pdf)
                translated_pdf_path = Path(translated_pdf_result)
                original_pdf_pages = pdf_page_count(original_pdf)
                translated_pdf_pages = pdf_page_count(translated_pdf_path)
                if original_pdf_pages != translated_pdf_pages and not args.allow_misaligned_bilingual:
                    final_translated_pdf = output_dir / translated_pdf_path.name
                    if translated_pdf_path.resolve() != final_translated_pdf.resolve():
                        shutil.copy2(translated_pdf_path, final_translated_pdf)
                    bilingual_alignment = (
                        "skipped_page_mismatch: original has "
                        f"{original_pdf_pages} pages, translated has {translated_pdf_pages} pages"
                    )
                    warnings.append(
                        "Bilingual page-level PDF was skipped because page counts differ "
                        f"(original={original_pdf_pages}, translated={translated_pdf_pages}). "
                        "Using the Chinese-only PDF as final output. Re-run with "
                        "--allow-misaligned-bilingual only for page-thumbnail comparison."
                    )
                    pdf_success = True
                    pdf_result = str(final_translated_pdf)
                else:
                    bilingual_alignment = (
                        "page_counts_match"
                        if original_pdf_pages == translated_pdf_pages
                        else "forced_misaligned_page_bilingual"
                    )
                    if bilingual_alignment == "forced_misaligned_page_bilingual":
                        warnings.append(
                            "Forced page-level bilingual PDF with mismatched page counts "
                            f"(original={original_pdf_pages}, translated={translated_pdf_pages}); "
                            "left/right content may not align."
                        )
                    pdf_success, pdf_result = build_bilingual_side_by_side_pdf(
                        original_pdf=original_pdf,
                        translated_pdf=translated_pdf_path,
                        output_pdf=output_dir / f"{merged_tex_path.stem}_bilingual.pdf",
                        work_dir=compile_dir,
                        engine=args.engine,
                    )
            except Exception as exc:
                pdf_success = False
                pdf_result = f"bilingual PDF failed: {exc}"
        else:
            pdf_success = False
            pdf_result = translated_pdf_result

        if args.pdf_required and not pdf_success:
            errors = [str(pdf_result or "PDF compilation failed")]
            write_qa_warnings(qa_warnings_path, qa_warnings)
            write_total_log(
                total_log_path,
                success=False,
                tex_path=merged_tex_path,
                pdf_path=None,
                pdf_mode=args.pdf_mode,
                pdf_success=False,
                pdf_result=pdf_result,
                translated_pdf_result=translated_pdf_result,
                original_pdf_result=original_pdf_result,
                merge_message=merge_message,
                warnings=warnings,
                qa_warnings=qa_warnings,
                errors=errors,
                segment_count=len(translated_segments),
                compile_dir=compile_dir,
                redact_roots=redact_roots,
                layout_mode=args.layout_mode,
            )
            write_json(
                report_path,
                {
                    "success": False,
                    "tex_path": str(merged_tex_path),
                    "pdf_mode": args.pdf_mode,
                    "layout_mode": args.layout_mode,
                    "pdf_success": False,
                    "pdf_result": pdf_result,
                    "translated_pdf_result": translated_pdf_result,
                    "original_pdf_result": original_pdf_result,
                    "original_pdf_pages": original_pdf_pages,
                    "translated_pdf_pages": translated_pdf_pages,
                    "bilingual_alignment": bilingual_alignment,
                    "warnings": warnings,
                    "qa_warnings": qa_warnings,
                },
            )
            print(
                json.dumps(
                    {
                        "success": False,
                        "tex_path": str(merged_tex_path),
                        "qa_warnings_path": str(qa_warnings_path),
                        "log_path": str(total_log_path),
                    },
                    ensure_ascii=False,
                )
            )
            return 1

    pdf_path = Path(pdf_result) if pdf_success and pdf_result and Path(str(pdf_result)).exists() else None
    write_qa_warnings(qa_warnings_path, qa_warnings)
    write_article_summary(
        summary_path,
        package=package,
        merged_content=merged_content,
        glossary=glossary,
        qa_warnings=qa_warnings,
        warnings=warnings,
        tex_path=merged_tex_path,
        pdf_path=pdf_path,
        segment_count=len(translated_segments),
    )
    write_total_log(
        total_log_path,
        success=True,
        tex_path=merged_tex_path,
        pdf_path=pdf_path,
        summary_path=summary_path,
        pdf_mode=args.pdf_mode if args.compile_pdf else None,
        pdf_success=pdf_success,
        pdf_result=pdf_result,
        translated_pdf_result=translated_pdf_result,
        original_pdf_result=original_pdf_result,
        merge_message=merge_message,
        warnings=warnings,
        qa_warnings=qa_warnings,
        errors=[],
        segment_count=len(translated_segments),
        compile_dir=compile_dir,
        redact_roots=redact_roots,
        layout_mode=args.layout_mode,
    )

    report = {
        "success": True,
        "tex_path": str(merged_tex_path),
        "summary_path": str(summary_path),
        "merge_message": merge_message,
        "pdf_mode": args.pdf_mode if args.compile_pdf else None,
        "layout_mode": args.layout_mode,
        "pdf_success": pdf_success,
        "pdf_result": pdf_result,
        "translated_pdf_result": translated_pdf_result,
        "original_pdf_result": original_pdf_result,
        "original_pdf_pages": original_pdf_pages,
        "translated_pdf_pages": translated_pdf_pages,
        "bilingual_alignment": bilingual_alignment,
        "warnings": warnings,
        "qa_warnings": qa_warnings,
        "segment_count": len(translated_segments),
    }
    write_json(report_path, report)
    if not args.keep_intermediates:
        keep_paths = make_keep_paths(
            merged_tex_path,
            summary_path,
            qa_warnings_path,
            total_log_path,
            report_path,
            pdf_path,
            translated_pdf_result,
            original_pdf_result,
        )
        cleanup_generated_artifacts(
            output_dir=output_dir,
            keep_paths=keep_paths,
            package=package,
            package_path=package_path,
            translations_path=translations_path,
            report_path=report_path,
            translated_pdf_result=translated_pdf_result,
            original_pdf_result=original_pdf_result,
        )
    print(
        json.dumps(
            {
                "success": True,
                "tex_path": str(merged_tex_path),
                "pdf_path": str(pdf_path) if pdf_path else None,
                "summary_path": str(summary_path),
                "qa_warnings_path": str(qa_warnings_path),
                "log_path": str(total_log_path),
                "warnings_count": len(warnings),
                "qa_warnings_count": len(qa_warnings),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
