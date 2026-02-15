# -*- coding: utf-8 -*-
"""
测试语义搜索功能
"""

from semantic_expansion import SemanticExpander, expand_keywords, get_related_terms
from newsbank_search_builder import (
    SemanticSearchQuery, create_semantic_search, 
    SearchField, SEMANTIC_AVAILABLE
)

print("=" * 80)
print("语义搜索功能测试")
print("=" * 80)

# 测试1: 基础语义扩展
print("\n[测试1] 基础语义扩展")
print("-" * 50)
expander = SemanticExpander()

keywords = ["treasury wine", "penfolds", "acquisition"]
for kw in keywords:
    print(f"\n关键词: '{kw}'")
    related = get_related_terms(kw, max_terms=5)
    print(f"  相关词: {', '.join(related)}")

# 测试2: 不同扩展模式
print("\n\n[测试2] 不同扩展模式对比")
print("-" * 50)
test_keyword = "treasury wine"

for mode in ["conservative", "moderate", "aggressive"]:
    print(f"\n模式: {mode}")
    expanded = expand_keywords(test_keyword, mode=mode)
    print(f"  扩展结果: {expanded[:100]}...")

# 测试3: 语义搜索查询构建
print("\n\n[测试3] 语义搜索查询构建")
print("-" * 50)

if SEMANTIC_AVAILABLE:
    query = create_semantic_search("treasury wine", mode="moderate")
    print("搜索配置:")
    print(query.get_search_summary())
    print(f"\nURL: {query.build_url()[:200]}...")
else:
    print("语义搜索不可用")

# 测试4: 语义搜索构建器
print("\n\n[测试4] 语义搜索构建器")
print("-" * 50)

if SEMANTIC_AVAILABLE:
    builder = SemanticSearchQuery(semantic_mode="moderate")
    query = builder.build_query("penfolds", SearchField.TITLE)
    print("扩展信息:")
    print(builder.get_expansion_info("penfolds"))
    print(f"\nURL: {query.build_url()[:200]}...")

print("\n" + "=" * 80)
print("测试完成！")
print("=" * 80)

print("\n使用建议:")
print("1. conservative模式: 适合精确搜索，扩展少但准确")
print("2. moderate模式: 平衡精确度和召回率（推荐）")
print("3. aggressive模式: 适合初步探索，扩展多但可能有噪音")
print("\n运行示例:")
print("  python newsbank_semantic.py 'treasury wine' --semantic-mode moderate")
print("  python newsbank_semantic.py 'penfolds' --semantic-mode aggressive --max-pages 5")
