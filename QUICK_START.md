# NewsBank 抓取器 - 快速开始指南

## 📋 目录

1. [安装](#安装)
2. [配置](#配置)
3. [基础使用](#基础使用)
4. [高级特性](#高级特性)
5. [故障排除](#故障排除)

---

## 安装

### 1. 安装依赖

```bash
# 安装 Python 包
pip install -r requirements.txt

# 安装 Playwright 浏览器驱动
playwright install chromium
```

### 2. 验证安装

```bash
python -c "import playwright; print(f'Playwright {playwright.__version__} installed')"
python -c "import aiosqlite; print('aiosqlite installed')"
python -c "from pydantic_settings import BaseSettings; print('pydantic-settings installed')"
```

---

## 配置

### 1. 创建 .env 文件

```bash
# 复制示例配置
cp .env.example .env

# 编辑 .env 文件根据需要修改参数
```

### 2. 配置参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `SCRAPER_HEADLESS` | 无头模式（不显示浏览器窗口） | `true` |
| `SCRAPER_MAX_CONCURRENT_PAGES` | 最大并发页面数 | `5` |
| `SCRAPER_PAGE_TIMEOUT` | 页面加载超时时间（毫秒） | `30000` |
| `SCRAPER_DATABASE_PATH` | SQLite 数据库文件路径 | `newsbank.db` |
| `SCRAPER_MAX_RETRIES` | 最大重试次数 | `3` |
| `SCRAPER_LOG_LEVEL` | 日志级别 | `INFO` |

### 3. 环境变量优先级

配置加载顺序（优先级从高到低）：
1. 环境变量（`SCRAPER_*` 前缀）
2. `.env` 文件
3. 代码中的默认值

---

## 基础使用

### 1. 简单的抓取示例

```python
import asyncio
from advanced_scraper_example import NewsBankScraper, ScraperSettings

async def main():
    # 加载配置
    settings = ScraperSettings()
    
    # 创建抓取器
    scraper = NewsBankScraper(settings)
    await scraper.initialize()
    
    # 抓取 URL
    urls = [
        "https://example.com/news/1",
        "https://example.com/news/2",
    ]
    
    result = await scraper.scrape_and_store(urls)
    print(f"Result: {result}")

if __name__ == "__main__":
    asyncio.run(main())
```

### 2. 从文件读取 URL

```python
import asyncio
from advanced_scraper_example import NewsBankScraper, ScraperSettings

async def main():
    settings = ScraperSettings()
    scraper = NewsBankScraper(settings)
    await scraper.initialize()
    
    # 从文件读取 URL
    with open("urls.txt", "r") as f:
        urls = [line.strip() for line in f if line.strip()]
    
    result = await scraper.scrape_and_store(urls)
    print(f"Scraped {result['successful']} articles")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 高级特性

### 1. 自定义重试策略

```python
from tenacity import retry, stop_after_attempt, wait_exponential
from playwright.async_api import async_playwright

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, max=30)
)
async def scrape_with_custom_retry(url: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            return await page.content()
        finally:
            await page.close()
            await browser.close()
```

### 2. 数据库查询

```python
import asyncio
from advanced_scraper_example import ConcurrentSQLiteManager

async def main():
    db = ConcurrentSQLiteManager("newsbank.db")
    
    # 获取单个文章
    article = await db.get_article(1)
    print(f"Article: {article}")
    
    # 获取所有文章
    async with db.get_connection() as conn:
        conn.row_factory = __import__('aiosqlite').Row
        cursor = await conn.execute("SELECT * FROM articles LIMIT 10")
        rows = await cursor.fetchall()
        for row in rows:
            print(dict(row))

if __name__ == "__main__":
    asyncio.run(main())
```

### 3. 并发控制

```python
import asyncio
from advanced_scraper_example import PlaywrightConcurrentScraper

async def main():
    # 创建抓取器，最多 10 个并发页面
    scraper = PlaywrightConcurrentScraper(
        max_pages=10,
        headless=True,
        timeout=30000
    )
    
    urls = [f"https://example.com/page/{i}" for i in range(100)]
    results = await scraper.scrape_multiple_pages(urls)
    
    successful = sum(1 for r in results if r['status'] == 'success')
    print(f"Scraped {successful}/{len(urls)} pages")

if __name__ == "__main__":
    asyncio.run(main())
```

### 4. 错误处理和日志

```python
import logging
import asyncio
from advanced_scraper_example import NewsBankScraper, ScraperSettings

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler()
    ]
)

async def main():
    try:
        settings = ScraperSettings()
        scraper = NewsBankScraper(settings)
        await scraper.initialize()
        
        urls = ["https://example.com/news/1"]
        result = await scraper.scrape_and_store(urls)
        
    except Exception as e:
        logging.error(f"Scraping failed: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 故障排除

### 问题 1: Playwright 浏览器驱动未安装

**症状**: `PlaywrightError: Executable doesn't exist`

**解决方案**:
```bash
playwright install chromium
# 或安装所有浏览器
playwright install
```

### 问题 2: 数据库被锁定

**症状**: `sqlite3.OperationalError: database is locked`

**解决方案**:
- 确保启用了 WAL 模式（代码已包含）
- 减少并发连接数
- 检查是否有其他进程访问数据库

```python
# 在 ScraperSettings 中调整
SCRAPER_MAX_DB_CONNECTIONS=3  # 减少并发连接
```

### 问题 3: 页面加载超时

**症状**: `TimeoutError: Timeout 30000ms exceeded`

**解决方案**:
```python
# 增加超时时间
settings = ScraperSettings()
settings.page_timeout = 60000  # 60 秒

# 或在 .env 中设置
SCRAPER_PAGE_TIMEOUT=60000
```

### 问题 4: 内存占用过高

**症状**: 抓取过程中内存持续增长

**解决方案**:
```python
# 减少并发页面数
SCRAPER_MAX_CONCURRENT_PAGES=3

# 定期清理浏览器缓存
async def scrape_with_cleanup(urls):
    for batch in chunks(urls, 10):  # 每 10 个 URL 重启浏览器
        results = await scraper.scrape_multiple_pages(batch)
        # 处理结果
```

### 问题 5: 网站反爬虫

**症状**: 403 Forbidden 或被重定向

**解决方案**:
```python
# 使用代理
SCRAPER_USE_PROXY=true
SCRAPER_PROXY_URL=http://proxy.example.com:8080

# 添加延迟
import asyncio
for url in urls:
    await scraper.scrape_and_store([url])
    await asyncio.sleep(2)  # 每个请求间隔 2 秒
```

---

## 性能优化建议

### 1. 数据库优化

```python
# 启用 WAL 模式（已在代码中启用）
PRAGMA journal_mode=WAL;

# 调整缓存大小
PRAGMA cache_size=10000;

# 使用批量插入而不是逐条插入
await db.batch_insert_articles(articles)
```

### 2. Playwright 优化

```python
# 禁用图片加载加快速度
page = await browser.new_page()
await page.route("**/*.{png,jpg,jpeg,gif,svg}", lambda route: route.abort())

# 使用 CDP 模式（更快）
browser = await p.chromium.connect_over_cdp(remote_debugging_url)
```

### 3. 并发优化

```python
# 根据 CPU 核心数调整并发数
import multiprocessing
optimal_pages = multiprocessing.cpu_count() * 2
```

---

## 监控和日志

### 查看日志

```bash
# 实时查看日志
tail -f scraper.log

# 查看错误日志
grep ERROR scraper.log

# 统计抓取结果
grep "Batch inserted" scraper.log
```

### 数据库统计

```python
import asyncio
from advanced_scraper_example import ConcurrentSQLiteManager

async def stats():
    db = ConcurrentSQLiteManager("newsbank.db")
    
    async with db.get_connection() as conn:
        # 总文章数
        cursor = await conn.execute("SELECT COUNT(*) FROM articles")
        total = (await cursor.fetchone())[0]
        
        # 按来源统计
        cursor = await conn.execute(
            "SELECT source, COUNT(*) FROM articles GROUP BY source"
        )
        sources = await cursor.fetchall()
        
        print(f"Total articles: {total}")
        for source, count in sources:
            print(f"  {source}: {count}")

asyncio.run(stats())
```

---

## 下一步

- 查看 `PLAYWRIGHT_PATTERNS.md` 了解更多高级模式
- 查看 `advanced_scraper_example.py` 的完整源代码
- 根据需要自定义抓取逻辑
