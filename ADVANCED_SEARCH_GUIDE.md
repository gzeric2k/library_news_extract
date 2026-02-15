# NewsBank 高级搜索优化指南

## 概述

本项目现已集成高级搜索查询构建器，支持多字段搜索、布尔逻辑组合和通配符，大幅提高搜索精确度。

## 新功能

### 1. 多字段搜索
- **Title (标题)**: 文章标题/Headline
- **Lead (首段)**: 文章导语/Lead Paragraph
- **All Text (全文)**: 完整文章内容
- **Author (作者)**: 作者名称
- **Source (来源)**: 出版物来源

### 2. 布尔逻辑
- **AND**: 必须同时满足
- **OR**: 满足任一条件
- **NOT**: 排除条件

### 3. 通配符支持
- **`*`**: 匹配多个字符（如 `penfold*` 匹配 penfolds/penfold）
- **`?`**: 匹配单个字符（如 `wom?n` 匹配 woman/women）

## 使用方法

### 方法一：使用高级爬虫（推荐）

```bash
# 1. 基础关键词搜索（自动优化）
python newsbank_advanced.py "treasury wine estates"

# 2. 使用预设模板（高精准）
python newsbank_advanced.py "template:treasury_mergers"
python newsbank_advanced.py "template:treasury_strategy"
python newsbank_advanced.py "template:treasury_financial"

# 3. 仅生成搜索URL（调试使用）
python newsbank_advanced.py "treasury wine" --show-url

# 4. 指定页数和下载数量
python newsbank_advanced.py "penfolds" --max-pages 5 --max-full-articles 30

# 5. 无头模式（已登录后使用）
python newsbank_advanced.py "template:treasury_mergers" --headless
```

### 方法二：更新现有爬虫

现有的 `newsbank_smart.py` 也已集成高级搜索功能：

```bash
# 使用模板
python newsbank_smart.py "template:treasury_mergers"

# 普通关键词（自动优化）
python newsbank_smart.py "treasury wine estates"
```

## 预设搜索模板

### 1. Treasury Wine 并购主题 (`treasury_mergers`)

**搜索策略：**
- 全文必须包含: "treasury wine estates"
- 标题必须包含: penfold* OR "wolf blass" OR "treasury wine"
- 全文包含并购词汇: acquisition OR merger OR takeover OR "bought" OR "purchased" OR deal
- 排除: advertisement, sponsored

**适用场景：**
- 查找并购、收购相关新闻
- 投资交易报道
- 公司重组新闻

### 2. Treasury Wine 战略主题 (`treasury_strategy`)

**搜索策略：**
- 标题包含核心品牌: penfold* OR grange OR "bin 389" OR "wolf blass"
- 首段包含公司名: treasury OR "wine estates" OR TWE
- 全文包含战略词汇: strategy OR brand OR marketing OR expansion OR export OR premium

**适用场景：**
- 品牌战略报道
- 市场扩张新闻
- 营销活动报道

### 3. Treasury Wine 财务主题 (`treasury_financial`)

**搜索策略：**
- 标题包含: treasury wine* OR TWE
- 首段包含: treasury OR TWE
- 全文包含财务词汇: earnings OR profit OR revenue OR "annual report" OR ASX OR financial

**适用场景：**
- 财报发布
- 业绩分析
- 股价相关新闻

## 高级自定义搜索

### 示例1: 精确标题搜索

```python
from newsbank_search_builder import AdvancedSearchQuery, SearchField, BooleanOperator

# 创建查询
query = AdvancedSearchQuery()

# 标题必须包含 penfolds 或 penfold
query.add_title_keyword("penfold*")

# AND 全文包含 treasury
query.add_condition("treasury", SearchField.ALL_TEXT, BooleanOperator.AND)

# AND 全文包含 merger 或 acquisition
query.add_condition("merger OR acquisition", SearchField.ALL_TEXT, BooleanOperator.AND)

# 生成URL
url = query.build_url()
print(url)
```

### 示例2: 排除特定内容

```python
query = AdvancedSearchQuery()

# 搜索关键词
query.add_keyword("treasury wine")

# 排除广告
query.exclude_keyword("advertisement", SearchField.TITLE)

# 排除赞助内容
query.exclude_keyword("sponsored", SearchField.TITLE)

# 排除葡萄酒评分/评论
query.exclude_keyword("wine review", SearchField.ALL_TEXT)
```

### 示例3: 词形变化处理

```python
query = AdvancedSearchQuery()

# 处理同一词的不同形式
query.add_variations(
    base_word="penfold",
    variations=["penfolds", "penfold", "penfold's", "Penfolds"],
    field=SearchField.TITLE
)

# AND 其他条件
query.add_condition("wine", SearchField.ALL_TEXT, BooleanOperator.AND)
```

### 示例4: 短语精确匹配

```python
query = AdvancedSearchQuery()

# 精确短语（自动加引号）
query.add_phrase("treasury wine estates", SearchField.TITLE)

# AND 另一个短语
query.add_phrase("wolf blass", SearchField.ALL_TEXT, BooleanOperator.AND)
```

## 搜索优化策略对比

### 优化前（基础搜索）
```
URL: ?p=AWGLNB&fld-base-0=alltext&val-base-0=treasury wine estates

问题：
- 只搜索全文
- 返回大量不相关结果
- 噪音高
```

### 优化后（高级搜索）
```
URL: ?p=AWGLNB&f=advanced
  &val-base-0="treasury wine estates"&fld-base-0=Title
  &bln-base-1=and&val-base-1=penfold*&fld-base-1=Title
  &bln-base-2=and&val-base-2=merger OR acquisition&fld-base-2=alltext

优势：
- 标题必须包含核心词（提高相关性）
- 通配符匹配变体（提高召回率）
- 布尔逻辑组合（精确控制）
- 排除广告内容（减少噪音）
```

## 命令行参数说明

### newsbank_advanced.py

```bash
python newsbank_advanced.py [keyword] [options]

位置参数:
  keyword               搜索关键词或模板名称

可选参数:
  --all-pages          扫描所有可用页数（谨慎使用）
  --max-pages N        最大扫描页数（默认: 10）
  --start-page N       从第N页开始（默认: 1）
  --end-page N         到第N页结束（0=自动检测）
  --min-preview-words N 预览文本最小词数（默认: 30）
  --max-full-articles N 下载全文的最大文章数（默认: 20）
  --headless           无头模式（不显示浏览器）
  --show-url           仅显示生成的URL，不执行爬取
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `newsbank_search_builder.py` | 高级搜索查询构建器核心模块 |
| `newsbank_advanced.py` | 集成高级搜索的完整爬虫 |
| `newsbank_smart.py` | 已更新支持高级搜索的原爬虫 |
| `articles_advanced/` | 高级爬虫输出目录 |

## 最佳实践

1. **先使用 `--show-url` 测试搜索策略**
   ```bash
   python newsbank_advanced.py "your keyword" --show-url
   ```

2. **从预设模板开始**
   - 模板已针对特定主题优化
   - 可根据需要修改模板

3. **逐步精确化**
   - 开始先用宽泛条件
   - 根据结果逐步添加限制条件
   - 使用 NOT 排除噪音

4. **合理设置页数**
   - 精准搜索通常前几页就足够
   - 过多页数可能遇到反爬限制

5. **利用预览筛选**
   - 调整 `--min-preview-words` 控制文章质量
   - 太低的阈值可能包含无关内容

## 故障排除

### 搜索结果为空
- 检查关键词拼写
- 尝试使用通配符（如 `penfold*`）
- 减少条件数量，放宽搜索

### 结果太多不相关
- 使用 Title 字段提高相关性
- 添加更多 AND 条件
- 使用 NOT 排除噪音词

### URL生成错误
- 检查 Python 版本（需要 3.7+）
- 确保安装了依赖: `pip install playwright`

## 技术细节

### URL参数结构
```
https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/results?
  p=AWGLNB                              # 产品ID
  &hide_duplicates=2                    # 去重级别
  &maxresults=60                        # 每页结果数
  &f=advanced                           # 高级搜索模式
  &sort=YMD_date%3AD                   # 排序方式
  &t=favorite%3A...                    # 来源筛选
  &val-base-0=...&fld-base-0=...       # 条件0
  &bln-base-1=...&val-base-1=...       # 条件1
  ...
```

### 布尔逻辑URL编码
- AND → `and`
- OR → `or`
- NOT → `not`
- 空格 → `%20`
- 引号 → `%22`

---

**提示**: 所有现有爬虫功能保持不变，高级搜索是新增的可选功能。您可以根据需要选择使用基础搜索或高级搜索。
