# -*- coding: utf-8 -*-
"""
NewsBank Scraper with Smart Auto-Login
Intelligently uses saved cookies or auto-login with credentials
"""

import asyncio
import argparse
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple, Any

from playwright.async_api import async_playwright, Page
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


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
    """NewsBank Scraper with Smart Auto-Login"""
    
    def __init__(self, headless: bool = False, max_pages: int = 10):
        self.headless = headless
        self.max_pages = max_pages
        self.cookie_file = Path("cookies/newsbank_auth.json")
        self.output_dir = Path(os.getenv("OUTPUT_DIR", "articles"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cookie_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Load credentials from environment
        self.login_type = os.getenv("LOGIN_TYPE", "")
        self.public_library_card = os.getenv("PUBLIC_LIBRARY_CARD", "")
        self.library_member_username = os.getenv("LIBRARY_MEMBER_USERNAME", "")
        self.library_member_password = os.getenv("LIBRARY_MEMBER_PASSWORD", "")
        self.login_timeout = int(os.getenv("LOGIN_TIMEOUT", "120"))
        
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
            "browse": "https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/browse-multi?p=AWGLNB&t=favorite%3AAFRWAFRN%21Australian%2520Financial%2520Review%2520Collection&action=browse",
            "search": "https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/easy-search?p=AWGLNB"
        }
    
    async def check_cookies_valid(self, context) -> bool:
        """Check if saved cookies are still valid by accessing NewsBank"""
        print("   Checking if saved cookies are valid...")
        
        try:
            page = await context.new_page()
            
            # Try to access NewsBank directly
            await page.goto(self.urls["browse"], wait_until="networkidle", timeout=30000)
            
            current_url = page.url
            await page.close()
            
            # If we can access the browse page without redirect to login, cookies are valid
            if "infoweb-newsbank" in current_url and "login" not in current_url:
                print("   [OK] Cookies are valid!")
                return True
            else:
                print(f"   [INFO] Cookies invalid or expired. Current URL: {current_url}")
                return False
                
        except Exception as e:
            print(f"   [WARNING] Error checking cookies: {e}")
            return False
    
    async def auto_login_public_library(self, page: Page) -> bool:
        """Auto-login using public library card"""
        print("\n   [Auto-Login] Attempting Public Library login...")
        
        if not self.public_library_card:
            print("   [ERROR] PUBLIC_LIBRARY_CARD not configured in .env file")
            return False
        
        try:
            # Wait for the public library form to be visible
            await page.wait_for_selector("#login__public_library", timeout=5000)
            
            # Check if we need to select the public library tab
            public_library_radio = await page.query_selector("#login-options-selector-login_option-public_library")
            if public_library_radio:
                is_checked = await public_library_radio.is_checked()
                if not is_checked:
                    print("   Selecting 'Public library log in' tab...")
                    await public_library_radio.click()
                    await asyncio.sleep(1)
            
            # Fill in the library card number
            print(f"   Entering library card number...")
            card_input = await page.wait_for_selector("input#user", timeout=5000)
            await card_input.fill(self.public_library_card)
            
            # Click the login button
            print("   Clicking login button...")
            login_button = await page.wait_for_selector("button[type='submit']", timeout=5000)
            await login_button.click()
            
            # Wait for navigation
            print("   Waiting for login to complete...")
            await asyncio.sleep(3)
            
            # Check if login successful
            if await self.wait_for_login_complete(page, timeout=60):
                print("   [OK] Public Library auto-login successful!")
                return True
            else:
                print("   [ERROR] Public Library auto-login failed")
                return False
                
        except Exception as e:
            print(f"   [ERROR] Auto-login failed: {e}")
            return False
    
    async def auto_login_library_member(self, page: Page) -> bool:
        """Auto-login using library member credentials (handles iframe)"""
        print("\n   [Auto-Login] Attempting Library Member login...")
        
        if not self.library_member_username or not self.library_member_password:
            print("   [ERROR] LIBRARY_MEMBER_USERNAME or LIBRARY_MEMBER_PASSWORD not configured")
            return False
        
        try:
            # Wait for iframe to load
            iframe = await page.wait_for_selector("#member-sso-login-frame", timeout=10000)
            
            # Get iframe content
            frame = await iframe.content_frame()
            if not frame:
                print("   [ERROR] Could not access login iframe")
                return False
            
            print("   Filling in login credentials in iframe...")
            
            # Fill username
            username_input = await frame.wait_for_selector("input[name='username'], input#username, input[type='text']", timeout=5000)
            await username_input.fill(self.library_member_username)
            
            # Fill password
            password_input = await frame.wait_for_selector("input[name='password'], input#password, input[type='password']", timeout=5000)
            await password_input.fill(self.library_member_password)
            
            # Click login button
            login_button = await frame.wait_for_selector("button[type='submit'], input[type='submit']", timeout=5000)
            await login_button.click()
            
            # Wait for navigation
            print("   Waiting for login to complete...")
            await asyncio.sleep(3)
            
            # Check if login successful
            if await self.wait_for_login_complete(page, timeout=60):
                print("   [OK] Library Member auto-login successful!")
                return True
            else:
                print("   [ERROR] Library Member auto-login failed")
                return False
                
        except Exception as e:
            print(f"   [ERROR] Auto-login failed: {e}")
            return False
    
    async def wait_for_login_complete(self, page: Page, timeout: int = 120) -> bool:
        """Wait for login to complete (either manual or auto)"""
        print("   Waiting for login completion...")
        start_time = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            current_url = page.url
            print(f"   Current URL: {current_url}")
            
            # Check if we're on NewsBank
            if "infoweb-newsbank-com.ezproxy" in current_url and "login" not in current_url:
                print("   [OK] Login complete!")
                return True
            
            # Check if on results/browse page
            if "/apps/news/results" in current_url or "/apps/news/browse" in current_url:
                print("   [OK] Login complete!")
                return True
            
            await asyncio.sleep(2)
        
        return False
    
    async def manual_login(self, page: Page) -> bool:
        """Fallback to manual login"""
        print("\n" + "="*60)
        print("[INFO] Manual Login Required")
        print("="*60)
        print("Please complete login in the browser window:")
        print("1. Select your login method (Library member / Public library)")
        print("2. Enter your credentials")
        print("3. The script will auto-detect successful login")
        print("\nWaiting for you to complete login...")
        print("="*60 + "\n")
        
        if await self.wait_for_login_complete(page, timeout=180):
            print("   [OK] Manual login successful!")
            return True
        else:
            print("   [ERROR] Manual login timeout")
            return False
    
    async def smart_login(self, context, page) -> bool:
        """Smart login: try cookies -> auto-login -> manual"""
        print("\n[Step 1] Smart Login Process")
        print("-" * 40)
        
        # Try 1: Check if we already have valid cookies
        if self.cookie_file.exists():
            if await self.check_cookies_valid(context):
                print("[OK] Using saved cookies (valid)")
                return True
            else:
                print("[INFO] Saved cookies expired or invalid")
        
        # Try 2: Auto-login with credentials
        if self.login_type:
            print(f"[INFO] Attempting auto-login (type: {self.login_type})...")
            
            # Navigate to login page
            await page.goto(self.urls["login"], wait_until="networkidle", timeout=60000)
            
            if self.login_type == "public_library":
                if await self.auto_login_public_library(page):
                    return True
            elif self.login_type == "library_member":
                if await self.auto_login_library_member(page):
                    return True
            
            print("[WARNING] Auto-login failed, falling back to manual login...")
        else:
            print("[INFO] No auto-login credentials configured")
            # Navigate to login page
            await page.goto(self.urls["login"], wait_until="networkidle", timeout=60000)
        
        # Try 3: Manual login
        if not self.headless:
            if await self.manual_login(page):
                return True
        else:
            print("[ERROR] Cannot use manual login in headless mode")
            print("[INFO] Please run once without --headless to login and save cookies")
            return False
        
        return False
    
    async def find_search_input(self, page) -> Optional[Any]:
        """Find search input field"""
        selectors = [
            'input[name="val-base-0"]',
            'input.simple-search__text-field',
            'input[placeholder*="keyword" i]',
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
                    if len(text.strip()) > 20:
                        return True, text.strip()[:1000]
            except:
                continue
        
        return False, ""
    
    async def extract_article(self, element, page_num: int) -> Optional[ArticleData]:
        """Extract article data from element"""
        try:
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
            
            has_preview, preview = await self.has_preview_text(element)
            if not has_preview:
                return None
            
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
        print(f"NewsBank Scraper with Smart Auto-Login")
        print(f"Keyword: '{keyword}'")
        print(f"Max pages: {self.max_pages}")
        print("="*60)
        
        # Show login configuration
        if self.login_type:
            print(f"\n[Config] Auto-login enabled: {self.login_type}")
        else:
            print(f"\n[Config] Auto-login not configured, will use manual login")
        print(f"[Config] Cookies file: {self.cookie_file}")
        print(f"[Config] Headless mode: {self.headless}")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            
            # Create context (with or without cookies)
            if self.cookie_file.exists():
                context = await browser.new_context(storage_state=str(self.cookie_file))
            else:
                context = await browser.new_context()
            
            page = await context.new_page()
            
            try:
                # Smart login process
                if not await self.smart_login(context, page):
                    print("[ERROR] Login failed")
                    return self.stats
                
                # Save cookies after successful login
                if os.getenv("SAVE_COOKIES", "true").lower() == "true":
                    await context.storage_state(path=str(self.cookie_file))
                    print("[OK] Cookies saved for future use")
                
                # Navigate to browse page
                print("\n[Step 2] Navigating to browse page...")
                await page.goto(self.urls["browse"], wait_until="networkidle", timeout=60000)
                print(f"   URL: {page.url}")
                
                # Search
                print("\n[Step 3] Searching...")
                search_input = await self.find_search_input(page)
                if not search_input:
                    print("[ERROR] Search input not found")
                    return self.stats
                
                # Clear existing text and enter new keyword
                print(f"   Clearing search box and entering: '{keyword}'")
                await search_input.click()
                await search_input.fill("")  # Clear first
                await asyncio.sleep(0.3)
                await search_input.fill(keyword)
                await asyncio.sleep(0.5)
                await search_input.press("Enter")
                
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)
                print("   Search results loaded")
                
                # Scrape pages
                print(f"\n[Step 4] Scraping articles...")
                
                for page_num in range(1, self.max_pages + 1):
                    print(f"\n   Page {page_num}...")
                    
                    articles = await page.query_selector_all('article, .article, .result, [class*="result"]')
                    
                    if not articles:
                        print(f"   No articles found")
                        break
                    
                    self.stats["total_pages"] += 1
                    self.stats["total_articles"] += len(articles)
                    
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
    parser = argparse.ArgumentParser(
        description="NewsBank Scraper with Smart Auto-Login"
    )
    parser.add_argument("keyword", help="Search keyword")
    parser.add_argument("--max-pages", type=int, default=10, help="Max pages")
    parser.add_argument("--headless", action="store_true", help="Headless mode")
    
    args = parser.parse_args()
    
    scraper = NewsBankScraper(headless=args.headless, max_pages=args.max_pages)
    stats = asyncio.run(scraper.scrape(args.keyword))
    
    return 0 if stats["saved_articles"] > 0 else 1


if __name__ == "__main__":
    exit(main())
