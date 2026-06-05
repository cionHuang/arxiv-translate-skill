# 术语表

[English](README.md) | [简体中文](README.zh-CN.md)

编辑 `terms.csv` 可以控制整个项目的翻译术语。skill 每次运行都会从项目根目录
读取该文件，所以编辑后不需要再复制或粘贴到 Codex skill 目录。

## 格式

术语表只保留三列：

```csv
source,target,case_sensitive
attention mechanism,注意力机制,false
ResNet,ResNet,true
```

- `source`：原文，论文中需要匹配的源术语或短语。
- `target`：指定表达；如果术语不翻译，则填写需要保留的英文形式。
- `case_sensitive`：大小写是否敏感；只有大小写确实重要时才设为 `true`，
  其他情况设为 `false`。

也可以把论文专属术语放在 `glossary/papers/` 下。例如
`glossary/papers/1812.10695.csv` 会在对应 run 中自动合并。

## 命令

校验当前术语表：

```bash
.venv/bin/python skills/arxiv-bilingual-pdf-translate/scripts/glossary.py validate
```

列出当前术语：

```bash
.venv/bin/python skills/arxiv-bilingual-pdf-translate/scripts/glossary.py list
```

追加一个术语：

```bash
.venv/bin/python skills/arxiv-bilingual-pdf-translate/scripts/glossary.py add "attention mechanism" "注意力机制"
```
