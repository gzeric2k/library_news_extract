# -*- coding: utf-8 -*-
"""
NewsBank Smart Full-Text Scraper
Two-phase approach:
1. Quick preview scan to identify articles with substantial content
2. Selective full-text download for quality articles only
"""

import asyncio
import argparse
import json
import random
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
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


class NewsBankSmartScraper:
    """Smart scraper with preview screening"""
    
    def __init__(self, headless: bool = False, max_pages: int = 10,
                 min_preview_words: int = 30, max_full_articles: int = 50):
        self.headless = headless
        self.max_pages = max_pages
        self.min_preview_words = min_preview_words  # Minimum words in preview to qualify
        self.max_full_articles = max_full_articles
        
        self.cookie_file = Path("cookies/newsbank_auth.json")
        self.output_dir = Path("articles_smart")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cookie_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Anti-detection
        self.min_delay = 2
        self.max_delay = 5
        self.last_request_time = 0
        
        self.article_index: List[ArticleIndex] = []
        
        self.stats = {
            "total_pages": 0,
            "total_previewed": 0,
            "quality_articles": 0,
            "downloaded_full": 0,
            "skipped_low_quality": 0,
        }
    
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
    
    def analyze_preview_quality(self, preview: str) -> tuple[bool, int]:
        """Analyze if preview has substantial content
        Returns: (has_quality_content, word_count)
        """
        if not preview:
            return False, 0
        
        # Clean the text
        clean_text = preview.strip()
        
        # Count words (rough estimate)
        words = clean_text.split()
        word_count = len(words)
        
        # Check for indicators of low-quality content
        low_quality_indicators = [
            "Pages", "Clear Filters", "Privacy Policy",
            "Contact Customer Service", "Create Email Alert",
            "Terms of Use", "Cookie Policy", "Sign Out",
            "Search", "Next", "Previous"
        ]
        
        # If contains low-quality indicators and very short
        has_indicators = any(indicator in clean_text for indicator in low_quality_indicators)
        
        if has_indicators and word_count < 20:
            return False, word_count
        
        # Check if it looks like actual article content
        # Should have reasonable length and sentence structure
        if word_count < self.min_preview_words:
            return False, word_count
        
        # Check for sentence structure (should have periods)
        if '.' not in clean_text and '?' not in clean_text and '!' not in clean_text:
            return False, word_count
        
        return True, word_count
    
    async def phase1_preview_scan(self, page, keyword: str) -> List[ArticleIndex]:
        """Phase 1: Quick preview scan to identify quality articles"""
        print("\n" + "="*80)
        print("PHASE 1: Preview Scan (Quick)")
        print("="*80)
        print("Analyzing preview text to identify articles with substantial content...")
        print(f"Minimum preview words required: {self.min_preview_words}\n")
        
        article_index_list: List[ArticleIndex] = []
        
        for page_num in range(1, self.max_pages + 1):
            print(f"Scanning page {page_num}...")
            
            if page_num > 1:
                # Navigate to next page
                next_selectors = [
                    'a:has-text("Next")',
                    'button:has-text("Next")',
                    '[aria-label="Next"]',
                ]
                next_button = None
                for selector in next_selectors:
                    try:
                        next_button = await page.wait_for_selector(selector, timeout=2000)
                        if next_button:
                            break
                    except:
                        continue
                
                if not next_button:
                    print("   No more pages")
                    break
                
                await next_button.click()
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(1)  # Brief delay for page load
            
            # Find all articles on this page
            articles = await page.query_selector_all('article.search-hits__hit')
            
            if not articles:
                print("   No articles found")
                break
            
            self.stats["total_pages"] += 1
            print(f"   Found {len(articles)} articles")
            
            page_quality_count = 0
            for i, article_elem in enumerate(articles, 1):
                try:
                    # Extract basic info quickly
                    title_elem = await article_elem.query_selector("h3.search-hits__hit__title a")
                    if not title_elem:
                        continue
                    
                    title = await title_elem.inner_text()
                    title = title.replace("Go to the document viewer for ", "").strip()
                    
                    url = await title_elem.get_attribute("href") or ""
                    full_url = urljoin(page.url, url)
                    
                    # Get preview
                    preview = ""
                    preview_elem = await article_elem.query_selector("div.preview-first-paragraph")
                    if preview_elem:
                        preview = await preview_elem.inner_text()
                    else:
                        # Fallback
                        preview_container = await article_elem.query_selector("div.search-hits__hit__preview")
                        if preview_container:
                            preview = await preview_container.inner_text()
                    
                    preview = preview.strip()
                    
                    # Get metadata
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
                    
                    # Analyze quality
                    has_quality, word_count = self.analyze_preview_quality(preview)
                    
                    article_index = ArticleIndex(
                        title=title[:300],
                        date=date.strip()[:100],
                        source=source.strip()[:200],
                        author=author.strip()[:100],
                        preview=preview[:1000],
                        url=full_url[:500],
                        page_num=page_num,
                        has_substantial_content=has_quality,
                        word_count=word_count,
                    )
                    
                    article_index_list.append(article_index)
                    self.stats["total_previewed"] += 1
                    
                    if has_quality:
                        self.stats["quality_articles"] += 1
                        page_quality_count += 1
                        status = "[QUALITY]"
                    else:
                        self.stats["skipped_low_quality"] += 1
                        status = "[SKIP]"
                    
                    if i <= 10 or has_quality:  # Print first 10 and all quality ones
                        print(f"   {status} #{i}: {title[:60]}... ({word_count} words)")
                
                except Exception as e:
                    continue
            
            print(f"   Page {page_num} summary: {page_quality_count}/{len(articles)} quality articles\n")
        
        return article_index_list
    
    async def phase2_download_full(self, page, keyword: str, quality_articles: List[ArticleIndex]):
        """Phase 2: Download full text for quality articles only"""
        print("\n" + "="*80)
        print("PHASE 2: Full-Text Download (Selective)")
        print("="*80)
        
        total_quality = len(quality_articles)
        to_download = min(total_quality, self.max_full_articles)
        
        print(f"Found {total_quality} quality articles with substantial content")
        print(f"Will download full text for top {to_download} articles\n")
        
        downloaded_count = 0
        
        for i, article in enumerate(quality_articles[:to_download], 1):
            print(f"\n[{i}/{to_download}] Downloading full article...")
            print(f"   Title: {article.title[:70]}...")
            print(f"   Preview quality: {article.word_count} words")
            
            try:
                # Add anti-detection delay
                await self.human_like_delay(3, 7)
                
                # Navigate to article
                await page.goto(article.url, wait_until="networkidle", timeout=30000)
                await asyncio.sleep(2)
                
                # Extract full text
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
                    # Fallback to paragraphs
                    paragraphs = await page.query_selector_all('p')
                    texts = []
                    for p in paragraphs:
                        text = await p.inner_text()
                        if len(text.strip()) > 20:
                            texts.append(text)
                    full_text = '\n\n'.join(texts)
                
                if not full_text or len(full_text.strip()) < 50:
                    print(f"   [WARNING] No substantial full text found")
                    continue
                
                # Create full article object
                full_article = FullArticleData(
                    title=article.title,
                    date=article.date,
                    source=article.source,
                    author=article.author,
                    full_text=full_text.strip()[:20000],
                    url=article.url,
                )
                
                # Save to file
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_title = "".join(c for c in article.title[:50] if c.isalnum() or c in (' ', '-', '_')).strip()
                filename = f"{i:03d}_{timestamp}_{safe_title}.txt"
                filepath = self.output_dir / filename
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(full_article.to_text(keyword))
                
                downloaded_count += 1
                self.stats["downloaded_full"] += 1
                
                print(f"   [OK] Saved: {len(full_text)} chars")
                print(f"        File: {filename}")
                
            except Exception as e:
                print(f"   [ERROR] Failed to download: {e}")
                continue
        
        return downloaded_count
    
    async def scrape(self, keyword: str) -> dict:
        """Main scraping method with two-phase approach"""
        print("="*80)
        print(f"NewsBank SMART Full-Text Scraper")
        print(f"Keyword: '{keyword}'")
        print(f"Max pages: {self.max_pages}")
        print(f"Min preview words: {self.min_preview_words}")
        print(f"Max full articles: {self.max_full_articles}")
        print("="*80)
        print("\nThis scraper uses a two-phase approach:")
        print("  Phase 1: Quick preview scan to identify quality articles")
        print("  Phase 2: Selective full-text download for quality articles only")
        print("="*80)
        
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
                print("\n[Login]")
                print("-" * 40)
                
                if self.cookie_file.exists():
                    print("Checking saved cookies...")
                    test_page = await context.new_page()
                    await test_page.goto(
                        "https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/browse-multi?p=AWGLNB",
                        wait_until="networkidle", timeout=30000
                    )
                    
                    if "infoweb-newsbank" in test_page.url and "login" not in test_page.url:
                        print("[OK] Cookies valid, logged in automatically")
                        await test_page.close()
                    else:
                        print("[INFO] Cookies expired, please login manually")
                        await test_page.close()
                        
                        if not self.headless:
                            await page.goto(
                                "https://eresources.sl.nsw.gov.au/newsbank-including-access-australia",
                                wait_until="networkidle", timeout=60000
                            )
                            
                            start_time = asyncio.get_event_loop().time()
                            while (asyncio.get_event_loop().time() - start_time) < 180:
                                if "infoweb-newsbank-com.ezproxy" in page.url and "login" not in page.url:
                                    print("[OK] Login successful")
                                    break
                                await asyncio.sleep(2)
                            else:
                                print("[ERROR] Login timeout")
                                return self.stats
                        else:
                            print("[ERROR] Cannot login in headless mode")
                            return self.stats
                
                await context.storage_state(path=str(self.cookie_file))
                
                # Navigate to search results
                print("\n[Searching]")
                print("-" * 40)
                
                # 检查是否使用预设搜索模板
                if keyword.startswith("template:"):
                    template_name = keyword.replace("template:", "").strip()
                    print(f"[INFO] Using search template: {template_name}")
                    search_query = create_optimized_search(template_name)
                    print(search_query.get_search_summary())
                    search_url = search_query.build_url()
                else:
                    # 构建优化的高级搜索查询
                    print(f"[INFO] Building optimized search for: {keyword}")
                    search_query = AdvancedSearchQuery()
                    
                    # 自动识别是否包含空格（短语）
                    if ' ' in keyword:
                        # 多词关键词：标题必须包含，全文也必须包含
                        search_query.add_title_keyword(f'"{keyword}"', BooleanOperator.AND)
                        search_query.add_condition(keyword, SearchField.ALL_TEXT, BooleanOperator.AND)
                    else:
                        # 单词关键词：全文搜索，同时标题加分
                        search_query.add_condition(keyword, SearchField.ALL_TEXT)
                        search_query.add_title_keyword(keyword, BooleanOperator.OR)
                    
                    print(search_query.get_search_summary())
                    search_url = search_query.build_url()
                
                await page.goto(search_url, wait_until="networkidle", timeout=60000)
                print(f"Search results loaded: {await page.title()}")
                
                # Phase 1: Preview scan
                self.article_index = await self.phase1_preview_scan(page, keyword)
                
                # Save index to JSON
                index_path = self.output_dir / f"index_{keyword.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                with open(index_path, 'w', encoding='utf-8') as f:
                    json.dump([a.to_dict() for a in self.article_index], f, indent=2, ensure_ascii=False)
                print(f"\nArticle index saved: {index_path}")
                
                # Filter quality articles
                quality_articles = [a for a in self.article_index if a.has_substantial_content]
                
                if not quality_articles:
                    print("\n[WARNING] No quality articles found with substantial content")
                    print("Consider lowering --min-preview-words threshold")
                    return self.stats
                
                # Phase 2: Download full text
                downloaded = await self.phase2_download_full(page, keyword, quality_articles)
                
                # Final report
                print("\n" + "="*80)
                print("[DONE] Smart Scraping Completed!")
                print("="*80)
                print(f"Phase 1 - Preview Scan:")
                print(f"   Pages scanned: {self.stats['total_pages']}")
                print(f"   Articles previewed: {self.stats['total_previewed']}")
                print(f"   Quality articles: {self.stats['quality_articles']}")
                print(f"   Low quality skipped: {self.stats['skipped_low_quality']}")
                print(f"\nPhase 2 - Full-Text Download:")
                print(f"   Articles downloaded: {self.stats['downloaded_full']}")
                print(f"\nOutput directory: {self.output_dir.absolute()}")
                print("="*80)
                
                if not self.headless:
                    print("\n[INFO] Browser will stay open for 10 seconds...")
                    await asyncio.sleep(10)
                
            except Exception as e:
                print(f"\n[ERROR] {e}")
                import traceback
                traceback.print_exc()
            
            finally:
                await context.close()
                await browser.close()
        
        return self.stats


def main():
    parser = argparse.ArgumentParser(
        description="NewsBank Smart Full-Text Scraper with Advanced Search",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
搜索关键词格式:
  普通关键词: "treasury wine estates"
  使用预设模板: "template:treasury_mergers"
  
可用模板:
  - treasury_mergers: Treasury Wine并购主题（标题含品牌+全文并购词汇）
  - treasury_strategy: Treasury Wine战略主题（标题品牌+战略词汇）
  - treasury_financial: Treasury Wine财务主题（财报相关）

高级搜索功能:
  - 自动多字段搜索（标题+全文）
  - 布尔逻辑组合（AND/OR/NOT）
  - 通配符支持（*匹配多字符，?匹配单字符）
  - 来源自动筛选（Australian Financial Review）
        """
    )
    parser.add_argument("keyword", help="搜索关键词或使用 template:名称")
    parser.add_argument("--max-pages", type=int, default=3, help="最大搜索页数（默认: 3）")
    parser.add_argument("--min-preview-words", type=int, default=30,
                        help="预览文本最小词数（默认: 30）")
    parser.add_argument("--max-full-articles", type=int, default=20,
                        help="下载全文的最大文章数（默认: 20）")
    parser.add_argument("--headless", action="store_true", help="无头模式（不显示浏览器）")
    parser.add_argument("--show-url", action="store_true", 
                        help="显示生成的搜索URL（用于调试）")
    
    args = parser.parse_args()
    
    # 如果只需要显示URL
    if args.show_url:
        if args.keyword.startswith("template:"):
            template_name = args.keyword.replace("template:", "").strip()
            search_query = create_optimized_search(template_name)
        else:
            search_query = AdvancedSearchQuery()
            if ' ' in args.keyword:
                search_query.add_title_keyword(f'"{args.keyword}"', BooleanOperator.AND)
                search_query.add_condition(args.keyword, SearchField.ALL_TEXT, BooleanOperator.AND)
            else:
                search_query.add_condition(args.keyword, SearchField.ALL_TEXT)
                search_query.add_title_keyword(args.keyword, BooleanOperator.OR)
        
        print(search_query.get_search_summary())
        print("\n" + "="*80)
        print("Generated Search URL:")
        print("="*80)
        print(search_query.build_url())
        return 0
    
    scraper = NewsBankSmartScraper(
        headless=args.headless,
        max_pages=args.max_pages,
        min_preview_words=args.min_preview_words,
        max_full_articles=args.max_full_articles
    )
    stats = asyncio.run(scraper.scrape(args.keyword))
    
    return 0 if stats["downloaded_full"] > 0 else 1


if __name__ == "__main__":
    exit(main())
