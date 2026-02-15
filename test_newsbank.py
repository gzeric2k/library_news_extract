# -*- coding: utf-8 -*-
"""
NewsBank Test Script - Search keyword "Nick Scali"
Improved version with better selector detection
"""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright


class NewsBankTester:
    """NewsBank Tester"""
    
    def __init__(self):
        self.cookie_file = Path("cookies/newsbank_auth.json")
        self.output_dir = Path("articles")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cookie_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.urls = {
            "login": "https://eresources.sl.nsw.gov.au/newsbank-including-access-australia",
            "browse": "https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/browse-multi?p=AWGLNB&t=favorite%3AAFRWAFRN%21Australian%2520Financial%2520Review%2520Collection&action=browse"
        }
    
    async def wait_for_login(self, page, timeout=180):
        """Wait for user to complete login automatically"""
        print("   Waiting for login (up to 180 seconds)...")
        start_time = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            current_url = page.url
            
            # Check if logged in (redirected to newsbank)
            if "infoweb-newsbank" in current_url or "easy-search" in current_url:
                print(f"   [OK] Login detected! URL: {current_url}")
                return True
            
            await asyncio.sleep(2)
        
        return False
    
    async def find_search_input(self, page):
        """Find search input with multiple strategies"""
        print("   Searching for input field...")
        
        # Strategy 1: By placeholder text (exact match from requirements)
        placeholder_selectors = [
            'input[placeholder*="Enter any keyword" i]',
            'input[placeholder*="keyword" i]',
            'input[placeholder*="search" i]',
            'textarea[placeholder*="Enter any keyword" i]',
            'textarea[placeholder*="keyword" i]',
        ]
        
        for selector in placeholder_selectors:
            try:
                element = await page.wait_for_selector(selector, timeout=3000)
                if element:
                    elem_type = await element.get_attribute('type')
                    if elem_type not in ['radio', 'checkbox', 'hidden']:
                        print(f"   [OK] Found by placeholder: {selector}")
                        return element
            except:
                continue
        
        # Strategy 2: By ID or name
        id_selectors = [
            'input#search',
            'input#query',
            'input#q',
            'input[name="search"]',
            'input[name="query"]',
            'input[name="q"]',
            'input[id*="search" i]',
            'input[id*="query" i]',
        ]
        
        for selector in id_selectors:
            try:
                element = await page.wait_for_selector(selector, timeout=2000)
                if element:
                    elem_type = await element.get_attribute('type')
                    if elem_type not in ['radio', 'checkbox', 'hidden']:
                        print(f"   [OK] Found by ID/name: {selector}")
                        return element
            except:
                continue
        
        # Strategy 3: By class containing search-related terms
        class_selectors = [
            'input[class*="search" i]',
            'input[class*="query" i]',
            'textarea[class*="search" i]',
        ]
        
        for selector in class_selectors:
            try:
                element = await page.wait_for_selector(selector, timeout=2000)
                if element:
                    elem_type = await element.get_attribute('type')
                    if elem_type not in ['radio', 'checkbox', 'hidden']:
                        print(f"   [OK] Found by class: {selector}")
                        return element
            except:
                continue
        
        # Strategy 4: Get all text inputs and find the first visible one
        print("   Trying to find any visible text input...")
        try:
            inputs = await page.query_selector_all('input[type="text"], input:not([type]), textarea')
            print(f"   Found {len(inputs)} text inputs")
            
            for i, inp in enumerate(inputs):
                try:
                    is_visible = await inp.is_visible()
                    if is_visible:
                        placeholder = await inp.get_attribute('placeholder') or ""
                        elem_id = await inp.get_attribute('id') or ""
                        elem_name = await inp.get_attribute('name') or ""
                        elem_class = await inp.get_attribute('class') or ""
                        print(f"   Input {i}: placeholder='{placeholder}', id='{elem_id}', name='{elem_name}', class='{elem_class[:50]}'")
                        
                        # Return the first one that looks like a search box
                        if any(x in placeholder.lower() for x in ['keyword', 'search', 'enter']) or \
                           any(x in elem_id.lower() for x in ['search', 'query']) or \
                           any(x in elem_name.lower() for x in ['search', 'query']):
                            print(f"   [OK] Selected input {i} as search box")
                            return inp
                except:
                    continue
            
            # If no obvious search box, return the first visible text input
            for inp in inputs:
                try:
                    if await inp.is_visible():
                        print("   [OK] Using first visible text input")
                        return inp
                except:
                    continue
                    
        except Exception as e:
            print(f"   Error finding inputs: {e}")
        
        return None
    
    async def test_search(self, keyword="Nick Scali"):
        """Test search functionality"""
        print("="*60)
        print(f"NewsBank Test - Keyword: {keyword}")
        print("="*60)
        
        async with async_playwright() as p:
            # Launch browser
            browser = await p.chromium.launch(headless=False)
            
            # Check cookie file
            if self.cookie_file.exists():
                print(f"[OK] Found saved login state: {self.cookie_file}")
                context = await browser.new_context(storage_state=str(self.cookie_file))
            else:
                print("[INFO] No login state found, manual login required")
                print("[INFO] A browser window will open. Please login manually.")
                context = await browser.new_context()
            
            page = await context.new_page()
            
            try:
                # Step 1: Visit login page
                print(f"\n[Step 1] Visiting login page...")
                await page.goto(self.urls["login"], wait_until="networkidle", timeout=60000)
                print(f"   Current URL: {page.url}")
                
                # Check if login is needed
                if any(x in page.url.lower() for x in ["login", "signin", "access", "sl.nsw"]):
                    print("\n" + "="*60)
                    print("[INFO] Login Required")
                    print("="*60)
                    print("Please complete login in the browser window:")
                    print("1. Click 'Log in as a Library member'")
                    print("2. Enter your library member credentials")
                    print("3. The script will auto-detect successful login")
                    print("="*60 + "\n")
                    
                    # Auto-wait for login
                    logged_in = await self.wait_for_login(page, timeout=180)
                    
                    if not logged_in:
                        print("[ERROR] Login timeout")
                        return
                    
                    # Save login state
                    await context.storage_state(path=str(self.cookie_file))
                    print(f"[OK] Login state saved to: {self.cookie_file}")
                else:
                    print("[OK] Already logged in")
                
                # Step 2: Visit browse page
                print(f"\n[Step 2] Visiting browse page...")
                await page.goto(self.urls["browse"], wait_until="networkidle", timeout=60000)
                print(f"   Current URL: {page.url}")
                
                # Save screenshot and HTML for debugging
                screenshot_path = self.output_dir / "browse_page.png"
                await page.screenshot(path=str(screenshot_path), full_page=True)
                print(f"   Page screenshot saved: {screenshot_path}")
                
                html_path = self.output_dir / "browse_page.html"
                html_content = await page.content()
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                print(f"   Page HTML saved: {html_path}")
                
                # Step 3: Find search box using improved strategy
                print(f"\n[Step 3] Finding search box...")
                search_input = await self.find_search_input(page)
                
                if not search_input:
                    print("   [ERROR] Could not find search input")
                    print("   Please check browse_page.html to understand page structure")
                    return
                
                # Step 4: Enter keyword
                print(f"\n[Step 4] Entering keyword '{keyword}'...")
                await search_input.fill(keyword)
                await asyncio.sleep(1)
                print("   [OK] Keyword entered")
                
                # Step 5: Find and click search button
                print(f"\n[Step 5] Finding search button...")
                button_selectors = [
                    'button:has-text("Search")',
                    'button[type="submit"]',
                    'input[type="submit"]',
                    'button:has-text("Go")',
                    'a:has-text("Search")',
                    'button[class*="search" i]',
                    'input[class*="search" i][type="submit"]',
                ]
                
                search_button = None
                for selector in button_selectors:
                    try:
                        search_button = await page.wait_for_selector(selector, timeout=2000)
                        if search_button and await search_button.is_visible():
                            print(f"   [OK] Found search button: {selector}")
                            break
                    except:
                        continue
                
                # Click search or press Enter
                if search_button:
                    await search_button.click()
                    print("   [OK] Search button clicked")
                else:
                    print("   [INFO] No search button found, pressing Enter")
                    await search_input.press("Enter")
                
                # Step 6: Wait for results
                print(f"\n[Step 6] Waiting for search results...")
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(3)
                print(f"   Current URL: {page.url}")
                
                # Save screenshot and HTML of results
                results_screenshot = self.output_dir / "search_results.png"
                await page.screenshot(path=str(results_screenshot), full_page=True)
                print(f"   Search results screenshot: {results_screenshot}")
                
                results_html = self.output_dir / "search_results.html"
                results_content = await page.content()
                with open(results_html, 'w', encoding='utf-8') as f:
                    f.write(results_content)
                print(f"   Search results HTML: {results_html}")
                
                # Step 7: Find articles
                print(f"\n[Step 7] Finding articles...")
                article_selectors = [
                    'article',
                    '.article',
                    '.result',
                    '.search-result',
                    '[class*="article" i]',
                    '[class*="result" i]',
                    '.item',
                    '.hit',
                    '[data-testid*="result"]',
                ]
                
                articles = []
                for selector in article_selectors:
                    try:
                        articles = await page.query_selector_all(selector)
                        if len(articles) > 0:
                            print(f"   [OK] Found {len(articles)} articles: {selector}")
                            break
                    except:
                        continue
                
                if not articles:
                    print("   [WARNING] No articles found with standard selectors")
                    print("   Check search_results.html for page structure")
                    return
                
                # Process articles
                print(f"\n[Step 8] Processing and saving articles...")
                saved_count = 0
                
                for i, article in enumerate(articles[:10], 1):
                    try:
                        # Check if has preview text
                        preview_selectors = [
                            '.preview', '.snippet', '.summary',
                            '[class*="preview" i]', '[class*="snippet" i]',
                            'p', '.description', '.abstract',
                        ]
                        
                        has_preview = False
                        preview_text = ""
                        for selector in preview_selectors:
                            try:
                                preview_elem = await article.query_selector(selector)
                                if preview_elem:
                                    text = await preview_elem.inner_text()
                                    if len(text.strip()) > 10:
                                        has_preview = True
                                        preview_text = text.strip()[:500]
                                        break
                            except:
                                continue
                        
                        if not has_preview:
                            print(f"   Article {i}: Skipped (no preview)")
                            continue
                        
                        # Extract title
                        title_selectors = ['h2', 'h3', 'h4', '.title', 'a', '[class*="title" i]']
                        title = ""
                        for selector in title_selectors:
                            try:
                                title_elem = await article.query_selector(selector)
                                if title_elem:
                                    title = await title_elem.inner_text()
                                    if title.strip():
                                        break
                            except:
                                continue
                        
                        # Save article
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        safe_title = "".join(c for c in title[:50] if c.isalnum() or c in (' ', '-', '_')).strip()
                        filename = f"{i:03d}_{timestamp}_{safe_title}.txt"
                        filepath = self.output_dir / filename
                        
                        content = f"""Title: {title}
Keyword: {keyword}
Scraped at: {datetime.now().isoformat()}

Preview:
{preview_text}

{'='*60}
"""
                        
                        with open(filepath, 'w', encoding='utf-8') as f:
                            f.write(content)
                        
                        print(f"   [OK] Article {i}: {title[:60]}... -> {filename}")
                        saved_count += 1
                        
                    except Exception as e:
                        print(f"   [ERROR] Article {i} processing failed: {e}")
                
                print(f"\n" + "="*60)
                print(f"[DONE] Test completed!")
                print(f"   Total articles found: {len(articles)}")
                print(f"   Articles saved: {saved_count}")
                print(f"   Output directory: {self.output_dir.absolute()}")
                print(f"="*60)
                
                # Wait for user to review
                print("\n[INFO] Browser will stay open for 30 seconds...")
                await asyncio.sleep(30)
                
            except Exception as e:
                print(f"\n[ERROR] {e}")
                import traceback
                traceback.print_exc()
                
                # Save error screenshot
                try:
                    error_screenshot = self.output_dir / "error_screenshot.png"
                    await page.screenshot(path=str(error_screenshot), full_page=True)
                    print(f"   Error screenshot saved: {error_screenshot}")
                except:
                    pass
            
            finally:
                await context.close()
                await browser.close()


async def main():
    """Main function"""
    tester = NewsBankTester()
    await tester.test_search("Nick Scali")


if __name__ == "__main__":
    asyncio.run(main())
