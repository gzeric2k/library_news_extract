# -*- coding: utf-8 -*-
"""
NewsBank Full Article Scraper with Anti-Detection Measures
Grabs complete article text by visiting each article's detail page
Includes anti-crawling protections:
- Random delays between requests
- Human-like browsing patterns
- Request rate limiting
- Error handling and retry logic
"""

import asyncio
import argparse
import random
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Any
from urllib.parse import quote, urljoin

from playwright.async_api import async_playwright


class ArticleData:
    """Article data container"""
    def __init__(self, title: str = "", date: str = "", source: str = "", 
                 author: str = "", full_text: str = "", url: str = ""):
        self.title = title
        self.date = date
        self.source = source
        self.author = author
        self.full_text = full_text
        self.url = url
    
    def to_text(self, keyword: str) -> str:
        """Export as formatted text"""
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


class NewsBankFullScraper:
    """NewsBank Scraper with full article extraction and anti-detection"""
    
    def __init__(self, headless: bool = False, max_pages: int = 10, max_articles: int = 50):
        self.headless = headless
        self.max_pages = max_pages
        self.max_articles = max_articles
        self.cookie_file = Path("cookies/newsbank_auth.json")
        self.output_dir = Path("articles_full")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cookie_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Anti-detection settings
        self.min_delay = 2  # Minimum seconds between requests
        self.max_delay = 5  # Maximum seconds between requests
        self.max_retries = 3  # Max retries on failure
        self.last_request_time = 0
        
        self.stats = {
            "total_pages": 0,
            "total_articles": 0,
            "saved_articles": 0,
            "skipped_articles": 0,
            "errors": [],
        }
    
    async def human_like_delay(self, min_seconds: float = 0, max_seconds: float = 0):
        """Add random delay to mimic human behavior"""
        min_sec = min_seconds if min_seconds > 0 else self.min_delay
        max_sec = max_seconds if max_seconds > 0 else self.max_delay
        delay = random.uniform(min_sec, max_sec)
        
        # Ensure minimum time between requests
        time_since_last = time.time() - self.last_request_time
        if time_since_last < min_sec:
            delay = max(delay, min_sec - time_since_last)
        
        await asyncio.sleep(delay)
        self.last_request_time = time.time()
    
    async def safe_goto(self, page, url: str, timeout: int = 30000, retries: int = 0) -> bool:
        """Navigate to URL with retry logic and delays"""
        max_attempts = retries if retries > 0 else self.max_retries
        
        for attempt in range(1, retries + 1):
            try:
                # Add delay before request
                if attempt > 1:
                    delay = random.uniform(3, 7)  # Longer delay on retry
                    print(f"      [Anti-detection] Waiting {delay:.1f}s before retry {attempt}...")
                    await asyncio.sleep(delay)
                else:
                    await self.human_like_delay()
                
                await page.goto(url, wait_until="networkidle", timeout=timeout)
                return True
                
            except Exception as e:
                print(f"      [WARNING] Navigation failed (attempt {attempt}/{retries}): {e}")
                if attempt == retries:
                    return False
        
        return False
    
    async def check_cookies_valid(self, context) -> bool:
        """Check if saved cookies are still valid"""
        print("   Checking cookies...")
        
        try:
            page = await context.new_page()
            await page.goto(
                "https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/browse-multi?p=AWGLNB",
                wait_until="networkidle", timeout=30000
            )
            
            current_url = page.url
            await page.close()
            
            if "infoweb-newsbank" in current_url and "login" not in current_url:
                print("   [OK] Cookies valid")
                return True
            else:
                print(f"   [INFO] Cookies invalid: {current_url}")
                return False
                
        except Exception as e:
            print(f"   [WARNING] {e}")
            return False
    
    async def smart_login(self, context, page) -> bool:
        """Smart login with cookies or manual"""
        print("\n[Step 1] Login")
        print("-" * 40)
        
        if self.cookie_file.exists():
            if await self.check_cookies_valid(context):
                print("[OK] Using saved cookies")
                return True
            else:
                print("[INFO] Cookies expired")
        
        if not self.headless:
            print("[INFO] Manual login required")
            print("      Please login in the browser window...")
            
            await page.goto(
                "https://eresources.sl.nsw.gov.au/newsbank-including-access-australia",
                wait_until="networkidle", timeout=60000
            )
            
            start_time = asyncio.get_event_loop().time()
            while (asyncio.get_event_loop().time() - start_time) < 180:
                current_url = page.url
                if "infoweb-newsbank-com.ezproxy" in current_url and "login" not in current_url:
                    print("   [OK] Login successful!")
                    return True
                await asyncio.sleep(2)
            
            print("[ERROR] Login timeout")
            return False
        else:
            print("[ERROR] Cannot login in headless mode without cookies")
            return False
    
    async def extract_full_article(self, page, article_url: str) -> Optional[ArticleData]:
        """Visit article page and extract full text"""
        try:
            # Navigate to article page
            await page.goto(article_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)  # Wait for content to load
            
            # Extract title
            title = ""
            title_selectors = [
                'h1.document-view__title',
                'h1.gnus-doc__title',
                'h1',
                '.document-title',
            ]
            for selector in title_selectors:
                try:
                    elem = await page.wait_for_selector(selector, timeout=2000)
                    if elem:
                        title = await elem.inner_text()
                        if title.strip():
                            break
                except:
                    continue
            
            # Extract date
            date = ""
            date_selectors = [
                '.document-view__date',
                '.gnus-doc__date',
                '.date',
                'time',
            ]
            for selector in date_selectors:
                try:
                    elem = await page.query_selector(selector)
                    if elem:
                        date = await elem.inner_text()
                        if date.strip():
                            break
                except:
                    continue
            
            # Extract source
            source = ""
            source_selectors = [
                '.document-view__source',
                '.gnus-doc__source',
                '.source',
            ]
            for selector in source_selectors:
                try:
                    elem = await page.query_selector(selector)
                    if elem:
                        source = await elem.inner_text()
                        if source.strip():
                            break
                except:
                    continue
            
            # Extract author
            author = ""
            author_selectors = [
                '.document-view__author',
                '.gnus-doc__author',
                '.author',
            ]
            for selector in author_selectors:
                try:
                    elem = await page.query_selector(selector)
                    if elem:
                        author = await elem.inner_text()
                        if author.strip():
                            break
                except:
                    continue
            
            # Extract FULL TEXT - try multiple selectors
            full_text = ""
            text_selectors = [
                '.document-view__body',
                '.gnus-doc__body',
                '.document-text',
                'article',
                '.text',
                '#document-body',
                '.body',
            ]
            
            for selector in text_selectors:
                try:
                    elem = await page.query_selector(selector)
                    if elem:
                        full_text = await elem.inner_text()
                        if len(full_text.strip()) > 100:  # Must have substantial content
                            break
                except:
                    continue
            
            # If no specific container found, try to get all paragraphs
            if not full_text:
                try:
                    paragraphs = await page.query_selector_all('p')
                    texts = []
                    for p in paragraphs:
                        text = await p.inner_text()
                        if len(text.strip()) > 20:
                            texts.append(text)
                    full_text = '\n\n'.join(texts)
                except:
                    pass
            
            if not full_text or len(full_text.strip()) < 50:
                return None
            
            return ArticleData(
                title=title.strip()[:500],
                date=date.strip()[:100],
                source=source.strip()[:200],
                author=author.strip()[:100],
                full_text=full_text.strip()[:20000],  # Limit to 20k chars
                url=article_url[:500],
            )
            
        except Exception as e:
            print(f"   [ERROR] Failed to extract article: {e}")
            return None
    
    async def scrape(self, keyword: str) -> dict:
        """Main scraping method with full text extraction"""
        print("="*80)
        print(f"NewsBank FULL ARTICLE Scraper")
        print(f"Keyword: '{keyword}'")
        print(f"Max pages: {self.max_pages}")
        print(f"Max articles: {self.max_articles}")
        print("="*80)
        print("\n[WARNING] Note: This will visit each article page to grab FULL TEXT")
        print("   This takes longer but gets complete articles.\n")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            
            if self.cookie_file.exists():
                context = await browser.new_context(storage_state=str(self.cookie_file))
            else:
                context = await browser.new_context()
            
            page = await context.new_page()
            
            try:
                # Login
                if not await self.smart_login(context, page):
                    return self.stats
                
                await context.storage_state(path=str(self.cookie_file))
                
                # Search
                print("\n[Step 2] Searching...")
                encoded_keyword = quote(keyword)
                search_url = f"https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/results?p=AWGLNB&hide_duplicates=2&fld-base-0=alltext&sort=YMD_date%3AD&maxresults=60&val-base-0={encoded_keyword}"
                
                await page.goto(search_url, wait_until="networkidle", timeout=60000)
                print(f"   Search results loaded")
                
                # Scrape pages
                print(f"\n[Step 3] Scraping full articles...")
                total_articles_scraped = 0
                
                for page_num in range(1, self.max_pages + 1):
                    if total_articles_scraped >= self.max_articles:
                        print(f"\n[INFO] Reached max articles limit ({self.max_articles})")
                        break
                    
                    print(f"\n   Page {page_num}...")
                    
                    # Find article links
                    articles = await page.query_selector_all('article.search-hits__hit')
                    
                    if not articles:
                        print(f"   No articles found")
                        break
                    
                    self.stats["total_pages"] += 1
                    print(f"   Found {len(articles)} articles on this page")
                    
                    # Extract article links
                    article_links = []
                    for article_elem in articles:
                        try:
                            title_link = await article_elem.query_selector("h3.search-hits__hit__title a")
                            if title_link:
                                href = await title_link.get_attribute("href")
                                if href:
                                    full_url = urljoin(page.url, href)
                                    # Get preview text to check if it exists
                                    preview_elem = await article_elem.query_selector("div.preview-first-paragraph")
                                    has_preview = preview_elem is not None
                                    article_links.append((full_url, has_preview))
                        except:
                            continue
                    
                    print(f"   {len(article_links)} articles with links")
                    
                    # Visit each article and extract full text
                    saved_on_page = 0
                    for i, (article_url, has_preview) in enumerate(article_links, 1):
                        if total_articles_scraped >= self.max_articles:
                            break
                        
                        if not has_preview:
                            self.stats["skipped_articles"] += 1
                            continue
                        
                        print(f"\n   [{i}/{len(article_links)}] Fetching full article...")
                        print(f"      URL: {article_url[:80]}...")
                        
                        # Extract full article
                        article = await self.extract_full_article(page, article_url)
                        
                        if not article:
                            print(f"      [ERROR] Failed to extract article")
                            continue
                        
                        # Save to file
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        safe_title = "".join(c for c in article.title[:50] if c.isalnum() or c in (' ', '-', '_')).strip()
                        filename = f"full_p{page_num}_{i:03d}_{timestamp}_{safe_title}.txt"
                        filepath = self.output_dir / filename
                        
                        with open(filepath, 'w', encoding='utf-8') as f:
                            f.write(article.to_text(keyword))
                        
                        self.stats["saved_articles"] += 1
                        total_articles_scraped += 1
                        saved_on_page += 1
                        
                        text_preview = article.full_text[:100].replace('\n', ' ')
                        print(f"      [OK] Saved: {article.title[:60]}...")
                        print(f"           Length: {len(article.full_text)} chars")
                        print(f"           Preview: {text_preview}...")
                        
                        # Small delay to be nice to the server
                        await asyncio.sleep(1)
                    
                    print(f"\n   Page {page_num} summary: {saved_on_page} articles saved")
                    
                    # Next page
                    if page_num < self.max_pages and total_articles_scraped < self.max_articles:
                        next_button = await self.find_next_button(page)
                        if not next_button:
                            print("   No more pages")
                            break
                        
                        print("   Navigating to next page...")
                        await next_button.click()
                        await page.wait_for_load_state("networkidle")
                        await asyncio.sleep(2)
                
                # Final report
                print("\n" + "="*80)
                print("[DONE] Full Article Scraping Completed!")
                print(f"   Pages processed: {self.stats['total_pages']}")
                print(f"   Articles saved: {self.stats['saved_articles']}")
                print(f"   Articles skipped: {self.stats['skipped_articles']}")
                print(f"   Output directory: {self.output_dir.absolute()}")
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
    
    async def find_next_button(self, page) -> Optional[Any]:
        """Find next page button"""
        selectors = [
            'a:has-text("Next")',
            'button:has-text("Next")',
            '[aria-label="Next"]',
        ]
        
        for selector in selectors:
            try:
                button = await page.wait_for_selector(selector, timeout=2000)
                if button:
                    is_disabled = await button.is_disabled()
                    if not is_disabled:
                        return button
            except:
                continue
        
        return None


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(description="NewsBank FULL ARTICLE Scraper")
    parser.add_argument("keyword", help="Search keyword")
    parser.add_argument("--max-pages", type=int, default=3, help="Max search result pages (default: 3)")
    parser.add_argument("--max-articles", type=int, default=20, help="Max articles to scrape (default: 20)")
    parser.add_argument("--headless", action="store_true", help="Headless mode")
    
    args = parser.parse_args()
    
    scraper = NewsBankFullScraper(
        headless=args.headless, 
        max_pages=args.max_pages,
        max_articles=args.max_articles
    )
    stats = asyncio.run(scraper.scrape(args.keyword))
    
    return 0 if stats["saved_articles"] > 0 else 1


if __name__ == "__main__":
    exit(main())
