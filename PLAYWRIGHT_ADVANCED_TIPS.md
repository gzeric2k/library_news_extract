# Playwright 高级技巧和最佳实践

## 1. Locator API（推荐用法）

### 1.1 使用 Locator 替代 query_selector
```python
# ❌ 旧方式（不推荐）
element = await page.query_selector("div.article")
text = await element.inner_text()

# ✅ 新方式（推荐）
locator = page.locator("div.article")
text = await locator.inner_text()
```

### 1.2 Locator 的优势
```python
# 来源: dreammis/social-auto-upload, IBM/mcp-context-forge
async def locator_advantages():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto("https://example.com")
        
        # 1. 链式选择
        label = page.locator("label").filter(has_text="定时发布")
        await label.click()
        
        # 2. 使用 has_text 过滤
        button = page.locator("button:has-text('下一页')")
        await button.click()
        
        # 3. 使用 nth() 获取第 N 个元素
        first_article = page.locator("div.article").nth(0)
        text = await first_article.inner_text()
        
        # 4. 使用 count() 获取元素数量
        count = await page.locator("div.article").count()
        print(f"找到 {count} 篇文章")
        
        # 5. 使用 is_visible() 检查可见性
        is_visible = await page.locator("div.modal").is_visible()
        
        # 6. 使用 wait_for() 等待元素
        await page.locator("div.loading").wait_for(state="hidden")
        
        await browser.close()
```

---

## 2. 反爬虫对策

### 2.1 设置 User-Agent
```python
# 来源: EvolvingLMMs-Lab/lmms-eval
async def set_user_agent():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.4324.150 Safari/537.36"
        
        context = await browser.new_context(user_agent=user_agent)
        page = await context.new_page()
        
        await page.goto("https://example.com")
        
        # 验证 User-Agent
        ua = await page.evaluate("() => navigator.userAgent")
        print(f"User-Agent: {ua}")
        
        await context.close()
        await browser.close()
```

### 2.2 设置代理
```python
# 来源: EvolvingLMMs-Lab/lmms-eval
async def set_proxy():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            proxy={"server": "http://proxy.example.com:8080"}
        )
        
        context = await browser.new_context()
        page = await context.new_page()
        
        await page.goto("https://example.com")
        
        await context.close()
        await browser.close()
```

### 2.3 隐身模式
```python
# 来源: 综合示例
async def incognito_mode():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        # 创建隐身上下文（不保存 cookies）
        context = await browser.new_context()
        page = await context.new_page()
        
        await page.goto("https://example.com")
        
        await context.close()
        await browser.close()
```

### 2.4 禁用图片加载（加速）
```python
# 来源: 综合示例
async def disable_images():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        context = await browser.new_context()
        page = await context.new_page()
        
        # 禁用图片加载
        await page.route("**/*.{png,jpg,jpeg,gif,webp}", lambda route: route.abort())
        
        await page.goto("https://example.com")
        print("✅ 页面加载完成（无图片）")
        
        await context.close()
        await browser.close()
```

---

## 3. 性能优化

### 3.1 并发抓取多个页面
```python
# 来源: unclecode/crawl4ai
async def concurrent_scraping():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        urls = [
            "https://news.example.com/page1",
            "https://news.example.com/page2",
            "https://news.example.com/page3",
        ]
        
        async def scrape_url(url):
            context = await browser.new_context()
            page = await context.new_page()
            
            try:
                await page.goto(url)
                await page.wait_for_load_state("networkidle")
                
                articles = await page.query_selector_all("div.article")
                print(f"✅ {url}: 抓取 {len(articles)} 篇文章")
                
                return len(articles)
            finally:
                await context.close()
        
        # 并发执行
        results = await asyncio.gather(*[scrape_url(url) for url in urls])
        print(f"✅ 总共抓取 {sum(results)} 篇文章")
        
        await browser.close()
```

### 3.2 复用浏览器上下文
```python
# 来源: unclecode/crawl4ai
async def reuse_context():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        
        urls = [
            "https://news.example.com/page1",
            "https://news.example.com/page2",
            "https://news.example.com/page3",
        ]
        
        for url in urls:
            page = await context.new_page()
            
            try:
                await page.goto(url)
                await page.wait_for_load_state("networkidle")
                
                articles = await page.query_selector_all("div.article")
                print(f"✅ {url}: 抓取 {len(articles)} 篇文章")
            finally:
                await page.close()
        
        await context.close()
        await browser.close()
```

---

## 4. 网络拦截和修改

### 4.1 拦截请求
```python
# 来源: microsoft/playwright-python
async def intercept_requests():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 拦截所有请求
        async def handle_route(route):
            request = route.request
            print(f"📡 请求: {request.method} {request.url}")
            
            # 继续请求
            await route.continue_()
        
        await page.route("**/*", handle_route)
        
        await page.goto("https://example.com")
        
        await browser.close()
```

### 4.2 修改请求头
```python
# 来源: 综合示例
async def modify_headers():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 设置请求头
        await page.set_extra_http_headers({
            "Authorization": "Bearer token123",
            "X-Custom-Header": "custom-value"
        })
        
        await page.goto("https://api.example.com/articles")
        
        await browser.close()
```

### 4.3 监听响应
```python
# 来源: 综合示例
async def listen_responses():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 监听 API 响应
        async def handle_response(response):
            if "api/articles" in response.url:
                print(f"✅ API 响应: {response.status}")
                data = await response.json()
                print(f"   数据: {data}")
        
        page.on("response", handle_response)
        
        await page.goto("https://example.com")
        
        await browser.close()
```

---

## 5. 键盘和鼠标操作

### 5.1 键盘输入
```python
# 来源: dreammis/social-auto-upload
async def keyboard_operations():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto("https://example.com")
        
        # 点击输入框
        await page.click("input#search")
        
        # 清空输入框
        await page.keyboard.press("Control+KeyA")
        
        # 输入文本
        await page.keyboard.type("搜索关键词")
        
        # 按 Enter 键
        await page.keyboard.press("Enter")
        
        # 等待搜索结果
        await page.wait_for_load_state("networkidle")
        
        await browser.close()
```

### 5.2 鼠标操作
```python
# 来源: 综合示例
async def mouse_operations():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto("https://example.com")
        
        # 悬停
        await page.hover("div.article")
        
        # 点击
        await page.click("button.like")
        
        # 双击
        await page.dblclick("div.item")
        
        # 右键点击
        await page.click("div.menu", button="right")
        
        # 拖拽
        await page.drag_and_drop("div.source", "div.target")
        
        await browser.close()
```

---

## 6. 对话框处理

### 6.1 处理 Alert/Confirm
```python
# 来源: 综合示例
async def handle_dialogs():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 监听对话框
        async def handle_dialog(dialog):
            print(f"对话框类型: {dialog.type}")
            print(f"对话框消息: {dialog.message}")
            
            if dialog.type == "alert":
                await dialog.accept()
            elif dialog.type == "confirm":
                await dialog.accept()  # 点击确定
            elif dialog.type == "prompt":
                await dialog.fill("输入内容")
                await dialog.accept()
        
        page.on("dialog", handle_dialog)
        
        await page.goto("https://example.com")
        
        await browser.close()
```

---

## 7. 截图和录制

### 7.1 截图
```python
# 来源: 综合示例
async def take_screenshots():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto("https://example.com")
        await page.wait_for_load_state("networkidle")
        
        # 截图整个页面
        await page.screenshot(path="full_page.png", full_page=True)
        
        # 截图特定元素
        element = page.locator("div.article")
        await element.screenshot(path="article.png")
        
        # 截图特定区域
        await page.screenshot(
            path="region.png",
            clip={"x": 0, "y": 0, "width": 800, "height": 600}
        )
        
        await browser.close()
```

### 7.2 录制视频
```python
# 来源: 综合示例
async def record_video():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        context = await browser.new_context(
            record_video_dir="videos/"
        )
        page = await context.new_page()
        
        await page.goto("https://example.com")
        await page.wait_for_load_state("networkidle")
        
        # 执行操作...
        await page.click("button.next")
        
        await context.close()
        await browser.close()
        
        print("✅ 视频已保存到 videos/ 目录")
```

---

## 8. 调试技巧

### 8.1 启用调试模式
```python
# 来源: 综合示例
async def debug_mode():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # 显示浏览器窗口
            slow_mo=1000     # 每个操作延迟 1 秒
        )
        page = await browser.new_page()
        
        await page.goto("https://example.com")
        
        # 暂停执行，等待调试器继续
        await page.pause()
        
        await browser.close()
```

### 8.2 打印页面内容
```python
# 来源: 综合示例
async def debug_page_content():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto("https://example.com")
        
        # 获取页面 HTML
        html = await page.content()
        print(f"页面 HTML 长度: {len(html)}")
        
        # 执行 JavaScript 获取信息
        title = await page.evaluate("() => document.title")
        print(f"页面标题: {title}")
        
        # 获取所有 console 消息
        page.on("console", lambda msg: print(f"Console: {msg.text}"))
        
        await browser.close()
```

### 8.3 记录网络请求
```python
# 来源: 综合示例
async def log_network():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        requests = []
        responses = []
        
        page.on("request", lambda req: requests.append(req.url))
        page.on("response", lambda res: responses.append((res.url, res.status)))
        
        await page.goto("https://example.com")
        await page.wait_for_load_state("networkidle")
        
        print(f"✅ 请求数: {len(requests)}")
        print(f"✅ 响应数: {len(responses)}")
        
        for url, status in responses[:5]:
            print(f"   {status} {url}")
        
        await browser.close()
```

---

## 9. 处理特殊场景

### 9.1 处理 iframe
```python
# 来源: TeamWiseFlow/wiseflow
async def handle_iframes():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto("https://example.com")
        
        # 获取所有 iframe
        iframes = await page.query_selector_all("iframe")
        print(f"找到 {len(iframes)} 个 iframe")
        
        # 访问 iframe 内容
        for i, iframe in enumerate(iframes):
            try:
                # 获取 iframe 的 frame 对象
                frame = await iframe.content_frame()
                if frame:
                    # 在 iframe 内执行操作
                    content = await frame.content()
                    print(f"iframe {i} 内容长度: {len(content)}")
            except Exception as e:
                print(f"❌ 访问 iframe {i} 失败: {e}")
        
        await browser.close()
```

### 9.2 处理文件下载
```python
# 来源: 综合示例
async def handle_downloads():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 监听下载事件
        async with page.expect_download() as download_info:
            await page.click("a.download-button")
        
        download = await download_info.value
        
        # 保存文件
        await download.save_as(f"downloads/{download.suggested_filename}")
        print(f"✅ 文件已下载: {download.suggested_filename}")
        
        await browser.close()
```

### 9.3 处理文件上传
```python
# 来源: dreammis/social-auto-upload
async def handle_file_upload():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto("https://example.com/upload")
        
        # 方式 1: 使用 set_input_files
        file_input = page.locator('input[type="file"]')
        await file_input.set_input_files("path/to/file.pdf")
        
        # 方式 2: 使用 file_chooser
        async with page.expect_file_chooser() as fc_info:
            await page.click("button.upload")
        
        file_chooser = await fc_info.value
        await file_chooser.set_files("path/to/file.pdf")
        
        await browser.close()
```

---

## 10. 最佳实践总结

### ✅ 推荐做法
1. **使用 Locator API** - 比 query_selector 更强大
2. **设置合理的超时** - 避免无限等待
3. **使用 try-except** - 处理所有可能的异常
4. **记录详细日志** - 便于调试
5. **复用浏览器上下文** - 提高性能
6. **设置 User-Agent** - 避免被识别为爬虫
7. **实现重试机制** - 提高稳定性
8. **保存 cookies** - 避免重复登录

### ❌ 避免做法
1. **不要使用 sleep()** - 使用 wait_for_* 替代
2. **不要忽略异常** - 总是处理可能的错误
3. **不要设置过长的超时** - 浪费时间
4. **不要频繁创建浏览器** - 复用上下文
5. **不要忽视反爬虫** - 设置 User-Agent 和代理
6. **不要并发过多** - 控制并发数量
7. **不要保存敏感信息** - 妥善处理 cookies

---

## 11. 常见问题解决

### Q1: 页面加载超时
```python
# 解决方案：使用 networkidle 而不是 load
await page.goto(url, wait_until="networkidle", timeout=30000)
```

### Q2: 元素找不到
```python
# 解决方案：使用多个选择器尝试
selectors = ["div.article", "article", "div[role='article']"]
for selector in selectors:
    element = page.locator(selector)
    if await element.count() > 0:
        break
```

### Q3: Cookie 失效
```python
# 解决方案：定期更新 cookie
await context.storage_state(path=cookies_file)
```

### Q4: 被识别为爬虫
```python
# 解决方案：设置 User-Agent 和代理
context = await browser.new_context(
    user_agent="Mozilla/5.0...",
)
```

### Q5: 内存泄漏
```python
# 解决方案：正确关闭资源
try:
    # 操作...
finally:
    await page.close()
    await context.close()
    await browser.close()
```
