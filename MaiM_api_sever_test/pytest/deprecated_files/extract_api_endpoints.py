#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从项目的 Markdown 文档、源代码与测试代码中自动提取 API 接口列表，
并汇总输出到 api-index/endpoints.json 与 api-index/ALL_ENDPOINTS.md。

扫描范围:
- docs/**.md
- src/**.py
- tests/**.py (包括以 test_*.py 命名的文件)
- integration_tests/**.py

提取规则(覆盖常见模式):
- Markdown:
  * "GET /api/..." / "POST /api/..." 等形式
  * 代码块或行内出现的 "/api/..." 路径
  * curl -X METHOD "http://.../api/..." 形式
- 源代码:
  * @app.get("/api/..."), @router.post("/api/..."), @router.delete("/api/..."), 等装饰器
  * WebSocket: @app.websocket("/ws..."), @router.websocket("/ws...")
- 测试代码:
  * client.get("/api/..."), self.client.post("/api/...") 等
  * requests.get(".../api/...") 等

输出结构:
- endpoints.json: 每个端点包含 method, path, category, versions, sources(来源文件、行号、片段)、flags(是否来自docs/code/tests)
- ALL_ENDPOINTS.md: 人类可读的清单，按分类与版本分组展示

用法:
- python scripts/extract_api_endpoints.py
"""
import os
import re
import json
from typing import Dict, Any, List, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
OUTPUT_DIR = os.path.join(REPO_ROOT, "api-index")
ENDPOINTS_JSON = os.path.join(OUTPUT_DIR, "endpoints.json")
ENDPOINTS_MD = os.path.join(OUTPUT_DIR, "ALL_ENDPOINTS.md")

# 扫描目录配置
SCAN_DIRS = [
    ("docs", os.path.join(REPO_ROOT, "docs"), (".md",)),
    ("src", os.path.join(REPO_ROOT, "src"), (".py",)),
    ("tests", os.path.join(REPO_ROOT, "tests"), (".py",)),
    ("integration_tests", os.path.join(REPO_ROOT, "integration_tests"), (".py",)),
]

# 正则模式
# Markdown 中带方法的声明
MD_METHOD_PATH_RE = re.compile(r'\b(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\b[^\n]*\b(/api[^\s\)\]\}"]+)', re.IGNORECASE)
# Markdown 中任何 /api 路径
MD_PATH_ONLY_RE = re.compile(r'["\'`]?(/api[^\s"\'`]+)', re.IGNORECASE)
# curl 形式
MD_CURL_RE = re.compile(r'curl\s+-X\s+(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+"[^"]*(/api[^"]+)"', re.IGNORECASE)

# Python 源码装饰器
PY_ROUTE_RE = re.compile(r'@\s*(?:app|router)\s*\.\s*(get|post|put|delete|patch)\s*\(\s*["\'](/api[^"\']+)["\']', re.IGNORECASE)
# WebSocket 装饰器
PY_WS_RE = re.compile(r'@\s*(?:app|router)\s*\.websocket\s*\(\s*["\'](/ws[^"\']*)["\']', re.IGNORECASE)

# 测试代码 / 客户端调用
PY_CLIENT_CALL_RE = re.compile(r'\b(?:client|self\.client|requests)\s*\.\s*(get|post|put|delete|patch)\s*\(\s*["\'](?:[^"\']*?)(/api[^"\']]+)["\']', re.IGNORECASE)

def read_file_lines(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.readlines()
    except Exception:
        return []

def category_for_path(path: str) -> str:
    # 简单分类策略
    if path.startswith("/api/v2/"):
        return "v2"
    if path.startswith("/api/v1/"):
        # 进一步分类
        if "/memory" in path:
            return "memory"
        if "/chat" in path:
            return "chat"
        if "/agents" in path:
            return "agents"
        if "/auth" in path or "login" in path or "register" in path:
            return "auth"
        if "/tenant" in path or "/tenants" in path:
            return "tenant"
        if "/stats" in path:
            return "stats"
        if "/plugins" in path:
            return "plugins"
        if "/config" in path:
            return "config"
        if "/emoji" in path:
            return "emoji"
        if "/heartflow" in path:
            return "heartflow"
        return "v1"
    if path.startswith("/api/api-keys"):
        return "api-keys"
    if path.startswith("/api/multi_tenant"):
        return "multi_tenant"
    if path.startswith("/api/"):
        return "api"
    if path.startswith("/ws"):
        return "ws"
    return "unknown"

def versions_for_path(path: str) -> List[str]:
    vs: List[str] = []
    if "/api/v1/" in path:
        vs.append("v1")
    if "/api/v2/" in path:
        vs.append("v2")
    return vs or ["unversioned"]

def normalize_method(m: str) -> str:
    m = (m or "").upper()
    if m in {"GET","POST","PUT","DELETE","PATCH","HEAD","OPTIONS"}:
        return m
    return "?"

def add_endpoint(store: Dict[str, Any], method: str, path: str, origin: str, file_path: str, line_no: int, snippet: str) -> None:
    key = f"{normalize_method(method)} {path}"
    entry = store.get(key)
    flags = {
        "from_docs": origin == "docs",
        "from_code": origin == "src",
        "from_tests": origin in {"tests", "integration_tests"},
    }
    src_obj = {"origin": origin, "file": os.path.relpath(file_path, REPO_ROOT), "line": line_no, "snippet": snippet.strip()}
    if entry is None:
        store[key] = {
            "method": normalize_method(method),
            "path": path,
            "category": category_for_path(path),
            "versions": versions_for_path(path),
            "sources": [src_obj],
            "flags": flags.copy(),
        }
    else:
        # 更新 flags
        entry["flags"]["from_docs"] = entry["flags"]["from_docs"] or flags["from_docs"]
        entry["flags"]["from_code"] = entry["flags"]["from_code"] or flags["from_code"]
        entry["flags"]["from_tests"] = entry["flags"]["from_tests"] or flags["from_tests"]
        # 去重追加来源
        sig = (src_obj["origin"], src_obj["file"], src_obj["line"], src_obj["snippet"])
        existing = {(s["origin"], s["file"], s["line"], s["snippet"]) for s in entry["sources"]}
        if sig not in existing:
            entry["sources"].append(src_obj)

def scan_markdown(file_path: str, store: Dict[str, Any]) -> None:
    lines = read_file_lines(file_path)
    for idx, line in enumerate(lines, start=1):
        # 形式: METHOD + 路径
        for m in MD_METHOD_PATH_RE.finditer(line):
            method = m.group(1)
            path = m.group(2)
            add_endpoint(store, method, path, "docs", file_path, idx, line)
        # curl 形式
        for m in MD_CURL_RE.finditer(line):
            method = m.group(1)
            path = m.group(2)
            add_endpoint(store, method, path, "docs", file_path, idx, line)
        # 单纯路径
        for p in MD_PATH_ONLY_RE.finditer(line):
            path = p.group(1)
            # 未指定方法时使用 "?"
            add_endpoint(store, "?", path, "docs", file_path, idx, line)

def scan_python(file_path: str, store: Dict[str, Any], origin: str) -> None:
    lines = read_file_lines(file_path)
    for idx, line in enumerate(lines, start=1):
        for m in PY_ROUTE_RE.finditer(line):
            method = m.group(1)
            path = m.group(2)
            add_endpoint(store, method, path, origin, file_path, idx, line)
        for m in PY_WS_RE.finditer(line):
            path = m.group(1)
            add_endpoint(store, "WS", path, origin, file_path, idx, line)
        for m in PY_CLIENT_CALL_RE.finditer(line):
            method = m.group(1)
            path = m.group(2)
            add_endpoint(store, method, path, origin, file_path, idx, line)

def scan_all() -> Dict[str, Any]:
    endpoints: Dict[str, Any] = {}
    for origin, base_dir, exts in SCAN_DIRS:
        if not os.path.isdir(base_dir):
            continue
        for root, _, files in os.walk(base_dir):
            for name in files:
                if any(name.endswith(ext) for ext in exts):
                    path = os.path.join(root, name)
                    try:
                        if origin == "docs":
                            scan_markdown(path, endpoints)
                        else:
                            scan_python(path, endpoints, origin)
                    except Exception as e:
                        # 忽略单文件错误
                        print(f"[WARN] 扫描失败: {path} -> {e}")
                        continue
    return endpoints

def write_outputs(endpoints: Dict[str, Any]) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    # JSON 输出
    sorted_items = sorted(endpoints.values(), key=lambda x: (x["method"], x["path"]))
    with open(ENDPOINTS_JSON, "w", encoding="utf-8") as f:
        json.dump(sorted_items, f, ensure_ascii=False, indent=2)
    # MD 输出
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for item in sorted_items:
        cat = item["category"]
        groups.setdefault(cat, []).append(item)

    def fmt_sources(srcs: List[Dict[str, Any]]) -> str:
        parts = []
        for s in srcs[:5]:  # 最多展示前5个来源
            parts.append(f"{s['origin']}:{s['file']}:{s['line']}")
        more = len(srcs) - len(parts)
        return ", ".join(parts) + (f" (+{more} more)" if more > 0 else "")

    with open(ENDPOINTS_MD, "w", encoding="utf-8") as f:
        f.write("# API 接口索引\n\n")
        f.write(f"- 总计端点: {len(sorted_items)}\n")
        f.write(f"- 来源目录: {', '.join([d for d,_,_ in SCAN_DIRS])}\n\n")
        for cat in sorted(groups.keys()):
            items = groups[cat]
            f.write(f"## {cat} ({len(items)})\n\n")
            f.write("| 方法 | 路径 | 版本 | 来源(示例) |\n")
            f.write("|------|------|------|------------|\n")
            for it in items:
                f.write(f"| {it['method']} | `{it['path']}` | {', '.join(it['versions'])} | {fmt_sources(it['sources'])} |\n")
            f.write("\n")
        f.write("\n---\n生成于扫描 docs/src/tests/integration_tests，可能包含文档草拟接口或已废弃接口，请结合源码确认。\n")

def main():
    eps = scan_all()
    write_outputs(eps)
    print(f"[DONE] 提取完成 -> {ENDPOINTS_JSON} / {ENDPOINTS_MD} (总计 {len(eps)} 端点)")

if __name__ == "__main__":
    main()
