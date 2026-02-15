# NewsBank 全文抓取 - 防爬虫指南

## ⚠️ 重要提醒

抓取全文会**频繁访问网站**，容易触发反爬虫机制。请遵守以下原则：

## 🛡️ 已实施的防爬虫措施

### 1. 随机延迟 (Random Delays)
```python
# 请求间隔: 3-7秒随机延迟
self.min_delay = 3
self.max_delay = 7
```

### 2. 请求频率限制
```python
# 确保请求间隔
await asyncio.sleep(random.uniform(3, 7))
```

### 3. 重试机制
```python
# 失败时重试3次，每次增加延迟
max_retries = 3
```

### 4. 浏览器伪装
```python
# 禁用自动化检测标志
args=['--disable-blink-features=AutomationControlled']

# 真实User-Agent
user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36...'

# 真实视口大小
viewport={'width': 1920, 'height': 1080}
```

### 5. 人类行为模拟
- 随机浏览时间
- 翻页前额外等待 (5-10秒)
- 文章间延迟 (2-5秒)

## 📊 推荐设置

### 保守模式（最安全）
```bash
# 少量文章，较长延迟
python newsbank_full_article.py "关键词" --max-pages 2 --max-articles 10
```
- 每篇文章间隔: 5-10秒
- 每页间隔: 10-15秒
- 预计时间: 5-10分钟

### 标准模式
```bash
# 中等数量
python newsbank_full_article.py "关键词" --max-pages 3 --max-articles 20
```
- 每篇文章间隔: 3-7秒
- 每页间隔: 5-10秒
- 预计时间: 3-5分钟

## 🚫 避免的爬取行为

### ❌ 不要这样做：
1. **高频请求** - 每秒多次请求
2. **无延迟** - 连续快速抓取
3. **大量并发** - 同时打开多个页面
4. **长时间持续** - 连续抓取数小时
5. **重复抓取** - 短时间内重复相同关键词

### ✅ 应该这样做：
1. **控制速率** - 限制每分钟请求数 < 10
2. **随机延迟** - 使用随机间隔
3. **模拟人类** - 添加鼠标移动、滚动等
4. **分时抓取** - 每次抓取间隔 > 30分钟
5. **限制数量** - 单次抓取不超过50篇文章

## ⚡ 降低被封风险的技巧

### 1. 使用Cookies
```python
# 已登录状态比频繁登录更安全
context = await browser.new_context(storage_state="cookies.json")
```

### 2. 限制抓取量
```python
max_articles = 20  # 不要一次抓取太多
max_pages = 3
```

### 3. 错误处理
```python
try:
    await scrape_article()
except Exception as e:
    # 出错时增加额外延迟
    await asyncio.sleep(10)
```

### 4. 分时运行
```bash
# 不要连续运行，间隔一段时间
# 推荐间隔: 30分钟以上
```

## 🔴 被封的迹象

如果出现以下情况，说明可能被封：
1. ❌ 连续多次请求失败
2. ❌ 返回验证码页面
3. ❌ 页面加载异常缓慢
4. ❌ 被重定向到登录页
5. ❌ 返回403/503错误

## 🟢 解封方法

如果被封：
1. **立即停止** - 停止所有抓取
2. **等待** - 等待30-60分钟
3. **清除cookies** - 删除cookies文件，重新登录
4. **降低速率** - 减少抓取量，增加延迟
5. **更换IP** - 如果有条件，更换网络IP

## 📋 最佳实践

### 单次抓取建议
```bash
# 示例：Treasury wine estates
python newsbank_full_article.py "Treasury wine estates" \
    --max-pages 2 \
    --max-articles 15 \
    --headless  # 可选
```

### 批量抓取建议
```bash
# 不要连续抓取多个关键词
# 推荐间隔30分钟以上

# 第1次
python newsbank_full_article.py "关键词1" --max-articles 10

# 等待30分钟
sleep 1800

# 第2次  
python newsbank_full_article.py "关键词2" --max-articles 10
```

### 定时任务建议
```bash
# 每天最多抓取2-3次
# 推荐时间: 工作时间（模拟正常用户）
# 避免: 凌晨0-6点（容易被检测）
```

## 📊 抓取速率对比

| 模式 | 延迟设置 | 风险等级 | 推荐场景 |
|------|----------|----------|----------|
| **极速** | 0-1秒 | 🔴 高 | ❌ 不推荐 |
| **快速** | 1-3秒 | 🟡 中 | ⚠️ 少量测试 |
| **标准** | 3-7秒 | 🟢 低 | ✅ 日常使用 |
| **保守** | 5-10秒 | 🟢 很低 | ✅ 大量抓取 |
| **极慢** | 10-30秒 | 🟢 极低 | ✅ 敏感场景 |

## ⚖️ 法律与道德

### 合规建议：
1. **查看Robots.txt** - 尊重网站的爬虫协议
2. **遵守服务条款** - 查看NewsBank使用条款
3. **个人使用** - 仅限个人研究，不要商业用途
4. **不传播** - 不要大规模分享抓取内容
5. **适度使用** - 不要对服务器造成负担

## 🆘 紧急停止

如果触发反爬虫，立即：
```python
# 脚本会自动暂停，但也可以手动：
Ctrl + C  # 停止脚本

# 删除cookies，重新开始
rm cookies/newsbank_auth.json
```

## 📞 技术支持

如果遇到问题：
1. 降低抓取速率
2. 减少抓取数量
3. 增加延迟时间
4. 等待后重试

---

**记住：宁可慢，不要被封！**

稳定可持续的低速抓取 > 快速被封
