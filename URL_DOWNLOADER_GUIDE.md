# NewsBank URL直下载工具使用指南

## 🎯 功能简介

这个工具让您可以直接复制NewsBank浏览器中的搜索URL，然后一键下载该搜索结果中的所有文章！

## ✨ 主要特性

- ✅ **直接URL输入** - 复制浏览器地址栏URL即可
- ✅ **URL参数解析** - 自动分析搜索条件
- ✅ **交互式选择** - 手动选择要下载的文章
- ✅ **批量下载** - 自动下载所有优质文章
- ✅ **智能筛选** - 自动识别有预览内容的文章

---

## 🚀 快速开始

### 方法1: 自动下载（推荐）

```bash
python newsbank_url_downloader.py "你的NewsBank URL"
```

工具会自动：
1. 解析URL中的搜索条件
2. 扫描所有文章
3. 下载有预览内容的优质文章

### 方法2: 交互式选择

```bash
python newsbank_url_downloader.py "URL" --interactive
```

交互模式让您可以：
- 查看完整文章列表
- 输入编号选择特定文章
- 输入范围批量选择（如：1,3,5-10）

### 方法3: 仅分析URL

```bash
python newsbank_url_downloader.py "URL" --analyze-only
```

只分析URL参数，不下载文章。

---

## 📖 使用步骤

### 步骤1: 在浏览器中搜索

1. 打开浏览器，访问NewsBank
2. 输入搜索关键词，调整筛选条件
3. 确认搜索结果满意

### 步骤2: 复制URL

1. 在地址栏中选中完整的URL
2. 按 `Ctrl+C` 复制

示例URL：
```
https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/results?p=AWGLNB&fld-base-0=alltext&sort=YMD_date%3AD&maxresults=60&val-base-0=treasury%20wine%20estates
```

### 步骤3: 运行下载工具

```bash
python newsbank_url_downloader.py "粘贴你的URL"
```

---

## 🎮 交互式选择指南

运行命令：
```bash
python newsbank_url_downloader.py "URL" --interactive
```

### 可用命令

| 输入 | 功能 |
|------|------|
| `1,3,5` | 下载第1、3、5篇 |
| `1-10` | 下载第1到10篇 |
| `1,3,5-10` | 下载第1、3篇，以及5到10篇 |
| `all` | 下载所有文章 |
| `quality` | 下载所有优质文章 |
| `q` | 退出 |

### 示例交互

```
[1] ✓ Treasury Wine Estates reports...
[2] ✗ Pages
[3] ✓ Penfolds acquisition deal...

请输入选择: 1,3,5-10
已选择 9 篇文章
开始下载...
```

---

## ⚙️ 命令行参数

```bash
python newsbank_url_downloader.py "URL" [选项]
```

### 常用选项

| 参数 | 说明 | 示例 |
|------|------|------|
| `--max-pages N` | 最大扫描页数 | `--max-pages 5` |
| `--download-limit N` | 最大下载数量 | `--download-limit 20` |
| `--interactive` | 交互式选择 | `--interactive` |
| `--download-all` | 下载所有文章 | `--download-all` |
| `--headless` | 无头模式 | `--headless` |
| `--analyze-only` | 仅分析URL | `--analyze-only` |

### 完整示例

```bash
# 基础使用
python newsbank_url_downloader.py "https://..."

# 限制扫描3页，最多下载20篇
python newsbank_url_downloader.py "URL" --max-pages 3 --download-limit 20

# 交互式选择，无头模式
python newsbank_url_downloader.py "URL" --interactive --headless

# 下载所有文章，不限数量
python newsbank_url_downloader.py "URL" --download-all --download-limit 1000
```

---

## 📊 URL分析示例

运行：
```bash
python newsbank_url_downloader.py "URL" --analyze-only
```

输出示例：
```
URL Analysis Results
============================================================
Original URL: https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/results?...

Base Parameters:
  p: AWGLNB
  hide_duplicates: 2
  maxresults: 60
  f: advanced

Search Conditions (3 total):
  [1] AND alltext: treasury wine estates
  [2] AND Title: penfolds
  [3] OR Title: penfold

Source Filter: AFRWAFRN
Sort Method: Date (Newest First)
Max Results per Page: 60
============================================================
```

---

## 📁 输出文件

下载的文章保存在 `articles_url/` 目录：

```
articles_url/
├── 001_20260215_120000_Treasury_Wine_Estates.txt
├── 002_20260215_120005_Penfolds_Acquisition.txt
├── 003_20260215_120010_Wine_Industry_Report.txt
└── article_list_20260215_120000.json
```

每篇文章文件包含：
- 标题、日期、来源、作者
- 原始搜索URL
- 完整文章内容

---

## 💡 使用技巧

### 技巧1: 先分析再下载

```bash
# 先分析URL
python newsbank_url_downloader.py "URL" --analyze-only

# 确认搜索条件正确后，再下载
python newsbank_url_downloader.py "URL"
```

### 技巧2: 批量下载多个URL

创建 `download_urls.txt`：
```
https://infoweb-newsbank-com...链接1
https://infoweb-newsbank-com...链接2
https://infoweb-newsbank-com...链接3
```

运行批量脚本：
```bash
while read url; do
    python newsbank_url_downloader.py "$url" --max-pages 3
done < download_urls.txt
```

### 技巧3: 筛选特定日期范围

在浏览器中：
1. 设置日期筛选
2. 复制URL
3. 运行下载工具

工具会自动保留日期筛选条件。

---

## 🔧 常见问题

### Q1: URL格式错误

**错误信息：**
```
[错误] URL不是NewsBank的搜索URL
```

**解决：**
- 确保URL来自 `infoweb-newsbank-com.ezproxy.sl.nsw.gov.au`
- 确保URL包含 `/apps/news/results`

### Q2: 需要登录

**现象：**
工具提示需要登录

**解决：**
1. 首次运行不要加 `--headless`
2. 在打开的浏览器窗口中完成登录
3. 登录成功后会自动继续
4. 后续运行会自动使用保存的Cookie

### Q3: 如何获取URL

**步骤：**
1. 在浏览器中访问 NewsBank
2. 输入搜索词，如 "treasury wine estates"
3. 调整筛选条件（日期、来源等）
4. 确认搜索结果满意
5. 复制地址栏中的完整URL

---

## 📋 工作流程对比

### 传统方式
```
打开浏览器 → 搜索关键词 → 逐篇打开文章 → 复制内容 → 保存文件
```

### URL直下载方式
```
打开浏览器 → 搜索关键词 → 复制URL → 运行工具 → 自动下载所有文章
```

**节省时间：约 80-90%**

---

## 🎓 进阶用法

### 与其他工具结合

```bash
# 1. 使用高级搜索构建器生成URL
python newsbank_search_builder.py

# 2. 复制生成的URL

# 3. 使用URL下载器下载
python newsbank_url_downloader.py "生成的URL"
```

### 自动化脚本

```python
# auto_download.py
import subprocess

urls = [
    "https://infoweb-newsbank-com...链接1",
    "https://infoweb-newsbank-com...链接2",
]

for url in urls:
    subprocess.run([
        "python", "newsbank_url_downloader.py",
        url,
        "--max-pages", "3",
        "--download-limit", "20"
    ])
```

---

## ✅ 检查清单

使用前确认：
- [ ] URL是NewsBank搜索结果页
- [ ] URL包含搜索参数（有`?`和`val-base-0=`）
- [ ] 已安装Playwright依赖
- [ ] 首次使用需手动登录

---

**现在就开始使用URL直下载工具吧！**

```bash
python newsbank_url_downloader.py "粘贴你的NewsBank URL"
```
