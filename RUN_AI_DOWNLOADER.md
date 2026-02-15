# AI智能下载器运行指南

## 🎯 测试URL分析

您提供的URL：
```
https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/results?sort=YMD_date%3AD&p=AWGLNB&hide_duplicates=2&t=favorite%3AAFRWAFRN%21Australian%2520Financial%2520Review%2520Collection/year%3A2014%212014&maxresults=60&f=advanced&val-base-0=Treasury&fld-base-0=Title&bln-base-1=or&val-base-1=Penfolds&fld-base-1=Title&bln-base-2=and&val-base-2=%22Treasury%20wine%22&fld-base-2=alltext
```

### URL参数解析：

**搜索条件：**
1. **Title包含**: "Treasury" OR "Penfolds"
2. **全文包含**: "Treasury wine"
3. **年份**: 2014
4. **来源**: Australian Financial Review

**预期问题：**
- "Treasury" 会匹配政府债券新闻（误报）
- "Penfolds" 可能匹配其他品牌的Penfolds
- 需要AI智能筛选出真正的酒业新闻

---

## 🚀 运行步骤

### 步骤1: 配置环境

```bash
# 1. 确保.env文件存在
copy .env.example .env

# 2. 编辑.env文件，填入NVIDIA API Key
# 打开.env文件，修改这一行：
NVIDIA_API_KEY=nvapi-xxxxxxxxxxxxxxxxxxxxxxxx
```

### 步骤2: 运行AI下载器

```bash
python newsbank_ai_downloader.py "https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/results?sort=YMD_date%3AD&p=AWGLNB&hide_duplicates=2&t=favorite%3AAFRWAFRN%21Australian%2520Financial%2520Review%2520Collection/year%3A2014%212014&maxresults=60&f=advanced&val-base-0=Treasury&fld-base-0=Title&bln-base-1=or&val-base-1=Penfolds&fld-base-1=Title&bln-base-2=and&val-base-2=%22Treasury%20wine%22&fld-base-2=alltext" --use-llm --max-pages 3
```

### 步骤3: 登录（首次）

如果是首次运行：
1. 浏览器窗口会自动打开
2. 在页面中登录NewsBank
3. 登录成功后，程序会自动继续

---

## ⚙️ 推荐参数组合

### 方案A: 严格筛选（推荐）
```bash
python newsbank_ai_downloader.py "URL" --use-llm --threshold 0.5 --max-pages 5
```
- 只下载最相关的文章
- 适合需要高质量结果的场景

### 方案B: 宽松筛选
```bash
python newsbank_ai_downloader.py "URL" --use-llm --threshold 0.3 --max-pages 10
```
- 下载更多文章，包括部分相关的
- 适合需要全面收集的场景

### 方案C: 仅关键词筛选（快速）
```bash
python newsbank_ai_downloader.py "URL" --threshold 0.4 --max-pages 5
```
- 不使用LLM，只使用关键词匹配
- 速度快，不需要API Key

---

## 📊 预期效果

### 无AI筛选时：
- 下载所有包含"Treasury"或"Penfolds"的文章
- 可能包括：政府债券、ASX新闻、其他Penfolds
- **预估下载**: 50-60篇文章
- **相关度**: 约50%

### 有AI筛选后：
- AI会分析每篇文章的实际内容
- 排除：政府Treasury债券、无关ASX新闻
- 保留：真正的Treasury Wine Estates、Penfolds酒业新闻
- **预估下载**: 20-30篇文章
- **相关度**: 约90%

### 节省时间：
- 减少下载：约50%的无用文章
- 减少阅读：直接获得高质量结果
- 节省时间：约60-70%

---

## 🔍 实际运行示例

### 场景1: 您已配置NVIDIA_API_KEY

```bash
$ python newsbank_ai_downloader.py "URL" --use-llm --max-pages 3

===============================================================
NewsBank AI智能下载器
===============================================================
搜索URL: https://infoweb-newsbank-com...
搜索主题: Treasury Penfolds "Treasury wine"

===============================================================
初始化AI智能筛选器
===============================================================
[AI] 检测到NVIDIA API
[AI] 使用NVIDIA API, 模型: z-ai/glm4.7
[AI] 检测到Treasury Wine主题

AI文章选择器配置
============================================================
目标关键词: treasury wine, treasury wine estates, twe, penfolds, penfold, wolf blass, wynns, lindeman, australian wine, wine industry
相关性阈值: 0.4

筛选策略权重:
  关键词匹配: 50%
  LLM判断: 50%
============================================================

[检查登录状态]
[成功] 已登录

[访问搜索页面]
页面标题: Search Results | NewsBank

扫描文章列表
============================================================
[第 1 页]
  找到 60 篇文章
  本页提取: 60 篇

[第 2 页]
  找到 60 篇文章
  本页提取: 60 篇

[第 3 页]
  找到 60 篇文章
  本页提取: 60 篇

AI智能筛选文章
============================================================
[AI] 正在评估 180 篇文章...
[AI] 目标关键词: treasury wine, treasury wine estates, twe, penfolds...
[AI] 相关性阈值: 0.4

[AI筛选结果]
------------------------------------------------------------
总文章数: 180
相关文章: 85
筛选比例: 47.2%

Top 5 最相关文章:
  ✓ [1] Treasury Wine profit rises... (分数: 0.923)
  ✓ [2] Penfolds launches new vintage... (分数: 0.891)
  ✓ [3] Wolf Blass expands... (分数: 0.856)
  ✗ [4] Australian Treasury bonds... (分数: 0.234)
  ✓ [5] TWE acquisition... (分数: 0.812)

开始下载 85 篇相关文章
...

===============================================================
AI智能下载完成
===============================================================
扫描页数: 3
总文章: 180
AI识别相关: 85
成功下载: 85
输出目录: articles_ai
===============================================================
```

---

## 🐛 常见问题

### Q1: 提示找不到NVIDIA_API_KEY

```bash
# 检查.env文件是否存在
dir .env

# 检查Key是否正确设置
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print('Key:', os.getenv('NVIDIA_API_KEY', 'Not Found')[:10])"
```

### Q2: 浏览器没有打开

```bash
# 不要使用--headless（首次运行）
python newsbank_ai_downloader.py "URL" --use-llm

# 如果需要手动登录，不要加--headless
```

### Q3: 下载的文章数量太少

```bash
# 降低阈值，增加页数
python newsbank_ai_downloader.py "URL" --use-llm --threshold 0.3 --max-pages 10
```

### Q4: 想先看看效果再下载

```bash
# 使用test_ai_url.py进行模拟测试
python test_ai_url.py

# 这会展示AI如何筛选文章（不需要API Key）
```

---

## 💡 建议运行流程

### 第1次：测试模式（推荐）

```bash
# 先使用模拟测试（不需要API Key）
python test_ai_url.py

# 这会显示AI会如何筛选文章
```

### 第2次：实际运行

```bash
# 配置好.env后，运行实际下载
python newsbank_ai_downloader.py "URL" --use-llm --max-pages 3 --threshold 0.4
```

### 第3次：根据需要调整

如果结果满意：
```bash
# 增加页数，获取更多结果
python newsbank_ai_downloader.py "URL" --use-llm --max-pages 10
```

如果结果太少：
```bash
# 降低阈值，获取更宽范围
python newsbank_ai_downloader.py "URL" --use-llm --threshold 0.3
```

---

## ✅ 运行前检查清单

- [ ] `.env` 文件已创建：`copy .env.example .env`
- [ ] `.env` 文件中已填入 `NVIDIA_API_KEY`
- [ ] API Key格式正确（以 `nvapi-` 开头）
- [ ] 已安装依赖：`pip install python-dotenv openai playwright`
- [ ] 如果是首次运行，不要加 `--headless`
- [ ] 已准备好复制的NewsBank URL

---

## 🎉 开始运行！

复制以下命令并运行：

```bash
python newsbank_ai_downloader.py "https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/results?sort=YMD_date%3AD&p=AWGLNB&hide_duplicates=2&t=favorite%3AAFRWAFRN%21Australian%2520Financial%2520Review%2520Collection/year%3A2014%212014&maxresults=60&f=advanced&val-base-0=Treasury&fld-base-0=Title&bln-base-1=or&val-base-1=Penfolds&fld-base-1=Title&bln-base-2=and&val-base-2=%22Treasury%20wine%22&fld-base-2=alltext" --use-llm --max-pages 3
```

或者先测试模拟效果：

```bash
python test_ai_url.py
```

**祝使用愉快！AI会帮您筛选出最相关的Treasury Wine文章！** 🤖🍷
