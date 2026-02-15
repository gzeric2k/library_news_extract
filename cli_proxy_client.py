# -*- coding: utf-8 -*-
"""
CLI Proxy API 客户端
通过 HTTP 调用 cli-proxy-api.exe 提供的本地 AI 模型服务

使用方法:
    from cli_proxy_client import CLIProxyClient
    
    client = CLIProxyClient(base_url="http://localhost:8080/v1")
    response = client.chat.completions.create(
        model="local-model",
        messages=[{"role": "user", "content": "你好"}]
    )

环境变量配置 (.env):
    CLI_PROXY_ENABLED=true
    CLI_PROXY_URL=http://localhost:8080/v1
    CLI_PROXY_MODEL=local-model
    CLI_PROXY_TIMEOUT=60

作者: AI Assistant
日期: 2026-02-15
"""

import os
import json
import time
from typing import List, Dict, Any, Optional, Union, Iterator, Tuple
from dataclasses import dataclass, field
import urllib.request
import urllib.error


@dataclass
class Message:
    """聊天消息"""
    role: str
    content: str
    
    def to_dict(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class Choice:
    """聊天完成选项"""
    index: int
    message: Message
    finish_reason: str = "stop"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "message": self.message.to_dict(),
            "finish_reason": self.finish_reason
        }


@dataclass
class Usage:
    """Token 使用情况"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    
    def to_dict(self) -> Dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens
        }


@dataclass
class ChatCompletion:
    """聊天完成响应"""
    id: str
    object: str
    created: int
    model: str
    choices: List[Choice]
    usage: Usage
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "object": self.object,
            "created": self.created,
            "model": self.model,
            "choices": [c.to_dict() for c in self.choices],
            "usage": self.usage.to_dict()
        }


class ChatCompletions:
    """聊天完成接口 (兼容 OpenAI SDK 格式)"""
    
    def __init__(self, client: 'CLIProxyClient'):
        self.client = client
    
    def create(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        top_p: float = 1.0,
        stream: bool = False,
        **kwargs
    ) -> ChatCompletion:
        """
        创建聊天完成请求
        
        Args:
            model: 模型名称
            messages: 消息列表
            temperature: 采样温度
            max_tokens: 最大生成 token 数
            top_p: 核采样参数
            stream: 是否流式输出
            **kwargs: 其他参数
        
        Returns:
            ChatCompletion 对象
        """
        return self.client._chat_completion(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            stream=stream,
            **kwargs
        )


class CLIProxyClient:
    """
    CLI Proxy API 客户端
    
    提供与 OpenAI Python SDK 兼容的接口，用于调用本地 cli-proxy-api.exe 服务
    
    示例:
        client = CLIProxyClient(base_url="http://localhost:8080/v1")
        
        response = client.chat.completions.create(
            model="local-model",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "你好"}
            ]
        )
        
        print(response.choices[0].message.content)
    """
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: int = 60
    ):
        """
        初始化 CLI Proxy 客户端
        
        Args:
            base_url: API 基础 URL (默认从环境变量 CLI_PROXY_URL 读取)
            api_key: API Key (本地服务通常不需要，但保留兼容性)
            timeout: 请求超时时间（秒）
        """
        self.base_url = base_url or os.getenv("CLI_PROXY_URL", "http://localhost:8080/v1")
        self.api_key = api_key or os.getenv("CLI_PROXY_API_KEY", "dummy-key")
        self.timeout = timeout
        
        # 确保 base_url 以 /v1 结尾
        if not self.base_url.endswith("/v1"):
            self.base_url = self.base_url.rstrip("/") + "/v1"
        
        # 初始化聊天完成接口
        self.chat = type('Chat', (), {'completions': ChatCompletions(self)})()
        
        print(f"[CLI Proxy] 初始化客户端: {self.base_url}")
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        发送 HTTP 请求到 CLI Proxy API
        
        Args:
            method: HTTP 方法 (GET, POST 等)
            endpoint: API 端点（不含 base_url）
            data: 请求数据
        
        Returns:
            JSON 响应数据
        """
        url = f"{self.base_url}{endpoint}"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        try:
            if data:
                json_data = json.dumps(data, ensure_ascii=False).encode('utf-8')
                req = urllib.request.Request(
                    url,
                    data=json_data,
                    headers=headers,
                    method=method
                )
            else:
                req = urllib.request.Request(
                    url,
                    headers=headers,
                    method=method
                )
            
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                response_data = response.read().decode('utf-8')
                return json.loads(response_data)
                
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            raise Exception(f"HTTP Error {e.code}: {error_body}")
        except urllib.error.URLError as e:
            raise Exception(f"Connection Error: {e.reason}")
        except json.JSONDecodeError as e:
            raise Exception(f"JSON Decode Error: {e}")
        except Exception as e:
            raise Exception(f"Request Error: {e}")
    
    def _chat_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        top_p: float = 1.0,
        stream: bool = False,
        **kwargs
    ) -> ChatCompletion:
        """
        内部方法：创建聊天完成
        """
        # 构建请求数据
        request_data = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "stream": stream
        }
        
        if max_tokens:
            request_data["max_tokens"] = max_tokens
        
        # 添加其他可选参数
        for key, value in kwargs.items():
            if value is not None:
                request_data[key] = value
        
        # 发送请求
        response_data = self._make_request("POST", "/chat/completions", request_data)
        
        # 解析响应
        return self._parse_chat_completion_response(response_data)
    
    def _parse_chat_completion_response(self, data: Dict[str, Any]) -> ChatCompletion:
        """
        解析聊天完成响应
        """
        # 处理 OpenAI 兼容格式
        if "choices" in data:
            choices = []
            for i, choice_data in enumerate(data.get("choices", [])):
                message_data = choice_data.get("message", {})
                message = Message(
                    role=message_data.get("role", "assistant"),
                    content=message_data.get("content", "")
                )
                choice = Choice(
                    index=choice_data.get("index", i),
                    message=message,
                    finish_reason=choice_data.get("finish_reason", "stop")
                )
                choices.append(choice)
            
            usage_data = data.get("usage", {})
            usage = Usage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0)
            )
            
            return ChatCompletion(
                id=data.get("id", f"chatcmpl-{int(time.time())}"),
                object=data.get("object", "chat.completion"),
                created=data.get("created", int(time.time())),
                model=data.get("model", "unknown"),
                choices=choices,
                usage=usage
            )
        
        # 处理简化格式（直接返回内容）
        elif "content" in data:
            message = Message(role="assistant", content=data["content"])
            choice = Choice(index=0, message=message)
            usage = Usage()
            
            return ChatCompletion(
                id=f"chatcmpl-{int(time.time())}",
                object="chat.completion",
                created=int(time.time()),
                model=data.get("model", "unknown"),
                choices=[choice],
                usage=usage
            )
        
        # 处理文本格式（直接返回字符串）
        elif isinstance(data, str):
            message = Message(role="assistant", content=data)
            choice = Choice(index=0, message=message)
            usage = Usage()
            
            return ChatCompletion(
                id=f"chatcmpl-{int(time.time())}",
                object="chat.completion",
                created=int(time.time()),
                model="unknown",
                choices=[choice],
                usage=usage
            )
        
        else:
            raise Exception(f"Unknown response format: {data}")
    
    def check_connection(self) -> Tuple[bool, str]:
        """
        检查 CLI Proxy API 连接状态
        
        Returns:
            (是否可用, 状态信息)
        """
        try:
            # 尝试获取模型列表
            response = self._make_request("GET", "/models")
            
            if "data" in response or "object" in response:
                models = response.get("data", [])
                model_names = [m.get("id", "unknown") for m in models[:3]]
                return True, f"API 可用 (模型: {', '.join(model_names) if model_names else 'unknown'})"
            else:
                return True, "API 响应正常"
                
        except Exception as e:
            return False, f"连接失败: {str(e)[:100]}"
    
    def list_models(self) -> List[Dict[str, Any]]:
        """
        获取可用模型列表
        
        Returns:
            模型列表
        """
        try:
            response = self._make_request("GET", "/models")
            return response.get("data", [])
        except Exception as e:
            print(f"[警告] 获取模型列表失败: {e}")
            return []


# 为了兼容性，提供与 OpenAI SDK 类似的接口
def create_client(
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: int = 60
) -> CLIProxyClient:
    """
    创建 CLI Proxy 客户端（兼容 OpenAI SDK 风格）
    
    示例:
        client = create_client(base_url="http://localhost:8080/v1")
    """
    return CLIProxyClient(base_url=base_url, api_key=api_key, timeout=timeout)


# 便捷函数：快速检测 CLI Proxy 是否可用
def is_proxy_available(url: Optional[str] = None) -> bool:
    """
    快速检测 CLI Proxy API 是否可用
    
    Args:
        url: API URL (默认从环境变量读取)
    
    Returns:
        是否可用
    """
    url = url or os.getenv("CLI_PROXY_URL", "http://localhost:8080/v1")
    
    try:
        client = CLIProxyClient(base_url=url)
        is_available, _ = client.check_connection()
        return is_available
    except:
        return False


if __name__ == "__main__":
    # 测试代码
    print("=" * 60)
    print("CLI Proxy Client 测试")
    print("=" * 60)
    
    # 从环境变量读取配置
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    proxy_url = os.getenv("CLI_PROXY_URL", "http://localhost:8080/v1")
    proxy_model = os.getenv("CLI_PROXY_MODEL", "local-model")
    
    print(f"\n[配置]")
    print(f"  URL: {proxy_url}")
    print(f"  Model: {proxy_model}")
    
    # 检测连接
    print(f"\n[检测连接]")
    client = CLIProxyClient(base_url=proxy_url)
    is_available, message = client.check_connection()
    
    if is_available:
        print(f"  ✓ {message}")
        
        # 测试聊天
        print(f"\n[测试聊天]")
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
            print(f"  响应: {content}")
            print(f"\n  ✓ 测试成功!")
            
        except Exception as e:
            print(f"  ✗ 测试失败: {e}")
    else:
        print(f"  ✗ {message}")
        print(f"\n请确保 cli-proxy-api.exe 正在运行，并监听 {proxy_url}")
