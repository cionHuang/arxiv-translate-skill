# arxiv-translate-skill

[English](README.md) | [简体中文](README.zh-CN.md)

用于将 arXiv/LaTeX 学术论文翻译为简体中文的 Codex skill。它使用本地 Codex/subagent 完成翻译，不调用外部 LLM API；脚本只负责下载、解析、切分、合并和 PDF 编译等确定性工作。

## 功能概览

- 输入：arXiv ID、arXiv URL，或可解析的 arXiv LaTeX 源码论文。
- 下载：准备阶段默认同时下载 arXiv LaTeX 源码和原始英文 PDF，双语 PDF 合并会优先使用本地缓存，减少二次联网授权。
- 翻译：按 LaTeX 结构切分论文，由 agent/subagent 翻译分段。
- 术语与 QA：主 agent 维护术语表、翻译规范、一致性和最终检查。
- 版面策略：将图、表、算法、显示公式和代码块作为不可拆 anchor block。默认 `--layout-mode preserve` 保留原始浮动位置和尺寸；仅在需要时使用 `--layout-mode repair` 启用 FloatBarrier/flafter、图片/表格尺寸限制和算法缩排。
- 必要产物：必须生成翻译后的 `.tex` 和 PDF；PDF 编译失败时本次翻译视为失败。
- 默认 PDF：仅在原文和译文页数一致时生成左英右中的双语并排 PDF；页数不一致时自动将中文单语 PDF 作为最终 PDF，并把原因写入 `build/merge_report.json`。
- 论文速览：生成 `article_summary.md`，便于快速了解论文，也可作为后续 AI/agent 问答的轻量上下文。
- 干净输出：默认在论文根目录只保留最终 PDF 和 Markdown；可编译的 `.tex`、JSON、日志和工作流/编译过程文件统一放在 `build/` 下。

## 环境要求

安装 Python 依赖：

```bash
pip install -r requirements.txt
```

PDF 编译需要本地 LaTeX 环境，例如 `xelatex`，并需要中文字体支持。双语并排 PDF 还需要 `poppler-utils` 提供的 `pdfinfo`。在 Ubuntu/Debian 环境中通常需要：

```bash
sudo apt-get install -y texlive-xetex texlive-latex-recommended texlive-latex-extra texlive-lang-chinese poppler-utils fonts-noto-cjk
```

## 验证

验证 skill 元数据：

```bash
VALIDATOR="${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py"
if [ -f "$VALIDATOR" ]; then
  python3 "$VALIDATOR" skills/arxiv-translate-skill
else
  echo "quick_validate.py not found; run smoke_test.py instead."
fi
```

无网络 smoke test：验证 `.tex` 合并、输出清理和路径脱敏，显式跳过 PDF。

```bash
python3 skills/arxiv-translate-skill/scripts/smoke_test.py
```

PDF smoke test：额外验证本机 PDF 编译能力，生成中文单语测试 PDF，不下载英文原文 PDF。

```bash
python3 skills/arxiv-translate-skill/scripts/smoke_test.py --compile-pdf
```

如果本机缺少 `xelatex`、`xeCJK` 或中文字体支持，PDF smoke test 会返回失败。

## 安装到 Agent

将 `skills/arxiv-translate-skill/` 安装或复制到 agent 的 skills 目录。对于 Codex，通常是：

```text
$CODEX_HOME/skills/arxiv-translate-skill/
```

之后在对话中直接点名 `arxiv-translate-skill` 即可触发该 skill。

## 使用方法

- 基础翻译：`使用 arxiv-translate-skill skill 将 arXiv 1812.10695 翻译为简体中文。`
  功能说明：下载 arXiv LaTeX 源码和原始英文 PDF，解析并切分论文，组织 agent 翻译，合并生成中文 `.tex` 和默认双语并排 PDF。
- URL 翻译：`使用 arxiv-translate-skill 为 https://arxiv.org/abs/1812.10695 生成中文翻译。`
  功能说明：自动从 arXiv URL 提取论文 ID，复用同一翻译流程，最终交付 `.tex` 和 PDF。
- 双语并排 PDF：`使用 arxiv-translate-skill 为 https://arxiv.org/abs/1812.10695 生成左英右中的双语并排 PDF。`
  功能说明：页数一致时左侧展示英文原文页、右侧展示中文译文页，适合校对和对照阅读。只有在接受错页缩略图对比时才使用 `--allow-misaligned-bilingual`。
- 中文单语 PDF：`使用 arxiv-translate-skill 将 arXiv 1812.10695 翻译为中文单语 PDF。`
  功能说明：生成仅包含中文译文的 PDF，适合最终阅读或分发。
- 继续修订：`继续 arxiv-translate-skill 流程，并根据 build/qa_warnings.json 修订翻译。`
  功能说明：根据格式保护风险、术语缺失、标题/图表未翻译等 QA 项继续修订。

## 输出文件

正常交付后，论文根目录默认只保留最终 PDF 和 Markdown：

- `*_translated_bilingual.pdf` 或 `*_translated.pdf`：最终 PDF。原文和译文页数不一致时会自动跳过双语并排输出，因为页级配对会导致文字和图表错位。
- `article_summary.md`：论文速览，包含标题、摘要、章节目录、图表/算法标题、命中术语和 QA 状态，便于快速阅读或作为 AI/agent 问答上下文。

`build/` 目录保留可编辑和诊断文件：

- `*_translated.tex`：中文译文 LaTeX，与编译依赖放在一起，便于修改后快速重编。
- `package/original.pdf`：准备阶段下载的原始英文 PDF 副本；双语 PDF 合并会优先使用它。
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
