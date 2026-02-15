# NewsBank Scraper 完整解决方案

## 📦 文件清单

| 文件 | 说明 | 用途 |
|------|------|------|
| `newsbank_autologin.py` | **智能自动登录版** ⭐ | 推荐使用，支持三种登录方式 |
| `newsbank_scraper.py` | 基础生产版 | 之前的版本，支持手动登录 |
| `test_newsbank.py` | 测试脚本 | 开发和测试使用 |
| `cleanup_articles.py` | 清理工具 | 删除非文章文件 |
| `.env.example` | 配置文件模板 | 复制为 `.env` 后配置凭证 |
| `AUTO_LOGIN_GUIDE.md` | 自动登录指南 | 详细配置说明 |
| `README.md` | 基础使用说明 | 快速入门 |

---

## 🚀 快速开始（推荐方式）

### 第1步：配置自动登录（可选但推荐）

```bash
# 1. 复制配置文件
copy .env.example .env

# 2. 编辑 .env 文件，填入你的登录信息（选择其中一种方式）

# 方式A：Public Library（图书馆卡号）
LOGIN_TYPE=public_library
PUBLIC_LIBRARY_CARD=你的卡号

# 方式B：Library Member（会员账号）
LOGIN_TYPE=library_member
LIBRARY_MEMBER_USERNAME=你的用户名
LIBRARY_MEMBER_PASSWORD=你的密码

# 方式C：不配置，使用手动登录
# 保持 LOGIN_TYPE 为空即可
```

### 第2步：运行抓取器

```bash
# 运行智能自动登录版本
python newsbank_autologin.py "Nick Scali"

# 或指定更多参数
python newsbank_autologin.py "Nick Scali" --max-pages 5 --headless
```

---

## 🎯 三种登录方式对比

### ✅ 方式1: 已保存的Cookies（最快）

**工作原理**:
- 首次登录后，cookies自动保存到 `cookies/newsbank_auth.json`
- 下次运行时，脚本首先检查cookies是否有效
- 如果有效，直接跳过登录，立即开始抓取

**适用场景**: 日常使用

**优点**: 
- 最快，无需等待
- 不需要存储密码
- 最安全

**缺点**: 
- Cookies会过期（通常几天到几周）

---

### ✅ 方式2: 自动登录（使用配置文件）

**工作原理**:
- 在 `.env` 文件中配置登录凭证
- 脚本自动打开登录页面、填写表单、提交
- 登录成功后，自动保存cookies供下次使用

**适用场景**: 不想手动操作，有固定凭证

**优点**: 
- 完全自动化
- 适合定时任务
- 可配合 `--headless` 模式

**缺点**: 
- 需要存储凭证（安全风险）
- 如果网站结构改变可能需要更新脚本

**配置示例**:
```env
LOGIN_TYPE=public_library
PUBLIC_LIBRARY_CARD=123456789
```

---

### ✅ 方式3: 手动登录（备用）

**工作原理**:
- 打开浏览器窗口
- 用户手动完成登录流程
- 脚本自动检测登录成功

**适用场景**: 其他方式失败时使用

**优点**: 
- 最可靠
- 不存储任何凭证
- 适用于任何登录方式

**缺点**: 
- 需要人工操作
- 不能用于定时任务

---

## 🔄 智能登录流程

脚本会自动选择最佳的登录方式：

```
┌─────────────────────────────────────────┐
│  开始运行脚本                              │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  检查已保存的cookies                       │
│  cookies/newsbank_auth.json               │
└──────────────┬──────────────────────────┘
               │
      ┌────────┴────────┐
      │                 │
      ▼                 ▼
  ┌────────┐      ┌──────────┐
  │ 有效?  │      │ 无效/无  │
  └───┬────┘      └────┬─────┘
      │                │
      ▼                ▼
  ┌─────────┐    ┌──────────────────┐
  │ 使用    │    │ 检查 .env 配置    │
  │ cookies │    │ LOGIN_TYPE 设置  │
  │ 登录 ✅  │    └────────┬─────────┘
  └─────────┘             │
                   ┌──────┴──────┐
                   │             │
                   ▼             ▼
             ┌─────────┐   ┌─────────┐
             │ 已配置   │   │ 未配置   │
             │ 自动登录 │   │          │
             └────┬────┘   └────┬────┘
                  │             │
                  ▼             ▼
         ┌────────────┐   ┌───────────┐
         │ 尝试自动   │   │ 手动登录   │
         │ 填写表单   │   │ 模式      │
         └─────┬──────┘   └─────┬─────┘
               │                │
        ┌──────┴──────┐        │
        │             │        │
        ▼             ▼        │
   ┌─────────┐  ┌──────────┐   │
   │ 成功?   │  │ 失败     │   │
   └───┬─────┘  └────┬─────┘   │
       │             │         │
       ▼             ▼         ▼
  ┌────────┐   ┌──────────┐
  │ 登录   │   │ 提示用户 │
  │ 完成 ✅ │   │ 手动登录 │
  └────────┘   └──────────┘
```

---

## 📊 使用示例

### 场景1: 首次使用，想配置自动登录

```bash
# 1. 编辑 .env 文件配置凭证
copy .env.example .env
notepad .env  # 填入你的登录信息

# 2. 运行（会先尝试自动登录）
python newsbank_autologin.py "Nick Scali"

# 3. 成功后，cookies会被保存
# 4. 下次运行会更快
```

### 场景2: 已配置自动登录，日常使用

```bash
# 完全自动，包括登录和抓取
python newsbank_autologin.py "关键词" --headless --max-pages 10

# 适合添加到定时任务
```

### 场景3: Cookies过期了

```bash
# 脚本会自动检测并提示
python newsbank_autologin.py "关键词"

# 输出:
# [INFO] Cookies invalid or expired
# [INFO] Attempting auto-login...
# [OK] Auto-login successful!
# [OK] Cookies saved for future use
```

### 场景4: 不想配置自动登录，使用手动

```bash
# 不创建 .env 文件，或保持 LOGIN_TYPE 为空
python newsbank_autologin.py "关键词"

# 输出:
# [INFO] Auto-login not configured
# [INFO] Manual Login Required
# (打开浏览器，等待你手动登录)
```

---

## 🔒 安全建议

### 1. 保护配置文件

```bash
# 在 .gitignore 中添加：
.env
cookies/
articles/
```

### 2. 文件权限（Linux/Mac）

```bash
chmod 600 .env
chmod 700 cookies/
chmod 700 articles/
```

### 3. 密码安全

- 如果使用自动登录，密码以明文存储在 `.env` 中
- 仅在受信任的本地环境使用
- 不要将 `.env` 文件分享给他人
- 定期更换密码

---

## 🐛 故障排除

### 问题1: 自动登录失败

**解决步骤**:
1. 检查 `.env` 文件中的凭证是否正确
2. 确保选择了正确的 `LOGIN_TYPE`
3. 尝试手动登录一次，确认凭证有效
4. 检查网络连接

### 问题2: Cookies频繁过期

**解决步骤**:
1. 这是正常的安全机制
2. 使用自动登录配置，脚本会自动处理
3. 或定期手动登录更新cookies

### 问题3: 找不到搜索框

**解决步骤**:
1. 网站结构可能已更新
2. 使用最新版本的脚本
3. 或联系开发者更新选择器

---

## 🎓 高级用法

### 批量抓取多个关键词

```bash
# 创建脚本 batch_scrape.bat
@echo off
python newsbank_autologin.py "Nick Scali" --max-pages 3
python newsbank_autologin.py "ASX" --max-pages 3
python newsbank_autologin.py "RBA" --max-pages 3
```

### Windows 定时任务

```batch
# 每天凌晨2点运行
schtasks /create /tn "NewsBank Scraper" /tr "python C:\path\to\newsbank_autologin.py '关键词' --headless" /sc daily /st 02:00
```

---

## 📞 需要帮助？

1. 查看详细文档: `AUTO_LOGIN_GUIDE.md`
2. 检查日志输出
3. 确认 `.env` 配置正确
4. 尝试删除 `cookies/newsbank_auth.json` 重新登录

---

## ✨ 特性总结

- ✅ **智能登录检测**: 自动选择最佳登录方式
- ✅ **Cookies持久化**: 登录状态自动保存
- ✅ **自动登录**: 支持配置凭证自动填写
- ✅ **手动备用**: 其他方式失败时可手动登录
- ✅ **翻页抓取**: 支持多页抓取
- ✅ **预览过滤**: 只保存有预览文本的文章
- ✅ **文件清理**: 自动清理非文章内容
- ✅ **错误处理**: 完善的异常处理和日志
- ✅ **配置灵活**: 通过 .env 文件灵活配置
- ✅ **无头模式**: 支持后台运行

---

**准备好开始抓取了！** 🚀

运行: `python newsbank_autologin.py "你的关键词"`
