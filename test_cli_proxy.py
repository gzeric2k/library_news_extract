# -*- coding: utf-8 -*-
"""
CLI Proxy 集成测试脚本
测试 cli_proxy_client.py 是否能正确调用 cli-proxy-api.exe

使用方法:
    1. 确保 cli-proxy-api.exe 正在运行 (如 http://localhost:8080)
    2. 在 .env 文件中设置 CLI_PROXY_ENABLED=true
    3. 运行: python test_cli_proxy.py

作者: AI Assistant
日期: 2026-02-15
"""

import os
import sys

# 加载 .env 文件
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 导入 CLI Proxy Client
try:
    from cli_proxy_client import CLIProxyClient, is_proxy_available
    CLI_PROXY_AVAILABLE = True
except ImportError as e:
    print(f"[错误] 无法导入 cli_proxy_client: {e}")
    CLI_PROXY_AVAILABLE = False
    sys.exit(1)


def test_cli_proxy_connection():
    """测试 CLI Proxy 连接"""
    print("=" * 70)
    print("CLI Proxy 连接测试")
    print("=" * 70)

    # 获取配置
    proxy_url = os.getenv("CLI_PROXY_URL", "http://localhost:8080/v1")
    proxy_model = os.getenv("CLI_PROXY_MODEL", "local-model")
    proxy_enabled = os.getenv("CLI_PROXY_ENABLED", "false").lower() == "true"

    print(f"\n[配置信息]")
    print(f"  CLI_PROXY_ENABLED: {proxy_enabled}")
    print(f"  CLI_PROXY_URL: {proxy_url}")
    print(f"  CLI_PROXY_MODEL: {proxy_model}")

    # 快速检测
    print(f"\n[快速检测]")
    if is_proxy_available(proxy_url):
        print(f"  ✓ CLI Proxy 服务在线 ({proxy_url})")
    else:
        print(f"  ✗ CLI Proxy 服务未检测到")
        print(f"\n请确保 cli-proxy-api.exe 正在运行并监听 {proxy_url}")
        return False

    # 创建客户端
    print(f"\n[创建客户端]")
    try:
        client = CLIProxyClient(base_url=proxy_url)
        print(f"  ✓ 客户端创建成功")
    except Exception as e:
        print(f"  ✗ 客户端创建失败: {e}")
        return False

    # 检测连接
    print(f"\n[连接检测]")
    is_online, message = client.check_connection()
    if is_online:
        print(f"  ✓ {message}")
    else:
        print(f"  ✗ {message}")
        return False

    # 获取模型列表
    print(f"\n[获取模型列表]")
    try:
        models = client.list_models()
        if models:
            print(f"  ✓ 发现 {len(models)} 个模型:")
            for model in models[:5]:  # 只显示前5个
                model_id = model.get('id', 'unknown')
                print(f"    - {model_id}")
            if len(models) > 5:
                print(f"    ... 还有 {len(models) - 5} 个模型")
        else:
            print(f"  ! 未获取到模型列表（可能 API 不支持）")
    except Exception as e:
        print(f"  ! 获取模型列表失败: {e}")

    return True


def test_chat_completion():
    """测试聊天完成功能"""
    print("\n" + "=" * 70)
    print("聊天完成测试")
    print("=" * 70)

    # 获取配置
    proxy_url = os.getenv("CLI_PROXY_URL", "http://localhost:8080/v1")
    proxy_model = os.getenv("CLI_PROXY_MODEL", "local-model")

    # 创建客户端
    client = CLIProxyClient(base_url=proxy_url)

    # 测试简单对话
    print(f"\n[测试 1: 简单对话]")
    try:
        response = client.chat.completions.create(
            model=proxy_model,
            messages=[
                {"role": "user", "content": "Say 'Hello from CLI Proxy' and nothing else."}
            ],
            temperature=0.1,
            max_tokens=20
        )

        content = response.choices[0].message.content
        print(f"  请求: Say 'Hello from CLI Proxy' and nothing else.")
        print(f"  响应: {content}")
        print(f"  ✓ 测试成功")

    except Exception as e:
        print(f"  ✗ 测试失败: {e}")
        return False

    # 测试系统消息
    print(f"\n[测试 2: 系统消息]")
    try:
        response = client.chat.completions.create(
            model=proxy_model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "What is 2+2? Answer with just the number."}
            ],
            temperature=0.1,
            max_tokens=10
        )

        content = response.choices[0].message.content
        print(f"  请求: What is 2+2?")
        print(f"  响应: {content}")
        print(f"  ✓ 测试成功")

    except Exception as e:
        print(f"  ✗ 测试失败: {e}")
        return False

    # 测试中文
    print(f"\n[测试 3: 中文对话]")
    try:
        response = client.chat.completions.create(
            model=proxy_model,
            messages=[
                {"role": "user", "content": "你好，请回复'你好，世界'"}
            ],
            temperature=0.1,
            max_tokens=20
        )

        content = response.choices[0].message.content
        print(f"  请求: 你好，请回复'你好，世界'")
        print(f"  响应: {content}")
        print(f"  ✓ 测试成功")

    except Exception as e:
        print(f"  ✗ 测试失败: {e}")
        return False

    return True


def test_with_llm_filter():
    """测试与 LLMArticleFilter 的集成"""
    print("\n" + "=" * 70)
    print("LLMArticleFilter 集成测试")
    print("=" * 70)

    try:
        from newsbank_ai_downloader import LLMArticleFilter
    except ImportError as e:
        print(f"[错误] 无法导入 LLMArticleFilter: {e}")
        return False

    # 获取配置
    proxy_url = os.getenv("CLI_PROXY_URL", "http://localhost:8080/v1")
    proxy_model = os.getenv("CLI_PROXY_MODEL", "local-model")

    print(f"\n[创建 LLMArticleFilter 实例]")
    print(f"  Provider: cli-proxy")
    print(f"  URL: {proxy_url}")
    print(f"  Model: {proxy_model}")

    try:
        llm_filter = LLMArticleFilter(
            api_key="dummy-key",
            model=proxy_model,
            base_url=proxy_url,
            provider="cli-proxy",
            relevance_threshold=0.4
        )
        print(f"  ✓ 创建成功")
    except Exception as e:
        print(f"  ✗ 创建失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 检测 API 连接
    print(f"\n[检测 API 连接]")
    is_online, message = llm_filter.check_api_connection()
    if is_online:
        print(f"  ✓ {message}")
    else:
        print(f"  ✗ {message}")
        return False

    return True


def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("CLI Proxy 集成测试套件")
    print("=" * 70)
    print("\n此测试脚本将验证 cli_proxy_client 是否能正确调用")
    print("cli-proxy-api.exe 提供的本地 AI 模型服务。")
    print("\n请确保:")
    print("  1. cli-proxy-api.exe 正在运行")
    print("  2. 服务监听在配置的地址 (默认: http://localhost:8080)")

    # 运行测试
    results = []

    # 测试 1: 连接测试
    results.append(("连接测试", test_cli_proxy_connection()))

    # 测试 2: 聊天完成
    results.append(("聊天完成", test_chat_completion()))

    # 测试 3: LLMArticleFilter 集成
    results.append(("LLMArticleFilter 集成", test_with_llm_filter()))

    # 汇总结果
    print("\n" + "=" * 70)
    print("测试结果汇总")
    print("=" * 70)

    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"  {name}: {status}")

    all_passed = all(r for _, r in results)

    if all_passed:
        print(f"\n🎉 所有测试通过!")
        print(f"\n您现在可以在 .env 文件中设置:")
        print(f"  CLI_PROXY_ENABLED=true")
        print(f"\n然后运行 newsbank_ai_downloader.py 来使用本地 AI 模型。")
    else:
        print(f"\n⚠️ 部分测试失败")
        print(f"\n请检查:")
        print(f"  1. cli-proxy-api.exe 是否正在运行")
        print(f"  2. 配置是否正确 (URL、端口)")
        print(f"  3. API 是否兼容 OpenAI 格式")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
