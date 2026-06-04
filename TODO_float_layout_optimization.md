# Float 布局优化 TODO

> 创建日期：2026-06-04
> 状态：分析完成，待执行
> 关联 issue：翻译后图表/表格严重位置漂移

---

## 一、问题定性

### 1.1 现象

用 `arxiv-translate-skill` 翻译论文（以 `2602.16710` 作为测试样本）后，**所有** figure 和 table 在译文中与原位严重偏离，甚至跳节。三个变体的输出对照：

| 变体 | layout_mode | 页数 | 双语PDF | 问题 |
|---|---|---|---|---|
| `arxiv_translate_2602_preserve` | preserve | 22 | ✅ 成功 | float 漂移 |
| `arxiv_translate_2602_layout_fix` | repair | 22 | ✅ 成功 | float 漂移 + 多余白边 |
| `arxiv_translate_2602_guarded` | repair | **19** | ❌ 跳过 | float 漂移到丢失 3 页 |

三项产物的翻译内容完全一致（同一份 140 个 segment 的 agent 输出），问题出在 merge 编译阶段。

### 1.2 根因链

```
中文文本比英文短 ~43%（73586 → 41668 字符）
  → body text 占页减少
    → LaTeX float 算法重新计算 figure/table 位置
      → float 漂移到与原文不同的页码/节
```

同时还有一个**结构性缺陷**放大了漂移：

```
step3_content_splitter 的"第六阶段：反向操作"
  → reverse_latex_command_arguments(["caption"], ...)
    → 把 figure 环境内部 \caption{...} 挖出作为独立 segment
      → 每个 figure 被切碎为 3-7 个 preserve/translate 碎片
        → 翻译 agent 看不到完整的 figure 上下文
          → caption 翻译后字符长度变化 → figure 内部行数改变 → 再次加速漂移
```

### 1.3 为什么原项目 chinarxiv 不会这样

原项目 [kaixindelele/chinarxiv](https://github.com/kaixindelele/chinarxiv) 基于 GPT Academic 的 `latex_actions.py`。它的翻译策略是**整段发送给 LLM**，LLM 在完整的 LaTeX 上下文中翻译 caption 和文字。figure 环境始终作为不可拆分的原子块，不会出现"碎片化"问题。

当前项目的 `step3_content_splitter.py` 虽然代码复用自同一来源，但其 fine-grained 分段策略在 float 处理上引入了结构性破坏。

---

## 二、涉及的关键模块和行号

### 2.1 切分阶段（问题源头）

| 文件 | 关键函数/位置 | 行号 | 作用 |
|---|---|---|---|
| `scripts/arxiv_translate_core/step3_content_splitter.py` | `reverse_latex_command_arguments()` | L284 | **祸首**：在已标记 PRESERVE 的 figure 内部把 `\caption{...}` 挖出来标为 TRANSFORM |
| 同上 | `split_latex_with_full_protection()` | L429 | 主切分流程 |
| 同上 | 第六阶段 "反向操作" | L550-574 | 调用 `reverse_latex_command_arguments(["caption"], ...)` 和 `reverse_forbidden_text(..., "abstract", ...)` |
| `scripts/prepare_arxiv_translation.py` | `main()` → `splitter.split_content()` | L70 | 调用切分器生成 segments 和 structure_info |

### 2.2 merge 阶段（缺少锚定机制）

| 文件 | 关键函数/位置 | 行号 | 作用 |
|---|---|---|---|
| `scripts/merge_agent_translations.py` | `merge_with_structure()` | L946 | **简单拼接** preserve + translate，无 float 位置感知 |
| 同上 | `patch_latex_for_engine()` | L535 | LaTeX 引擎适配（目前没有 float 锚定逻辑） |
| 同上 | `ensure_layout_safety_support()` | L313 | repair 模式的 FloatBarrier 补丁（**反而加剧问题**） |
| 同上 | `add_float_barriers()` | L356 | 在 section 前插 `\FloatBarrier`（缩短的 body text + 强制清空 float queue → 多余白边） |
| 同上 | `normalize_float_placements()` | L344 | 标准化 float placement 为 `[!htbp]` |
| 同上 | `patch_includegraphics_limits()` | L371 | 限制 includegraphics 尺寸 |

---

## 三、优化方向

### 方向一：float 包 `[H]` 锚定（短期，今天可落地）

**核心思路**：在 merge 阶段对全部 `\begin{figure}` / `\begin{table}` 改写成 `[H]` 定位（需同时添加 `\usepackage{float}`）。figure 固定在源码出现位置，不再被 LaTeX float 算法推走。

**实现要点**：
1. 在 `merge_agent_translations.py` 的 `patch_latex_for_engine()`（L535）中新增 `patch_float_placement_H()` 函数
2. 遍历所有 `\begin{figure}` 和 `\begin{table}`，将其 placement option 替换为 `[H]`
3. 确保导言区包含 `\usepackage{float}`（如果已存在则不重复添加）
4. 处理特殊情况：`\begin{figure*}` → `\begin{figure*}[H]`，`\begin{table*}` → `\begin{table*}[H]`
5. 对于已经是 `[H]` 的 float 不重复修改

**验证标准（方向一达标条件）**：

| 检查项 | 方法 | 通过条件 |
|---|---|---|
| float 不跨节漂移 | 对比原文/译文 PDF 中每个 float 所处的 `\section` | 零违规 |
| 页数偏差控制 | 检查 `build/merge_report.json` 中的 `original_pdf_pages` vs `translated_pdf_pages` | 差值 ≤ 1 页 |
| 无双语 PDF 跳过 | merge_report 中 `bilingual_alignment` 不为 `skipped_page_mismatch` | 必须通过 |
| 无大段白边 | 肉眼检查 PDF，连续空白不超过 1/3 页 | 零违规；如有则改用回退策略 |
| 测试论文 | 2602.16710（10 个 figure 的富图论文） | 全部通过 |

**验证命令**：
```bash
# 1. 重新 prepare（如果还没有 package）
python3 skills/arxiv-translate-skill/scripts/prepare_arxiv_translation.py 2602.16710

# 2. 翻译（用已有的 translations）
# 3. 以 bilingual 模式 merge
python3 skills/arxiv-translate-skill/scripts/merge_agent_translations.py \
  arxiv_translate_work/2602.16710/translation_package.json \
  arxiv_translate_work/2602.16710/translations.completed.json \
  --pdf-mode bilingual

# 4. 检查 merge_report.json
python3 -c "
import json
r = json.load(open('arxiv_translate_work/2602.16710/build/merge_report.json'))
print(f'pages: orig={r.get(\"original_pdf_pages\")} trans={r.get(\"translated_pdf_pages\")}')
print(f'bilingual: {r.get(\"bilingual_alignment\")}')
"
```

---

### 方向二：float 环境原子化拆分（中期，需重构 splitter）

**核心思路**：不再把 figure/table 内部的 caption 拆成独立 segment。float 环境整体作为 PRESERVE 块，caption 文本作为附属元数据交给 agent 翻译。

**实现要点**：

1. **修改 `step3_content_splitter.py` 的切分策略**：
   - 在 `split_latex_with_full_protection()` (L429) 中，**先于**第一阶段识别所有 `\begin{figure}...\end{figure}` 和 `\begin{table}...\end{table}` 块
   - 将这些块整体标记为不可拆分的 PRESERVE
   - **移除**或**跳过**对这些块调用 `reverse_latex_command_arguments(["caption"], ...)`——只对 float 外部的 caption 做反向操作
   - 将 figure/table 内的 caption 文本提取出来，作为 segment 的 **附属元数据**（而非独立 segment）

2. **修改 segment 数据结构**（`prepare_arxiv_translation.py`）：
   - 为 segment 增加可选的 `caption_snippets` 字段，列出该 segment 包含的 float 的 caption 原文
   - agent 翻译时将 caption 一并返回，但标记为 caption 类型

3. **修改 merge 逻辑**（`merge_agent_translations.py`）：
   - `merge_with_structure()` (L946) 需要能区分"正文翻译"和"caption 翻译"
   - 将翻译后的 caption 精确替换回 PRESERVE 块中的对应位置

**验证标准（方向二达标条件）**：

| 检查项 | 方法 | 通过条件 |
|---|---|---|
| structure_info 无 float 碎片 | 脚本自动检查：每个包含 `\begin{figure}` 的 preserve item 必须同时包含 `\end{figure}` | 零违规 |
| segment 中没有孤立 caption | 遍历 segments 目录下的 `.tex` 文件，caption 文本不应作为独立文件出现 | 零违规 |
| captain 翻译质量不退化 | 人工抽检 5 个 figure caption，与方向一的翻译结果对比 | 不出现上下文断裂导致的误译 |
| 方向一的达标条件仍满足 | 同方向一的验收流程 | 全部通过 |

**验证脚本**：
```python
# 检查 structure_info.json 中的 float 完整性
import json
data = json.load(open('build/package/structure_info.json'))
for item in data:
    content = item.get('content', '')
    has_begin_fig = '\\begin{figure' in content
    has_end_fig = '\\end{figure' in content
    has_begin_tab = '\\begin{table' in content
    has_end_tab = '\\end{table' in content
    if has_begin_fig and not has_end_fig:
        print(f"FAIL: figure fractured at index {item.get('index', '?')}")
    if has_begin_tab and not has_end_tab:
        print(f"FAIL: table fractured at index {item.get('index', '?')}")
print("All floats are atomic.")
```

---

### 方向三：页位锚定（长期，需新增模块）

**核心思路**：将"页面布局保持"作为 pipeline 的显式设计目标。先分析原文 PDF 的 page break 位置和 float 分布，据此指导分段和 merge。

**实现要点**：

1. **新增 page layout 分析模块**（建议新建 `arxiv_translate_core/step_page_analyzer.py`）：
   - 输入：原文 PDF + merged_source.tex
   - 用 `pdftotext -bbox` 获取每页的 float 位置和文本 range
   - 输出：`page_map.json`，记录每个 page 上的 section 标题、float 列表

2. **修改分段策略**：
   - 用 page break 位置作为主要分段边界（替代纯 token 限制）
   - 每个 segment 对应一个原文 page 的 text
   - float 描述作为该 segment 的 side metadata

3. **修改 merge 策略**：
   - 在每个 page break 位置插入 `\pagebreak`
   - 对 float 使用 `\afterpage{\FloatBarrier}` 将其锚定在当前页

4. **双语 PDF 对齐验证**：
   - 用 `pdfinfo` 逐页对比页数
   - 用 `pdftotext` 逐页提取 section 标题列表进行对比

**验收标准（方向三分层达标）**：

**第一层：页面对齐（必修）**

| 检查项 | 方法 | 通过条件 |
|---|---|---|
| 页数差值 | merge_report 中的 `original_pdf_pages` vs `translated_pdf_pages` | 差值 ≤ 1 |
| 首尾页内容对应 | 对比原文/译文 PDF 各 page 的 `pdftotext` 输出中的 section 标题 | 首尾页的章节对应无误 |

**第二层：float 对齐（强烈推荐）**

| 检查项 | 方法 | 通过条件 |
|---|---|---|
| float 页面归属 | `pdfinfo -f N -l N` 逐页检查 | 原文第 N 页的 float 在译文中出现在第 N 页或 N±1 页 |
| 双语并排 visual check | 肉眼逐页翻看双语 PDF | 相同页码左右两侧的 figure 位置大致对齐 |

**第三层：双语并排精确对齐（最终目标）**

| 检查项 | 方法 | 通过条件 |
|---|---|---|
| figure 对齐率 | 人工计数+对比双语 PDF | 所有 figure 都在同一页出现 |
| 表格对齐率 | 同上 | 所有 table 都在同一页出现 |

**验证命令**：
```bash
# 第一层：页数对齐
python3 -c "
import json, subprocess
r = json.load(open('build/merge_report.json'))
assert r['original_pdf_pages'] == r['translated_pdf_pages'], \
    f'Page mismatch: {r[\"original_pdf_pages\"]} vs {r[\"translated_pdf_pages\"]}'
print('Page alignment: PASS')
"

# 第二层：逐页 section 对比
for page in $(seq 1 $(pdfinfo original.pdf | grep Pages | awk '{print $2}')); do
  echo "=== Page $page ==="
  echo "ORIG:"; pdftotext -f $page -l $page original.pdf - | grep -E '^[0-9]+\.?[0-9]*\s' | head -5
  echo "TRANS:"; pdftotext -f $page -l $page translated.pdf - | grep -E '^[0-9]+\.?[0-9]*\s' | head -5
done
```

---

## 四、阶段性路径

```
方向一（1天）
  ├── 实现 patch_float_placement_H()
  ├── 用 2602.16710 验证：float 不跨节 + 页数差 ≤ 1
  └── ✋ 达标判定：merge_report 双语通过 + 肉眼确认无跨节漂移

方向一 + 方向二（3-5天）
  ├── 重构 step3_content_splitter 的 float 处理
  ├── 修改 segment 数据结构（增加 caption_snippets 字段）
  ├── 修改 merge_with_structure 的 caption 替换逻辑
  ├── 验证：structure_info 全绿 + caption 翻译质量抽检
  └── ✋ 达标判定：float 零碎片 + 方向一条件仍满足

方向一 + 方向二 + 方向三第一层（1-2周）
  ├── 新增 step_page_analyzer.py
  ├── page break 驱动的分段策略
  ├── merge 阶段的 \pagebreak 插入
  ├── 验证：页数对齐 + 逐页 TOC 对比
  └── ✋ 达标判定：页数差 ≤ 1 + TOC 逐页对应

所有方向完成（2-3周）
  ├── 方向三第二层：float 逐页锚定
  ├── 方向三第三层：双语 PDF 左右精确对齐
  └── ✋ 达标判定：双语 PDF 逐页翻看全部对齐
```

---

## 五、测试论文

| 论文 | arXiv ID | 特点 | 用途 |
|---|---|---|---|
| 主测试 | `2602.16710` | 10 个 figure + 复杂 subfigure 结构 | 方向一～三全部验收 |
| 辅助测试 | `1812.10695` | 中等复杂度，少量 figure | 回归测试 |

---

## 六、不可回退的约束

以下约束在所有方向的实现中必须保持：

1. **不得改变 segment ID 和 source_hash 的契约**：translation agent 的输入格式不变
2. **结构完整性**：merge 后的 `.tex` 必须通过 `check_latex_completeness()` 全部检查项
3. **双语 PDF 兼容**：新的 merge 逻辑必须与 `build_bilingual_side_by_side_pdf()` 兼容
4. **smoke test 通过**：`smoke_test.py` 和 `smoke_test.py --compile-pdf` 必须继续保持绿色
5. **preserve layout mode 仍是默认**：`--layout-mode preserve` 的语义必须保持为"尽可能保留原文布局"
