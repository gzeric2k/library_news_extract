# NewsBank AI下载器 .env 配置指南

## 🚀 快速配置（推荐）

### 步骤1: 安装依赖

```bash
pip install python-dotenv openai playwright
```

### 步骤2: 创建.env文件

```bash
# Windows
copy .env.example .env

# Mac/Linux
cp .env.example .env
```

### 步骤3: 编辑.env文件

用文本编辑器打开 `.env` 文件，找到以下行并填入你的API Key：

```bash
# NVIDIA API Key (推荐)
NVIDIA_API_KEY=nvapi-xxxxxxxxxxxxxxxxxxxxxxxx
```

将 `nvapi-xxxxxxxxxxxxxxxxxxxxxxxx` 替换为你从NVIDIA获取的实际API Key。

### 步骤4: 运行程序

```bash
python newsbank_ai_downloader.py "你的URL" --use-llm
```

---

## 📋 .env 文件完整示例

```bash
# ========================================
# AI智能筛选配置
# ========================================

# NVIDIA API Key (推荐，优先使用)
# 获取地址: https://build.nvidia.com/explore/discover
NVIDIA_API_KEY=nvapi-xxxxxxxxxxxxxxxxxxxxxxxx

# OpenAI API Key (备选)
# 获取地址: https://platform.openai.com/api-keys
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx

# ========================================
# LLM配置
# ========================================

# LLM提供商
# 可选: nvidia, openai, auto
# auto会自动检测API Key类型
LLM_PROVIDER=auto

# LLM模型 (仅NVIDIA)
# 推荐: z-ai/glm4.7 (中文理解好)
# 其他: mistralai/mistral-large-3-675b-instruct-2512
#      qwen/qwen3-235b-a22b
LLM_MODEL=z-ai/glm4.7

# ========================================
# 筛选配置
# ========================================

# 相关性阈值 (0.0 - 1.0)
# 0.7 = 严格，只下载最相关文章
# 0.4 = 适中，平衡质量和数量
# 0.2 = 宽松，下载更多文章
RELEVANCE_THRESHOLD=0.4
```

---

## 🎯 配置优先级

配置项的优先级（从高到低）：

1. **命令行参数** (最高)
   ```bash
   python newsbank_ai_downloader.py "URL" --api-key nvapi-xxx --threshold 0.5
   ```

2. **.env文件** (推荐)
   ```bash
   # 在.env文件中
   NVIDIA_API_KEY=nvapi-xxx
   RELEVANCE_THRESHOLD=0.5
   ```

3. **系统环境变量** (备选)
   ```bash
   export NVIDIA_API_KEY=nvapi-xxx
   ```

---

## 🔧 获取NVIDIA API Key

### 步骤1: 注册NVIDIA开发者账号
访问 https://build.nvidia.com/

### 步骤2: 选择模型
点击你想使用的模型，例如：
- `z-ai/glm4.7`
- `mistralai/mistral-large-3-675b-instruct-2512`

### 步骤3: 获取API Key
1. 点击 "Get API Key"
2. 复制生成的Key（格式：`nvapi-xxxxxxxx`）

### 步骤4: 配置到.env
```bash
NVIDIA_API_KEY=nvapi-xxxxxxxx
```

---

## ✅ 配置检查清单

使用AI下载器前，请确认：

- [ ] 已安装 `python-dotenv`: `pip install python-dotenv`
- [ ] 已创建 `.env` 文件: `cp .env.example .env`
- [ ] 已在 `.env` 中填入 `NVIDIA_API_KEY`
- [ ] API Key格式正确（以 `nvapi-` 开头）
- [ ] `.env` 文件和脚本在同一目录

---

## 🆚 .env vs 环境变量

| 方式 | 优点 | 缺点 |
|------|------|------|
| **.env文件** | 持久保存、项目隔离、易于管理 | 需要创建文件 |
| **环境变量** | 全局可用、临时设置 | 关闭终端后失效 |

**推荐：使用 .env 文件**

---

## 🔒 安全提示

1. **不要将.env提交到Git**
   ```bash
   # .gitignore中应该包含
   .env
   ```

2. **保护好你的API Key**
   - 不要分享给他人
   - 不要上传到公开仓库
   - 定期更换

3. **.env.example 是安全的**
   - 示例文件不包含真实Key
   - 可以提交到Git
   - 用于展示配置格式

---

## 🐛 常见问题

### Q1: 程序找不到.env文件

**症状：**
```
[提示] python-dotenv未安装，环境变量需手动设置
```

**解决：**
```bash
pip install python-dotenv
```

### Q2: API Key未生效

**症状：**
```
[警告] 使用LLM需要提供API Key
```

**检查：**
1. `.env` 文件是否在脚本同一目录？
2. 变量名是否拼写正确？（`NVIDIA_API_KEY`）
3. Key是否以 `nvapi-` 开头？

### Q3: 如何验证配置成功？

**测试：**
```bash
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print('Key:', os.getenv('NVIDIA_API_KEY', 'Not Found')[:10] + '...')"
```

---

## 💡 高级用法

### 多个项目不同配置

每个NewsBank项目有自己的.env：

```bash
# 项目1: Treasury Wine研究
cd project1
cp .env.example .env
# 编辑.env设置NVIDIA_API_KEY

# 项目2: 其他主题
cd project2
cp .env.example .env
# 编辑.env使用不同的KEY
```

### 临时覆盖配置

```bash
# 平时使用.env中的配置
python newsbank_ai_downloader.py "URL" --use-llm

# 临时使用不同的阈值
python newsbank_ai_downloader.py "URL" --use-llm --threshold 0.6
```

---

## 📁 项目结构

```
News_Extract/
├── .env                      # ← 你的配置文件（不提交Git）
├── .env.example              # ← 示例文件（可提交Git）
├── .gitignore               # 包含 .env
├── newsbank_ai_downloader.py
└── ...
```

---

## ✅ 完整配置流程

```bash
# 1. 进入项目目录
cd News_Extract

# 2. 安装依赖
pip install python-dotenv openai playwright

# 3. 复制示例文件
copy .env.example .env

# 4. 编辑 .env 文件
# 填入: NVIDIA_API_KEY=nvapi-xxxxxxxx

# 5. 运行程序
python newsbank_ai_downloader.py "你的URL" --use-llm
```

---

**现在使用 .env 文件配置你的API Key，享受AI智能筛选吧！** 🤖✨
