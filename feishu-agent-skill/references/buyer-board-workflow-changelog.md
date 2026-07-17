# buyer-board-workflow Skill — Bug 修复记录

> 实例：V for Meorient (`v-for-meorient`)  
> 维护人：古振涛  
> 修复日期：2026-07-15

---

## Bug #1：模板文字残留（严重）

### 现象

填充 PPT 表格后，单元格中出现新旧文字混合。例如"采购产品"字段同时显示新的产品列表和原模板的"电流传感器""霍尔开关芯片""MOSFET/IGBT驱动"等旧内容。

### 根因

python-pptx 将模板表格中的长文本自动拆分为多个 **run**（如下所示）：

```
[采购产品单元格]
  runs[0]: "逆变器用电流传感器（闭环霍尔电流传感器、磁通门电流传感器）"
  runs[1]: "、霍尔效应电流传感器IC、霍尔开关芯片、"
  runs[2]: "功率开关MOSFET/IGBT驱动器用隔离电流传感器、霍尔转速"
```

原代码只替换了 `runs[0].text`：

```python
# ❌ 错误方式 — 仅替换第一个 run，其余 run 残留
cell.text_frame.paragraphs[0].runs[0].text = buyer["products"]
```

结果：runs[1] 和 runs[2] 的旧文字全部保留，与新产品混在一起。

### 修复

使用 **clean_fill_cell()** 函数：**先清空所有 paragraph 所有 run 的文字，再写入单一干净 run**。

```python
def clean_fill_cell(cell, text):
    """先清空所有run的文字，再写入单一干净run，保留原格式"""
    tf = cell.text_frame
    
    # 1. 保存原模板格式
    first_run = tf.paragraphs[0].runs[0]
    try:
        saved_color = str(first_run.font.color.rgb)  # 如 "2A49F4"
    except:
        saved_color = None
    saved_size = first_run.font.size        # 如 203200 (16pt)
    saved_font = first_run.font.name        # 如 "微软雅黑"
    
    # 2. 遍历清空所有 paragraph 的所有 run
    for para in tf.paragraphs:
        for run in para.runs:
            run.text = ""
    
    # 3. 写入新文字
    tf.paragraphs[0].runs[0].text = text
    
    # 4. 恢复格式（蓝色 #2A49F4 / 16pt / 微软雅黑）
    run = tf.paragraphs[0].runs[0]
    if saved_color:
        run.font.color.rgb = RGBColor(
            int(saved_color[:2], 16),
            int(saved_color[2:4], 16),
            int(saved_color[4:6], 16)
        )
    run.font.size = saved_size
    run.font.name = saved_font

# ✅ 调用
clean_fill_cell(table.cell(0, 1), buyer["name"])
clean_fill_cell(table.cell(3, 1), buyer["products"])
clean_fill_cell(table.cell(4, 1), buyer["intro"])
```

### 验证方法

生成后逐页扫描所有表格单元格，检查是否包含原模板关键词（如"电流传感器""Goodwe""固德威""Americana""沙特""KFC"等），有残留即失败。

---

## Bug #2：动态行距未执行

### 现象

所有表格行等高，长简介文本被截断（行高不够）或留白过多（行高过大），视觉效果差。

### 根因

生成 PPT 时只填充了文字，未按 skill 规范调整行高，`table.rows[3].height` 和 `table.rows[4].height` 使用了模板默认值。

### 修复

填充数据后强制执行动态行距：

```python
def product_row_height(text):
    """采购产品：≤25字→500000, ≤50字→700000, >50字→900000 EMU"""
    n = len(text)
    if n <= 25:    return 500000
    elif n <= 50:  return 700000
    else:          return 900000

def intro_row_height(text):
    """简介：≤200字→2200000, ≤280字→2600000, >280字→3000000 EMU"""
    n = len(text)
    if n <= 200:   return 2200000
    elif n <= 280: return 2600000
    else:          return 3000000

# 填充后必须执行：
table.rows[0].height = 250000    # 企业 — 固定
table.rows[1].height = 250000    # 国家 — 固定
table.rows[2].height = 250000    # 网站 — 固定
table.rows[3].height = product_row_height(buyer["products"])  # 动态
table.rows[4].height = intro_row_height(buyer["intro"])       # 动态
```

### 行高规格一览

| 行 | EMU | 对应 |
|----|-----|------|
| 企业 | 250000 | 固定 |
| 国家 | 250000 | 固定 |
| 网站 | 250000 | 固定 |
| 采购产品 | ≤25字→500000 / ≤50字→700000 / >50字→900000 | 动态 |
| 简介 | ≤200字→2200000 / ≤280字→2600000 / >280字→3000000 | 动态 |

---

## Bug #3：幻灯片克隆（ZIP 级别操作）

### 现象

模板内容页数量不足时，不能用 `add_slide()`，因为 `add_slide()` 从母版复制只得到空白布局，不会复制表格、图片和装饰元素。

### 修复

当模板页面数不够时，用 ZIP 级别操作克隆内容页：

1. 解压 .pptx（本质是 ZIP）
2. 复制 `ppt/slides/slideX.xml` 为 `slideY.xml`
3. 复制 `ppt/slides/_rels/slideX.xml.rels` 为 `slideY.xml.rels`
4. 在 `ppt/presentation.xml` 的 `<p:sldIdLst>` 中添加新条目
5. 在 `ppt/_rels/presentation.xml.rels` 中添加新 Relationship
6. 在 `[Content_Types].xml` 中注册新 `Override`
7. 重新打包 ZIP

```python
import zipfile, shutil, os, re
from lxml import etree

def clone_slide(src_pptx, dst_pptx, src_slide_num=2, new_slide_num=7):
    """在 ZIP 级别克隆幻灯片"""
    tmpdir = "/tmp/pptx_work"
    if os.path.exists(tmpdir):
        shutil.rmtree(tmpdir)
    os.makedirs(tmpdir)
    
    with zipfile.ZipFile(src_pptx, 'r') as zf:
        zf.extractall(tmpdir)
    
    # 复制 slide XML + rels
    shutil.copy(
        f"{tmpdir}/ppt/slides/slide{src_slide_num}.xml",
        f"{tmpdir}/ppt/slides/slide{new_slide_num}.xml"
    )
    shutil.copy(
        f"{tmpdir}/ppt/slides/_rels/slide{src_slide_num}.xml.rels",
        f"{tmpdir}/ppt/slides/_rels/slide{new_slide_num}.xml.rels"
    )
    
    # 更新 presentation.xml — 添加 sldId
    # 更新 presentation.xml.rels — 添加 Relationship
    # 更新 [Content_Types].xml — 注册 Override
    # （完整代码见 skill SKILL.md 第 4.7 节）
    
    # 重新打包
    with zipfile.ZipFile(dst_pptx, 'w', zipfile.ZIP_DEFLATED) as zfout:
        for root, dirs, files in os.walk(tmpdir):
            for f in files:
                fpath = os.path.join(root, f)
                zfout.write(fpath, os.path.relpath(fpath, tmpdir))
    shutil.rmtree(tmpdir)
```

---

## Logo 抓取策略（已优化）

| 优先级 | 方法 | 备注 |
|:---:|------|------|
| 1 | requests + BeautifulSoup 访问官网，查找 src/alt 含 "logo" 的 `<img>` | 成功率约 40-60% |
| 2 | 扩展搜索：遍历前 10 个 `<img>`，筛选尺寸 50-800x20-400 的图片 | 成功率再 +20% |
| 3 | 降级：蓝色文字占位（#2A49F4 / 16pt / 微软雅黑 加粗），**不造假图片** | 兜底 |

```python
for img in soup.find_all('img'):
    src = img.get('src', '')
    alt = img.get('alt', '')
    cls = ' '.join(img.get('class', []))
    
    is_logo = any(kw in (src + alt + cls).lower() 
                  for kw in ['logo', 'brand', 'header-logo', 'site-logo'])
    
    if is_logo and not src.endswith('.svg'):
        # 构建完整 URL 并下载
        ...
```

Logo 插入位置和约束：
- **位置**：(890905, 1200000) EMU
- **最大尺寸**：≤ 4.2cm 宽 × 1.6cm 高
- **缩放**：等比缩放，取 min(scale_w, scale_h)

---

## 买家搜索规则

### 关键原则：找终端用户，不是制造商

| 品类 | 正确搜索目标 | 错误目标 |
|------|------------|---------|
| 食品加工设备 | 肉联厂、食品厂、冷冻食品企业 | 绞肉机制造商 |
| 物流仓储 | 3PL仓库、电商配送中心、冷库 | 货架制造商 |
| 液压设备 | 挖掘机厂、采矿企业、重工企业 | 液压件制造商 |
| 电机设备 | 水泵厂、风扇厂、空压机厂、钢厂、水泥厂 | 电机制造商 |
| 水泵设备 | 水务公司、电厂、炼油厂、灌溉公司 | 水泵制造商 |

### 核验标准

每家企业至少交叉验证两类证据：
1. **官网可访问** — 确认企业真实存在
2. **行业报道 / 工商信息 / 出口记录** — 确认业务匹配

---

## 生成校验清单

每次生成 PPT 后必须逐项检查：

- [ ] 封面标题已替换（如 "泵阀管件"→"食品加工设备"）
- [ ] 所有表格单元格无原模板残留文字（扫描旧关键词）
- [ ] 采购产品行高按字数动态调整
- [ ] 简介行高按字数动态调整
- [ ] Logo 已插入或文字占位
- [ ] 模板固定元素未改动（装饰组、底部提示文字、背景图）

---

## 更新记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-07-15 | v1.1 | 新增 clean_fill_cell() 修复文字残留 (Bug #1) |
| 2026-07-15 | v1.2 | 强制动态行距 (Bug #2) |
| 2026-07-15 | v1.3 | Logo 抓取策略优化，增加降级文本占位 |
| 2026-07-15 | v1.4 | 补充幻灯片克隆 ZIP 级别操作说明 (Bug #3) |
| 2026-07-15 | v1.5 | 买家搜索规则：终端用户 vs 制造商区分 |
| 2026-07-15 | v1.6 | 建议页码从 6 改为按需（印度模板 10 页） |
