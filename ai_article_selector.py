# -*- coding: utf-8 -*-
"""
AI智能文章筛选模块
基于关键词匹配、BERT语义相似度和LLM判断的混合筛选系统

功能：
1. 关键词匹配筛选（基础层）
2. BERT语义相似度筛选（语义层）
3. LLM智能判断（AI层，可选）
4. 混合评分排序

专为Treasury Wine等特定主题优化

作者: AI Assistant
日期: 2026-02-15
"""

from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
import re
import numpy as np
from difflib import SequenceMatcher

# 尝试导入BERT
try:
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity
    BERT_AVAILABLE = True
except ImportError:
    BERT_AVAILABLE = False

# 尝试导入OpenAI
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# NVIDIA API配置
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"


@dataclass
class ArticleRelevance:
    """文章相关性评分"""
    article_id: str
    title: str
    keyword_score: float = 0.0      # 关键词匹配分数
    semantic_score: float = 0.0     # 语义相似度分数
    llm_score: float = 0.0          # LLM判断分数
    combined_score: float = 0.0     # 综合分数
    is_relevant: bool = False       # 是否相关
    reason: str = ""                # 判断理由


class KeywordMatcher:
    """关键词匹配筛选器"""
    
    def __init__(self, target_keywords: List[str]):
        """
        初始化关键词匹配器
        
        Args:
            target_keywords: 目标关键词列表
        """
        self.target_keywords = [kw.lower() for kw in target_keywords]
        
        # 扩展同义词和变体
        self.keyword_expansions = self._build_expansions()
    
    def _build_expansions(self) -> Dict[str, List[str]]:
        """构建关键词扩展（同义词、缩写等）"""
        expansions = {}
        
        for keyword in self.target_keywords:
            expansions[keyword] = [keyword]
            
            # Treasury Wine相关扩展
            if 'treasury' in keyword and 'wine' in keyword:
                expansions[keyword].extend([
                    'twe', 'treasury wine estates', 'treasury wines',
                    'penfolds', 'wolf blass', 'wynns', 'lindeman',
                    'australian wine', 'wine industry'
                ])
            
            # Penfolds相关扩展
            if 'penfolds' in keyword or 'penfold' in keyword:
                expansions[keyword].extend([
                    'penfold', "penfold's", 'grange', 'bin 389',
                    'bin 407', 'kalimna', 'shiraz', 'treasury'
                ])
            
            # 商业术语扩展
            if any(term in keyword for term in ['acquisition', 'merger', 'takeover']):
                expansions[keyword].extend([
                    'acquire', 'purchase', 'buyout', 'deal',
                    'investment', 'consolidation'
                ])
        
        return expansions
    
    def calculate_relevance(self, title: str, preview: str = "") -> Tuple[float, str]:
        """
        计算关键词匹配分数
        
        Returns:
            (分数, 匹配到的关键词)
        """
        text = (title + " " + preview).lower()
        total_score = 0.0
        matched_keywords = []
        
        for keyword in self.target_keywords:
            expansions = self.keyword_expansions.get(keyword, [keyword])
            keyword_max_score = 0.0
            
            for expansion in expansions:
                # 精确匹配（标题中权重更高）
                if expansion in title.lower():
                    score = 1.0
                    if expansion == keyword:  # 原始关键词额外加分
                        score += 0.5
                    keyword_max_score = max(keyword_max_score, score)
                    matched_keywords.append(expansion)
                
                # 部分匹配
                elif expansion in text:
                    score = 0.5
                    keyword_max_score = max(keyword_max_score, score)
                    matched_keywords.append(expansion)
                
                # 字符串相似度（处理拼写变体）
                else:
                    similarity = SequenceMatcher(None, expansion, text).ratio()
                    if similarity > 0.6:
                        keyword_max_score = max(keyword_max_score, similarity * 0.3)
            
            total_score += keyword_max_score
        
        # 归一化分数（0-1）
        final_score = min(1.0, total_score / max(1, len(self.target_keywords)))
        
        return final_score, ", ".join(set(matched_keywords[:5]))


class SemanticRelevanceChecker:
    """BERT语义相关性检查器"""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """初始化BERT模型"""
        if not BERT_AVAILABLE:
            raise ImportError("sentence-transformers未安装，无法使用BERT功能")
        
        self.model = SentenceTransformer(model_name)
        self.target_embeddings = {}
    
    def set_target(self, target_description: str):
        """设置目标主题描述"""
        self.target_description = target_description
        self.target_embedding = self.model.encode([target_description])[0]
    
    def calculate_similarity(self, article_text: str) -> float:
        """
        计算文章与目标的语义相似度
        
        Returns:
            相似度分数 (0-1)
        """
        if not hasattr(self, 'target_embedding'):
            return 0.0
        
        article_embedding = self.model.encode([article_text])[0]
        similarity = cosine_similarity(
            [self.target_embedding], 
            [article_embedding]
        )[0][0]
        
        return float(similarity)


class LLMRelevanceChecker:
    """LLM智能相关性判断器 - 支持OpenAI和NVIDIA API"""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-3.5-turbo", 
                 base_url: Optional[str] = None, provider: str = "auto"):
        """
        初始化LLM检查器
        
        Args:
            api_key: API Key (OpenAI或NVIDIA)
            model: 使用的模型名称
            base_url: API基础URL (NVIDIA需要)
            provider: API提供商 ("openai", "nvidia", "auto")
        """
        if not OPENAI_AVAILABLE:
            raise ImportError("openai未安装，无法使用LLM功能。运行: pip install openai")
        
        self.provider = self._detect_provider(api_key, base_url, provider)
        self.client = self._initialize_client(api_key, base_url)
        self.model = self._get_model_name(model)
        self.target_topic = ""
        
        print(f"[LLM] 使用{self.provider.upper()} API, 模型: {self.model}")
    
    def _detect_provider(self, api_key: Optional[str], base_url: Optional[str], 
                        provider: str) -> str:
        """自动检测API提供商"""
        if provider != "auto":
            return provider
        
        # 如果base_url包含nvidia，使用NVIDIA
        if base_url and "nvidia" in base_url.lower():
            return "nvidia"
        
        # 如果api_key以nvapi开头，使用NVIDIA
        if api_key and api_key.startswith("nvapi-"):
            return "nvidia"
        
        # 默认使用OpenAI
        return "openai"
    
    def _initialize_client(self, api_key: Optional[str], base_url: Optional[str]):
        """初始化API客户端"""
        if self.provider == "nvidia":
            # NVIDIA API配置
            return openai.OpenAI(
                api_key=api_key,
                base_url=base_url or NVIDIA_BASE_URL
            )
        else:
            # OpenAI API配置
            return openai.OpenAI(api_key=api_key)
    
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
    
    def set_target_topic(self, topic: str, context: str = ""):
        """设置目标主题"""
        self.target_topic = topic
        self.context = context
    
    def check_relevance(self, title: str, preview: str = "") -> Tuple[float, str]:
        """
        使用LLM判断文章相关性
        
        Returns:
            (相关性分数, 判断理由)
        """
        if not self.target_topic:
            return 0.0, "未设置目标主题"
        
        prompt = f"""请判断以下文章是否与主题"{self.target_topic}"相关。

主题背景：{self.context}

文章信息：
标题：{title}
预览：{preview[:500]}

请按以下格式回复：
相关性分数：0-100的数字（0=完全无关，100=高度相关）
判断理由：简要说明为什么相关或不相关

回复："""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a professional article relevance assessment assistant. Analyze the relevance of news articles to specific topics."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=200
            )
            
            content = response.choices[0].message.content
            
            # 解析分数
            score_match = re.search(r'(\d+)', content)
            if score_match:
                score = int(score_match.group(1)) / 100.0
            else:
                score = 0.5
            
            # 解析理由
            reason_match = re.search(r'判断理由[：:]\s*(.+)', content, re.DOTALL)
            if reason_match:
                reason = reason_match.group(1).strip()
            else:
                reason = content[:200]
            
            return score, reason
            
        except Exception as e:
            return 0.0, f"LLM判断失败: {str(e)}"


class AIArticleSelector:
    """AI智能文章选择器（混合策略）"""
    
    def __init__(self, 
                 target_keywords: List[str],
                 use_bert: bool = False,
                 use_llm: bool = False,
                 openai_api_key: Optional[str] = None,
                 llm_base_url: Optional[str] = None,
                 llm_provider: str = "auto",
                 llm_model: str = "gpt-3.5-turbo",
                 relevance_threshold: float = 0.5):
        """
        初始化AI文章选择器
        
        Args:
            target_keywords: 目标关键词
            use_bert: 是否使用BERT
            use_llm: 是否使用LLM
            openai_api_key: OpenAI/NVIDIA API Key
            llm_base_url: LLM API基础URL (NVIDIA需要)
            llm_provider: LLM提供商 ("openai", "nvidia", "auto")
            llm_model: LLM模型名称
            relevance_threshold: 相关性阈值
        """
        self.target_keywords = target_keywords
        self.relevance_threshold = relevance_threshold
        
        # 初始化各层筛选器
        self.keyword_matcher = KeywordMatcher(target_keywords)
        
        self.bert_checker = None
        if use_bert and BERT_AVAILABLE:
            try:
                self.bert_checker = SemanticRelevanceChecker()
                target_desc = f"Articles about {', '.join(target_keywords)}"
                self.bert_checker.set_target(target_desc)
                print(f"[AI] BERT语义筛选已启用")
            except Exception as e:
                print(f"[AI] BERT初始化失败: {e}")
        
        self.llm_checker = None
        if use_llm and OPENAI_AVAILABLE and openai_api_key:
            try:
                self.llm_checker = LLMRelevanceChecker(
                    api_key=openai_api_key,
                    model=llm_model,
                    base_url=llm_base_url,
                    provider=llm_provider
                )
                context = f"Focus on news articles about {', '.join(target_keywords)}"
                self.llm_checker.set_target_topic(
                    ', '.join(target_keywords),
                    context
                )
                print(f"[AI] LLM智能筛选已启用")
            except Exception as e:
                print(f"[AI] LLM初始化失败: {e}")
        
        # 权重配置
        self.weights = {
            'keyword': 0.5,
            'semantic': 0.3 if self.bert_checker else 0.0,
            'llm': 0.2 if self.llm_checker else 0.0
        }
        
        # 重新归一化权重
        total = sum(self.weights.values())
        if total > 0:
            self.weights = {k: v/total for k, v in self.weights.items()}
    
    def evaluate_article(self, article: Dict[str, Any]) -> ArticleRelevance:
        """
        评估单篇文章的相关性
        
        Args:
            article: 文章字典，包含title, preview等字段
        
        Returns:
            ArticleRelevance对象
        """
        title = article.get('title', '')
        preview = article.get('preview', '')
        article_id = article.get('article_id', '')
        
        result = ArticleRelevance(
            article_id=article_id,
            title=title
        )
        
        # 1. 关键词匹配
        keyword_score, matched_kw = self.keyword_matcher.calculate_relevance(title, preview)
        result.keyword_score = keyword_score
        result.reason = f"关键词匹配: {matched_kw}"
        
        # 2. BERT语义相似度
        if self.bert_checker:
            combined_text = f"{title}. {preview}"
            semantic_score = self.bert_checker.calculate_similarity(combined_text)
            result.semantic_score = semantic_score
        
        # 3. LLM判断
        if self.llm_checker:
            llm_score, llm_reason = self.llm_checker.check_relevance(title, preview)
            result.llm_score = llm_score
            result.reason += f" | LLM: {llm_reason}"
        
        # 4. 计算综合分数
        result.combined_score = (
            result.keyword_score * self.weights.get('keyword', 0.5) +
            result.semantic_score * self.weights.get('semantic', 0.0) +
            result.llm_score * self.weights.get('llm', 0.0)
        )
        
        # 5. 判断是否相关
        result.is_relevant = result.combined_score >= self.relevance_threshold
        
        return result
    
    def select_articles(self, articles: List[Dict[str, Any]], 
                       top_k: Optional[int] = None) -> Tuple[List[Dict], List[ArticleRelevance]]:
        """
        从文章列表中选择相关文章
        
        Args:
            articles: 文章列表
            top_k: 最多选择多少篇（None表示全部符合条件的）
        
        Returns:
            (选中的文章列表, 所有评估结果)
        """
        print(f"\n[AI筛选] 正在评估 {len(articles)} 篇文章...")
        print(f"[AI] 目标关键词: {', '.join(self.target_keywords)}")
        print(f"[AI] 相关性阈值: {self.relevance_threshold}")
        
        # 评估所有文章
        evaluations = []
        for article in articles:
            eval_result = self.evaluate_article(article)
            evaluations.append(eval_result)
        
        # 按综合分数排序
        evaluations.sort(key=lambda x: x.combined_score, reverse=True)
        
        # 选择相关文章
        selected = []
        selected_evaluations = []
        
        for eval_result in evaluations:
            if eval_result.is_relevant:
                # 找到对应的文章
                article = next(
                    (a for a in articles if a.get('article_id') == eval_result.article_id),
                    None
                )
                if article:
                    selected.append(article)
                    selected_evaluations.append(eval_result)
                    
                    if top_k and len(selected) >= top_k:
                        break
        
        # 显示结果
        print(f"\n[AI筛选结果]")
        print("-" * 60)
        print(f"总文章数: {len(articles)}")
        print(f"相关文章: {len(selected)}")
        print(f"筛选比例: {len(selected)/len(articles)*100:.1f}%")
        print("\nTop 5 最相关文章:")
        for i, eval_result in enumerate(evaluations[:5], 1):
            status = "✓" if eval_result.is_relevant else "✗"
            print(f"  {status} [{i}] {eval_result.title[:50]}... (分数: {eval_result.combined_score:.3f})")
        
        return selected, evaluations
    
    def get_selection_summary(self) -> str:
        """获取选择器配置摘要"""
        lines = [
            "AI文章选择器配置",
            "=" * 60,
            f"目标关键词: {', '.join(self.target_keywords)}",
            f"相关性阈值: {self.relevance_threshold}",
            "",
            "筛选策略权重:",
            f"  关键词匹配: {self.weights.get('keyword', 0):.0%}",
        ]
        
        if self.bert_checker:
            lines.append(f"  BERT语义: {self.weights.get('semantic', 0):.0%}")
        
        if self.llm_checker:
            lines.append(f"  LLM判断: {self.weights.get('llm', 0):.0%}")
        
        lines.append("=" * 60)
        
        return "\n".join(lines)


# 便捷函数
def create_treasury_wine_selector(
    use_bert: bool = False,
    use_llm: bool = False,
    openai_api_key: Optional[str] = None,
    llm_base_url: Optional[str] = None,
    llm_provider: str = "auto",
    llm_model: str = "gpt-3.5-turbo",
    threshold: float = 0.4
) -> AIArticleSelector:
    """
    创建专门用于Treasury Wine的AI选择器
    
    Args:
        use_bert: 是否使用BERT
        use_llm: 是否使用LLM
        openai_api_key: OpenAI/NVIDIA API Key
        llm_base_url: LLM API基础URL
        llm_provider: LLM提供商 ("openai", "nvidia", "auto")
        llm_model: LLM模型名称
        threshold: 相关性阈值
        use_llm: 是否使用LLM
        openai_api_key: OpenAI API Key
        threshold: 相关性阈值
    
    Returns:
        配置好的AIArticleSelector
    """
    keywords = [
        "treasury wine",
        "treasury wine estates",
        "twe",
        "penfolds",
        "penfold",
        "wolf blass",
        "wynns",
        "lindeman",
        "australian wine",
        "wine industry"
    ]
    
    return AIArticleSelector(
        target_keywords=keywords,
        use_bert=use_bert,
        use_llm=use_llm,
        openai_api_key=openai_api_key,
        relevance_threshold=threshold
    )


# 测试代码
if __name__ == "__main__":
    print("=" * 80)
    print("AI智能文章筛选模块 - 测试")
    print("=" * 80)
    
    # 测试文章列表
    test_articles = [
        {
            "article_id": "1",
            "title": "Treasury Wine Estates profit rises 15%",
            "preview": "Treasury Wine Estates has reported a 15% increase in profit for the fiscal year...",
        },
        {
            "article_id": "2",
            "title": "Penfolds launches new Grange vintage",
            "preview": "Penfolds, owned by Treasury Wine Estates, has released its latest Grange vintage...",
        },
        {
            "article_id": "3",
            "title": "Nick Scali furniture profit falls",
            "preview": "Nick Scali has reported a decline in profits this quarter...",
        },
        {
            "article_id": "4",
            "title": "ASX ends week lower on mining losses",
            "preview": "The Australian stock market closed lower this week...",
        },
        {
            "article_id": "5",
            "title": "Wolf Blass expands into Asian markets",
            "preview": "Wolf Blass, a subsidiary of Treasury Wine Estates, is expanding its presence...",
        },
    ]
    
    print("\n测试文章列表:")
    for i, article in enumerate(test_articles, 1):
        print(f"[{i}] {article['title']}")
    
    # 创建Treasury Wine选择器
    print("\n" + "=" * 80)
    print("创建Treasury Wine专用AI选择器")
    print("=" * 80)
    
    selector = create_treasury_wine_selector(
        use_bert=False,  # 基础版本
        use_llm=False,
        threshold=0.3
    )
    
    print(selector.get_selection_summary())
    
    # 执行筛选
    print("\n" + "=" * 80)
    selected, evaluations = selector.select_articles(test_articles)
    
    print("\n最终选择:")
    for article in selected:
        print(f"  ✓ {article['title']}")
    
    print("\n" + "=" * 80)
    print("测试完成!")
    print("=" * 80)
