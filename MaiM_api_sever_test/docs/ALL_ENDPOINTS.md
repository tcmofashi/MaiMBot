# MaiMBot 项目 API 接口总览

说明:
- 本清单综合了项目内 Markdown 文档与源码实际路由定义，分为“文档定义的接口”和“源码实现的接口”两部分。
- 主应用 FastAPI 在 `src/api/main.py` 中以 `app.include_router(api_router, prefix="/api")` 方式统一加上 `/api` 前缀；各子路由文件的 `APIRouter(prefix=...)` 再追加版本或模块前缀。
- 记忆系统（Memory Service）为独立服务，路由前缀已在其应用中定义（通常不再额外追加 `/api` 根前缀）。

目录:
- 文档定义的接口
- 源码实现的接口
  - 主应用通用端点
  - 认证（Auth v1）
  - 租户管理（Tenant v1）
  - 智能体管理（Agents v1）
  - 聊天（Chat v1, v2, 隔离式）
  - API 密钥管理
  - 记忆系统服务（Memory Service）
  - 其他示例/测试端点
- 差异与备注

---

## 文档定义的接口

来源: `docs/API_SERVER.md` 与 `docs/API_REFERENCE.md`

认证相关:
- POST /api/v1/auth/register
- POST /api/v1/auth/login
- GET  /api/v1/auth/me
- POST /api/v1/auth/logout
- POST /api/v1/auth/refresh

基础与系统:
- GET  /api/v1/health
- GET  /api/v1/system/info
- GET  /api/v1/ready

租户管理:
- GET    /api/v1/tenants?page=1&limit=20&search=关键词
- POST   /api/v1/tenants
- GET    /api/v1/tenants/{tenant_id}
- PUT    /api/v1/tenants/{tenant_id}
- DELETE /api/v1/tenants/{tenant_id}
- GET    /api/v1/tenants/{tenant_id}/statistics

智能体管理:
- GET    /api/v1/agents?page=1&limit=20&status=active
- POST   /api/v1/agents
- GET    /api/v1/agents/{agent_id}
- PUT    /api/v1/agents/{agent_id}
- DELETE /api/v1/agents/{agent_id}
- GET    /api/v1/agents/{agent_id}/config
- PUT    /api/v1/agents/{agent_id}/config

聊天与消息:
- POST /api/v1/chat/send
- GET  /api/v1/chat/{chat_stream_id}/messages?page=...&limit=...&before=...
- POST /api/v1/chat/streams
- GET  /api/v1/chat/streams?platform=...&status=...
- GET  /api/v1/chat/messages/{message_id}/status

记忆系统:
- POST   /api/v1/memory/store
- GET    /api/v1/memory/search?query=...&limit=...&type=...
- GET    /api/v1/memory/agent/{agent_id}?type=...&limit=...
- PUT    /api/v1/memory/{memory_id}
- DELETE /api/v1/memory/{memory_id}
- GET    /api/v1/memory/statistics

心流处理:
- POST /api/v1/heartflow/process
- GET  /api/v1/heartflow/status/{chat_stream_id}
- PUT  /api/v1/heartflow/config/{chat_stream_id}
- GET  /api/v1/heartflow/analysis/{chat_stream_id}?period=...

表情系统:
- POST /api/v1/emoji/send
- GET  /api/v1/emoji/packs?platform=...&category=...
- POST /api/v1/emoji/packs
- GET  /api/v1/emoji/statistics?period=...

插件系统:
- GET  /api/v1/plugins?status=...&category=...
- POST /api/v1/plugins/install
- POST /api/v1/plugins/{plugin_id}/enable
- POST /api/v1/plugins/{plugin_id}/disable
- GET  /api/v1/plugins/{plugin_id}/config
- PUT  /api/v1/plugins/{plugin_id}/config
- POST /api/v1/plugins/{plugin_id}/execute

配置管理:
- GET  /api/v1/config?category=...&platform=...
- PUT  /api/v1/config
- POST /api/v1/config/reset?category=...
- GET  /api/v1/config/history?category=...&limit=...

监控与统计:
- GET /api/v1/monitor/status
- GET /api/v1/stats/usage?period=...&group_by=...
- GET /api/v1/stats/tenants?period=...
- GET /api/v1/stats/api?endpoint=...&period=...
- GET /api/v1/stats/performance?period=...

---

## 源码实现的接口

来源: `src/api/main.py` 及各 `src/api/routes/*.py`，以及 `src/memory_system/service/*`

### 主应用通用端点（来自 `src/api/main.py`）
- GET /api/           （API 根路径信息）
- GET /api/health     （API 层健康检查）
- GET /api/info       （API 信息）
- GET /health         （应用级健康检查，不带 `/api` 前缀）

### 认证（Auth v1）（`src/api/routes/auth_api.py`，前缀 `/v1/auth`）
- POST /api/v1/auth/register
- POST /api/v1/auth/login
- POST /api/v1/auth/logout
- GET  /api/v1/auth/me
- POST /api/v1/auth/refresh

### 租户管理（Tenant v1）（`src/api/routes/tenant_api.py`，前缀 `/v1/tenant`）
- GET  /api/v1/tenant
- PUT  /api/v1/tenant
- GET  /api/v1/tenant/stats
- POST /api/v1/tenant/upgrade
- GET  /api/v1/tenant/api-key
- POST /api/v1/tenant/regenerate-api-key

### 智能体管理（Agents v1）（`src/api/routes/agent_api.py`，前缀 `/v1/agents`）
- GET    /api/v1/agents/templates
- GET    /api/v1/agents/templates/{template_id}
- POST   /api/v1/agents
- GET    /api/v1/agents
- GET    /api/v1/agents/{agent_id}
- PUT    /api/v1/agents/{agent_id}
- DELETE /api/v1/agents/{agent_id}
- POST   /api/v1/agents/templates   （管理员创建 Agent 模板）

### 聊天（Chat v1）（`src/api/routes/chat_api.py`，前缀 `/v1`）
- POST /api/v1/chat
- GET  /api/v1/agents
- POST /api/v1/chat/batch
- GET  /api/v1/status

### 聊天（Chat v2）（`src/api/routes/chat_api_v2.py`，前缀 `/v2`）
- POST /api/v2/chat
- POST /api/v2/chat/auth
- GET  /api/v2/agents
- POST /api/v2/chat/batch

### 隔离式聊天（Isolated Chat v1）（`src/api/routes/isolated_chat_api.py`，前缀 `/v1`）
- POST /api/v1/{tenant_id}/chat
- GET  /api/v1/{tenant_id}/agents
- POST /api/v1/{tenant_id}/agents/{agent_id}/chat
- GET  /api/v1/{tenant_id}/chat/history
- GET  /api/v1/{tenant_id}/stats
- POST /api/v1/{tenant_id}/search
- GET  /api/v1/{tenant_id}/health

### API 密钥管理（`src/api/routes/api_key_api.py`，无前缀，挂载到 `/api`）
- POST /api/api-keys
- GET  /api/api-keys
- DELETE /api/api-keys/{api_key_id}
- POST /api/api-keys/validate

备注: 文档中该类接口路径标注为 `/api/v1/api-keys`，源码当前实现为 `/api/api-keys`（版本前缀缺失）。

### 记忆系统服务（Memory Service）（独立服务，`src/memory_system/service/main.py`）
健康与管理（前缀 `/api/v1`，来自 `api/health.py` 与 `api/admin.py`）:
- GET  /api/v1/health
- GET  /api/v1/health/readiness
- GET  /api/v1/health/liveness
- GET  /api/v1/health/components
- GET  /api/v1/stats
- GET  /api/v1/health          （详细健康）
- POST /api/v1/maintenance/cleanup
- POST /api/v1/maintenance/backup
- POST /api/v1/maintenance/optimize
- GET  /api/v1/maintenance/{task_id}
- GET  /api/v1/maintenance/tasks
- DELETE /api/v1/maintenance/tasks/{task_id}

记忆（前缀 `/api/v1/memories`，来自 `api/memories.py`）:
- POST   /api/v1/memories/                      （创建记忆）
- GET    /api/v1/memories/{memory_id}           （获取记忆）
- PUT    /api/v1/memories/{memory_id}           （更新记忆）
- DELETE /api/v1/memories/{memory_id}           （删除记忆）
- POST   /api/v1/memories/search                （搜索记忆）
- POST   /api/v1/memories/query                 （复杂查询）
- POST   /api/v1/memories/aggregate             （聚合记忆）
- POST   /api/v1/memories/batch                 （批量创建）
- DELETE /api/v1/memories/batch                 （批量删除）
- GET    /api/v1/memories/tenant/{tenant_id}/agent/{agent_id}  （按租户+智能体获取）

冲突（前缀 `/api/v1/conflicts`，来自 `api/conflicts.py`）:
- POST   /api/v1/conflicts/                     （创建冲突记录）
- GET    /api/v1/conflicts/{conflict_id}        （获取冲突记录）
- PUT    /api/v1/conflicts/{conflict_id}        （更新冲突记录）
- DELETE /api/v1/conflicts/{conflict_id}        （删除冲突记录）
- GET    /api/v1/conflicts/                     （查询冲突列表）
- POST   /api/v1/conflicts/{conflict_id}/resolve
- POST   /api/v1/conflicts/{conflict_id}/follow
- POST   /api/v1/conflicts/{conflict_id}/unfollow
- GET    /api/v1/conflicts/{conflict_id}/related-memories
- GET    /api/v1/conflicts/tenant/{tenant_id}/agent/{agent_id}  （按租户+智能体获取）

### 其他示例/测试端点
- GET  /users    （`src/common/server.py` 示例）
- POST /users    （`src/common/server.py` 示例）

---

## 差异与备注

- 文档与源码在部分模块存在路径风格差异：
  - 文档记忆系统以 `/api/v1/memory/*` 描述；源码独立服务采用更 REST 的 `/api/v1/memories/*`、`/api/v1/conflicts/*`。
  - API 密钥管理：文档路径 `/api/v1/api-keys`；源码当前为 `/api/api-keys`（缺少版本前缀）。如需与文档一致，建议在 `src/api/routes/api_key_api.py` 中设置 `router = APIRouter(prefix="/v1")` 并调整装饰器路径为 `"/api-keys"`，或直接 `prefix="/v1/api-keys"`。
- `src/api/routes/chat_api.py` 的 `GET /api/v1/agents` 与 `src/api/routes/agent_api.py` 的 `GET /api/v1/agents` 命名上可能产生语义重叠（一个用于聊天可用 Agent 列表，一个用于管理侧 Agent 列表）。建议在文档中区分用途或改用更明确的路径（如 `/api/v1/chat/agents`）。

以上为当前项目内可定位的全部 API 接口汇总。
