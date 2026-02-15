# -*- coding: utf-8 -*-
"""
NewsBank Semantic Search Scraper
集成语义扩展的智能爬虫

功能：
1. 语义查询扩展（自动延伸到相关词）
2. 多字段精确搜索
3. 布尔逻辑组合
4. 智能预览筛选

使用方法：
    python newsbank_semantic.py "treasury wine" --semantic-mode moderate
    python newsbank_semantic.py "penfolds" --semantic-mode aggressive --max-pages 5
"""

import asyncio
import argparse
import json
import random
import time
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from urllib.parse import quote, urljoin

from playwright.async_api import async_playwright

# 导入搜索构建器和语义扩展
try:
    from newsbank_search_builder import (
        AdvancedSearchQuery, SearchField, BooleanOperator,
        SearchTemplates, SemanticSearchQuery, SemanticSearchTemplates,
        create_optimized_search, create_semantic_search,
        SEMANTIC_AVAILABLE
    )
    from semantic_expansion import SemanticExpander, get_related_terms
except ImportError as e:
    print(f"[错误] 缺少依赖模块: {e}")
    print("请确保以下文件在当前目录:")
    print("  - newsbank_search_builder.py")
    print("  - semantic_expansion.py")
    exit(1)


class ArticleIndex:
    """文章索引"""
    def __init__(self, title: str = "", date: str = "", source: str = "",
                 author: str = "", preview: str = "", url: str = "",
                 page_num: int = 0, has_substantial_content: bool = False,
                 word_count: int = 0):
        self.title = title
        self.date = date
        self.source = source
        self.author = author
        self.preview = preview
        self.url = url
        self.page_num = page_num
        self.has_substantial_content = has_substantial_content
        self.word_count = word_count
    
    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "date": self.date,
            "source": self.source,
            "author": self.author,
            "preview": self.preview[:500],
            "url": self.url,
            "page_num": self.page_num,
            "has_substantial_content": self.has_substantial_content,
            "word_count": self.word_count,
        }


class FullArticleData:
    """完整文章数据"""
    def __init__(self, title: str = "", date: str = "", source: str = "",
                 author: str = "", full_text: str = "", url: str = ""):
        self.title = title
        self.date = date
        self.source = source
        self.author = author
        self.full_text = full_text
        self.url = url
    
    def to_text(self, keyword: str, semantic_expansions: Optional[List[str]] = None) -> str:
        expansion_info = ""
        if semantic_expansions:
            expansion_info = f"\nSemantic Expansions: {', '.join(semantic_expansions)}"
        
        return f"""Title: {self.title}
Date: {self.date}
Source: {self.source}
Author: {self.author}
URL: {self.url}
Keyword: {keyword}{expansion_info}
Scraped at: {datetime.now().isoformat()}

Full Text:
{self.full_text}

{'='*80}
"""


class NewsBankSemanticScraper:
    """语义搜索爬虫"""
    
    def __init__(self,
                 headless: bool = False,
                 max_pages: int = 10,
                 min_preview_words: int = 30,
                 max_full_articles: int = 50,
                 semantic_mode: str = "moderate",
                 enable_semantic: bool = True,
                 start_page: int = 1,
                 end_page: int = 0):
        self.headless = headless
        self.max_pages = max_pages
        self.min_preview_words = min_preview_words
        self.max_full_articles = max_full_articles
        self.semantic_mode = semantic_mode
        self.enable_semantic = enable_semantic and SEMANTIC_AVAILABLE
        self.start_page = start_page
        self.end_page = end_page
        
        self.cookie_file = Path("cookies/newsbank_auth.json")
        self.output_dir = Path("articles_semantic")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cookie_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 反检测设置
        self.min_delay = 2
        self.max_delay = 5
        self.last_request_time = 0
        
        # 统计
        self.stats = {
            "total_pages": 0,
            "total_previewed": 0,
            "quality_articles": 0,
            "downloaded_full": 0,
            "skipped_low_quality": 0,
        }
        
        # 语义扩展器
        if self.enable_semantic:
            self.expander = SemanticExpander()
            self.semantic_builder = SemanticSearchQuery(
                semantic_mode=semantic_mode,
                enable_semantic=True
            )
        else:
            self.expander = None
            self.semantic_builder = None
        
        self.semantic_expansions: List[str] = []
    
    async def human_like_delay(self, min_sec: float = 0, max_sec: float = 0):
        """添加随机延迟"""
        min_seconds = min_sec if min_sec > 0 else self.min_delay
        max_seconds = max_sec if max_sec > 0 else self.max_delay
        delay = random.uniform(min_seconds, max_seconds)
        
        time_since_last = time.time() - self.last_request_time
        if time_since_last < min_seconds:
            delay = max(delay, min_seconds - time_since_last)
        
        await asyncio.sleep(delay)
        self.last_request_time = time.time()
    
    def build_semantic_search_query(self, keyword: str) -> Tuple[AdvancedSearchQuery, List[str]]:
        """
        构建语义增强的搜索查询
        
        Returns:
            (查询对象, 扩展词列表)
        """
        expansions = []
        
        if self.enable_semantic and self.expander:
            print(f"\n[语义扩展] 模式: {self.semantic_mode}")
            print("-" * 50)
            
            # 显示扩展信息
            expansion_summary = self.expander.get_expansion_summary(keyword, self.semantic_mode)
            print(expansion_summary)
            
            # 获取扩展词
            expansion_results = self.expander.expand_query(keyword, self.semantic_mode)
            for word, expanded_list in expansion_results.items():
                for term, score in expanded_list:
                    expansions.append(term)
            
            # 使用语义搜索构建器
            if self.semantic_builder:
                query = self.semantic_builder.build_query(keyword, SearchField.ALL_TEXT)
            else:
                query = AdvancedSearchQuery()
                expanded_query = self.expander.build_expanded_query(
                    keyword, self.semantic_mode
                )
                query.add_condition(expanded_query, SearchField.ALL_TEXT)
        else:
            # 不使用语义扩展
            print(f"\n[普通搜索] 关键词: {keyword}")
            query = AdvancedSearchQuery()
            query.add_condition(keyword, SearchField.ALL_TEXT)
        
        self.semantic_expansions = expansions
        return query, expansions
    
    async def scrape(self, keyword: str) -> dict:
        """主爬取方法"""
        print("="*80)
        print(f"NewsBank 语义搜索爬虫")
        print(f"原始关键词: '{keyword}'")
        print(f"语义扩展: {'启用' if self.enable_semantic else '禁用'}")
        print("="*80)
        
        # 构建搜索查询
        search_query, expansions = self.build_semantic_search_query(keyword)
        
        print("\n[搜索配置]")
        print(search_query.get_search_summary())
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.headless,
                args=['--disable-blink-features=AutomationControlled']
            )
            
            context = await browser.new_context(
                storage_state=str(self.cookie_file) if self.cookie_file.exists() else None,
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            
            page = await context.new_page()
            
            try:
                # 登录
                print("\n[登录]")
                print("-" * 40)
                
                if self.cookie_file.exists():
                    test_page = await context.new_page()
                    await test_page.goto(
                        "https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/browse-multi?p=AWGLNB",
                        wait_until="networkidle", timeout=30000
                    )
                    
                    if "infoweb-newsbank" in test_page.url and "login" not in test_page.url:
                        print("[成功] Cookie有效，自动登录")
                        await test_page.close()
                    else:
                        print("[信息] Cookie已过期，需要手动登录")
                        await test_page.close()
                        
                        if not self.headless:
                            await page.goto(
                                "https://eresources.sl.nsw.gov.au/newsbank-including-access-australia",
                                wait_until="networkidle", timeout=60000
                            )
                            
                            start_time = asyncio.get_event_loop().time()
                            while (asyncio.get_event_loop().time() - start_time) < 180:
                                if "infoweb-newsbank-com.ezproxy" in page.url and "login" not in page.url:
                                    print("[成功] 登录成功")
                                    break
                                await asyncio.sleep(2)
                            else:
                                print("[错误] 登录超时")
                                return self.stats
                        else:
                            print("[错误] 无头模式下无法手动登录")
                            return self.stats
                
                await context.storage_state(path=str(self.cookie_file))
                
                # 导航到搜索结果
                print("\n[开始搜索]")
                print("-" * 40)
                search_url = search_query.build_url()
                print(f"搜索URL已生成")
                
                await page.goto(search_url, wait_until="networkidle", timeout=60000)
                print(f"搜索结果已加载: {(await page.title()).split('|')[0].strip()}")
                
                # 扫描页面（简化版）
                print("\n[扫描文章]")
                print("-" * 40)
                
                quality_articles = []
                
                for page_num in range(1, self.max_pages + 1):
                    print(f"\n第 {page_num} 页...")
                    
                    articles = await page.query_selector_all('article.search-hits__hit')
                    if not articles:
                        print("  无更多文章")
                        break
                    
                    self.stats["total_pages"] += 1
                    print(f"  找到 {len(articles)} 篇文章")
                    
                    for i, article_elem in enumerate(articles, 1):
                        try:
                            # 提取基本信息
                            title_elem = await article_elem.query_selector("h3.search-hits__hit__title a")
                            if not title_elem:
                                continue
                            
                            title = await title_elem.inner_text()
                            title = title.replace("Go to the document viewer for ", "").strip()
                            
                            url = await title_elem.get_attribute("href") or ""
                            full_url = urljoin(page.url, url)
                            
                            # 预览
                            preview = ""
                            preview_elem = await article_elem.query_selector("div.preview-first-paragraph")
                            if preview_elem:
                                preview = await preview_elem.inner_text()
                            
                            # 元数据
                            date = ""
                            date_elem = await article_elem.query_selector("li.search-hits__hit__meta__item--display-date")
                            if date_elem:
                                date = await date_elem.inner_text()
                            
                            source = ""
                            source_elem = await article_elem.query_selector("li.search-hits__hit__meta__item--source")
                            if source_elem:
                                source = await source_elem.inner_text()
                            
                            # 质量检查
                            word_count = len(preview.split()) if preview else 0
                            if word_count >= self.min_preview_words:
                                article_index = ArticleIndex(
                                    title=title[:300],
                                    date=date.strip()[:100],
                                    source=source.strip()[:200],
                                    preview=preview[:1000],
                                    url=full_url[:500],
                                    page_num=page_num,
                                    has_substantial_content=True,
                                    word_count=word_count,
                                )
                                quality_articles.append(article_index)
                                self.stats["quality_articles"] += 1
                                if i <= 3:
                                    print(f"  [优质] #{i}: {title[:60]}... ({word_count}词)")
                            else:
                                self.stats["skipped_low_quality"] += 1
                        
                        except Exception as e:
                            continue
                    
                    # 下一页
                    if page_num < self.max_pages:
                        next_button = await page.query_selector('a:has-text("Next")')
                        if not next_button or await next_button.is_disabled():
                            print("  无下一页")
                            break
                        
                        await next_button.click()
                        await page.wait_for_load_state("networkidle")
                        await asyncio.sleep(1)
                
                # 下载全文
                print(f"\n[下载全文] 找到 {len(quality_articles)} 篇优质文章")
                print("-" * 40)
                
                to_download = min(len(quality_articles), self.max_full_articles)
                
                for i, article in enumerate(quality_articles[:to_download], 1):
                    print(f"\n[{i}/{to_download}] 下载: {article.title[:60]}...")
                    
                    try:
                        await self.human_like_delay(3, 7)
                        
                        await page.goto(article.url, wait_until="networkidle", timeout=30000)
                        await asyncio.sleep(2)
                        
                        # 提取全文
                        full_text = ""
                        for selector in ['.document-view__body', '.gnus-doc__body', '.document-text']:
                            elem = await page.query_selector(selector)
                            if elem:
                                full_text = await elem.inner_text()
                                if len(full_text.strip()) > 100:
                                    break
                        
                        if not full_text:
                            paragraphs = await page.query_selector_all('p')
                            texts = [await p.inner_text() for p in paragraphs if len(await p.inner_text()) > 20]
                            full_text = '\n\n'.join(texts)
                        
                        if len(full_text.strip()) < 50:
                            print(f"  [警告] 无有效全文")
                            continue
                        
                        # 保存
                        full_article = FullArticleData(
                            title=article.title,
                            date=article.date,
                            source=article.source,
                            author="",
                            full_text=full_text.strip()[:20000],
                            url=article.url,
                        )
                        
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        safe_title = "".join(c for c in article.title[:50] if c.isalnum() or c in (' ', '-', '_')).strip()
                        filename = f"{i:03d}_{timestamp}_{safe_title}.txt"
                        filepath = self.output_dir / filename
                        
                        with open(filepath, 'w', encoding='utf-8') as f:
                            f.write(full_article.to_text(keyword, self.semantic_expansions))
                        
                        self.stats["downloaded_full"] += 1
                        print(f"  [成功] 已保存 {len(full_text)} 字符")
                    
                    except Exception as e:
                        print(f"  [错误] {e}")
                        continue
                
                # 最终报告
                print("\n" + "="*80)
                print("[完成] 爬取完成！")
                print("="*80)
                print(f"扫描页数: {self.stats['total_pages']}")
                print(f"优质文章: {self.stats['quality_articles']}")
                print(f"下载全文: {self.stats['downloaded_full']}")
                print(f"跳过低质: {self.stats['skipped_low_quality']}")
                if self.semantic_expansions:
                    print(f"语义扩展: {', '.join(self.semantic_expansions[:10])}")
                print(f"输出目录: {self.output_dir.absolute()}")
                print("="*80)
                
                if not self.headless:
                    print("\n[INFO] 浏览器保持打开10秒...")
                    await asyncio.sleep(10)
            
            except Exception as e:
                print(f"\n[错误] {e}")
                import traceback
                traceback.print_exc()
            
            finally:
                await context.close()
                await browser.close()
        
        return self.stats


def main():
    parser = argparse.ArgumentParser(
        description="NewsBank Semantic Search Scraper - 语义搜索爬虫",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
语义搜索使用示例:

1. 基础语义搜索（自动扩展到相关词）:
   python newsbank_semantic.py "treasury wine"

2. 保守模式（高精确度）:
   python newsbank_semantic.py "treasury wine" --semantic-mode conservative

3. 激进模式（最大化召回率）:
   python newsbank_semantic.py "penfolds" --semantic-mode aggressive --max-pages 5

4. 禁用语义扩展（普通搜索）:
   python newsbank_semantic.py "treasury wine" --no-semantic

语义扩展效果:
  "treasury wine" → "treasury wine" OR "twe" OR "penfolds" OR "australian wine" ...
  "penfolds" → "penfolds" OR "penfold" OR "penfold's" OR "grange" ...

扩展模式说明:
  - conservative: 保守（最多3个高置信度扩展）
  - moderate: 适中（最多5个扩展，平衡精确度和召回率）
  - aggressive: 激进（最多8个扩展，最大化召回率）
        """
    )
    
    parser.add_argument("keyword", help="搜索关键词")
    
    # 语义搜索选项
    semantic_group = parser.add_argument_group("语义搜索选项")
    semantic_group.add_argument("--semantic-mode", 
                               choices=["conservative", "moderate", "aggressive"],
                               default="moderate",
                               help="语义扩展模式（默认: moderate）")
    semantic_group.add_argument("--no-semantic", action="store_true",
                               help="禁用语义扩展")
    
    # 爬取选项
    crawl_group = parser.add_argument_group("爬取选项")
    crawl_group.add_argument("--max-pages", type=int, default=5,
                            help="最大扫描页数（默认: 5）")
    crawl_group.add_argument("--max-full-articles", type=int, default=20,
                            help="下载全文的最大文章数（默认: 20）")
    crawl_group.add_argument("--min-preview-words", type=int, default=30,
                            help="预览文本最小词数（默认: 30）")
    crawl_group.add_argument("--headless", action="store_true",
                            help="无头模式")
    
    args = parser.parse_args()
    
    # 创建爬虫
    scraper = NewsBankSemanticScraper(
        headless=args.headless,
        max_pages=args.max_pages,
        max_full_articles=args.max_full_articles,
        min_preview_words=args.min_preview_words,
        semantic_mode=args.semantic_mode,
        enable_semantic=not args.no_semantic
    )
    
    # 运行爬取
    stats = asyncio.run(scraper.scrape(args.keyword))
    
    return 0 if stats["downloaded_full"] > 0 else 1


if __name__ == "__main__":
    exit(main())
