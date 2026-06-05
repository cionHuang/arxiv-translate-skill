# chinarxiv BabelDOC Agent Translator

[English](README.md) | [简体中文](README.zh-CN.md)

将 arXiv 论文和学术 PDF 翻译为简体中文，并生成版面保真的左英右中双语
PDF。本项目把 PDF 解析、版面保持和渲染交给 BabelDOC；Codex、Claude Code
或其他 agent 平台只负责翻译 BabelDOC 抽取出的 JSONL 单元。仓库脚本本身不
直接调用 LLM API。

## 功能概览

- 输入：arXiv ID、arXiv URL 或本地学术 PDF。
- 输出：左英右中的双语 `.dual.pdf`。
- 版面保真：从原始 PDF 出发，由 BabelDOC 负责解析和渲染，避免 LaTeX
  重编译导致的页码重排和图表漂移。
- Agent 翻译：BabelDOC 的翻译请求会被抽取为 JSONL 单元，交给本地
  Codex/Claude Code subagent 翻译。
- 声明策略：bridge 默认关闭 BabelDOC 原始水印，并在输出 PDF 中加入本项目
  自己的仓库和译文核对声明。
- 校验：渲染前检查 `unit_id`、`source_hash`、占位符和译文字段，错误结果不会进入 PDF。
- 可选 TeX 上下文：arXiv 源码只用于术语表和上下文，不再作为默认 PDF 生成路径。

## 环境要求

统一使用项目内 `uv` 环境。不要把依赖安装到系统 Python，也不要把
`uv tool run --from BabelDOC` 作为默认 bridge 命令；它会创建独立的临时
tool 环境，在 agent 沙箱里可能反复触发 PyPI 下载。

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -c "import babeldoc.translator.translator; print('BabelDOC ok')"
.venv/bin/babeldoc --warmup
```

所有仓库脚本都从项目根目录用 `.venv/bin/python` 运行。

## 验证

验证 skill 元数据：

```bash
VALIDATOR="${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py"
if [ -f "$VALIDATOR" ]; then
  .venv/bin/python "$VALIDATOR" skills/arxiv-bilingual-pdf-translate
else
  echo "quick_validate.py not found; run smoke_test.py instead."
fi
```

运行无网络 smoke test。该测试只验证 JSONL 分批和翻译契约，不触发 BabelDOC
PDF 渲染：

```bash
.venv/bin/python skills/arxiv-bilingual-pdf-translate/scripts/smoke_test.py
```

## 安装到 Agent

将 skill 目录安装或复制到 agent 的 skills 目录。对于 Codex，通常是：

```text
$CODEX_HOME/skills/arxiv-bilingual-pdf-translate/
```

项目内 `.venv` 与 skill 目录是分开的。调用 skill 时应从项目根目录运行命令，
确保 `.venv/bin/python` 可用。

## 使用方法

- arXiv 论文：
  `使用 arxiv-bilingual-pdf-translate 将 arXiv 1812.10695 翻译为左英右中的简体中文双语 PDF。`
- arXiv URL：
  `使用 arxiv-bilingual-pdf-translate 将 https://arxiv.org/abs/1812.10695 翻译为左英右中的中文双语 PDF。`
- 本地 PDF：
  `使用 arxiv-bilingual-pdf-translate 将 ./paper.pdf 翻译为左英右中的中文双语 PDF。`

工作流：

1. 准备 `source.pdf` 和可选 arXiv 源码上下文。
2. 抽取 BabelDOC 翻译单元到 `translation_units.jsonl`。
3. 拆分为 `batches/batch_*.jsonl`。
4. 用本地 agent subagent 翻译批次。
5. 校验并合并为 `translations.completed.jsonl`。
6. 由 BabelDOC 渲染最终 `.dual.pdf`。

## 输出文件

运行产物位于 `chinarxiv_runs/<paper>/`：

- `source.pdf`：原始输入 PDF。
- `source_tex/`：可选 arXiv 源码上下文。
- `translation_units.jsonl`：BabelDOC 记录给 agent 的翻译请求。
- `batches/`：分发给 subagent 的 JSONL 批次。
- `batch_results/`：subagent 返回的 JSONL 翻译结果。
- `translations.completed.jsonl`：校验并合并后的译文。
- `output/*.dual.pdf`：最终左英右中的双语 PDF。

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
```

## 许可证与来源

本项目以 GNU General Public License v3.0 发布，详见 [LICENSE](LICENSE)。

本项目使用 BabelDOC 作为 PDF 解析和渲染引擎，并在 [NOTICE](NOTICE) 中记录
chinarxiv 和 GPT Academic 的工作流启发来源。
