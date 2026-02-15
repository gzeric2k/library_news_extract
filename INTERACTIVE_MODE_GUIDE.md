# NewsBank AI智能下载器 - 交互式模式使用指南

## 功能概述

修改后的 `newsbank_ai_downloader.py` 现在支持**交互式模式**，用户无需在命令行中提供URL，而是在程序启动时通过交互式界面输入。

## 主要改进

### 1. 移除命令行URL参数
- **之前**: `python newsbank_ai_downloader.py "URL"`
- **现在**: `python newsbank_ai_downloader.py` (可选提供URL)

### 2. 交互式URL输入
- 程序启动时提示用户输入URL
- 支持URL验证
- 支持退出选项 (输入 'q')

### 3. URL解析显示
- 自动解析URL中的搜索条件
- 显示搜索主题、条件数量和详细条件

### 4. 参数确认界面
- 显示所有配置参数
- 用户确认后才执行
- 支持取消操作

## 使用方式

### 方式1: 交互式模式（推荐）

```bash
python newsbank_ai_downloader.py
```

**交互流程:**

```
============================================================
NewsBank AI智能下载器
============================================================

请输入NewsBank搜索URL:
(或输入 'q' 退出)
> https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/results?...

[URL解析]
搜索主题: treasury penfolds treasury wine 2014 australian financial review
搜索条件: 3 个
  条件1: Treasury Penfolds Treasury wine (字段: alltext)
  条件2: 2014 (字段: YR)
  条件3: Australian Financial Review (字段: SN)

============================================================
配置参数确认
============================================================

[搜索URL]
  https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/results?...

[AI筛选配置]
  使用 LLM: 是 (NVIDIA API)
  模型: z-ai/glm4.7

[下载配置]
  相关性阈值: 0.4
  最大扫描页数: 10
  最大下载数量: 50

============================================================
是否开始执行? (y/n): y

[开始执行...]
```

### 方式2: 命令行模式（直接指定URL）

```bash
python newsbank_ai_downloader.py "https://infoweb-newsbank-com.ezproxy.sl.nsw.gov.au/apps/news/results?..."
```

- 直接提供URL时，跳过交互式输入
- 仍然显示URL解析和参数确认界面

### 方式3: 跳过参数确认

```bash
python newsbank_ai_downloader.py "URL" --skip-confirm
```

- 直接执行，不显示参数确认界面
- 适合自动化脚本

## 命令行参数

### 位置参数
- `url` (可选): NewsBank搜索URL
  - 不提供时，交互式输入
  - 提供时，直接使用

### AI筛选选项
- `--use-bert`: 使用BERT语义筛选
- `--use-llm`: 使用LLM智能判断
- `--threshold THRESHOLD`: 相关性阈值 (0-1, 默认0.4)
- `--api-key API_KEY`: API Key
- `--llm-model LLM_MODEL`: LLM模型名称

### 下载选项
- `--max-pages MAX_PAGES`: 最大扫描页数 (默认: 10)
- `--download-limit DOWNLOAD_LIMIT`: 最大下载数量 (默认: 50)
- `--interactive`: 下载前确认
- `--headless`: 无头模式
- `--skip-confirm`: 跳过参数确认（直接执行）

## 使用示例

### 示例1: 基础交互式模式
```bash
python newsbank_ai_downloader.py
```

### 示例2: 使用LLM筛选
```bash
python newsbank_ai_downloader.py --use-llm
```

### 示例3: 调整相关性阈值
```bash
python newsbank_ai_downloader.py --threshold 0.3
```

### 示例4: 直接指定URL并跳过确认
```bash
python newsbank_ai_downloader.py "URL" --skip-confirm
```

### 示例5: 只扫描不下载（测试）
```bash
python newsbank_ai_downloader.py --max-pages 1
```

### 示例6: 使用BERT+LLM双重筛选
```bash
python newsbank_ai_downloader.py --use-bert --use-llm
```

## 环境变量配置

在 `.env` 文件中配置：

```
NVIDIA_API_KEY=nvapi-your-key-here
OPENAI_API_KEY=sk-your-key-here
LLM_MODEL=z-ai/glm4.7
RELEVANCE_THRESHOLD=0.4
```

## 新增函数说明

### `_get_interactive_url() -> Optional[str]`
- 交互式获取用户输入的URL
- 验证URL有效性
- 支持退出选项

### `_display_url_analysis(url_analysis: Dict[str, Any]) -> None`
- 显示URL解析结果
- 展示搜索主题和详细条件

### `_display_config_confirmation(...) -> bool`
- 显示参数确认界面
- 返回用户是否确认执行

## 工作流程

```
1. 启动程序
   ↓
2. 获取URL (命令行参数 或 交互式输入)
   ↓
3. 验证URL
   ↓
4. 解析URL并显示信息
   ↓
5. 显示参数确认界面
   ↓
6. 用户确认 (y/n)
   ↓
7. 执行下载
```

## 注意事项

1. **首次使用**: 需要在浏览器中完成登录
2. **登录状态**: 自动保存到 `cookies/newsbank_auth.json`
3. **URL验证**: 必须是有效的NewsBank搜索URL
4. **参数确认**: 默认显示，可用 `--skip-confirm` 跳过
5. **交互式输入**: 支持 'q' 或 'quit' 退出

## 常见问题

### Q: 如何跳过参数确认？
A: 使用 `--skip-confirm` 参数

### Q: 如何在命令行中直接指定URL？
A: `python newsbank_ai_downloader.py "URL"`

### Q: 如何使用LLM筛选？
A: 需要在 `.env` 中设置 API Key，然后使用 `--use-llm` 参数

### Q: 如何调整相关性阈值？
A: 使用 `--threshold` 参数，例如 `--threshold 0.3`

## 修改总结

| 功能 | 修改前 | 修改后 |
|------|--------|--------|
| URL输入 | 必须命令行参数 | 可选，支持交互式 |
| 参数确认 | 无 | 显示确认界面 |
| URL解析显示 | 无 | 显示详细信息 |
| 执行前确认 | 无 | 用户确认后执行 |
| 跳过确认 | N/A | `--skip-confirm` |

