#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置驱动的一键API自动测试脚本（独立文件）

设计目标:
- 不修改现有 scripts/api_tester.py
- 通过配置文件(config/api_tester.json)进行自动化测试，一次性执行全套用例
- 支持自动登录获取Token并注入Header
- 可选WS测试(需要 websocket-client)
- 在服务未启动时给出可读性提示，并可选择跳过不可达的基础地址

创建时间: 2025-11-27
最后修改: 2025-11-27
AI生成标识: Cline
测试类型: API自动测试
文件类型: API测试
测试模块: src/api/main.py, bot.py
测试功能: API接口自动测试
分类标签: [api_test, auto_test, integration_test]

依赖:
- requests
- websocket-client (如需WS测试)

使用:
- python test_api_auto_tester.py --config config\\api_tester.json
  可选参数:
    --timeout 15         每个请求的超时时间(秒)，默认15
    --fail-fast          首次失败后立即退出(返回非0)
    --skip-check         不进行基础地址可达性预检查
    --list               仅列出将要执行的用例，不实际请求
"""

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# 路径
REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
DEFAULT_CONFIG_PATH = os.path.join(REPO_ROOT, "config", "api_tester.json")

# ------------------------- 工具函数 -------------------------

def ensure_requests_available() -> bool:
    try:
        import requests  # noqa: F401
        return True
    except ImportError:
        print("[ERROR] 未找到 requests 库。请先安装：pip install requests")
        return False

def ensure_ws_available() -> bool:
    try:
        import websocket  # noqa: F401
        return True
    except ImportError:
        return False

def pretty_json(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        return str(obj)

def load_config(path: Optional[str]) -> Dict[str, Any]:
    cfg_path = path or DEFAULT_CONFIG_PATH
    if not os.path.exists(cfg_path):
        print(f"[ERROR] 未找到配置文件: {cfg_path}")
        return {}
    with open(cfg_path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception as e:
            print(f"[ERROR] 配置文件解析失败: {e}")
            return {}

def get_by_path(data: Any, dotted_path: Optional[str]) -> Any:
    """从JSON对象中按点路径取值，例如 'data.token.value'"""
    if not dotted_path or data is None:
        return None
    cur = data
    for key in str(dotted_path).split("."):
        if isinstance(cur, dict):
            cur = cur.get(key)
        else:
            return None
    return cur

def merge_headers(base: Dict[str, str], extra: Optional[Dict[str, str]]) -> Dict[str, str]:
    out = dict(base or {})
    if extra:
        for k, v in extra.items():
            out[k] = v
    return out

# ------------------------- 请求执行 -------------------------

def perform_request(base_url: str, method: str, path: str, headers: Dict[str, str], params: Dict[str, str], body: Optional[Any], timeout: int = 15) -> Tuple[int, Dict[str, str], Any]:
    import requests
    url = base_url.rstrip("/") + path
    t0 = time.time()
    try:
        resp = requests.request(
            method=method.upper(),
            url=url,
            headers=headers or None,
            params=params or None,
            json=body,
            timeout=timeout,
        )
    except Exception as e:
        print(f"[ERROR] 请求失败: {e}")
        raise
    elapsed = (time.time() - t0) * 1000.0
    content_type = resp.headers.get("Content-Type", "")
    data: Any
    if "application/json" in (content_type or "").lower():
        try:
            data = resp.json()
        except Exception:
            data = resp.text
    else:
        data = resp.text
    print(f"-> {method.upper()} {url} [{resp.status_code}] {elapsed:.2f} ms")
    return resp.status_code, dict(resp.headers), data

def perform_ws_test(url: str, headers: Dict[str, str], message: Optional[str] = None, timeout: int = 10) -> Tuple[int, Dict[str, Any], Any]:
    """简单WS连接测试: 建连、发送消息、接收一条返回"""
    if not ensure_ws_available():
        print("[ERROR] 需要进行WS测试但未安装 websocket-client。请安装: pip install websocket-client")
        raise RuntimeError("websocket-client not installed")
    import websocket
    print(f"-> WS CONNECT {url}")
    ws = websocket.WebSocket()
    ws.settimeout(timeout)
    ws.connect(url, header=[f"{k}: {v}" for k, v in (headers or {}).items()])
    status_code = 101  # Switching Protocols (模拟)
    received = None
    if message:
        ws.send(message)
        try:
            received = ws.recv()
        except Exception:
            received = None
    ws.close()
    print(f"-> WS DONE [{status_code}] recv={received is not None}")
    return status_code, {"connected": True}, received

# ------------------------- 可达性检查 -------------------------

def check_base_availability(name: str, base_url: str, timeout: int = 5) -> bool:
    """快速检查基础地址是否可达(HEAD/GET)"""
    if not base_url:
        return False
    try:
        import requests
        probe_paths = ["/api/health", "/health", "/"]
        ok = False
        for p in probe_paths:
            url = base_url.rstrip("/") + p
            try:
                resp = requests.get(url, timeout=timeout)
                if resp.status_code < 500:
                    ok = True
                    break
            except Exception:
                continue
        if not ok:
            print(f"[WARN] 基础地址不可达({name}): {base_url}，将导致相关用例失败。")
        else:
            print(f"[INFO] 基础地址可达({name}): {base_url}")
        return ok
    except Exception:
        print(f"[WARN] 可达性检查异常({name}): {base_url}")
        return False

# ------------------------- 自动测试主逻辑 -------------------------

def perform_auto_tests(config: Dict[str, Any], timeout: int = 15, fail_fast: bool = False, skip_check: bool = False) -> int:
    default = config.get("default", {})
    base_urls = {
        "base": default.get("base_url", ""),
        "bot": default.get("bot_base_url", ""),
        "memory": default.get("memory_base_url", ""),
        "ws": default.get("ws_url", ""),
    }
    headers = default.get("headers", {}) or {}
    auth_cfg = default.get("auth", {}) or {}
    auto_tests: List[Dict[str, Any]] = default.get("auto_tests", []) or []

    if not auto_tests:
        print("[ERROR] 配置未提供 auto_tests。")
        return 1

    # 可达性预检查
    if not skip_check:
        print("\n[CHECK] 基础地址可达性预检查...")
        check_base_availability("base", base_urls.get("base") or "")
        check_base_availability("bot", base_urls.get("bot") or "")
        check_base_availability("memory", base_urls.get("memory") or "")

    # 自动登录获取Token
    if auth_cfg.get("login_path"):
        auth_use_base = auth_cfg.get("use_base", "base")
        auth_base_url = base_urls.get(auth_use_base) or base_urls.get("base") or ""
        auth_method = str(auth_cfg.get("method", "POST")).upper()
        auth_body = auth_cfg.get("request_body", {}) or {
            "username": auth_cfg.get("username", ""),
            "password": auth_cfg.get("password", "")
        }
        auth_headers = merge_headers(headers, auth_cfg.get("headers"))
        try:
            print("\n[AUTH] 尝试登录获取Token...")
            status, _, data = perform_request(auth_base_url, auth_method, auth_cfg["login_path"], auth_headers, auth_cfg.get("params", {}) or {}, auth_body, timeout=timeout)
            token_path = auth_cfg.get("response_token_json_path") or auth_cfg.get("token_json_path") or "access_token"
            token_value = get_by_path(data, token_path) if isinstance(data, dict) else None
            if token_value:
                token_header = auth_cfg.get("token_header", "Authorization")
                token_prefix = auth_cfg.get("token_prefix", "Bearer ")
                headers[token_header] = f"{token_prefix}{token_value}"
                print(f"[AUTH] 登录成功，已注入Header: {token_header}={token_prefix}******")
            else:
                print("[AUTH] 未能从响应提取Token，继续无Token模式。")
        except Exception as e:
            print(f"[AUTH] 登录失败: {e}，继续执行后续测试。")

    # 执行自动测试
    total = len(auto_tests)
    success = 0
    failures: List[Tuple[int, str]] = []

    print(f"\n[AUTO] 开始执行 {total} 项用例...")
    for i, t in enumerate(auto_tests, start=1):
        method = str(t.get("method", "GET")).upper()
        path = t.get("path", "/")
        use_base = t.get("use", "base")
        base_url = base_urls.get(use_base) or base_urls.get("base") or ""
        th = merge_headers(headers, t.get("headers"))
        params = t.get("params", {}) or {}
        body = t.get("body", None)

        print(f"\n[AUTO #{i}] {method} {path} @ ({use_base}) {base_url}")
        try:
            if method == "WS":
                ws_url = t.get("ws_url") or base_urls.get("ws")
                if not ws_url:
                    ws_url = base_url.rstrip("/").replace("http", "ws") + path
                perform_ws_test(ws_url, th, t.get("message"), timeout=min(timeout, 10))
                success += 1
            else:
                status_code, _, _ = perform_request(base_url, method, path, th, params, body, timeout=timeout)
                if 200 <= status_code < 300:
                    success += 1
                else:
                    failures.append((i, f"HTTP {status_code}"))
                    if fail_fast:
                        break
        except Exception as e:
            failures.append((i, str(e)))
            print(f"[AUTO #{i}] 失败: {e}")
            if fail_fast:
                break

    print("\n[AUTO] 测试完成")
    print(f"成功: {success}/{total}")
    if failures:
        print("失败用例:")
        for idx, reason in failures:
            print(f" - #{idx}: {reason}")

    # 返回码: 全成功返回0；部分失败返回2；无用例或配置错误返回1
    if success == total:
        return 0
    return 2

# ------------------------- 主程序 -------------------------

def main():
    if not ensure_requests_available():
        sys.exit(1)

    parser = argparse.ArgumentParser(description="MaiMBot 配置驱动的一键API自动测试")
    parser.add_argument("--config", type=str, default=DEFAULT_CONFIG_PATH, help="配置文件路径(JSON)")
    parser.add_argument("--timeout", type=int, default=15, help="每个请求的超时时间(秒)")
    parser.add_argument("--fail-fast", action="store_true", help="首次失败后立即退出")
    parser.add_argument("--skip-check", action="store_true", help="跳过基础地址可达性预检查")
    parser.add_argument("--list", action="store_true", help="仅列出将要执行的用例，不实际请求")
    args = parser.parse_args()

    cfg = load_config(args.config)
    if not cfg:
        sys.exit(1)

    default = cfg.get("default", {})
    auto_tests = default.get("auto_tests", []) or []
    if args.list:
        print(f"[LIST] 将执行 {len(auto_tests)} 项用例:")
        for i, t in enumerate(auto_tests, start=1):
            print(f" - #{i}: {t.get('method','GET')} {t.get('path','/')} use={t.get('use','base')}")
        sys.exit(0)

    rc = perform_auto_tests(cfg, timeout=args.timeout, fail_fast=args.fail_fast, skip_check=args.skip_check)
    sys.exit(rc)

if __name__ == "__main__":
    main()
