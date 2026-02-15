# -*- coding: utf-8 -*-
"""
BERT-enhanced Semantic Search Integration
BERT增强语义搜索完整集成模块

功能：
1. 结合BERT语义理解和传统规则
2. 领域特定的词库（酒业）
3. 支持多种BERT模型选择
4. 可配置的混合策略

依赖：
    pip install sentence-transformers numpy scikit-learn

使用方法：
    python newsbank_bert_search.py "treasury wine" --mode moderate
    python newsbank_bert_search.py "penfolds" --bert-model fast --top-k 5

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
from urllib.parse import quote, urljoin

from playwright.async_api import async_playwright

# 导入搜索构建器
try:
    from newsbank_search_builder import (
        AdvancedSearchQuery, SearchField, BooleanOperator,
        SearchTemplates, SemanticSearchQuery,
        create_optimized_search, create_semantic_search,
        SEMANTIC_AVAILABLE
    )
except ImportError as e:
    print(f"[错误] 缺少依赖: {e}")
    exit(1)

# 尝试导入BERT扩展器
try:
    from bert_semantic_expansion import (
        DomainBertExpander, HybridSemanticExpander,
        BertSemanticExpander, BERT_AVAILABLE,
        bert_expand_keywords, compare_expansion_methods
    )
    print(f"[BERT] BERT模块已加载，可用: {BERT_AVAILABLE}")
except ImportError as e:
    print(f"[警告] BERT模块导入失败: {e}")
    BERT_AVAILABLE = False


class NewsBankBertScraper:
    """
    BERT增强的语义搜索爬虫
    """
    
    def __init__(self,
                 headless: bool = False,
                 max_pages: int = 10,
                 min_preview_words: int = 30,
                 max_full_articles: int = 50,
                 semantic_mode: str = "moderate",
                 use_bert: bool = True,
                 bert_model: str = "fast",
                 top_k_expansions: int = 5,
                 hybrid_mix: float = 0.7):
        """
        初始化BERT爬虫
        
        Args:
            headless: 是否无头模式
            max_pages: 最大页数
            min_preview_words: 最小预览词数
            max_full_articles: 最大下载文章数
            semantic_mode: 语义扩展模式
            use_bert: 是否使用BERT
            bert_model: BERT模型 (fast/balanced/accurate)
            top_k_expansions: 扩展词数量
            hybrid_mix: BERT权重 (0-1)
        """
        self.headless = headless
        self.max_pages = max_pages
        self.min_preview_words = min_preview_words
        self.max_full_articles = max_full_articles
        self.semantic_mode = semantic_mode
        self.use_bert = use_bert and BERT_AVAILABLE
        self.bert_model = bert_model
        self.top_k_expansions = top_k_expansions
        self.hybrid_mix = hybrid_mix
        
        # 路径设置
        self.cookie_file = Path("cookies/newsbank_auth.json")
        self.output_dir = Path("articles_bert")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cookie_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 反检测
        self.min_delay = 2
        self.max_delay = 5
        self.last_request_time = 0
        
        # 统计
        self.stats = {
            "total_pages": 0,
            "total_previewed": 0,
            "quality_articles": 0,
            "downloaded_full": 0,
            "skipped_low_quality": 0,
        }
        
        # 初始化扩展器
        self._init_expander()
        
        self.expansion_info: Dict[str, Any] = {}
    
    def _init_expander(self):
        """初始化语义扩展器"""
        self.expander = None
        
        if self.use_bert:
            try:
                # 映射模型选择
                model_map = {
                    "fast": "all-MiniLM-L6-v2",
                    "balanced": "all-mpnet-base-v2",
                    "accurate": "all-roberta-large-v1"
                }
                model_name = model_map.get(self.bert_model, "all-MiniLM-L6-v2")
                
                print(f"[BERT] 初始化BERT扩展器 (模型: {model_name})...")
                
                # 使用混合扩展器
                self.expander = HybridSemanticExpander(
                    use_bert=True,
                    bert_model=model_name
                )
                
                print("[BERT] BERT扩展器初始化成功")
                
            except Exception as e:
                print(f"[BERT] BERT初始化失败: {e}")
                print("[BERT] 回退到传统语义扩展")
                self.use_bert = False
                self._init_rule_expander()
        else:
            self._init_rule_expander()
    
    def _init_rule_expander(self):
        """初始化传统规则扩展器"""
        try:
            from semantic_expansion import SemanticExpander
            self.expander = SemanticExpander()
            print("[BERT] 传统语义扩展器初始化成功")
        except ImportError:
            print("[BERT] 语义扩展器不可用")
            self.expander = None
    
    def build_bert_search_query(self, keyword: str) -> Tuple[AdvancedSearchQuery, Dict]:
        """
        构建BERT增强的搜索查询
        
        Returns:
            (查询对象, 扩展信息字典)
        """
        print("\n" + "=" * 70)
        print("[BERT语义扩展]")
        print("=" * 70)
        
        expansion_info = {
            "original_keyword": keyword,
            "use_bert": self.use_bert,
            "mode": self.semantic_mode,
            "expansions": [],
            "expansion_time": 0
        }
        
        if not self.expander:
            # 无扩展器，使用原始关键词
            print("[BERT] 语义扩展器不可用，使用原始关键词")
            query = AdvancedSearchQuery()
            query.add_condition(keyword, SearchField.ALL_TEXT)
            return query, expansion_info
        
        # 执行语义扩展
        start_time = time.time()
        
        try:
            if isinstance(self.expander, HybridSemanticExpander):
                # 混合扩展器
                print(f"[BERT] 使用混合扩展 (BERT权重: {self.hybrid_mix})")
                expansions = self.expander.expand(
                    keyword, 
                    mode=self.semantic_mode,
                    top_k=self.top_k_expansions
                )
            else:
                # 传统扩展器
                print("[BERT] 使用传统规则扩展")
                expansions = self.expander.expand_term(
                    keyword, 
                    mode=self.semantic_mode
                )
                # 限制数量
                expansions = expansions[:self.top_k_expansions]
            
            expansion_time = time.time() - start_time
            expansion_info["expansion_time"] = expansion_time
            expansion_info["expansions"] = expansions
            
            print(f"[BERT] 扩展耗时: {expansion_time:.2f}秒")
            print(f"[BERT] 找到 {len(expansions)} 个相关词:")
            for term, score in expansions:
                print(f"  - {term} (相关度: {score:.3f})")
            
            # 构建搜索查询
            query = AdvancedSearchQuery()
            
            # 构建OR表达式（原始词 + 扩展词）
            all_terms = [keyword]
            for term, score in expansions:
                if term.lower() not in [t.lower() for t in all_terms]:
                    all_terms.append(term)
            
            # 构建布尔表达式
            or_terms = []
            for term in all_terms[:self.top_k_expansions + 1]:  # +1 包含原始词
                if ' ' in term:
                    or_terms.append(f'"{term}"')
                else:
                    or_terms.append(term)
            
            title_expr = " OR ".join(or_terms)
            
            # 标题字段搜索（使用语义扩展词）
            query.add_condition(title_expr, SearchField.TITLE)
            
            # 全文搜索（原始关键词）
            query.add_condition(keyword, SearchField.ALL_TEXT, BooleanOperator.AND)
            
            return query, expansion_info
            
        except Exception as e:
            print(f"[BERT] 扩展失败: {e}")
            # 回退到原始关键词
            query = AdvancedSearchQuery()
            query.add_condition(keyword, SearchField.ALL_TEXT)
            return query, expansion_info
    
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
    
    async def scrape(self, keyword: str) -> dict:
        """主爬取方法"""
        print("=" * 80)
        print(f"NewsBank BERT语义搜索爬虫")
        print(f"原始关键词: '{keyword}'")
        print(f"BERT增强: {'启用' if self.use_bert else '禁用'}")
        if self.use_bert:
            print(f"BERT模型: {self.bert_model}")
        print("=" * 80)
        
        # 构建BERT增强的搜索查询
        search_query, expansion_info = self.build_bert_search_query(keyword)
        self.expansion_info = expansion_info
        
        print("\n[搜索配置]")
        print(search_query.get_search_summary())
        
        # 构建搜索URL
        search_url = search_query.build_url()
        print(f"\n[搜索URL] 已生成")
        
        # 开始爬取
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
                # 登录检查
                print("\n[登录]")
                print("-" * 40)
                
                if self.cookie_file.exists():
                    test_page = await context.new_page()
                    await test_page.goto(
                        "https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/browse-multi?p=AWGLNB",
                        wait_until="networkidle", timeout=30000
                    )
                    
                    if "infoweb-newsbank" in test_page.url and "login" not in test_page.url:
                        print("[成功] Cookie有效，自动登录")
                        await test_page.close()
                    else:
                        print("[信息] Cookie已过期，需要手动登录")
                        await test_page.close()
                        
                        if not self.headless:
                            await page.goto(
                                "https://eresources.sl.nsw.gov.au/newsbank-including-access-australia",
                                wait_until="networkidle", timeout=60000
                            )
                            
                            start_time = asyncio.get_event_loop().time()
                            while (asyncio.get_event_loop().time() - start_time) < 180:
                                if "infoweb-newsbank-com.ezproxy" in page.url and "login" not in page.url:
                                    break
                                await asyncio.sleep(2)
                        else:
                            print("[错误] 无头模式下无法手动登录")
                            return self.stats
                
                await context.storage_state(path=str(self.cookie_file))
                
                # 访问搜索结果
                print("\n[开始搜索]")
                print("-" * 40)
                
                await page.goto(search_url, wait_until="networkidle", timeout=60000)
                print(f"搜索结果已加载: {(await page.title()).split('|')[0].strip()}")
                
                # 扫描文章（简化版）
                print("\n[扫描文章]")
                print("-" * 40)
                
                for page_num in range(1, self.max_pages + 1):
                    print(f"\n第 {page_num} 页...")
                    
                    articles = await page.query_selector_all('article.search-hits__hit')
                    if not articles:
                        print("  无更多文章")
                        break
                    
                    self.stats["total_pages"] += 1
                    print(f"  找到 {len(articles)} 篇文章")
                    
                    # 简单统计
                    quality_count = 0
                    for article_elem in articles:
                        preview_elem = await article_elem.query_selector("div.preview-first-paragraph")
                        if preview_elem:
                            preview = await preview_elem.inner_text()
                            if len(preview.split()) >= self.min_preview_words:
                                quality_count += 1
                    
                    self.stats["quality_articles"] += quality_count
                    print(f"  优质文章: {quality_count} 篇")
                    
                    # 下一页
                    if page_num < self.max_pages:
                        next_button = await page.query_selector('a:has-text("Next")')
                        if not next_button or await next_button.is_disabled():
                            print("  无下一页")
                            break
                        
                        await next_button.click()
                        await page.wait_for_load_state("networkidle")
                        await asyncio.sleep(1)
                
                # 最终报告
                print("\n" + "=" * 80)
                print("[完成] 扫描完成！")
                print("=" * 80)
                print(f"扫描页数: {self.stats['total_pages']}")
                print(f"优质文章: {self.stats['quality_articles']}")
                if self.use_bert and self.expansion_info.get("expansions"):
                    expansions = self.expansion_info["expansions"]
                    print(f"\nBERT扩展词 ({len(expansions)}个):")
                    for term, score in expansions[:5]:
                        print(f"  - {term} ({score:.3f})")
                print("=" * 80)
                
                if not self.headless:
                    await asyncio.sleep(10)
            
            except Exception as e:
                print(f"\n[错误] {e}")
                import traceback
                traceback.print_exc()
            
            finally:
                await context.close()
                await browser.close()
        
        return self.stats


def main():
    parser = argparse.ArgumentParser(
        description="NewsBank BERT-enhanced Semantic Search",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
BERT语义搜索使用示例:

1. 基础BERT搜索（推荐）:
   python newsbank_bert_search.py "treasury wine"

2. 使用不同BERT模型:
   python newsbank_bert_search.py "treasury wine" --bert-model fast
   python newsbank_bert_search.py "treasury wine" --bert-model balanced
   python newsbank_bert_search.py "treasury wine" --bert-model accurate

3. 调整扩展数量:
   python newsbank_bert_search.py "penfolds" --top-k 3
   python newsbank_bert_search.py "treasury wine" --top-k 8

4. 禁用BERT（仅规则方法）:
   python newsbank_bert_search.py "treasury wine" --no-bert

BERT模型说明:
  - fast: all-MiniLM-L6-v2 (最快，384维，推荐日常使用)
  - balanced: all-mpnet-base-v2 (平衡精度和速度)
  - accurate: all-roberta-large-v1 (最准确但较慢)

扩展模式说明:
  - conservative: 高相似度阈值，结果精确
  - moderate: 平衡模式，推荐日常使用
  - aggressive: 低相似度阈值，结果全面
        """
    )
    
    parser.add_argument("keyword", help="搜索关键词")
    
    # BERT选项
    bert_group = parser.add_argument_group("BERT选项")
    bert_group.add_argument("--bert-model", 
                           choices=["fast", "balanced", "accurate"],
                           default="fast",
                           help="BERT模型选择 (默认: fast)")
    bert_group.add_argument("--no-bert", action="store_true",
                           help="禁用BERT，仅使用规则方法")
    bert_group.add_argument("--top-k", type=int, default=5,
                           help="语义扩展词数量 (默认: 5)")
    bert_group.add_argument("--semantic-mode",
                           choices=["conservative", "moderate", "aggressive"],
                           default="moderate",
                           help="语义扩展模式 (默认: moderate)")
    
    # 爬取选项
    crawl_group = parser.add_argument_group("爬取选项")
    crawl_group.add_argument("--max-pages", type=int, default=5,
                            help="最大扫描页数 (默认: 5)")
    crawl_group.add_argument("--headless", action="store_true",
                            help="无头模式")
    
    # 对比测试模式
    parser.add_argument("--compare", action="store_true",
                       help="对比不同扩展方法的效果（不执行爬取）")
    
    args = parser.parse_args()
    
    # 对比测试模式
    if args.compare:
        print("=" * 80)
        print("BERT vs 规则方法 对比测试")
        print("=" * 80)
        
        if not BERT_AVAILABLE:
            print("\n[错误] BERT不可用，请安装: pip install sentence-transformers")
            return 1
        
        try:
            comparison = compare_expansion_methods(args.keyword)
            
            print(f"\n对比关键词: '{args.keyword}'")
            print("-" * 50)
            
            for method, results in comparison.items():
                print(f"\n{method}:")
                for i, (term, score) in enumerate(results[:5], 1):
                    print(f"  {i}. {term} (相关度: {score:.3f})")
            
            print("\n" + "=" * 80)
        
        except Exception as e:
            print(f"对比测试失败: {e}")
            import traceback
            traceback.print_exc()
        
        return 0
    
    # 创建爬虫
    scraper = NewsBankBertScraper(
        headless=args.headless,
        max_pages=args.max_pages,
        use_bert=not args.no_bert,
        bert_model=args.bert_model,
        semantic_mode=args.semantic_mode,
        top_k_expansions=args.top_k
    )
    
    # 运行爬取
    stats = asyncio.run(scraper.scrape(args.keyword))
    
    return 0 if stats["quality_articles"] > 0 else 1


if __name__ == "__main__":
    exit(main())
