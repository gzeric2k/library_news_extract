# Playwright Python 快速参考卡片

## 基础设置

```python
from playwright.async_api import async_playwright

async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    page = await browser.new_page()
    # ... 操作 ...
    await browser.close()
```

---

## 导航和等待

| 操作 | 代码 | 说明 |
|------|------|------|
| 导航到 URL | `await page.goto(url)` | 基础导航 |
| 导航（等待网络空闲） | `await page.goto(url, wait_until="networkidle")` | 推荐用于新闻网站 |
| 导航（等待 DOM） | `await page.goto(url, wait_until="domcontentloaded")` | 快速导航 |
| 等待元素出现 | `await page.wait_for_selector("div.article")` | 等待特定元素 |
| 等待元素可见 | `await page.wait_for_selector("div.article", state="visible")` | 等待可见 |
| 等待页面加载 | `await page.wait_for_load_state("networkidle")` | 等待网络空闲 |
| 等待 URL 变化 | `await page.wait_for_url("https://example.com/page2")` | 等待导航完成 |
| 等待函数返回 true | `await page.wait_for_function("() => window.loaded")` | 等待 JS 条件 |
| 延迟 | `await page.wait_for_timeout(2000)` | 延迟 2 秒 |

---

## 元素选择

| 操作 | 代码 | 说明 |
|------|------|------|
| 获取单个元素 | `element = page.locator("div.article")` | 推荐方式 |
| 获取所有元素 | `elements = await page.query_selector_all("div.article")` | 获取列表 |
| 按文本过滤 | `page.locator("button:has-text('下一页')")` | 文本匹配 |
| 获取第 N 个 | `page.locator("div.article").nth(0)` | 获取第一个 |
| 获取元素数量 | `count = await page.locator("div.article").count()` | 计数 |
| 检查可见性 | `is_visible = await page.locator("div").is_visible()` | 检查可见 |
| 检查存在性 | `exists = await page.locator("div").count() > 0` | 检查存在 |

---

## 文本和属性

| 操作 | 代码 | 说明 |
|------|------|------|
| 获取文本 | `text = await page.locator("h2").inner_text()` | 获取内部文本 |
| 获取 HTML | `html = await page.locator("div").inner_html()` | 获取 HTML |
| 获取属性 | `href = await page.locator("a").get_attribute("href")` | 获取属性值 |
| 获取页面 HTML | `html = await page.content()` | 获取整个页面 |
| 获取页面标题 | `title = await page.title()` | 获取标题 |
| 获取当前 URL | `url = page.url` | 获取 URL |

---

## 交互操作

| 操作 | 代码 | 说明 |
|------|------|------|
| 点击 | `await page.click("button")` | 点击元素 |
| 点击（Locator） | `await page.locator("button").click()` | 推荐方式 |
| 双击 | `await page.dblclick("div")` | 双击 |
| 右键点击 | `await page.click("div", button="right")` | 右键菜单 |
| 填充文本 | `await page.fill("input", "text")` | 填充输入框 |
| 填充文本（Locator） | `await page.locator("input").fill("text")` | 推荐方式 |
| 输入文本 | `await page.type("input", "text")` | 逐字输入 |
| 清空输入框 | `await page.fill("input", "")` | 清空 |
| 选择选项 | `await page.select_option("select", "value")` | 下拉框 |
| 勾选复选框 | `await page.check("input[type='checkbox']")` | 勾选 |
| 取消勾选 | `await page.uncheck("input[type='checkbox']")` | 取消勾选 |
| 悬停 | `await page.hover("div")` | 鼠标悬停 |
| 拖拽 | `await page.drag_and_drop("source", "target")` | 拖拽 |

---

## 键盘操作

| 操作 | 代码 | 说明 |
|------|------|------|
| 按键 | `await page.keyboard.press("Enter")` | 按 Enter |
| 输入文本 | `await page.keyboard.type("text")` | 输入文本 |
| 全选 | `await page.keyboard.press("Control+KeyA")` | Ctrl+A |
| 复制 | `await page.keyboard.press("Control+KeyC")` | Ctrl+C |
| 粘贴 | `await page.keyboard.press("Control+KeyV")` | Ctrl+V |
| 删除 | `await page.keyboard.press("Delete")` | Delete |
| 退出 | `await page.keyboard.press("Escape")` | Esc |

---

## Cookie 和存储

| 操作 | 代码 | 说明 |
|------|------|------|
| 保存 Cookie | `await context.storage_state(path="cookies.json")` | 保存会话 |
| 加载 Cookie | `context = await browser.new_context(storage_state="cookies.json")` | 加载会话 |
| 获取 Cookie | `cookies = await context.cookies()` | 获取所有 Cookie |
| 添加 Cookie | `await context.add_cookies([{"name": "key", "value": "val", "url": "https://example.com"}])` | 添加 Cookie |
| 清除 Cookie | `await context.clear_cookies()` | 清除所有 Cookie |

---

## 截图和录制

| 操作 | 代码 | 说明 |
|------|------|------|
| 截图整页 | `await page.screenshot(path="page.png", full_page=True)` | 整页截图 |
| 截图元素 | `await page.locator("div").screenshot(path="element.png")` | 元素截图 |
| 截图区域 | `await page.screenshot(path="region.png", clip={"x": 0, "y": 0, "width": 800, "height": 600})` | 区域截图 |

---

## 网络和请求

| 操作 | 代码 | 说明 |
|------|------|------|
| 拦截请求 | `await page.route("**/*", lambda route: route.continue_())` | 拦截所有请求 |
| 设置请求头 | `await page.set_extra_http_headers({"Authorization": "Bearer token"})` | 设置请求头 |
| 监听响应 | `page.on("response", lambda res: print(res.status))` | 监听响应 |
| 监听请求 | `page.on("request", lambda req: print(req.url))` | 监听请求 |

---

## 浏览器上下文

| 操作 | 代码 | 说明 |
|------|------|------|
| 创建上下文 | `context = await browser.new_context()` | 新上下文 |
| 创建上下文（带 Cookie） | `context = await browser.new_context(storage_state="cookies.json")` | 带会话 |
| 创建上下文（带 User-Agent） | `context = await browser.new_context(user_agent="Mozilla/5.0...")` | 自定义 UA |
| 创建上下文（带代理） | `context = await browser.new_context(proxy={"server": "http://proxy:8080"})` | 代理 |
| 创建页面 | `page = await context.new_page()` | 新页面 |
| 关闭上下文 | `await context.close()` | 关闭上下文 |

---

## 浏览器启动选项

| 选项 | 代码 | 说明 |
|------|------|------|
| 无头模式 | `await p.chromium.launch(headless=True)` | 无界面 |
| 显示浏览器 | `await p.chromium.launch(headless=False)` | 显示界面 |
| 慢速模式 | `await p.chromium.launch(slow_mo=1000)` | 每个操作延迟 1 秒 |
| 自定义路径 | `await p.chromium.launch(executable_path="/path/to/chrome")` | 自定义浏览器 |
| 代理 | `await p.chromium.launch(proxy={"server": "http://proxy:8080"})` | 代理 |
| 禁用 GPU | `await p.chromium.launch(args=["--disable-gpu"])` | 禁用 GPU |

---

## 错误处理

```python
from playwright.async_api import TimeoutError as PlaywrightTimeout

try:
    await page.goto(url, timeout=30000)
except PlaywrightTimeout:
    print("❌ 页面加载超时")
except Exception as e:
    print(f"❌ 错误: {e}")
finally:
    await browser.close()
```

---

## 常用模式

### 登录并保存 Cookie
```python
async with async_playwright() as p:
    browser = await p.chromium.launch(headless=False)
    context = await browser.new_context()
    page = await context.new_page()
    
    await page.goto("https://example.com/login")
    await page.pause()  # 手动登录
    
    await context.storage_state(path="cookies.json")
    await browser.close()
```

### 使用保存的 Cookie
```python
async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context(storage_state="cookies.json")
    page = await context.new_page()
    
    await page.goto("https://example.com/protected")
    # 已登录状态
    
    await browser.close()
```

### 抓取文章列表
```python
async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    page = await browser.new_page()
    
    await page.goto("https://news.example.com")
    await page.wait_for_load_state("networkidle")
    
    articles = await page.query_selector_all("div.article")
    for article in articles:
        title = await article.query_selector("h2")
        text = await title.inner_text()
        print(text)
    
    await browser.close()
```

### 翻页抓取
```python
async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    page = await browser.new_page()
    
    for page_num in range(1, 6):
        await page.goto(f"https://example.com?page={page_num}")
        await page.wait_for_load_state("networkidle")
        
        articles = await page.query_selector_all("div.article")
        print(f"第 {page_num} 页: {len(articles)} 篇文章")
    
    await browser.close()
```

### 并发抓取
```python
async def scrape_url(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto(url)
        await page.wait_for_load_state("networkidle")
        
        articles = await page.query_selector_all("div.article")
        return len(articles)

# 并发执行
results = await asyncio.gather(
    scrape_url("https://example.com/page1"),
    scrape_url("https://example.com/page2"),
    scrape_url("https://example.com/page3"),
)
```

---

## 调试技巧

| 操作 | 代码 | 说明 |
|------|------|------|
| 暂停执行 | `await page.pause()` | 等待调试器继续 |
| 打印页面标题 | `print(await page.title())` | 获取标题 |
| 打印当前 URL | `print(page.url)` | 获取 URL |
| 执行 JavaScript | `result = await page.evaluate("() => document.title")` | 执行 JS |
| 获取页面 HTML | `html = await page.content()` | 获取 HTML |
| 截图 | `await page.screenshot(path="debug.png")` | 截图 |

---

## 性能优化

| 优化 | 代码 | 说明 |
|------|------|------|
| 禁用图片 | `await page.route("**/*.{png,jpg,jpeg,gif}", lambda route: route.abort())` | 加速加载 |
| 复用上下文 | 创建一个 context，多个 page | 节省资源 |
| 并发请求 | `asyncio.gather(...)` | 并行处理 |
| 设置超时 | `timeout=30000` | 避免无限等待 |

---

## 常见错误

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| TimeoutError | 元素加载超时 | 增加超时时间或检查选择器 |
| ElementNotFound | 元素不存在 | 检查选择器或等待元素加载 |
| TargetClosed | 页面/浏览器已关闭 | 检查资源释放顺序 |
| NotImplementedError | 不支持的操作 | 检查 Playwright 版本 |

---

## 参考资源

- **官方文档**: https://playwright.dev/python/
- **API 参考**: https://playwright.dev/python/docs/api/class-page
- **GitHub**: https://github.com/microsoft/playwright-python
