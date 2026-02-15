# NewsBank 智能自动登录配置指南

## 🎯 三种登录方式

本脚本支持三种登录方式，按优先级自动选择：

### 方式1: 已保存的Cookies（推荐）
- 如果之前登录过，cookies会自动保存
- 脚本首先检测cookies是否仍然有效
- 如果有效，直接跳过登录步骤

### 方式2: 自动登录（使用配置文件）
- 在 `.env` 文件中配置登录凭证
- 脚本自动填写表单并登录
- 支持两种登录类型：
  - **Public Library**（图书馆卡号）- 更简单
  - **Library Member**（会员账号）- 需要处理iframe

### 方式3: 手动登录（备用）
- 如果cookies无效且未配置自动登录
- 会打开浏览器让用户手动操作

---

## 📋 快速开始

### 第1步：选择登录方式

编辑 `.env` 文件，选择你的登录方式：

#### 选项A: Public Library（推荐）

```bash
# 复制示例配置文件
copy .env.example .env

# 编辑 .env 文件，设置以下值：
LOGIN_TYPE=public_library
PUBLIC_LIBRARY_CARD=你的图书馆卡号
```

#### 选项B: Library Member

```bash
# 编辑 .env 文件：
LOGIN_TYPE=library_member
LIBRARY_MEMBER_USERNAME=你的用户名
LIBRARY_MEMBER_PASSWORD=你的密码
```

#### 选项C: 手动登录（不使用自动登录）

```bash
# 保持 .env 中的登录配置为空：
# LOGIN_TYPE=
# 或不创建 .env 文件
```

### 第2步：运行脚本

```bash
# 使用自动登录（配置了凭证）
python newsbank_autologin.py "Nick Scali"

# 强制使用cookies（如果有效）
python newsbank_autologin.py "Nick Scali" --headless

# 指定抓取页数
python newsbank_autologin.py "Nick Scali" --max-pages 5
```

---

## 🔧 完整配置选项

### .env 文件示例

```env
# ============================================================
# 自动登录配置
# 警告：此文件包含敏感信息，请妥善保管！
# ============================================================

# 登录方式选择
# 可选值: "library_member" 或 "public_library"
LOGIN_TYPE=public_library

# 方式1: Public Library 登录（推荐，更简单）
PUBLIC_LIBRARY_CARD=123456789

# 方式2: Library Member 登录（通过SSO）
# 注意：此方式需要处理iframe，可能不稳定
LIBRARY_MEMBER_USERNAME=your_username
LIBRARY_MEMBER_PASSWORD=your_password

# 登录超时时间（秒）
LOGIN_TIMEOUT=120

# 是否保存登录后的cookies（推荐开启）
SAVE_COOKIES=true

# 无头模式（true=不显示浏览器窗口，false=显示）
HEADLESS=false

# 最大抓取页数
MAX_PAGES=10

# 输出目录
OUTPUT_DIR=articles
```

---

## 🔄 登录流程说明

脚本会按以下顺序尝试登录：

```
1. 检查已保存的cookies
   └── 有效？→ 使用cookies登录 ✅
   └── 无效？→ 继续下一步

2. 检查是否配置了自动登录
   └── 配置了？→ 尝试自动登录
       └── 成功？→ 登录完成 ✅
       └── 失败？→ 继续下一步
   └── 未配置？→ 继续下一步

3. 检查是否headless模式
   └── 非headless？→ 打开浏览器等待手动登录
       └── 成功？→ 登录完成 ✅
       └── 超时？→ 登录失败 ❌
   └── headless？→ 登录失败 ❌
```

---

## 💡 使用建议

### 首次使用
1. 先运行一次非headless模式
2. 观察自动登录是否成功
3. 成功后，cookies会被保存
4. 之后可以使用 `--headless` 模式

### 日常使用
```bash
# 最简单的方式（自动使用cookies或自动登录）
python newsbank_autologin.py "关键词"

# 完全自动（需要cookies有效或配置了自动登录）
python newsbank_autologin.py "关键词" --headless
```

### 当cookies过期时
1. 脚本会自动检测到cookies无效
2. 如果配置了自动登录，会自动尝试
3. 如果没有配置，会进入手动登录模式

---

## 🔒 安全提示

1. **保护 .env 文件**: 包含敏感信息，不要提交到Git仓库
   ```bash
   # 在 .gitignore 中添加：
   .env
   cookies/
   ```

2. **文件权限**: 在Linux/Mac上设置适当的权限
   ```bash
   chmod 600 .env
   chmod 700 cookies/
   ```

3. **密码安全**: 如果使用自动登录，密码以明文存储在.env文件中

---

## 🐛 故障排除

### 问题1: 自动登录失败

**现象**: 提示"Auto-login failed"

**解决**:
- 检查 `.env` 文件中的凭证是否正确
- 尝试手动登录一次，观察页面结构
- 检查是否选择了正确的 LOGIN_TYPE

### 问题2: Cookies无效

**现象**: 提示"Cookies invalid or expired"

**解决**:
- 这是正常的，cookies会过期
- 脚本会自动尝试其他登录方式
- 或删除 `cookies/newsbank_auth.json` 强制重新登录

### 问题3: 无法找到登录表单

**现象**: 提示"Could not find login form"

**解决**:
- 网站结构可能已更改
- 使用手动登录模式
- 更新脚本中的选择器

---

## 📊 对比：三种方式

| 方式 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| **Cookies** | 最快，最安全 | 会过期 | 日常使用 |
| **Public Library** | 简单可靠 | 需要卡号 | 有图书馆卡 |
| **Library Member** | SSO登录 | iframe复杂 | 有会员账号 |
| **Manual** | 最可靠 | 需要人工 | 其他方式失败 |

---

## 📝 更新日志

### 2026-02-14
- 添加智能自动登录功能
- 支持三种登录方式自动切换
- 添加 .env 配置文件支持
- 优化登录流程和错误处理
