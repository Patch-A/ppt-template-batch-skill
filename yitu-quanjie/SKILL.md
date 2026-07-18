# 一图全解（Yitu Quanjie）— 展会推广海报批量生成工作流

> 触发关键词："一图全解"
> 技能名称：`yitu-quanjie`
> 版本：2026-07-16

---

## 硬触发规则（MEMORY.md 级别）

用户提到「一图全解」关键词时，必须强制执行本流程。

**触发词：** 一图全解

**执行步骤：**
1. 读 `skills/yitu-quanjie/SKILL.md`
2. Step 1：逐项收集 国家 → 产品 → PPT模版（每项确认✅后继续）
3. Step 2：用 python-pptx 递归拆解模版（含 Group 嵌套，shape_type==6）
4. Step 3：web_search 查 2026 真实市场数据（5 维度：市场规模/进口依赖/中X贸易/产业政策/相关展会）
5. Step 4：按原文长度约束替换 6 个区域（封面/介绍/产品范围表格/市场优势4点/买家采购），文本长度 ≤ 原文
6. Step 5：验证无溢出、无残留原文、格式完整、Group无遗漏

**核心铁律：**
- 文本长度 ≤ 原文（防溢出串联坍塌）
- Group 必须递归遍历（防遗漏）
- 表格行高使用明确的最小高度并按内容计算；溢出必须进入验证报告
- 市场数据必须来自公开报告（IMARC/Mordor Intelligence/Grand View Research等），不编造

---

## 工作流概览

```
用户触发 → 收集3项输入 → 拆解模版 → 研究市场数据 → 替换内容 → 验证交付
```

---

## Step 1：触发 & 信息收集

用户发送 **"一图全解"** 启动流程，AI 逐项收集：

| # | 字段 | 说明 | 示例 |
|---|------|------|------|
| 1 | 国家 | 目标市场国家 | 巴西、墨西哥、印尼 |
| 2 | 产品 | 具体品类 | 印刷技术及包装、中央厨房及餐饮设备 |
| 3 | PPT模版 | 一图全解 PPTX 文件 | 用户上传 |

每收到一项确认一项（✅），全部收齐后进入 Step 2。

---

## Step 2：拆解模版

用 `python-pptx` 递归遍历所有形状（**必须递归 Group**，`shape_type == 6`）：

```python
def walk_shapes(shapes, callback):
    for shape in shapes:
        callback(shape)
        if shape.shape_type == 6:  # GROUP
            walk_shapes(shape.shapes, callback)
```

识别以下关键区域：

| 区域 | 识别方式 | 替换策略 |
|------|---------|---------|
| 封面标题 | 文本框，通常位于顶部 | 替换国家+产品名称 |
| 介绍段落 | 大段文本，位于标题下方 | 精简改写至原文长度 |
| 产品范围 | TABLE 或文本框 | 按品类重写分类列表 |
| 市场优势 | 文本框（可能在 Group 内） | 4 点结构，每点约 150–200 字 |
| 买家采购 | 文本框，位于底部 | 买家画像替换 |

---

## Step 3：研究 2026 真实市场数据

针对「国家 + 产品」搜索以下维度（使用 web_search，不得编造数据）：

1. **市场规模**：该国家该品类 2025–2026 市场规模、CAGR
2. **进口依赖**：本土产能缺口、主要进口来源国
3. **中X贸易**：中国占该国进口份额、双边贸易趋势
4. **产业政策**：该国相关产业激励、环保法规、数字化政策
5. **相关展会**：该国已有的同类展会作为定位参考

数据来源优先级：IMARC > Mordor Intelligence > Grand View Research > Fortune BI > 行业展会官网

---

## Step 4：内容替换规则

### 4.1 文本替换（保留格式）

```python
def replace_text(shape, new_text):
    tf = shape.text_frame
    for p in tf.paragraphs:
        for r in p.runs:
            r.text = ''
    if tf.paragraphs[0].runs:
        tf.paragraphs[0].runs[0].text = new_text
    else:
        run = tf.paragraphs[0].add_run()
        run.text = new_text
```

### 4.2 长度约束（铁律）

**所有替换文本长度必须 ≤ 原文长度**，优先控制在原文 80%–100%：

```python
original_len = len(shape.text_frame.text)
assert len(new_text) <= original_len * 1.05, f"文本超长: {len(new_text)} vs {original_len}"
```

### 4.3 各区域模板

**介绍段落**（原文约 220–250 字）：
```
2026{国家}{产品}新品汇将深度聚焦{国家}{产品}产业的{增长态势}，
以及{下游行业1}、{下游行业2}、{下游行业3}等领域持续释放的{需求关键词}，
汇聚中国{产品}优质企业登陆{城市}，集中展示{核心技术1}、{核心技术2}、
{核心技术3}及{核心技术4}等全产业链前沿技术与新品，
成为中国企业开拓{区域}{产品}市场的核心桥梁与精准对接平台。
```

**市场优势 4 点**（每点约 150–200 字）：
```
一、市场体量庞大，需求持续增长
{国家}是{区域}第一大{产品}市场。{市场规模数据，含年份、金额、CAGR}。
{下游驱动行业}持续驱动需求扩张，{政策/趋势}升级需求迫切。

二、本土高端产能不足，进口替代空间大
{国家}高端{具体设备/材料}本土供给缺口显著，依赖{主要进口来源}进口。
中国{产品}性价比高、交付快，在{细分赛道}已建立全球竞争力。

三、区域枢纽效应强，中X合作稳固
{国家}辐射{周边国家列表}，是进入{区域}{产品}市场的首选门户。
中国连续X年居{国家}第一大贸易伙伴，中X产能合作为中国企业出海提供背书。

四、产业政策协同发力，升级红利释放
{政策名称}目标{政策目标}，{金额}投资。{法规名称}强制{具体要求}，
倒逼全产业链设备升级，数字化转型战略同步推进{技术关键词}落地。
```

**买家采购**（原文约 180–200 字）：
```
本次展会将多渠道精准邀约{国家}及{区域}地区{产品}领域专业观众，
核心群体涵盖：{买家类型1}、{买家类型2}、{买家类型3}、
{买家类型4}、{买家类型5}等行业采购商及终端用户，
助力参展企业直通{区域}{产品}核心市场。
```

### 4.4 表格替换

产品范围表格（2 行 × 2 列）按品类拆分为两个一级分类，每个下列 5–6 个子类：
- Cell[0,0]：一级分类标签（如"印刷技术领域："）
- Cell[0,1]：5 个子类列表，用 `\n` 分隔
- Cell[1,0]：一级分类标签（如"包装设备领域："）
- Cell[1,1]：5–6 个子类列表

替换后使用脚本定义的 `MIN_TABLE_ROW_HEIGHT`（0.25 英寸）和内容估算行高；不得依赖 `Emu(0)`。

---

## Step 5：验证

替换完成后逐项检查：

| 检查项 | 方法 |
|--------|------|
| 无残留原文 | 搜索原产品关键词（如"中央厨房"）不应出现 |
| 文本不溢出 | 对比替换前后文本长度 |
| 格式保留 | 字体/颜色/大小与原文一致 |
| Group 内无遗漏 | 递归遍历验证所有嵌套文本 |
| 表格行高 | 无异常留白 |

---

## 踩坑经验

1. **Group 递归必须**：一图全解模版中市场优势文本框常嵌套在 Group 内，`slide.shapes` 无法直接访问
2. **文本长度是第一优先级**：宁可精简，不可溢出。溢出会导致串联覆盖后续全部区域
3. **表格行高明确**：每行至少 0.25 英寸，按内容计算所需高度；超过表格原始高度时报告 overflow。
4. **保留下方不变区域**：模版中"参展费用""补贴"等区域不在一图全解替换范围，不修改
5. **数据必须真实**：不得编造市场数据，必须来自搜索确认的公开报告

---

## 附带脚本：`scripts/yitu_quanjie_replace.py`

```python
#!/usr/bin/env python3
"""一图全解 PPT 内容替换脚本"""

from pptx import Presentation
from pptx.util import Emu
import sys, os

def replace_text(shape, new_text):
    tf = shape.text_frame
    for p in tf.paragraphs:
        for r in p.runs:
            r.text = ''
    if tf.paragraphs[0].runs:
        tf.paragraphs[0].runs[0].text = new_text
    else:
        run = tf.paragraphs[0].add_run()
        run.text = new_text

def replace_text_keep_lines(shape, new_text):
    tf = shape.text_frame
    lines = new_text.split('\n')
    for p in tf.paragraphs:
        for r in p.runs:
            r.text = ''
    for i, line in enumerate(lines):
        if i < len(tf.paragraphs):
            if tf.paragraphs[i].runs:
                tf.paragraphs[i].runs[0].text = line
            else:
                run = tf.paragraphs[i].add_run()
                run.text = line

def replace_cell(cell, new_text):
    tf = cell.text_frame
    for p in tf.paragraphs:
        for r in p.runs:
            r.text = ''
    if tf.paragraphs[0].runs:
        tf.paragraphs[0].runs[0].text = new_text
    else:
        run = tf.paragraphs[0].add_run()
        run.text = new_text

def walk_shapes(shapes, callback):
    for shape in shapes:
        callback(shape)
        if shape.shape_type == 6:
            walk_shapes(shape.shapes, callback)

def run_replacement(input_path, output_path, content_map, table_data=None):
    """
    input_path: 模版 PPTX 路径
    output_path: 输出 PPTX 路径
    content_map: {shape_name: new_text}
    table_data: {'cell_00': text, 'cell_01': text, 'cell_10': text, 'cell_11': text}
    """
    prs = Presentation(input_path)
    slide = prs.slides[0]
    
    def process(shape):
        if shape.name in content_map:
            new_text = content_map[shape.name]
            original_len = len(shape.text_frame.text)
            if len(new_text) > original_len * 1.1:
                print(f"⚠️ {shape.name}: 替换文本({len(new_text)}字)超过原文({original_len}字)10%，可能有溢出风险")
            if '\n' in new_text:
                replace_text_keep_lines(shape, new_text)
            else:
                replace_text(shape, new_text)
            print(f"✅ {shape.name} ({len(new_text)}字)")
        
        if shape.has_table and table_data:
            table = shape.table
            replace_cell(table.cell(0, 0), table_data['cell_00'])
            replace_cell(table.cell(0, 1), table_data['cell_01'])
            replace_cell(table.cell(1, 0), table_data['cell_10'])
            replace_cell(table.cell(1, 1), table_data['cell_11'])
            for row in table.rows:
                row.height = max(MIN_TABLE_ROW_HEIGHT, content_row_height(row, table))
            print(f"✅ {shape.name} 表格已替换 + 行高自适应")
    
    walk_shapes(slide.shapes, process)
    prs.save(output_path)
    print(f"🎉 完成：{output_path} ({os.path.getsize(output_path):,} bytes)")
```

---

## Replacement validation contract

`validate_replacement(input_path, output_path, content_map, table_data=None)` loads the first slide and returns a JSON-serializable report without saving. The report validates mapped shape names, text capacity, table coordinates (`cell_00`, `cell_01`, `cell_10`, `cell_11`, or `cell_<row>_<col>`), and the output path. Missing shapes, invalid cells, and overflows are reported under stable fields and make `ok` false.

`run_replacement(...)` keeps the existing Python and CLI entry point. It runs validation before any mutation or save, then preserves existing runs and recursively processes groups. Table rows use a minimum height of 0.25 inches and content-based sizing; the implementation never uses `Emu(0)`.

The CLI supports `--dry-run`. It prints only the validation report as JSON and never creates or overwrites the output PPTX. A normal invocation retains the existing `Created: ...` output.

## 部署路径

```
skills/yitu-quanjie/
├── SKILL.md                      ← 本文件（工作流说明）
└── scripts/
    └── yitu_quanjie_replace.py   ← PPT 替换脚本
```

MEMORY.md 中添加入口规则：

```markdown
## yitu-quanjie 硬触发规则

触发词：一图全解

执行步骤：
1. 读 skills/yitu-quanjie/SKILL.md
2. Step 1：逐项收集 国家 → 产品 → PPT模版
3. Step 2：python-pptx 递归拆解模版（含 Group）
4. Step 3：web_search 2026 真实市场数据（5维度）
5. Step 4：按原文长度约束替换 6 个区域
6. Step 5：验证无溢出/无残留/格式完整

核心铁律：
- 文本长度 ≤ 原文
- Group 必须递归遍历
- 市场数据来自公开报告，不编造
```
