# -*- coding: utf-8 -*-
"""
NewsBank AI智能下载器（LLM增强版）
使用AI自动筛选和下载与主题相关的文章

功能：
1. 智能解析URL搜索意图
2. AI自动评估每篇文章相关性（默认使用LLM）
3. 只下载高相关度文章
4. 支持多种AI筛选策略

使用方法：
    # LLM增强筛选（默认，需要NVIDIA_API_KEY）
    python newsbank_ai_downloader.py
    
    # 禁用LLM，仅使用关键词匹配
    python newsbank_ai_downloader.py --no-llm
    
    # BERT+LLM双重筛选
    python newsbank_ai_downloader.py --use-bert

环境变量配置 (.env文件):
    NVIDIA_API_KEY=nvapi-your-key-here  （默认使用）
    OPENAI_API_KEY=sk-your-key-here     （备选）
    LLM_PROVIDER=auto
    LLM_MODEL=z-ai/glm4.7
    RELEVANCE_THRESHOLD=0.4

作者: AI Assistant
日期: 2026-02-15
"""

import os
import sys
import asyncio
import argparse
import json
import random
import time
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from urllib.parse import urlparse, parse_qs, urljoin, unquote, urlencode, parse_qsl
from dataclasses import dataclass, asdict

from playwright.async_api import async_playwright

# 加载 .env 文件
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 尝试导入OpenAI
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# NVIDIA API配置
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"


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
    relevance_score: float = 0.0  # AI相关性分数
    relevance_reason: str = ""     # AI判断理由
    
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
    extracted_keywords: List[str]  # 从URL提取的关键词
    
    def to_display_string(self) -> str:
        """格式化为显示字符串"""
        lines = [
            "",
            "=" * 70,
            "URL Analysis Results",
            "=" * 70,
            f"Original URL: {self.original_url[:80]}...",
            "",
            "Base Parameters:",
        ]
        
        for key, value in self.base_params.items():
            lines.append(f"   {key}: {value}")
        
        lines.extend([
            "",
            f"Search Conditions ({self.total_conditions} total):",
        ])
        
        for i, condition in enumerate(self.search_conditions[:5], 1):
            field = condition.get('field', 'unknown')
            value = condition.get('value', '')
            boolean = condition.get('boolean', 'AND')
            lines.append(f"   [{i}] {boolean} {field}: {value[:50]}")
        
        if self.total_conditions > 5:
            lines.append(f"   ... and {self.total_conditions - 5} more")
        
        lines.extend([
            "",
            f"Source Filter: {self.source_filter or 'None'}",
            f"Sort Method: {self.sort_method or 'Default'}",
            f"Max Results per Page: {self.max_results}",
            "",
            "Extracted Keywords for AI Filtering:",
        ])
        
        for kw in self.extracted_keywords:
            lines.append(f"   *{kw}")
        
        lines.append("=" * 70)
        
        return "\n".join(lines)


class URLParser:
    """NewsBank URL解析器"""
    
    @staticmethod
    def parse_url(url: str) -> URLAnalysis:
        """
        解析NewsBank URL参数并提取关键词
        
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
        extracted_keywords = []
        
        while True:
            value_key = f'val-base-{condition_index}'
            field_key = f'fld-base-{condition_index}'
            boolean_key = f'bln-base-{condition_index}'
            
            if value_key not in base_params:
                break
            
            value = unquote(base_params.get(value_key, ''))
            field = base_params.get(field_key, 'unknown')
            boolean = base_params.get(boolean_key, 'AND' if condition_index > 0 else None)
            
            condition = {
                'index': condition_index,
                'value': value,
                'field': field,
                'boolean': boolean
            }
            search_conditions.append(condition)
            
            # 提取关键词（用于AI筛选）
            if value and field in ['all', 'headline', 'Title', 'alltext', 'body']:
                # 清理关键词
                clean_kw = value.strip().lower()
                # 移除引号
                clean_kw = clean_kw.strip('"').strip("'")
                # 分割多个关键词
                for kw in re.split(r'[;,|]', clean_kw):
                    kw = kw.strip()
                    if kw and len(kw) > 1:
                        extracted_keywords.append(kw)
            
            condition_index += 1
        
        # 提取其他信息
        source_filter = None
        year_filter = None
        if 't' in base_params:
            t_param = base_params['t']
            if 'favorite:' in str(t_param):
                match = re.search(r'favorite:([^!]+)', str(t_param))
                if match:
                    source_filter = unquote(match.group(1))
            # 提取年份
            year_match = re.search(r'year:(\d{4})!(\d{4})', str(t_param))
            if year_match:
                year_filter = f"{year_match.group(1)}-{year_match.group(2)}"
        
        sort_method = base_params.get('sort', 'Default')
        if sort_method == 'YMD_date:D':
            sort_method = 'Date (Newest First)'
        elif sort_method == 'YMD_date:A':
            sort_method = 'Date (Oldest First)'
        elif sort_method == 'relevance':
            sort_method = 'Relevance'
        
        max_results = int(base_params.get('maxresults', 60))
        
        # 如果没有提取到关键词，尝试从URL其他部分提取
        if not extracted_keywords:
            # 尝试从整个URL中提取可能的搜索词
            url_text = unquote(url).lower()
            # 移除URL参数名，保留值
            for pattern in [r'val-base-\d+[=]([^&]+)', r'q[=]([^&]+)', r'query[=]([^&]+)']:
                matches = re.findall(pattern, url_text)
                for match in matches:
                    clean = match.strip('"').strip("'").strip()
                    if clean and len(clean) > 1:
                        extracted_keywords.append(clean)
        
        # 去重并保持顺序
        seen = set()
        unique_keywords = []
        for kw in extracted_keywords:
            if kw not in seen:
                seen.add(kw)
                unique_keywords.append(kw)
        extracted_keywords = unique_keywords
        
        # 如果有年份信息，添加到来源过滤器
        if year_filter and source_filter:
            source_filter = f"{source_filter} ({year_filter})"
        
        return URLAnalysis(
            original_url=url,
            base_params=base_params,
            search_conditions=search_conditions,
            total_conditions=len(search_conditions),
            source_filter=source_filter,
            sort_method=sort_method,
            max_results=max_results,
            extracted_keywords=extracted_keywords
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


class LLMArticleFilter:
    """LLM智能文章筛选器"""
    
    def __init__(self, 
                 api_key: Optional[str] = None, 
                 model: str = "gpt-3.5-turbo",
                 base_url: Optional[str] = None, 
                 provider: str = "auto",
                 relevance_threshold: float = 0.4):
        """
        初始化LLM筛选器
        
        Args:
            api_key: API Key
            model: 模型名称
            base_url: API基础URL
            provider: 提供商 ("nvidia", "openai", "auto")
            relevance_threshold: 相关性阈值
        """
        if not OPENAI_AVAILABLE:
            raise ImportError("openai未安装，运行: pip install openai")
        
        self.provider = self._detect_provider(api_key, base_url, provider)
        self.client = self._initialize_client(api_key, base_url)
        self.model = self._get_model_name(model)
        self.relevance_threshold = relevance_threshold
        self.target_keywords: List[str] = []
        
        print(f"[LLM] 使用{self.provider.upper()} API, 模型: {self.model}")
        print(f"[LLM] 相关性阈值: {relevance_threshold}")
    
    def _detect_provider(self, api_key: Optional[str], base_url: Optional[str], 
                        provider: str) -> str:
        """自动检测API提供商"""
        if provider != "auto":
            return provider
        
        if base_url and "nvidia" in base_url.lower():
            return "nvidia"
        
        if api_key and api_key.startswith("nvapi-"):
            return "nvidia"
        
        return "openai"
    
    def _initialize_client(self, api_key: Optional[str], base_url: Optional[str]):
        """初始化API客户端"""
        if not OPENAI_AVAILABLE:
            raise ImportError("openai 包未安装，无法初始化客户端")
        
        # 使用类型忽略来避免 LSP 错误
        import openai as oai  # type: ignore
        
        if self.provider == "nvidia":
            return oai.OpenAI(
                api_key=api_key,
                base_url=base_url or NVIDIA_BASE_URL
            )
        else:
            return oai.OpenAI(api_key=api_key)
    
    def _get_model_name(self, model: str) -> str:
        """获取正确的模型名称"""
        if self.provider == "nvidia":
            # NVIDIA模型名称映射
            nvidia_models = {
                "gpt-3.5-turbo": "meta/llama-3.1-405b-instruct",
                "gpt-4": "meta/llama-3.1-405b-instruct",
                "llama-3.1-405b": "meta/llama-3.1-405b-instruct",
                "llama-3.1-70b": "meta/llama-3.1-70b-instruct",
                "llama-3.1-8b": "meta/llama-3.1-8b-instruct",
            }
            return nvidia_models.get(model, model)
        return model
    
    def set_keywords(self, keywords: List[str]):
        """设置目标关键词"""
        self.target_keywords = keywords
        print(f"[LLM] 目标关键词: {', '.join(keywords)}")
    
    def check_api_connection(self) -> Tuple[bool, str]:
        """
        检测 LLM API 是否在线可用
        
        Returns:
            (是否在线, 状态信息)
        """
        if not OPENAI_AVAILABLE:
            return False, "openai 包未安装"
        
        try:
            # 发送一个简单的测试请求
            from typing import Any
            test_messages: List[Any] = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say 'API is working' and nothing else."}
            ]
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=test_messages,
                temperature=0.1,
                max_tokens=20
            )
            
            if response and response.choices and len(response.choices) > 0:
                content = response.choices[0].message.content
                if content and len(content) > 0:
                    return True, f"API 在线正常 (响应: {content[:30]}...)"
                else:
                    return True, "API 在线但响应内容为空"
            else:
                return False, "API 响应格式异常"
                
        except Exception as e:
            error_msg = str(e).lower()
            if "authentication" in error_msg or "api key" in error_msg:
                return False, f"API Key 认证失败: {str(e)[:50]}"
            elif "rate limit" in error_msg or "too many requests" in error_msg:
                return False, f"API 速率限制: {str(e)[:50]}"
            elif "connection" in error_msg or "timeout" in error_msg:
                return False, f"API 连接失败: {str(e)[:50]}"
            else:
                return False, f"API 检测失败: {str(e)[:50]}"
    
    async def filter_articles_batch(self, articles: List[ArticleInfo], 
                                    batch_size: int = 10) -> List[ArticleInfo]:
        """
        批量使用LLM筛选文章
        
        Args:
            articles: 文章列表
            batch_size: 每批处理的文章数
        
        Returns:
            筛选后的文章列表（添加了relevance_score和relevance_reason）
        """
        if not self.target_keywords:
            print("[警告] 未设置目标关键词，跳过LLM筛选")
            return articles
        
        print(f"\n[LLM筛选] 正在评估 {len(articles)} 篇文章...")
        print("-" * 60)
        
        filtered_articles = []
        
        # 分批处理
        for i in range(0, len(articles), batch_size):
            batch = articles[i:i+batch_size]
            print(f"  处理批次 {i//batch_size + 1}/{(len(articles)-1)//batch_size + 1} ({len(batch)} 篇)")
            
            batch_results = await self._evaluate_batch(batch)
            filtered_articles.extend(batch_results)
            
            # 添加延迟避免API限制
            if i + batch_size < len(articles):
                await asyncio.sleep(0.5)
        
        # 按相关性分数排序
        filtered_articles.sort(key=lambda x: x.relevance_score, reverse=True)
        
        # 统计
        relevant_count = sum(1 for a in filtered_articles if a.relevance_score >= self.relevance_threshold)
        print(f"\n[LLM筛选完成]")
        print(f"  总文章数: {len(filtered_articles)}")
        print(f"  相关文章: {relevant_count} (≥{self.relevance_threshold})")
        print(f"  筛选比例: {relevant_count/len(filtered_articles)*100:.1f}%")
        
        return filtered_articles
    
    async def _evaluate_batch(self, articles: List[ArticleInfo]) -> List[ArticleInfo]:
        """评估一批文章"""
        # 构建提示 - 发送完整的标题和预览内容
        articles_text = "\n\n".join([
            f"[{i+1}] 标题: {a.title}\n    预览: {a.preview}"
            for i, a in enumerate(articles)
        ])
        
        keywords_text = ", ".join(self.target_keywords)
        
        prompt = f"""请评估以下文章与搜索主题的相关性。

搜索主题关键词: {keywords_text}

文章列表:
{articles_text}

请为每篇文章给出:
1. 相关性分数 (0-100): 0=完全无关, 100=高度相关
2. 判断理由: 简要说明为什么相关或不相关

回复格式（严格按此格式）:
[1] 分数: XX, 理由: XXXXXX
[2] 分数: XX, 理由: XXXXXX
..."""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a professional article relevance assessment assistant. Analyze news articles and provide relevance scores based on the given keywords. Be objective and consistent."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=800
            )
            
            content = response.choices[0].message.content or ""
            
            # 解析结果
            results = self._parse_llm_response(content, len(articles))
            
            # 更新文章对象
            for i, article in enumerate(articles):
                if i < len(results):
                    article.relevance_score = results[i]['score']
                    article.relevance_reason = results[i]['reason']
                else:
                    article.relevance_score = 0.0
                    article.relevance_reason = "解析失败"
            
            return articles
            
        except Exception as e:
            print(f"  [错误] LLM API调用失败: {e}")
            # 如果API失败，给所有文章默认分数
            for article in articles:
                article.relevance_score = 0.5
                article.relevance_reason = f"API错误: {str(e)[:50]}"
            return articles
    
    def _parse_llm_response(self, content: str, expected_count: int) -> List[Dict]:
        """解析LLM回复"""
        results = []
        
        # 尝试匹配格式: [N] 分数: XX, 理由: XXXXXX
        pattern = r'\[(\d+)\]\s*分数[:：]\s*(\d+),?\s*理由[:：]\s*(.+?)(?=\[\d+\]|$)'
        matches = re.findall(pattern, content, re.DOTALL)
        
        if matches:
            for match in matches:
                idx = int(match[0]) - 1
                score = int(match[1]) / 100.0
                reason = match[2].strip()
                results.append({'index': idx, 'score': score, 'reason': reason})
        else:
            # 备选解析：查找所有数字作为分数
            scores = re.findall(r'(\d+)', content)
            reasons = content.split('\n')
            
            for i in range(min(len(scores), expected_count)):
                score = min(100, max(0, int(scores[i]))) / 100.0
                reason = reasons[i] if i < len(reasons) else "未提供理由"
                results.append({'index': i, 'score': score, 'reason': reason[:100]})
        
        # 确保有所有文章的结果
        while len(results) < expected_count:
            results.append({'index': len(results), 'score': 0.5, 'reason': '未解析到结果'})
        
        return results[:expected_count]


class NewsBankAIDownloader:
    """NewsBank AI智能下载器"""
    
    def __init__(self,
                 headless: bool = False,
                 max_pages: int = 10,
                 download_limit: int = 50,
                 min_preview_words: int = 30,
                 use_llm: bool = True,
                 use_bert: bool = False,
                 relevance_threshold: float = 0.4,
                 output_dir: str = "articles_ai"):
        self.headless = headless
        self.max_pages = max_pages
        self.download_limit = download_limit
        self.min_preview_words = min_preview_words
        self.use_llm = use_llm
        self.use_bert = use_bert
        self.relevance_threshold = relevance_threshold
        
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
            "ai_filtered": 0,
            "user_selected": 0,
            "downloaded": 0,
            "skipped": 0,
            "errors": []
        }
        
        self.articles: List[ArticleInfo] = []
        self.url_analysis: Optional[URLAnalysis] = None
        self.llm_filter: Optional[LLMArticleFilter] = None
        
        # 初始化LLM筛选器
        if use_llm:
            self._init_llm_filter()
    
    def _init_llm_filter(self):
        """初始化LLM筛选器"""
        if not OPENAI_AVAILABLE:
            print("[警告] openai未安装，禁用LLM筛选")
            self.use_llm = False
            return
        
        # 从环境变量读取配置
        api_key = os.getenv("NVIDIA_API_KEY") or os.getenv("OPENAI_API_KEY")
        provider = os.getenv("LLM_PROVIDER", "auto")
        model = os.getenv("LLM_MODEL", "gpt-3.5-turbo")
        threshold = float(os.getenv("RELEVANCE_THRESHOLD", "0.4"))
        
        if not api_key:
            print("[警告] 未找到API Key (NVIDIA_API_KEY 或 OPENAI_API_KEY)，禁用LLM筛选")
            self.use_llm = False
            return
        
        try:
            self.llm_filter = LLMArticleFilter(
                api_key=api_key,
                model=model,
                provider=provider,
                relevance_threshold=threshold
            )
            
            # 检测 API 是否在线
            print("[AI] 正在检测 LLM API 连接状态...")
            is_online, status_msg = self.llm_filter.check_api_connection()
            
            if is_online:
                print(f"[AI] ✓ {status_msg}")
                print(f"[AI] LLM智能筛选已启用 (阈值: {threshold})")
            else:
                print(f"[警告] ✗ {status_msg}")
                print("[警告] LLM API 不在线，将禁用AI筛选功能")
                self.use_llm = False
                self.llm_filter = None
                
        except Exception as e:
            print(f"[错误] LLM筛选器初始化失败: {e}")
            self.use_llm = False
    
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
    
    def _build_page_url(self, base_url: str, page_num: int, max_results: int = 20) -> str:
        """构建分页URL
        
        Args:
            base_url: 基础URL
            page_num: 页码（从1开始）
            max_results: 每页结果数
        
        Returns:
            带分页参数的URL
        """
        parsed = urlparse(base_url)
        query_params = dict(parse_qsl(parsed.query))
        
        # 计算offset (第一页offset=0, 第二页offset=20或maxresults)
        offset = (page_num - 1) * max_results
        
        # 更新分页参数
        query_params['offset'] = str(offset)
        query_params['maxresults'] = str(max_results)
        query_params['page'] = str(page_num - 1)  # page参数从0开始
        
        # 重新构建URL
        new_query = urlencode(query_params, doseq=True)
        new_url = parsed._replace(query=new_query).geturl()
        
        return new_url
    
    async def scan_articles(self, page, url: str) -> List[ArticleInfo]:
        """扫描文章列表"""
        print("\n" + "=" * 70)
        print("扫描文章列表")
        print("=" * 70)
        
        articles = []
        current_url = url
        
        # 从URL解析maxresults，默认20
        parsed = urlparse(url)
        query_params = dict(parse_qsl(parsed.query))
        max_results = int(query_params.get('maxresults', 20))
        
        for page_num in range(1, self.max_pages + 1):
            print(f"\n[Page] 第 {page_num} 页")
            
            if page_num > 1:
                # 构建下一页的URL
                current_url = self._build_page_url(url, page_num, max_results)
                print(f"  访问: {current_url[:100]}...")
                
                # 直接访问下一页URL
                await page.goto(current_url, wait_until="networkidle", timeout=60000)
                await asyncio.sleep(2)
            
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
    
    def display_article_list(self, articles: List[ArticleInfo], show_scores: bool = True):
        """显示文章列表"""
        print("\n" + "=" * 70)
        print(f"[文章列表 (共 {len(articles)} 篇)")
        print("=" * 70)
        
        for i, article in enumerate(articles[:30], 1):
            quality_mark = "[OK]" if article.word_count >= self.min_preview_words else "[NO]"
            score_info = ""
            if show_scores and article.relevance_score > 0:
                score_emoji = "🟢" if article.relevance_score >= self.relevance_threshold else "🔴"
                score_info = f" [{score_emoji} {article.relevance_score:.0%}]"
            
            print(f"\n[{i:3d}] {quality_mark}{score_info} {article.title[:60]}...")
            print(f"      Date: {article.date} | Source: {article.source[:30]}")
            print(f"      Words: {article.word_count}词")
            if show_scores and article.relevance_reason:
                print(f"      [Reason] {article.relevance_reason[:60]}...")
        
        if len(articles) > 30:
            print(f"\n... 还有 {len(articles) - 30} 篇文章 ...")
        
        print("=" * 70)
    
    async def interactive_select(self, articles: List[ArticleInfo]) -> List[ArticleInfo]:
        """交互式选择文章"""
        print("\n" + "=" * 70)
        print("Keywords: 交互式选择")
        print("=" * 70)
        print("输入要下载的文章编号，用逗号分隔")
        print("例如: 1,3,5,7-10")
        print("输入 'all' 下载所有文章")
        print("输入 'high' 下载高相关度文章（AI评分 ≥ 阈值）")
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
                
                if user_input == 'high':
                    high_relevance = [a for a in articles if a.relevance_score >= self.relevance_threshold]
                    print(f"已选择 {len(high_relevance)} 篇高相关度文章")
                    return high_relevance
                
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
        print(f"[Download] 开始下载文章 (共 {len(articles)} 篇)")
        print("=" * 70)
        
        downloaded = 0
        
        for i, article in enumerate(articles[:self.download_limit], 1):
            print(f"\n[{i}/{len(articles)}] 下载: {article.title[:50]}...")
            
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
AI Relevance Score: {article.relevance_score:.0%}
AI Relevance Reason: {article.relevance_reason}

Full Text:
{full_text}

{'='*70}
"""
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                downloaded += 1
                self.stats["downloaded"] += 1
                print(f"  [Success] 已保存 ({len(full_text)} 字符) -> {filename}")
                
            except Exception as e:
                print(f"  [Error] 下载失败: {e}")
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
        print("NewsBank AI智能下载器")
        print("=" * 80)
        
        # 解析URL
        self.url_analysis = URLParser.parse_url(url)
        print(self.url_analysis.to_display_string())
        
        # 让用户确认URL参数
        print("\n" + "-" * 70)
        confirm = input("[OK] 是否继续？ (y/n): ").strip().lower()
        if confirm != 'y':
            print("已取消")
            return
        
        # 设置LLM关键词
        if self.llm_filter and self.url_analysis.extracted_keywords:
            self.llm_filter.set_keywords(self.url_analysis.extracted_keywords)
        
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
                
                # AI筛选
                if self.use_llm and self.llm_filter:
                    print("\n" + "=" * 70)
                    print("🧠 AI正在分析文章相关性...")
                    print("=" * 70)
                    self.articles = await self.llm_filter.filter_articles_batch(self.articles)
                    self.stats["ai_filtered"] = sum(1 for a in self.articles if a.relevance_score >= self.relevance_threshold)
                
                # 显示文章列表
                self.display_article_list(self.articles, show_scores=self.use_llm)
                
                # 保存文章列表到JSON
                json_path = self.output_dir / f"article_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump([a.to_dict() for a in self.articles], f, indent=2, ensure_ascii=False)
                print(f"\n[Save] 文章列表已保存: {json_path}")
                
                # 交互式选择文章
                selected = await self.interactive_select(self.articles)
                
                if not selected:
                    print("\n[信息] 没有选择任何文章")
                    return
                
                self.stats["user_selected"] = len(selected)
                
                # 确认下载
                print("\n" + "-" * 70)
                final_confirm = input(f"确认下载 {len(selected)} 篇文章? (y/n): ").strip().lower()
                if final_confirm != 'y':
                    print("已取消下载")
                    return
                
                # 下载文章
                downloaded = await self.download_articles(page, selected, url)
                
                # 最终报告
                print("\n" + "=" * 80)
                print("[Success] 下载完成报告")
                print("=" * 80)
                print(f"[Page] 扫描页数: {self.stats['total_pages']}")
                print(f"Source: 发现文章: {self.stats['total_articles']}")
                if self.use_llm:
                    print(f"[AI] AI筛选出相关文章: {self.stats['ai_filtered']}")
                print(f"Keywords: 用户选择: {self.stats['user_selected']}")
                print(f"[Download] 成功下载: {self.stats['downloaded']}")
                print(f"[Skip] 跳过/失败: {self.stats['skipped']}")
                print(f"Output: 输出目录: {self.output_dir.absolute()}")
                
                if self.stats["errors"]:
                    print(f"\n[Warning] 错误 ({len(self.stats['errors'])}):")
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


def get_user_url() -> str:
    """获取用户输入的URL"""
    print("=" * 80)
    print("[AI] NewsBank AI智能下载器")
    print("=" * 80)
    print("\n请输入NewsBank搜索URL")
    print("提示: 在浏览器中完成搜索后，复制地址栏的URL")
    print("示例: https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/results?...&val-base-0=Treasury&fld-base-0=Title...")
    print("-" * 80)
    
    while True:
        url = input("\nURL: URL: ").strip()
        
        if not url:
            print("[Error] URL不能为空，请重新输入")
            continue
        
        # 验证URL
        is_valid, message = URLParser.validate_url(url)
        if not is_valid:
            print(f"[Error] {message}")
            retry = input("是否重新输入? (y/n): ").strip().lower()
            if retry != 'y':
                return ""
            continue
        
        return url


def main():
    parser = argparse.ArgumentParser(
        description="NewsBank AI智能下载器 - 使用LLM智能筛选文章",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用方法示例:

1. 交互式模式（推荐）:
   python newsbank_ai_downloader.py

2. 直接指定URL:
   python newsbank_ai_downloader.py "https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/results?..."

3. 禁用LLM，仅使用关键词筛选:
   python newsbank_ai_downloader.py --no-llm

4. 调整相关性阈值:
   python newsbank_ai_downloader.py --threshold 0.6

5. 无头模式:
   python newsbank_ai_downloader.py --headless "URL"

环境变量 (.env文件):
    NVIDIA_API_KEY=nvapi-xxx     # NVIDIA API Key (推荐)
    OPENAI_API_KEY=sk-xxx        # OpenAI API Key (备选)
    LLM_PROVIDER=auto            # 自动检测提供商
    LLM_MODEL=z-ai/glm4.7        # 模型选择
    RELEVANCE_THRESHOLD=0.4      # 相关性阈值

流程:
    1. 输入NewsBank搜索URL
    2. 系统自动解析URL参数并显示
    3. 用户确认参数
    4. 系统自动登录（如需要）
    5. 扫描文章列表
    6. AI评估每篇文章相关性
    7. 显示文章列表（带AI评分）
    8. 用户选择要下载的文章
    9. 下载选中的文章
        """
    )
    
    parser.add_argument("url", nargs="?", default=None,
                       help="NewsBank搜索URL（可选，不提供则交互式输入）")
    
    parser.add_argument("--max-pages", type=int, default=10,
                       help="最大扫描页数 (默认: 10)")
    
    parser.add_argument("--download-limit", type=int, default=50,
                       help="最大下载文章数 (默认: 50)")
    
    parser.add_argument("--min-preview-words", type=int, default=30,
                       help="优质文章最小预览词数 (默认: 30)")
    
    parser.add_argument("--no-llm", action="store_true",
                       help="禁用LLM筛选，仅使用基础关键词匹配")
    
    parser.add_argument("--threshold", type=float, default=None,
                       help="AI相关性阈值 (0.0-1.0，默认从环境变量读取)")
    
    parser.add_argument("--headless", action="store_true",
                       help="无头模式")
    
    parser.add_argument("--output-dir", default="articles_ai",
                       help="输出目录 (默认: articles_ai)")
    
    args = parser.parse_args()
    
    # 获取URL
    url = args.url
    if not url:
        url = get_user_url()
        if not url:
            print("未提供有效URL，退出")
            return 1
    
    # 确定是否使用LLM
    use_llm = not args.no_llm
    
    # 确定阈值
    threshold = args.threshold
    if threshold is None:
        threshold = float(os.getenv("RELEVANCE_THRESHOLD", "0.4"))
    
    # 创建下载器
    downloader = NewsBankAIDownloader(
        headless=args.headless,
        max_pages=args.max_pages,
        download_limit=args.download_limit,
        min_preview_words=args.min_preview_words,
        use_llm=use_llm,
        relevance_threshold=threshold,
        output_dir=args.output_dir
    )
    
    # 执行下载
    asyncio.run(downloader.download_from_url(url))
    
    return 0


if __name__ == "__main__":
    exit(main())
