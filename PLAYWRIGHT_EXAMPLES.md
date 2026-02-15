# Playwright 网站登录和文章抓取代码示例汇总

## 1. Cookie/Session 保存和加载

### 1.1 保存 Cookie 到文件
```python
# 来源: dreammis/social-auto-upload
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

async def save_cookies():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        # 手动登录（暂停页面等待用户操作）
        await page.goto("https://creator.douyin.com/")
        await page.pause()  # 调试器暂停，等待手动登录
        
        # 保存 cookie 到文件
        cookies_dir = Path("cookiesFile")
        cookies_dir.mkdir(exist_ok=True)
        await context.storage_state(path=cookies_dir / "douyin_cookies.json")
        print("✅ Cookie 已保存")
        
        await context.close()
        await browser.close()
```

### 1.2 从文件加载 Cookie 并使用
```python
# 来源: dreammis/social-auto-upload
async def use_saved_cookies(account_file):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        
        # 使用保存的 storage_state（包含 cookies 和 localStorage）
        context = await browser.new_context(storage_state=account_file)
        page = await context.new_page()
        
        # 直接访问需要登录的页面
        await page.goto("https://creator.douyin.com/creator-micro/content/upload")
        
        # 验证登录状态
        try:
            await page.wait_for_url(
                "https://creator.douyin.com/creator-micro/content/upload", 
                timeout=5000
            )
            print("✅ Cookie 有效，已登录")
        except:
            print("❌ Cookie 失效，需要重新登录")
        
        await context.close()
        await browser.close()
```

### 1.3 更新和保存 Cookie
```python
# 来源: dreammis/social-auto-upload
async def update_cookies_after_action(context, account_file):
    """在执行操作后更新 cookie"""
    # 执行某些操作...
    await page.click("button.publish")
    await page.wait_for_load_state("networkidle")
    
    # 更新保存的 cookie
    await context.storage_state(path=account_file)
    print("✅ Cookie 已更新")
```

---

## 2. 页面导航和等待策略

### 2.1 基础导航
```python
# 来源: NanmiCoder/CrawlerTutorial
async def navigate_page():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 基本导航
        await page.goto("https://example.com")
        print(f"页面标题: {await page.title()}")
        print(f"当前 URL: {page.url}")
        
        await browser.close()
```

### 2.2 等待策略详解
```python
# 来源: NanmiCoder/CrawlerTutorial
async def wait_strategies():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 1. 等待页面加载完成（推荐用于新闻网站）
        await page.goto(
            "https://example.com",
            wait_until="networkidle"  # 等待网络空闲
        )
        
        # 2. 等待 DOM 内容加载
        await page.goto(
            "https://example.com",
            wait_until="domcontentloaded"
        )
        
        # 3. 等待特定元素出现
        await page.wait_for_selector("div.article", timeout=10000)
        
        # 4. 等待页面加载状态
        await page.wait_for_load_state("load", timeout=15000)
        await page.wait_for_load_state("networkidle", timeout=15000)
        
        # 5. 等待 URL 变化（登录后跳转）
        await page.wait_for_url(
            "https://example.com/dashboard", 
            timeout=5000
        )
        
        await browser.close()
```

### 2.3 自动等待机制
```python
# 来源: NanmiCoder/CrawlerTutorial
async def auto_waiting():
    """Playwright 的操作会自动等待元素可操作"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto("https://quotes.toscrape.com/login")
        
        # 以下操作会自动等待：
        # - 元素存在于 DOM
        # - 元素可见
        # - 元素稳定（不在动画中）
        # - 元素可接收事件
        # - 元素没有被其他元素遮挡
        
        await page.fill("input#username", "test")  # 自动等待输入框可用
        await page.click("input[type='submit']")   # 自动等待按钮可点击
        
        await browser.close()
```

---

## 3. 表单填充和登录

### 3.1 登录表单填充
```python
# 来源: NanmiCoder/CrawlerTutorial
async def login_form():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto("https://quotes.toscrape.com/login")
        
        # 填充用户名
        await page.fill("input#username", "test")
        
        # 填充密码
        await page.fill("input#password", "test")
        
        # 点击登录按钮
        await page.click("input[type='submit']")
        
        # 等待登录完成
        await page.wait_for_load_state("networkidle")
        
        await browser.close()
```

### 3.2 复杂登录流程（带验证）
```python
# 来源: s3rgeym/hh-applicant-tool
async def complex_login():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        await page.goto("https://example.com/login")
        
        # 选择登录方式（邮箱或电话）
        username = "user@example.com"
        if "@" in username:
            # 选择邮箱登录
            await page.check('input[value="email"]', force=True)
            await page.fill('input[name="email"]', username)
        else:
            # 选择电话登录
            await page.fill('input[name="phone"]', username)
        
        # 点击展开密码输入
        await page.click('button.expand-password')
        
        # 等待密码输入框出现
        await page.wait_for_selector('input[name="password"]')
        
        # 填充密码
        await page.fill('input[name="password"]', "password123")
        
        # 提交表单
        await page.click('button[type="submit"]')
        
        # 等待登录完成
        await page.wait_for_load_state("networkidle", timeout=10000)
        
        await browser.close()
```

---

## 4. 文章抓取（核心功能）

### 4.1 基础文章抓取
```python
# 来源: ed-donner/agents
async def scrape_articles():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto("https://news.example.com")
        await page.wait_for_load_state("networkidle")
        
        # 多个选择器尝试（提高兼容性）
        selectors = [
            "div.article",
            "article",
            "div[role='article']",
            "div.news-item"
        ]
        
        articles = []
        for selector in selectors:
            elements = await page.query_selector_all(selector)
            if len(elements) > 5:  # 找到足够的结果
                for element in elements[:10]:
                    try:
                        title = await element.query_selector("h2, h3, .title")
                        if title:
                            text = await title.inner_text()
                            if text and len(text) > 10:
                                articles.append(text)
                    except:
                        continue
                break
        
        print(f"✅ 抓取到 {len(articles)} 篇文章")
        for article in articles:
            print(f"  - {article[:50]}...")
        
        await browser.close()
        return articles
```

### 4.2 详细文章信息抓取
```python
# 来源: 综合示例
async def scrape_article_details():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto("https://news.example.com")
        await page.wait_for_load_state("networkidle")
        
        # 获取所有文章元素
        articles = await page.query_selector_all("div.article-item")
        
        article_list = []
        for article in articles:
            try:
                # 提取标题
                title_elem = await article.query_selector("h2.title")
                title = await title_elem.inner_text() if title_elem else "N/A"
                
                # 提取摘要
                summary_elem = await article.query_selector("p.summary")
                summary = await summary_elem.inner_text() if summary_elem else "N/A"
                
                # 提取发布时间
                time_elem = await article.query_selector("span.publish-time")
                publish_time = await time_elem.inner_text() if time_elem else "N/A"
                
                # 提取链接
                link_elem = await article.query_selector("a.article-link")
                link = await link_elem.get_attribute("href") if link_elem else "N/A"
                
                article_list.append({
                    "title": title.strip(),
                    "summary": summary.strip(),
                    "publish_time": publish_time.strip(),
                    "link": link
                })
            except Exception as e:
                print(f"❌ 抓取文章失败: {e}")
                continue
        
        print(f"✅ 抓取到 {len(article_list)} 篇完整文章")
        return article_list
```

---

## 5. 翻页处理

### 5.1 点击下一页按钮
```python
# 来源: xnl-h4ck3r/xnldorker
async def pagination_click_next():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto("https://news.example.com")
        
        all_articles = []
        page_num = 1
        
        while page_num <= 5:  # 最多抓取 5 页
            print(f"📄 正在抓取第 {page_num} 页...")
            
            # 等待页面加载
            await page.wait_for_load_state("networkidle")
            
            # 抓取当前页的文章
            articles = await page.query_selector_all("div.article")
            for article in articles:
                title = await article.query_selector("h2")
                if title:
                    text = await title.inner_text()
                    all_articles.append(text)
            
            # 查找并点击下一页按钮
            next_button = await page.query_selector("a.next-page, button.next")
            if not next_button:
                print("✅ 已到最后一页")
                break
            
            # 检查下一页按钮是否可用
            is_disabled = await next_button.get_attribute("disabled")
            if is_disabled:
                print("✅ 下一页按钮已禁用，抓取完成")
                break
            
            # 点击下一页
            await next_button.click()
            await page.wait_for_load_state("networkidle", timeout=10000)
            page_num += 1
        
        print(f"✅ 总共抓取 {len(all_articles)} 篇文章")
        await browser.close()
        return all_articles
```

### 5.2 滚动加载更多（无限滚动）
```python
# 来源: 综合示例
async def pagination_scroll_load():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto("https://news.example.com")
        
        all_articles = []
        previous_height = 0
        scroll_count = 0
        max_scrolls = 10
        
        while scroll_count < max_scrolls:
            # 获取当前页面高度
            current_height = await page.evaluate("document.body.scrollHeight")
            
            if current_height == previous_height:
                print("✅ 已到底部，无更多内容")
                break
            
            # 滚动到底部
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            
            # 等待新内容加载
            await page.wait_for_load_state("networkidle", timeout=5000)
            
            # 抓取文章
            articles = await page.query_selector_all("div.article")
            all_articles = []
            for article in articles:
                title = await article.query_selector("h2")
                if title:
                    text = await title.inner_text()
                    all_articles.append(text)
            
            previous_height = current_height
            scroll_count += 1
            print(f"📄 滚动 {scroll_count} 次，已加载 {len(all_articles)} 篇文章")
        
        print(f"✅ 总共抓取 {len(all_articles)} 篇文章")
        await browser.close()
        return all_articles
```

### 5.3 URL 参数翻页
```python
# 来源: 综合示例
async def pagination_url_params():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        all_articles = []
        base_url = "https://news.example.com/list"
        
        for page_num in range(1, 6):  # 抓取 1-5 页
            url = f"{base_url}?page={page_num}"
            print(f"📄 正在抓取: {url}")
            
            await page.goto(url)
            await page.wait_for_load_state("networkidle")
            
            # 抓取文章
            articles = await page.query_selector_all("div.article")
            if not articles:
                print("✅ 无更多文章，抓取完成")
                break
            
            for article in articles:
                title = await article.query_selector("h2")
                if title:
                    text = await title.inner_text()
                    all_articles.append(text)
            
            print(f"✅ 第 {page_num} 页抓取 {len(articles)} 篇文章")
        
        print(f"✅ 总共抓取 {len(all_articles)} 篇文章")
        await browser.close()
        return all_articles
```

---

## 6. 动态内容加载等待

### 6.1 等待特定元素加载
```python
# 来源: agiresearch/AIOS
async def wait_for_dynamic_content():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto("https://news.example.com")
        
        # 等待文章列表加载
        try:
            await page.wait_for_selector(
                "div.article-list",
                state="attached",  # 元素附加到 DOM
                timeout=10000
            )
            print("✅ 文章列表已加载")
        except:
            print("❌ 文章列表加载超时")
        
        # 等待元素可见
        try:
            await page.wait_for_selector(
                "div.article-item",
                state="visible",  # 元素可见
                timeout=10000
            )
            print("✅ 文章项已可见")
        except:
            print("❌ 文章项加载超时")
        
        await browser.close()
```

### 6.2 等待图片加载
```python
# 来源: unclecode/crawl4ai
async def wait_for_images():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto("https://news.example.com")
        
        # 等待 DOM 内容加载
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=5000)
        except:
            pass
        
        # 等待网络空闲（所有图片加载完成）
        await page.wait_for_load_state("networkidle", timeout=15000)
        
        # 检查图片是否加载
        images = await page.query_selector_all("img")
        print(f"✅ 页面包含 {len(images)} 张图片")
        
        await browser.close()
```

### 6.3 等待 JavaScript 执行完成
```python
# 来源: 综合示例
async def wait_for_javascript():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto("https://news.example.com")
        
        # 等待特定的 JavaScript 变量出现
        await page.wait_for_function(
            "() => window.articlesLoaded === true",
            timeout=10000
        )
        print("✅ JavaScript 执行完成")
        
        # 或者等待特定元素的属性变化
        await page.wait_for_function(
            "() => document.querySelectorAll('.article').length > 0",
            timeout=10000
        )
        print("✅ 文章已加载")
        
        await browser.close()
```

---

## 7. 错误处理和重试

### 7.1 基础错误处理
```python
# 来源: 综合示例
async def error_handling():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            await page.goto("https://news.example.com", timeout=30000)
        except Exception as e:
            print(f"❌ 页面加载失败: {e}")
            await browser.close()
            return None
        
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception as e:
            print(f"⚠️ 网络等待超时: {e}")
            # 继续执行，不中断
        
        try:
            articles = await page.query_selector_all("div.article")
            print(f"✅ 抓取到 {len(articles)} 篇文章")
        except Exception as e:
            print(f"❌ 抓取失败: {e}")
        finally:
            await browser.close()
```

### 7.2 重试机制
```python
# 来源: 综合示例
async def retry_mechanism():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                await page.goto("https://news.example.com", timeout=30000)
                await page.wait_for_load_state("networkidle", timeout=15000)
                print("✅ 页面加载成功")
                break
            except Exception as e:
                retry_count += 1
                print(f"⚠️ 加载失败 (尝试 {retry_count}/{max_retries}): {e}")
                
                if retry_count < max_retries:
                    await page.reload()  # 重新加载页面
                    await asyncio.sleep(2)  # 等待 2 秒后重试
                else:
                    print("❌ 达到最大重试次数，放弃")
                    await browser.close()
                    return None
        
        await browser.close()
```

---

## 8. 完整示例：NewsBank 网站抓取

```python
# -*- coding: utf-8 -*-
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

class NewsExtractor:
    def __init__(self, cookies_file="cookies.json"):
        self.cookies_file = cookies_file
    
    async def login_and_save_cookies(self):
        """手动登录并保存 cookies"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()
            
            await page.goto("https://newsbank.example.com/login")
            print("⏸️ 请在浏览器中手动登录...")
            await page.pause()  # 等待手动登录
            
            # 保存 cookies
            await context.storage_state(path=self.cookies_file)
            print(f"✅ Cookies 已保存到 {self.cookies_file}")
            
            await context.close()
            await browser.close()
    
    async def scrape_articles(self, url, max_pages=5):
        """抓取文章"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(storage_state=self.cookies_file)
            page = await context.new_page()
            
            all_articles = []
            
            for page_num in range(1, max_pages + 1):
                try:
                    # 构建 URL
                    page_url = f"{url}?page={page_num}"
                    print(f"📄 正在抓取第 {page_num} 页: {page_url}")
                    
                    # 导航到页面
                    await page.goto(page_url, timeout=30000)
                    await page.wait_for_load_state("networkidle", timeout=15000)
                    
                    # 等待文章列表加载
                    await page.wait_for_selector("div.article-item", timeout=10000)
                    
                    # 抓取文章
                    articles = await page.query_selector_all("div.article-item")
                    
                    if not articles:
                        print("✅ 无更多文章，抓取完成")
                        break
                    
                    for article in articles:
                        try:
                            # 提取标题
                            title_elem = await article.query_selector("h2.title")
                            title = await title_elem.inner_text() if title_elem else "N/A"
                            
                            # 提取摘要
                            summary_elem = await article.query_selector("p.summary")
                            summary = await summary_elem.inner_text() if summary_elem else "N/A"
                            
                            # 提取发布时间
                            time_elem = await article.query_selector("span.publish-time")
                            publish_time = await time_elem.inner_text() if time_elem else "N/A"
                            
                            # 提取链接
                            link_elem = await article.query_selector("a.article-link")
                            link = await link_elem.get_attribute("href") if link_elem else "N/A"
                            
                            all_articles.append({
                                "title": title.strip(),
                                "summary": summary.strip(),
                                "publish_time": publish_time.strip(),
                                "link": link,
                                "page": page_num
                            })
                        except Exception as e:
                            print(f"⚠️ 抓取单篇文章失败: {e}")
                            continue
                    
                    print(f"✅ 第 {page_num} 页抓取 {len(articles)} 篇文章")
                    
                except PlaywrightTimeout:
                    print(f"⚠️ 第 {page_num} 页加载超时")
                    continue
                except Exception as e:
                    print(f"❌ 第 {page_num} 页抓取失败: {e}")
                    continue
            
            print(f"\n✅ 总共抓取 {len(all_articles)} 篇文章")
            
            await context.close()
            await browser.close()
            
            return all_articles
    
    async def save_articles(self, articles, output_file="articles.json"):
        """保存文章到 JSON 文件"""
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)
        print(f"✅ 文章已保存到 {output_file}")

# 使用示例
async def main():
    extractor = NewsExtractor(cookies_file="newsbank_cookies.json")
    
    # 第一次运行：登录并保存 cookies
    # await extractor.login_and_save_cookies()
    
    # 抓取文章
    articles = await extractor.scrape_articles(
        url="https://newsbank.example.com/search",
        max_pages=5
    )
    
    # 保存结果
    await extractor.save_articles(articles)

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 9. 关键要点总结

### Cookie 管理
- ✅ 使用 `context.storage_state(path=file)` 保存 cookies
- ✅ 使用 `browser.new_context(storage_state=file)` 加载 cookies
- ✅ 在执行操作后更新 cookies 以保持会话有效

### 等待策略
- ✅ `wait_until="networkidle"` - 最可靠，等待网络空闲
- ✅ `wait_for_load_state("networkidle")` - 等待网络空闲
- ✅ `wait_for_selector()` - 等待特定元素出现
- ✅ 自动等待 - Playwright 操作自动等待元素可操作

### 文章抓取
- ✅ 使用多个选择器提高兼容性
- ✅ 使用 `query_selector_all()` 获取所有元素
- ✅ 使用 `inner_text()` 获取文本内容
- ✅ 使用 `get_attribute()` 获取属性值

### 翻页处理
- ✅ 点击下一页按钮 - 适合传统分页
- ✅ 滚动加载 - 适合无限滚动
- ✅ URL 参数 - 适合 RESTful API

### 错误处理
- ✅ 使用 try-except 捕获异常
- ✅ 实现重试机制
- ✅ 设置合理的超时时间
- ✅ 记录详细的错误日志

---

## 10. 参考资源

- **Playwright 官方文档**: https://playwright.dev/python/
- **GitHub 示例项目**:
  - dreammis/social-auto-upload - 社交媒体自动上传
  - NanmiCoder/CrawlerTutorial - 爬虫教程
  - unclecode/crawl4ai - AI 爬虫框架
  - ed-donner/agents - 智能代理示例
