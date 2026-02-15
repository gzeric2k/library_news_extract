# -*- coding: utf-8 -*-
"""
NewsBank URL Direct Downloader
NewsBank URL直下载工具

功能：
1. 用户直接输入NewsBank搜索URL
2. 解析URL参数（可选）
3. 直接访问该URL获取文章列表
4. 选择性或批量下载文章

使用方法：
    python newsbank_url_downloader.py "https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/results?..."
    
    python newsbank_url_downloader.py "URL" --max-pages 5 --download-all
    
    python newsbank_url_downloader.py "URL" --interactive

作者: AI Assistant
日期: 2026-02-15
"""

import asyncio
import argparse
import json
import random
import time
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from urllib.parse import urlparse, parse_qs, urljoin, quote, unquote
from dataclasses import dataclass, asdict

from playwright.async_api import async_playwright


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
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class URLAnalysis:
    """URL分析结果"""
    original_url: str
    base_params: Dict[str, str]
    search_conditions: List[Dict[str, str]]
    total_conditions: int
    source_filter: Optional[str]
    sort_method: Optional[str]
    max_results: int
    
    def to_display_string(self) -> str:
        """格式化为显示字符串"""
        lines = [
            "URL Analysis Results",
            "=" * 60,
            f"Original URL: {self.original_url[:80]}...",
            "",
            "Base Parameters:",
        ]
        
        for key, value in self.base_params.items():
            lines.append(f"  {key}: {value}")
        
        lines.extend([
            "",
            f"Search Conditions ({self.total_conditions} total):",
        ])
        
        for i, condition in enumerate(self.search_conditions[:5], 1):
            field = condition.get('field', 'unknown')
            value = condition.get('value', '')
            boolean = condition.get('boolean', 'AND')
            lines.append(f"  [{i}] {boolean} {field}: {value[:50]}")
        
        if self.total_conditions > 5:
            lines.append(f"  ... and {self.total_conditions - 5} more")
        
        lines.extend([
            "",
            f"Source Filter: {self.source_filter or 'None'}",
            f"Sort Method: {self.sort_method or 'Default'}",
            f"Max Results per Page: {self.max_results}",
            "=" * 60,
        ])
        
        return "\n".join(lines)


class URLParser:
    """NewsBank URL解析器"""
    
    @staticmethod
    def parse_url(url: str) -> URLAnalysis:
        """
        解析NewsBank URL参数
        
        Args:
            url: NewsBank搜索URL
        
        Returns:
            URLAnalysis对象
        """
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        
        # 解析基础参数
        base_params = {}
        for key, values in query_params.items():
            if len(values) == 1:
                base_params[key] = values[0]
            else:
                base_params[key] = values
        
        # 解析搜索条件
        search_conditions = []
        condition_index = 0
        
        while True:
            value_key = f'val-base-{condition_index}'
            field_key = f'fld-base-{condition_index}'
            boolean_key = f'bln-base-{condition_index}'
            
            if value_key not in base_params:
                break
            
            condition = {
                'index': condition_index,
                'value': unquote(base_params.get(value_key, '')),
                'field': base_params.get(field_key, 'unknown'),
                'boolean': base_params.get(boolean_key, 'AND' if condition_index > 0 else None)
            }
            search_conditions.append(condition)
            condition_index += 1
        
        # 提取其他信息
        source_filter = None
        if 't' in base_params:
            t_param = base_params['t']
            if 'favorite:' in str(t_param):
                match = re.search(r'favorite:([^!]+)', str(t_param))
                if match:
                    source_filter = match.group(1)
        
        sort_method = base_params.get('sort', 'Default')
        if sort_method == 'YMD_date:D':
            sort_method = 'Date (Newest First)'
        elif sort_method == 'YMD_date:A':
            sort_method = 'Date (Oldest First)'
        elif sort_method == 'relevance':
            sort_method = 'Relevance'
        
        max_results = int(base_params.get('maxresults', 60))
        
        return URLAnalysis(
            original_url=url,
            base_params=base_params,
            search_conditions=search_conditions,
            total_conditions=len(search_conditions),
            source_filter=source_filter,
            sort_method=sort_method,
            max_results=max_results
        )
    
    @staticmethod
    def validate_url(url: str) -> Tuple[bool, str]:
        """
        验证URL是否有效
        
        Returns:
            (是否有效, 错误信息)
        """
        if not url or not url.strip():
            return False, "URL不能为空"
        
        url = url.strip()
        
        # 检查是否包含NewsBank域名
        if 'infoweb-newsbank-com' not in url and 'newsbank.com' not in url:
            return False, "URL不是NewsBank的搜索URL"
        
        # 检查是否是搜索结果页
        if '/apps/news/results' not in url:
            return False, "URL不是搜索结果页面"
        
        # 检查是否有搜索参数
        parsed = urlparse(url)
        if not parsed.query:
            return False, "URL没有搜索参数"
        
        return True, "Valid"


class NewsBankURLDownloader:
    """NewsBank URL直下载器"""
    
    def __init__(self,
                 headless: bool = False,
                 max_pages: int = 10,
                 download_limit: int = 50,
                 min_preview_words: int = 30,
                 interactive: bool = False,
                 output_dir: str = "articles_url"):
        self.headless = headless
        self.max_pages = max_pages
        self.download_limit = download_limit
        self.min_preview_words = min_preview_words
        self.interactive = interactive
        
        self.cookie_file = Path("cookies/newsbank_auth.json")
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cookie_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 反检测
        self.min_delay = 2
        self.max_delay = 5
        self.last_request_time = 0
        
        # 统计
        self.stats = {
            "total_pages": 0,
            "total_articles": 0,
            "selected_articles": 0,
            "downloaded": 0,
            "skipped": 0,
            "errors": []
        }
        
        self.articles: List[ArticleInfo] = []
        self.url_analysis: Optional[URLAnalysis] = None
    
    async def human_like_delay(self, min_sec: float = 0, max_sec: float = 0):
        """添加随机延迟"""
        min_seconds = min_sec if min_sec > 0 else self.min_delay
        max_seconds = max_sec if max_sec > 0 else self.max_delay
        delay = random.uniform(min_seconds, max_seconds)
        
        time_since_last = time.time() - self.last_request_time
        if time_since_last < min_seconds:
            delay = max(delay, min_seconds - time_since_last)
        
        await asyncio.sleep(delay)
        self.last_request_time = time.time()
    
    async def check_login(self, context) -> bool:
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
    
    async def do_login(self, page) -> bool:
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
    
    async def scan_articles(self, page, url: str) -> List[ArticleInfo]:
        """扫描文章列表"""
        print("\n" + "=" * 70)
        print("扫描文章列表")
        print("=" * 70)
        
        articles = []
        
        for page_num in range(1, self.max_pages + 1):
            print(f"\n[第 {page_num} 页]")
            
            if page_num > 1:
                # 点击下一页
                next_button = await page.query_selector('a:has-text("Next")')
                if not next_button or await next_button.is_disabled():
                    print("  无更多页面")
                    break
                
                await next_button.click()
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(1)
            
            # 提取文章
            article_elements = await page.query_selector_all('article.search-hits__hit')
            
            if not article_elements:
                print("  未找到文章")
                break
            
            self.stats["total_pages"] += 1
            print(f"  找到 {len(article_elements)} 篇文章")
            
            page_articles = []
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
                        article_id = id_match.group(1)
                    
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
                    
                    page_articles.append(article)
                    
                    # 显示前几篇文章
                    if i <= 3:
                        print(f"  [{i}] {title[:60]}... ({word_count}词)")
                
                except Exception as e:
                    print(f"  [错误] 提取文章失败: {e}")
                    continue
            
            articles.extend(page_articles)
            self.stats["total_articles"] += len(page_articles)
            
            print(f"  本页成功提取: {len(page_articles)} 篇")
        
        return articles
    
    def display_article_list(self, articles: List[ArticleInfo]):
        """显示文章列表"""
        print("\n" + "=" * 70)
        print(f"文章列表 (共 {len(articles)} 篇)")
        print("=" * 70)
        
        for i, article in enumerate(articles[:20], 1):
            quality_mark = "✓" if article.word_count >= self.min_preview_words else "✗"
            print(f"\n[{i:3d}] {quality_mark} {article.title[:70]}")
            print(f"      日期: {article.date}")
            print(f"      来源: {article.source}")
            print(f"      预览: {article.word_count}词")
            print(f"      链接: {article.url[:60]}...")
        
        if len(articles) > 20:
            print(f"\n... 还有 {len(articles) - 20} 篇文章 ...")
        
        print("=" * 70)
    
    async def interactive_select(self, articles: List[ArticleInfo]) -> List[ArticleInfo]:
        """交互式选择文章"""
        print("\n" + "=" * 70)
        print("交互式选择")
        print("=" * 70)
        print("输入要下载的文章编号，用逗号分隔")
        print("例如: 1,3,5,7-10")
        print("输入 'all' 下载所有文章")
        print("输入 'quality' 下载所有优质文章（预览>30词）")
        print("输入 'q' 退出")
        print("-" * 70)
        
        while True:
            try:
                user_input = input("\n请输入选择: ").strip().lower()
                
                if user_input == 'q':
                    return []
                
                if user_input == 'all':
                    return articles
                
                if user_input == 'quality':
                    quality_articles = [a for a in articles if a.word_count >= self.min_preview_words]
                    print(f"已选择 {len(quality_articles)} 篇优质文章")
                    return quality_articles
                
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
                print(f"已选择 {len(selected)} 篇文章")
                return selected
                
            except (ValueError, IndexError) as e:
                print(f"输入格式错误: {e}")
                print("请重新输入")
    
    async def download_articles(self, page, articles: List[ArticleInfo], url: str) -> int:
        """下载选中的文章"""
        print("\n" + "=" * 70)
        print(f"开始下载文章 (共 {len(articles)} 篇)")
        print("=" * 70)
        
        downloaded = 0
        
        for i, article in enumerate(articles[:self.download_limit], 1):
            print(f"\n[{i}/{len(articles)}] 下载: {article.title[:60]}...")
            
            try:
                await self.human_like_delay(3, 7)
                
                # 访问文章页面
                await page.goto(article.url, wait_until="networkidle", timeout=30000)
                await asyncio.sleep(2)
                
                # 提取全文
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
                
                if not full_text:
                    # 备选方案：提取所有段落
                    paragraphs = await page.query_selector_all('p')
                    texts = []
                    for p in paragraphs:
                        text = await p.inner_text()
                        if len(text.strip()) > 20:
                            texts.append(text)
                    full_text = '\n\n'.join(texts)
                
                if len(full_text.strip()) < 50:
                    print(f"  [警告] 文章无有效全文")
                    self.stats["skipped"] += 1
                    continue
                
                # 保存文章
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_title = "".join(c for c in article.title[:50] if c.isalnum() or c in (' ', '-', '_')).strip()
                filename = f"{i:03d}_{timestamp}_{safe_title}.txt"
                filepath = self.output_dir / filename
                
                content = f"""Title: {article.title}
Date: {article.date}
Source: {article.source}
Author: {article.author}
URL: {article.url}
Original Search URL: {url}
Downloaded at: {datetime.now().isoformat()}
Page: {article.page_num}

Full Text:
{full_text}

{'='*70}
"""
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                downloaded += 1
                self.stats["downloaded"] += 1
                print(f"  [成功] 已保存 ({len(full_text)} 字符) -> {filename}")
                
            except Exception as e:
                print(f"  [错误] 下载失败: {e}")
                self.stats["errors"].append(f"{article.title}: {str(e)}")
                continue
        
        return downloaded
    
    async def download_from_url(self, url: str):
        """从URL下载文章的主方法"""
        # 验证URL
        is_valid, message = URLParser.validate_url(url)
        if not is_valid:
            print(f"[错误] {message}")
            return
        
        print("=" * 80)
        print("NewsBank URL直下载工具")
        print("=" * 80)
        
        # 解析URL
        self.url_analysis = URLParser.parse_url(url)
        print("\n" + self.url_analysis.to_display_string())
        
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
                # 检查/执行登录
                if not await self.check_login(context):
                    if self.headless:
                        print("[错误] 无头模式下无法登录")
                        return
                    
                    if not await self.do_login(page):
                        return
                    
                    # 保存Cookie
                    await context.storage_state(path=str(self.cookie_file))
                
                # 访问搜索URL
                print(f"\n[访问URL]")
                print(f"正在打开搜索页面...")
                
                await page.goto(url, wait_until="networkidle", timeout=60000)
                await asyncio.sleep(2)
                
                print(f"页面标题: {await page.title()}")
                
                # 扫描文章
                self.articles = await self.scan_articles(page, url)
                
                if not self.articles:
                    print("\n[警告] 未找到任何文章")
                    return
                
                # 显示文章列表
                self.display_article_list(self.articles)
                
                # 保存文章列表到JSON
                json_path = self.output_dir / f"article_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump([a.to_dict() for a in self.articles], f, indent=2, ensure_ascii=False)
                print(f"\n文章列表已保存: {json_path}")
                
                # 选择要下载的文章
                if self.interactive:
                    selected = await self.interactive_select(self.articles)
                else:
                    # 自动选择优质文章
                    selected = [a for a in self.articles if a.word_count >= self.min_preview_words]
                    print(f"\n自动选择 {len(selected)} 篇优质文章")
                
                if not selected:
                    print("\n[信息] 没有选择任何文章")
                    return
                
                self.stats["selected_articles"] = len(selected)
                
                # 下载文章
                downloaded = await self.download_articles(page, selected, url)
                
                # 最终报告
                print("\n" + "=" * 80)
                print("下载完成报告")
                print("=" * 80)
                print(f"扫描页数: {self.stats['total_pages']}")
                print(f"发现文章: {self.stats['total_articles']}")
                print(f"选择文章: {self.stats['selected_articles']}")
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
        description="NewsBank URL直下载工具 - 直接输入URL下载文章",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用方法示例:

1. 基础使用（自动下载优质文章）:
   python newsbank_url_downloader.py "https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/results?..."

2. 交互式选择文章:
   python newsbank_url_downloader.py "URL" --interactive

3. 限制页数和下载数量:
   python newsbank_url_downloader.py "URL" --max-pages 3 --download-limit 20

4. 下载所有文章:
   python newsbank_url_downloader.py "URL" --download-all

5. 无头模式:
   python newsbank_url_downloader.py "URL" --headless

URL获取方法:
   1. 在浏览器中访问NewsBank并搜索
   2. 调整搜索条件到满意结果
   3. 复制浏览器地址栏的URL
   4. 使用本工具下载

注意:
   - URL必须是NewsBank搜索结果页
   - 首次使用需要登录（会自动提示）
   - 登录状态会保存，后续无需重复登录
        """
    )
    
    parser.add_argument("url", help="NewsBank搜索URL")
    
    parser.add_argument("--max-pages", type=int, default=10,
                       help="最大扫描页数 (默认: 10)")
    
    parser.add_argument("--download-limit", type=int, default=50,
                       help="最大下载文章数 (默认: 50)")
    
    parser.add_argument("--min-preview-words", type=int, default=30,
                       help="优质文章最小预览词数 (默认: 30)")
    
    parser.add_argument("--interactive", action="store_true",
                       help="交互式选择文章")
    
    parser.add_argument("--download-all", action="store_true",
                       help="下载所有文章（跳过交互选择）")
    
    parser.add_argument("--headless", action="store_true",
                       help="无头模式")
    
    parser.add_argument("--output-dir", default="articles_url",
                       help="输出目录 (默认: articles_url)")
    
    parser.add_argument("--analyze-only", action="store_true",
                       help="仅分析URL参数，不下载")
    
    args = parser.parse_args()
    
    # 仅分析URL
    if args.analyze_only:
        print("=" * 80)
        print("URL分析模式")
        print("=" * 80)
        
        is_valid, message = URLParser.validate_url(args.url)
        if not is_valid:
            print(f"[错误] {message}")
            return 1
        
        analysis = URLParser.parse_url(args.url)
        print(analysis.to_display_string())
        return 0
    
    # 创建下载器
    downloader = NewsBankURLDownloader(
        headless=args.headless,
        max_pages=args.max_pages,
        download_limit=args.download_limit,
        min_preview_words=args.min_preview_words,
        interactive=args.interactive or not args.download_all,
        output_dir=args.output_dir
    )
    
    # 执行下载
    asyncio.run(downloader.download_from_url(args.url))
    
    return 0


if __name__ == "__main__":
    exit(main())
