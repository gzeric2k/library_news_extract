# -*- coding: utf-8 -*-
"""
NewsBank Semantic Query Expansion Module
语义查询扩展模块 - 智能延伸搜索关键词

功能：
1. 领域知识图谱（酒业/商业新闻）
2. 同义词扩展
3. 语义相关词推荐
4. 可配置的扩展强度

作者: AI Assistant
日期: 2026-02-15
"""

from typing import List, Dict, Set, Optional, Tuple, Any
from difflib import SequenceMatcher
import re


class DomainKnowledgeBase:
    """
    领域知识库 - 酒业和商业新闻领域
    
    包含：
    - 公司与品牌关系
    - 产品类别层次
    - 行业术语分类
    - 地理区域关系
    """
    
    def __init__(self):
        # 公司 -> 品牌映射
        self.company_brands: Dict[str, List[str]] = {
            "treasury wine estates": ["penfolds", "wolf blass", "wynns", "lindeman's", 
                                     "seppelt", "pepperjack", "19 crimes", "daou vineyards",
                                     "st hubert's the stag", "squealing pig", "blossom hill",
                                     "frank family vineyards", "beringer", "etude", 
                                     "sterling vineyards", "beaulieu vineyard", "stags' leap",
                                     "beringer bros", "castello di gabbiano", "matua"],
            "twe": ["penfolds", "wolf blass", "wynns", "lindeman's"],  # 缩写
            "penfolds": ["grange", "bin 389", "bin 407", "bin 28", "bin 128", 
                        "kalimna", "st henri", "magill estate"],
            "wolf blass": ["grey label", "gold label", "black label", "yellow label"],
        }
        
        # 产品类别
        self.product_categories: Dict[str, List[str]] = {
            "wine": ["red wine", "white wine", "rose", "sparkling", "fortified",
                    "shiraz", "cabernet sauvignon", "chardonnay", "pinot noir",
                    "merlot", "sauvignon blanc", "riesling", "grenache"],
            "australian wine": ["penfolds", "wolf blass", "wynns", "lindeman's",
                               "south australia", "barossa valley", "mclaren vale",
                               "coonawarra", "margaret river"],
            "premium wine": ["penfolds grange", "bin 389", "icon wine", 
                           "luxury wine", "fine wine", "reserve"],
        }
        
        # 行业术语分类
        self.industry_terms: Dict[str, List[str]] = {
            "business": ["acquisition", "merger", "takeover", "investment", 
                        "revenue", "profit", "earnings", "market share",
                        "growth", "expansion", "strategy", "deal"],
            "production": ["vintage", "winemaking", "vineyard", "harvest",
                          "fermentation", "aging", "bottling", "cellar door"],
            "marketing": ["brand", "marketing", "export", "distribution",
                         "sales", "consumer", "premium", "luxury", "positioning"],
            "finance": ["asx", "share price", "dividend", "market cap",
                       "annual report", "financial results", "shareholder"],
        }
        
        # 地理区域
        self.geographic: Dict[str, List[str]] = {
            "australia": ["south australia", "new south wales", "victoria",
                         "western australia", "tasmania"],
            "south australia": ["barossa valley", "mclaren vale", "coonawarra",
                               "adelaide hills", "clare valley"],
            "wine regions": ["barossa", "mclaren vale", "coonawarra", 
                           "margaret river", "hunter valley", "yarra valley"],
        }
        
        # 同义词库
        self.synonyms: Dict[str, List[str]] = {
            # 公司相关
            "treasury wine estates": ["twe", "treasury wine", "treasury wines"],
            "twe": ["treasury wine estates"],
            "penfolds": ["penfold", "penfold's"],
            
            # 商业术语
            "acquisition": ["takeover", "purchase", "buyout", "deal"],
            "merger": ["consolidation", "integration", "combination"],
            "revenue": ["sales", "turnover", "income"],
            "profit": ["earnings", "income", "gain", "margin"],
            
            # 产品相关
            "wine": ["vino", "beverage"],
            "vintage": ["harvest", "year"],
            "vineyard": ["winery", "estate", "cellar"],
        }
        
        # 相关概念（用于语义扩展）
        self.related_concepts: Dict[str, List[str]] = {
            "treasury wine": ["penfolds", "wolf blass", "australian wine", 
                            "wine industry", "asx", "wine export"],
            "penfolds": ["grange", "bin 389", "shiraz", "australian wine",
                        "treasury wine", "luxury wine", "icon wine"],
            "wine industry": ["vineyard", "winemaking", "export", "asx",
                            "treasury wine", "foster's group", "constellation brands"],
            "acquisition": ["merger", "takeover", "investment", "deal",
                           "market consolidation", "expansion"],
        }
    
    def get_brands_for_company(self, company: str) -> List[str]:
        """获取公司旗下的品牌"""
        company_lower = company.lower()
        for key, brands in self.company_brands.items():
            if key in company_lower or company_lower in key:
                return brands
        return []
    
    def get_company_for_brand(self, brand: str) -> Optional[str]:
        """获取品牌所属公司"""
        brand_lower = brand.lower()
        for company, brands in self.company_brands.items():
            if any(brand_lower == b.lower() or brand_lower in b.lower() 
                   for b in brands):
                return company
        return None
    
    def get_synonyms(self, word: str) -> List[str]:
        """获取同义词"""
        word_lower = word.lower()
        for key, syns in self.synonyms.items():
            if key in word_lower or word_lower in key:
                return syns
        return []
    
    def get_related_concepts(self, concept: str) -> List[str]:
        """获取相关概念"""
        concept_lower = concept.lower()
        results = []
        for key, concepts in self.related_concepts.items():
            if key in concept_lower or concept_lower in key:
                results.extend(concepts)
        return list(set(results))  # 去重
    
    def get_all_related_terms(self, term: str, max_depth: int = 2) -> Set[str]:
        """
        获取所有相关术语（递归）
        
        Args:
            term: 起始术语
            max_depth: 最大递归深度
        
        Returns:
            相关术语集合
        """
        results = set()
        visited = set()
        
        def explore(current_term: str, depth: int):
            if depth > max_depth or current_term in visited:
                return
            
            visited.add(current_term)
            
            # 同义词
            for syn in self.get_synonyms(current_term):
                results.add(syn)
                explore(syn, depth + 1)
            
            # 相关概念
            for concept in self.get_related_concepts(current_term):
                results.add(concept)
                explore(concept, depth + 1)
            
            # 公司-品牌关系
            if brands := self.get_brands_for_company(current_term):
                for brand in brands:
                    results.add(brand)
                    explore(brand, depth + 1)
            
            if company := self.get_company_for_brand(current_term):
                results.add(company)
                explore(company, depth + 1)
        
        explore(term.lower(), 0)
        return results


class SemanticExpander:
    """
    语义扩展引擎
    
    功能：
    1. 基于领域知识的智能扩展
    2. 可配置的扩展强度
    3. 相关性评分
    """
    
    def __init__(self, knowledge_base: Optional[DomainKnowledgeBase] = None):
        self.kb = knowledge_base or DomainKnowledgeBase()
        
        # 扩展强度配置
        self.expansion_modes = {
            "conservative": {
                "description": "保守模式 - 仅高置信度扩展",
                "max_terms": 3,
                "use_synonyms": True,
                "use_related": False,
                "min_similarity": 0.9
            },
            "moderate": {
                "description": "适中模式 - 平衡精确度和召回率",
                "max_terms": 5,
                "use_synonyms": True,
                "use_related": True,
                "min_similarity": 0.7
            },
            "aggressive": {
                "description": "激进模式 - 最大化召回率",
                "max_terms": 8,
                "use_synonyms": True,
                "use_related": True,
                "min_similarity": 0.5
            }
        }
    
    def calculate_similarity(self, term1: str, term2: str) -> float:
        """
        计算两个术语的相似度
        
        使用多种方法：
        1. 字符串相似度（编辑距离）
        2. 包含关系
        3. 领域知识关联
        """
        t1, t2 = term1.lower(), term2.lower()
        
        # 方法1: SequenceMatcher（编辑距离）
        seq_sim = SequenceMatcher(None, t1, t2).ratio()
        
        # 方法2: 包含关系
        if t1 in t2 or t2 in t1:
            containment_bonus = 0.3
        else:
            containment_bonus = 0
        
        # 方法3: 领域知识关联
        knowledge_bonus = 0
        if t2 in self.kb.get_synonyms(t1):
            knowledge_bonus = 0.4
        elif t2 in self.kb.get_related_concepts(t1):
            knowledge_bonus = 0.2
        elif t2 in self.kb.get_all_related_terms(t1, max_depth=1):
            knowledge_bonus = 0.1
        
        # 综合评分
        final_score = min(1.0, seq_sim + containment_bonus + knowledge_bonus)
        return final_score
    
    def expand_term(self, term: str, mode: str = "moderate", 
                    min_similarity: Optional[float] = None) -> List[Tuple[str, float]]:
        """
        扩展单个术语
        
        Args:
            term: 原始术语
            mode: 扩展模式 (conservative/moderate/aggressive)
            min_similarity: 最小相似度阈值（覆盖模式设置）
        
        Returns:
            [(扩展词, 相似度), ...]
        """
        if mode not in self.expansion_modes:
            mode = "moderate"
        
        config = self.expansion_modes[mode]
        threshold = min_similarity or config["min_similarity"]
        
        candidates = []
        
        # 1. 同义词扩展
        if config["use_synonyms"]:
            for syn in self.kb.get_synonyms(term):
                sim = self.calculate_similarity(term, syn)
                if sim >= threshold:
                    candidates.append((syn, sim))
        
        # 2. 相关概念扩展
        if config["use_related"]:
            for concept in self.kb.get_related_concepts(term):
                sim = self.calculate_similarity(term, concept)
                if sim >= threshold:
                    candidates.append((concept, sim))
            
            # 深度扩展
            if mode == "aggressive":
                for related in self.kb.get_all_related_terms(term, max_depth=2):
                    sim = self.calculate_similarity(term, related)
                    if sim >= threshold:
                        candidates.append((related, sim))
        
        # 去重并排序
        seen = set()
        unique_candidates = []
        for term, score in sorted(candidates, key=lambda x: x[1], reverse=True):
            if term.lower() not in seen:
                seen.add(term.lower())
                unique_candidates.append((term, score))
        
        # 限制数量
        return unique_candidates[:config["max_terms"]]
    
    def expand_query(self, query: str, mode: str = "moderate") -> Dict[str, List[Tuple[str, float]]]:
        """
        扩展完整查询
        
        Args:
            query: 原始查询
            mode: 扩展模式
        
        Returns:
            {原始词: [(扩展词, 相似度), ...], ...}
        """
        # 分词（简单实现）
        words = self._tokenize(query)
        
        results = {}
        for word in words:
            if len(word) > 2:  # 忽略短词
                expansions = self.expand_term(word, mode)
                if expansions:
                    results[word] = expansions
        
        return results
    
    def _tokenize(self, text: str) -> List[str]:
        """简单分词"""
        # 移除标点，分词
        cleaned = re.sub(r'[^\w\s]', ' ', text.lower())
        words = cleaned.split()
        
        # 过滤停用词
        stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        return [w for w in words if w not in stopwords and len(w) > 2]
    
    def build_expanded_query(self, original_query: str, mode: str = "moderate",
                            include_original: bool = True) -> str:
        """
        构建扩展后的查询字符串
        
        Args:
            original_query: 原始查询
            mode: 扩展模式
            include_original: 是否包含原始词
        
        Returns:
            扩展后的查询字符串（布尔表达式）
        """
        expansions = self.expand_query(original_query, mode)
        
        if not expansions:
            return original_query
        
        parts = []
        
        for original_word, expanded_list in expansions.items():
            if not expanded_list:
                if include_original:
                    parts.append(f'"{original_word}"')
                continue
            
            # 构建 OR 表达式
            all_terms = []
            if include_original:
                all_terms.append(f'"{original_word}"')
            
            for term, score in expanded_list:
                if ' ' in term:  # 多词短语加引号
                    all_terms.append(f'"{term}"')
                else:
                    all_terms.append(term)
            
            if len(all_terms) == 1:
                parts.append(all_terms[0])
            else:
                parts.append(f'({" OR ".join(all_terms)})')
        
        # 使用 AND 连接各个词的扩展组
        if len(parts) == 1:
            return parts[0]
        else:
            return " AND ".join(parts)
    
    def get_expansion_summary(self, original_query: str, mode: str = "moderate") -> str:
        """获取扩展摘要"""
        expansions = self.expand_query(original_query, mode)
        
        lines = [
            "Semantic Query Expansion Summary",
            "=" * 50,
            f"Original Query: {original_query}",
            f"Mode: {mode}",
            "-" * 50
        ]
        
        for word, expanded_list in expansions.items():
            lines.append(f"\n'{word}' 的扩展:")
            for term, score in expanded_list:
                lines.append(f"  - {term} (相似度: {score:.2f})")
        
        if not expansions:
            lines.append("\n未找到可扩展的术语")
        
        lines.append("\n" + "=" * 50)
        
        return "\n".join(lines)


class SemanticSearchTemplates:
    """
    语义搜索预设模板
    结合语义扩展和搜索模板
    """
    
    @staticmethod
    def semantic_treasury_expansion(mode: str = "moderate") -> Dict[str, Any]:
        """
        Treasury Wine 语义扩展搜索
        
        自动扩展：treasury wine → penfolds, australian wine, wine industry等
        """
        expander = SemanticExpander()
        
        base_keywords = ["treasury wine", "penfolds"]
        all_expansions = {}
        
        for kw in base_keywords:
            expansions = expander.expand_term(kw, mode=mode)
            all_expansions[kw] = expansions
        
        return {
            "base_keywords": base_keywords,
            "expansions": all_expansions,
            "suggested_query": expander.build_expanded_query(
                "treasury wine estates", mode=mode
            )
        }
    
    @staticmethod
    def get_semantic_suggestions(keyword: str, mode: str = "moderate") -> List[str]:
        """
        获取语义建议词
        
        Returns:
            建议词列表
        """
        expander = SemanticExpander()
        expansions = expander.expand_term(keyword, mode=mode)
        return [term for term, score in expansions]


# 便捷函数
def expand_keywords(keywords: str, mode: str = "moderate") -> str:
    """
    快速扩展关键词
    
    Args:
        keywords: 原始关键词
        mode: 扩展模式 (conservative/moderate/aggressive)
    
    Returns:
        扩展后的查询字符串
    
    Example:
        >>> expand_keywords("treasury wine", mode="moderate")
        '"treasury wine" OR "twe" OR "penfolds" OR "australian wine"'
    """
    expander = SemanticExpander()
    return expander.build_expanded_query(keywords, mode=mode)


def get_related_terms(term: str, max_terms: int = 5) -> List[str]:
    """
    获取相关术语
    
    Args:
        term: 输入词
        max_terms: 最大返回数量
    
    Returns:
        相关术语列表
    """
    expander = SemanticExpander()
    expansions = expander.expand_term(term, mode="moderate")
    return [t for t, s in expansions[:max_terms]]


# 测试代码
if __name__ == "__main__":
    print("=" * 80)
    print("Semantic Query Expansion Module - Demo")
    print("=" * 80)
    
    expander = SemanticExpander()
    
    # 测试1: 基础扩展
    print("\n[测试1] 基础语义扩展")
    print("-" * 50)
    query = "treasury wine"
    for mode in ["conservative", "moderate", "aggressive"]:
        print(f"\n模式: {mode}")
        print(expander.get_expansion_summary(query, mode))
        expanded = expander.build_expanded_query(query, mode=mode)
        print(f"\n扩展后查询: {expanded}")
    
    # 测试2: 品牌扩展
    print("\n\n[测试2] 品牌语义扩展")
    print("-" * 50)
    query = "penfolds"
    print(expander.get_expansion_summary(query, mode="moderate"))
    
    # 测试3: 便捷函数
    print("\n\n[测试3] 便捷函数")
    print("-" * 50)
    result = expand_keywords("treasury wine", mode="moderate")
    print(f"expand_keywords('treasury wine'): {result}")
    
    related = get_related_terms("penfolds", max_terms=5)
    print(f"\nget_related_terms('penfolds'): {related}")
    
    print("\n" + "=" * 80)
    print("Demo completed!")
    print("=" * 80)
