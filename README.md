# NewsBank Scraper - 使用说明

## 功能概述

这个工具可以自动从NewsBank的Australian Financial Review Collection搜索并保存文章。

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
| `newsbank_scraper.py` | 主抓取脚本 |
| `cleanup_articles.py` | 清理非文章文件 |
| `cookies/newsbank_auth.json` | 登录状态文件 |
| `articles/` | 保存的文章目录 |

## 使用方法

### 1. 首次运行（需要手动登录）

```bash
python newsbank_scraper.py "Nick Scali"
```

**注意：**
- 会打开浏览器窗口
- 请在浏览器中完成登录流程：
  1. 点击 "Log in as a Library member"
  2. 输入您的图书馆会员信息
  3. 脚本会自动检测登录成功
- 登录状态会自动保存到 `cookies/newsbank_auth.json`

### 2. 后续运行（自动登录）

```bash
# 使用已保存的登录状态自动登录
python newsbank_scraper.py "Your Keyword"

# 指定抓取页数
python newsbank_scraper.py "Your Keyword" --max-pages 5

# 无头模式（仅当已登录过）
python newsbank_scraper.py "Your Keyword" --headless
```

### 3. 清理非文章文件

```bash
python cleanup_articles.py
```

## 命令行参数

```
usage: newsbank_scraper.py [-h] [--max-pages MAX_PAGES] [--headless] keyword

positional arguments:
  keyword               Search keyword (e.g., 'Nick Scali')

optional arguments:
  -h, --help            show this help message and exit
  --max-pages MAX_PAGES
                        Maximum number of pages to scrape (default: 10)
  --headless            Run in headless mode (requires prior login)
```

## 输出格式

每篇文章保存为单独的 `.txt` 文件：

```
Title: [文章标题]
Date: [发布日期]
Keyword: [搜索关键词]
Page: [页码]
Scraped at: [抓取时间]

Preview:
[预览文本]

============================================================
```

## 注意事项

1. **首次登录必需**：首次运行必须在非headless模式下进行，以便完成手动登录
2. **登录有效期**：登录状态通常会保持一段时间，但如果遇到登录失效，请重新运行并登录
3. **网络要求**：确保网络可以访问NewsBank网站（通过代理）
4. **翻页限制**：默认最多抓取10页，可以通过 `--max-pages` 参数调整

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

## 技术细节

- **浏览器自动化**: Playwright
- **登录状态**: 使用 `context.storage_state()` 保存cookies
- **页面检测**: 自动检测多种可能的元素选择器
- **错误处理**: 包含超时、重试等健壮性处理

## 更新日志

### 2026-02-14
- 初始版本发布
- 支持手动登录和自动登录状态保存
- 支持翻页抓取
- 自动清理非文章内容
