# -*- coding: utf-8 -*-
"""
NewsBank Smart Scraper - Auto Total Pages Detection
Automatically detects total pages and supports page range selection
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
    """Smart scraper with auto page detection"""
    
    def __init__(self, headless: bool = False, max_pages: int = 0,
                 min_preview_words: int = 30, max_full_articles: int = 50,
                 start_page: int = 1, end_page: int = 0):
        self.headless = headless
        self.max_pages = max_pages  # 0 means auto-detect all
        self.min_preview_words = min_preview_words
        self.max_full_articles = max_full_articles
        self.start_page = start_page
        self.end_page = end_page  # 0 means no limit
        
        self.cookie_file = Path("cookies/newsbank_auth.json")
        self.output_dir = Path("articles_smart")
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
    
    async def detect_total_pages(self, page) -> Tuple[int, int]:
        """Detect total number of pages and results from the page
        Returns: (total_pages, total_results)
        """
        print("\n[Detecting total pages and results...]")
        
        total_pages = 0
        total_results = 0
        
        # Method 1: Look for "X Results" text
        try:
            # Try to find results count in meta section
            results_meta = await page.query_selector('.search-hits__meta--total_hits')
            if results_meta:
                text = await results_meta.inner_text()
                # Extract number from text like "22,460 Results"
                match = re.search(r'([\d,]+)\s*Results?', text)
                if match:
                    total_results = int(match.group(1).replace(',', ''))
                    print(f"   Total results found: {total_results:,}")
        except:
            pass
        
        # Method 2: Look for pagination
        try:
            # Check for page numbers in pagination
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
                print(f"   Total pages from pagination: {total_pages}")
        except:
            pass
        
        # Method 3: Calculate from results (60 per page)
        if total_results > 0 and total_pages == 0:
            total_pages = (total_results + 59) // 60  # Round up
            print(f"   Calculated total pages: {total_pages} (60 per page)")
        
        # Default if still not found
        if total_pages == 0:
            total_pages = 10  # Default fallback
            print(f"   Could not detect, using default: {total_pages} pages")
        
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
        """Phase 1: Quick preview scan"""
        print("\n" + "="*80)
        print("PHASE 1: Preview Scan (Quick)")
        print("="*80)
        print(f"Analyzing preview text (min {self.min_preview_words} words)...")
        print(f"Page range: {self.start_page} to {self.end_page if self.end_page else 'auto'}\n")
        
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
            
            print(f"\n   Will scan pages {self.start_page} to {self.end_page}")
            print(f"   (Total available: {self.total_pages_detected} pages, {self.total_results:,} results)\n")
        
        current_page = self.start_page
        
        while current_page <= self.end_page:
            print(f"Scanning page {current_page}/{self.end_page}...")
            
            # Navigate to specific page if not on page 1
            if current_page > 1:
                # Try to click next or navigate directly
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
                            # Check if disabled
                            is_disabled = await next_button.is_disabled()
                            if not is_disabled:
                                break
                            else:
                                next_button = None
                    except:
                        continue
                
                if not next_button:
                    print(f"   No next button found, ending scan at page {current_page-1}")
                    break
                
                await next_button.click()
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(1)
            
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
                        status = "[QUALITY]"
                    else:
                        self.stats["skipped_low_quality"] += 1
                        status = "[SKIP]"
                    
                    # Print first few and quality ones
                    if i <= 5 or has_quality:
                        print(f"   {status} #{i}: {title[:55]}... ({word_count}w)")
                
                except Exception as e:
                    continue
            
            print(f"   Page {current_page}: {page_quality_count}/{len(articles)} quality\n")
            
            current_page += 1
            
            # Brief delay between pages
            if current_page <= self.end_page:
                await asyncio.sleep(0.5)
        
        return article_index_list
    
    async def phase2_download_full(self, page, keyword: str, quality_articles: List[ArticleIndex]):
        """Phase 2: Download full text for quality articles"""
        print("\n" + "="*80)
        print("PHASE 2: Full-Text Download")
        print("="*80)
        
        total_quality = len(quality_articles)
        to_download = min(total_quality, self.max_full_articles)
        
        print(f"Quality articles: {total_quality}")
        print(f"Will download: {to_download}\n")
        
        downloaded_count = 0
        
        for i, article in enumerate(quality_articles[:to_download], 1):
            print(f"\n[{i}/{to_download}] Downloading...")
            print(f"   Title: {article.title[:65]}...")
            print(f"   Preview: {article.word_count} words")
            
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
                    print(f"   [WARNING] No full text")
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
                
                print(f"   [OK] {len(full_text)} chars saved")
                
            except Exception as e:
                print(f"   [ERROR] {e}")
                continue
        
        return downloaded_count
    
    async def scrape(self, keyword: str) -> dict:
        """Main scraping method"""
        print("="*80)
        print(f"NewsBank Smart Scraper - Auto Page Detection")
        print(f"Keyword: '{keyword}'")
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
                    test_page = await context.new_page()
                    await test_page.goto(
                        "https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/browse-multi?p=AWGLNB",
                        wait_until="networkidle", timeout=30000
                    )
                    
                    if "infoweb-newsbank" in test_page.url and "login" not in test_page.url:
                        print("[OK] Cookies valid")
                        await test_page.close()
                    else:
                        print("[INFO] Cookies expired")
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
                
                # Search
                print("\n[Searching]")
                print("-" * 40)
                encoded_keyword = quote(keyword)
                search_url = f"https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/results?p=AWGLNB&hide_duplicates=2&fld-base-0=alltext&sort=YMD_date%3AD&maxresults=60&val-base-0={encoded_keyword}"
                
                await page.goto(search_url, wait_until="networkidle", timeout=60000)
                print(f"Results loaded: {(await page.title()).split('|')[0].strip()}")
                
                # Phase 1
                self.article_index = await self.phase1_preview_scan(page, keyword)
                
                # Save index
                index_path = self.output_dir / f"index_{keyword.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                with open(index_path, 'w', encoding='utf-8') as f:
                    json.dump([a.to_dict() for a in self.article_index], f, indent=2, ensure_ascii=False)
                print(f"\nIndex saved: {index_path}")
                
                # Filter quality
                quality_articles = [a for a in self.article_index if a.has_substantial_content]
                
                if not quality_articles:
                    print("\n[WARNING] No quality articles found")
                    return self.stats
                
                # Phase 2
                downloaded = await self.phase2_download_full(page, keyword, quality_articles)
                
                # Report
                print("\n" + "="*80)
                print("[DONE] Scraping Completed!")
                print("="*80)
                print(f"Pages scanned: {self.stats['total_pages']}")
                print(f"Articles previewed: {self.stats['total_previewed']}")
                print(f"Quality articles: {self.stats['quality_articles']}")
                print(f"Low quality: {self.stats['skipped_low_quality']}")
                print(f"Full articles: {self.stats['downloaded_full']}")
                print(f"Output: {self.output_dir.absolute()}")
                print("="*80)
                
                if not self.headless:
                    print("\n[INFO] Browser open for 10 seconds...")
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
    parser = argparse.ArgumentParser(description="NewsBank Smart Scraper - Auto Page Detection")
    parser.add_argument("keyword", help="Search keyword")
    
    # Page range options
    page_group = parser.add_mutually_exclusive_group()
    page_group.add_argument("--all-pages", action="store_true",
                           help="Scan ALL available pages (use with caution!)")
    page_group.add_argument("--max-pages", type=int, default=10,
                           help="Maximum pages to scan (default: 10)")
    
    parser.add_argument("--start-page", type=int, default=1,
                       help="Start from page N (default: 1)")
    parser.add_argument("--end-page", type=int, default=0,
                       help="End at page N (0 = auto-detect, default: 0)")
    
    # Quality filters
    parser.add_argument("--min-preview-words", type=int, default=30,
                       help="Min words in preview (default: 30)")
    parser.add_argument("--max-full-articles", type=int, default=20,
                       help="Max articles to download (default: 20)")
    
    parser.add_argument("--headless", action="store_true", help="Headless mode")
    
    args = parser.parse_args()
    
    # Calculate max_pages based on arguments
    max_pages = 0 if args.all_pages else args.max_pages
    
    scraper = NewsBankSmartScraper(
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
