# NewsBank 语义搜索功能指南

## 新功能概览

我们为您实现了强大的**语义搜索功能**，可以智能扩展搜索关键词，帮助您找到更多相关文章！

### 核心特性

1. **语义扩展**: 输入 "treasury wine" 自动扩展到 "penfolds", "australian wine", "wine industry" 等相关词
2. **多模式选择**: 保守/适中/激进三种扩展强度
3. **领域知识图谱**: 专门针对酒业/商业新闻构建的知识库
4. **智能相似度**: 基于字符串相似度和领域关联度的综合评分

## 快速开始

### 1. 使用语义搜索爬虫（推荐）

```bash
# 基础语义搜索
python newsbank_semantic.py "treasury wine"

# 保守模式（高精确度）
python newsbank_semantic.py "treasury wine" --semantic-mode conservative

# 激进模式（最大化召回率）
python newsbank_semantic.py "penfolds" --semantic-mode aggressive --max-pages 5

# 禁用语义扩展（普通搜索）
python newsbank_semantic.py "treasury wine" --no-semantic
```

### 2. 测试语义扩展效果

```bash
python test_semantic.py
```

## 语义扩展示例

### 示例1: Treasury Wine Estates

**原始关键词**: `treasury wine`

**扩展结果**:
- conservative模式: `treasury wine OR treasury wines OR twe`
- moderate模式: `treasury wine OR treasury wines OR twe OR australian wine`
- aggressive模式: `treasury wine OR treasury wines OR twe OR australian wine OR wine industry OR penfolds`

### 示例2: Penfolds

**原始关键词**: `penfolds`

**扩展结果**:
- conservative模式: `penfolds OR penfold OR penfold's`
- moderate模式: `penfolds OR penfold OR penfold's OR grange`
- aggressive模式: `penfolds OR penfold OR penfold's OR grange OR bin 389 OR shiraz`

### 示例3: 商业术语

**原始关键词**: `acquisition`

**扩展结果**:
- conservative模式: `acquisition OR takeover`
- moderate模式: `acquisition OR takeover OR merger OR purchase`
- aggressive模式: `acquisition OR takeover OR merger OR purchase OR buyout OR deal`

## 扩展模式说明

| 模式 | 扩展数量 | 适用场景 | 精确度 | 召回率 |
|------|---------|---------|--------|--------|
| **conservative** | 最多3个 | 精确搜索 | 高 | 低 |
| **moderate** | 最多5个 | 日常搜索 | 中 | 中 |
| **aggressive** | 最多8个 | 探索性搜索 | 低 | 高 |

## 技术实现

### 领域知识图谱

我们构建了一个专门针对酒业和商业新闻的知识库，包含：

1. **公司-品牌关系**
   - Treasury Wine Estates → Penfolds, Wolf Blass, Wynns, Lindeman's...
   - Penfolds → Grange, Bin 389, Bin 407...

2. **产品类别**
   - Wine → Red wine, White wine, Shiraz, Cabernet Sauvignon...
   - Australian wine → South Australia, Barossa Valley...

3. **行业术语**
   - Business → Acquisition, Merger, Revenue, Profit...
   - Finance → ASX, Annual report, Shareholder...

4. **同义词库**
   - Treasury wine estates ↔ TWE
   - Acquisition ↔ Takeover, Purchase
   - Revenue ↔ Sales, Turnover

### 相似度计算

语义扩展使用多维度相似度计算：

1. **字符串相似度**: 编辑距离（SequenceMatcher）
2. **包含关系**: 词A包含词B给予额外权重
3. **领域关联**: 知识图谱中定义的关系

综合评分 = 字符串相似度 + 包含关系权重 + 领域知识权重

## API使用指南

### 基础用法

```python
from semantic_expansion import expand_keywords, get_related_terms

# 快速扩展
expanded = expand_keywords("treasury wine", mode="moderate")
print(expanded)
# 输出: ("treasury" OR "treasury wine" OR "treasury wines" OR twe) AND ("wine" OR ...)

# 获取相关词
related = get_related_terms("penfolds", max_terms=5)
print(related)
# 输出: ['penfold', "penfold's", 'grange', 'bin 389', 'shiraz']
```

### 高级用法

```python
from semantic_expansion import SemanticExpander

# 创建扩展器
expander = SemanticExpander()

# 获取扩展摘要
summary = expander.get_expansion_summary("treasury wine", mode="moderate")
print(summary)

# 构建扩展查询
query = expander.build_expanded_query("treasury wine", mode="moderate")
print(query)
```

### 与搜索构建器集成

```python
from newsbank_search_builder import (
    SemanticSearchQuery, 
    create_semantic_search,
    SearchField
)

# 方法1: 使用语义搜索构建器
builder = SemanticSearchQuery(semantic_mode="moderate")
query = builder.build_query("treasury wine", SearchField.TITLE)
url = query.build_url()

# 方法2: 便捷函数
query = create_semantic_search("treasury wine", mode="moderate")
url = query.build_url()
```

## 文件结构

```
News_Extract/
├── semantic_expansion.py          # 语义扩展核心模块
├── newsbank_search_builder.py     # 搜索构建器（已集成语义扩展）
├── newsbank_semantic.py           # 语义搜索爬虫
├── test_semantic.py               # 语义功能测试脚本
├── ADVANCED_SEARCH_GUIDE.md       # 高级搜索指南
└── SEMANTIC_SEARCH_GUIDE.md       # 本文件
```

## 最佳实践

### 1. 选择合适的扩展模式

- **初次探索**: 使用 `aggressive` 模式，获得最全面的结果
- **日常搜索**: 使用 `moderate` 模式，平衡精确度和召回率
- **精确查找**: 使用 `conservative` 模式，只获取高度相关的文章

### 2. 组合使用多字段搜索

```python
# 标题使用语义扩展（提高相关性）
query.add_title_keyword(expanded_terms, BooleanOperator.AND)

# 全文使用原始词（确保完整性）
query.add_condition("treasury wine", SearchField.ALL_TEXT, BooleanOperator.AND)
```

### 3. 渐进式搜索策略

```bash
# 第1步: 激进模式探索
python newsbank_semantic.py "treasury wine" --semantic-mode aggressive --max-pages 3

# 第2步: 分析结果，确定相关扩展词

# 第3步: 适中模式精确搜索
python newsbank_semantic.py "treasury wine" --semantic-mode moderate --max-pages 10
```

### 4. 排除噪音

```python
# 使用NOT操作符排除不相关内容
query.exclude_keyword("advertisement", SearchField.TITLE)
query.exclude_keyword("wine review", SearchField.ALL_TEXT)
```

## 性能考虑

1. **扩展计算是本地进行的**，不需要调用外部API
2. **知识库已预加载**，查询响应时间 < 1ms
3. **支持增量更新**，可以动态添加新的领域知识

## 自定义扩展

### 添加新的同义词

```python
from semantic_expansion import DomainKnowledgeBase

kb = DomainKnowledgeBase()

# 添加同义词
kb.synonyms["new term"] = ["synonym1", "synonym2", "synonym3"]

# 添加相关概念
kb.related_concepts["new term"] = ["related1", "related2"]
```

### 创建自定义模板

```python
from newsbank_search_builder import SemanticSearchQuery

class MySearchTemplates:
    @staticmethod
    def my_custom_search(mode="moderate"):
        builder = SemanticSearchQuery(semantic_mode=mode)
        query = builder.build_query("my keyword", SearchField.ALL_TEXT)
        # 添加更多条件...
        return query
```

## 故障排除

### 问题1: 语义扩展未生效

**症状**: 搜索结果与普通搜索相同

**解决**:
```bash
# 检查模块是否可用
python -c "from semantic_expansion import SemanticExpander; print('OK')"

# 测试扩展功能
python test_semantic.py
```

### 问题2: 扩展结果过多噪音

**解决**:
- 切换到 `conservative` 模式
- 使用 `--no-semantic` 暂时禁用扩展
- 添加排除条件

### 问题3: 缺少特定领域的扩展

**解决**:
编辑 `semantic_expansion.py` 中的 `DomainKnowledgeBase` 类，添加：
- 公司-品牌关系
- 同义词
- 相关概念

## 版本历史

### v2.0 - 语义搜索功能
- 添加语义扩展模块
- 实现领域知识图谱
- 集成到搜索构建器
- 新增语义搜索爬虫

## 未来计划

1. **机器学习增强**: 使用词向量模型（Word2Vec/GloVe）提升语义相似度
2. **用户反馈学习**: 根据用户点击行为优化扩展策略
3. **多语言支持**: 扩展到其他语言的新闻搜索
4. **实时更新**: 动态更新知识库

---

**提示**: 所有新功能都与原有系统向后兼容，您可以继续使用旧的爬虫，也可以切换到新的语义搜索功能！
