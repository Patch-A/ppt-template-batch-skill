# 买家看板 Skill 问题同步与优化修复说明

> 日期：2026-07-17  
> 相关 Skill：`buyer-board-workflow`  
> 提交人：古振涛  
> 处理状态：已应用到现有 Skill

## 1. 本次同步背景

今天在使用「买家看板」Skill 生成 PPT 时，发现部分模板固定元素样式被改动，影响了交付物与原模板的一致性。因此本次对 `buyer-board-workflow` 做了专项优化：明确模板样式保留原则、补充安全替换方法、强化生成后校验，并新增模型使用建议。

## 2. 今日发现的问题

### 2.1 内容页标题样式被重设

- **问题位置**：内容页标题，例如「沙特买家需求」。
- **表现现象**：标题字体、字号、颜色、加粗、阴影或描边等效果与原模板不一致。
- **可能根因**：
  - 生成时重新设置了标题样式；
  - 或新建文本框替代了模板原有 shape；
  - 或在替换文字时没有保留原 run 的样式属性。

### 2.2 底部提示语样式被重设

- **问题位置**：底部提示语，例如「该买家已入驻出海精灵……」。
- **表现现象**：底部提示语与模板原字体效果不一致。
- **可能根因**：与标题问题一致，生成逻辑对模板固定元素做了样式覆盖或替换。

### 2.3 已有风险继续保留并强化处理

此前 Skill 中已经记录过两个风险，本次继续保留并强调：

1. **表格长文本 run 残留**
   - 不能只使用 `runs[0].text = xxx` 写入文本。
   - 因为 PPT 模板中的长文本可能被拆成多个 run，只替换第一个 run 会导致旧内容残留。

2. **动态行高未执行**
   - 如果不根据字数动态调整采购产品行和简介行高度，容易出现文本截断或留白过多。

## 3. 已应用到 Skill 的优化内容

### 3.1 新增“模型建议”

已在 Skill 中加入：

- 使用买家看板 Skill 时，**优先推荐 GPT-5.5 / ChatGPT(OpenAI) 模型**。
- 适用原因：该任务同时涉及买家检索、结构化判断、PPT 模板拆解、样式一致性校验，对模型综合能力要求较高。
- 该建议**不是硬性要求**；如果运行环境已有模型指定、用户另有要求或当前模型不可用，可继续使用当前可用模型。

### 3.2 新增“样式保留总原则”

核心原则：

> **模板自带元素只改文字，不重设样式。**

必须严格保留以下元素的原始字体、字号、颜色、加粗、阴影、描边、行距、位置和文本框属性：

- 内容页标题，例如「越南买家需求」「沙特买家需求」；
- 底部提示语，例如「该买家已入驻出海精灵……」；
- 页脚、免责声明、装饰文字；
- 蓝色头栏、底部装饰组；
- Logo、底图、装饰线等固定视觉元素。

### 3.3 明确禁止做法

Skill 中已补充以下禁止项：

- 禁止用新建 text box 替换模板标题或页脚提示语；
- 禁止对标题、页脚、固定元素重新设置：
  - `font.name`
  - `font.size`
  - `bold`
  - `color`
  - `shadow`
  - `outline`
  - 其他模板视觉效果
- 禁止为了“统一样式”而覆盖模板自带样式。

### 3.4 明确允许做法

允许且推荐的方式：

- 在原 shape / 原 paragraph / 原 run 内替换文本内容；
- 替换前保存原 run 样式；
- 替换后恢复原样式；
- 如果原文字被拆成多个 run，先清空所有 run 文本，再在第一个 run 写入新文字，同时恢复第一个 run 的原样式。

## 4. 关键修复方法

### 4.1 表格内容安全写入：`clean_fill_cell()`

表格单元格仍使用已有的 `clean_fill_cell()` 逻辑：

```python
def clean_fill_cell(cell, text):
    """先清空所有run的文字，再写入单一干净run"""
    tf = cell.text_frame
    # 1. 保存原格式
    first_run = tf.paragraphs[0].runs[0]
    saved_color = str(first_run.font.color.rgb)  # 如 "2A49F4"
    saved_size = first_run.font.size             # 如 203200 (16pt)
    saved_font = first_run.font.name             # 如 "微软雅黑"

    # 2. 清空所有 paragraph 所有 run 的文字
    for para in tf.paragraphs:
        for run in para.runs:
            run.text = ""

    # 3. 在第一个 run 写入新文字
    tf.paragraphs[0].runs[0].text = text

    # 4. 恢复格式
    run = tf.paragraphs[0].runs[0]
    run.font.color.rgb = RGBColor(
        int(saved_color[:2], 16),
        int(saved_color[2:4], 16),
        int(saved_color[4:6], 16)
    )
    run.font.size = saved_size
    run.font.name = saved_font
```

### 4.2 标题/页脚安全替换：`safe_replace_shape_text()`

新增用于标题、页脚、提示语、免责声明等模板固定文本的安全替换函数：

```python
def safe_replace_shape_text(shape, new_text):
    """仅替换文本，最大限度保留模板原始样式。适用于标题、页脚、提示语等固定元素。"""
    if not getattr(shape, "has_text_frame", False):
        return False
    tf = shape.text_frame
    if not tf.paragraphs or not tf.paragraphs[0].runs:
        return False

    first_run = tf.paragraphs[0].runs[0]
    saved = {
        "name": first_run.font.name,
        "size": first_run.font.size,
        "bold": first_run.font.bold,
        "italic": first_run.font.italic,
        "underline": first_run.font.underline,
    }
    saved_color = None
    try:
        saved_color = first_run.font.color.rgb
    except Exception:
        pass

    for para in tf.paragraphs:
        for run in para.runs:
            run.text = ""
    first_run.text = new_text

    first_run.font.name = saved["name"]
    first_run.font.size = saved["size"]
    first_run.font.bold = saved["bold"]
    first_run.font.italic = saved["italic"]
    first_run.font.underline = saved["underline"]
    if saved_color:
        first_run.font.color.rgb = saved_color
    return True
```

## 5. 生成后新增校验要求

生成买家看板 PPT 后，必须执行以下校验：

1. 逐页检查表格各单元格文字，确保无原模板残留文字；
2. 逐页检查行高是否按规则动态调整；
3. 检查 logo 插入或文字占位是否正确；
4. **专项检查内容页标题样式**：例如「沙特买家需求」，必须与模板原标题字体、字号、颜色、加粗、阴影/描边效果一致；
5. **专项检查底部提示语样式**：例如「该买家已入驻出海精灵……」，必须与模板原页脚提示语字体、字号、颜色、加粗、阴影/描边效果一致；
6. 检查固定元素没有被删除、移动或新建替换。

## 6. 已补充 Bug 记录

### Bug #3：模板标题和页脚样式被重设（2026-07-17）

- **现象**：沙特买家看板中，内容页标题「沙特买家需求」和底部提示语「该买家已入驻出海精灵……」与模板字体/效果不一致。
- **根因**：生成时对模板自带标题/页脚执行了样式重设，或用新文本框替代了原 shape，导致字体、字号、加粗、阴影/描边等模板效果丢失。
- **修复**：标题、页脚、免责声明、装饰文字等固定元素必须使用 `safe_replace_shape_text()` 或等价方式，只替换文字，不重设样式；生成后必须专项校验标题和底部提示语样式。

## 7. 本次落地状态

- Skill 更新提案：`buyer-board-workflow-20260717-12c3c13581`
- 状态：已 apply 到现有 `buyer-board-workflow` Skill
- 已新增内容：
  - GPT-5.5 / ChatGPT(OpenAI) 推荐说明；
  - 模板样式保留总原则；
  - 标题/页脚安全替换方法；
  - 禁止/允许操作边界；
  - 生成后专项校验清单；
  - Bug #3 记录。
