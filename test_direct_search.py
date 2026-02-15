# -*- coding: utf-8 -*-
"""
NewsBank Test - Direct Search URL
"""

import asyncio
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from playwright.async_api import async_playwright


async def test_search(keyword="Treasury wine estates"):
    """Test search using direct URL"""
    print("="*60)
    print(f"Testing search: {keyword}")
    print("="*60)
    
    cookie_file = Path("cookies/newsbank_auth.json")
    output_dir = Path("articles")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Build search URL directly
    encoded_keyword = quote(keyword)
    search_url = f"https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/results?p=AWGLNB&hide_duplicates=2&fld-base-0=alltext&sort=YMD_date%3AD&maxresults=60&val-base-0={encoded_keyword}"
    
    print(f"\nSearch URL: {search_url}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        
        if cookie_file.exists():
            print("[OK] Using saved cookies")
            context = await browser.new_context(storage_state=str(cookie_file))
        else:
            print("[INFO] No cookies found")
            context = await browser.new_context()
        
        page = await context.new_page()
        
        try:
            # Go directly to search results
            print(f"\n[Step 1] Navigating to search results...")
            await page.goto(search_url, wait_until="networkidle", timeout=60000)
            print(f"   URL: {page.url}")
            print(f"   Title: {await page.title()}")
            
            # Save screenshot and HTML
            await page.screenshot(path=str(output_dir / "treasury_search_results.png"), full_page=True)
            html_content = await page.content()
            with open(output_dir / "treasury_search_results.html", 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"   Screenshot and HTML saved")
            
            # Find articles
            print(f"\n[Step 2] Finding articles...")
            articles = await page.query_selector_all('article, .article, .result, [class*="result"]')
            print(f"   Found {len(articles)} articles")
            
            # Save articles with preview
            saved_count = 0
            for i, article_elem in enumerate(articles[:10], 1):
                try:
                    # Get text content
                    text = await article_elem.inner_text()
                    lines = [l.strip() for l in text.split('\n') if l.strip()]
                    
                    if len(lines) < 2:
                        continue
                    
                    title = lines[0][:100]
                    preview = '\n'.join(lines[1:5])[:500]
                    
                    # Save to file
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    safe_title = "".join(c for c in title[:40] if c.isalnum() or c in (' ', '-', '_')).strip()
                    filename = f"treasury_{i:03d}_{timestamp}_{safe_title}.txt"
                    filepath = output_dir / filename
                    
                    content = f"""Title: {title}
Keyword: {keyword}
Scraped at: {datetime.now().isoformat()}

Preview:
{preview}

{'='*60}
"""
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(content)
                    
                    print(f"   [OK] Saved: {title[:60]}...")
                    saved_count += 1
                    
                except Exception as e:
                    print(f"   [ERROR] Article {i}: {e}")
            
            print(f"\n[DONE] Saved {saved_count} articles")
            print(f"   Files in: {output_dir}")
            
            # Wait for user
            print("\n[INFO] Browser will stay open for 30 seconds...")
            await asyncio.sleep(30)
            
        except Exception as e:
            print(f"\n[ERROR] {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            await context.close()
            await browser.close()


if __name__ == "__main__":
    asyncio.run(test_search())
