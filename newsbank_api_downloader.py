# -*- coding: utf-8 -*-
"""
NewsBank API 下载器
通过直接调用NewsBank的API获取文章内容

功能：
1. 用户输入NewsBank搜索结果页URL
2. 脚本访问页面并获取必要的参数
3. 直接调用API获取多篇文章完整内容
4. 从响应中解析文章列表和内容
5. 保存文章为文本文件

使用方法：
    python newsbank_api_downloader.py "https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/results?..."
    
    python newsbank_api_downloader.py "URL" --max-pages 3
    
    python newsbank_api_downloader.py "URL" --download-all

作者: AI Assistant
日期: 2026-02-15
"""

import asyncio
import argparse
import json
import re
import time
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from urllib.parse import urlparse, parse_qs, urljoin, quote, unquote
from dataclasses import dataclass, asdict

from playwright.async_api import async_playwright, Page, BrowserContext

# 尝试导入 openai（用于LLM调用）
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("[警告] openai 包未安装，LLM筛选功能不可用。请运行: pip install openai")

# 尝试加载 .env 文件
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


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


class NewsBankAPIDownloader:
    """NewsBank API 下载器 - 直接调用API获取文章"""
    
    def __init__(self,
                 headless: bool = False,
                 max_pages: int = 10,
                 output_dir: str = "articles_api",
                 request_delay: float = 2.0):
        self.headless = headless
        self.max_pages = max_pages
        self.request_delay = request_delay  # 请求间隔（秒），防止被封
        
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
    
    async def _safe_delay(self, seconds: float = 2.0):
        """安全的延迟，带有随机波动以模拟人类行为"""
        import random
        delay = seconds if seconds else self.request_delay
        # 添加随机波动 (±20%)，模拟人类行为
        jitter = delay * 0.2 * (random.random() * 2 - 1)
        await asyncio.sleep(delay + jitter)
    
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
    
    def _build_search_url(self, 
                         keyword: str,
                         maxresults: int = 200,
                         source: str = "Australian Financial Review Collection",
                         year_from: Optional[int] = None,
                         year_to: Optional[int] = None,
                         first_page_maxresults: int = 60) -> str:
        """
        根据关键字构建NewsBank搜索URL
        
        参数:
            keyword: 搜索关键字
            maxresults: 每页结果数（后续页默认20）
            source: 数据源名称
            year_from: 起始年份
            year_to: 结束年份
            first_page_maxresults: 第一页结果数（默认60）
        
        返回:
            完整的搜索URL
        """
        # 基础URL
        base_url = "https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/results"
        
        # 参数构建 - 与用户提供的URL一致
        # sort=_rank_:D 表示按相关性排序
        params = {
            "p": "AWGLNB",
            "hide_duplicates": "2",
            "fld-base-0": "alltext",
            "sort": "_rank_:D",  # 按相关性排序
            "maxresults": str(first_page_maxresults),  # 第一页使用60
            "val-base-0": keyword,
        }
        
        # 构建t参数（数据源）
        source_encoded = quote(source)
        params["t"] = f"favorite:AFRWAFRN!{source_encoded}"
        
        # 构建年份过滤
        if year_from or year_to:
            if year_from and year_to:
                year_filter = f"year:{year_from}%21{year_to}"
            elif year_from:
                year_filter = f"year:{year_from}"
            else:
                year_filter = f"year:{year_to}"
            params["t"] = f"{params['t']}/{year_filter}"
        
        # 构建URL - 使用与参考URL一致的格式（但保留YMD_date:D排序）
        query_string = f"p=AWGLNB&hide_duplicates=2&fld-base-0=alltext&sort=YMD_date:D&maxresults={params['maxresults']}&val-base-0={quote(params['val-base-0'])}&t={quote(params['t'])}"
        
        return f"{base_url}?{query_string}"
    
    def _extract_total_results(self, html_content: str) -> int:
        """从页面HTML中提取总结果数"""
        # 匹配格式：<div class="search-hits__meta--total_hits">1,006 Results</div>
        pattern = r'search-hits__meta--total_hits[^>]*>[\s]*([\d,]+)\s*Results'
        match = re.search(pattern, html_content)
        if match:
            total_str = match.group(1).replace(',', '')
            try:
                return int(total_str)
            except:
                pass
        return 0
    
    def _build_page_url(self, base_url: str, page_num: int, first_page_maxresults: int = 60, subsequent_maxresults: int = 40) -> str:
        """
        构建分页URL
        
        根据翻页.txt的规律：
        - 第1页：offset=0, maxresults=60
        - 第2页及以后：offset=63, maxresults=40, page=页码-1
        """
        if page_num == 1:
            # 第一页保持原样
            return base_url
        else:
            # 第2页及以后：添加 offset=63, maxresults=20, page=页码-1
            parsed = urlparse(base_url)
            query_params = parse_qs(parsed.query)
            
            # 设置后续页的参数
            query_params['offset'] = ['63']
            query_params['maxresults'] = [str(subsequent_maxresults)]
            query_params['page'] = [str(page_num - 1)]  # page参数从0开始
            query_params['hide_duplicates'] = ['0']  # 后续页关闭hide_duplicates
            
            # 重新构建URL
            new_query = "&".join([f"{k}={quote(v[0])}" for k, v in query_params.items()])
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{new_query}"
    
    def _is_search_keyword(self, input_text: str) -> bool:
        """判断输入是搜索关键字还是URL"""
        # 如果包含空格且不是完整URL，认为是关键字
        if ' ' in input_text and not input_text.startswith('http'):
            return True
        # 如果不包含apps/news/results，认为是关键字
        if 'apps/news/results' not in input_text:
            return True
        return False
    
    def _extract_preview_from_html(self, html_content: str) -> List[Dict]:
        """从HTML中提取文章的docref和preview"""
        articles = []
        
        # 匹配文章块 - 使用更宽的范围：search-hits__hit__inner
        preview_pattern = r'<div class="search-hits__hit__inner"[^>]*>.*?preview-first-paragraph.*?</div>\s*</div>\s*</div>'
        article_matches = re.findall(preview_pattern, html_content, re.DOTALL)
        
        print(f"  [调试] 从HTML中找到 {len(article_matches)} 个包含preview的文章块")
        
        for idx, article_html in enumerate(article_matches):
            # 提取docref - 从href中提取
            doc_id = ''
            
            # 方法1: 从href中提取 docref=news/xxx
            docref_match = re.search(r'docref=(news/[^&"]+)', article_html)
            if docref_match:
                doc_id = docref_match.group(1)
            
            # 方法2: 如果方法1没有，尝试data-doc-id
            if not doc_id:
                docref_match = re.search(r'data-doc-id="([^"]+)"', article_html)
                if docref_match:
                    doc_id = 'news/' + docref_match.group(1)
            
            if not doc_id:
                print(f"  [调试] 文章{idx+1} 未能提取到docref")
                continue
            
            # 提取preview - 正确匹配<div class="preview-first-paragraph">到</div>之间的内容
            preview = ""
            preview_match = re.search(
                r'preview-first-paragraph[^>]*>(.*?)</div>',
                article_html, re.DOTALL
            )
            if preview_match:
                preview = preview_match.group(1).strip()
                # 清理HTML标签，获取纯文本
                preview = re.sub(r'<[^>]+>', '', preview)
                preview = preview.strip()[:200]
                print(f"  [调试] 文章{idx+1} docref={doc_id}, preview={preview[:30]}...")
            
            if doc_id:
                articles.append({
                    'docref': doc_id,
                    'preview': preview
                })
        
        print(f"  [调试] 提取到 {len(articles)} 个preview数据")
        return articles
    
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
    
    async def _extract_selected_articles_metadata(self, page: Page) -> List[Dict]:
        """
        从页面提取选中文章的元数据
        
        返回格式:
        [{"docref":"news/xxx","cache_type":"AWGLNB","size":xxx,"pbi":"xxx","title":"xxx","product":"AWGLNB"}, ...]
        
        这个格式是 nb-cache-doc/js/set API 所需的
        """
        print("  [提取] 提取选中文章的元数据...")
        
        try:
            # 从页面提取选中复选框的文章信息
            metadata = await page.evaluate("""() => {
                const selectedArticles = [];
                
                // 查找所有选中的文章复选框
                const checkboxes = document.querySelectorAll('article.search-hits__hit input[type="checkbox"]:checked');
                
                console.log('Found ' + checkboxes.length + ' checked checkboxes');
                
                checkboxes.forEach(checkbox => {
                    // 找到对应的文章元素
                    const article = checkbox.closest('article.search-hits__hit');
                    if (!article) return;
                    
                    // 打印article的dataset用于调试
                    console.log('Article dataset:', JSON.stringify(article.dataset));
                    
                    // 提取文章信息 - 从data属性提取
                    const docref = article.dataset.docId || '';
                    const pbi = article.dataset.pbi || article.dataset.pbI || '';
                    const cacheType = article.dataset.cacheType || article.dataset.cacheType || 'AWGLNB';
                    const product = article.dataset.product || 'AWGLNB';
                    const size = article.dataset.size || article.dataset.docSize || '0';
                    
                    // 方法2: 从href中提取docref
                    const link = article.querySelector('h3.search-hits__hit__title a');
                    const href = link ? link.href : '';
                    const docMatch = href.match(/doc=([^&]+)/);
                    const docIdFromHref = docMatch ? 'news/' + docMatch[1] : '';
                    
                    // 提取标题
                    const title = link ? link.textContent.trim() : '';
                    
                    // 使用从href中提取的docref（更可靠）
                    const finalDocref = docIdFromHref || docref;
                    
                    if (finalDocref) {
                        selectedArticles.push({
                            docref: finalDocref,
                            cache_type: cacheType,
                            size: parseInt(size) || 0,
                            pbi: pbi,
                            title: title,
                            product: product
                        });
                    }
                });
                
                // 如果没有选中任何文章，返回所有文章（未选中的）
                if (selectedArticles.length === 0) {
                    const allArticles = document.querySelectorAll('article.search-hits__hit');
                    console.log('No checked articles, trying all ' + allArticles.length + ' articles');
                    
                    allArticles.forEach(article => {
                        const link = article.querySelector('h3.search-hits__hit__title a');
                        const href = link ? link.href : '';
                        const docMatch = href.match(/doc=([^&]+)/);
                        const docIdFromHref = docMatch ? 'news/' + docMatch[1] : '';
                        const title = link ? link.textContent.trim() : '';
                        
                        // 从各种可能的data属性中提取
                        const pbi = article.dataset.pbi || article.dataset.pbI || 
                                   article.dataset.bpi || '';
                        const cacheType = article.dataset.cacheType || 'AWGLNB';
                        const product = article.dataset.product || 'AWGLNB';
                        const size = article.dataset.size || article.dataset.docSize || '0';
                        
                        if (docIdFromHref) {
                            selectedArticles.push({
                                docref: docIdFromHref,
                                cache_type: cacheType,
                                size: parseInt(size) || 0,
                                pbi: pbi,
                                title: title,
                                product: product
                            });
                        }
                    });
                }
                
                return selectedArticles;
            }""")
            
            print(f"  [提取] 找到 {len(metadata)} 篇选中文章")
            
            # 打印前几篇用于调试
            for i, art in enumerate(metadata[:3]):
                print(f"    [{i+1}] title={art.get('title', 'N/A')[:30]}...")
                print(f"        docref={art.get('docref', 'N/A')}, size={art.get('size', 0)}, pbi={art.get('pbi', 'N/A')[:20]}...")
            
            return metadata
            
        except Exception as e:
            print(f"  [错误] 提取选中文章元数据失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    async def _capture_selected_articles_payload(self, page: Page) -> Optional[str]:
        """
        通过监听网络请求捕获实际发送的payload
        
        在选中文章后，网页会发送一个POST请求到 nb-cache-doc/js/set
        这个方法捕获该请求的body，即实际使用的payload
        """
        print("  [捕获] 监听网络请求以捕获实际payload...")
        
        captured_payloads = []
        
        async def handle_request(request):
            # 监听 nb-cache-doc/js/set 或 nb-multidocs/get 请求
            url = request.url
            if "nb-cache-doc" in url or "nb-multidocs" in url:
                try:
                    # 获取请求的post数据
                    post_data = request.post_data
                    if post_data:
                        if isinstance(post_data, bytes):
                            post_data = post_data.decode('utf-8')
                        
                        # 只捕获包含docs=的请求（这是设置选中文章 的请求）
                        if 'docs=' in post_data:
                            captured_payloads.append({
                                'url': url,
                                'post_data': post_data,
                                'timestamp': time.time(),
                                'length': len(post_data)
                            })
                            print(f"  [捕获] 捕获到请求: {request.method} {url.split('/')[-1]}")
                            print(f"  [捕获] Payload长度: {len(post_data)} 字符")
                            print(f"  [捕获] Payload预览: {post_data[:200]}...")
                except Exception as e:
                    pass  # 静默处理，避免过多输出
        
        # 设置监听器
        page.on("request", handle_request)
        
        # 等待一段时间，收集所有请求
        print("  [等待] 等待捕获请求...")
        for i in range(4):
            await asyncio.sleep(1)
            if captured_payloads:
                print(f"  [信息] 已捕获 {len(captured_payloads)} 个相关请求")
                # 打印每个捕获的payload长度
                for idx, p in enumerate(captured_payloads):
                    print(f"    [{idx+1}] 长度: {p['length']} 字符")
        
        if captured_payloads:
            # 使用最后一个包含docs=的请求（通常是最新的）
            # 因为选中操作会触发多次请求
            last_payload = captured_payloads[-1]['post_data']
            payload_length = len(last_payload)
            print(f"  [成功] 使用最后一个请求的payload ({payload_length} 字符)")
            
            # 检查payload是否可能被截断
            if payload_length > 5000:
                print(f"  [警告] Payload较长({payload_length}字符)，检查完整性...")
                # 检查是否有未闭合的括号
                bracket_count = last_payload.count('[') - last_payload.count(']')
                brace_count = last_payload.count('{') - last_payload.count('}')
                print(f"  [检查] 括号平衡: [ {bracket_count}, {{ {brace_count}")
                if bracket_count != 0 or brace_count != 0:
                    print(f"  [警告] Payload可能被截断！")
            
            return last_payload
        else:
            print(f"  [警告] 未捕获到包含docs=的payload")
            return None
    
    def _parse_captured_payload(self, payload_str: str) -> Optional[List[Dict]]:
        """
        解析捕获的payload字符串，提取文章元数据列表
        
        返回格式:
        [{"docref":"news/xxx","cache_type":"AWGLNB","size":xxx,"pbi":"xxx","title":"xxx","product":"AWGLNB"}, ...]
        """
        try:
            # payload可能是URL编码的，可能需要多次解码
            decoded = payload_str
            
            # 尝试多次解码，直到不再是URL编码格式
            max_iterations = 3
            for i in range(max_iterations):
                try:
                    # 检查是否包含URL编码（%XX格式）
                    if '%' in decoded:
                        decoded = unquote(decoded)
                        print(f"  [解码] 第{i+1}次解码后: {decoded[:200]}...")
                    else:
                        break
                except Exception:
                    break
            
            # 打印完整的解码后的payload用于调试
            print(f"  [调试] 完整payload: {decoded[:500]}...")
            print(f"  [调试] Payload总长度: {len(decoded)} 字符")
            
            # 提取 docs= 后面的JSON数组
            if 'docs=' in decoded:
                json_part = decoded.split('docs=')[1]
                
                # 可能还包含其他参数，用 & 分隔
                # 但要注意JSON内部可能有 &amp; (HTML实体) 解码后的 &
                # 需要智能找到真正的参数分隔位置
                if '&' in json_part:
                    # 尝试找到JSON数组的结束位置（最后一个]）
                    # 通过计算括号的平衡来确定
                    last_bracket = json_part.rfind(']')
                    if last_bracket > 0:
                        # 检查后面是否还有其他参数
                        remaining = json_part[last_bracket+1:]
                        if remaining and '&' in remaining:
                            # 确实有其他参数，只取到]为止
                            json_part = json_part[:last_bracket+1]
                            print(f"  [调试] 智能截断到最后一个]，位置: {last_bracket}")
                        else:
                            # 后面没有&，说明没有其他参数了
                            json_part = json_part[:last_bracket+1]
                            print(f"  [调试] 无后续参数，使用完整JSON，位置: {last_bracket}")
                    else:
                        # 没有找到]，用原来的方式
                        print(f"  [调试] 未找到]，使用原方式")
                        json_part = json_part.split('&')[0]
                
                # 清理可能的空白字符
                json_part = json_part.strip()
                
                print(f"  [调试] JSON部分长度: {len(json_part)} 字符")
                print(f"  [调试] JSON部分前200字符: {json_part[:200]}...")
                
                # 检查JSON是否被截断 - 更详细的检查
                bracket_diff = json_part.count('[') - json_part.count(']')
                brace_diff = json_part.count('{') - json_part.count('}')
                print(f"  [调试] 括号平衡: [ {bracket_diff}, {{ {brace_diff}")
                
                if bracket_diff > 0 or brace_diff > 0:
                    print(f"  [警告] JSON数组可能未正确关闭，尝试修复...")
                    # 尝试补全缺失的 ]
                    if bracket_diff > 0:
                        json_part = json_part + ']' * bracket_diff
                    if brace_diff > 0:
                        json_part = json_part + '}' * brace_diff
                
                # 解析JSON
                try:
                    articles = json.loads(json_part)
                    print(f"  [解析] 从payload中提取到 {len(articles)} 篇文章")
                    
                    # 打印文章标题用于调试
                    for i, art in enumerate(articles[:5]):
                        print(f"    [{i+1}] {art.get('title', 'N/A')[:40]}")
                        print(f"        docref: {art.get('docref', 'N/A')}")
                    
                    return articles
                except json.JSONDecodeError as json_err:
                    print(f"  [解析] JSON解析失败: {json_err}")
                    # 尝试更详细的错误定位
                    print(f"  [调试] 错误位置: char {json_err.pos}, line {json_err.lineno}, col {json_err.colno}")
                    # 打印错误位置前后的字符
                    if json_err.pos and json_err.pos < len(json_part):
                        start = max(0, json_err.pos - 50)
                        end = min(len(json_part), json_err.pos + 50)
                        print(f"  [调试] 错误位置附近: ...{json_part[start:end]}...")
                    
                    # 如果JSON被截断，尝试只解析已有的部分
                    if json_err.pos:
                        truncated_json = json_part[:json_err.pos]
                        print(f"  [备选] 尝试解析截断的JSON部分...")
                        try:
                            # 尝试找到最后一个完整的对象
                            # 通过找到最后一个 } 来判断
                            last_brace = truncated_json.rfind('}')
                            if last_brace > 0:
                                truncated_json = truncated_json[:last_brace+1]
                                truncated_json = '[' + truncated_json + ']'
                                articles = json.loads(truncated_json)
                                print(f"  [解析] 从截断payload中提取到 {len(articles)} 篇文章")
                                return articles
                        except:
                            pass
                    raise
            
            elif decoded.startswith('['):
                # 尝试直接解析（没有docs=前缀）
                articles = json.loads(decoded)
                return articles
            else:
                print(f"  [警告] payload中未找到docs=参数")
                print(f"  [调试] payload内容: {decoded[:500]}...")
                return None
                
        except Exception as e:
            print(f"  [解析] 解析payload失败: {e}")
            # 打印原始payload用于调试
            print(f"  [调试] 原始payload: {payload_str[:300]}...")
            print(f"  [调试] 原始payload长度: {len(payload_str)} 字符")
            return None
    
    async def _save_article_metadata_to_json(self, article_metadata: List[Dict], keyword: str) -> Path:
        """
        将文章元数据保存到JSON文件
        
        Args:
            article_metadata: 文章元数据列表
            keyword: 搜索关键字
            
        Returns:
            保存的文件路径
        """
        # 筛选处理：只保留 docref 以 "news/" 开头的记录
        filtered_metadata = [
            art for art in article_metadata 
            if art.get('docref', '').startswith('news/')
        ]
        
        if len(filtered_metadata) < len(article_metadata):
            print(f"  [筛选] 过滤掉 {len(article_metadata) - len(filtered_metadata)} 条非 news/ 开头的记录")
            print(f"  [筛选] 保留 {len(filtered_metadata)} 条记录")
        
        # 如果筛选后没有有效记录，发出警告
        if not filtered_metadata:
            print(f"  [警告] 筛选后没有有效记录，请检查 docref 格式")
            filtered_metadata = article_metadata  # 保留原始数据以便调试
        
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_keyword = re.sub(r'[^\w\s-]', '', keyword).replace(' ', '_')[:30]
        filename = f"article_{safe_keyword}_{timestamp}.json"
        filepath = self.output_dir / filename
        
        # 准备保存的数据
        save_data = {
            "search_keyword": keyword,
            "extracted_at": datetime.now().isoformat(),
            "total_articles": len(filtered_metadata),
            "original_count": len(article_metadata),  # 记录原始数量
            "articles": filtered_metadata
        }
        
        # 保存到JSON文件
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
        
        print(f"  [保存] 元数据已保存到: {filepath}")
        return filepath
    
    def _init_llm_client(self, api_key: str = None, model: str = None):
        """
        初始化 LLM 客户端
        
        Args:
            api_key: API密钥，默认从环境变量读取
            model: 模型名称
            
        Returns:
            openai客户端，如果失败返回None
        """
        if not OPENAI_AVAILABLE:
            print("[错误] openai 包未安装")
            return None
        
        # 获取 API Key
        if not api_key:
            api_key = os.getenv("NVIDIA_API_KEY") or os.getenv("OPENAI_API_KEY")
        
        if not api_key:
            print("[错误] 未设置 API Key，请设置 NVIDIA_API_KEY 或 OPENAI_API_KEY 环境变量")
            return None
        
        # 检测 provider
        if api_key.startswith("nvapi-"):
            provider = "nvidia"
            base_url = "https://integrate.api.nvidia.com/v1"
            default_model = "z-ai/glm4.7"  # 推荐中文理解好的模型
        else:
            provider = "openai"
            base_url = None
            default_model = "gpt-3.5-turbo"
        
        # 优先级：命令行参数 > 环境变量 > 默认值
        if not model:
            # 尝试从 LLM_MODEL 环境变量读取
            model = os.getenv("LLM_MODEL")
        
        if not model:
            model = default_model
        
        print(f"[LLM] Provider: {provider}")
        print(f"[LLM] Model: {model}")
        
        try:
            client = openai.OpenAI(
                api_key=api_key,
                base_url=base_url
            )
            return client, model
        except Exception as e:
            print(f"[错误] 初始化 LLM 客户端失败: {e}")
            return None
    
    def _build_relevance_prompt(self, keyword: str, articles: List[Dict]) -> str:
        """
        构建相关性判断的 prompt
        
        Args:
            keyword: 搜索关键字
            articles: 文章列表，包含 title 和 preview
            
        Returns:
            prompt 字符串
        """
        # 解码URL编码的标题和预览
        decoded_articles = []
        for art in articles:
            title = art.get('title', '')
            preview = art.get('preview', '')[:200] if art.get('preview') else ''  # 限制preview长度
            
            # URL解码
            title = title.replace('+', ' ')
            try:
                title = unquote(title)
            except:
                pass
            
            if preview:
                preview = preview.replace('+', ' ')
                try:
                    preview = unquote(preview)
                except:
                    pass
            
            decoded_articles.append({
                'title': title[:100],  # 限制标题长度
                'preview': preview[:200] if preview else ''
            })
        
        # 构建prompt
        articles_text = "\n".join([
            f"{i+1}. 标题: {a['title'][:80]}\n   预览: {a['preview'][:150] if a['preview'] else '(无预览)'}"
            for i, a in enumerate(decoded_articles)
        ])
        
        prompt = f"""你是一个文章相关性判断专家。请判断以下文章是否与搜索关键字"{keyword}"相关。

判断标准：
- 直接提到关键字或关键字的变体（如公司名，品牌名、缩写）
- 讨论与关键字相关的事件、产品、服务
- 与关键字所在行业或领域直接相关
- 仅仅是通用新闻但没有实质性提到关键字，不算相关

文章列表：
{articles_text}

请按以下JSON格式返回结果：
{{
    "results": [
        {{"index": 1, "relevant": true/false, "reason": "简短原因"}},
        ...
    ]
}}

只返回JSON，不要有其他内容。"""
        
        return prompt
    
    async def _filter_articles_by_llm(self, 
                                       json_file: Path, 
                                       api_key: str = None, 
                                       model: str = None,
                                       threshold: float = 0.5,
                                       batch_size: int = 10) -> Optional[Path]:
        """
        使用 LLM 筛选相关文章
        
        Args:
            json_file: 输入的 JSON 文件路径
            api_key: API 密钥
            model: 模型名称
            threshold: 相关性阈值 (0-1)
            batch_size: 每批次处理的文章数
            
        Returns:
            筛选后的 JSON 文件路径，失败返回 None
        """
        print("\n" + "=" * 60)
        print("[LLM 智能筛选]")
        print("=" * 60)
        
        if not OPENAI_AVAILABLE:
            print("[错误] openai 包未安装，无法使用 LLM 筛选")
            return None
        
        # 加载 JSON 文件
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"[错误] 加载 JSON 文件失败: {e}")
            return None
        
        keyword = data.get('search_keyword', '')
        articles = data.get('articles', [])
        
        if not articles:
            print("[警告] 文章列表为空")
            return None
        
        print(f"[LLM] 搜索关键字: {keyword}")
        print(f"[LLM] 文章总数: {len(articles)}")
        print(f"[LLM] 相关性阈值: {threshold}")
        
        # 初始化 LLM 客户端
        llm_result = self._init_llm_client(api_key, model)
        if not llm_result:
            return None
        
        client, model = llm_result
        
        # 提取所有标题
        titles = [art.get('title', '') for art in articles]
        
        # 批量处理
        relevant_articles = []
        total_batches = (len(articles) + batch_size - 1) // batch_size
        
        print(f"[LLM] 开始筛选，共 {total_batches} 批次...")
        
        for batch_idx in range(total_batches):
            start_idx = batch_idx * batch_size
            end_idx = min(start_idx + batch_size, len(articles))
            batch_titles = titles[start_idx:end_idx]
            batch_articles = articles[start_idx:end_idx]
            
            print(f"[LLM] 处理批次 {batch_idx + 1}/{total_batches} ({start_idx+1}-{end_idx})...")
            
            # 构建 prompt
            prompt = self._build_relevance_prompt(keyword, batch_titles)
            
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "你是一个文章相关性判断专家，擅长分析文章标题与搜索主题的相关性。"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    max_tokens=2000
                )
                
                result_text = response.choices[0].message.content.strip()
                
                # 解析 JSON 结果
                try:
                    # 尝试提取 JSON
                    if '```json' in result_text:
                        result_text = result_text.split('```json')[1].split('```')[0]
                    elif '```' in result_text:
                        result_text = result_text.split('```')[1].split('```')[0]
                    
                    result_json = json.loads(result_text)
                    results = result_json.get('results', [])
                    
                    # 处理结果
                    for i, result in enumerate(results):
                        if result.get('relevant', False):
                            relevant_articles.append(batch_articles[i])
                    
                    # 打印批次结果
                    relevant_count = sum(1 for r in results if r.get('relevant', False))
                    print(f"    批次 {batch_idx + 1}: {relevant_count}/{len(batch_articles)} 相关文章")
                    
                except json.JSONDecodeError as json_err:
                    print(f"    [警告] 解析 LLM 响应失败: {json_err}")
                    # 如果解析失败，默认保留所有文章
                    relevant_articles.extend(batch_articles)
                    
            except Exception as api_err:
                print(f"    [错误] API 调用失败: {api_err}")
                # API 失败时默认保留所有文章
                relevant_articles.extend(batch_articles)
            
            # 避免过快请求
            if batch_idx < total_batches - 1:
                await asyncio.sleep(1)
        
        # 统计结果
        filtered_count = len(relevant_articles)
        removed_count = len(articles) - filtered_count
        
        print(f"\n[LLM 筛选结果]")
        print(f"  原始文章: {len(articles)}")
        print(f"  相关文章: {filtered_count}")
        print(f"  过滤掉: {removed_count}")
        print(f"  筛选比例: {filtered_count/len(articles)*100:.1f}%")
        
        if not relevant_articles:
            print("[警告] 没有相关文章被保留")
            return None
        
        # 保存筛选后的结果
        output_data = {
            "search_keyword": keyword,
            "extracted_at": data.get('extracted_at', datetime.now().isoformat()),
            "llm_filtered_at": datetime.now().isoformat(),
            "total_articles": filtered_count,
            "original_count": len(articles),
            "filter_threshold": threshold,
            "filter_model": model,
            "articles": relevant_articles
        }
        
        # 生成输出文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_keyword = re.sub(r'[^\w\s-]', '', keyword).replace(' ', '_')[:30]
        output_filename = f"article_{safe_keyword}_filtered_{timestamp}.json"
        output_filepath = self.output_dir / output_filename
        
        with open(output_filepath, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        print(f"\n[保存] 筛选后的结果已保存到: {output_filepath}")
        return output_filepath
    
    async def _filter_single_page_with_llm(self,
                                            article_metadata: List[Dict],
                                            keyword: str,
                                            llm_client,
                                            llm_model: str,
                                            threshold: float = 0.5) -> List[Dict]:
        """
        对单页文章进行 LLM 筛选
        
        Args:
            article_metadata: 单页文章元数据列表
            keyword: 搜索关键字
            llm_client: 已初始化的 LLM 客户端
            llm_model: 模型名称
            threshold: 相关性阈值
            
        Returns:
            筛选后的文章列表
        """
        if not article_metadata:
            return []
        
        # 解码标题用于显示
        decoded_titles = []
        for title in article_metadata:
            t = title.get('title', '')
            t = t.replace('+', ' ')
            try:
                t = unquote(t)
            except:
                pass
            decoded_titles.append(t[:60] + "..." if len(t) > 60 else t)
        
        print(f"    [LLM] 待筛选文章标题:")
        for i, t in enumerate(decoded_titles[:5]):  # 只显示前5个
            print(f"      [{i+1}] {t}")
        if len(decoded_titles) > 5:
            print(f"      ... 还有 {len(decoded_titles) - 5} 篇")
        
        # 构建 prompt - 传入完整文章列表
        prompt = self._build_relevance_prompt(keyword, article_metadata)
        
        print(f"    [LLM] 发送请求到模型: {llm_model}...")
        
        try:
            start_time = time.time()
            response = llm_client.chat.completions.create(
                model=llm_model,
                messages=[
                    {"role": "system", "content": "你是一个文章相关性判断专家，擅长分析文章标题与搜索主题的相关性。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=2000
            )
            elapsed = time.time() - start_time
            
            result_text = response.choices[0].message.content.strip()
            print(f"    [LLM] 模型响应时间: {elapsed:.2f}秒")
            print(f"    [LLM] 响应长度: {len(result_text)} 字符")
            
            # 解析 JSON 结果
            try:
                # 尝试提取 JSON
                if '```json' in result_text:
                    result_text = result_text.split('```json')[1].split('```')[0]
                elif '```' in result_text:
                    result_text = result_text.split('```')[1].split('```')[0]
                
                result_json = json.loads(result_text)
                results = result_json.get('results', [])
                
                # 显示每个结果的判断
                print(f"    [LLM] 模型判断结果:")
                relevant_articles = []
                for i, result in enumerate(results):
                    if i < len(article_metadata):
                        title_short = decoded_titles[i][:40] if i < len(decoded_titles) else "Unknown"
                        is_relevant = result.get('relevant', False)
                        reason = result.get('reason', '')[:30]
                        status = "✓ 相关" if is_relevant else "✗ 不相关"
                        print(f"      [{i+1}] {status} - {title_short}")
                        if is_relevant:
                            relevant_articles.append(article_metadata[i])
                
                return relevant_articles
                
            except json.JSONDecodeError as e:
                # 解析失败时返回所有文章
                print(f"    [警告] 解析LLM响应失败: {e}")
                print(f"    [警告] 响应内容: {result_text[:200]}...")
                return article_metadata
                
        except Exception as e:
            print(f"    [错误] LLM 调用失败: {e}")
            # API 失败时返回所有文章
            return article_metadata
    
    async def _prompt_user_to_select_articles(self, article_metadata: List[Dict], max_download: int = 20) -> List[Dict]:
        """
        让用户选择要下载的文章
        
        Args:
            article_metadata: 文章元数据列表
            max_download: 建议的最大下载数量（服务器限制）
            
        Returns:
            用户选择的文章元数据列表
        """
        print("\n" + "=" * 60)
        print("[文章选择]")
        print("=" * 60)
        
        total = len(article_metadata)
        print(f"\n共提取到 {total} 篇文章。")
        print(f"\n⚠️  警告: 建议单次下载不超过 {max_download} 篇，防止服务器限制。")
        
        # 显示文章列表（带编号）
        print("\n文章列表:")
        print("-" * 60)
        
        for i, art in enumerate(article_metadata, 1):
            title = art.get('title', 'N/A')[:60]
            size = art.get('size', 0)
            docref = art.get('docref', 'N/A')
            print(f"  {i:3}. [{size:>6} bytes] {title}")
        
        print("-" * 60)
        
        # 让用户输入选择
        print(f"\n请选择要下载的文章:")
        print("  - 输入数字编号 (例如: 1,5,10)")
        print("  - 输入范围 (例如: 1-10)")
        print("  - 输入 'all' 下载全部 (⚠️ 可能触发服务器限制)")
        print("  - 输入 'first N' 下载前N篇 (例如: first 10)")
        print("  - 输入 'last N' 下载后N篇")
        print("  - 输入 'cancel' 取消下载")
        
        while True:
            user_input = input("\n请输入选择: ").strip().lower()
            
            if user_input == 'cancel':
                print("  已取消下载")
                return []
            
            if user_input == 'all':
                selected = article_metadata
                print(f"\n  ⚠️  选择了全部 {len(selected)} 篇文章")
                if len(selected) > max_download:
                    confirm = input(f"  超过建议数量 ({max_download})，是否继续? (y/n): ").strip().lower()
                    if confirm != 'y':
                        continue
                return selected
            
            # 处理 "first N" 或 "last N"
            if user_input.startswith('first '):
                try:
                    n = int(user_input.split()[1])
                    selected = article_metadata[:n]
                    print(f"\n  已选择前 {len(selected)} 篇文章")
                    return selected
                except:
                    print("  输入格式错误")
                    continue
            
            if user_input.startswith('last '):
                try:
                    n = int(user_input.split()[1])
                    selected = article_metadata[-n:]
                    print(f"\n  已选择后 {len(selected)} 篇文章")
                    return selected
                except:
                    print("  输入格式错误")
                    continue
            
            # 处理范围 (例如: 1-10)
            if '-' in user_input:
                try:
                    parts = user_input.split('-')
                    start = int(parts[0].strip())
                    end = int(parts[1].strip())
                    if 1 <= start <= end <= total:
                        selected = article_metadata[start-1:end]
                        print(f"\n  已选择第 {start} 到 {end} 篇，共 {len(selected)} 篇")
                        return selected
                    else:
                        print(f"  范围无效 (1-{total})")
                except:
                    print("  输入格式错误")
                    continue
            
            # 处理单个或多个数字 (例如: 1,5,10)
            if ',' in user_input or user_input.replace(',', '').replace(' ', '').isdigit():
                try:
                    # 解析输入
                    nums = []
                    for part in user_input.replace(',', ' ').split():
                        if part.isdigit():
                            nums.append(int(part))
                    
                    if nums:
                        # 验证范围
                        valid = all(1 <= n <= total for n in nums)
                        if valid:
                            selected = [article_metadata[n-1] for n in nums]
                            print(f"\n  已选择 {len(selected)} 篇文章: {nums}")
                            return selected
                        else:
                            print(f"  数字范围无效 (1-{total})")
                    else:
                        print("  输入格式错误")
                except:
                    print("  输入格式错误")
                    continue
            
            print("  输入无效，请重试")
    
    def _load_article_metadata_from_json(self, json_path: Path) -> Optional[List[Dict]]:
        """
        从JSON文件加载文章元数据
        
        Args:
            json_path: JSON文件路径
            
        Returns:
            文章元数据列表，如果失败返回None
        """
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            articles = data.get('articles', [])
            print(f"  [加载] 从 {json_path.name} 加载了 {len(articles)} 篇文章元数据")
            return articles
            
        except Exception as e:
            print(f"  [错误] 加载JSON失败: {e}")
            return None
    
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
        # maxresults=20 可以一次获取最多20篇文章的完整内容，不能设置得太大，防止限流
        payload = {
            "page": str(page_num),
            "load_pager": "true",
            "p": p_param,
            "action": "download",
            "label": "Multidocs Display pane",
            "maxresults": "20",  # 改为20，系统的预设值。这个数字放的过大可能触发服务器限制
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
                            
                            # 强制触发网络请求：无论是否选中，都要点击
                            # 如果已选中，先取消再选中；如果未选中，直接选中
                            if is_checked:
                                print(f"    [强制] 复选框已选中，先取消再选中以触发网络请求...")
                                # 取消选中
                                try:
                                    await select_all_elem.click(force=True)
                                    print(f"    [取消] 已取消选中")
                                    await asyncio.sleep(0.5)
                                except Exception as e:
                                    print(f"    [警告] 取消失败: {e}")
                            
                            print(f"    准备点击复选框...")
                            
                            # 方法1: 使用鼠标模拟点击（更真实）
                            click_success = False
                            try:
                                box = await select_all_elem.bounding_box()
                                if box:
                                    # 计算元素中心点
                                    x = box['x'] + box['width'] / 2
                                    y = box['y'] + box['height'] / 2
                                    print(f"    使用鼠标点击坐标: ({x}, {y})")
                                    await page.mouse.click(x, y)
                                    print(f"    [成功] 使用 mouse.click() 点击")
                                    click_success = True
                            except Exception as mouse_err:
                                print(f"    [警告] 鼠标点击失败: {mouse_err}")
                            
                            # 方法2: 直接点击
                            if not click_success:
                                try:
                                    await select_all_elem.click(force=True)
                                    print(f"    [成功] 使用 click(force=True) 点击")
                                    click_success = True
                                except Exception as click_err:
                                    print(f"    [警告] 直接点击失败: {click_err}")
                            
                            # 方法3: JavaScript点击
                            if not click_success:
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
                                    click_success = True
                                except Exception as js_err:
                                    print(f"    [警告] JavaScript点击也失败: {js_err}")
                            
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
            # 使用_build_download_payload方法正确构建payload，包含article_ids
            payload = self._build_download_payload(
                page_num=1,
                article_ids=article_ids,
                p_param=p_param
            )
            
            # 将payload转换为URL编码的form data字符串
            form_parts = []
            for key, value in payload.items():
                if isinstance(value, str):
                    form_parts.append(f"{key}={quote(value)}")
                else:
                    form_parts.append(f"{key}={value}")
            form_data_str = "&".join(form_parts)
            
            print(f"  [请求] POST {self.api_endpoint}")
            print(f"  [文章ID数量] {len(article_ids) if article_ids else 0}")
            print(f"  [参数] {form_data_str[:150]}...")
            
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
    
    async def _call_download_api_with_payload(self, page: Page, captured_payload: str, p_param: str = "AWGLNB") -> Optional[Dict]:
        """
        使用捕获的payload直接调用下载API
        
        这是最可靠的方式，因为使用的是浏览器实际发送的payload
        """
        print("\n[使用捕获的Payload调用API]")
        print("-" * 40)
        
        try:
            # 构建完整的请求payload
            # 捕获的payload可能只是docs=部分，需要补充其他参数
            full_payload = captured_payload
            
            # 检查是否需要添加额外参数
            if 'instance_id' not in captured_payload:
                # 可能需要从页面获取instance_id
                instance_id = await page.evaluate("""() => {
                    // 尝试从页面获取instance_id
                    const el = document.querySelector('[data-instance-id]');
                    if (el) return el.dataset.instanceId;
                    // 或者从URL参数获取
                    const urlParams = new URLSearchParams(window.location.search);
                    return urlParams.get('instance_id') || '';
                }""")
                
                if instance_id:
                    full_payload = f"{captured_payload}&instance_id={instance_id}"
            
            print(f"  [请求] POST {self.api_endpoint}")
            print(f"  [Payload] {full_payload[:200]}...")
            
            # 使用Playwright发送请求
            try:
                api_response = await page.context.request.post(
                    self.api_endpoint,
                    data=full_payload,
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
                print(f"  [警告] API请求失败: {api_err}")
                # 回退到fetch方式
                response = await page.evaluate("""async ({url, payload}) => {
                    try {
                        const response = await fetch(url, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/x-www-form-urlencoded',
                                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                                'X-Requested-With': 'XMLHttpRequest'
                            },
                            body: payload,
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
                }""", {"url": self.api_endpoint, "payload": full_payload})
            
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
            print(f"  [错误] 调用API失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def _call_download_api_with_articles(self, page: Page, article_metadata: List[Dict], p_param: str = "AWGLNB") -> Optional[Dict]:
        """
        使用文章元数据构建payload并调用下载API
        
        article_metadata 格式:
        [{"docref":"news/xxx","cache_type":"AWGLNB","size":xxx,"pbi":"xxx","title":"xxx","product":"AWGLNB"}, ...]
        """
        print("\n[使用文章元数据调用API]")
        print("-" * 40)
        
        try:
            # 从页面获取必要的参数
            instance_id = await page.evaluate("""() => {
                // 尝试从各种来源获取instance_id
                const urlParams = new URLSearchParams(window.location.search);
                return urlParams.get('instance_id') || 
                       urlParams.get('i') || 
                       document.querySelector('[data-instance-id]')?.dataset?.instanceId ||
                       '';
            }""")
            
            # 构建docs JSON数组
            docs_json = json.dumps(article_metadata[:100])  # 最多100篇
            
            # 构建完整的payload
            # 根据实际观察到的格式
            form_data_parts = [
                f"docs={quote(docs_json)}",
                f"p={p_param}",
                f"instance_id={instance_id}" if instance_id else "",
                "action=download",
                "format=html",
                "load_pager=false"
            ]
            
            # 过滤空值
            form_data_parts = [p for p in form_data_parts if p]
            form_data_str = "&".join(form_data_parts)
            
            print(f"  [请求] POST {self.api_endpoint}")
            print(f"  [文章数] {len(article_metadata)}")
            print(f"  [Payload] {form_data_str[:200]}...")
            
            # 发送请求
            try:
                api_response = await page.context.request.post(
                    self.api_endpoint,
                    data=form_data_str,
                    headers={
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'X-Requested-With': 'XMLHttpRequest',
                        'Referer': page.url,
                        'Cache-Control': 'no-cache',
                        'Pragma': 'no-cache'
                    }
                )
                
                response_body = await api_response.text()
                response = {
                    "status": api_response.status,
                    "body": response_body,
                    "url": api_response.url
                }
            except Exception as api_err:
                print(f"  [警告] API请求失败: {api_err}")
                # 回退到fetch
                response = await page.evaluate("""async ({url, payload}) => {
                    try {
                        const response = await fetch(url, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/x-www-form-urlencoded',
                                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                                'X-Requested-With': 'XMLHttpRequest',
                                'Cache-Control': 'no-cache'
                            },
                            body: payload,
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
                }""", {"url": self.api_endpoint, "payload": form_data_str})
            
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
            print(f"  [错误] 调用API失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def remove_selection(self, page: Page, p_param: str = "AWGLNB") -> bool:
        """
        清除当前的文章选择
        
        调用 nb-cache-doc/js/remove API 来清除所有已选择的文章
        """
        print("\n[清除选择]")
        print("-" * 40)
        
        remove_url = "https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/nb-cache-doc/js/remove"
        
        # 用户确认的payload格式
        payload = f"docrefs=ALL&p={p_param}"
        
        print(f"  [请求] POST nb-cache-doc/js/remove")
        print(f"  [Payload] {payload}")
        
        try:
            # 使用Playwright发送请求
            api_response = await page.context.request.post(
                remove_url,
                data=payload,
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Accept': 'application/json, text/javascript, */*; q=0.01',
                    'X-Requested-With': 'XMLHttpRequest',
                    'Referer': page.url
                }
            )
            
            response_body = await api_response.text()
            
            if api_response.status == 200:
                print(f"  [成功] 清除选择成功")
                return True
            else:
                print(f"  [警告] 清除选择失败 (状态: {api_response.status})")
                print(f"  [调试] 响应: {response_body[:200]}...")
                return False
                
        except Exception as e:
            print(f"  [错误] 清除选择请求失败: {e}")
            return False
    
    async def fetch_articles_via_api(self, 
                                     page: Page, 
                                     base_url: str,
                                     page_num: int = 1) -> List[ArticleInfo]:
        """
        通过API获取文章列表
        
        流程：
        1. 选中所有文章
        2. 捕获实际发送的payload（从网络请求）
        3. 如果捕获失败，从页面直接构建payload
        4. 使用payload调用下载API
        """
        print(f"\n[第 {page_num} 页] 获取文章列表")
        print("-" * 40)
        print(f"  [调试] 当前URL: {page.url[:100]}...")
        
        articles = []
        p_param = "AWGLNB"  # 默认值
        
        try:
            # 获取页面HTML以提取文章ID
            html_content = await page.content()
            
            article_ids = self._extract_article_ids_from_page(html_content)
            
            print(f"  [扫描] 从页面提取到 {len(article_ids)} 个文章ID")
            
            # 从当前URL提取参数
            parsed_url = urlparse(page.url)
            query_params = parse_qs(parsed_url.query)
            p_param = query_params.get('p', ['AWGLNB'])[0]
            
            # 步骤1: 选中所有文章
            print(f"  [步骤1] 选中所有文章...")
            select_success = await self.select_all_articles(page)
            if select_success:
                print(f"  [成功] 文章已选中")
            else:
                print(f"  [警告] 选择文章可能未成功，继续尝试...")
            
            # 等待一下确保选中状态生效
            await asyncio.sleep(1)
            
            # 步骤2: 尝试捕获实际的网络请求payload
            print(f"  [步骤2] 捕获实际payload...")
            captured_payload = await self._capture_selected_articles_payload(page)
            
            # 用于存储文章元数据
            article_metadata = None
            
            if captured_payload:
                # 解析捕获的payload获取文章元数据
                article_metadata = self._parse_captured_payload(captured_payload)
            
            # 如果没有捕获到payload，或者需要强制刷新，从页面直接构建
            if not article_metadata:
                print(f"  [备选] 从页面直接提取文章元数据...")
                article_metadata = await self._extract_selected_articles_metadata(page)
            
            if article_metadata and len(article_metadata) > 0:
                print(f"  [成功] 获取到 {len(article_metadata)} 篇文章元数据")
                
                # 使用文章元数据构建payload并调用API
                print(f"  [步骤3] 构建payload并调用下载API...")
                response_data = await self._call_download_api_with_articles(page, article_metadata, p_param)
                
                if response_data and response_data.get('body'):
                    body = response_data['body']
                    print(f"  [调试] API响应长度: {len(body)} bytes")
                    
                    # 检查是否是PDF
                    if body.startswith('%PDF'):
                        print("  [警告] API返回PDF")
                        articles = await self._parse_articles_from_page(page, page_num)
                    else:
                        articles = self._parse_api_response(body, page_num)
                        print(f"  [成功] 从API响应解析到 {len(articles)} 篇文章")
                
                # 清除选择，避免累积导致payload过长
                await self.remove_selection(page, p_param)
                
                return articles
            
            # 如果完全没有获取到文章元数据，回退到原有方法
            print(f"  [回退] 未能获取文章元数据，使用原有方法...")
            print(f"  [步骤3] 调用API获取文章数据...")
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
            
            # 清除选择，避免累积导致payload过长
            await self.remove_selection(page, p_param)
            
            return articles
            
        except Exception as e:
            print(f"  [错误] API请求失败: {e}")
            import traceback
            traceback.print_exc()
            # 失败时也尝试清除选择
            try:
                await self.remove_selection(page, p_param)
            except:
                await self.remove_selection(page, "AWGLNB")  # 使用默认值
            # 失败时回退到页面解析
            return await self._parse_articles_from_page(page, page_num)
    
    async def fetch_page_metadata_only(self, page: Page, page_num: int = 1) -> Optional[List[Dict]]:
        """
        只获取页面元数据，不下载文章内容
        
        新流程步骤2：选中→获取元数据→返回（翻页由调用者处理）
        
        Returns:
            文章元数据列表，如果失败返回None
        """
        print(f"\n[第 {page_num} 页] 获取元数据...")
        print("-" * 40)
        
        article_metadata = None
        
        # 设置网络请求监听器（在选中之前）
        captured_payloads = []
        
        async def handle_request(request):
            url = request.url
            if "nb-cache-doc" in url:
                try:
                    post_data = request.post_data
                    if post_data:
                        if isinstance(post_data, bytes):
                            post_data = post_data.decode('utf-8')
                        if 'docs=' in post_data:
                            captured_payloads.append(post_data)
                except:
                    pass
        
        page.on("request", handle_request)
        
        try:
            # 步骤1: 选中当前页所有文章
            print(f"  [选中] 点击全选复选框...")
            select_success = await self.select_all_articles(page)
            if not select_success:
                print(f"  [警告] 选择文章可能未成功，继续...")
            
            # 等待网络请求完成
            print(f"  [等待] 等待网络请求...")
            for i in range(5):
                await asyncio.sleep(0.5)
                if captured_payloads:
                    print(f"  [成功] 捕获到 {len(captured_payloads)} 个请求")
                    break
            
            # 步骤2: 解析捕获的payload获取元数据
            if captured_payloads:
                payload = captured_payloads[-1]  # 使用最后一个
                article_metadata = self._parse_captured_payload(payload)
                if article_metadata:
                    print(f"  [成功] 从捕获的payload解析到 {len(article_metadata)} 篇文章")
            
            # 如果没有捕获到，从页面提取
            if not article_metadata:
                print(f"  [未捕获] 未捕获到payload，从页面提取...")
                article_metadata = await self._extract_selected_articles_metadata(page)
            
            # 从HTML中提取preview并补充到元数据中
            if article_metadata:
                print(f"  [补充] 从HTML提取preview...")
                html_content = await page.content()
                html_articles = self._extract_preview_from_html(html_content)
                
                # 打印payload中的docref用于对比
                print(f"  [调试] Payload中的docref (前5个):")
                for i, art in enumerate(article_metadata[:5]):
                    print(f"    {i+1}: {art.get('docref', 'N/A')}")
                
                # 打印HTML中的docref用于对比
                print(f"  [调试] HTML中的docref (前5个):")
                for i, ha in enumerate(html_articles[:5]):
                    print(f"    {i+1}: {ha.get('docref', 'N/A')}")
                
                if html_articles:
                    matched_count = 0
                    for art in article_metadata:
                        docref = art.get('docref', '')
                        for html_art in html_articles:
                            if html_art.get('docref') == docref:
                                # 如果HTML中有preview，则覆盖payload中的preview（HTML的更准确）
                                html_preview = html_art.get('preview', '')
                                if html_preview:
                                    art['preview'] = html_preview
                                    matched_count += 1
                                break
                    print(f"  [补充] 为 {matched_count} 篇文章补充了preview")
                else:
                    print(f"  [警告] 未从HTML提取到preview")
            
            if not article_metadata:
                print(f"  [第 {page_num}] 未获取到元数据")
                return None
            
            # 步骤3: 筛选 docref 以 "news/" 开头的记录
            filtered_by_docref = [
                art for art in article_metadata 
                if art.get('docref', '').startswith('news/')
            ]
            
            if len(filtered_by_docref) < len(article_metadata):
                print(f"  [预筛选] 过滤掉 {len(article_metadata) - len(filtered_by_docref)} 条非 news/ 记录")
            
            print(f"  [完成] 获取到 {len(filtered_by_docref)} 篇元数据")
            return filtered_by_docref
            
        except Exception as e:
            print(f"  [错误] 获取元数据失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
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
        
        # 检查是否是API模式成功获取的文章（有全文）
        api_success = articles_with_fulltext > 0
        
        if api_success:
            # API成功获取文章，直接保存所有文章，无需确认
            print(f"\n[API模式] 检测到 {articles_with_fulltext} 篇有全文，直接保存所有 {len(articles)} 篇文章")
            selected = articles
        else:
            # API未成功，直接退出
            print(f"\n[错误] API未成功获取文章全文，退出")
            import sys
            sys.exit(1)
        
        if not selected:
            print("未选择任何文章")
            return
        
        print(f"\n将保存 {len(selected)} 篇文章...")
        
        downloaded = 0
        
        # 移除下载限制，保存所有文章
        for i, article in enumerate(selected, 1):
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
        print("NewsBank API 下载器")
        print("=" * 80)
        print(f"\n目标URL: {url[:80]}...")
        print(f"最大页数: {self.max_pages}")
        
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
                
                # 保存文章列表到JSON（带筛选）
                articles_to_save = self.articles
                
                # 尝试从文章中提取 docref 信息进行筛选
                # ArticleInfo 有 article_id 字段，可以构造 docref
                articles_with_docref = []
                for a in self.articles:
                    if a.article_id:
                        # 构造 docref
                        docref = f"news/{a.article_id}"
                        articles_with_docref.append((a, docref))
                
                if articles_with_docref:
                    # 筛选只保留 docref 以 "news/" 开头的
                    filtered_articles = [a for a, docref in articles_with_docref if docref.startswith('news/')]
                    removed_count = len(self.articles) - len(filtered_articles)
                    
                    if removed_count > 0:
                        print(f"\n[筛选] 过滤掉 {removed_count} 条非 news/ 开头的记录")
                        print(f"[筛选] 保留 {len(filtered_articles)} 条记录")
                        articles_to_save = filtered_articles
                
                json_path = self.output_dir / f"article_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump([a.to_dict() for a in articles_to_save], f, indent=2, ensure_ascii=False)
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
    
    async def extract_metadata_only(self, url: str):
        """
        仅提取文章元数据并保存到JSON，不下载文章内容
        
        两阶段模式第一步：
        1. 访问搜索页面
        2. 选中所有文章
        3. 提取元数据并保存到JSON
        4. 让用户选择要下载的文章
        """
        print("=" * 80)
        print("元数据提取模式")
        print("=" * 80)
        print(f"\n目标URL: {url[:80]}...")
        print(f"最大页数: {self.max_pages}")
        
        # 启动浏览器
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.headless,
                args=['--disable-blink-features=AutomationControlled']
            )
            
            context = await browser.new_context(
                storage_state=str(self.cookie_file) if self.cookie_file.exists() else None,
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            
            page = await context.new_page()
            
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
                
                # 提取总结果数（从第一页HTML）
                html_content = await page.content()
                total_results = self._extract_total_results(html_content)
                if total_results:
                    print(f"总结果数: {total_results}")
                
                # 保存基础URL用于后续分页
                base_search_url = url
                
                # 提取搜索关键字
                parsed_url = urlparse(url)
                query_params = parse_qs(parsed_url.query)
                keyword = query_params.get('val-base-0', ['unknown'])[0]
                
                all_metadata = []
                
                # 初始化 LLM 客户端（如果启用）
                # 新流程：先收集所有页元数据，最后统一筛选
                llm_client = None
                llm_model = None
                use_llm_filter = os.getenv("LLM_FILTER_ENABLED", "").lower() == "true"
                llm_threshold = float(os.getenv("LLM_FILTER_THRESHOLD", "0.5"))
                
                if use_llm_filter and OPENAI_AVAILABLE:
                    llm_result = self._init_llm_client()
                    if llm_result:
                        llm_client, llm_model = llm_result
                        print(f"[LLM] 已启用，将在收集完所有页后统一筛选，阈值: {llm_threshold}")
                    else:
                        print("[警告] LLM 初始化失败，将不使用筛选")
                
                # ========== 新流程：逐页获取元数据 ==========
                for page_num in range(1, self.max_pages + 1):
                    # 使用新函数获取元数据（不下载内容）
                    article_metadata = await self.fetch_page_metadata_only(page, page_num)
                    
                    if not article_metadata:
                        print(f"  [第 {page_num}] 无法获取元数据，停止")
                        break
                    
                    # 收集元数据
                    all_metadata.extend(article_metadata)
                    print(f"  [累计] 共获取 {len(all_metadata)} 篇元数据")
                    
                    # 从URL获取p参数
                    parsed = urlparse(page.url)
                    query = parse_qs(parsed.query)
                    p_param = query.get('p', ['AWGLNB'])[0]
                    
                    # 步骤3: remove_selection 清除选择（翻页前）
                    print(f"  [清除] 翻页前清除选择...")
                    await self.remove_selection(page, p_param)
                    
                    # 步骤4: 翻到下一页
                    if page_num < self.max_pages:
                        next_button = await page.query_selector('a[data-testid="pager-next"], button[data-testid="pager-next"], a:has-text("Next"), a:has-text("›")')
                        if next_button:
                            next_url = self._build_page_url(base_search_url, page_num + 1)
                            print(f"  [翻页] 访问第 {page_num + 1} 页...")
                            await page.goto(next_url, wait_until="networkidle", timeout=60000)
                            await asyncio.sleep(2)
                        else:
                            print(f"  [信息] 未找到下一页按钮，停止")
                            break
                    
                    # 检查是否达到100篇（API限制）
                    if len(all_metadata) >= 100:
                        print(f"  [信息] 已获取100篇，达到限制")
                        break
                
                # ========== 收集完所有页后进行去重 ==========
                seen = set()
                unique_metadata = []
                for art in all_metadata:
                    docref = art.get('docref', '')
                    if docref not in seen:
                        seen.add(docref)
                        unique_metadata.append(art)
                
                print(f"\n[完成] 共提取到 {len(unique_metadata)} 篇唯一文章")
                
                # ========== 新流程：收集完所有页后，统一进行LLM筛选 ==========
                if use_llm_filter and llm_client and unique_metadata:
                    print(f"\n[LLM] 开始统一筛选 {len(unique_metadata)} 篇文章...")
                    # 批量筛选（每批20篇）
                    batch_size = 20
                    filtered_metadata = []
                    total_batches = (len(unique_metadata) + batch_size - 1) // batch_size
                    
                    for batch_idx in range(total_batches):
                        start_idx = batch_idx * batch_size
                        end_idx = min(start_idx + batch_size, len(unique_metadata))
                        batch = unique_metadata[start_idx:end_idx]
                        
                        print(f"  [LLM] 筛选批次 {batch_idx + 1}/{total_batches} ({start_idx+1}-{end_idx})...")
                        
                        filtered_batch = await self._filter_single_page_with_llm(
                            batch, keyword, llm_client, llm_model, llm_threshold
                        )
                        filtered_metadata.extend(filtered_batch)
                    
                    print(f"  [LLM] 筛选完成: {len(filtered_metadata)}/{len(unique_metadata)} 篇相关文章")
                    unique_metadata = filtered_metadata
                
                # 保存到JSON
                json_path = await self._save_article_metadata_to_json(unique_metadata, keyword)
                
                # 让用户选择
                print("\n" + "=" * 80)
                confirm = input("是否现在选择要下载的文章? (y/n): ").strip().lower()
                
                if confirm == 'y':
                    selected_metadata = await self._prompt_user_to_select_articles(unique_metadata)
                    
                    if selected_metadata:
                        print(f"\n[开始] 下载选中的 {len(selected_metadata)} 篇文章...")
                        # 重新创建浏览器上下文进行下载
                        await context.close()
                        await browser.close()
                        await self.download_selected_articles(selected_metadata, self.output_dir)
                        return
                
                print(f"\n[完成] 元数据已保存到: {json_path}")
                print("如需下载，请运行:")
                print(f"  python newsbank_api_downloader.py --from-metadata \"{json_path}\"")
                
            except Exception as e:
                print(f"\n[错误] {e}")
                import traceback
                traceback.print_exc()
            
            finally:
                await context.close()
                await browser.close()
    
    async def download_selected_articles(self, article_metadata: List[Dict[str, Any]], output_dir: str | Path):
        """
        下载用户选定的文章
        
        Args:
            article_metadata: 用户选定的文章元数据列表
            output_dir: 输出目录
        """
        print("\n" + "=" * 80)
        print("下载选定文章")
        print("=" * 80)
        
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
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
                accept_downloads=False
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
                
                # 访问任意NewsBank页面以获取session
                await page.goto(
                    "https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/results?p=AWGLNB",
                    wait_until="networkidle", timeout=30000
                )
                
                # 获取p参数
                p_param = "AWGLNB"
                
                # 调用API下载选定的文章
                print(f"\n[调用API] 下载 {len(article_metadata)} 篇文章...")
                response_data = await self._call_download_api_with_articles(page, article_metadata, p_param)
                
                if response_data and response_data.get('body'):
                    body = response_data['body']
                    print(f"  [调试] API响应长度: {len(body)} bytes")
                    
                    # 解析文章
                    articles = self._parse_api_response(body, page_num=1)
                    print(f"  [成功] 解析到 {len(articles)} 篇文章")
                    
                    # 保存文章
                    await self.save_articles(page, articles, "", download_all=True)
                else:
                    print("[错误] API调用失败")
                
            except Exception as e:
                print(f"\n[错误] {e}")
                import traceback
                traceback.print_exc()
            
            finally:
                await context.close()
                await browser.close()


def main():
    parser = argparse.ArgumentParser(
        description="NewsBank API 下载器 - 通过API获取文章内容",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用方法示例:

1. 使用搜索关键字:
   python newsbank_api_downloader.py "treasury wine penfolds" --max-results 200

2. 指定年份范围:
   python newsbank_api_downloader.py "treasury wine" --year-from 2014 --year-to 2020

3. 指定数据源:
   python newsbank_api_downloader.py "treasury wine" --source "Australian Financial Review Collection"

4. 使用完整URL:
   python newsbank_api_downloader.py "https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/results?..."

5. 限制页数和下载数:
   python newsbank_api_downloader.py "treasury wine" --max-pages 5 --max-results 100

6. 无头模式:
   python newsbank_api_downloader.py "treasury wine" --headless

7. 仅提取元数据（两阶段模式）:
   python newsbank_api_downloader.py "treasury wine" --metadata-only

8. 从元数据文件加载并选择下载:
   python newsbank_api_downloader.py --from-metadata "article_metadata_xxx.json"

9. 设置单次下载最大数量:
   python newsbank_api_downloader.py --from-metadata "xxx.json" --max-download 10

10. 使用 LLM 筛选文章相关性:
   python newsbank_api_downloader.py --filter-from "article_treasury_wine_xxx.json"

11. LLM 筛选并指定阈值:
   python newsbank_api_downloader.py --filter-from "xxx.json" --threshold 0.7

12. LLM 筛选并指定模型:
   python newsbank_api_downloader.py --filter-from "xxx.json" --llm-model "z-ai/glm4.7"
        """
    )
    
    parser.add_argument("keyword_or_url", nargs='?', default=None,
                       help="搜索关键字或NewsBank搜索URL (LLM筛选模式时可选)")
    
    parser.add_argument("--max-results", type=int, default=200,
                       help="最大结果数 (默认: 200)")
    
    parser.add_argument("--max-pages", type=int, default=10,
                       help="最大扫描页数 (默认: 10)")
    
    parser.add_argument("--year-from", type=int, default=None,
                       help="起始年份 (例如: 2014)")
    
    parser.add_argument("--year-to", type=int, default=None,
                       help="结束年份 (例如: 2020)")
    
    parser.add_argument("--source", type=str, default="Australian Financial Review Collection",
                       help="数据源名称 (默认: Australian Financial Review Collection)")
    
    parser.add_argument("--headless", action="store_true",
                       help="无头模式")
    
    parser.add_argument("--delay", type=float, default=3.0,
                       help="请求间隔秒数，防止被封 (默认: 3.0)")
    
    parser.add_argument("--output-dir", default="articles_api",
                       help="输出目录 (默认: articles_api)")
    
    # 新增：两阶段模式参数
    parser.add_argument("--metadata-only", action="store_true",
                       help="仅提取文章元数据并保存到JSON，不下载文章内容")
    
    parser.add_argument("--from-metadata", type=str, default=None,
                       help="从已保存的元数据JSON文件加载并让用户选择下载")
    
    parser.add_argument("--max-download", type=int, default=20,
                       help="单次下载最大文章数 (默认: 20，防止服务器限制)")
    
    # LLM 筛选参数
    parser.add_argument("--filter-llm", action="store_true",
                       help="使用 LLM 筛选相关文章")
    
    parser.add_argument("--filter-from", type=str, default=None,
                       help="从已保存的 article_*.json 文件进行 LLM 筛选")
    
    parser.add_argument("--api-key", type=str, default=None,
                       help="LLM API 密钥 (默认从环境变量 NVIDIA_API_KEY 或 OPENAI_API_KEY 读取)")
    
    parser.add_argument("--llm-model", type=str, default=None,
                       help="LLM 模型名称 (默认: z-ai/glm4.7 for NVIDIA, gpt-3.5-turbo for OpenAI)")
    
    parser.add_argument("--threshold", type=float, default=0.5,
                       help="LLM 相关性阈值 (0-1, 默认: 0.5)")
    
    parser.add_argument("--batch-size", type=int, default=10,
                       help="LLM 每批次处理的文章数 (默认: 10)")
    
    args = parser.parse_args()
    
    print(f"[注意] 请求间隔: {args.delay} 秒 (防止被封)")
    
    # 创建下载器实例
    downloader = NewsBankAPIDownloader(
        headless=args.headless,
        max_pages=args.max_pages,
        output_dir=args.output_dir,
        request_delay=args.delay
    )
    
    # 模式2: 从元数据文件加载并下载
    if args.from_metadata:
        json_path = Path(args.from_metadata)
        if not json_path.exists():
            print(f"[错误] 文件不存在: {json_path}")
            return
        
        # 加载元数据
        article_metadata = downloader._load_article_metadata_from_json(json_path)
        if not article_metadata:
            print("[错误] 加载元数据失败")
            return
        
        # 让用户选择
        selected_metadata = asyncio.run(downloader._prompt_user_to_select_articles(
            article_metadata, max_download=args.max_download
        ))
        
        if not selected_metadata:
            print("已取消下载")
            return
        
        # 下载选中的文章
        print(f"\n[开始] 下载选中的 {len(selected_metadata)} 篇文章...")
        asyncio.run(downloader.download_selected_articles(selected_metadata, args.output_dir))
        return
    
    # LLM 筛选模式
    if args.filter_from:
        print("\n[模式] LLM 智能筛选模式")
        print("=" * 50)
        
        json_path = Path(args.filter_from)
        if not json_path.exists():
            print(f"[错误] 文件不存在: {json_path}")
            return
        
        # 运行 LLM 筛选
        result = asyncio.run(downloader._filter_articles_by_llm(
            json_file=json_path,
            api_key=args.api_key,
            model=args.llm_model,
            threshold=args.threshold,
            batch_size=args.batch_size
        ))
        
        if result:
            print(f"\n[完成] LLM 筛选完成，结果已保存到: {result}")
            print("\n可以使用 --from-metadata 参数下载筛选后的文章:")
            print(f"  python newsbank_api_downloader.py --from-metadata \"{result}\"")
        else:
            print("[错误] LLM 筛选失败")
        return
    
    # 判断输入是关键字还是URL
    if downloader._is_search_keyword(args.keyword_or_url):
        # 是关键字，构建搜索URL
        print(f"\n[信息] 检测为搜索关键字: {args.keyword_or_url}")
        search_url = downloader._build_search_url(
            keyword=args.keyword_or_url,
            maxresults=args.max_results,
            source=args.source,
            year_from=args.year_from,
            year_to=args.year_to
        )
        print(f"[信息] 生成的搜索URL:")
        print(f"  {search_url}")
        url = search_url
    else:
        # 是URL，直接使用
        url = args.keyword_or_url
        print(f"\n[信息] 使用提供的URL: {url}")
    
    # 模式1: 仅提取元数据
    if args.metadata_only:
        print("\n[模式] 元数据提取模式")
        print("=" * 50)
        asyncio.run(downloader.extract_metadata_only(url))
        return
    
    # 正常下载模式
    asyncio.run(downloader.download_from_url(url, download_all=True))


if __name__ == "__main__":
    exit(main())
