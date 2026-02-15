# -*- coding: utf-8 -*-
"""
NewsBank Advanced Search Query Builder
优化搜索策略，支持多字段、布尔逻辑和通配符
"""

from typing import List, Dict, Optional, Union, Tuple
from urllib.parse import quote
from enum import Enum

# 尝试导入语义扩展模块
SEMANTIC_AVAILABLE = False
SemanticExpander = None
DomainKnowledgeBase = None
expand_keywords = None

try:
    from semantic_expansion import (
        SemanticExpander as _SemanticExpander,
        DomainKnowledgeBase as _DomainKnowledgeBase,
        expand_keywords as _expand_keywords
    )
    SemanticExpander = _SemanticExpander
    DomainKnowledgeBase = _DomainKnowledgeBase
    expand_keywords = _expand_keywords
    SEMANTIC_AVAILABLE = True
except ImportError:
    pass


class SearchField(Enum):
    """NewsBank可用搜索字段"""
    ALL_TEXT = "alltext"           # 全文
    TITLE = "Title"                # 标题/Headline
    LEAD = "Lead"                  # 首段/导语
    AUTHOR = "Author"              # 作者
    SOURCE = "Source"              # 来源
    SECTION = "Section"            # 版面


class BooleanOperator(Enum):
    """布尔操作符"""
    AND = "and"
    OR = "or"
    NOT = "not"


class SearchCondition:
    """单个搜索条件"""
    def __init__(self, 
                 value: str, 
                 field: SearchField = SearchField.ALL_TEXT,
                 boolean_op: Optional[BooleanOperator] = None):
        self.value = value
        self.field = field
        self.boolean_op = boolean_op
    
    def to_url_param(self, index: int) -> Dict[str, str]:
        """转换为URL参数字典"""
        params = {}
        
        # 布尔操作符（除第一个条件外）
        if index > 0 and self.boolean_op:
            params[f'bln-base-{index}'] = self.boolean_op.value
        
        # 搜索词和字段
        params[f'val-base-{index}'] = self.value
        params[f'fld-base-{index}'] = self.field.value
        
        return params


class AdvancedSearchQuery:
    """
    NewsBank高级搜索查询构建器
    
    使用示例:
        # 基础用法
        query = AdvancedSearchQuery()
        query.add_keyword("treasury wine estates")
        url = query.build_url()
        
        # 高级用法：多字段布尔搜索
        query = AdvancedSearchQuery()
        query.add_condition("treasury wine", SearchField.ALL_TEXT)
        query.add_condition("penfold*", SearchField.TITLE, BooleanOperator.AND)
        query.add_condition("merger OR acquisition", SearchField.ALL_TEXT, BooleanOperator.AND)
        url = query.build_url()
    """
    
    def __init__(self, 
                 source_filter: Optional[str] = "AFRWAFRN",
                 max_results: int = 60,
                 sort_by_date: bool = True,
                 hide_duplicates: int = 2):
        self.conditions: List[SearchCondition] = []
        self.source_filter = source_filter
        self.max_results = max_results
        self.sort_by_date = sort_by_date
        self.hide_duplicates = hide_duplicates
        
        # NewsBank基础参数
        self.base_url = "https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/results"
        self.product_id = "AWGLNB"
    
    def add_condition(self, 
                     value: str, 
                     field: SearchField = SearchField.ALL_TEXT,
                     boolean_op: Optional[BooleanOperator] = BooleanOperator.AND) -> 'AdvancedSearchQuery':
        """
        添加搜索条件
        
        Args:
            value: 搜索词（支持通配符 * 和 ?）
            field: 搜索字段
            boolean_op: 布尔操作符（第一个条件可为None）
        """
        condition = SearchCondition(value, field, boolean_op)
        self.conditions.append(condition)
        return self
    
    def add_keyword(self, keyword: str) -> 'AdvancedSearchQuery':
        """简单关键词搜索（全文）"""
        return self.add_condition(keyword, SearchField.ALL_TEXT, None)
    
    def add_title_keyword(self, keyword: str, 
                         boolean_op: BooleanOperator = BooleanOperator.AND) -> 'AdvancedSearchQuery':
        """标题关键词搜索"""
        return self.add_condition(keyword, SearchField.TITLE, boolean_op)
    
    def add_lead_keyword(self, keyword: str,
                        boolean_op: BooleanOperator = BooleanOperator.AND) -> 'AdvancedSearchQuery':
        """首段关键词搜索"""
        return self.add_condition(keyword, SearchField.LEAD, boolean_op)
    
    def add_phrase(self, phrase: str, 
                  field: SearchField = SearchField.ALL_TEXT,
                  boolean_op: Optional[BooleanOperator] = BooleanOperator.AND) -> 'AdvancedSearchQuery':
        """
        添加精确短语搜索（自动加引号）
        
        Args:
            phrase: 短语（如 "treasury wine estates"）
        """
        # 确保短语有引号
        if not (phrase.startswith('"') and phrase.endswith('"')):
            phrase = f'"{phrase}"'
        return self.add_condition(phrase, field, boolean_op)
    
    def add_wildcard(self, pattern: str,
                    field: SearchField = SearchField.ALL_TEXT,
                    boolean_op: BooleanOperator = BooleanOperator.AND) -> 'AdvancedSearchQuery':
        """
        添加通配符搜索
        
        Args:
            pattern: 通配符模式（如 penfold*）
        """
        return self.add_condition(pattern, field, boolean_op)
    
    def add_variations(self, 
                      base_word: str,
                      variations: List[str],
                      field: SearchField = SearchField.ALL_TEXT,
                      boolean_op: BooleanOperator = BooleanOperator.AND) -> 'AdvancedSearchQuery':
        """
        添加词形变化（使用OR组合）
        
        Args:
            base_word: 基础词
            variations: 变体列表（如 ["penfolds", "penfold", "penfold's"]）
        """
        if not variations:
            return self.add_condition(base_word, field, boolean_op)
        
        # 构建 OR 表达式
        or_expression = " OR ".join([f'"{v}"' if ' ' in v else v for v in variations])
        return self.add_condition(or_expression, field, boolean_op)
    
    def exclude_keyword(self, keyword: str,
                       field: SearchField = SearchField.ALL_TEXT) -> 'AdvancedSearchQuery':
        """排除关键词（NOT操作）"""
        return self.add_condition(keyword, field, BooleanOperator.NOT)
    
    def set_date_range(self, start_date: str, end_date: str) -> 'AdvancedSearchQuery':
        """
        设置日期范围
        
        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
        """
        # NewsBank日期格式: YYYY-MM-DD
        self.start_date = start_date
        self.end_date = end_date
        return self
    
    def build_url(self) -> str:
        """构建完整搜索URL"""
        if not self.conditions:
            raise ValueError("至少需要一个搜索条件")
        
        params = []
        
        # 基础参数
        params.append(f'p={self.product_id}')
        params.append(f'hide_duplicates={self.hide_duplicates}')
        params.append(f'maxresults={self.max_results}')
        params.append('f=advanced')  # 启用高级搜索
        
        # 排序
        if self.sort_by_date:
            params.append('sort=YMD_date%3AD')  # 日期降序
        
        # 来源筛选
        if self.source_filter:
            # Australian Financial Review Collection
            params.append(f't=favorite%3A{self.source_filter}%21Australian%2520Financial%2520Review%2520Collection')
        
        # 搜索条件
        for i, condition in enumerate(self.conditions):
            condition_params = condition.to_url_param(i)
            for key, value in condition_params.items():
                encoded_value = quote(value, safe='*?" ')
                params.append(f'{key}={encoded_value}')
        
        return f"{self.base_url}?{'&'.join(params)}"
    
    def get_search_summary(self) -> str:
        """获取搜索摘要"""
        lines = ["NewsBank Advanced Search Query", "=" * 50]
        
        for i, condition in enumerate(self.conditions):
            if i == 0:
                lines.append(f"  [{i+1}] {condition.field.value}: {condition.value}")
            else:
                op_str = condition.boolean_op.value.upper() if condition.boolean_op else "AND"
                lines.append(f"  [{i+1}] {op_str} {condition.field.value}: {condition.value}")
        
        lines.append("=" * 50)
        lines.append(f"Max Results: {self.max_results}")
        lines.append(f"Source: {self.source_filter or 'All'}")
        lines.append(f"Sort: {'Date (newest first)' if self.sort_by_date else 'Relevance'}")
        
        return "\n".join(lines)


class SearchTemplates:
    """预设搜索模板"""
    
    @staticmethod
    def treasury_wine_mergers() -> AdvancedSearchQuery:
        """
        Treasury Wine Estates 并购主题搜索
        优化用于查找并购、收购相关文章
        """
        query = AdvancedSearchQuery()
        
        # 基础条件：公司名必须在全文出现
        query.add_condition("treasury wine estates", SearchField.ALL_TEXT)
        
        # 标题必须包含品牌相关
        query.add_condition("penfold* OR \"wolf blass\" OR \"treasury wine\"", 
                          SearchField.TITLE, BooleanOperator.AND)
        
        # 全文包含并购相关词汇
        query.add_condition("acquisition OR merger OR takeover OR \"bought\" OR \"purchased\" OR deal",
                          SearchField.ALL_TEXT, BooleanOperator.AND)
        
        # 排除广告和赞助内容
        query.exclude_keyword("advertisement", SearchField.TITLE)
        query.exclude_keyword("sponsored", SearchField.TITLE)
        
        return query
    
    @staticmethod
    def treasury_wine_strategy() -> AdvancedSearchQuery:
        """
        Treasury Wine Estates 战略/品牌主题搜索
        优化用于查找品牌战略、市场扩张相关文章
        """
        query = AdvancedSearchQuery()
        
        # 标题包含核心品牌
        query.add_condition("penfold* OR grange OR \"bin 389\" OR \"wolf blass\"",
                          SearchField.TITLE)
        
        # 首段或全文包含公司名
        query.add_condition("treasury OR \"wine estates\" OR TWE",
                          SearchField.LEAD, BooleanOperator.AND)
        
        # 战略相关词汇
        query.add_condition("strategy OR brand OR marketing OR expansion OR export OR premium",
                          SearchField.ALL_TEXT, BooleanOperator.AND)
        
        return query
    
    @staticmethod
    def treasury_wine_financial() -> AdvancedSearchQuery:
        """
        Treasury Wine Estates 财务业绩主题搜索
        优化用于查找财报、业绩相关文章
        """
        query = AdvancedSearchQuery()
        
        # 标题或首段包含公司名
        query.add_condition("treasury wine* OR TWE",
                          SearchField.TITLE)
        query.add_condition("treasury OR TWE",
                          SearchField.LEAD, BooleanOperator.OR)
        
        # 财务相关词汇
        query.add_condition("earnings OR profit OR revenue OR \"annual report\" OR ASX OR financial",
                          SearchField.ALL_TEXT, BooleanOperator.AND)
        
        return query
    
    @staticmethod
    def precise_headline_search(keywords: List[str], 
                               must_include: Optional[List[str]] = None) -> AdvancedSearchQuery:
        """
        精确标题搜索模板
        
        Args:
            keywords: 标题必须包含的关键词列表（OR关系）
            must_include: 全文必须包含的关键词列表（AND关系）
        """
        query = AdvancedSearchQuery()
        
        # 构建标题搜索表达式
        title_expr = " OR ".join([f'"{k}"' if ' ' in k else k for k in keywords])
        query.add_condition(title_expr, SearchField.TITLE)
        
        # 添加必须包含的条件
        if must_include:
            for kw in must_include:
                query.add_condition(kw, SearchField.ALL_TEXT, BooleanOperator.AND)
        
        return query


def create_optimized_search(keyword_type: str = "treasury_mergers") -> AdvancedSearchQuery:
    """
    创建优化的搜索查询
    
    Args:
        keyword_type: 搜索类型
            - "treasury_mergers": Treasury Wine并购主题
            - "treasury_strategy": Treasury Wine战略主题
            - "treasury_financial": Treasury Wine财务主题
            - "custom": 自定义（返回空查询对象）
    
    Returns:
        AdvancedSearchQuery对象
    """
    templates = {
        "treasury_mergers": SearchTemplates.treasury_wine_mergers,
        "treasury_strategy": SearchTemplates.treasury_wine_strategy,
        "treasury_financial": SearchTemplates.treasury_wine_financial,
    }
    
    if keyword_type in templates:
        return templates[keyword_type]()
    else:
        return AdvancedSearchQuery()


class SemanticSearchQuery:
    """
    语义搜索查询构建器
    
    集成语义扩展和高级搜索
    """
    
    def __init__(self, 
                 semantic_mode: str = "moderate",
                 enable_semantic: bool = True,
                 source_filter: Optional[str] = "AFRWAFRN",
                 max_results: int = 60):
        """
        初始化语义搜索查询
        
        Args:
            semantic_mode: 语义扩展模式 (conservative/moderate/aggressive)
            enable_semantic: 是否启用语义扩展
            source_filter: 来源筛选
            max_results: 最大结果数
        """
        self.semantic_mode = semantic_mode
        self.enable_semantic = enable_semantic and SEMANTIC_AVAILABLE
        self.source_filter = source_filter
        self.max_results = max_results
        
        if self.enable_semantic and SEMANTIC_AVAILABLE and SemanticExpander:
            self.expander = SemanticExpander()
        else:
            self.expander = None
    
    def build_query(self, keyword: str, 
                   field: SearchField = SearchField.ALL_TEXT) -> AdvancedSearchQuery:
        """
        构建语义增强的搜索查询
        
        Args:
            keyword: 原始关键词
            field: 搜索字段
        
        Returns:
            AdvancedSearchQuery对象
        """
        query = AdvancedSearchQuery(
            source_filter=self.source_filter,
            max_results=self.max_results
        )
        
        if not self.enable_semantic or not self.expander:
            # 不使用语义扩展，直接添加关键词
            query.add_condition(keyword, field)
            return query
        
        # 使用语义扩展
        expanded = self.expander.build_expanded_query(
            keyword, 
            mode=self.semantic_mode,
            include_original=True
        )
        
        # 解析扩展后的查询并添加到条件
        # 扩展后的格式如: ("treasury" OR "twe") AND ("wine" OR "winemaking")
        if " AND " in expanded:
            # 多组条件
            groups = expanded.split(" AND ")
            for i, group in enumerate(groups):
                # 清理括号
                group = group.strip().strip('()')
                if i == 0:
                    query.add_condition(group, field)
                else:
                    query.add_condition(group, field, BooleanOperator.AND)
        else:
            # 单组条件
            query.add_condition(expanded, field)
        
        return query
    
    def get_expansion_info(self, keyword: str) -> str:
        """获取语义扩展信息"""
        if not self.enable_semantic or not self.expander:
            return "语义扩展未启用"
        
        return self.expander.get_expansion_summary(keyword, self.semantic_mode)


class SemanticSearchTemplates:
    """语义搜索预设模板"""
    
    @staticmethod
    def treasury_wine_semantic(mode: str = "moderate") -> AdvancedSearchQuery:
        """
        Treasury Wine 语义增强搜索
        
        自动扩展: treasury wine → penfolds, australian wine, wine industry等
        """
        builder = SemanticSearchQuery(
            semantic_mode=mode,
            enable_semantic=True
        )
        
        # 构建标题搜索（语义扩展）
        query = AdvancedSearchQuery()
        
        # 使用语义扩展获取相关词
        if SEMANTIC_AVAILABLE and SemanticExpander:
            expander = SemanticExpander()
            
            # 扩展核心词
            treasury_expanded = expander.build_expanded_query(
                "treasury wine", mode=mode, include_original=True
            )
            penfolds_expanded = expander.build_expanded_query(
                "penfolds", mode=mode, include_original=True
            )
            
            # 标题搜索：核心品牌 + 语义扩展
            title_terms = [treasury_expanded, penfolds_expanded]
            # 去重并合并
            all_title_terms = []
            for term_group in title_terms:
                if " OR " in term_group:
                    all_title_terms.append(term_group)
                else:
                    all_title_terms.append(f'"{term_group}"')
            
            title_expr = " OR ".join(all_title_terms)
            query.add_condition(title_expr, SearchField.TITLE)
        else:
            # 回退到普通搜索
            query.add_title_keyword("treasury wine OR penfolds")
        
        # 全文必须包含业务相关词
        query.add_condition(
            "business OR acquisition OR merger OR strategy OR wine industry",
            SearchField.ALL_TEXT, 
            BooleanOperator.AND
        )
        
        return query


def create_semantic_search(keyword: str, 
                          mode: str = "moderate",
                          field: SearchField = SearchField.ALL_TEXT) -> AdvancedSearchQuery:
    """
    创建语义增强的搜索查询
    
    Args:
        keyword: 原始关键词
        mode: 语义扩展模式
        field: 搜索字段
    
    Returns:
        AdvancedSearchQuery对象
    
    Example:
        >>> query = create_semantic_search("treasury wine", mode="moderate")
        >>> print(query.build_url())
    """
    builder = SemanticSearchQuery(semantic_mode=mode)
    return builder.build_query(keyword, field)


# 使用示例
if __name__ == "__main__":
    print("=" * 80)
    print("NewsBank Advanced Search Query Builder - Examples")
    print("=" * 80)
    
    # 示例1: 基础搜索
    print("\n[示例1] 基础关键词搜索")
    print("-" * 50)
    query1 = AdvancedSearchQuery()
    query1.add_keyword("treasury wine estates")
    print(query1.get_search_summary())
    print(f"\nURL:\n{query1.build_url()[:150]}...")
    
    # 示例2: 精确标题搜索
    print("\n\n[示例2] 精确标题搜索（多词组合）")
    print("-" * 50)
    query2 = AdvancedSearchQuery()
    query2.add_title_keyword("penfold*")  # 通配符匹配 penfolds/penfold
    query2.add_condition("treasury", SearchField.ALL_TEXT, BooleanOperator.AND)
    query2.add_condition("merger OR acquisition", SearchField.ALL_TEXT, BooleanOperator.AND)
    print(query2.get_search_summary())
    print(f"\nURL:\n{query2.build_url()[:200]}...")
    
    # 示例3: 使用预设模板
    print("\n\n[示例3] 预设模板 - Treasury Wine并购主题")
    print("-" * 50)
    query3 = SearchTemplates.treasury_wine_mergers()
    print(query3.get_search_summary())
    print(f"\nURL:\n{query3.build_url()[:250]}...")
    
    # 示例4: 词形变化
    print("\n\n[示例4] 词形变化搜索")
    print("-" * 50)
    query4 = AdvancedSearchQuery()
    query4.add_variations("penfold", ["penfolds", "penfold", "penfold's"], SearchField.TITLE)
    query4.add_condition("wine", SearchField.ALL_TEXT, BooleanOperator.AND)
    print(query4.get_search_summary())
    print(f"\nURL:\n{query4.build_url()}")
    
    # 示例5: 语义搜索（如果可用）
    if SEMANTIC_AVAILABLE:
        print("\n\n[示例5] 语义扩展搜索")
        print("-" * 50)
        print("启用语义扩展: treasury wine → penfolds, australian wine, wine industry...")
        
        semantic_builder = SemanticSearchQuery(semantic_mode="moderate")
        query5 = semantic_builder.build_query("treasury wine", SearchField.TITLE)
        print(query5.get_search_summary())
        print(f"\n语义扩展信息:")
        print(semantic_builder.get_expansion_info("treasury wine"))
        print(f"\nURL:\n{query5.build_url()[:300]}...")
        
        # 示例6: 使用语义模板
        print("\n\n[示例6] 语义模板 - Treasury Wine语义增强")
        print("-" * 50)
        query6 = SemanticSearchTemplates.treasury_wine_semantic(mode="moderate")
        print(query6.get_search_summary())
        print(f"\nURL:\n{query6.build_url()[:300]}...")
    else:
        print("\n\n[提示] 语义扩展模块未安装，跳过示例5-6")
        print("要启用语义搜索，请确保 semantic_expansion.py 在当前目录")
    
    print("\n\n" + "=" * 80)
    print("所有示例生成成功！")
    print("=" * 80)
