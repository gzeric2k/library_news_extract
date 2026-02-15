# -*- coding: utf-8 -*-
"""
测试 LLM API 连接检测功能
"""

import os
import sys

# 加载 .env 文件
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 测试导入
print("=" * 70)
print("Test LLM API Connection")
print("=" * 70)

# 检查 openai 包
try:
    import openai
    print("[OK] openai package installed")
except ImportError:
    print("[ERROR] openai package not installed, run: pip install openai")
    sys.exit(1)

# 检查 API Key
api_key = os.getenv("NVIDIA_API_KEY") or os.getenv("OPENAI_API_KEY")
if not api_key:
    print("[ERROR] API Key not found, check .env file")
    print("  Need NVIDIA_API_KEY or OPENAI_API_KEY")
    sys.exit(1)

print(f"[OK] API Key configured ({api_key[:10]}...)")

# 测试 API 连接
print("\nTesting API connection...")
print("-" * 70)

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

provider = "nvidia" if api_key.startswith("nvapi-") else "openai"
base_url = NVIDIA_BASE_URL if provider == "nvidia" else None

print(f"Provider: {provider}")
print(f"Base URL: {base_url or 'default'}")

try:
    # 初始化客户端
    client = openai.OpenAI(
        api_key=api_key,
        base_url=base_url
    )
    
    # 获取模型名称
    if provider == "nvidia":
        model = "meta/llama-3.1-8b-instruct"  # 使用小模型测试
    else:
        model = "gpt-3.5-turbo"
    
    print(f"Test model: {model}")
    print("-" * 70)
    
    # 发送测试请求
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say 'API is working' and nothing else."}
        ],
        temperature=0.1,
        max_tokens=20
    )
    
    if response and response.choices:
        content = response.choices[0].message.content
        print(f"[OK] API connection successful!")
        print(f"  Response: {content}")
        print(f"  Model: {model}")
        print(f"  Provider: {provider}")
    else:
        print("[ERROR] API response abnormal")
        
except openai.AuthenticationError as e:
    print(f"[ERROR] API Key authentication failed")
    print(f"  Error: {e}")
except openai.RateLimitError as e:
    print(f"[ERROR] API rate limit")
    print(f"  Error: {e}")
except openai.APIConnectionError as e:
    print(f"[ERROR] API connection failed")
    print(f"  Error: {e}")
except Exception as e:
    print(f"[ERROR] Unknown error")
    print(f"  Error type: {type(e).__name__}")
    print(f"  Error message: {e}")

print("\n" + "=" * 70)
print("Test completed")
print("=" * 70)
