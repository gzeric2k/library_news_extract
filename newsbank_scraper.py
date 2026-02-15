# -*- coding: utf-8 -*-
"""
NewsBank Production Scraper
Search and save articles from NewsBank Australian Financial Review

Usage:
    python newsbank_scraper.py "Nick Scali" --max-pages 5
    python newsbank_scraper.py "Your Keyword" --headless
"""

import asyncio
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Any, Tuple

from playwright.async_api import async_playwright


class ArticleData:
    """Article data container"""
    def __init__(self, title: str = "", date: str = "", preview: str = "", 
                 url: str = "", page_number: int = 0):
        self.title = title
        self.date = date
        self.preview = preview
        self.url = url
        self.page_number = page_number
    
    def to_text(self, keyword: str) -> str:
        """Export as formatted text"""
        return f"""Title: {self.title}
Date: {self.date}
Keyword: {keyword}
Page: {self.page_number}
Scraped at: {datetime.now().isoformat()}

Preview:
{self.preview}

{'='*60}
"""


class NewsBankScraper:
    """Production-ready NewsBank Scraper"""
    
    def __init__(self, headless: bool = False, max_pages: int = 10):
        self.headless = headless
        self.max_pages = max_pages
        self.cookie_file = Path("cookies/newsbank_auth.json")
        self.output_dir = Path("articles")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cookie_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Statistics
        self.stats = {
            "total_pages": 0,
            "total_articles": 0,
            "saved_articles": 0,
            "skipped_articles": 0,
            "errors": [],
        }
        
        self.urls = {
            "login": "https://eresources.sl.nsw.gov.au/newsbank-including-access-australia",
            "browse": "https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/browse-multi?p=AWGLNB&t=favorite%3AAFRWAFRN%21Australian%2520Financial%2520Review%2520Collection&action=browse"
        }
    
    async def wait_for_login(self, page, timeout: int = 180) -> bool:
        """Auto-detect successful login including proxy authentication"""
        print("   Waiting for login (auto-detection)...")
        start_time = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            current_url = page.url
            print(f"   Current URL: {current_url}")
            
            # Check if we're on the actual NewsBank site (not just in URL params)
            if "infoweb-newsbank-com.ezproxy" in current_url and "login" not in current_url:
                print(f"   [OK] Login successful!")
                return True
            
            # Check if we're on results page
            if "/apps/news/results" in current_url or "/apps/news/browse" in current_url:
                print(f"   [OK] Login successful!")
                return True
            
            await asyncio.sleep(2)
        
        return False
    
    async def find_search_input(self, page) -> Optional[Any]:
        """Find search input field"""
        # NewsBank specific selectors (based on actual HTML structure)
        selectors = [
            'input[name="val-base-0"]',  # Primary selector
            'input.simple-search__text-field',
            'input[placeholder*="keyword" i]',
            'input[placeholder*="Enter any keyword" i]',
            '#edit-val-base-0--4',
            'input[type="text"].form-text',
        ]
        
        for selector in selectors:
            try:
                element = await page.wait_for_selector(selector, timeout=3000)
                if element:
                    elem_type = await element.get_attribute('type')
                    if elem_type not in ['radio', 'checkbox', 'hidden', 'submit']:
                        print(f"   [OK] Found search input: {selector}")
                        return element
            except:
                continue
        
        return None
    
    async def find_next_button(self, page) -> Optional[Any]:
        """Find next page button"""
        selectors = [
            'a:has-text("Next")',
            'button:has-text("Next")',
            '[aria-label="Next"]',
            'a:has-text("下一页")',
            '[rel="next"]',
            '.pagination a:has-text("Next")',
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
    
    async def has_preview_text(self, element) -> Tuple[bool, str]:
        """Check if article has preview text"""
        preview_selectors = [
            '.preview', '.snippet', '.summary', '.description',
            'p', '.abstract', '.excerpt',
        ]
        
        for selector in preview_selectors:
            try:
                preview_elem = await element.query_selector(selector)
                if preview_elem:
                    text = await preview_elem.inner_text()
                    if len(text.strip()) > 20:  # At least 20 chars
                        return True, text.strip()[:1000]
            except:
                continue
        
        # Try getting any text content
        try:
            full_text = await element.inner_text()
            lines = [line.strip() for line in full_text.split('\n') if line.strip()]
            if len(lines) >= 2:
                # Assume second line or longer lines might be preview
                for line in lines[1:]:
                    if len(line) > 50:
                        return True, line[:1000]
        except:
            pass
        
        return False, ""
    
    async def extract_article(self, element, page_num: int) -> Optional[ArticleData]:
        """Extract article data from element"""
        try:
            # Get title
            title_selectors = ['h2', 'h3', 'h4', '.title', 'a:first-child', '[class*="title"]']
            title = ""
            for selector in title_selectors:
                try:
                    elem = await element.query_selector(selector)
                    if elem:
                        title = await elem.inner_text()
                        if title.strip():
                            break
                except:
                    continue
            
            # Get date
            date_selectors = ['.date', 'time', '[class*="date"]', '[datetime]']
            date = ""
            for selector in date_selectors:
                try:
                    elem = await element.query_selector(selector)
                    if elem:
                        date = await elem.inner_text()
                        if date.strip():
                            break
                except:
                    continue
            
            # Get preview
            has_preview, preview = await self.has_preview_text(element)
            if not has_preview:
                return None
            
            # Get URL
            url = ""
            try:
                link = await element.query_selector('a')
                if link:
                    url = await link.get_attribute('href') or ""
            except:
                pass
            
            return ArticleData(
                title=title.strip()[:500],
                date=date.strip()[:100],
                preview=preview,
                url=url[:1000],
                page_number=page_num,
            )
            
        except Exception as e:
            return None
    
    async def scrape(self, keyword: str) -> dict:
        """Main scraping method"""
        print("="*60)
        print(f"NewsBank Scraper - Keyword: '{keyword}'")
        print(f"Max pages: {self.max_pages}")
        print("="*60)
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            
            # Load cookies if available
            if self.cookie_file.exists():
                print(f"[OK] Loading saved session")
                context = await browser.new_context(storage_state=str(self.cookie_file))
            else:
                print("[INFO] No saved session, manual login required")
                context = await browser.new_context()
            
            page = await context.new_page()
            
            try:
                # Step 1: Login
                print("\n[Step 1] Checking login status...")
                await page.goto(self.urls["login"], wait_until="networkidle", timeout=60000)
                
                if any(x in page.url.lower() for x in ["sl.nsw", "login", "access"]):
                    if not self.headless:
                        print("[INFO] Please login in the browser window")
                        print("      You may need to complete both:")
                        print("      1. Library member login")
                        print("      2. Proxy authentication (if prompted)")
                        print("\n      Waiting for navigation to NewsBank...")
                        
                        if not await self.wait_for_login(page, timeout=180):
                            print("[ERROR] Login timeout")
                            return self.stats
                        
                        # Save session
                        await context.storage_state(path=str(self.cookie_file))
                        print("[OK] Session saved")
                    else:
                        print("[ERROR] Login required but running in headless mode")
                        print("[INFO] Run once without --headless to login")
                        return self.stats
                else:
                    print("[OK] Already logged in")
                
                # Step 2: Navigate to browse page
                print("\n[Step 2] Navigating to browse page...")
                await page.goto(self.urls["browse"], wait_until="networkidle", timeout=60000)
                print(f"   Current URL: {page.url}")
                
                # Check if we need additional authentication
                if "login" in page.url.lower() or "ezproxy" in page.url.lower():
                    if not self.headless:
                        print("\n   [INFO] Additional authentication required")
                        print("      Please complete the proxy login in the browser...")
                        if not await self.wait_for_login(page, timeout=120):
                            print("[ERROR] Proxy login timeout")
                            return self.stats
                        # Save updated session
                        await context.storage_state(path=str(self.cookie_file))
                        print("[OK] Updated session saved")
                    else:
                        print("[ERROR] Proxy authentication required")
                        return self.stats
                
                # Step 3: Search
                print("\n[Step 3] Searching...")
                search_input = await self.find_search_input(page)
                if not search_input:
                    print("[ERROR] Search input not found")
                    return self.stats
                
                await search_input.fill(keyword)
                await asyncio.sleep(0.5)
                await search_input.press("Enter")
                
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)
                print(f"   Search results loaded")
                
                # Step 4: Scrape pages
                print(f"\n[Step 4] Scraping articles...")
                
                for page_num in range(1, self.max_pages + 1):
                    print(f"\n   Processing page {page_num}...")
                    
                    # Find articles
                    articles = await page.query_selector_all('article, .article, .result, [class*="result"]')
                    
                    if not articles:
                        print(f"   No articles found on page {page_num}")
                        break
                    
                    self.stats["total_pages"] += 1
                    self.stats["total_articles"] += len(articles)
                    
                    print(f"   Found {len(articles)} articles")
                    
                    # Process each article
                    saved_on_page = 0
                    for i, article_elem in enumerate(articles):
                        article = await self.extract_article(article_elem, page_num)
                        
                        if not article:
                            self.stats["skipped_articles"] += 1
                            continue
                        
                        # Save to file
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        safe_title = "".join(c for c in article.title[:50] if c.isalnum() or c in (' ', '-', '_')).strip()
                        filename = f"p{page_num}_{i+1:03d}_{timestamp}_{safe_title}.txt"
                        filepath = self.output_dir / filename
                        
                        with open(filepath, 'w', encoding='utf-8') as f:
                            f.write(article.to_text(keyword))
                        
                        self.stats["saved_articles"] += 1
                        saved_on_page += 1
                        print(f"      Saved: {article.title[:60]}...")
                    
                    print(f"   Page {page_num}: {saved_on_page}/{len(articles)} articles saved")
                    
                    # Check for next page
                    if page_num < self.max_pages:
                        next_button = await self.find_next_button(page)
                        if not next_button:
                            print("   No more pages")
                            break
                        
                        await next_button.click()
                        await page.wait_for_load_state("networkidle")
                        await asyncio.sleep(2)
                
                # Final report
                print("\n" + "="*60)
                print("[DONE] Scraping completed!")
                print(f"   Pages processed: {self.stats['total_pages']}")
                print(f"   Total articles found: {self.stats['total_articles']}")
                print(f"   Articles saved: {self.stats['saved_articles']}")
                print(f"   Articles skipped (no preview): {self.stats['skipped_articles']}")
                print(f"   Output directory: {self.output_dir.absolute()}")
                print("="*60)
                
                if not self.headless:
                    print("\n[INFO] Browser will stay open for 10 seconds...")
                    await asyncio.sleep(10)
                
            except Exception as e:
                print(f"\n[ERROR] {e}")
                self.stats["errors"].append(str(e))
                import traceback
                traceback.print_exc()
            
            finally:
                await context.close()
                await browser.close()
        
        return self.stats


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Scrape articles from NewsBank Australian Financial Review"
    )
    parser.add_argument(
        "keyword",
        help="Search keyword (e.g., 'Nick Scali')"
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=10,
        help="Maximum number of pages to scrape (default: 10)"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run in headless mode (requires prior login)"
    )
    
    args = parser.parse_args()
    
    # Run scraper
    scraper = NewsBankScraper(headless=args.headless, max_pages=args.max_pages)
    stats = asyncio.run(scraper.scrape(args.keyword))
    
    return 0 if stats["saved_articles"] > 0 else 1


if __name__ == "__main__":
    exit(main())
