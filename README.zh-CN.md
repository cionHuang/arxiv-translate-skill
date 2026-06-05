# arxiv-translate-skill

[English](README.md) | [简体中文](README.zh-CN.md)

将 arXiv 论文和学术 PDF 翻译为简体中文，并生成版面保真的左英右中双语
PDF。左侧保留原始英文 PDF 版面，右侧是由 BabelDOC 渲染的中文译文。

这是一个项目绑定型 Agent Skill。skill 可以安装到兼容 Agent Skills 目录的
agent 客户端，但 Python/BabelDOC 运行环境由本仓库提供。目前端到端流程只在
Codex 中测试过；其他兼容 Agent Skills 的客户端需要各自再做运行验证。

## 环境要求

- Python 3.12。
- `uv` 已在 `PATH` 中。
- 初始化环境和下载 arXiv 论文时需要网络。
- agent 客户端需要能读取 Agent Skills，并能运行本地 shell 命令。
- 建议 agent 支持本地 subagent/并行代理，用于加速批量翻译。

## 初始化

在仓库根目录运行：

```bash
python3 skills/arxiv-bilingual-pdf-translate/scripts/bootstrap.py
.venv/bin/python skills/arxiv-bilingual-pdf-translate/scripts/arxiv_translate.py preflight
```

`bootstrap.py` 会创建 `.venv`、安装锁定依赖、准备项目内运行目录，并预热
BabelDOC 资源。`preflight` 会检查环境、术语表和输出目录是否可用。

## 安装到 Agent

安装到当前仓库的标准 Agent Skills 目录：

```bash
.venv/bin/python scripts/install_skill.py --target agent-repo --force
```

安装到用户级 Agent Skills 目录：

```bash
.venv/bin/python scripts/install_skill.py --target agent-user --force
```

安装到自定义 skill 目录：

```bash
.venv/bin/python scripts/install_skill.py --dest /path/to/skills/arxiv-bilingual-pdf-translate --force
```

如果当前 Codex runtime 仍读取 `CODEX_HOME`，使用：

```bash
.venv/bin/python scripts/install_skill.py --target codex-home --force
```

安装命令只复制 skill 文件，不会安装 BabelDOC，也不会创建 Python 环境。因此请先完成初始化。

## 使用方法

初始化并安装后，在本仓库根目录向 agent 发出请求：

```text
使用 arxiv-bilingual-pdf-translate 将 arXiv 1812.10695 翻译为左英右中的简体中文双语 PDF。
```

也支持 arXiv URL：

```text
使用 arxiv-bilingual-pdf-translate 将 https://arxiv.org/abs/1812.10695 翻译为左英右中的简体中文双语 PDF。
```

也支持本地 PDF：

```text
使用 arxiv-bilingual-pdf-translate 将 ./paper.pdf 翻译为左英右中的简体中文双语 PDF。
```

最终 PDF 会输出到：

```text
arxiv_outputs/<paper>.zh-CN.dual.pdf
```

中间文件会保存在 `.arxiv_work/`，通常只有排查失败运行时才需要查看。

## 术语表

项目术语表在：

```text
glossary/terms.csv
```

CSV 列为：

```text
source,target,case_sensitive
```

也可以用命令追加术语：

```bash
.venv/bin/python skills/arxiv-bilingual-pdf-translate/scripts/glossary.py add "attention mechanism" "注意力机制"
```

校验当前术语表：

```bash
.venv/bin/python skills/arxiv-bilingual-pdf-translate/scripts/glossary.py validate
```

## 常见问题

如果 agent 无法运行 skill，先执行：

```bash
.venv/bin/python skills/arxiv-bilingual-pdf-translate/scripts/arxiv_translate.py preflight
```

如果 BabelDOC 导入或资源加载失败，重新初始化：

```bash
python3 skills/arxiv-bilingual-pdf-translate/scripts/bootstrap.py
```

如果某个 PDF 渲染失败，可以要求 agent 使用增强兼容模式重试，或禁用富文本翻译后重试。skill 中已写入这些失败恢复规则。

## 许可证与来源

本项目以 GNU General Public License v3.0 发布，详见 [LICENSE](LICENSE)。

开源项目引用说明：

- BabelDOC：用于 PDF 解析、版面保持和渲染。仓库：
  <https://github.com/funstory-ai/BabelDOC>。
- GPT Academic：学术论文翻译工具链的工作流启发来源。仓库：
  <https://github.com/binary-husky/gpt_academic>。
- kaixindelele/chinarxiv：原始项目启发来源。仓库：
  <https://github.com/kaixindelele/chinarxiv>。

详见 [NOTICE](NOTICE)。
