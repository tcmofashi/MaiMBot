#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交互式 API 测试脚本

功能:
- 从 api-index/endpoints.json 加载项目内已整理的 API 端点
- 支持按关键词过滤、按模块筛选、选择要测试的端点
- 交互式输入 Base URL、Headers(Authorization/X-Tenant-ID/X-Agent-ID 等)、Query 参数、Request Body
- 发起请求并以漂亮格式打印响应 (状态码、响应头、JSON/文本)
- 支持保存上一次请求配置到本地文件 (scripts/.api_tester_last.json)

依赖:
- requests (如未安装, 请运行: pip install requests)

用法:
- 直接运行: python scripts/api_tester.py
- 按提示选择端点并输入请求参数
"""

import json
import os
import sys
import time
import re
from typing import Any, Dict, List, Optional, Tuple

ENDPOINTS_JSON_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "api-index", "endpoints.json")
LAST_CONF_PATH = os.path.join(os.path.dirname(__file__), ".api_tester_last.json")


def ensure_requests_available():
    try:
        import requests  # noqa: F401

        return True
    except ImportError:
        print("[ERROR] 未找到 requests 库。请先安装：pip install requests")
        return False


def load_endpoints() -> Dict[str, List[Dict[str, Any]]]:
    if not os.path.exists(ENDPOINTS_JSON_PATH):
        print(f"[ERROR] 未找到端点清单文件: {ENDPOINTS_JSON_PATH}")
        sys.exit(1)
    with open(ENDPOINTS_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {
        "docs_endpoints": data.get("docs_endpoints", []),
        "code_endpoints": data.get("code_endpoints", []),
        "memory_service_endpoints": data.get("memory_service_endpoints", []),
    }


def normalize_endpoint(ep: Dict[str, Any], source_group: str) -> Dict[str, Any]:
    return {
        "method": ep.get("method"),
        "path": ep.get("path"),
        "module": ep.get("module"),
        "source": ep.get("source") or ep.get("file") or source_group,
        "group": source_group,  # docs | code | memory_service
        "router_prefix": ep.get("router_prefix", ""),
    }


def merge_endpoints(raw: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen = set()
    # 优先使用代码端点覆盖文档端点
    order = [("code_endpoints", "code"), ("docs_endpoints", "docs"), ("memory_service_endpoints", "memory_service")]
    for key, group in order:
        for ep in raw.get(key, []):
            n = normalize_endpoint(ep, group)
            # 唯一键: (method, path, group)
            uniq = (n["method"], n["path"], n["group"])
            if uniq in seen:
                continue
            seen.add(uniq)
            merged.append(n)
    return merged


def pretty_json(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        return str(obj)


def print_endpoint_list(endpoints: List[Dict[str, Any]], limit: Optional[int] = None):
    print("\n可选端点列表:")
    count = 0
    for idx, ep in enumerate(endpoints, start=1):
        count += 1
        tag = f"[{ep.get('group')}]"
        print(f"{idx:3d}. {ep['method']:<6} {ep['path']}  {tag}  ({ep.get('module')})")
        if limit and count >= limit:
            break
    print(f"\n共 {len(endpoints)} 个端点。")


def input_with_default(prompt: str, default: Optional[str] = None) -> str:
    if default:
        text = input(f"{prompt} [{default}]: ").strip()
        return text or default
    return input(f"{prompt}: ").strip()


def filter_endpoints(endpoints: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    while True:
        print("\n筛选选项:")
        print("1) 关键词过滤 (path/module)")
        print("2) 按分组过滤 (docs/code/memory_service)")
        print("3) 显示全部")
        print("4) 返回")
        choice = input("选择操作(1-4): ").strip()
        if choice == "1":
            kw = input("输入关键词(支持多个, 空格分隔): ").strip()
            kws = [k.lower() for k in kw.split()] if kw else []

            def match(ep):
                text = f"{ep.get('path', '')} {ep.get('module', '')}".lower()
                return all(k in text for k in kws)

            endpoints = [ep for ep in endpoints if match(ep)]
            print_endpoint_list(endpoints, limit=50)
        elif choice == "2":
            grp = input("输入分组(docs/code/memory_service): ").strip().lower()
            endpoints = [ep for ep in endpoints if ep.get("group") == grp]
            print_endpoint_list(endpoints, limit=50)
        elif choice == "3":
            print_endpoint_list(endpoints, limit=50)
        elif choice == "4":
            return endpoints
        else:
            print("无效选择，请重试。")


def choose_endpoint(endpoints: List[Dict[str, Any]]) -> Dict[str, Any]:
    print_endpoint_list(endpoints, limit=50)
    while True:
        idx_str = input("输入要测试的端点序号(或输入 'f' 进行筛选): ").strip().lower()
        if idx_str == "f":
            endpoints = filter_endpoints(endpoints)
            print_endpoint_list(endpoints, limit=50)
            continue
        if not idx_str.isdigit():
            print("请输入有效的数字。")
            continue
        idx = int(idx_str)
        if idx < 1 or idx > len(endpoints):
            print("序号超出范围。")
            continue
        return endpoints[idx - 1]


def parse_query_params(qs: str) -> Dict[str, str]:
    params: Dict[str, str] = {}
    if not qs:
        return params
    parts = re.split(r"[&\s]+", qs.strip())
    for p in parts:
        if not p:
            continue
        if "=" in p:
            k, v = p.split("=", 1)
            params[k] = v
        else:
            params[p] = ""
    return params


def input_headers() -> Dict[str, str]:
    headers: Dict[str, str] = {}
    print("\n可选快速Headers输入:")
    auth = input_with_default("Authorization(Bearer ...)", "")
    tenant = input_with_default("X-Tenant-ID", "")
    agent = input_with_default("X-Agent-ID", "")
    if auth:
        headers["Authorization"] = auth
    if tenant:
        headers["X-Tenant-ID"] = tenant
    if agent:
        headers["X-Agent-ID"] = agent

    print("是否添加自定义Header? y/N")
    if input().strip().lower() == "y":
        while True:
            kv = input("输入Header(格式: Key=Value，回车结束): ").strip()
            if not kv:
                break
            if "=" in kv:
                k, v = kv.split("=", 1)
                headers[k.strip()] = v.strip()
            else:
                print("格式错误，应为 Key=Value")
    return headers


def input_body(method: str) -> Optional[Any]:
    if method.upper() in ("POST", "PUT", "PATCH"):
        print("\n请求体输入选项:")
        print("1) 直接键入 JSON")
        print("2) 从文件读取 (路径指向 .json)")
        print("3) 空请求体")
        choice = input("选择(1/2/3): ").strip()
        if choice == "1":
            text = input("请输入 JSON 文本: ").strip()
            try:
                return json.loads(text) if text else None
            except Exception as e:
                print(f"[ERROR] JSON 解析失败: {e}")
                return None
        elif choice == "2":
            path = input("文件路径: ").strip()
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[ERROR] 读取文件失败: {e}")
                return None
        else:
            return None
    return None


def save_last_config(conf: Dict[str, Any]):
    try:
        with open(LAST_CONF_PATH, "w", encoding="utf-8") as f:
            json.dump(conf, f, ensure_ascii=False, indent=2)
        print(f"[INFO] 已保存本次配置到 {LAST_CONF_PATH}")
    except Exception as e:
        print(f"[WARN] 保存配置失败: {e}")


def load_last_config() -> Optional[Dict[str, Any]]:
    if not os.path.exists(LAST_CONF_PATH):
        return None
    try:
        with open(LAST_CONF_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] 读取历史配置失败: {e}")
        return None


def perform_request(
    base_url: str, method: str, path: str, headers: Dict[str, str], params: Dict[str, str], body: Optional[Any]
) -> Tuple[int, Dict[str, str], Any]:
    import requests

    url = base_url.rstrip("/") + path
    t0 = time.time()
    try:
        resp = requests.request(
            method=method.upper(), url=url, headers=headers or None, params=params or None, json=body, timeout=30
        )
    except Exception as e:
        print(f"[ERROR] 请求失败: {e}")
        raise
    elapsed = (time.time() - t0) * 1000.0
    print("\n=== 请求信息 ===")
    print(f"URL:      {resp.request.url}")
    print(f"Method:   {method.upper()}")
    print(f"Headers:  {pretty_json(dict(resp.request.headers))}")
    if body is not None:
        print(f"Body:     {pretty_json(body)}")
    print("=== 响应信息 ===")
    print(f"Status:   {resp.status_code}")
    try:
        content_type = resp.headers.get("Content-Type", "")
    except Exception:
        content_type = ""
    print(f"Headers:  {pretty_json(dict(resp.headers))}")
    data: Any
    if "application/json" in content_type.lower():
        try:
            data = resp.json()
            print(f"JSON:     {pretty_json(data)}")
        except Exception:
            text = resp.text
            print(f"Text:     {text[:1000]}")
            data = text
    else:
        text = resp.text
        print(f"Text:     {text[:2000]}")
        data = text
    print(f"Elapsed:  {elapsed:.2f} ms")
    return resp.status_code, dict(resp.headers), data


def main():
    print("== MaiMBot API 交互式测试 ==")
    if not ensure_requests_available():
        sys.exit(1)

    # 读取端点
    raw = load_endpoints()
    endpoints = merge_endpoints(raw)

    # 提供加载上次配置的选项
    last_conf = load_last_config()
    use_last = False
    if last_conf:
        print("检测到历史配置，是否使用? y/N")
        use_last = input().strip().lower() == "y"

    if use_last:
        base_url = last_conf.get("base_url", "http://localhost:8000")
        method = last_conf.get("method", "GET")
        path = last_conf.get("path", "/api/health")
        headers = last_conf.get("headers", {})
        params = last_conf.get("params", {})
        body = last_conf.get("body", None)
        print(f"[INFO] 使用历史配置: {method} {path} @ {base_url}")
    else:
        # 选择端点
        ep = choose_endpoint(endpoints)
        method = ep["method"]
        path = ep["path"]
        print(f"\n选择端点: {method} {path}  (组:{ep.get('group')}, 模块:{ep.get('module')}, 来源:{ep.get('source')})")

        # Base URL
        print("\n输入 Base URL (示例):")
        print("主API后端: http://localhost:8000")
        print("回复后端(bot.py): http://localhost:8095  (仅 v2/chat 等)")
        print("记忆系统独立服务: http://localhost:8001 或自定义")
        default_base = "http://localhost:8000"
        base_url = input_with_default("Base URL", default_base)

        # Headers
        headers = input_headers()

        # Query 参数
        qstr = input_with_default("Query 参数(格式 key=value&key2=value2; 留空则无)", "")
        params = parse_query_params(qstr)

        # Body
        body = input_body(method)

    print(f"\n即将请求: {method} {path} @ {base_url}")
    print("确认执行? y/N")
    if input().strip().lower() != "y":
        print("已取消。")
        sys.exit(0)

    # 执行
    try:
        status_code, resp_headers, data = perform_request(base_url, method, path, headers, params, body)
    except Exception:
        sys.exit(2)

    # 保存本次配置
    save_last_config(
        {
            "base_url": base_url,
            "method": method,
            "path": path,
            "headers": headers,
            "params": params,
            "body": body,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    )

    # 结束
    print("\n=== 测试结束 ===")
    print(f"状态码: {status_code}")


if __name__ == "__main__":
    main()
