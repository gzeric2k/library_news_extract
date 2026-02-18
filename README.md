# NewsBank Scraper - 使用说明

## 功能概述

这个工具可以自动从NewsBank的Australian Financial Review Collection搜索并保存文章。

提供两种下载模式：
1. **`newsbank_scraper.py`** - 传统抓取模式：通过浏览器渲染页面，逐个访问文章URL获取内容
2. **`newsbank_api_downloader.py`** - API模式：直接调用NewsBank API批量获取多篇文章完整内容（推荐）

## 工作流程

1. 访问NewsBank登录页面
2. 自动检测并等待手动登录（首次）
3. 保存登录状态（cookies）供后续使用
4. 搜索指定关键词
5. 抓取搜索结果（支持翻页）
6. 只保存有预览文本的文章
7. 自动清理非文章内容

## 文件说明

| 文件 | 说明 |
|------|------|
| `newsbank_scraper.py` | 传统抓取脚本（逐个访问文章） |
| `newsbank_api_downloader.py` | API下载器（批量获取，推荐） |
| `cleanup_articles.py` | 清理非文章文件 |
| `cookies/newsbank_auth.json` | 登录状态文件 |
| `articles/` | 传统模式保存的文章目录 |
| `articles_api/` | API模式保存的文章目录 |

## 使用方法

### 方式一：API模式（推荐）

API模式直接调用NewsBank接口，批量获取多篇文章完整内容，速度更快。

#### 1. 首次运行（需要手动登录）

```bash
python newsbank_api_downloader.py "Nick Scali"
```

**注意：**
- 会打开浏览器窗口
- 请在浏览器中完成登录流程：
  1. 点击 "Log in as a Library member"
  2. 输入您的图书馆会员信息
  3. 脚本会自动检测登录成功
- 登录状态会自动保存到 `cookies/newsbank_auth.json`

#### 2. 后续运行（自动登录）

```bash
# 使用搜索关键字
python newsbank_api_downloader.py "treasury wine penfolds"

# 指定最大结果数
python newsbank_api_downloader.py "treasury wine" --max-results 200

# 指定年份范围
python newsbank_api_downloader.py "treasury wine" --year-from 2014 --year-to 2020

# 指定数据源
python newsbank_api_downloader.py "treasury wine" --source "Australian Financial Review Collection"

# 无头模式（仅当已登录过）
python newsbank_api_downloader.py "treasury wine" --headless
```

#### 3. 使用完整URL

也可以直接使用NewsBank搜索结果页面的URL：

```bash
python newsbank_api_downloader.py "https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/results?p=AWGLNB&hide_duplicates=2&fld-base-0=alltext&sort=YMD_date%3AD&maxresults=200&val-base-0=treasury%20wine%20penfolds&t=favorite%3AAFRWAFRN%21Australian%2520Financial%2520Review%2520Collection/year%3A2014%212014"
```

#### 4. 两阶段模式（先提取元数据，后选择下载）

两阶段模式允许您：
1. 先提取所有文章的元数据（标题、预览等）
2. 查看元数据后选择要下载的文章
3. 在同一浏览器会话中下载选中的文章

```bash
# 阶段1：仅提取元数据
python newsbank_api_downloader.py "treasury wine" --metadata-only

# 脚本会：
# - 扫描所有搜索结果页面
# - 提取每篇文章的元数据
# - 保存到 JSON 文件
# - 询问是否立即选择下载

# 如果选择稍后下载，可以使用 --from-metadata 参数
python newsbank_api_downloader.py --from-metadata "articles_api/article_xxx.json"
```

#### 5. LLM智能筛选

使用AI筛选与搜索关键字相关的文章：

```bash
# 从元数据文件进行LLM筛选
python newsbank_api_downloader.py --filter-from "articles_api/article_xxx.json"

# 指定相关性阈值 (0-1，越高越严格)
python newsbank_api_downloader.py --filter-from "articles_api/article_xxx.json" --threshold 0.7

# 指定模型
python newsbank_api_downloader.py --filter-from "articles_api/article_xxx.json" --llm-model "z-ai/glm4.7"

# 筛选后下载
python newsbank_api_downloader.py --from-metadata "articles_api/article_treasury_wine_filtered_xxx.json"
```

**环境变量：**
- `NVIDIA_API_KEY` 或 `OPENAI_API_KEY` - API密钥
- `LLM_FILTER_ENABLED=true` - 启用自动LLM筛选
- `LLM_FILTER_THRESHOLD=0.5` - 筛选阈值

### 方式二：传统模式

传统模式逐个访问文章页面获取内容。

```bash
python newsbank_scraper.py "Nick Scali"

# 指定抓取页数
python newsbank_scraper.py "Nick Scali" --max-pages 5

# 无头模式
python newsbank_scraper.py "Nick Scali" --headless
```

### 清理非文章文件

```bash
python cleanup_articles.py
```

## 命令行参数

### newsbank_api_downloader.py（API模式）

```
usage: newsbank_api_downloader.py [-h] [--max-results MAX_RESULTS] [--max-pages MAX_PAGES]
                                  [--year-from YEAR_FROM] [--year-to YEAR_TO]
                                  [--source SOURCE] [--headless]
                                  [--output-dir OUTPUT_DIR]
                                  [--metadata-only] [--from-metadata FROM_METADATA]
                                  [--max-download MAX_DOWNLOAD] [--filter-llm]
                                  [--filter-from FILTER_FROM] [--api-key API_KEY]
                                  [--llm-model LLM_MODEL] [--threshold THRESHOLD]
                                  [--batch-size BATCH_SIZE]
                                  keyword_or_url

positional arguments:
  keyword_or_url        搜索关键字或NewsBank搜索URL (LLM筛选模式时可选)

optional arguments:
  -h, --help            show this help message exit
  --max-results         最大结果数 (默认: 200)
  --max-pages           最大扫描页数 (默认: 10)
  --year-from           起始年份 (例如: 2014)
  --year-to             结束年份 (例如: 2020)
  --source              数据源名称 (默认: Australian Financial Review Collection)
  --headless            无头模式
  --output-dir          输出目录 (默认: articles_api)
  --metadata-only       仅提取文章元数据，不下载内容
  --from-metadata      从元数据JSON文件加载并选择下载
  --max-download       单次下载最大文章数 (默认: 20)
  --filter-llm         使用LLM筛选相关文章
  --filter-from        从已保存的JSON文件进行LLM筛选
  --api-key           LLM API密钥
  --llm-model         LLM模型名称 (默认: z-ai/glm4.7)
  --threshold         LLM相关性阈值 (0-1, 默认: 0.5)
  --batch-size        LLM每批次处理文章数 (默认: 10)
```

### newsbank_scraper.py（传统模式）

```
usage: newsbank_scraper.py [-h] [--max-pages MAX_PAGES] [--headless] keyword

positional arguments:
  keyword               Search keyword (e.g., 'Nick Scali')

optional arguments:
  -h, --help            show this help message exit
  --max-pages           Maximum number of pages to scrape (default: 10)
  --headless            Run in headless mode (requires prior login)
```

## 输出格式

每篇文章保存为单独的 `.txt` 文件：

```
Title: [文章标题]
Date: [发布日期]
Source: [来源]
Author: [作者]
URL: [原文链接]
Article ID: [文章ID]
Original Search URL: [搜索URL]
Downloaded at: [下载时间]
Page: [页码]
Word Count: [字数]

Preview:
[预览文本]

Full Text:
[完整文章内容]

======================================================================
```

## 两种模式对比

| 特性 | API模式 (newsbank_api_downloader.py) | 传统模式 (newsbank_scraper.py) |
|------|-------------------------------------|-------------------------------|
| 速度 | 快（批量获取） | 慢（逐个访问） |
| 获取方式 | NewsBank API | 页面渲染 |
| 适用场景 | 大量文章 | 少量文章/特殊页面 |
| 输出目录 | articles_api/ | articles/ |

**推荐**：优先使用API模式，效率更高。

### API模式子模式

| 子模式 | 命令 | 说明 |
|--------|------|------|
| 直接下载 | `python newsbank_api_downloader.py "关键字"` | 直接搜索并下载所有文章 |
| 两阶段模式 | `--metadata-only` → `--from-metadata` | 先提取元数据，后选择下载 |
| LLM筛选 | `--filter-from` | 使用AI筛选相关文章 |

## 注意事项

1. **首次登录必需**：首次运行必须在非headless模式下进行，以便完成手动登录
2. **登录有效期**：登录状态通常会保持一段时间，但如果遇到登录失效，请重新运行并登录
3. **网络要求**：确保网络可以访问NewsBank网站（通过代理）
4. **翻页限制**：默认最多抓取10页，可以通过 `--max-pages` 参数调整
5. **API模式**：成功获取文章后自动保存全部，失败则直接退出
6. **两阶段模式**：选择下载时会保持浏览器会话，确保登录状态有效
7. **LLM筛选**：需要设置 `NVIDIA_API_KEY` 或 `OPENAI_API_KEY` 环境变量
8. **流量控制**：程序会自动记录请求频率，接近限流阈值时发出警告

## 流量监控

程序内置流量监控功能，会自动：

- 记录每次 API/页面 请求
- 统计请求频率（每分钟/每秒）
- 检测限流风险并发出警告
- 生成流量报告和日志文件

### 流量报告示例

```
============================================================
📊 NewsBank 流量报告
============================================================
  会话时长: 120.5 秒
  总请求数: 45
    - API请求: 30
    - 页面请求: 15
  成功/失败: 43 / 2
  平均请求频率: 22.5 请求/分钟
  平均响应时间: 0.523 秒
  状态码分布:
    200: 40
    429: 2
  ⚠️  曾触发限流警告
  🚫 曾被阻止访问
============================================================
```

### 限流警告

当请求频率过高时，程序会显示警告：

- **⚠️ 流量警告**：最近1分钟请求数接近阈值
- **🚫 限流警告**：检测到 429 状态码（请求被阻止）

### 日志文件

流量日志会自动保存到 `articles_api/traffic_log_*.json`，包含：
- 每个请求的详细信息（时间、URL、状态码、响应时间）
- 会话统计信息
- 成功/失败计数

## 常见问题

### Q: 需要哪些依赖？
```bash
pip install playwright
playwright install chromium
```

### Q: 如何切换到自动登录模式？
如果你希望完全自动登录（不手动操作），需要：
1. 知道登录表单的具体字段名
2. 在脚本中添加自动填写用户名/密码的逻辑
3. **注意**：这需要在代码中存储凭证，有安全风险

### Q: 为什么有些文章没有保存？
根据原始需求，脚本只保存有预览文本的文章。如果文章没有预览文本（只有标题），则会被跳过。

### Q: API模式和传统模式有什么区别？
- API模式：直接调用NewsBank的批量下载接口，一次性获取多篇文章完整内容，速度快
- 传统模式：通过浏览器渲染页面，逐个访问每个文章URL获取内容，速度慢但更稳定

### Q: 输入关键字和URL有什么区别？
- 关键字：脚本会自动构建搜索URL（包含年份、结果数等参数）
- URL：直接使用你提供的搜索结果页URL

### Q: 两阶段模式是什么？
两阶段模式允许您分两步下载文章：
1. **阶段1（--metadata-only）**：仅提取文章元数据（标题、预览、大小等），保存到JSON文件
2. **阶段2（--from-metadata）**：从JSON文件加载元数据，选择要下载的文章，然后下载

**优点**：
- 可以先查看文章列表，决定要下载哪些
- 不需要一次下载所有文章
- 选择下载时保持浏览器会话，避免登录问题

### Q: LLM筛选是什么？
LLM筛选使用AI判断每篇文章与搜索关键字的相关性，自动过滤掉不相关的文章。

**使用方式**：
```bash
# 筛选元数据文件
python newsbank_api_downloader.py --filter-from "article_xxx.json"

# 筛选后下载
python newsbank_api_downloader.py --from-metadata "article_xxx_filtered.json"
```

**注意事项**：
- 需要设置 `NVIDIA_API_KEY` 或 `OPENAI_API_KEY` 环境变量
- 推荐使用 NVIDIA API（支持免费的 z-ai/glm4.7 模型）
- 阈值越高筛选越严格（0.5为默认值）

## 技术细节

- **浏览器自动化**: Playwright
- **登录状态**: 使用 `context.storage_state()` 保存cookies
- **页面检测**: 自动检测多种可能的元素选择器
- **API调用**: 直接调用 NewsBank nb-multidocs/get 接口
- **HTML解析**: 使用正则表达式从API响应中提取文章内容

## 更新日志

### 2026-02-17
- 新增两阶段工作流：`--metadata-only` + `--from-metadata`
  - 阶段1：仅提取文章元数据，保存到JSON
  - 阶段2：选择文章后在同一浏览器会话中下载
  - 修复：选择下载时保持浏览器会话，避免登录状态丢失
- 新增LLM智能筛选功能
  - 支持使用AI判断文章与关键字的相关性
  - 可调节相关性阈值
  - 支持批量处理
- 新增流量监控功能
  - 记录所有API和页面请求
  - 实时检测限流风险
  - 自动生成流量报告和日志文件
  - 接近限流阈值时发出警告

### 2026-02-15
- 新增 `newsbank_api_downloader.py` - API批量下载模式
- 支持搜索关键字自动构建URL
- 支持年份范围、数据源、结果数等参数
- API成功自动保存全部，失败直接退出
- 修复文章解析问题

### 2026-02-14
- 初始版本发布
- 支持手动登录和自动登录状态保存
- 支持翻页抓取
- 自动清理非文章内容
