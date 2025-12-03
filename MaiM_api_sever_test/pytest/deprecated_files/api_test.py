# -*- coding: utf-8 -*-
"""
api_test.py

说明:
- 提供一个简单的示例函数 call_rest_api，用于向指定端口的本地/远程服务发送 RESTful API 请求。
- 依赖标准库与 urllib3（requirements.txt 已包含 urllib3），无需额外安装 requests。

使用示例:
1) GET 请求:
    status, headers, body = call_rest_api(
        port=8000,
        path="/health",
        method="GET",
    )
    print(status, headers, body.decode("utf-8", errors="ignore"))

2) POST JSON:
    status, headers, body = call_rest_api(
        port=8000,
        path="/echo",
        method="POST",
        json={"hello": "world"},
    )
    print(status, headers, body.decode("utf-8", errors="ignore"))

注意:
- 请将 port、path 改为你实际服务的端口与路径。
- 若你的服务运行在 HTTPS 或者不是本机，请调整 scheme、host。
"""

from typing import Optional, Dict, Any, Tuple
import json as _json
import urllib.parse as _urlparse
import urllib3
from datetime import datetime


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
    """对指定端口的服务发送 RESTful API 请求（同步示例，基于 urllib3）。

    参数:
      - port: 目标端口，如 8000
      - path: 路径，以 "/" 开头，如 "/api/v1/ping"
      - method: HTTP 方法: GET/POST/PUT/DELETE/PATCH/HEAD
      - host: 主机名，默认 "127.0.0.1"
      - scheme: 协议 "http" 或 "https"
      - params: 查询参数 dict，将被拼接到 URL
      - headers: 额外请求头 dict
      - json: 若提供，将以 application/json 发送
      - data: 发送原始数据；dict 会以 x-www-form-urlencoded 编码，str 将按 utf-8 编码
      - timeout: 超时时间（秒）

    返回:
      (status_code, response_headers, response_body_bytes)
    """
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


def Call_api_get(port: int, path: str):
    """简单演示。需要你的服务在相应端口与路径可用。"""
    try:
        status, headers, body = call_rest_api(
            port,  # 修改为你的服务端口
            path,
            method="GET",
        )
        res = f"{path}请求成功"
        res += f"\tStatus:{status}\nHeaders:,{headers}\nBody:{body.decode('utf-8', errors='ignore')}\n\n"

        return res

    except Exception as e:
        print(f"{path}请求失败:", repr(e))


def Call_api_post(port: int, path: str, json_data: Dict[str, Any]):
    """简单演示POST请求。需要你的服务在相应端口与路径可用。"""
    try:
        status, headers, body = call_rest_api(
            port,  # 修改为你的服务端口
            path,
            method="POST",
            json=json_data,
        )
        res = f"{path} POST请求成功"
        res += f"\tStatus:{status}\nHeaders:,{headers}\nBody:{body.decode('utf-8', errors='ignore')}\n\n"

        return res

    except Exception as e:
        print(f"{path} POST请求失败:", repr(e))


if __name__ == "__main__":
    # 将端口按需修改为你本地正在运行的 API 服务端口，例如 8000/3000/8080 等
    results = {"test_run": "API 测试运行", "timestamp": datetime.now().isoformat(), "results": []}

    # 执行所有请求并自动收集结果
    results["results"].append(Call_api_get(port=18000, path="/health"))
    results["results"].append(Call_api_get(port=18000, path="/docs"))
    results["results"].append(Call_api_get(port=18000, path="/api/v1/agents/templates"))
    results["results"].append(
        Call_api_post(
            port=18000,
            path="/api/v1/auth/register",
            json_data={
                "username": "maple123",
                "password": "maple123",
                "email": "maple123@example.com",
                "tenant_name": "mapleの测试租户",
                "tenant_type": "personal",
            },
        )
    )

    results["results"].append(
        Call_api_post(
            port=18000,
            path="/api/v1/auth/login",
            json_data={"tenant_id": "tenant_20f7f2c47825531a", "username": "maple123", "password": "maple123"},
        )
    )

    results["results"].append(
        Call_api_post(
            port=18000,
            path="/api/v1/auth/me",
            json_data={"tenant_id": "tenant_20f7f2c47825531a", "username": "maple123", "password": "maple123"},
        )
    )

    # 自动保存到 JSON 文件
    with open("api_test_results.json", "w", encoding="utf-8") as f:
        _json.dump(results, f, ensure_ascii=False, indent=2)

    print("测试完成！结果已保存到 api_test_results.json")
