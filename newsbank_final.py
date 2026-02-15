# -*- coding: utf-8 -*-
"""
NewsBank Scraper - Updated for correct article extraction
"""

import asyncio
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple, Any
from urllib.parse import quote

from playwright.async_api import async_playwright


class ArticleData:
    """Article data container"""
    def __init__(self, title: str = "", date: str = "", preview: str = "", 
                 url: str = "", source: str = "", author: str = "", page_number: int = 0):
        self.title = title
        self.date = date
        self.preview = preview
        self.url = url
        self.source = source
        self.author = author
        self.page_number = page_number
    
    def to_text(self, keyword: str) -> str:
        """Export as formatted text"""
        return f"""Title: {self.title}
Date: {self.date}
Source: {self.source}
Author: {self.author}
Keyword: {keyword}
Page: {self.page_number}
Scraped at: {datetime.now().isoformat()}

Preview:
{self.preview}

{'='*60}
"""


class NewsBankScraper:
    """NewsBank Scraper"""
    
    def __init__(self, headless: bool = False, max_pages: int = 10):
        self.headless = headless
        self.max_pages = max_pages
        self.cookie_file = Path("cookies/newsbank_auth.json")
        self.output_dir = Path("articles")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cookie_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.stats = {
            "total_pages": 0,
            "total_articles": 0,
            "saved_articles": 0,
            "skipped_articles": 0,
            "errors": [],
        }
    
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
    
    async def extract_article(self, element, page_num: int) -> Optional[ArticleData]:
        """Extract article data from NewsBank search hit"""
        try:
            # Get title from h3.search-hits__hit__title
            title_elem = await element.query_selector("h3.search-hits__hit__title")
            if not title_elem:
                return None
            
            title_link = await title_elem.query_selector("a")
            if not title_link:
                return None
            
            title = await title_link.inner_text()
            # Remove "Go to the document viewer for " prefix
            title = title.replace("Go to the document viewer for ", "").strip()
            
            if not title or len(title) < 5:
                return None
            
            # Get URL
            url = await title_link.get_attribute("href") or ""
            
            # Get date from meta
            date = ""
            date_elem = await element.query_selector("li.search-hits__hit__meta__item--display-date")
            if date_elem:
                date = await date_elem.inner_text()
            
            # Get source
            source = ""
            source_elem = await element.query_selector("li.search-hits__hit__meta__item--source")
            if source_elem:
                source = await source_elem.inner_text()
            
            # Get author
            author = ""
            author_elem = await element.query_selector("li.search-hits__hit__meta__item--author")
            if author_elem:
                author = await author_elem.inner_text()
            
            # Get preview from preview-first-paragraph
            preview = ""
            preview_elem = await element.query_selector("div.preview-first-paragraph")
            if preview_elem:
                preview = await preview_elem.inner_text()
            else:
                # Fallback to search-hits__hit__preview
                preview_container = await element.query_selector("div.search-hits__hit__preview")
                if preview_container:
                    preview = await preview_container.inner_text()
            
            preview = preview.strip()[:1000]
            
            if len(preview) < 30:  # Too short, probably not a real article
                return None
            
            return ArticleData(
                title=title[:300],
                date=date.strip()[:100],
                preview=preview,
                url=url[:500],
                source=source.strip()[:200],
                author=author.strip()[:100],
                page_number=page_num,
            )
            
        except Exception as e:
            return None
    
    async def find_next_button(self, page) -> Optional[Any]:
        """Find next page button"""
        selectors = [
            'a:has-text("Next")',
            'button:has-text("Next")',
            '[aria-label="Next"]',
            'a:has-text("下一页")',
            '[rel="next"]',
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
    
    async def scrape(self, keyword: str) -> dict:
        """Main scraping method"""
        print("="*60)
        print(f"NewsBank Scraper")
        print(f"Keyword: '{keyword}'")
        print(f"Max pages: {self.max_pages}")
        print("="*60)
        
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
                
                # Build search URL and navigate directly
                print("\n[Step 2] Searching...")
                encoded_keyword = quote(keyword)
                search_url = f"https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/results?p=AWGLNB&hide_duplicates=2&fld-base-0=alltext&sort=YMD_date%3AD&maxresults=60&val-base-0={encoded_keyword}"
                
                await page.goto(search_url, wait_until="networkidle", timeout=60000)
                print(f"   URL: {page.url}")
                print(f"   Title: {await page.title()}")
                
                # Scrape pages
                print(f"\n[Step 3] Scraping articles...")
                
                for page_num in range(1, self.max_pages + 1):
                    print(f"\n   Page {page_num}...")
                    
                    # Find articles using correct selector
                    articles = await page.query_selector_all('article.search-hits__hit')
                    
                    if not articles:
                        print(f"   No articles found")
                        break
                    
                    self.stats["total_pages"] += 1
                    self.stats["total_articles"] += len(articles)
                    
                    print(f"   Found {len(articles)} articles")
                    
                    saved_on_page = 0
                    for i, article_elem in enumerate(articles, 1):
                        article = await self.extract_article(article_elem, page_num)
                        
                        if not article:
                            self.stats["skipped_articles"] += 1
                            continue
                        
                        # Save to file
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        safe_title = "".join(c for c in article.title[:40] if c.isalnum() or c in (' ', '-', '_')).strip()
                        filename = f"p{page_num}_{i:03d}_{timestamp}_{safe_title}.txt"
                        filepath = self.output_dir / filename
                        
                        with open(filepath, 'w', encoding='utf-8') as f:
                            f.write(article.to_text(keyword))
                        
                        self.stats["saved_articles"] += 1
                        saved_on_page += 1
                        print(f"      [OK] {article.title[:70]}...")
                    
                    print(f"   Saved: {saved_on_page}/{len(articles)}")
                    
                    # Next page
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
                print(f"   Pages: {self.stats['total_pages']}")
                print(f"   Articles found: {self.stats['total_articles']}")
                print(f"   Articles saved: {self.stats['saved_articles']}")
                print(f"   Articles skipped: {self.stats['skipped_articles']}")
                print(f"   Output: {self.output_dir.absolute()}")
                print("="*60)
                
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
    """CLI entry point"""
    parser = argparse.ArgumentParser(description="NewsBank Scraper")
    parser.add_argument("keyword", help="Search keyword")
    parser.add_argument("--max-pages", type=int, default=10, help="Max pages")
    parser.add_argument("--headless", action="store_true", help="Headless mode")
    
    args = parser.parse_args()
    
    scraper = NewsBankScraper(headless=args.headless, max_pages=args.max_pages)
    stats = asyncio.run(scraper.scrape(args.keyword))
    
    return 0 if stats["saved_articles"] > 0 else 1


if __name__ == "__main__":
    exit(main())
