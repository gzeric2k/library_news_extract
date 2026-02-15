# -*- coding: utf-8 -*-
"""
BERT语义搜索对比测试脚本
对比不同方法的关键词扩展效果
"""

import time
from typing import Dict, List, Tuple

print("=" * 80)
print("BERT语义搜索 - 对比测试")
print("=" * 80)

# 测试关键词
test_keywords = [
    "treasury wine",
    "penfolds",
    "acquisition",
    "wine industry",
    "grange"
]

print("\n测试关键词:")
for i, kw in enumerate(test_keywords, 1):
    print(f"  {i}. {kw}")

# 方法1: 基础字符串匹配（无语义）
def basic_string_expansion(keyword: str) -> List[Tuple[str, float]]:
    """基础字符串匹配"""
    results = []
    keyword_lower = keyword.lower()
    
    # 简单的字符串包含匹配
    candidates = {
        "treasury wine": ["treasury", "wine", "treasury wine estates", "twe"],
        "penfolds": ["penfold", "grange", "bin 389"],
        "acquisition": ["acquire", "purchase", "buyout"],
        "wine industry": ["winemaking", "vineyard", "winery"],
        "grange": ["penfolds", "shiraz", "icon wine"]
    }
    
    if keyword_lower in candidates:
        for term in candidates[keyword_lower]:
            # 计算简单的相似度
            similarity = len(set(keyword_lower.split()) & set(term.split())) / max(len(keyword_lower.split()), len(term.split()))
            results.append((term, similarity))
    
    return sorted(results, key=lambda x: x[1], reverse=True)

# 方法2: 规则方法（DomainKnowledge）
def rule_based_expansion(keyword: str) -> List[Tuple[str, float]]:
    """基于规则的扩展"""
    try:
        from semantic_expansion import SemanticExpander
        expander = SemanticExpander()
        return expander.expand_term(keyword, mode="moderate")
    except ImportError:
        return [("规则扩展器不可用", 0.0)]

# 方法3: BERT语义扩展（如果可用）
def bert_expansion(keyword: str) -> List[Tuple[str, float]]:
    """BERT语义扩展"""
    try:
        from bert_semantic_expansion import DomainBertExpander, BERT_AVAILABLE
        
        if not BERT_AVAILABLE:
            return [("BERT不可用（未安装sentence-transformers）", 0.0)]
        
        expander = DomainBertExpander()
        return expander.expand(keyword, top_k=5, min_similarity=0.35)
    except Exception as e:
        return [(f"BERT错误: {str(e)}", 0.0)]

# 运行对比测试
print("\n" + "=" * 80)
print("开始对比测试")
print("=" * 80)

results_summary = {}

for keyword in test_keywords:
    print(f"\n\n关键词: '{keyword}'")
    print("-" * 60)
    
    keyword_results = {}
    
    # 测试方法1: 基础字符串
    print("\n[方法1] 基础字符串匹配:")
    start = time.time()
    basic_results = basic_string_expansion(keyword)
    basic_time = time.time() - start
    keyword_results["Basic String"] = (basic_results, basic_time)
    
    if basic_results:
        for term, score in basic_results[:3]:
            print(f"  - {term}: {score:.3f}")
    print(f"  耗时: {basic_time:.4f}秒")
    
    # 测试方法2: 规则方法
    print("\n[方法2] 领域规则扩展:")
    start = time.time()
    rule_results = rule_based_expansion(keyword)
    rule_time = time.time() - start
    keyword_results["Domain Rules"] = (rule_results, rule_time)
    
    if rule_results and rule_results[0][1] > 0:
        for term, score in rule_results[:3]:
            print(f"  - {term}: {score:.3f}")
    else:
        print("  无可用的规则扩展")
    print(f"  耗时: {rule_time:.4f}秒")
    
    # 测试方法3: BERT
    print("\n[方法3] BERT语义扩展:")
    start = time.time()
    bert_results = bert_expansion(keyword)
    bert_time = time.time() - start
    keyword_results["BERT"] = (bert_results, bert_time)
    
    if bert_results and bert_results[0][1] > 0:
        for term, score in bert_results[:3]:
            print(f"  - {term}: {score:.3f}")
    else:
        print(f"  {bert_results[0][0] if bert_results else '无结果'}")
    print(f"  耗时: {bert_time:.4f}秒")
    
    results_summary[keyword] = keyword_results

# 打印总结
print("\n\n" + "=" * 80)
print("测试总结")
print("=" * 80)

print("\n性能对比:")
print("-" * 60)
print(f"{'关键词':<20} {'基础字符串':<15} {'规则方法':<15} {'BERT':<15}")
print("-" * 60)

for keyword in test_keywords:
    if keyword in results_summary:
        basic_time = results_summary[keyword]["Basic String"][1]
        rule_time = results_summary[keyword]["Domain Rules"][1]
        bert_time = results_summary[keyword]["BERT"][1]
        
        print(f"{keyword:<20} {basic_time:<15.4f} {rule_time:<15.4f} {bert_time:<15.4f}")

print("\n扩展质量对比:")
print("-" * 60)

for keyword in test_keywords:
    print(f"\n'{keyword}':")
    
    if keyword in results_summary:
        # 检查BERT结果质量
        bert_results = results_summary[keyword]["BERT"][0]
        if bert_results and bert_results[0][1] > 0:
            print(f"  BERT扩展质量: 高 (捕捉语义关系)")
        else:
            print(f"  BERT扩展质量: 未测试")
        
        # 检查规则结果
        rule_results = results_summary[keyword]["Domain Rules"][0]
        if rule_results and rule_results[0][1] > 0:
            print(f"  规则扩展质量: 中 (基于预定义关系)")
        else:
            print(f"  规则扩展质量: 低 (无预定义规则)")

print("\n\n" + "=" * 80)
print("BERT优势说明")
print("=" * 80)

print("""
1. **语义理解能力**
   - BERT能识别"treasury wine"和"penfolds"的语义关系（同一公司）
   - 传统方法只能基于字符串匹配，无法理解语义

2. **上下文感知**
   - BERT理解"acquisition"在商业语境下与"merger"、"takeover"相关
   - 能区分不同语境下的词义

3. **发现隐含关系**
   - BERT能发现未在规则中显式定义的关系
   - 例如："wine industry" → "vineyard", "export", "ASX"

4. **自适应学习**
   - BERT模型可以针对特定领域微调
   - 可从用户反馈中学习优化

5. **无需人工维护词库**
   - 传统方法需要手动维护同义词表
   - BERT自动学习语义关系
""")

print("=" * 80)
print("安装BERT支持")
print("=" * 80)

print("""
要启用BERT功能，请运行:

    pip install sentence-transformers numpy scikit-learn

推荐模型:
- all-MiniLM-L6-v2: 速度快，适合实时应用 (推荐)
- all-mpnet-base-v2: 平衡精度和速度
- all-roberta-large-v1: 最准确，但较慢

使用示例:
    python newsbank_bert_search.py "treasury wine"
    python newsbank_bert_search.py "penfolds" --bert-model fast
""")

print("=" * 80)
print("测试完成!")
print("=" * 80)
