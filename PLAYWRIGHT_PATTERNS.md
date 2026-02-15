# Playwright 高级自动化模式与最佳实践

## 1. 错误重试与指数退避策略

### 1.1 使用 Tenacity 库的重试装饰器

```python
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    wait_fixed,
    retry_if_not_exception_type,
    RetryError
)
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

# 模式 1: 基础指数退避
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, max=10)
)
def fetch_with_exponential_backoff(url: str) -> Dict[str, Any]:
    """
    使用指数退避重试的网络请求
    - 第1次: 立即重试
    - 第2次: 等待 2^1 * 1 = 2 秒
    - 第3次: 等待 2^2 * 1 = 4 秒
    - 第4次: 等待 2^3 * 1 = 8 秒
    - 第5次: 等待 2^4 * 1 = 16 秒 (但 max=10，所以是 10 秒)
    """
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()


# 模式 2: 固定等待时间
@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(1)
)
async def async_fetch_with_fixed_wait(url: str) -> str:
    """每次重试等待 1 秒"""
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=10) as resp:
            return await resp.text()


# 模式 3: 选择性重试（排除特定异常）
@retry(
    stop=stop_after_attempt(6),
    wait=wait_fixed(10),
    retry=retry_if_not_exception_type((ValueError, KeyError))
)
def selective_retry_fetch(url: str) -> Dict[str, Any]:
    """
    不重试 ValueError 和 KeyError，其他异常重试
    适用于：业务逻辑错误不需要重试，网络错误需要重试
    """
    response = requests.get(url)
    if response.status_code == 404:
        raise ValueError("Resource not found")
    return response.json()


# 模式 4: 异步重试包装
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=1, max=10)
)
async def async_operation_with_retry() -> str:
    """异步操作的重试"""
    # 模拟异步操作
    await asyncio.sleep(0.1)
    return "success"
```

### 1.2 Playwright 中的重试模式

```python
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from tenacity import retry, stop_after_attempt, wait_exponential
import asyncio

class PlaywrightScraper:
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=10)
    )
    async def navigate_with_retry(self, page, url: str, timeout: int = 30000):
        """
        带重试的页面导航
        """
        try:
            await page.goto(url, wait_until="networkidle", timeout=timeout)
            return True
        except PlaywrightTimeout as e:
            logger.warning(f"Navigation timeout for {url}: {e}")
            raise
        except Exception as e:
            logger.error(f"Navigation failed for {url}: {e}")
            raise
    
    async def scrape_with_retry(self, url: str) -> Optional[str]:
        """
        完整的重试流程
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            try:
                await self.navigate_with_retry(page, url)
                content = await page.content()
                return content
            except Exception as e:
                logger.error(f"Failed to scrape {url} after retries: {e}")
                return None
            finally:
                await page.close()
                await browser.close()
```

---

## 2. SQLite 异步操作最佳实践

### 2.1 基础异步 SQLite 连接

```python
import aiosqlite
import sqlite3
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager
import logging

logger = logging.getLogger(__name__)

class AsyncSQLiteManager:
    def __init__(self, db_path: str = "data.db"):
        self.db_path = db_path
    
    @asynccontextmanager
    async def get_connection(self):
        """
        获取异步数据库连接的上下文管理器
        """
        conn = await aiosqlite.connect(self.db_path)
        try:
            # 启用 WAL 模式提升并发性能
            await conn.execute("PRAGMA journal_mode=WAL")
            # 启用外键约束
            await conn.execute("PRAGMA foreign_keys=ON")
            yield conn
        finally:
            await conn.close()
    
    async def init_db(self):
        """初始化数据库表"""
        async with self.get_connection() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    url TEXT UNIQUE NOT NULL,
                    content TEXT,
                    source TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS scrape_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id INTEGER,
                    status TEXT,
                    error_message TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (article_id) REFERENCES articles(id)
                )
            """)
            
            await conn.commit()
            logger.info("Database initialized successfully")
    
    async def insert_article(self, title: str, url: str, content: str, source: str) -> int:
        """
        插入文章记录
        返回插入的行 ID
        """
        async with self.get_connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO articles (title, url, content, source)
                VALUES (?, ?, ?, ?)
                """,
                (title, url, content, source)
            )
            await conn.commit()
            return cursor.lastrowid
    
    async def batch_insert_articles(self, articles: List[Dict[str, str]]) -> List[int]:
        """
        批量插入文章（性能优化）
        """
        async with self.get_connection() as conn:
            cursor = await conn.cursor()
            
            # 使用事务提升性能
            await cursor.execute("BEGIN TRANSACTION")
            
            inserted_ids = []
            try:
                for article in articles:
                    await cursor.execute(
                        """
                        INSERT INTO articles (title, url, content, source)
                        VALUES (?, ?, ?, ?)
                        """,
                        (article['title'], article['url'], article['content'], article['source'])
                    )
                    inserted_ids.append(cursor.lastrowid)
                
                await conn.commit()
                logger.info(f"Batch inserted {len(inserted_ids)} articles")
                return inserted_ids
            except sqlite3.IntegrityError as e:
                await conn.rollback()
                logger.error(f"Batch insert failed: {e}")
                raise
    
    async def get_article(self, article_id: int) -> Optional[Dict[str, Any]]:
        """获取单个文章"""
        async with self.get_connection() as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                "SELECT * FROM articles WHERE id = ?",
                (article_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    async def get_articles_by_source(self, source: str) -> List[Dict[str, Any]]:
        """按来源获取文章"""
        async with self.get_connection() as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                "SELECT * FROM articles WHERE source = ? ORDER BY created_at DESC",
                (source,)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def log_scrape_result(self, article_id: int, status: str, error_message: Optional[str] = None):
        """记录抓取结果"""
        async with self.get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO scrape_logs (article_id, status, error_message)
                VALUES (?, ?, ?)
                """,
                (article_id, status, error_message)
            )
            await conn.commit()
```

### 2.2 高级并发操作

```python
import asyncio
from typing import Coroutine

class ConcurrentSQLiteManager(AsyncSQLiteManager):
    def __init__(self, db_path: str = "data.db", max_concurrent: int = 5):
        super().__init__(db_path)
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
    
    async def _execute_with_semaphore(self, coro: Coroutine):
        """
        使用信号量限制并发数
        """
        async with self.semaphore:
            return await coro
    
    async def batch_insert_with_concurrency(self, articles: List[Dict[str, str]]):
        """
        并发插入多个文章
        """
        tasks = [
            self._execute_with_semaphore(
                self.insert_article(
                    article['title'],
                    article['url'],
                    article['content'],
                    article['source']
                )
            )
            for article in articles
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常
        successful = [r for r in results if not isinstance(r, Exception)]
        failed = [r for r in results if isinstance(r, Exception)]
        
        logger.info(f"Inserted {len(successful)} articles, {len(failed)} failed")
        return successful, failed
    
    async def concurrent_scrape_and_store(self, urls: List[str], scraper_func):
        """
        并发抓取和存储
        """
        async def scrape_and_store(url: str):
            try:
                content = await scraper_func(url)
                article_id = await self.insert_article(
                    title=url.split('/')[-1],
                    url=url,
                    content=content,
                    source="newsbank"
                )
                await self.log_scrape_result(article_id, "success")
                return article_id
            except Exception as e:
                logger.error(f"Failed to scrape {url}: {e}")
                await self.log_scrape_result(None, "failed", str(e))
                raise
        
        tasks = [
            self._execute_with_semaphore(scrape_and_store(url))
            for url in urls
        ]
        
        return await asyncio.gather(*tasks, return_exceptions=True)
```

---

## 3. Playwright 并发/多页面抓取模式

### 3.1 基础多页面并发

```python
from playwright.async_api import async_playwright, Browser, Page
from typing import List, Callable, Any
import asyncio

class PlaywrightConcurrentScraper:
    def __init__(self, max_pages: int = 5, headless: bool = True):
        self.max_pages = max_pages
        self.headless = headless
        self.semaphore = asyncio.Semaphore(max_pages)
    
    async def scrape_single_page(self, browser: Browser, url: str) -> str:
        """
        抓取单个页面
        """
        async with self.semaphore:
            page = await browser.new_page()
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                content = await page.content()
                return content
            except Exception as e:
                logger.error(f"Failed to scrape {url}: {e}")
                raise
            finally:
                await page.close()
    
    async def scrape_multiple_pages(self, urls: List[str]) -> List[str]:
        """
        并发抓取多个页面
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            
            try:
                tasks = [
                    self.scrape_single_page(browser, url)
                    for url in urls
                ]
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                return results
            finally:
                await browser.close()
    
    async def scrape_with_context(self, urls: List[str]) -> List[str]:
        """
        使用浏览器上下文（推荐）
        - 每个上下文有独立的 cookies、storage 等
        - 更好的隔离性
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            
            try:
                # 创建多个上下文
                contexts = [
                    await browser.new_context()
                    for _ in range(min(self.max_pages, len(urls)))
                ]
                
                async def scrape_in_context(context, url: str):
                    page = await context.new_page()
                    try:
                        await page.goto(url, wait_until="networkidle", timeout=30000)
                        return await page.content()
                    finally:
                        await page.close()
                
                # 分配 URL 到上下文
                tasks = []
                for i, url in enumerate(urls):
                    context = contexts[i % len(contexts)]
                    tasks.append(scrape_in_context(context, url))
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # 清理上下文
                for context in contexts:
                    await context.close()
                
                return results
            finally:
                await browser.close()
```

### 3.2 高级并发模式

```python
class AdvancedPlaywrightScraper:
    def __init__(self, max_concurrent: int = 5, timeout: int = 30000):
        self.max_concurrent = max_concurrent
        self.timeout = timeout
        self.semaphore = asyncio.Semaphore(max_concurrent)
    
    async def scrape_with_semaphore(self, browser: Browser, url: str) -> dict:
        """
        使用信号量控制并发
        """
        async with self.semaphore:
            page = await browser.new_page()
            try:
                await page.goto(url, wait_until="networkidle", timeout=self.timeout)
                
                # 提取数据
                title = await page.title()
                content = await page.content()
                
                return {
                    "url": url,
                    "title": title,
                    "content": content,
                    "status": "success"
                }
            except Exception as e:
                logger.error(f"Scrape failed for {url}: {e}")
                return {
                    "url": url,
                    "status": "failed",
                    "error": str(e)
                }
            finally:
                await page.close()
    
    async def scrape_batch(self, urls: List[str]) -> List[dict]:
        """
        批量抓取
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            
            try:
                tasks = [
                    self.scrape_with_semaphore(browser, url)
                    for url in urls
                ]
                
                results = await asyncio.gather(*tasks)
                return results
            finally:
                await browser.close()
    
    async def scrape_with_retry_and_semaphore(
        self,
        urls: List[str],
        max_retries: int = 3
    ) -> List[dict]:
        """
        带重试和并发控制的抓取
        """
        async def scrape_with_retry(browser: Browser, url: str):
            for attempt in range(max_retries):
                try:
                    return await self.scrape_with_semaphore(browser, url)
                except Exception as e:
                    if attempt == max_retries - 1:
                        logger.error(f"Failed after {max_retries} attempts: {url}")
                        return {
                            "url": url,
                            "status": "failed",
                            "error": str(e)
                        }
                    
                    wait_time = 2 ** attempt  # 指数退避
                    logger.warning(f"Retry {attempt + 1} for {url}, waiting {wait_time}s")
                    await asyncio.sleep(wait_time)
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            
            try:
                tasks = [
                    scrape_with_retry(browser, url)
                    for url in urls
                ]
                
                results = await asyncio.gather(*tasks)
                return results
            finally:
                await browser.close()
```

---

## 4. 配置管理（Pydantic Settings）

### 4.1 基础配置

```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import Optional, List
from pathlib import Path

class ScraperSettings(BaseSettings):
    """
    抓取器配置
    支持从 .env 文件、环境变量和代码默认值加载
    """
    
    # 基础配置
    app_name: str = "NewsBank Scraper"
    debug: bool = False
    
    # Playwright 配置
    headless: bool = True
    browser_type: str = "chromium"  # chromium, firefox, webkit
    max_concurrent_pages: int = 5
    page_timeout: int = 30000  # 毫秒
    
    # 数据库配置
    database_path: str = "data.db"
    max_db_connections: int = 5
    
    # 代理配置
    use_proxy: bool = False
    proxy_url: Optional[str] = None
    
    # 日志配置
    log_level: str = "INFO"
    log_file: Optional[str] = None
    
    # 重试配置
    max_retries: int = 3
    retry_wait_base: int = 1  # 秒
    
    # 请求配置
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    request_timeout: int = 10000  # 毫秒
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SCRAPER_",
        case_sensitive=False,
        extra="ignore"  # 忽略未定义的环境变量
    )
    
    @field_validator('max_concurrent_pages')
    @classmethod
    def validate_max_pages(cls, v):
        if v < 1 or v > 50:
            raise ValueError('max_concurrent_pages must be between 1 and 50')
        return v
    
    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v):
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'log_level must be one of {valid_levels}')
        return v.upper()


# 使用示例
settings = ScraperSettings()
print(f"Database: {settings.database_path}")
print(f"Max pages: {settings.max_concurrent_pages}")
```

### 4.2 YAML 配置文件支持

```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel
import yaml
from pathlib import Path
from typing import Optional, Dict, Any

class PlaywrightConfig(BaseModel):
    """Playwright 配置"""
    headless: bool = True
    timeout: int = 30000
    max_pages: int = 5

class DatabaseConfig(BaseModel):
    """数据库配置"""
    path: str = "data.db"
    max_connections: int = 5
    enable_wal: bool = True

class LoggingConfig(BaseModel):
    """日志配置"""
    level: str = "INFO"
    file: Optional[str] = None
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

class AdvancedScraperSettings(BaseSettings):
    """
    高级配置管理
    支持 YAML 文件加载
    """
    
    playwright: PlaywrightConfig = PlaywrightConfig()
    database: DatabaseConfig = DatabaseConfig()
    logging: LoggingConfig = LoggingConfig()
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    @classmethod
    def from_yaml(cls, yaml_path: str) -> 'AdvancedScraperSettings':
        """从 YAML 文件加载配置"""
        with open(yaml_path, 'r', encoding='utf-8') as f:
            config_dict = yaml.safe_load(f)
        
        return cls(**config_dict)
    
    def to_yaml(self, yaml_path: str):
        """保存配置到 YAML 文件"""
        config_dict = self.model_dump()
        with open(yaml_path, 'w', encoding='utf-8') as f:
            yaml.dump(config_dict, f, default_flow_style=False, allow_unicode=True)


# config.yaml 示例
"""
playwright:
  headless: true
  timeout: 30000
  max_pages: 5

database:
  path: data.db
  max_connections: 5
  enable_wal: true

logging:
  level: INFO
  file: scraper.log
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
"""

# 使用示例
settings = AdvancedScraperSettings.from_yaml("config.yaml")
```

### 4.3 环境变量配置

```python
# .env 文件示例
"""
SCRAPER_HEADLESS=true
SCRAPER_BROWSER_TYPE=chromium
SCRAPER_MAX_CONCURRENT_PAGES=5
SCRAPER_DATABASE_PATH=data.db
SCRAPER_LOG_LEVEL=INFO
SCRAPER_MAX_RETRIES=3
SCRAPER_USE_PROXY=false
"""

# 使用
import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

settings = ScraperSettings()
# 自动从环境变量读取 SCRAPER_* 前缀的变量
```

---

## 5. 完整集成示例

```python
import asyncio
import logging
from typing import List, Dict, Any
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class NewsBankScraper:
    """
    完整的 NewsBank 抓取器
    集成了重试、并发、数据库和配置管理
    """
    
    def __init__(self, settings: ScraperSettings):
        self.settings = settings
        self.db_manager = ConcurrentSQLiteManager(
            db_path=settings.database_path,
            max_concurrent=settings.max_db_connections
        )
        self.playwright_scraper = AdvancedPlaywrightScraper(
            max_concurrent=settings.max_concurrent_pages,
            timeout=settings.page_timeout
        )
    
    async def initialize(self):
        """初始化抓取器"""
        await self.db_manager.init_db()
        logger.info("Scraper initialized successfully")
    
    async def scrape_and_store(self, urls: List[str]) -> Dict[str, Any]:
        """
        抓取 URL 并存储到数据库
        """
        logger.info(f"Starting to scrape {len(urls)} URLs")
        
        # 并发抓取
        scrape_results = await self.playwright_scraper.scrape_batch(urls)
        
        # 存储到数据库
        articles = []
        for result in scrape_results:
            if result['status'] == 'success':
                articles.append({
                    'title': result.get('title', 'Unknown'),
                    'url': result['url'],
                    'content': result.get('content', ''),
                    'source': 'newsbank'
                })
        
        # 批量插入
        inserted_ids, failed = await self.db_manager.batch_insert_with_concurrency(articles)
        
        logger.info(f"Scraped {len(inserted_ids)} articles successfully, {len(failed)} failed")
        
        return {
            'total': len(urls),
            'successful': len(inserted_ids),
            'failed': len(failed),
            'timestamp': datetime.now().isoformat()
        }


# 使用示例
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
        "https://example.com/news/3",
    ]
    
    result = await scraper.scrape_and_store(urls)
    print(f"Scraping result: {result}")


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 总结

### 关键最佳实践

1. **错误重试**
   - 使用 Tenacity 库的 `@retry` 装饰器
   - 实现指数退避策略避免服务器过载
   - 选择性重试（排除业务逻辑错误）

2. **SQLite 异步操作**
   - 使用 `aiosqlite` 进行异步数据库操作
   - 启用 WAL 模式提升并发性能
   - 使用事务批量插入提升性能
   - 使用信号量限制并发连接数

3. **Playwright 并发**
   - 使用 `asyncio.Semaphore` 限制并发页面数
   - 使用浏览器上下文隔离会话
   - 实现重试机制处理网络错误

4. **配置管理**
   - 使用 Pydantic Settings 管理配置
   - 支持 .env 文件、YAML 和环境变量
   - 添加字段验证确保配置有效性

5. **性能优化**
   - 批量数据库操作使用事务
   - 合理设置并发数避免资源耗尽
   - 使用连接池管理数据库连接
