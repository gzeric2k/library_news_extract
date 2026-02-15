# -*- coding: utf-8 -*-
"""
NewsBank 按钮下载器
模拟点击网页"Download PDF"按钮，通过API payload获取文章内容

功能：
1. 用户输入NewsBank搜索结果页URL
2. 脚本访问页面并获取必要的参数（instance_id等）
3. 模拟点击"Download PDF"按钮，发送API请求
4. 从响应中解析文章列表和内容
5. 保存文章为文本文件

使用方法：
    python newsbank_button_downloader.py "https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/results?..."
    
    python newsbank_button_downloader.py "URL" --max-pages 3
    
    python newsbank_button_downloader.py "URL" --download-all

作者: AI Assistant
日期: 2026-02-15
"""

import asyncio
import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from urllib.parse import urlparse, parse_qs, urljoin, quote, unquote
from dataclasses import dataclass, asdict

from playwright.async_api import async_playwright, Page, BrowserContext


@dataclass
class ArticleInfo:
    """文章信息数据类"""
    title: str
    date: str
    source: str
    author: str
    preview: str
    url: str
    page_num: int
    article_id: Optional[str] = None
    word_count: int = 0
    full_text: str = ""  # 完整文章内容
    
    def to_dict(self) -> dict:
        return asdict(self)


class NewsBankButtonDownloader:
    """NewsBank 按钮下载器 - 模拟点击Download PDF按钮"""
    
    def __init__(self,
                 headless: bool = False,
                 max_pages: int = 10,
                 download_limit: int = 50,
                 output_dir: str = "articles_button"):
        self.headless = headless
        self.max_pages = max_pages
        self.download_limit = download_limit
        
        self.cookie_file = Path("cookies/newsbank_auth.json")
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cookie_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 统计
        self.stats = {
            "total_pages": 0,
            "total_articles": 0,
            "downloaded": 0,
            "skipped": 0,
            "errors": []
        }
        
        self.articles: List[ArticleInfo] = []
        self.api_endpoint = "https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/nb-multidocs/get"
    
    async def check_login(self, context: BrowserContext) -> bool:
        """检查登录状态"""
        print("\n[检查登录状态]")
        print("-" * 40)
        
        if not self.cookie_file.exists():
            print("[信息] 未找到登录Cookie")
            return False
        
        try:
            test_page = await context.new_page()
            await test_page.goto(
                "https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/browse-multi?p=AWGLNB",
                wait_until="networkidle", timeout=30000
            )
            
            current_url = test_page.url
            await test_page.close()
            
            if "infoweb-newsbank" in current_url and "login" not in current_url:
                print("[成功] Cookie有效，已登录")
                return True
            else:
                print("[信息] Cookie已过期，需要重新登录")
                return False
                
        except Exception as e:
            print(f"[警告] 检查登录状态时出错: {e}")
            return False
    
    async def do_login(self, page: Page) -> bool:
        """执行登录"""
        print("\n[登录]")
        print("-" * 40)
        print("请在浏览器窗口中完成登录...")
        print("登录成功后将自动继续")
        
        try:
            await page.goto(
                "https://eresources.sl.nsw.gov.au/newsbank-including-access-australia",
                wait_until="networkidle", timeout=60000
            )
            
            start_time = asyncio.get_event_loop().time()
            while (asyncio.get_event_loop().time() - start_time) < 180:
                if "infoweb-newsbank-com.ezproxy" in page.url and "login" not in page.url:
                    print("[成功] 登录成功！")
                    return True
                await asyncio.sleep(2)
            
            print("[错误] 登录超时（3分钟）")
            return False
            
        except Exception as e:
            print(f"[错误] 登录失败: {e}")
            return False
    
    def _extract_article_ids_from_page(self, html_content: str) -> List[str]:
        """从页面HTML中提取文章ID列表"""
        article_ids = []
        
        # 方法1: 匹配 doc= 参数 (在href中)
        pattern1 = r'href="[^"]*doc=([^&"\s]+)'
        matches1 = re.findall(pattern1, html_content)
        
        # 方法2: 匹配 data-doc-id 属性
        pattern2 = r'data-doc-id="([^"]+)"'
        matches2 = re.findall(pattern2, html_content)
        
        # 方法3: 匹配 doc= 在任何位置
        pattern3 = r'doc=([^&"\s]+)'
        matches3 = re.findall(pattern3, html_content)
        
        all_matches = matches1 + matches2 + matches3
        
        for match in all_matches:
            # 解码URL编码
            doc_id = unquote(match)
            # 过滤掉一些常见的非文章ID值
            if doc_id and doc_id not in article_ids and len(doc_id) > 5:
                article_ids.append(doc_id)
        
        return article_ids
    
    def _build_download_payload(self, 
                                page_num: int = 1, 
                                article_ids: Optional[List[str]] = None,
                                instance_id: Optional[str] = None,
                                p_param: str = "AWGLNB") -> Dict[str, str]:
        """
        构建下载API的payload
        
        基于newsbank-api-download.txt中的参数结构
        """
        # 基础payload
        # maxresults=100 可以一次获取最多100篇文章的完整内容
        payload = {
            "page": str(page_num),
            "load_pager": "true",
            "p": p_param,
            "action": "download",
            "label": "Multidocs Display pane",
            "maxresults": "100",  # 改为100，一次获取更多文章
            "pdf_enabled": "true",
            "pdf_label": "Download PDF",
            "pdf_path": "multidocs",
            "pdf_filename": "NewsBank Multiple Articles.pdf",
            "zustat_category_override": "co_sc_pdf_download"
        }
        
        # 添加instance_id（如果有）
        if instance_id:
            payload["instance_id"] = instance_id
        
        # 构建pdf_params（包含文章ID）
        pdf_params_parts = [
            "action=pdf",
            "format=pdf",
            "pdf_enabled=false",
            "load_pager=false",
            "maxresults=100"
        ]
        
        # 如果有文章ID，添加到pdf_params
        if article_ids:
            # 构建文档列表参数
            docs_param = "&".join([f"doc={quote(doc_id)}" for doc_id in article_ids[:100]])
            pdf_params_parts.append(docs_param)
        
        payload["pdf_params"] = "&".join(pdf_params_parts)
        
        return payload
    
    async def select_all_articles(self, page: Page) -> bool:
        """
        选中页面上的所有文章
        
        NewsBank通常有复选框或"Select All"按钮来选择文章
        
        Returns:
            是否成功选择
        """
        print("\n[选择所有文章]")
        print("-" * 40)
        
        try:
            # 方法1: 查找"Select All"或"全选"按钮/链接
            # 根据实际HTML结构：
            # <input class="search-hits__select-all form-checkbox" title="Select all articles on this page." id="search-hits__select-all" type="checkbox" value="1" aria-label="Select All Articles">
            select_all_selectors = [
                '#search-hits__select-all',  # 精确ID选择器（最可靠）
                'input.search-hits__select-all',  # class选择器
                'input[title*="Select all articles"]',  # title属性
                'input[aria-label="Select All Articles"]',  # aria-label
            ]
            
            for selector in select_all_selectors:
                try:
                    print(f"  [尝试] 查找全选复选框: {selector}")
                    
                    # 等待元素出现
                    try:
                        await page.wait_for_selector(selector, timeout=5000)
                    except:
                        print(f"    等待超时，尝试直接查找")
                    
                    # 查找元素
                    select_all_elem = await page.query_selector(selector)
                    
                    if select_all_elem:
                        print(f"    找到元素，准备滚动到视图...")
                        
                        # 强制滚动到页面顶部，确保复选框可见
                        await page.evaluate("window.scrollTo(0, 0)")
                        await asyncio.sleep(0.5)
                        
                        # 滚动到元素
                        await select_all_elem.scroll_into_view_if_needed()
                        await asyncio.sleep(0.5)
                        
                        # 检查元素状态
                        is_visible = await select_all_elem.is_visible()
                        box = await select_all_elem.bounding_box()
                        print(f"    元素状态 - visible: {is_visible}, box: {box}")
                        
                        if is_visible and box:
                            # 获取当前选中状态
                            is_checked = await select_all_elem.is_checked()
                            print(f"    当前选中状态: {is_checked}")
                            
                            if not is_checked:
                                print(f"    准备点击复选框...")
                                
                                # 方法1: 使用鼠标模拟点击（更真实）
                                try:
                                    box = await select_all_elem.bounding_box()
                                    if box:
                                        # 计算元素中心点
                                        x = box['x'] + box['width'] / 2
                                        y = box['y'] + box['height'] / 2
                                        print(f"    使用鼠标点击坐标: ({x}, {y})")
                                        await page.mouse.click(x, y)
                                        print(f"    [成功] 使用 mouse.click() 点击")
                                except Exception as mouse_err:
                                    print(f"    [警告] 鼠标点击失败: {mouse_err}")
                                    
                                    # 方法2: 直接点击
                                    try:
                                        await select_all_elem.click(force=True)
                                        print(f"    [成功] 使用 click(force=True) 点击")
                                    except Exception as click_err:
                                        print(f"    [警告] 直接点击失败: {click_err}")
                                        
                                        # 方法3: JavaScript点击
                                        try:
                                            await page.evaluate(f"""
                                                () => {{
                                                    const cb = document.querySelector('{selector}');
                                                    if (cb) {{
                                                        cb.click();
                                                        return 'clicked';
                                                    }}
                                                    return 'not found';
                                                }}
                                            """)
                                            print(f"    [成功] 使用页面级 JavaScript 点击")
                                        except Exception as js_err:
                                            print(f"    [警告] JavaScript点击也失败: {js_err}")
                                            continue
                                
                                # 等待UI更新
                                await asyncio.sleep(2)
                                
                                # 验证是否选中
                                is_checked_after = await select_all_elem.is_checked()
                                print(f"    点击后选中状态: {is_checked_after}")
                                
                                # 也检查页面上的选中计数
                                selection_text = await page.evaluate("""
                                    () => {
                                        const el = document.querySelector('.search-hits__selections--feedback');
                                        return el ? el.textContent : 'not found';
                                    }
                                """)
                                print(f"    页面选中计数: {selection_text}")
                                
                                if is_checked_after or '100' in selection_text:
                                    print(f"  [成功] 全选复选框已选中")
                                    return True
                                else:
                                    print(f"  [警告] 点击后仍未选中，尝试强制设置属性")
                                    # 强制设置checked属性并触发事件
                                    await page.evaluate("""
                                        () => {
                                            const cb = document.getElementById('search-hits__select-all');
                                            if (cb) {
                                                cb.checked = true;
                                                cb.dispatchEvent(new Event('change', { bubbles: true }));
                                                cb.dispatchEvent(new Event('click', { bubbles: true }));
                                                
                                                // 同时勾选所有文章复选框
                                                const articleCheckboxes = document.querySelectorAll('article.search-hits__hit input[type="checkbox"]');
                                                articleCheckboxes.forEach(box => {
                                                    if (!box.checked) {
                                                        box.checked = true;
                                                        box.dispatchEvent(new Event('change', { bubbles: true }));
                                                    }
                                                });
                                                return `checked ${articleCheckboxes.length} boxes`;
                                            }
                                            return 'checkbox not found';
                                        }
                                    """)
                                    await asyncio.sleep(1)
                                    return True
                            else:
                                print(f"  [信息] 全选复选框已经选中")
                                return True
                    else:
                        print(f"    未找到元素")
                        
                except Exception as e:
                    print(f"    选择器失败: {str(e)[:100]}")
                    continue
            
            # 方法2: 查找并点击每个文章的复选框
            print("  [信息] 未找到全选按钮，尝试逐个选择文章...")
            
            checkbox_selectors = [
                'article.search-hits__hit input[type="checkbox"]',
                '.search-hits__hit input[type="checkbox"]',
                'input[class*="select"]',
            ]
            
            total_checked = 0
            for selector in checkbox_selectors:
                try:
                    checkboxes = await page.query_selector_all(selector)
                    if checkboxes:
                        print(f"  [找到] {len(checkboxes)} 个复选框 ({selector})")
                        
                        for i, checkbox in enumerate(checkboxes):
                            try:
                                is_visible = await checkbox.is_visible()
                                if is_visible:
                                    is_checked = await checkbox.is_checked()
                                    if not is_checked:
                                        await checkbox.scroll_into_view_if_needed()
                                        await checkbox.click()
                                        total_checked += 1
                                        
                                        # 每10个延迟一下
                                        if total_checked % 10 == 0:
                                            print(f"    已选中 {total_checked} 个...")
                                            await asyncio.sleep(0.5)
                            except Exception as e:
                                continue
                        
                        if total_checked > 0:
                            print(f"  [成功] 选中了 {total_checked} 篇文章")
                            await asyncio.sleep(1)
                            return True
                        
                except Exception as e:
                    continue
            
            # 方法3: 强制使用JavaScript选择
            print("  [信息] 尝试强制使用JavaScript选择所有文章...")
            try:
                result = await page.evaluate("""() => {
                    // 找到全选复选框
                    const selectAllCheckbox = document.querySelector('#search-hits__select-all');
                    if (selectAllCheckbox && !selectAllCheckbox.checked) {
                        selectAllCheckbox.checked = true;
                        selectAllCheckbox.dispatchEvent(new Event('change', { bubbles: true }));
                        selectAllCheckbox.dispatchEvent(new Event('click', { bubbles: true }));
                        return { method: 'select_all_checkbox', checked: 1 };
                    }
                    
                    // 备选：勾选所有文章复选框
                    const checkboxes = document.querySelectorAll('article.search-hits__hit input[type="checkbox"], .search-hits__hit input[type="checkbox"]');
                    let checked = 0;
                    checkboxes.forEach(cb => {
                        if (!cb.checked && cb.offsetParent !== null) {
                            cb.checked = true;
                            cb.dispatchEvent(new Event('change', { bubbles: true }));
                            checked++;
                        }
                    });
                    return { method: 'individual_checkboxes', checked: checked };
                }""")
                
                if result and result.checked > 0:
                    print(f"  [成功] 通过JS选中了 {result.checked} 个复选框 (方法: {result.method})")
                    await asyncio.sleep(1)
                    return True
                else:
                    print("  [警告] JS选择未找到可选择的复选框")
                    
            except Exception as e:
                print(f"  [警告] JS选择失败: {e}")
            
            print("  [警告] 未能选择文章，下载按钮可能不会被激活")
            return False
            
        except Exception as e:
            print(f"  [错误] 选择文章时出错: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def click_download_button_and_get_response(self, page: Page) -> Optional[Dict]:
        """
        点击页面上的Download PDF按钮并捕获响应
        
        流程：
        1. 先选择所有文章
        2. 点击Download PDF按钮
        3. 捕获API响应
        
        Returns:
            API响应数据
        """
        print("\n[模拟点击下载按钮]")
        print("-" * 40)
        
        # 第1步：先选择所有文章（关键步骤！）
        select_success = await self.select_all_articles(page)
        if not select_success:
            print("  [警告] 选择文章失败，下载按钮可能无法点击")
        
        # 等待一下确保UI更新
        await asyncio.sleep(2)
        
        # 调试：截图查看当前页面状态
        debug_screenshot = self.output_dir / "debug_before_click.png"
        try:
            await page.screenshot(path=str(debug_screenshot), full_page=True)
            print(f"  [调试] 已保存页面截图: {debug_screenshot}")
        except Exception as e:
            print(f"  [调试] 截图失败: {e}")
        
        try:
            # 设置响应监听 - 使用列表来存储捕获的数据
            captured_responses = []
            captured_requests = []
            
            async def handle_response(response):
                url = response.url
                if "nb-multidocs/get" in url:
                    print(f"  [捕获] 响应: {response.request.method} {url[:60]}... status={response.status}")
                    if response.request.method == "POST":
                        try:
                            body = await response.body()
                            captured_responses.append({
                                "url": url,
                                "status": response.status,
                                "headers": dict(response.headers),
                                "body": body.decode('utf-8', errors='replace')
                            })
                            print(f"  [成功] 已捕获POST响应，body长度: {len(body)} bytes")
                        except Exception as e:
                            print(f"  [警告] 读取响应失败: {e}")
            
            async def handle_request(request):
                if "nb-multidocs/get" in request.url:
                    print(f"  [捕获] 请求: {request.method} {request.url[:60]}...")
                    captured_requests.append(request.url)
            
            # 监听响应和请求
            page.on("response", lambda response: asyncio.create_task(handle_response(response)))
            page.on("request", lambda request: asyncio.create_task(handle_request(request)))
            print("  [调试] 已设置请求/响应监听器")
            
            # 查找并点击Download PDF按钮
            # NewsBank特定选择器 - 基于实际页面结构
            download_selectors = [
                # NewsBank特定的工具栏按钮
                '[data-testid="download-button"]',
                '[data-testid="download-pdf"]',
                '.toolbar-download',
                '.toolbar-download-button',
                '.action-download',
                '.multidoc-download',
                
                # 通用文本匹配
                'button:has-text("Download PDF")',
                'button:has-text("Download")',
                'a:has-text("Download PDF")',
                'a:has-text("Download")',
                
                # 类名匹配
                '[class*="download"]:visible',
                '[class*="toolbar"] [class*="download"]',
                '[class*="action"] [class*="download"]',
                
                # SVG图标附近的按钮
                'button:has(svg)',
                'a:has(svg)',
                
                # 按钮和链接的一般匹配
                'button[title*="download" i]',
                'a[title*="download" i]',
                'button[aria-label*="download" i]',
                'a[aria-label*="download" i]',
            ]
            
            download_button = None
            found_selector = None
            
            print("  [调试] 开始查找下载按钮...")
            for selector in download_selectors:
                try:
                    print(f"    尝试选择器: {selector}")
                    # 先检查元素是否存在（不等待）
                    button = await page.query_selector(selector)
                    if button:
                        # 滚动到元素位置
                        await button.scroll_into_view_if_needed()
                        await asyncio.sleep(0.5)  # 等待滚动完成
                        
                        is_visible = await button.is_visible()
                        is_enabled = await button.is_enabled()
                        box = await button.bounding_box()
                        print(f"    找到元素 - visible: {is_visible}, enabled: {is_enabled}, box: {box}")
                        if is_visible:
                            download_button = button
                            found_selector = selector
                            print(f"  [找到] 下载按钮: {selector}")
                            break
                except Exception as e:
                    print(f"    选择器失败: {str(e)[:80]}")
                    continue
            
            if not download_button:
                print("  [调试] 所有选择器都未找到，尝试搜索页面所有按钮...")
                # 调试：获取页面所有按钮的文本和位置信息
                buttons_info = await page.evaluate("""() => {
                    const buttons = document.querySelectorAll('button, a[role="button"], input[type="submit"], a.btn, a[class*="button"]');
                    return Array.from(buttons).map(b => {
                        const rect = b.getBoundingClientRect();
                        return {
                            tag: b.tagName,
                            text: b.textContent?.trim()?.substring(0, 80) || '',
                            class: b.className,
                            id: b.id,
                            type: b.type,
                            visible: b.offsetParent !== null && rect.width > 0 && rect.height > 0,
                            href: b.href || '',
                            rect: {top: rect.top, left: rect.left, width: rect.width, height: rect.height}
                        };
                    }).filter(b => b.visible);  // 只返回可见的按钮
                }""")
                print(f"  [调试] 页面上的可见按钮 ({len(buttons_info)}个):")
                for btn in buttons_info[:15]:  # 显示前15个
                    class_str = btn['class'][:40] if btn['class'] else 'none'
                    print(f"    - {btn['tag']}: '{btn['text']}' (class={class_str}, id={btn['id'] or 'none'}, href={btn['href'][:50] if btn['href'] else 'none'})")
                
                # 也检查是否有包含特定关键词的文本
                print("  [调试] 搜索包含 'Download' 或 'PDF' 的元素...")
                download_elements = await page.evaluate("""() => {
                    const allElements = document.querySelectorAll('*');
                    const results = [];
                    for (const el of allElements) {
                        const text = el.textContent?.toLowerCase() || '';
                        if ((text.includes('download') || text.includes('pdf')) && el.offsetParent !== null) {
                            const rect = el.getBoundingClientRect();
                            if (rect.width > 50 && rect.height > 20) {
                                results.push({
                                    tag: el.tagName,
                                    text: el.textContent?.trim()?.substring(0, 60) || '',
                                    class: el.className,
                                    id: el.id
                                });
                            }
                        }
                    }
                    return results.slice(0, 10);
                }""")
                if download_elements.length > 0:
                    print(f"  [调试] 找到 {download_elements.length} 个可能相关的元素:")
                    for el in download_elements:
                        print(f"    - {el.tag}: '{el.text}'")
                
                print("  [警告] 未找到下载按钮，尝试直接调用API")
                return None
            
            # 点击按钮前再次截图
            debug_screenshot2 = self.output_dir / "debug_before_click2.png"
            try:
                await page.screenshot(path=str(debug_screenshot2), full_page=True)
                print(f"  [调试] 已保存点击前截图: {debug_screenshot2}")
            except:
                pass
            
            # 点击按钮
            print(f"  [操作] 点击下载按钮 (选择器: {found_selector})...")
            
            # 尝试多种点击方式，从最真实的鼠标点击开始
            click_success = False
            
            # 方法1: 鼠标模拟点击（最真实）
            try:
                box = await download_button.bounding_box()
                if box:
                    x = box['x'] + box['width'] / 2
                    y = box['y'] + box['height'] / 2
                    print(f"  [尝试] 使用鼠标点击坐标: ({x}, {y})")
                    await page.mouse.click(x, y)
                    print("  [成功] 使用 mouse.click() 点击")
                    click_success = True
            except Exception as mouse_err:
                print(f"  [警告] 鼠标点击失败: {mouse_err}")
            
            # 方法2: 标准点击
            if not click_success:
                try:
                    await download_button.click(force=True)
                    print("  [成功] 使用 click(force=True) 点击")
                    click_success = True
                except Exception as click_err:
                    print(f"  [警告] 标准点击失败: {click_err}")
            
            # 方法3: JavaScript点击
            if not click_success:
                try:
                    await download_button.evaluate("element => element.click()")
                    print("  [成功] 使用JavaScript点击")
                    click_success = True
                except Exception as js_err:
                    print(f"  [错误] JavaScript点击也失败: {js_err}")
                    return None
            
            # 等待响应 - 增加等待时间
            print("  [等待] 等待API响应...")
            response_data = None
            for i in range(10):  # 最多等待10秒
                await asyncio.sleep(1)
                if captured_responses:
                    response_data = captured_responses[-1]  # 使用最后一个响应
                    print(f"  [成功] 捕获到响应 (状态: {response_data['status']})")
                    break
                if captured_requests and i >= 3:
                    print(f"  [信息] 已捕获请求但未收到响应，继续等待...")
            
            if response_data:
                # 保存响应内容用于调试
                debug_response = self.output_dir / "debug_api_response.html"
                try:
                    with open(debug_response, 'w', encoding='utf-8') as f:
                        f.write(response_data['body'][:5000])  # 保存前5000字符
                    print(f"  [调试] 已保存响应内容: {debug_response}")
                except:
                    pass
                return response_data
            else:
                print("  [警告] 未捕获到API响应")
                if captured_requests:
                    print(f"  [警告] 请求已发出 ({len(captured_requests)}个) 但没有捕获到响应数据")
                return None
                
        except Exception as e:
            print(f"  [错误] 点击下载按钮失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def call_download_api_directly(self, page: Page, article_ids: List[str], p_param: str = "AWGLNB") -> Optional[Dict]:
        """
        直接调用 nb-multidocs/get API
        
        这是更可靠的方式，可以直接控制payload并获取响应
        """
        print("\n[直接调用API]")
        print("-" * 40)
        
        try:
            # 使用用户提供的payload格式
            print(f"  [请求] POST {self.api_endpoint}")
            
            # 构建form data字符串（使用用户提供的参数格式）
            form_data_str = f"getaction=download&p={p_param}&pdf_path=multidocs&maxresults=100&pdf_params=action%3Dpdf%26format%3Dpdf%26pdf_enabled%3Dfalse%26load_pager%3Dfalse%26maxresults%3D100&zustat_category_override=co_sc_pdf_download"
            
            print(f"  [参数] {form_data_str[:100]}...")
            
            # 使用Playwright的API上下文发送POST请求（自动携带cookies）
            try:
                # 方法1: 使用page.context.request
                api_response = await page.context.request.post(
                    self.api_endpoint,
                    data=form_data_str,
                    headers={
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'X-Requested-With': 'XMLHttpRequest',
                        'Referer': page.url
                    }
                )
                
                response_body = await api_response.text()
                response = {
                    "status": api_response.status,
                    "body": response_body,
                    "url": api_response.url
                }
            except Exception as api_err:
                print(f"  [警告] API上下文请求失败: {api_err}")
                # 方法2: 回退到page.evaluate
                response = await page.evaluate("""async ({url, formDataStr}) => {
                    try {
                        const response = await fetch(url, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/x-www-form-urlencoded',
                                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                                'X-Requested-With': 'XMLHttpRequest'
                            },
                            body: formDataStr,
                            credentials: 'include'
                        });
                        
                        const text = await response.text();
                        return {
                            status: response.status,
                            body: text,
                            url: response.url,
                            ok: response.ok
                        };
                    } catch (e) {
                        return {status: 0, body: '', error: e.message};
                    }
                }""", {"url": self.api_endpoint, "formDataStr": form_data_str})
            
            if response and response.get('status') == 200:
                print(f"  [成功] API调用成功 (状态: {response['status']})")
                return {
                    "status": response['status'],
                    "body": response['body'],
                    "url": response.get('url', self.api_endpoint)
                }
            else:
                print(f"  [警告] API调用失败 (状态: {response.get('status') if response else 'None'})")
                return None
                
        except Exception as e:
            print(f"  [错误] 直接调用API失败: {e}")
            return None
    
    async def fetch_articles_via_api(self, 
                                     page: Page, 
                                     base_url: str,
                                     page_num: int = 1) -> List[ArticleInfo]:
        """
        通过API获取文章列表
        
        方法1: 点击按钮触发API（首选）
        方法2: 直接调用API（备选）
        """
        print(f"\n[第 {page_num} 页] 获取文章列表")
        print("-" * 40)
        print(f"  [调试] 当前URL: {page.url[:100]}...")
        
        articles = []
        
        try:
            # 获取页面HTML以提取文章ID
            html_content = await page.content()
            
            article_ids = self._extract_article_ids_from_page(html_content)
            
            print(f"  [扫描] 从页面提取到 {len(article_ids)} 个文章ID")
            
            # 从当前URL提取参数
            parsed_url = urlparse(page.url)
            query_params = parse_qs(parsed_url.query)
            p_param = query_params.get('p', ['AWGLNB'])[0]
            
            # 新流程：先选中所有文章，然后直接调用API（不点击下载按钮，避免弹窗）
            print(f"  [步骤1] 选中所有文章...")
            select_success = await self.select_all_articles(page)
            if select_success:
                print(f"  [成功] 文章已选中")
            else:
                print(f"  [警告] 选择文章可能未成功，继续尝试调用API...")
            
            # 等待一下确保选中状态生效
            await asyncio.sleep(1)
            
            # 步骤2: 直接调用API获取文章数据
            print(f"  [步骤2] 调用API获取文章数据...")
            response_data = await self.call_download_api_directly(page, article_ids, p_param)
            
            if response_data and response_data.get('body'):
                body = response_data['body']
                print(f"  [调试] API响应长度: {len(body)} bytes")
                print(f"  [调试] 响应前500字符: {body[:500]}")
                
                # 检查是否是PDF或二进制数据
                if body.startswith('%PDF'):
                    print("  [警告] API返回的是PDF文件，不是HTML")
                    # 保存PDF
                    pdf_path = self.output_dir / f"articles_page_{page_num}.pdf"
                    with open(pdf_path, 'wb') as f:
                        f.write(body.encode('utf-8', errors='replace'))
                    print(f"  [保存] PDF已保存: {pdf_path}")
                    # 回退到页面解析
                    articles = await self._parse_articles_from_page(page, page_num)
                else:
                    # 解析HTML响应
                    articles = self._parse_api_response(body, page_num)
                    print(f"  [成功] 从API响应解析到 {len(articles)} 篇文章")
            else:
                # 备选: 直接解析页面获取文章信息
                print("  [备选] 直接解析页面内容...")
                articles = await self._parse_articles_from_page(page, page_num)
            
            return articles
            
        except Exception as e:
            print(f"  [错误] API请求失败: {e}")
            import traceback
            traceback.print_exc()
            # 失败时回退到页面解析
            return await self._parse_articles_from_page(page, page_num)
    
    async def _parse_articles_from_page(self, page: Page, page_num: int) -> List[ArticleInfo]:
        """从页面HTML中解析文章列表"""
        articles = []
        
        try:
            # 查找文章元素
            article_elements = await page.query_selector_all('article.search-hits__hit')
            
            if not article_elements:
                print(f"  [警告] 未找到文章元素")
                return articles
            
            print(f"  [解析] 找到 {len(article_elements)} 篇文章元素")
            
            for i, elem in enumerate(article_elements, 1):
                try:
                    # 提取标题
                    title_elem = await elem.query_selector("h3.search-hits__hit__title a")
                    if not title_elem:
                        continue
                    
                    title = await title_elem.inner_text()
                    title = title.replace("Go to the document viewer for ", "").strip()
                    
                    # 提取URL
                    href = await title_elem.get_attribute("href") or ""
                    full_url = urljoin(page.url, href)
                    
                    # 提取日期
                    date = ""
                    date_elem = await elem.query_selector("li.search-hits__hit__meta__item--display-date")
                    if date_elem:
                        date = await date_elem.inner_text()
                    
                    # 提取来源
                    source = ""
                    source_elem = await elem.query_selector("li.search-hits__hit__meta__item--source")
                    if source_elem:
                        source = await source_elem.inner_text()
                    
                    # 提取作者
                    author = ""
                    author_elem = await elem.query_selector("li.search-hits__hit__meta__item--author")
                    if author_elem:
                        author = await author_elem.inner_text()
                    
                    # 提取预览
                    preview = ""
                    preview_elem = await elem.query_selector("div.preview-first-paragraph")
                    if preview_elem:
                        preview = await preview_elem.inner_text()
                    
                    preview = preview.strip()
                    word_count = len(preview.split()) if preview else 0
                    
                    # 提取文章ID
                    article_id = None
                    id_match = re.search(r'doc=([^&]+)', href)
                    if id_match:
                        article_id = unquote(id_match.group(1))
                    
                    article = ArticleInfo(
                        title=title[:300],
                        date=date.strip()[:100],
                        source=source.strip()[:200],
                        author=author.strip()[:100],
                        preview=preview[:1000],
                        url=full_url[:500],
                        page_num=page_num,
                        article_id=article_id,
                        word_count=word_count
                    )
                    
                    articles.append(article)
                    
                    # 显示前几篇文章
                    if i <= 3:
                        print(f"    [{i}] {title[:50]}... ({word_count}词)")
                
                except Exception as e:
                    print(f"    [错误] 解析文章失败: {e}")
                    continue
            
            return articles
            
        except Exception as e:
            print(f"  [错误] 解析页面失败: {e}")
            return articles
    
    def _parse_api_response(self, response_body: str, page_num: int) -> List[ArticleInfo]:
        """
        解析API响应内容 - 从Download按钮的响应中提取文章
        
        API响应通常包含HTML格式的多篇文章，每篇都有完整或部分文章内容
        """
        articles = []
        
        try:
            # 尝试解析为JSON
            try:
                data = json.loads(response_body)
                print(f"  [解析] 响应为JSON格式")
                
                # 根据实际响应结构调整
                if isinstance(data, dict):
                    # 可能包含文章列表的键
                    for key in ['articles', 'docs', 'results', 'data', 'items', 'documents']:
                        if key in data:
                            items = data[key]
                            if isinstance(items, list):
                                for item in items:
                                    article = self._convert_api_item_to_article(item, page_num)
                                    if article:
                                        articles.append(article)
                                print(f"  [成功] 从JSON解析到 {len(articles)} 篇文章")
                                return articles
                
                # 如果找不到特定key，尝试直接遍历
                for key, value in data.items():
                    if isinstance(value, list) and len(value) > 0:
                        for item in value:
                            article = self._convert_api_item_to_article(item, page_num)
                            if article:
                                articles.append(article)
                        if articles:
                            print(f"  [成功] 从JSON key '{key}' 解析到 {len(articles)} 篇文章")
                            return articles
                
            except json.JSONDecodeError:
                # 不是JSON，是HTML
                pass
            
            # 解析HTML响应 - Download API通常返回包含多篇文章的HTML
            print(f"  [解析] 响应为HTML格式，长度: {len(response_body)}")
            
            # 保存响应内容用于调试分析
            debug_file = self.output_dir / f"debug_response_page{page_num}.html"
            try:
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(response_body)
                print(f"  [调试] 已保存响应HTML: {debug_file}")
            except Exception as e:
                print(f"  [调试] 保存响应失败: {e}")
            
            # 查找文章容器 - 可能包含完整文章内容
            # NewsBank multidoc下载响应通常包含多个document或article区块
            article_blocks = []
            
            # 尝试多种文章分隔模式
            # API响应使用 multidocs_item 类（注意class名可能有尾部空格）
             
            # 方法1: 使用前瞻断言正确分割（推荐）
            # 匹配从 <div class="multidocs_item "> 到下一个 <div class="multidocs_item "> 之前
            # 这样可以正确处理HTML中嵌套的多层div
            pattern1 = r'<div class="multidocs_item ">(.*?)(?=<div class="multidocs_item ">)'
            matches1 = re.findall(pattern1, response_body, re.DOTALL | re.IGNORECASE)
            if matches1 and len(matches1) >= 1:
                article_blocks = matches1
                print(f"  [匹配] 使用前瞻断言模式找到 {len(matches1)} 个文章块")
                
                # 获取最后一个块 - 从最后一个 multidocs_item 开始到文档末尾
                # 使用 last_index 来找到最后一个
                last_start = response_body.rfind('<div class="multidocs_item ">')
                if last_start > 0:
                    last_content = response_body[last_start + len('<div class="multidocs_item ">'):]
                    # 找到最后一个块的结束位置
                    if last_content.strip():
                        article_blocks.append(last_content)
                        print(f"  [匹配] 添加最后一个块，总计 {len(article_blocks)} 个")
            
            # 方法2: 如果方法1失败，尝试匹配到最后一个 </div></div>
            if not article_blocks:
                pattern2 = r'<div class="multidocs_item ">(.*?)</div>\s*</div>'
                matches2 = re.findall(pattern2, response_body, re.DOTALL | re.IGNORECASE)
                if matches2 and len(matches2) >= 1:
                    article_blocks = matches2
                    print(f"  [匹配] 使用贪婪模式找到 {len(matches2)} 个文章块")
            
            # 方法3: 回退到原来的模式（可能匹配不正确）
            if not article_blocks:
                separators = [
                    (r'<div[^>]*class="[^\"]*multidocs_item[^\"]*"\s*>', r'</div>'),
                    (r'<div[^>]*class="[^\"]*multidocs_item[^\"]*"[^>]*>', r'</div>'),
                ]
                for start_pattern, end_pattern in separators:
                    pattern = f'{start_pattern}(.*?){end_pattern}'
                    matches = re.findall(pattern, response_body, re.DOTALL | re.IGNORECASE)
                    if matches and len(matches) > 1:
                        article_blocks = matches
                        print(f"  [匹配] 使用回退模式找到 {len(matches)} 个文章块")
                        break
            
            # 如果没找到分隔块，尝试整个响应作为一个文章
            if not article_blocks:
                print(f"  [调试] 未找到文章分隔块，尝试整个响应作为单个文章")
                article_blocks = [response_body]
            
            print(f"  [调试] 开始解析 {len(article_blocks)} 个文章块...")
            
            # 解析每个文章块
            for i, html_snippet in enumerate(article_blocks):
                article = self._parse_full_article_from_html(html_snippet, page_num, i+1)
                
                # 只检查是否有标题
                if article and article.title and len(article.title) > 3:
                    articles.append(article)
                    if len(articles) <= 3:  # 只打印前3篇的调试信息
                        print(f"    [调试] 文章{len(articles)}: {article.title[:50]}... (字数: {article.word_count})")
                elif article and article.title:
                    if len(articles) < 3:
                        print(f"    [过滤] 标题太短: {article.title[:50]}...")
            
            if articles:
                print(f"  [成功] 从HTML解析到 {len(articles)} 篇文章")
            else:
                print(f"  [警告] 未能从HTML解析到文章，尝试备用解析...")
                # 备用：只提取标题
                articles = self._extract_articles_fallback(response_body, page_num)
            
            return articles
            
        except Exception as e:
            print(f"  [错误] 解析API响应失败: {e}")
            import traceback
            traceback.print_exc()
            return articles
    
    def _parse_full_article_from_html(self, html_snippet: str, page_num: int, index: int) -> Optional[ArticleInfo]:
        """从HTML片段中解析完整文章信息（包括全文）- 支持API响应的multidocs格式"""
        try:
            # 提取标题 - API响应使用 h1.document-view__title
            title = ""
            
            # 方法1: API响应格式 h1.document-view__title
            title_match = re.search(r'<h1[^>]*class="[^"]*document-view__title[^"]*"[^>]*>(.*?)</h1>', 
                                   html_snippet, re.DOTALL | re.IGNORECASE)
            if title_match:
                title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
            
            # 方法2: 回退到任何 h1/h2/h3
            if not title:
                h_match = re.search(r'<h[123][^>]*>(.*?)</h[123]>', html_snippet, re.DOTALL | re.IGNORECASE)
                if h_match:
                    title = re.sub(r'<[^>]+>', '', h_match.group(1)).strip()
                    print(f"    [解析调试] 方法2找到标题: {title[:50]}")
            
            # 过滤无效标题
            if not title or len(title) < 3 or title.startswith("<"):
                return None
            
            # 提取日期 - API格式 span.display-date
            date = ""
            date_match = re.search(r'<span[^>]*class="[^"]*display-date[^"]*"[^>]*>(.*?)</span>', 
                                  html_snippet, re.DOTALL | re.IGNORECASE)
            if date_match:
                date = re.sub(r'<[^>]+>', '', date_match.group(1)).strip()
            
            # 提取来源 - API格式 span.source
            source = ""
            source_match = re.search(r'<span[^>]*class="[^"]*source[^"]*"[^>]*>(.*?)</span>', 
                                    html_snippet, re.DOTALL | re.IGNORECASE)
            if source_match:
                source = re.sub(r'<[^>]+>', '', source_match.group(1)).strip()
            
            # 提取作者 - API格式 span.author
            author = ""
            author_match = re.search(r'<span[^>]*class="[^"]*author[^"]*"[^>]*>(.*?)</span>', 
                                    html_snippet, re.DOTALL | re.IGNORECASE)
            if author_match:
                author_text = re.sub(r'<[^>]+>', '', author_match.group(1)).strip()
                # 移除 "Author: " 前缀
                author = re.sub(r'^Author:\s*', '', author_text)
            
            # 提取文章ID - 从OpenURL链接中提取
            article_id = None
            openurl_match = re.search(r'rft_dat=document_id:([^"]+)', html_snippet)
            if openurl_match:
                article_id = unquote(openurl_match.group(1))
            
            # 提取URL
            url = ""
            if article_id:
                url = f"https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/document-view?p=AWGLNB&doc={article_id}"
            
            # 提取全文 - API格式 div.document-view__body
            full_text = ""
            body_match = re.search(r'<div[^>]*class="[^"]*document-view__body[^"]*"[^>]*>(.*?)</div>', 
                                  html_snippet, re.DOTALL | re.IGNORECASE)
            if body_match:
                # 将 <br/> 转换为换行符
                body_html = body_match.group(1)
                body_html = re.sub(r'<br\s*/?>', '\n', body_html, flags=re.IGNORECASE)
                full_text = re.sub(r'<[^>]+>', '', body_html).strip()
            
            # 确保有预览
            preview = full_text[:500] if full_text else ""
            
            word_count = len(full_text.split()) if full_text else 0
            
            if title:  # 只有有标题才返回
                return ArticleInfo(
                    title=title[:300],
                    date=date[:100],
                    source=source[:200],
                    author=author[:100],
                    preview=preview[:1000],
                    url=url[:500],
                    page_num=page_num,
                    article_id=article_id,
                    word_count=word_count,
                    full_text=full_text
                )
            
            return None
            
        except Exception as e:
            return None
    
    def _extract_articles_fallback(self, response_body: str, page_num: int) -> List[ArticleInfo]:
        """备用方法：只提取标题和基本信息"""
        articles = []
        
        # 提取所有标题
        title_pattern = r'<h[23][^>]*>(.*?)</h[23]>'
        titles = re.findall(title_pattern, response_body, re.DOTALL | re.IGNORECASE)
        
        for i, title_html in enumerate(titles, 1):
            title = re.sub(r'<[^>]+>', '', title_html).strip()
            if title and len(title) > 5:
                # 尝试在这个标题附近找更多内容
                # 获取标题后的部分内容
                title_pos = response_body.find(title_html)
                nearby_content = response_body[title_pos:title_pos+2000] if title_pos >= 0 else ""
                
                # 提取文章ID
                article_id = None
                doc_match = re.search(r'doc=([^&"\s]+)', nearby_content)
                if doc_match:
                    article_id = unquote(doc_match.group(1))
                
                articles.append(ArticleInfo(
                    title=title[:300],
                    date="",
                    source="",
                    author="",
                    preview=nearby_content[:500],
                    url="",
                    page_num=page_num,
                    article_id=article_id,
                    word_count=0
                ))
        
        return articles
    
    def _convert_api_item_to_article(self, item: Dict, page_num: int) -> Optional[ArticleInfo]:
        """将API返回的JSON项转换为ArticleInfo"""
        try:
            title = item.get('title', item.get('headline', item.get('name', '')))
            date = item.get('date', item.get('pubdate', item.get('published', '')))
            source = item.get('source', item.get('publication', ''))
            author = item.get('author', item.get('byline', ''))
            preview = item.get('preview', item.get('abstract', item.get('snippet', '')))
            url = item.get('url', item.get('link', ''))
            doc_id = item.get('doc', item.get('id', item.get('document_id', None)))
            
            word_count = len(preview.split()) if preview else 0
            
            return ArticleInfo(
                title=str(title)[:300],
                date=str(date)[:100],
                source=str(source)[:200],
                author=str(author)[:100],
                preview=str(preview)[:1000],
                url=str(url)[:500],
                page_num=page_num,
                article_id=str(doc_id) if doc_id else None,
                word_count=word_count
            )
        except Exception:
            return None
    
    def _parse_article_html(self, html_snippet: str, page_num: int) -> Optional[ArticleInfo]:
        """从HTML片段中解析文章信息"""
        try:
            # 提取标题
            title_match = re.search(r'<h[123][^>]*>(.*?)</h[123]>', html_snippet, re.DOTALL | re.IGNORECASE)
            title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip() if title_match else ""
            
            # 提取日期
            date_match = re.search(r'class="[^"]*date[^"]*"[^>]*>(.*?)</', html_snippet, re.DOTALL | re.IGNORECASE)
            date = re.sub(r'<[^>]+>', '', date_match.group(1)).strip() if date_match else ""
            
            # 提取来源
            source_match = re.search(r'class="[^"]*source[^"]*"[^>]*>(.*?)</', html_snippet, re.DOTALL | re.IGNORECASE)
            source = re.sub(r'<[^>]+>', '', source_match.group(1)).strip() if source_match else ""
            
            # 提取预览
            preview_match = re.search(r'class="[^"]*preview[^"]*"[^>]*>(.*?)</', html_snippet, re.DOTALL | re.IGNORECASE)
            preview = re.sub(r'<[^>]+>', '', preview_match.group(1)).strip() if preview_match else ""
            
            # 提取URL
            url_match = re.search(r'href="([^"]+)"', html_snippet)
            url = url_match.group(1) if url_match else ""
            
            # 提取文章ID
            doc_match = re.search(r'doc=([^&"\s]+)', html_snippet)
            doc_id = unquote(doc_match.group(1)) if doc_match else None
            
            word_count = len(preview.split()) if preview else 0
            
            if title:
                return ArticleInfo(
                    title=title[:300],
                    date=date[:100],
                    source=source[:200],
                    author="",
                    preview=preview[:1000],
                    url=url[:500],
                    page_num=page_num,
                    article_id=doc_id,
                    word_count=word_count
                )
            
            return None
            
        except Exception:
            return None
    
    async def scan_all_pages(self, page: Page, base_url: str) -> List[ArticleInfo]:
        """扫描所有页面的文章"""
        print("\n" + "=" * 70)
        print("开始扫描文章列表")
        print("=" * 70)
        
        all_articles = []
        current_url = base_url
        
        for page_num in range(1, self.max_pages + 1):
            # 获取当前页面的文章
            articles = await self.fetch_articles_via_api(page, current_url, page_num)
            
            if not articles:
                print(f"\n[第 {page_num} 页] 未找到文章，结束扫描")
                break
            
            all_articles.extend(articles)
            self.stats["total_pages"] += 1
            self.stats["total_articles"] += len(articles)
            
            print(f"\n[第 {page_num} 页] 成功获取 {len(articles)} 篇文章")
            
            # 如果已经获取了100篇文章（maxresults=100），停止扫描
            # 因为API一次最多返回100篇
            if len(articles) >= 100:
                print(f"  [信息] 已获取100篇文章，达到API限制，停止扫描")
                break
            
            # 如果文章数量少于100，说明没有更多页面了
            if len(articles) < 100:
                print(f"  [信息] 只有 {len(articles)} 篇文章，已获取全部内容")
                break
        
        return all_articles
    
    def display_articles(self, articles: List[ArticleInfo]):
        """显示文章列表"""
        print("\n" + "=" * 70)
        print(f"文章列表 (共 {len(articles)} 篇)")
        print("=" * 70)
        
        for i, article in enumerate(articles[:30], 1):
            quality = "✓" if article.word_count >= 30 else "○"
            print(f"\n[{i:3d}] {quality} {article.title[:60]}...")
            print(f"      日期: {article.date} | 来源: {article.source[:30]}")
            print(f"      预览: {article.word_count}词")
            if article.article_id:
                print(f"      ID: {article.article_id[:40]}...")
        
        if len(articles) > 30:
            print(f"\n... 还有 {len(articles) - 30} 篇文章 ...")
        
        print("=" * 70)
    
    async def download_article_full_text(self, page: Page, article: ArticleInfo) -> str:
        """下载文章完整内容"""
        if not article.url:
            return ""
        
        try:
            await page.goto(article.url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)
            
            # 尝试提取全文
            full_text = ""
            selectors = [
                '.document-view__body',
                '.gnus-doc__body',
                '.document-text',
                'article'
            ]
            
            for selector in selectors:
                elem = await page.query_selector(selector)
                if elem:
                    full_text = await elem.inner_text()
                    if len(full_text.strip()) > 100:
                        break
            
            # 备选方案
            if not full_text:
                paragraphs = await page.query_selector_all('p')
                texts = []
                for p in paragraphs:
                    text = await p.inner_text()
                    if len(text.strip()) > 20:
                        texts.append(text)
                full_text = '\n\n'.join(texts)
            
            return full_text
            
        except Exception as e:
            print(f"    [错误] 下载全文失败: {e}")
            return ""
    
    async def batch_download_full_text(self, page: Page, articles: List[ArticleInfo]) -> None:
        """批量下载文章全文 - 使用更高效的并发方式"""
        articles_need_download = [a for a in articles if not a.full_text or len(a.full_text) < 100]
        
        if not articles_need_download:
            return
        
        print(f"\n[批量下载] 需要下载 {len(articles_need_download)} 篇文章的全文...")
        
        for i, article in enumerate(articles_need_download, 1):
            print(f"  [{i}/{len(articles_need_download)}] 下载: {article.title[:40]}...")
            try:
                full_text = await self.download_article_full_text(page, article)
                if full_text:
                    article.full_text = full_text
                    article.word_count = len(full_text.split())
                    print(f"    ✓ 成功 ({len(full_text)} 字符)")
                else:
                    print(f"    ✗ 无内容")
            except Exception as e:
                print(f"    ✗ 失败: {e}")
            
            # 延迟避免被封
            if i < len(articles_need_download):
                await asyncio.sleep(1)
        
        print(f"[批量下载] 完成")

    async def save_articles(self, 
                           page: Page, 
                           articles: List[ArticleInfo],
                           base_url: str,
                           download_all: bool = False):
        """保存文章 - 优先使用API响应中已获取的全文"""
        print("\n" + "=" * 70)
        print("开始保存文章")
        print("=" * 70)
        
        # 统计有多少篇文章已经有全文
        articles_with_fulltext = sum(1 for a in articles if a.full_text and len(a.full_text) > 100)
        articles_without_fulltext = len(articles) - articles_with_fulltext
        
        if articles_with_fulltext == len(articles):
            print(f"[说明] 所有 {len(articles)} 篇文章已从API获取全文，直接保存")
        elif articles_with_fulltext > 0:
            print(f"[说明] {articles_with_fulltext}/{len(articles)} 篇文章有全文，其余 {articles_without_fulltext} 篇需要访问页面获取")
        else:
            print(f"[说明] API响应中无全文，全部 {len(articles)} 篇文章需要访问页面获取")
        
        # 注意：如果API响应成功，文章应该已经包含全文
        # 只有在API响应不包含全文时，才需要批量下载
        if articles_without_fulltext > 0 and articles_with_fulltext == 0:
            print(f"[说明] API响应不包含全文，需要逐个访问页面获取")
            await self.batch_download_full_text(page, articles)
        elif articles_without_fulltext > 0 and articles_with_fulltext > 0:
            print(f"[说明] 部分文章缺少全文，但API已成功提供{articles_with_fulltext}篇，直接保存现有内容")
        
        if not download_all:
            # 交互式选择
            print("\n输入要保存的文章编号（用逗号分隔）")
            print("例如: 1,3,5,7-10")
            print("输入 'all' 保存所有文章")
            print("输入 'q' 跳过")
            
            user_input = input("\n请选择: ").strip().lower()
            
            if user_input == 'q':
                print("跳过保存")
                return
            
            if user_input == 'all':
                selected = articles
            else:
                # 解析选择
                selected_indices = set()
                for part in user_input.split(','):
                    part = part.strip()
                    if '-' in part:
                        start, end = part.split('-')
                        selected_indices.update(range(int(start)-1, int(end)))
                    else:
                        selected_indices.add(int(part) - 1)
                
                selected = [articles[i] for i in selected_indices if 0 <= i < len(articles)]
        else:
            selected = articles
        
        if not selected:
            print("未选择任何文章")
            return
        
        print(f"\n将保存 {len(selected)} 篇文章...")
        
        downloaded = 0
        
        for i, article in enumerate(selected[:self.download_limit], 1):
            print(f"\n[{i}/{len(selected)}] {article.title[:50]}...")
            
            try:
                # 使用API响应中已获取的内容
                full_text = article.full_text
                
                # 如果API没有提供全文，但有预览，使用预览
                if (not full_text or len(full_text.strip()) < 50) and article.preview:
                    full_text = article.preview
                    print(f"    [信息] API未提供全文，使用预览内容 ({len(full_text)} 字符)")
                
                if not full_text or len(full_text.strip()) < 50:
                    print(f"    [跳过] 无有效内容")
                    self.stats["skipped"] += 1
                    continue
                
                print(f"    [信息] 内容长度: {len(full_text)} 字符")
                
                # 保存文件
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_title = "".join(c for c in article.title[:50] if c.isalnum() or c in (' ', '-', '_')).strip()
                filename = f"{i:03d}_{timestamp}_{safe_title}.txt"
                filepath = self.output_dir / filename
                
                content = f"""Title: {article.title}
Date: {article.date}
Source: {article.source}
Author: {article.author}
URL: {article.url}
Article ID: {article.article_id}
Original Search URL: {base_url}
Downloaded at: {datetime.now().isoformat()}
Page: {article.page_num}
Word Count: {len(full_text.split())}

Preview:
{article.preview}

Full Text:
{full_text}

{'='*70}
"""
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                downloaded += 1
                self.stats["downloaded"] += 1
                print(f"    [成功] 已保存 ({len(full_text)} 字符) -> {filename}")
                
            except Exception as e:
                print(f"    [错误] 保存失败: {e}")
                self.stats["errors"].append(f"{article.title}: {str(e)}")
                continue
            
            # 延迟，避免操作过快
            await asyncio.sleep(0.5)
        
        print(f"\n[完成] 成功保存 {downloaded} 篇文章")
    
    async def download_from_url(self, url: str, download_all: bool = False):
        """从URL下载文章的主方法"""
        print("=" * 80)
        print("NewsBank 按钮下载器")
        print("=" * 80)
        print(f"\n目标URL: {url[:80]}...")
        print(f"最大页数: {self.max_pages}")
        print(f"下载限制: {self.download_limit} 篇")
        
        # 启动浏览器
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.headless,
                args=['--disable-blink-features=AutomationControlled']
            )
            
            context = await browser.new_context(
                storage_state=str(self.cookie_file) if self.cookie_file.exists() else None,
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                accept_downloads=False  # 阻止PDF下载弹窗
            )
            
            page = await context.new_page()
            
            # 监听并取消下载事件
            async def handle_download(download):
                print(f"  [信息] 阻止了下载: {download.suggested_filename}")
                await download.cancel()
            
            page.on("download", lambda d: asyncio.create_task(handle_download(d)))
            
            try:
                # 检查登录
                if not await self.check_login(context):
                    if self.headless:
                        print("[错误] 无头模式下无法登录")
                        return
                    
                    if not await self.do_login(page):
                        return
                    
                    await context.storage_state(path=str(self.cookie_file))
                
                # 访问URL
                print(f"\n[访问页面]")
                await page.goto(url, wait_until="networkidle", timeout=60000)
                await asyncio.sleep(2)
                
                print(f"页面标题: {await page.title()}")
                
                # 扫描所有页面
                self.articles = await self.scan_all_pages(page, url)
                
                if not self.articles:
                    print("\n[警告] 未找到任何文章")
                    return
                
                # 显示文章列表
                self.display_articles(self.articles)
                
                # 保存文章列表到JSON
                json_path = self.output_dir / f"article_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump([a.to_dict() for a in self.articles], f, indent=2, ensure_ascii=False)
                print(f"\n文章列表已保存: {json_path}")
                
                # 下载文章
                await self.save_articles(page, self.articles, url, download_all)
                
                # 最终报告
                print("\n" + "=" * 80)
                print("下载完成报告")
                print("=" * 80)
                print(f"扫描页数: {self.stats['total_pages']}")
                print(f"发现文章: {self.stats['total_articles']}")
                print(f"成功下载: {self.stats['downloaded']}")
                print(f"跳过/失败: {self.stats['skipped']}")
                print(f"输出目录: {self.output_dir.absolute()}")
                
                if self.stats["errors"]:
                    print(f"\n错误 ({len(self.stats['errors'])}):")
                    for error in self.stats["errors"][:5]:
                        print(f"  - {error}")
                
                print("=" * 80)
                
                if not self.headless:
                    print("\n[INFO] 浏览器将保持打开10秒...")
                    await asyncio.sleep(10)
                
            except Exception as e:
                print(f"\n[错误] {e}")
                import traceback
                traceback.print_exc()
            
            finally:
                await context.close()
                await browser.close()


def main():
    parser = argparse.ArgumentParser(
        description="NewsBank 按钮下载器 - 模拟点击Download PDF按钮获取文章",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用方法示例:

1. 基础使用（交互式选择）:
   python newsbank_button_downloader.py "https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/results?..."

2. 自动下载所有文章:
   python newsbank_button_downloader.py "URL" --download-all

3. 限制页数:
   python newsbank_button_downloader.py "URL" --max-pages 5

4. 无头模式:
   python newsbank_button_downloader.py "URL" --headless --download-all

URL获取方法:
   1. 在浏览器中访问NewsBank并搜索
   2. 调整搜索条件到满意结果
   3. 复制浏览器地址栏的URL
   4. 使用本工具下载
        """
    )
    
    parser.add_argument("url", help="NewsBank搜索URL")
    
    parser.add_argument("--max-pages", type=int, default=10,
                       help="最大扫描页数 (默认: 10)")
    
    parser.add_argument("--download-limit", type=int, default=50,
                       help="最大下载文章数 (默认: 50)")
    
    parser.add_argument("--download-all", action="store_true",
                       help="自动下载所有文章（跳过交互选择）")
    
    parser.add_argument("--headless", action="store_true",
                       help="无头模式")
    
    parser.add_argument("--output-dir", default="articles_button",
                       help="输出目录 (默认: articles_button)")
    
    args = parser.parse_args()
    
    # 创建下载器
    downloader = NewsBankButtonDownloader(
        headless=args.headless,
        max_pages=args.max_pages,
        download_limit=args.download_limit,
        output_dir=args.output_dir
    )
    
    # 执行下载
    asyncio.run(downloader.download_from_url(args.url, args.download_all))


if __name__ == "__main__":
    exit(main())
