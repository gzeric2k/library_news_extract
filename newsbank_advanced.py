# -*- coding: utf-8 -*-
"""
NewsBank Advanced Search Scraper
集成高级搜索查询构建器的智能爬虫

功能特点:
1. 多字段精确搜索（标题、首段、全文）
2. 布尔逻辑组合（AND/OR/NOT）
3. 通配符支持（*匹配多字符）
4. 预设搜索模板（并购、战略、财务等主题）
5. 智能预览筛选和全文下载
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

from newsbank_search_builder import (
    AdvancedSearchQuery, SearchField, BooleanOperator,
    SearchTemplates, create_optimized_search
)


class ArticleIndex:
    """Article index for preview screening"""
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
    """Full article data"""
    def __init__(self, title: str = "", date: str = "", source: str = "",
                 author: str = "", full_text: str = "", url: str = ""):
        self.title = title
        self.date = date
        self.source = source
        self.author = author
        self.full_text = full_text
        self.url = url
    
    def to_text(self, keyword: str) -> str:
        return f"""Title: {self.title}
Date: {self.date}
Source: {self.source}
Author: {self.author}
URL: {self.url}
Keyword: {keyword}
Scraped at: {datetime.now().isoformat()}

Full Text:
{self.full_text}

{'='*80}
"""


class NewsBankAdvancedScraper:
    """高级搜索爬虫 - 支持精确搜索策略"""
    
    def __init__(self, 
                 headless: bool = False, 
                 max_pages: int = 10,
                 min_preview_words: int = 30, 
                 max_full_articles: int = 50,
                 start_page: int = 1, 
                 end_page: int = 0,
                 use_precise_search: bool = True):
        self.headless = headless
        self.max_pages = max_pages
        self.min_preview_words = min_preview_words
        self.max_full_articles = max_full_articles
        self.start_page = start_page
        self.end_page = end_page
        self.use_precise_search = use_precise_search
        
        self.cookie_file = Path("cookies/newsbank_auth.json")
        self.output_dir = Path("articles_advanced")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cookie_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Anti-detection
        self.min_delay = 2
        self.max_delay = 5
        self.last_request_time = 0
        
        self.article_index: List[ArticleIndex] = []
        self.total_pages_detected = 0
        self.total_results = 0
        
        self.stats = {
            "total_pages": 0,
            "total_previewed": 0,
            "quality_articles": 0,
            "downloaded_full": 0,
            "skipped_low_quality": 0,
        }
        
        self.search_query: Optional[AdvancedSearchQuery] = None
    
    async def human_like_delay(self, min_sec: float = 0, max_sec: float = 0):
        """Add random delay"""
        min_seconds = min_sec if min_sec > 0 else self.min_delay
        max_seconds = max_sec if max_sec > 0 else self.max_delay
        delay = random.uniform(min_seconds, max_seconds)
        
        time_since_last = time.time() - self.last_request_time
        if time_since_last < min_seconds:
            delay = max(delay, min_seconds - time_since_last)
        
        await asyncio.sleep(delay)
        self.last_request_time = time.time()
    
    def build_search_query(self, keyword: str) -> AdvancedSearchQuery:
        """
        构建优化的搜索查询
        
        策略:
        1. 模板搜索: template:名称
        2. 短语搜索（含空格）: 标题必须包含完整短语
        3. 单词搜索: 标题+全文组合
        """
        # 检查是否使用预设模板
        if keyword.startswith("template:"):
            template_name = keyword.replace("template:", "").strip()
            print(f"[INFO] 使用预设模板: {template_name}")
            return create_optimized_search(template_name)
        
        # 构建自定义优化查询
        query = AdvancedSearchQuery()
        
        if ' ' in keyword:
            # 多词短语：使用标题+全文双重确认
            # 标题必须包含（确保相关性）
            query.add_title_keyword(f'"{keyword}"', BooleanOperator.AND)
            # 全文也必须包含（确保完整性）
            query.add_condition(keyword, SearchField.ALL_TEXT, BooleanOperator.AND)
        else:
            # 单词：全文搜索为主，标题匹配加分
            query.add_condition(keyword, SearchField.ALL_TEXT)
            query.add_title_keyword(keyword, BooleanOperator.OR)
            # 首段包含也加分
            query.add_condition(keyword, SearchField.LEAD, BooleanOperator.OR)
        
        return query
    
    async def detect_total_pages(self, page) -> Tuple[int, int]:
        """Detect total number of pages and results"""
        print("\n[检测总页数和结果数...]")
        
        total_pages = 0
        total_results = 0
        
        # Method 1: Look for "X Results" text
        try:
            results_meta = await page.query_selector('.search-hits__meta--total_hits')
            if results_meta:
                text = await results_meta.inner_text()
                match = re.search(r'([\d,]+)\s*Results?', text)
                if match:
                    total_results = int(match.group(1).replace(',', ''))
                    print(f"   总结果数: {total_results:,}")
        except:
            pass
        
        # Method 2: Look for pagination
        try:
            pagination_links = await page.query_selector_all('.pagination a, .pager a, a[href*="page="]')
            page_numbers = []
            for link in pagination_links:
                try:
                    text = await link.inner_text()
                    if text.isdigit():
                        page_numbers.append(int(text))
                except:
                    continue
            
            if page_numbers:
                total_pages = max(page_numbers)
                print(f"   总页数: {total_pages}")
        except:
            pass
        
        # Method 3: Calculate from results (60 per page)
        if total_results > 0 and total_pages == 0:
            total_pages = (total_results + 59) // 60
            print(f"   计算总页数: {total_pages} (每页60条)")
        
        # Default if still not found
        if total_pages == 0:
            total_pages = 10
            print(f"   使用默认: {total_pages} 页")
        
        return total_pages, total_results
    
    def analyze_preview_quality(self, preview: str) -> tuple[bool, int]:
        """Analyze if preview has substantial content"""
        if not preview:
            return False, 0
        
        clean_text = preview.strip()
        words = clean_text.split()
        word_count = len(words)
        
        low_quality_indicators = [
            "Pages", "Clear Filters", "Privacy Policy",
            "Contact Customer Service", "Create Email Alert",
            "Terms of Use", "Cookie Policy", "Sign Out",
            "Search", "Next", "Previous"
        ]
        
        has_indicators = any(indicator in clean_text for indicator in low_quality_indicators)
        
        if has_indicators and word_count < 20:
            return False, word_count
        
        if word_count < self.min_preview_words:
            return False, word_count
        
        if '.' not in clean_text and '?' not in clean_text and '!' not in clean_text:
            return False, word_count
        
        return True, word_count
    
    async def phase1_preview_scan(self, page, keyword: str) -> List[ArticleIndex]:
        """Phase 1: Preview scan with quality filtering"""
        print("\n" + "="*80)
        print("阶段1: 预览扫描（智能筛选）")
        print("="*80)
        print(f"分析预览文本质量（最少{self.min_preview_words}词）...")
        print(f"页码范围: {self.start_page} 到 {self.end_page if self.end_page else '自动'}\n")
        
        article_index_list: List[ArticleIndex] = []
        
        # Detect total pages first
        if self.end_page == 0 or self.end_page > self.start_page:
            self.total_pages_detected, self.total_results = await self.detect_total_pages(page)
            
            # Calculate actual end page
            if self.end_page == 0:
                if self.max_pages > 0:
                    self.end_page = min(self.start_page + self.max_pages - 1, self.total_pages_detected)
                else:
                    self.end_page = self.total_pages_detected
            else:
                self.end_page = min(self.end_page, self.total_pages_detected)
            
            print(f"\n   将扫描第 {self.start_page} 到 {self.end_page} 页")
            print(f"   （可用: {self.total_pages_detected} 页, {self.total_results:,} 条结果）\n")
        
        current_page = self.start_page
        
        while current_page <= self.end_page:
            print(f"扫描第 {current_page}/{self.end_page} 页...")
            
            # Navigate to specific page if not on page 1
            if current_page > 1:
                next_selectors = [
                    'a:has-text("Next")',
                    'button:has-text("Next")',
                    '[aria-label="Next"]',
                ]
                next_button = None
                for selector in next_selectors:
                    try:
                        next_button = await page.wait_for_selector(selector, timeout=3000)
                        if next_button:
                            is_disabled = await next_button.is_disabled()
                            if not is_disabled:
                                break
                            else:
                                next_button = None
                    except:
                        continue
                
                if not next_button:
                    print(f"   无下一页按钮，结束于第 {current_page-1} 页")
                    break
                
                await next_button.click()
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(1)
            
            # Find all articles on this page
            articles = await page.query_selector_all('article.search-hits__hit')
            
            if not articles:
                print("   未找到文章")
                break
            
            self.stats["total_pages"] += 1
            print(f"   找到 {len(articles)} 篇文章")
            
            page_quality_count = 0
            for i, article_elem in enumerate(articles, 1):
                try:
                    title_elem = await article_elem.query_selector("h3.search-hits__hit__title a")
                    if not title_elem:
                        continue
                    
                    title = await title_elem.inner_text()
                    title = title.replace("Go to the document viewer for ", "").strip()
                    
                    url = await title_elem.get_attribute("href") or ""
                    full_url = urljoin(page.url, url)
                    
                    preview = ""
                    preview_elem = await article_elem.query_selector("div.preview-first-paragraph")
                    if preview_elem:
                        preview = await preview_elem.inner_text()
                    else:
                        preview_container = await article_elem.query_selector("div.search-hits__hit__preview")
                        if preview_container:
                            preview = await preview_container.inner_text()
                    
                    preview = preview.strip()
                    
                    date = ""
                    date_elem = await article_elem.query_selector("li.search-hits__hit__meta__item--display-date")
                    if date_elem:
                        date = await date_elem.inner_text()
                    
                    source = ""
                    source_elem = await article_elem.query_selector("li.search-hits__hit__meta__item--source")
                    if source_elem:
                        source = await source_elem.inner_text()
                    
                    author = ""
                    author_elem = await article_elem.query_selector("li.search-hits__hit__meta__item--author")
                    if author_elem:
                        author = await author_elem.inner_text()
                    
                    has_quality, word_count = self.analyze_preview_quality(preview)
                    
                    article_index = ArticleIndex(
                        title=title[:300],
                        date=date.strip()[:100],
                        source=source.strip()[:200],
                        author=author.strip()[:100],
                        preview=preview[:1000],
                        url=full_url[:500],
                        page_num=current_page,
                        has_substantial_content=has_quality,
                        word_count=word_count,
                    )
                    
                    article_index_list.append(article_index)
                    self.stats["total_previewed"] += 1
                    
                    if has_quality:
                        self.stats["quality_articles"] += 1
                        page_quality_count += 1
                        status = "[优质]"
                    else:
                        self.stats["skipped_low_quality"] += 1
                        status = "[跳过]"
                    
                    if i <= 5 or has_quality:
                        print(f"   {status} #{i}: {title[:55]}... ({word_count}词)")
                
                except Exception as e:
                    continue
            
            print(f"   第 {current_page} 页: {page_quality_count}/{len(articles)} 篇优质\n")
            
            current_page += 1
            
            if current_page <= self.end_page:
                await asyncio.sleep(0.5)
        
        return article_index_list
    
    async def phase2_download_full(self, page, keyword: str, quality_articles: List[ArticleIndex]):
        """Phase 2: Download full text for quality articles"""
        print("\n" + "="*80)
        print("阶段2: 全文下载")
        print("="*80)
        
        total_quality = len(quality_articles)
        to_download = min(total_quality, self.max_full_articles)
        
        print(f"优质文章: {total_quality} 篇")
        print(f"将下载: {to_download} 篇\n")
        
        downloaded_count = 0
        
        for i, article in enumerate(quality_articles[:to_download], 1):
            print(f"\n[{i}/{to_download}] 下载中...")
            print(f"   标题: {article.title[:65]}...")
            print(f"   预览: {article.word_count} 词")
            
            try:
                await self.human_like_delay(3, 7)
                
                await page.goto(article.url, wait_until="networkidle", timeout=30000)
                await asyncio.sleep(2)
                
                full_text = ""
                text_selectors = [
                    '.document-view__body',
                    '.gnus-doc__body',
                    '.document-text',
                    'article',
                    '.text',
                ]
                
                for selector in text_selectors:
                    try:
                        elem = await page.query_selector(selector)
                        if elem:
                            full_text = await elem.inner_text()
                            if len(full_text.strip()) > 100:
                                break
                    except:
                        continue
                
                if not full_text:
                    paragraphs = await page.query_selector_all('p')
                    texts = []
                    for p in paragraphs:
                        text = await p.inner_text()
                        if len(text.strip()) > 20:
                            texts.append(text)
                    full_text = '\n\n'.join(texts)
                
                if not full_text or len(full_text.strip()) < 50:
                    print(f"   [警告] 无有效全文")
                    continue
                
                full_article = FullArticleData(
                    title=article.title,
                    date=article.date,
                    source=article.source,
                    author=article.author,
                    full_text=full_text.strip()[:20000],
                    url=article.url,
                )
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_title = "".join(c for c in article.title[:50] if c.isalnum() or c in (' ', '-', '_')).strip()
                filename = f"{i:03d}_{timestamp}_{safe_title}.txt"
                filepath = self.output_dir / filename
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(full_article.to_text(keyword))
                
                downloaded_count += 1
                self.stats["downloaded_full"] += 1
                
                print(f"   [成功] {len(full_text)} 字符已保存")
                
            except Exception as e:
                print(f"   [错误] {e}")
                continue
        
        return downloaded_count
    
    async def scrape(self, keyword: str, search_query: Optional[AdvancedSearchQuery] = None) -> dict:
        """Main scraping method with advanced search"""
        print("="*80)
        print(f"NewsBank 高级搜索爬虫")
        print(f"关键词/模板: '{keyword}'")
        print("="*80)
        
        # Build search query
        if search_query is None:
            self.search_query = self.build_search_query(keyword)
        else:
            self.search_query = search_query
        
        # Display search strategy
        print("\n[搜索策略]")
        print(self.search_query.get_search_summary())
        
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
                # Login
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
                        print("[信息] Cookie已过期")
                        await test_page.close()
                        
                        if not self.headless:
                            await page.goto(
                                "https://eresources.sl.nsw.gov.au/newsbank-including-access-australia",
                                wait_until="networkidle", timeout=60000
                            )
                            
                            start_time = asyncio.get_event_loop().time()
                            while (asyncio.get_event_loop().time() - start_time) < 180:
                                if "infoweb-newsbank-com.ezproxy" in page.url and "login" not in page.url:
                                    break
                                await asyncio.sleep(2)
                
                await context.storage_state(path=str(self.cookie_file))
                
                # Navigate to search results using optimized URL
                print("\n[开始搜索]")
                print("-" * 40)
                search_url = self.search_query.build_url()
                print(f"搜索URL已生成")
                
                await page.goto(search_url, wait_until="networkidle", timeout=60000)
                print(f"搜索结果已加载: {(await page.title()).split('|')[0].strip()}")
                
                # Phase 1: Preview scan
                self.article_index = await self.phase1_preview_scan(page, keyword)
                
                # Save index
                index_path = self.output_dir / f"index_{keyword.replace(' ', '_').replace(':', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                with open(index_path, 'w', encoding='utf-8') as f:
                    json.dump([a.to_dict() for a in self.article_index], f, indent=2, ensure_ascii=False)
                print(f"\n索引已保存: {index_path}")
                
                # Filter quality
                quality_articles = [a for a in self.article_index if a.has_substantial_content]
                
                if not quality_articles:
                    print("\n[警告] 未找到有实质内容的优质文章")
                    return self.stats
                
                # Phase 2: Download full text
                downloaded = await self.phase2_download_full(page, keyword, quality_articles)
                
                # Final report
                print("\n" + "="*80)
                print("[完成] 爬取完成！")
                print("="*80)
                print(f"扫描页数: {self.stats['total_pages']}")
                print(f"预览文章: {self.stats['total_previewed']}")
                print(f"优质文章: {self.stats['quality_articles']}")
                print(f"跳过低质: {self.stats['skipped_low_quality']}")
                print(f"下载全文: {self.stats['downloaded_full']}")
                print(f"输出目录: {self.output_dir.absolute()}")
                print("="*80)
                
                if not self.headless:
                    print("\n[信息] 浏览器保持打开10秒...")
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
        description="NewsBank Advanced Search Scraper - 高级搜索爬虫",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用方法示例:

1. 基础关键词搜索（自动优化）:
   python newsbank_advanced.py "treasury wine estates"

2. 使用预设搜索模板（高精准）:
   python newsbank_advanced.py "template:treasury_mergers"
   python newsbank_advanced.py "template:treasury_strategy"
   python newsbank_advanced.py "template:treasury_financial"

3. 仅生成并显示搜索URL（不执行爬取）:
   python newsbank_advanced.py "treasury wine" --show-url

4. 指定页数范围和下载数量:
   python newsbank_advanced.py "penfolds" --max-pages 5 --max-full-articles 30

搜索策略说明:
- 多词短语: 标题必须包含完整短语（提高相关性）
- 单词搜索: 标题+首段+全文组合（提高召回率）
- 预设模板: 针对特定主题优化的搜索策略
        """
    )
    
    parser.add_argument("keyword", 
                       help="搜索关键词或模板（如 'treasury wine' 或 'template:treasury_mergers'）")
    
    # Page range options
    page_group = parser.add_mutually_exclusive_group()
    page_group.add_argument("--all-pages", action="store_true",
                           help="扫描所有可用页数（谨慎使用！）")
    page_group.add_argument("--max-pages", type=int, default=10,
                           help="最大扫描页数（默认: 10）")
    
    parser.add_argument("--start-page", type=int, default=1,
                       help="从第N页开始（默认: 1）")
    parser.add_argument("--end-page", type=int, default=0,
                       help="到第N页结束（0=自动检测，默认: 0）")
    
    # Quality filters
    parser.add_argument("--min-preview-words", type=int, default=30,
                       help="预览文本最小词数（默认: 30）")
    parser.add_argument("--max-full-articles", type=int, default=20,
                       help="下载全文的最大文章数（默认: 20）")
    
    parser.add_argument("--headless", action="store_true", 
                       help="无头模式（不显示浏览器窗口）")
    parser.add_argument("--show-url", action="store_true",
                       help="仅生成并显示搜索URL，不执行爬取")
    
    args = parser.parse_args()
    
    # Show URL only mode
    if args.show_url:
        print("="*80)
        print("NewsBank 高级搜索URL生成器")
        print("="*80)
        
        scraper = NewsBankAdvancedScraper()
        query = scraper.build_search_query(args.keyword)
        
        print("\n搜索策略:")
        print(query.get_search_summary())
        
        print("\n" + "="*80)
        print("生成的搜索URL:")
        print("="*80)
        print(query.build_url())
        print("\n" + "="*80)
        print("提示: 复制上述URL到浏览器测试搜索结果")
        print("="*80)
        return 0
    
    # Calculate max_pages
    max_pages = 0 if args.all_pages else args.max_pages
    
    scraper = NewsBankAdvancedScraper(
        headless=args.headless,
        max_pages=max_pages,
        min_preview_words=args.min_preview_words,
        max_full_articles=args.max_full_articles,
        start_page=args.start_page,
        end_page=args.end_page
    )
    
    stats = asyncio.run(scraper.scrape(args.keyword))
    
    return 0 if stats["downloaded_full"] > 0 else 1


if __name__ == "__main__":
    exit(main())
