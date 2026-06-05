# chinarxiv Agent Translation Skills

[English](README.md) | [简体中文](README.zh-CN.md)

用于将 arXiv 论文和学术 PDF 翻译为简体中文的 Codex skills。仓库脚本不内置
LLM API 调用；默认工作流是 `arxiv-bilingual-pdf-translate`：由 BabelDOC
负责 PDF 版面抽取和渲染，由 Codex/Claude Code subagent 翻译 JSONL 文本单元。
旧的 `arxiv-translate-skill` LaTeX 流程保留，用于需要可编辑 `.tex` 的场景。

## 工作流

- `arxiv-bilingual-pdf-translate`：默认的版面保真双语 PDF 工作流。从原始
  PDF 出发，抽取 BabelDOC 翻译单元，将 JSONL 批次交给本地 agent 翻译，
  校验结果后由 BabelDOC 渲染最终左英右中的 `.dual.pdf`。
- `arxiv-translate-skill`：旧 LaTeX 工作流。下载 arXiv 源码，切分 TeX
  片段，由 agent 翻译 LaTeX fragment，合并成中文 `.tex` 并编译 PDF。
  该路径适合可编辑 TeX，但 TeX 重排无法保证图表和页码对齐。

## 功能概览

- 输入：arXiv ID、arXiv URL、本地学术 PDF，或 arXiv LaTeX 源码。
- 不内置 LLM API 调用：Codex、Claude Code 或其他代码 agent 按文件契约填写翻译结果。
- 版面保真：默认路径将 PDF 解析和渲染交给 BabelDOC，避免 LaTeX float/page
  重排导致的双语 PDF 图文错位。
- 翻译契约：JSONL 单元保留 `unit_id`、`source_hash`、占位符、标签、引用和
  BabelDOC 要求的输出形态。
- 校验：渲染前拒绝缺失单元、重复 ID、hash 不匹配、空译文和占位符丢失。
- 旧 TeX 路径：需要可编辑中文 `.tex`、中文单语 PDF 或 LaTeX 级 QA 时仍可使用。

## 环境要求

统一使用 `uv` 管理 Python 环境和工具。不要把项目依赖直接安装到系统 Python。

```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt
```

BabelDOC PDF 渲染链路也统一用 `uv tool` 安装：

```bash
uv tool install --python 3.12 BabelDOC
babeldoc --warmup
```

运行项目中的 BabelDOC bridge 脚本时，应使用 BabelDOC 的 tool 环境，确保
Python 能 import BabelDOC：

```bash
uv tool run --from BabelDOC python <bridge-script> ...
```

旧的 LaTeX 编译路径仍需要本地 LaTeX 环境，例如 `xelatex`，并需要中文字体
支持。旧的双语并排 PDF 还需要 `poppler-utils` 提供的 `pdfinfo`。在
Ubuntu/Debian 环境中通常需要：

```bash
sudo apt-get install -y texlive-xetex texlive-latex-recommended texlive-latex-extra texlive-lang-chinese poppler-utils fonts-noto-cjk
```

## 验证

验证两个 skill 的元数据：

```bash
VALIDATOR="${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py"
if [ -f "$VALIDATOR" ]; then
  uv run python "$VALIDATOR" skills/arxiv-bilingual-pdf-translate
  uv run python "$VALIDATOR" skills/arxiv-translate-skill
else
  echo "quick_validate.py not found; run smoke_test.py instead."
fi
```

无网络 smoke test：验证 BabelDOC JSONL 文件契约和旧 `.tex` 合并路径，
显式跳过外部下载和 PDF 渲染。

```bash
uv run python skills/arxiv-bilingual-pdf-translate/scripts/smoke_test.py
uv run python skills/arxiv-translate-skill/scripts/smoke_test.py
```

旧 PDF smoke test：额外验证本机 LaTeX PDF 编译能力，生成中文单语测试 PDF，
不下载英文原文 PDF。

```bash
uv run python skills/arxiv-translate-skill/scripts/smoke_test.py --compile-pdf
```

PDF smoke test 会测试旧的 LaTeX 路径；如果本机缺少 `xelatex`、`xeCJK`
或中文字体支持，该测试会返回失败。

## 安装到 Agent

将需要的 skill 目录安装或复制到 agent 的 skills 目录。对于 Codex，通常是：

```text
$CODEX_HOME/skills/arxiv-bilingual-pdf-translate/
$CODEX_HOME/skills/arxiv-translate-skill/
```

默认双语 PDF 使用 `arxiv-bilingual-pdf-translate`。只有需要可编辑中文 TeX
时再使用 `arxiv-translate-skill`。

## 使用方法

- 默认双语 PDF：`使用 arxiv-bilingual-pdf-translate 将 arXiv 1812.10695 翻译为左英右中的简体中文双语 PDF。`
  功能说明：下载或复制原始 PDF，抽取 BabelDOC 翻译单元，分发 JSONL 批次给
  agent，校验后渲染版面保真的 `.dual.pdf`。
- 本地 PDF：`使用 arxiv-bilingual-pdf-translate 将 ./paper.pdf 翻译为左英右中的中文双语 PDF。`
  功能说明：不依赖 arXiv 源码，直接走同一 BabelDOC PDF 工作流。
- 可编辑 TeX：`使用 arxiv-translate-skill 翻译 arXiv 1812.10695 并生成可编辑中文 TeX。`
  功能说明：运行旧 LaTeX segment 工作流；本机具备 LaTeX 环境时可编译中文 PDF。

## 输出文件

BabelDOC 工作流会把运行产物写入 `chinarxiv_runs/<paper>/`：

- `source.pdf`：原始输入 PDF。
- `translation_units.jsonl`：BabelDOC 记录给 agent 的翻译请求。
- `batches/`：分发给 subagent 的 JSONL 批次。
- `batch_results/`：subagent 返回的 JSONL 翻译结果。
- `translations.completed.jsonl`：校验并合并后的译文。
- `output/*.dual.pdf`：最终左英右中的双语 PDF。

旧 LaTeX 工作流会在论文根目录保留最终 PDF 和 Markdown：

- `*_translated_bilingual.pdf` 或 `*_translated.pdf`：最终 PDF。原文和译文页数不一致时会自动跳过双语并排输出，因为页级配对会导致文字和图表错位。
- `article_summary.md`：论文速览，包含标题、摘要、章节目录、图表/算法标题、命中术语和 QA 状态，便于快速阅读或作为 AI/agent 问答上下文。

旧 `build/` 目录保留可编辑和诊断文件：

- `*_translated.tex`：中文译文 LaTeX，与编译依赖放在一起，便于修改后快速重编。
- `package/original.pdf`：准备阶段下载的原始英文 PDF 副本；双语 PDF 合并会优先使用它。
- `package/agent_tasks/`：供 Codex/Claude Code 直接执行的 agent 翻译任务文件。
- `package/translations.template.json`：agent 需要填写并另存为 `translations.completed.json` 的 JSON 模板。
- `qa_warnings.json`：翻译质量复核项，例如标题/图表未翻译、术语缺失、缩写间距、图中文字无法自动处理。
- `translation_log.log`：总日志，汇总格式保护风险、PDF 编译日志和最终产物信息。
- `merge_report.json`、`package/` 和 PDF 编译过程文件，用于调试或重新编译。

验证和日志输出会尽量使用 `<SMOKE_TEST_WORK_DIR>`、`<HOME>` 等占位符脱敏本机路径。

## 许可证与来源

本项目以 GNU General Public License v3.0 发布，详见 [LICENSE](LICENSE)。

本项目的部分 LaTeX/arXiv 处理思路和实现模式改编自或借鉴了以下上游项目：

- GPT Academic：<https://github.com/binary-husky/gpt_academic>
  许可证：GNU General Public License v3.0
- chinarxiv：<https://github.com/kaixindelele/chinarxiv>
  许可证：编写本引用说明时，未在仓库根目录识别到明确的许可证文件或 GitHub 检测许可证。
- 来源与修改说明：详见 [NOTICE](NOTICE)

上游项目组件的版权归各自作者和贡献者所有；本项目修改部分的版权归本项目贡献者所有，并同样受 GPL-3.0 约束。

## Skill 使用模型

- 主 agent：维护术语表、翻译规则、一致性、分段分配和最终验收。
- 流水线 subagent：运行脚本并报告生成路径、日志和状态。
- 翻译 subagent：只翻译分配的分段，输出必须符合翻译契约。

## 目录结构

```text
skills/arxiv-bilingual-pdf-translate/
├── SKILL.md
├── agents/
├── references/
└── scripts/
    ├── prepare_paper.py
    ├── babeldoc_agent_bridge.py
    ├── build_batches.py
    ├── validate_translations.py
    └── smoke_test.py

skills/arxiv-translate-skill/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── references/
│   ├── workflow.md
│   ├── translation-contract.md
│   └── local-testing.md
└── scripts/
    ├── prepare_arxiv_translation.py
    ├── merge_agent_translations.py
    ├── smoke_test.py
    └── arxiv_translate_core/
```
