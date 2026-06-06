# arxiv-translate-skill

[English](README.md) | [简体中文](README.zh-CN.md)

将 arXiv 论文和学术 PDF 翻译为简体中文，并生成版面保真的左英右中双语
PDF。左侧保留原始英文 PDF 版面，右侧是由 BabelDOC 渲染的中文译文。

这是一个项目绑定型 Agent Skill。安装入口面向 Codex 和 Claude Code；skill
文件会安装到对应客户端目录，但 Python/BabelDOC 运行环境由本仓库提供。

## 效果预览

<p align="center">
  <img src="assets/translation-preview.png" alt="左英右中双语 PDF 翻译效果预览：左侧为英文原文，右侧为简体中文译文。" width="100%">
</p>

<p align="center">
  <em>示例输出：左侧保留原文版面，右侧展示对应的简体中文译文。</em>
</p>

## 环境要求

- Python 3.12。
- `uv` 已在 `PATH` 中。
- 初始化环境和下载 arXiv 论文时需要网络。
- agent 客户端需要能读取 Agent Skills，并能运行本地 shell 命令。
- 建议 agent 支持本地 subagent/并行代理，用于加速批量翻译。

## 快速安装

在仓库根目录选择一个模式运行。`--agent` 选择客户端，`--scope` 选择安装范围：

```bash
python3 scripts/install_skill.py --agent codex --scope project --bootstrap --force
```

安装模式：

| 客户端 | 范围 | 命令 | 安装位置 |
| --- | --- | --- | --- |
| Codex | 当前仓库 | `python3 scripts/install_skill.py --agent codex --scope project --bootstrap --force` | `.agents/skills/arxiv-bilingual-pdf-translate` |
| Codex | 当前用户 | `python3 scripts/install_skill.py --agent codex --scope user --bootstrap --force` | `$CODEX_HOME/skills/...`，默认 `~/.codex/skills/...` |
| Claude Code | 当前仓库 | `python3 scripts/install_skill.py --agent claude --scope project --bootstrap --force` | `.claude/skills/arxiv-bilingual-pdf-translate` |
| Claude Code | 当前用户 | `python3 scripts/install_skill.py --agent claude --scope user --bootstrap --force` | `~/.claude/skills/arxiv-bilingual-pdf-translate` |

查看所有模式和目标路径：

```bash
python3 scripts/install_skill.py --list-modes
```

`--bootstrap` 会创建或更新 `.venv`、安装依赖、准备运行目录，并预热 BabelDOC
资源。安装脚本随后运行 preflight，确认 Python/BabelDOC、术语表和输出目录可用。

如果你已经初始化过环境，也可以省略 `--bootstrap`：

```bash
python3 scripts/install_skill.py --agent claude --scope project --force
```

安装命令会在目标 skill 目录写入 `.install-manifest.json`，记录本仓库的
`project_root`。因此用户级安装后，agent 仍能找到这个仓库里的 `.venv`、
`glossary/` 和输出目录。

## 高级安装

单独初始化运行环境：

```bash
python3 skills/arxiv-bilingual-pdf-translate/scripts/bootstrap.py
.venv/bin/python skills/arxiv-bilingual-pdf-translate/scripts/arxiv_translate.py preflight
```

使用旧的显式目标参数：

```bash
python3 scripts/install_skill.py --target codex-project --force
python3 scripts/install_skill.py --target codex-user --force
python3 scripts/install_skill.py --target claude-project --force
python3 scripts/install_skill.py --target claude-user --force
```

安装到自定义 skill 目录：

```bash
python3 scripts/install_skill.py --dest /path/to/skills/arxiv-bilingual-pdf-translate --force
```

兼容旧 Codex runtime 的 `CODEX_HOME` 目标：

```bash
python3 scripts/install_skill.py --target codex-home --force
```

## 使用方法

安装后建议从本仓库根目录启动 agent。Codex 用户新开一个 Codex 会话；Claude
Code 用户如果是首次创建 `.claude/skills` 目录，重启一次 `claude`。

向 agent 发出请求：

```text
使用 arxiv-bilingual-pdf-translate 将 arXiv 1812.10695 翻译为左英右中的简体中文双语 PDF。
```

Claude Code 也可以直接调用 slash command：

```text
/arxiv-bilingual-pdf-translate 1812.10695
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

如果不确定安装到了哪里：

```bash
python3 scripts/install_skill.py --list-modes
```

如果 Claude Code 识别不到 skill，确认安装目标是 `.claude/skills/...` 或
`~/.claude/skills/...`，而不是 `.agents/skills/...`。如果目录是在 Claude Code
启动后首次创建的，需要重启 `claude`。

如果 Codex 识别不到用户级 skill，确认目标在 `$CODEX_HOME/skills/...`，默认是
`~/.codex/skills/...`，然后新开一个 Codex 会话。

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
