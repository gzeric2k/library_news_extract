# -*- coding: utf-8 -*-
"""
BERT-enhanced Semantic Expansion Module
BERT增强的语义扩展模块

功能：
1. 使用Sentence-BERT计算语义嵌入
2. 基于余弦相似度的语义扩展
3. 与传统规则方法结合
4. 支持领域词向量

依赖安装：
    pip install sentence-transformers numpy scikit-learn

作者: AI Assistant
日期: 2026-02-15
"""

from typing import List, Dict, Set, Optional, Tuple, Union
import numpy as np
from difflib import SequenceMatcher
import re
import warnings

# 尝试导入sentence-transformers
try:
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity
    BERT_AVAILABLE = True
except ImportError:
    BERT_AVAILABLE = False
    warnings.warn("sentence-transformers未安装，BERT功能不可用。运行: pip install sentence-transformers")


class BertSemanticExpander:
    """
    BERT语义扩展器
    
    使用Sentence-BERT模型计算语义相似度
    """
    
    # 推荐的轻量级模型
    DEFAULT_MODEL = "all-MiniLM-L6-v2"  # 384维，速度快
    ALTERNATIVE_MODELS = {
        "fast": "all-MiniLM-L6-v2",      # 最快，适合实时应用
        "balanced": "all-mpnet-base-v2",  # 平衡精度和速度
        "accurate": "all-roberta-large-v1" # 最准确，但较慢
    }
    
    def __init__(self, model_name: str = None, device: str = None, 
                 cache_dir: str = None):
        """
        初始化BERT扩展器
        
        Args:
            model_name: 模型名称，None则使用默认轻量级模型
            device: 计算设备 ('cpu', 'cuda', 'cuda:0'等)
            cache_dir: 模型缓存目录
        """
        if not BERT_AVAILABLE:
            raise ImportError(
                "sentence-transformers未安装。请运行: pip install sentence-transformers"
            )
        
        self.model_name = model_name or self.DEFAULT_MODEL
        self.device = device or ('cuda' if self._check_cuda() else 'cpu')
        
        print(f"[BERT] 正在加载模型: {self.model_name}")
        print(f"[BERT] 使用设备: {self.device}")
        
        try:
            self.model = SentenceTransformer(
                self.model_name,
                device=self.device,
                cache_folder=cache_dir
            )
            self.embedding_dim = self.model.get_sentence_embedding_dimension()
            print(f"[BERT] 模型加载成功，嵌入维度: {self.embedding_dim}")
        except Exception as e:
            print(f"[BERT] 模型加载失败: {e}")
            print(f"[BERT] 尝试使用默认模型...")
            self.model = SentenceTransformer(self.DEFAULT_MODEL, device=self.device)
            self.embedding_dim = self.model.get_sentence_embedding_dimension()
        
        # 缓存已计算的嵌入
        self._embedding_cache: Dict[str, np.ndarray] = {}
        self._cache_hits = 0
        self._cache_misses = 0
    
    def _check_cuda(self) -> bool:
        """检查CUDA是否可用"""
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False
    
    def encode(self, texts: Union[str, List[str]], 
               batch_size: int = 32,
               show_progress: bool = False) -> np.ndarray:
        """
        计算文本嵌入
        
        Args:
            texts: 文本或文本列表
            batch_size: 批处理大小
            show_progress: 是否显示进度条
        
        Returns:
            嵌入向量 (N, embedding_dim)
        """
        if isinstance(texts, str):
            texts = [texts]
        
        # 检查缓存
        uncached_texts = []
        cached_embeddings = []
        
        for text in texts:
            text_lower = text.lower().strip()
            if text_lower in self._embedding_cache:
                cached_embeddings.append(self._embedding_cache[text_lower])
                self._cache_hits += 1
            else:
                uncached_texts.append(text)
                self._cache_misses += 1
        
        if uncached_texts:
            # 计算未缓存的嵌入
            new_embeddings = self.model.encode(
                uncached_texts,
                batch_size=batch_size,
                show_progress_bar=show_progress,
                convert_to_numpy=True
            )
            
            # 存入缓存
            for text, embedding in zip(uncached_texts, new_embeddings):
                self._embedding_cache[text.lower().strip()] = embedding
            
            # 合并结果
            if cached_embeddings:
                all_embeddings = np.vstack([
                    np.array(cached_embeddings),
                    new_embeddings
                ])
            else:
                all_embeddings = new_embeddings
        else:
            all_embeddings = np.array(cached_embeddings)
        
        return all_embeddings
    
    def calculate_similarity(self, text1: str, text2: str) -> float:
        """
        计算两个文本的语义相似度
        
        Args:
            text1: 文本1
            text2: 文本2
        
        Returns:
            相似度分数 (0-1)
        """
        embeddings = self.encode([text1, text2])
        similarity = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
        return float(similarity)
    
    def find_similar_terms(self, query: str, 
                          candidate_terms: List[str],
                          top_k: int = 5,
                          min_similarity: float = 0.5) -> List[Tuple[str, float]]:
        """
        从候选词中找到与查询最相似的词
        
        Args:
            query: 查询词
            candidate_terms: 候选词列表
            top_k: 返回前k个最相似的
            min_similarity: 最小相似度阈值
        
        Returns:
            [(相似词, 相似度), ...]
        """
        if not candidate_terms:
            return []
        
        # 计算所有嵌入
        query_embedding = self.encode([query])
        candidate_embeddings = self.encode(candidate_terms, show_progress=False)
        
        # 计算余弦相似度
        similarities = cosine_similarity(query_embedding, candidate_embeddings)[0]
        
        # 筛选并排序
        results = []
        for term, sim in zip(candidate_terms, similarities):
            if sim >= min_similarity and term.lower() != query.lower():
                results.append((term, float(sim)))
        
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]
    
    def expand_semantically(self, keyword: str,
                           candidate_pool: List[str],
                           top_k: int = 5,
                           min_similarity: float = 0.5,
                           combine_with_rules: bool = True) -> List[Tuple[str, float]]:
        """
        语义扩展主函数
        
        Args:
            keyword: 原始关键词
            candidate_pool: 候选词库
            top_k: 返回数量
            min_similarity: 最小相似度
            combine_with_rules: 是否结合规则方法
        
        Returns:
            扩展词列表 (带相似度)
        """
        # BERT语义扩展
        bert_results = self.find_similar_terms(
            keyword, candidate_pool, top_k=top_k*2, min_similarity=min_similarity
        )
        
        if not combine_with_rules:
            return bert_results[:top_k]
        
        # 结合规则方法（字符串相似度）
        combined_results = []
        seen_terms = set()
        
        # 添加BERT结果
        for term, bert_sim in bert_results:
            term_lower = term.lower()
            if term_lower not in seen_terms:
                # 计算字符串相似度
                string_sim = SequenceMatcher(None, keyword.lower(), term_lower).ratio()
                # 综合评分 (BERT权重更高)
                combined_score = bert_sim * 0.7 + string_sim * 0.3
                combined_results.append((term, combined_score))
                seen_terms.add(term_lower)
        
        # 按综合评分排序
        combined_results.sort(key=lambda x: x[1], reverse=True)
        return combined_results[:top_k]
    
    def get_cache_stats(self) -> Dict[str, int]:
        """获取缓存统计信息"""
        return {
            "cache_size": len(self._embedding_cache),
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "hit_rate": self._cache_hits / (self._cache_hits + self._cache_misses) 
                       if (self._cache_hits + self._cache_misses) > 0 else 0
        }
    
    def clear_cache(self):
        """清除嵌入缓存"""
        self._embedding_cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0


class DomainBertExpander(BertSemanticExpander):
    """
    领域特定的BERT扩展器（酒业/商业新闻）
    
    预置领域词库，提供更精准的扩展
    """
    
    def __init__(self, model_name: str = None, device: str = None):
        super().__init__(model_name, device)
        
        # 领域候选词库
        self.domain_vocabulary = self._build_domain_vocabulary()
        print(f"[BERT-Domain] 领域词库大小: {len(self.domain_vocabulary)}")
        
        # 预计算领域词嵌入（可选，加速后续查询）
        self._precompute_domain_embeddings()
    
    def _build_domain_vocabulary(self) -> List[str]:
        """构建领域词库"""
        vocabulary = set()
        
        # 公司和品牌
        companies_brands = [
            "treasury wine estates", "twe", "penfolds", "penfold", "wolf blass",
            "wynns", "lindeman's", "seppelt", "pepperjack", "19 crimes",
            "daou vineyards", "st hubert's the stag", "squealing pig",
            "blossom hill", "frank family vineyards", "beringer", "etude",
            "sterling vineyards", "beaulieu vineyard", "stags' leap",
            "grange", "bin 389", "bin 407", "bin 28", "kalimna", "st henri"
        ]
        vocabulary.update(companies_brands)
        
        # 葡萄酒类型
        wine_types = [
            "red wine", "white wine", "rose", "sparkling wine", "fortified wine",
            "shiraz", "cabernet sauvignon", "chardonnay", "pinot noir", "merlot",
            "sauvignon blanc", "riesling", "grenache", "malbec", "pinot grigio"
        ]
        vocabulary.update(wine_types)
        
        # 产区
        regions = [
            "australian wine", "south australia", "barossa valley", "mclaren vale",
            "coonawarra", "adelaide hills", "margaret river", "hunter valley",
            "yarra valley", "clare valley"
        ]
        vocabulary.update(regions)
        
        # 商业术语
        business_terms = [
            "acquisition", "merger", "takeover", "investment", "revenue",
            "profit", "earnings", "market share", "growth", "expansion",
            "strategy", "deal", "acquire", "purchase", "buyout",
            "asx", "share price", "annual report", "financial results",
            "dividend", "shareholder", "market cap"
        ]
        vocabulary.update(business_terms)
        
        # 行业术语
        industry_terms = [
            "winemaking", "vineyard", "winery", "cellar door", "vintage",
            "harvest", "fermentation", "aging", "bottling", "wine industry",
            "wine export", "wine market", "premium wine", "luxury wine",
            "icon wine", "fine wine", "reserve wine"
        ]
        vocabulary.update(industry_terms)
        
        return sorted(list(vocabulary))
    
    def _precompute_domain_embeddings(self):
        """预计算领域词嵌入"""
        print("[BERT-Domain] 预计算领域词嵌入...")
        self.encode(self.domain_vocabulary, show_progress=True)
        print("[BERT-Domain] 预计算完成")
    
    def expand(self, keyword: str, top_k: int = 5,
               min_similarity: float = 0.4,
               use_external_candidates: bool = False,
               external_candidates: List[str] = None) -> List[Tuple[str, float]]:
        """
        领域特定的语义扩展
        
        Args:
            keyword: 原始关键词
            top_k: 返回数量
            min_similarity: 最小相似度（比通用方法更低，因为领域词更专业）
            use_external_candidates: 是否使用外部候选词
            external_candidates: 外部候选词列表
        
        Returns:
            [(扩展词, 相似度), ...]
        """
        candidates = self.domain_vocabulary.copy()
        
        if use_external_candidates and external_candidates:
            candidates.extend(external_candidates)
            candidates = list(set(candidates))  # 去重
        
        return self.expand_semantically(
            keyword, candidates, top_k=top_k, 
            min_similarity=min_similarity, combine_with_rules=True
        )
    
    def batch_expand(self, keywords: List[str], top_k: int = 5) -> Dict[str, List[Tuple[str, float]]]:
        """
        批量扩展多个关键词
        
        Args:
            keywords: 关键词列表
            top_k: 每个关键词的扩展数量
        
        Returns:
            {关键词: [(扩展词, 相似度), ...], ...}
        """
        results = {}
        for keyword in keywords:
            results[keyword] = self.expand(keyword, top_k=top_k)
        return results


class HybridSemanticExpander:
    """
    混合语义扩展器
    
    结合BERT语义理解和传统规则方法的优点
    """
    
    def __init__(self, use_bert: bool = True, bert_model: str = None):
        """
        初始化混合扩展器
        
        Args:
            use_bert: 是否使用BERT（需要sentence-transformers）
            bert_model: BERT模型名称
        """
        self.use_bert = use_bert and BERT_AVAILABLE
        self.bert_expander = None
        
        if self.use_bert:
            try:
                self.bert_expander = DomainBertExpander(model_name=bert_model)
                print("[Hybrid] BERT扩展器初始化成功")
            except Exception as e:
                print(f"[Hybrid] BERT初始化失败: {e}")
                print("[Hybrid] 回退到规则方法")
                self.use_bert = False
        
        # 导入传统扩展器
        from semantic_expansion import SemanticExpander
        self.rule_expander = SemanticExpander()
        print("[Hybrid] 规则扩展器初始化成功")
    
    def expand(self, keyword: str, mode: str = "moderate",
               top_k: int = 5) -> List[Tuple[str, float]]:
        """
        混合扩展
        
        策略：
        1. 优先使用BERT语义扩展（如果可用）
        2. 补充规则方法的结果
        3. 综合评分排序
        
        Args:
            keyword: 原始关键词
            mode: 扩展模式（影响BERT阈值）
            top_k: 返回数量
        
        Returns:
            [(扩展词, 相似度), ...]
        """
        all_results = []
        seen_terms = set()
        
        # BERT扩展
        if self.use_bert and self.bert_expander:
            # 根据模式设置阈值
            thresholds = {
                "conservative": 0.6,
                "moderate": 0.4,
                "aggressive": 0.25
            }
            min_sim = thresholds.get(mode, 0.4)
            
            bert_results = self.bert_expander.expand(
                keyword, top_k=top_k*2, min_similarity=min_sim
            )
            
            for term, score in bert_results:
                term_lower = term.lower()
                if term_lower not in seen_terms:
                    all_results.append((term, score, "BERT"))
                    seen_terms.add(term_lower)
        
        # 规则扩展
        rule_results = self.rule_expander.expand_term(keyword, mode=mode)
        
        for term, score in rule_results:
            term_lower = term.lower()
            if term_lower not in seen_terms:
                # 规则方法的分数调整到BERT范围
                normalized_score = score * 0.8  # 稍低于BERT结果
                all_results.append((term, normalized_score, "Rule"))
                seen_terms.add(term_lower)
        
        # 按分数排序
        all_results.sort(key=lambda x: x[1], reverse=True)
        
        # 返回（移除来源标记）
        return [(term, score) for term, score, source in all_results[:top_k]]
    
    def get_expansion_summary(self, keyword: str, mode: str = "moderate") -> str:
        """获取扩展摘要"""
        lines = [
            "Hybrid Semantic Expansion Summary",
            "=" * 50,
            f"Keyword: {keyword}",
            f"Mode: {mode}",
            f"BERT Enabled: {self.use_bert}",
            "-" * 50,
            "Expanded Terms:"
        ]
        
        expansions = self.expand(keyword, mode=mode, top_k=10)
        for i, (term, score) in enumerate(expansions, 1):
            lines.append(f"  {i}. {term} (score: {score:.3f})")
        
        lines.append("=" * 50)
        return "\n".join(lines)


# 便捷函数
def bert_expand_keywords(keywords: str, 
                        top_k: int = 5,
                        model_name: str = None) -> str:
    """
    快速BERT扩展（生成布尔查询）
    
    Args:
        keywords: 原始关键词
        top_k: 扩展数量
        model_name: BERT模型名称
    
    Returns:
        布尔查询字符串
    
    Example:
        >>> bert_expand_keywords("treasury wine", top_k=3)
        '"treasury wine" OR "penfolds" OR "australian wine" OR "wine industry"'
    """
    try:
        expander = DomainBertExpander(model_name=model_name)
        expansions = expander.expand(keywords, top_k=top_k)
        
        terms = [f'"{keywords}"']  # 包含原始词
        for term, score in expansions:
            if ' ' in term:
                terms.append(f'"{term}"')
            else:
                terms.append(term)
        
        return " OR ".join(terms)
    except Exception as e:
        print(f"[BERT-Expand] 扩展失败: {e}")
        return f'"{keywords}"'


def compare_expansion_methods(keyword: str) -> Dict[str, List[Tuple[str, float]]]:
    """
    对比不同扩展方法的结果
    
    Returns:
        {方法名: [(扩展词, 分数), ...], ...}
    """
    results = {}
    
    # 1. 规则方法
    from semantic_expansion import SemanticExpander
    rule_expander = SemanticExpander()
    results["Rule-based"] = rule_expander.expand_term(keyword, mode="moderate")
    
    # 2. BERT方法（如果可用）
    if BERT_AVAILABLE:
        try:
            bert_expander = DomainBertExpander()
            results["BERT"] = bert_expander.expand(keyword, top_k=5)
        except Exception as e:
            results["BERT"] = [(f"Error: {e}", 0.0)]
    else:
        results["BERT"] = [("BERT not available", 0.0)]
    
    # 3. 混合方法
    try:
        hybrid = HybridSemanticExpander(use_bert=BERT_AVAILABLE)
        results["Hybrid"] = hybrid.expand(keyword, mode="moderate")
    except Exception as e:
        results["Hybrid"] = [(f"Error: {e}", 0.0)]
    
    return results


# 测试代码
if __name__ == "__main__":
    print("=" * 80)
    print("BERT-enhanced Semantic Expansion Module - Test")
    print("=" * 80)
    
    if not BERT_AVAILABLE:
        print("\n[警告] sentence-transformers未安装")
        print("请运行: pip install sentence-transformers")
        print("将仅测试基础功能...")
    
    # 测试1: 基础BERT扩展（如果可用）
    if BERT_AVAILABLE:
        print("\n[测试1] BERT语义扩展")
        print("-" * 50)
        
        try:
            expander = DomainBertExpander()
            
            test_keywords = ["treasury wine", "penfolds", "acquisition"]
            
            for kw in test_keywords:
                print(f"\n关键词: '{kw}'")
                expansions = expander.expand(kw, top_k=5, min_similarity=0.35)
                for term, score in expansions:
                    print(f"  - {term}: {score:.3f}")
        
        except Exception as e:
            print(f"错误: {e}")
            import traceback
            traceback.print_exc()
    
    # 测试2: 混合扩展器
    print("\n\n[测试2] 混合扩展器")
    print("-" * 50)
    
    try:
        hybrid = HybridSemanticExpander(use_bert=BERT_AVAILABLE)
        
        test_keywords = ["treasury wine", "penfolds"]
        
        for kw in test_keywords:
            print(f"\n{hybrid.get_expansion_summary(kw, mode='moderate')}")
    
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    
    # 测试3: 方法对比
    if BERT_AVAILABLE:
        print("\n\n[测试3] 扩展方法对比")
        print("-" * 50)
        
        keyword = "treasury wine"
        print(f"\n对比关键词: '{keyword}'")
        
        comparison = compare_expansion_methods(keyword)
        
        for method, results in comparison.items():
            print(f"\n{method}:")
            for term, score in results[:5]:
                print(f"  - {term}: {score:.3f}")
    
    print("\n" + "=" * 80)
    print("测试完成!")
    print("=" * 80)
    
    if BERT_AVAILABLE:
        print("\n使用示例:")
        print("  from bert_semantic_expansion import DomainBertExpander")
        print("  expander = DomainBertExpander()")
        print("  expansions = expander.expand('treasury wine', top_k=5)")
        print("  print(expansions)")
