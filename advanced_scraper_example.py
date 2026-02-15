# -*- coding: utf-8 -*-
"""
高级 NewsBank 抓取器示例
集成了 Playwright、SQLite、重试机制和配置管理
"""

import asyncio
import logging
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite
from playwright.async_api import Browser, async_playwright
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
)

# ============================================================================
# 日志配置
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# 配置管理
# ============================================================================

class ScraperSettings(BaseSettings):
    """抓取器配置"""
    
    # 基础配置
    app_name: str = "NewsBank Scraper"
    debug: bool = False
    
    # Playwright 配置
    headless: bool = True
    browser_type: str = "chromium"
    max_concurrent_pages: int = 5
    page_timeout: int = 30000
    
    # 数据库配置
    database_path: str = "newsbank.db"
    max_db_connections: int = 5
    
    # 代理配置
    use_proxy: bool = False
    proxy_url: Optional[str] = None
    
    # 日志配置
    log_level: str = "INFO"
    
    # 重试配置
    max_retries: int = 3
    retry_wait_base: int = 1
    
    # 请求配置
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    request_timeout: int = 10000
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SCRAPER_",
        case_sensitive=False,
        extra="ignore"
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


# ============================================================================
# 数据库管理
# ============================================================================

class AsyncSQLiteManager:
    """异步 SQLite 数据库管理器"""
    
    def __init__(self, db_path: str = "data.db"):
        self.db_path = db_path
    
    @asynccontextmanager
    async def get_connection(self):
        """获取异步数据库连接"""
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
            
            # 创建索引提升查询性能
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_articles_source 
                ON articles(source)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_articles_created_at 
                ON articles(created_at)
            """)
            
            await conn.commit()
            logger.info("Database initialized successfully")
    
    async def insert_article(
        self,
        title: str,
        url: str,
        content: str,
        source: str
    ) -> int:
        """插入文章记录"""
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
    
    async def batch_insert_articles(
        self,
        articles: List[Dict[str, str]]
    ) -> tuple[List[int], List[Exception]]:
        """批量插入文章"""
        async with self.get_connection() as conn:
            cursor = await conn.cursor()
            
            await cursor.execute("BEGIN TRANSACTION")
            
            inserted_ids = []
            failed = []
            
            try:
                for article in articles:
                    try:
                        await cursor.execute(
                            """
                            INSERT INTO articles (title, url, content, source)
                            VALUES (?, ?, ?, ?)
                            """,
                            (
                                article['title'],
                                article['url'],
                                article['content'],
                                article['source']
                            )
                        )
                        inserted_ids.append(cursor.lastrowid)
                    except sqlite3.IntegrityError as e:
                        logger.warning(f"Duplicate URL: {article['url']}")
                        failed.append(e)
                
                await conn.commit()
                logger.info(f"Batch inserted {len(inserted_ids)} articles")
                return inserted_ids, failed
            except Exception as e:
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
    
    async def log_scrape_result(
        self,
        article_id: Optional[int],
        status: str,
        error_message: Optional[str] = None
    ):
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


class ConcurrentSQLiteManager(AsyncSQLiteManager):
    """支持并发的 SQLite 管理器"""
    
    def __init__(self, db_path: str = "data.db", max_concurrent: int = 5):
        super().__init__(db_path)
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
    
    async def _execute_with_semaphore(self, coro):
        """使用信号量限制并发"""
        async with self.semaphore:
            return await coro
    
    async def batch_insert_with_concurrency(
        self,
        articles: List[Dict[str, str]]
    ) -> tuple[List[int], List[Exception]]:
        """并发插入多个文章"""
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
        
        successful = [r for r in results if not isinstance(r, Exception)]
        failed = [r for r in results if isinstance(r, Exception)]
        
        logger.info(f"Inserted {len(successful)} articles, {len(failed)} failed")
        return successful, failed


# ============================================================================
# Playwright 抓取器
# ============================================================================

class PlaywrightConcurrentScraper:
    """Playwright 并发抓取器"""
    
    def __init__(self, max_pages: int = 5, headless: bool = True, timeout: int = 30000):
        self.max_pages = max_pages
        self.headless = headless
        self.timeout = timeout
        self.semaphore = asyncio.Semaphore(max_pages)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=10)
    )
    async def scrape_single_page(self, browser: Browser, url: str) -> dict:
        """抓取单个页面（带重试）"""
        async with self.semaphore:
            page = await browser.new_page()
            try:
                await page.goto(
                    url,
                    wait_until="networkidle",
                    timeout=self.timeout
                )
                
                title = await page.title()
                content = await page.content()
                
                return {
                    "url": url,
                    "title": title,
                    "content": content,
                    "status": "success"
                }
            except Exception as e:
                logger.error(f"Failed to scrape {url}: {e}")
                return {
                    "url": url,
                    "status": "failed",
                    "error": str(e)
                }
            finally:
                await page.close()
    
    async def scrape_multiple_pages(self, urls: List[str]) -> List[dict]:
        """并发抓取多个页面"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            
            try:
                tasks = [
                    self.scrape_single_page(browser, url)
                    for url in urls
                ]
                
                results = await asyncio.gather(*tasks)
                return results
            finally:
                await browser.close()


# ============================================================================
# 完整抓取器
# ============================================================================

class NewsBankScraper:
    """完整的 NewsBank 抓取器"""
    
    def __init__(self, settings: ScraperSettings):
        self.settings = settings
        self.db_manager = ConcurrentSQLiteManager(
            db_path=settings.database_path,
            max_concurrent=settings.max_db_connections
        )
        self.playwright_scraper = PlaywrightConcurrentScraper(
            max_pages=settings.max_concurrent_pages,
            headless=settings.headless,
            timeout=settings.page_timeout
        )
    
    async def initialize(self):
        """初始化抓取器"""
        await self.db_manager.init_db()
        logger.info("Scraper initialized successfully")
    
    async def scrape_and_store(self, urls: List[str]) -> Dict[str, Any]:
        """抓取 URL 并存储到数据库"""
        logger.info(f"Starting to scrape {len(urls)} URLs")
        
        # 并发抓取
        scrape_results = await self.playwright_scraper.scrape_multiple_pages(urls)
        
        # 准备文章数据
        articles = []
        for result in scrape_results:
            if result['status'] == 'success':
                articles.append({
                    'title': result.get('title', 'Unknown'),
                    'url': result['url'],
                    'content': result.get('content', ''),
                    'source': 'newsbank'
                })
                await self.db_manager.log_scrape_result(
                    None,
                    'success'
                )
            else:
                await self.db_manager.log_scrape_result(
                    None,
                    'failed',
                    result.get('error', 'Unknown error')
                )
        
        # 批量插入
        inserted_ids, failed = await self.db_manager.batch_insert_with_concurrency(articles)
        
        logger.info(f"Scraped {len(inserted_ids)} articles successfully, {len(failed)} failed")
        
        return {
            'total': len(urls),
            'successful': len(inserted_ids),
            'failed': len(failed),
            'timestamp': datetime.now().isoformat()
        }


# ============================================================================
# 主程序
# ============================================================================

async def main():
    """主程序"""
    # 加载配置
    settings = ScraperSettings()
    
    # 创建抓取器
    scraper = NewsBankScraper(settings)
    await scraper.initialize()
    
    # 测试 URL
    urls = [
        "https://example.com/news/1",
        "https://example.com/news/2",
        "https://example.com/news/3",
    ]
    
    # 执行抓取
    result = await scraper.scrape_and_store(urls)
    print(f"Scraping result: {result}")


if __name__ == "__main__":
    asyncio.run(main())
