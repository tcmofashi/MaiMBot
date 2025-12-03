#!/usr/bin/env python3
"""
MaiMBot 完整 API 集成测试

创建时间: 2025-11-27 23:39:40
最后修改: 2025-11-29 01:21:01
AI生成标识: Cline
测试类型: 集成测试

功能描述:
- 完整的用户注册、登录、获取信息流程
- 自动从注册响应中提取 tenant_id 等关键信息
- 支持后续 API 调用使用提取的信息
- 所有结果自动保存到 JSON 文件
"""

import os
import sys
from typing import Optional, Dict, Any, Tuple
import json as _json
import urllib.parse as _urlparse
import urllib3
from datetime import datetime

# 添加项目根目录到路径，确保测试文件在任何目录下都可执行
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)


def call_rest_api(
    port: int,
    path: str = "/",
    method: str = "GET",
    host: str = "127.0.0.1",
    scheme: str = "http",
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    json: Optional[Any] = None,
    data: Optional[Any] = None,
    timeout: float = 10.0,
) -> Tuple[int, Dict[str, str], bytes]:
    """对指定端口的服务发送 RESTful API 请求"""
    if not path.startswith("/"):
        path = "/" + path

    query = _urlparse.urlencode(params or {}, doseq=True)
    netloc = f"{host}:{port}"
    url = _urlparse.urlunparse(
        (
            scheme,
            netloc,
            path,
            "",  # params (deprecated)
            query,
            "",  # fragment
        )
    )

    hdrs: Dict[str, str] = dict(headers or {})

    body: Optional[bytes] = None
    if json is not None:
        hdrs.setdefault("Content-Type", "application/json; charset=utf-8")
        body = _json.dumps(json, ensure_ascii=False).encode("utf-8")
    elif data is not None:
        if isinstance(data, dict):
            hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded; charset=utf-8")
            body = _urlparse.urlencode(data, doseq=True).encode("utf-8")
        elif isinstance(data, str):
            body = data.encode("utf-8")
        elif isinstance(data, (bytes, bytearray)):
            body = bytes(data)
        else:
            # 兜底：未知类型，按 JSON 文本发送
            hdrs.setdefault("Content-Type", "application/json; charset=utf-8")
            body = _json.dumps(data, ensure_ascii=False).encode("utf-8")

    http = urllib3.PoolManager()
    try:
        resp = http.request(
            method.upper(),
            url,
            body=body,
            headers=hdrs or None,
            timeout=urllib3.util.Timeout(total=timeout),
        )
        resp_headers = {k: v for k, v in resp.headers.items()}
        return resp.status, resp_headers, resp.data
    finally:
        try:
            http.clear()
        except Exception:
            pass


def api_call_with_result(
    method: str,
    path: str,
    port: int = 18000,
    host: str = "127.0.0.1",
    scheme: str = "http",
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    json: Optional[Any] = None,
    data: Optional[Any] = None,
    timeout: float = 10.0,
) -> Dict[str, Any]:
    """执行 API 调用并返回结构化结果"""
    try:
        status, headers, body = call_rest_api(
            port=port,
            path=path,
            method=method,
            host=host,
            scheme=scheme,
            params=params,
            headers=headers,
            json=json,
            data=data,
            timeout=timeout,
        )

        body_text = body.decode("utf-8", errors="ignore")

        # 尝试解析 JSON 响应体
        try:
            body_json = _json.loads(body_text)
        except:
            body_json = body_text

        result = {
            "endpoint": path,
            "method": method,
            "port": port,
            "status_code": status,
            "headers": dict(headers),
            "body": body_json,
            "success": status >= 200 and status < 300,
        }

        print(f"✓ {method} {path} - 状态码: {status}")
        return result

    except Exception as e:
        error_result = {"endpoint": path, "method": method, "port": port, "error": str(e), "success": False}
        print(f"✗ {method} {path} - 失败: {repr(e)}")
        return error_result


def extract_tenant_info(register_response: Dict[str, Any]) -> Dict[str, str]:
    """从注册响应中提取租户信息"""
    info = {}

    if register_response.get("success") and "body" in register_response:
        body = register_response["body"]
        if isinstance(body, dict) and "user_info" in body:
            user_info = body["user_info"]
            info["tenant_id"] = user_info.get("tenant_id", "")
            info["user_id"] = user_info.get("user_id", "")
            info["access_token"] = body.get("access_token", "")
            info["api_key"] = user_info.get("api_key", "")

    return info


def complete_api_test():
    """完整的 API 测试流程"""
    print("🚀 开始完整的 MaiMBot API 测试流程")
    print("=" * 50)

    # 收集所有测试结果
    results = {"test_run": "完整 API 测试流程", "timestamp": datetime.now().isoformat(), "test_steps": []}

    # 步骤 1: 健康检查
    print("\n❤️ 步骤 1: 健康检查")
    health_result = api_call_with_result(method="GET", path="/api/v1/health")
    results["test_steps"].append({"step": 1, "description": "健康检查", "result": health_result})

    # 步骤 2: 获取 Agent 模板
    print("\n🤖 步骤 2: 获取 Agent 模板")
    templates_result = api_call_with_result(method="GET", path="/api/v1/agents/templates")
    results["test_steps"].append({"step": 2, "description": "获取 Agent 模板", "result": templates_result})

    # 步骤 3: 用户注册
    print("\n📝 步骤 3: 用户注册")
    register_data = {
        "username": "maple123",
        "password": "maple123",
        "email": "maple123@example.com",
        "tenant_name": "mapleの测试租户",
        "tenant_type": "personal",
    }

    register_result = api_call_with_result(method="POST", path="/api/v1/auth/register", json=register_data)
    results["test_steps"].append({"step": 3, "description": "用户注册", "result": register_result})

    # 提取租户信息
    tenant_info = extract_tenant_info(register_result)
    print(f"   提取到的租户信息: {tenant_info}")

    # 步骤 4: 用户登录（使用注册的用户名密码）
    print("\n🔐 步骤 4: 用户登录")
    login_data = {"username": "maple123", "password": "maple123"}

    login_result = api_call_with_result(method="POST", path="/api/v1/auth/login", json=login_data)
    results["test_steps"].append({"step": 4, "description": "用户登录", "result": login_result})

    # 如果登录成功，更新 access_token
    if login_result.get("success") and "body" in login_result:
        body = login_result["body"]
        if isinstance(body, dict) and "access_token" in body:
            tenant_info["access_token"] = body["access_token"]
            print(f"   更新 access_token: {tenant_info['access_token'][:20]}...")

    # 步骤 5: 获取当前用户信息（需要认证）
    print("\n👤 步骤 5: 获取当前用户信息")
    if tenant_info.get("access_token"):
        me_headers = {"Authorization": f"Bearer {tenant_info['access_token']}"}
        me_result = api_call_with_result(method="GET", path="/api/v1/auth/me", headers=me_headers)
        results["test_steps"].append({"step": 5, "description": "获取当前用户信息", "result": me_result})
    else:
        print("   跳过 - 无有效的 access_token")

    # 步骤 6: 获取租户信息
    print("\n🏢 步骤 6: 获取租户信息")
    if tenant_info.get("access_token"):
        tenant_headers = {"Authorization": f"Bearer {tenant_info['access_token']}"}
        tenant_result = api_call_with_result(method="GET", path="/api/v1/tenant", headers=tenant_headers)
        results["test_steps"].append({"step": 6, "description": "获取租户信息", "result": tenant_result})
    else:
        print("   跳过 - 无有效的 access_token")

    # 步骤 7: 获取租户统计信息
    print("\n📊 步骤 7: 获取租户统计信息")
    if tenant_info.get("access_token"):
        stats_headers = {"Authorization": f"Bearer {tenant_info['access_token']}"}
        stats_result = api_call_with_result(method="GET", path="/api/v1/tenant/stats", headers=stats_headers)
        results["test_steps"].append({"step": 7, "description": "获取租户统计信息", "result": stats_result})
    else:
        print("   跳过 - 无有效的 access_token")

    # 步骤 8: 获取 Agent 列表
    print("\n📋 步骤 8: 获取 Agent 列表")
    if tenant_info.get("access_token"):
        agents_headers = {"Authorization": f"Bearer {tenant_info['access_token']}"}
        agents_result = api_call_with_result(method="GET", path="/api/v1/agents", headers=agents_headers)
        results["test_steps"].append({"step": 8, "description": "获取 Agent 列表", "result": agents_result})
    else:
        print("   跳过 - 无有效的 access_token")

    # 步骤 9: 创建 Agent
    print("\n🆕 步骤 9: 创建 Agent")
    if tenant_info.get("access_token"):
        create_agent_headers = {
            "Authorization": f"Bearer {tenant_info['access_token']}",
            "Content-Type": "application/json",
        }
        create_agent_data = {
            "name": "我的测试助手",
            "description": "一个用于测试的友好AI助手",
            "template_id": "friendly_assistant",
        }
        create_agent_result = api_call_with_result(
            method="POST", path="/api/v1/agents", headers=create_agent_headers, json=create_agent_data
        )
        results["test_steps"].append({"step": 9, "description": "创建 Agent", "result": create_agent_result})

        # 提取创建的 Agent ID
        agent_id = ""
        if create_agent_result.get("success") and "body" in create_agent_result:
            body = create_agent_result["body"]
            if isinstance(body, dict) and "agent_id" in body:
                agent_id = body["agent_id"]
                tenant_info["created_agent_id"] = agent_id
                print(f"   创建的 Agent ID: {agent_id}")
    else:
        print("   跳过 - 无有效的 access_token")

    # 步骤 10: 调用 Agent 聊天功能
    print("\n💬 步骤 10: 调用 Agent 聊天功能")
    if tenant_info.get("access_token") and tenant_info.get("created_agent_id"):
        chat_headers = {"Authorization": f"Bearer {tenant_info['access_token']}", "Content-Type": "application/json"}
        chat_data = {
            "message": "你好，请介绍一下你自己",
            "agent_id": tenant_info["created_agent_id"],
            "platform": "web",
            "user_id": "test_user_001",
        }
        chat_result = api_call_with_result(
            method="POST", path="/api/v2/chat/auth", headers=chat_headers, json=chat_data
        )
        results["test_steps"].append({"step": 10, "description": "调用 Agent 聊天功能", "result": chat_result})

        # 显示聊天响应
        if chat_result.get("success") and "body" in chat_result:
            body = chat_result["body"]
            if isinstance(body, dict) and "data" in body:
                response_data = body["data"]
                if "response" in response_data:
                    print(f"   Agent 回复: {response_data['response']}")
    else:
        print("   跳过 - 无有效的 access_token 或 Agent ID")

    # 保存提取的租户信息
    results["extracted_tenant_info"] = tenant_info

    # 自动保存到 JSON 文件
    import os

    results_dir = "MaiM_api_sever_test/test_data/api_tests"
    os.makedirs(results_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"complete_api_integration_test_results_{timestamp}.json"
    output_path = os.path.join(results_dir, output_file)

    with open(output_path, "w", encoding="utf-8") as f:
        _json.dump(results, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 50)
    print("✅ 测试完成！")
    print(f"📁 结果已保存到: {output_path}")
    print("🔑 提取的租户信息:")
    for key, value in tenant_info.items():
        if value:
            print(f"   {key}: {value}")

    return results


if __name__ == "__main__":
    complete_api_test()
