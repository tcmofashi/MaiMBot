# MaiMBot API 接口文档

## 概述

MaiMBot API v2 提供完整的多租户AI聊天机器人配置和管理功能，包括租户管理、Agent配置、API密钥管理和聊天功能。本服务设计为内部服务，所有接口都无需认证，可通过网络层面控制访问权限。

**基础URL**: `http://localhost:8000/api/v2`

**API版本**: v2

## 认证方式

### 内部服务模式
- **无需认证**: 所有API接口都无需身份验证
- **网络控制**: 通过防火墙、VPN等网络层面控制访问权限
- **专用网络**: 仅限可信网络访问

### API密钥格式
聊天接口使用的API密钥格式：
- **格式**: `mmc_{tenant_id}_{agent_id}_{random_hash}_{version}`
- **用途**: 用于外部服务调用聊天功能时的身份验证

## 统一响应格式

### 成功响应
```json
{
    "success": true,
    "message": "操作成功",
    "data": {
        // 具体数据内容
    },
    "timestamp": "2025-12-02T10:30:00Z",
    "request_id": "req_abc123def456",
    "tenant_id": "tenant_789",
    "execution_time": 0.123
}
```

### 错误响应
```json
{
    "success": false,
    "message": "操作失败",
    "error": "详细错误信息",
    "error_code": "ERROR_CODE",
    "timestamp": "2025-12-02T10:30:00Z",
    "request_id": "req_abc123def456"
}
```

### 分页响应
```json
{
    "success": true,
    "data": {
        "items": [...],
        "pagination": {
            "page": 1,
            "page_size": 20,
            "total": 100,
            "total_pages": 5,
            "has_next": true,
            "has_prev": false
        }
    }
}
```

---

## 1. 租户管理

### 1.1 创建租户（无需认证）
**POST** `/tenants`

创建新的租户，无需任何认证

**请求体**:
```json
{
    "tenant_name": "string",
    "tenant_type": "personal|enterprise",
    "description": "string",
    "contact_email": "user@example.com",
    "tenant_config": {
        "timezone": "Asia/Shanghai",
        "language": "zh-CN"
    }
}
```

**参数验证**:
- `tenant_name`: 1-100个字符
- `tenant_type`: personal 或 enterprise
- `contact_email`: 可选，有效邮箱格式

**响应**:
```json
{
    "success": true,
    "message": "租户创建成功",
    "data": {
        "tenant_id": "tenant_xyz789",
        "tenant_name": "我的公司",
        "tenant_type": "enterprise",
        "description": "AI聊天服务提供商",
        "tenant_config": {
            "timezone": "Asia/Shanghai",
            "language": "zh-CN"
        },
        "status": "active",
        "created_at": "2025-01-01T00:00:00Z"
    }
}
```

### 1.2 获取租户详情（无需认证）
**GET** `/tenants/{tenant_id}`

获取指定租户的详细信息

**路径参数**:
- `tenant_id`: 租户ID

**响应**:
```json
{
    "success": true,
    "message": "获取租户详情成功",
    "data": {
        "tenant_id": "tenant_xyz789",
        "tenant_name": "我的公司",
        "tenant_type": "enterprise",
        "status": "active",
        "description": "AI聊天服务提供商",
        "tenant_config": {
            "timezone": "Asia/Shanghai",
            "language": "zh-CN"
        },
        "owner_id": "temp_user_abc123",
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-12-01T10:00:00Z"
    }
}
```

---

## 2. Agent管理

### 2.1 创建Agent（无需认证）
**POST** `/agents`

创建新的AI Agent

**请求体**:
```json
{
    "tenant_id": "tenant_xyz789",
    "name": "客服助手",
    "description": "专业的客户服务AI助手",
    "template_id": "customer_service_template",
    "config": {
        "persona": "友好、专业的客服助手，具有耐心和细致的解答能力",
        "bot_overrides": {
            "nickname": "小助手",
            "platform": "qq",
            "qq_account": "123456789"
        },
        "config_overrides": {
            "personality": {
                "reply_style": "专业、礼貌",
                "interest": "客户服务、技术支持"
            },
            "chat": {
                "max_context_size": 20,
                "response_timeout": 30
            }
        },
        "tags": ["客服", "技术支持", "AI助手"]
    }
}
```

**配置字段说明**：
- `persona`: Agent人格描述（字符串）
- `bot_overrides`: Bot基础配置覆盖（对象）
  - `nickname`: 昵称
  - `platform`: 平台标识
  - `qq_account`: QQ账号
- `config_overrides`: 详细配置覆盖（对象）
  - `personality`: 个性化配置
    - `reply_style`: 回复风格
    - `interest`: 兴趣领域
  - `chat`: 聊天配置
    - `max_context_size`: 最大上下文大小
    - `response_timeout`: 响应超时时间
- `tags`: 标签列表（字符串数组）

**响应**:
```json
{
    "success": true,
    "message": "Agent创建成功",
    "data": {
        "agent_id": "agent_pqr345",
        "tenant_id": "tenant_xyz789",
        "name": "客服助手",
        "description": "专业的客户服务AI助手",
        "template_id": null,
        "config": {
            "persona": "友好、专业的客服助手，具有耐心和细致的解答能力",
            "bot_overrides": {
                "nickname": "小助手",
                "platform": "qq",
                "qq_account": "123456789"
            },
            "config_overrides": {
                "personality": {
                    "reply_style": "专业、礼貌",
                    "interest": "客户服务、技术支持"
                },
                "chat": {
                    "max_context_size": 20,
                    "response_timeout": 30
                }
            },
            "tags": ["客服", "技术支持", "AI助手"]
        },
        "status": "active",
        "created_at": "2025-01-01T00:00:00Z"
    }
}
```

### 2.2 获取Agent列表（无需认证）
**GET** `/agents`

获取指定租户的Agent列表

**查询参数**:
- `tenant_id`: 租户ID (必需)
- `page`: 页码 (默认: 1)
- `page_size`: 每页数量 (默认: 20)
- `status`: 状态过滤 (可选)

**说明**: Agent必须属于特定租户，因此tenant_id是必需参数

**响应**:
```json
{
    "success": true,
    "data": {
        "items": [
            {
                "agent_id": "agent_pqr345",
                "tenant_id": "tenant_xyz789",
                "name": "客服助手",
                "description": "专业的客户服务AI助手",
                "template_id": null,
                "config": {
                    "persona": "友好、专业的客服助手，具有耐心和细致的解答能力",
                    "bot_overrides": {
                        "nickname": "小助手",
                        "platform": "qq"
                    },
                    "config_overrides": {
                        "personality": {
                            "reply_style": "专业、礼貌"
                        }
                    },
                    "tags": ["客服", "技术支持"]
                },
                "status": "active",
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-12-01T10:00:00Z"
            }
        ],
        "pagination": {
            "page": 1,
            "page_size": 20,
            "total": 1,
            "total_pages": 1,
            "has_next": false,
            "has_prev": false
        }
    }
}
```

### 2.3 获取Agent详情（无需认证）
**GET** `/agents/{agent_id}`

获取指定Agent的详细信息

**路径参数**:
- `agent_id`: Agent ID

**响应**:
```json
{
    "success": true,
    "message": "获取Agent详情成功",
    "data": {
        "agent_id": "agent_pqr345",
        "tenant_id": "tenant_xyz789",
        "name": "客服助手",
        "description": "专业的客户服务AI助手",
        "template_id": null,
        "config": {
            "persona": "友好、专业的客服助手，具有耐心和细致的解答能力",
            "bot_overrides": {
                "nickname": "小助手",
                "platform": "qq",
                "qq_account": "123456789"
            },
            "config_overrides": {
                "personality": {
                    "reply_style": "专业、礼貌",
                    "interest": "客户服务、技术支持"
                },
                "chat": {
                    "max_context_size": 20,
                    "response_timeout": 30
                }
            },
            "tags": ["客服", "技术支持", "AI助手"]
        },
        "status": "active",
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-12-01T10:00:00Z"
    }
}
```

### 2.4 更新Agent（无需认证）
**PUT** `/agents/{agent_id}`

更新Agent信息和配置

**路径参数**:
- `agent_id`: Agent ID

**请求体**:
```json
{
    "name": "更新后的客服助手",
    "description": "更新后的描述",
    "config": {
        "persona": "更新后的人格描述，更加专业和高效",
        "bot_overrides": {
            "nickname": "超级助手",
            "platform": "discord"
        },
        "config_overrides": {
            "personality": {
                "reply_style": "简洁、高效",
                "interest": "技术支持、产品咨询"
            },
            "chat": {
                "max_context_size": 15
            }
        },
        "tags": ["客服", "技术支持", "专家"]
    }
}
```

**响应**:
```json
{
    "success": true,
    "message": "Agent更新成功",
    "data": {
        "agent_id": "agent_pqr345",
        "updated_at": "2025-12-02T10:30:00Z"
    }
}
```

### 2.5 删除Agent（无需认证）
**DELETE** `/agents/{agent_id}`

删除指定Agent

**路径参数**:
- `agent_id`: Agent ID

**响应**:
```json
{
    "success": true,
    "message": "Agent删除成功",
    "data": {
        "agent_id": "agent_pqr345",
        "deleted_at": "2025-12-02T10:30:00Z"
    }
}
```

---

## 3. API密钥管理

### 3.1 创建API密钥（无需认证）
**POST** `/api-keys`

为指定Agent创建新的API密钥

**请求体**:
```json
{
    "tenant_id": "tenant_xyz789",
    "agent_id": "agent_pqr345",
    "name": "string",
    "description": "string",
    "permissions": ["chat", "config_read"],
    "expires_at": "2026-01-01T00:00:00Z"
}
```

**响应**:
```json
{
    "success": true,
    "message": "API密钥创建成功",
    "data": {
        "api_key_id": "key_123",
        "tenant_id": "tenant_xyz789",
        "agent_id": "agent_pqr345",
        "name": "生产环境密钥",
        "description": "用于生产环境的API调用",
        "api_key": "mmc_dGVuYW50X3h5ejc4OV9hZ2VudF9wcXIzNDVfOGY4YTliMmMzZF92MQ==",
        "permissions": ["chat", "config_read"],
        "status": "active",
        "expires_at": "2026-01-01T00:00:00Z",
        "created_at": "2025-01-01T00:00:00Z"
    }
}
```

### 3.2 获取API密钥列表（无需认证）
**GET** `/api-keys`

获取指定租户的API密钥列表

**查询参数**:
- `tenant_id`: 租户ID (必需)
- `agent_id`: Agent ID (可选)
- `page`: 页码 (默认: 1)
- `page_size`: 每页数量 (默认: 20)
- `status`: 密钥状态过滤 (可选)

**说明**: API密钥必须属于特定租户，因此tenant_id是必需参数

**响应**:
```json
{
    "success": true,
    "data": {
        "items": [
            {
                "api_key_id": "key_123",
                "tenant_id": "tenant_xyz789",
                "agent_id": "agent_pqr345",
                "name": "生产环境密钥",
                "description": "用于生产环境的API调用",
                "api_key": "mmc_dGVuYW50X3h5ejc4OV9hZ2VudF9wcXIzNDVfOGY4YTliMmMzZF92MQ==",
                "permissions": ["chat", "config_read"],
                "status": "active",
                "expires_at": "2026-01-01T00:00:00Z",
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-12-01T10:00:00Z"
            }
        ],
        "pagination": {
            "page": 1,
            "page_size": 20,
            "total": 1,
            "total_pages": 1,
            "has_next": false,
            "has_prev": false
        }
    }
}
```

### 3.3 获取API密钥详情（无需认证）
**GET** `/api-keys/{api_key_id}`

获取指定API密钥的详细信息

**路径参数**:
- `api_key_id`: API密钥ID

**响应**:
```json
{
    "success": true,
    "message": "获取API密钥详情成功",
    "data": {
        "api_key_id": "key_123",
        "tenant_id": "tenant_xyz789",
        "agent_id": "agent_pqr345",
        "name": "生产环境密钥",
        "description": "用于生产环境的API调用",
        "api_key": "mmc_dGVuYW50X3h5ejc4OV9hZ2VudF9wcXIzNDVfOGY4YTliMmMzZF92MQ==",
        "permissions": ["chat", "config_read"],
        "status": "active",
        "expires_at": "2026-01-01T00:00:00Z",
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-12-01T10:00:00Z"
    }
}
```

### 3.4 更新API密钥（无需认证）
**PUT** `/api-keys/{api_key_id}`

更新API密钥的配置

**路径参数**:
- `api_key_id`: API密钥ID

**请求体**:
```json
{
    "name": "string",
    "description": "string",
    "permissions": ["chat", "config_read", "config_write"],
    "expires_at": "2026-06-01T00:00:00Z"
}
```

**响应**:
```json
{
    "success": true,
    "message": "API密钥更新成功",
    "data": {
        "api_key_id": "key_123",
        "updated_at": "2025-12-02T10:30:00Z"
    }
}
```

### 3.5 禁用API密钥（无需认证）
**POST** `/api-keys/{api_key_id}/disable`

临时禁用API密钥

**路径参数**:
- `api_key_id`: API密钥ID

**响应**:
```json
{
    "success": true,
    "message": "API密钥已禁用",
    "data": {
        "api_key_id": "key_123",
        "status": "disabled",
        "disabled_at": "2025-12-02T10:30:00Z"
    }
}
```

### 3.6 删除API密钥（无需认证）
**DELETE** `/api-keys/{api_key_id}`

永久删除API密钥（不可恢复）

**路径参数**:
- `api_key_id`: API密钥ID

**响应**:
```json
{
    "success": true,
    "message": "API密钥删除成功",
    "data": {
        "api_key_id": "key_123",
        "deleted_at": "2025-12-02T10:30:00Z"
    }
}
```

---

## 4. API密钥认证

### 4.1 解析API密钥（无需认证）
**POST** `/auth/parse-api-key`

解析API密钥获取租户和Agent信息

**请求体**:
```json
{
    "api_key": "mmc_dGVuYW50X3h5ejc4OV9hZ2VudF9wcXIzNDVfOGY4YTliMmMzZF92MQ=="
}
```

**响应**:
```json
{
    "success": true,
    "message": "API密钥解析成功",
    "data": {
        "tenant_id": "tenant_xyz789",
        "agent_id": "agent_pqr345",
        "version": "v1",
        "format_valid": true
    }
}
```

### 4.2 验证API密钥（无需认证）
**POST** `/auth/validate-api-key`

验证API密钥的有效性和权限

**请求体**:
```json
{
    "api_key": "mmc_dGVuYW50X3h5ejc4OV9hZ2VudF9wcXIzNDVfOGY4YTliMmMzZF92MQ==",
    "required_permission": "chat",
    "check_rate_limit": true
}
```

**响应**:
```json
{
    "success": true,
    "message": "API密钥验证成功",
    "data": {
        "valid": true,
        "tenant_id": "tenant_xyz789",
        "agent_id": "agent_pqr345",
        "api_key_id": "key_123",
        "permissions": ["chat", "config_read"],
        "has_permission": true,
        "status": "active"
    }
}
```

### 4.3 检查权限（无需认证）
**POST** `/auth/check-permission`

检查API密钥是否具有指定权限

**请求体**:
```json
{
    "api_key": "mmc_dGVuYW50X3h5ejc4OV9hZ2VudF9wcXIzNDVfOGY4YTliMmMzZF92MQ==",
    "permission": "chat"
}
```

**响应**:
```json
{
    "success": true,
    "message": "权限检查完成",
    "data": {
        "has_permission": true,
        "permission": "chat",
        "all_permissions": ["chat", "config_read"],
        "tenant_id": "tenant_xyz789",
        "agent_id": "agent_pqr345",
        "api_key_status": "active"
    }
}
```

---

## 5. 聊天功能

### 5.1 发送聊天消息（无需认证）
**POST** `/chat`

向指定Agent发送聊天消息

**请求体**:
```json
{
    "api_key": "mmc_dGVuYW50X3h5ejc4OV9hZ2VudF9wcXIzNDVfOGY4YTliMmMzZF92MQ==",
    "message": "你好，请帮我介绍一下产品功能",
    "conversation_id": "conv_12345",
    "user_id": "user_67890",
    "context": {
        "platform": "web",
        "session_id": "session_abc123",
        "metadata": {
            "source": "customer_portal"
        }
    },
    "options": {
        "stream": false,
        "temperature": 0.7,
        "max_tokens": 1000
    }
}
```

**响应**:
```json
{
    "success": true,
    "message": "消息处理成功",
    "data": {
        "message_id": "msg_abcdef123456",
        "conversation_id": "conv_12345",
        "response": "您好！我是您的AI助手，很高兴为您介绍我们的产品功能...",
        "metadata": {
            "agent_id": "agent_pqr345",
            "tenant_id": "tenant_xyz789",
            "model_used": "gpt-3.5-turbo",
            "tokens_used": 150,
            "processing_time": 1.2
        },
        "timestamp": "2025-12-02T10:30:00Z"
    },
    "execution_time": 1.234
}
```

### 5.2 获取聊天Agent列表（无需认证）
**GET** `/chat-agents`

获取指定租户的可用聊天Agent列表

**查询参数**:
- `tenant_id`: 租户ID (必需)

**说明**: Agent必须属于特定租户，因此tenant_id是必需参数

**响应**:
```json
{
    "success": true,
    "message": "获取聊天Agent列表成功",
    "data": [
        {
            "agent_id": "agent_pqr345",
            "tenant_id": "tenant_xyz789",
            "name": "客服助手",
            "description": "专业的客户服务AI助手",
            "capabilities": ["text_generation", "multilingual"],
            "status": "active",
            "api_keys_available": 3,
            "last_active": "2025-12-02T09:30:00Z"
        }
    ]
}
```

### 5.3 批量聊天处理（无需认证）
**POST** `/chat/batch`

批量处理多个聊天消息

**请求体**:
```json
{
    "api_key": "mmc_dGVuYW50X3h5ejc4OV9hZ2VudF9wcXIzNDVfOGY4YTliMmMzZF92MQ==",
    "messages": [
        {
            "message": "你好",
            "conversation_id": "conv_1",
            "user_id": "user_1"
        },
        {
            "message": "产品价格是多少？",
            "conversation_id": "conv_2",
            "user_id": "user_2"
        }
    ],
    "options": {
        "parallel_processing": true,
        "max_concurrent": 5
    }
}
```

**响应**:
```json
{
    "success": true,
    "message": "批量消息处理完成",
    "data": {
        "batch_id": "batch_12345",
        "results": [
            {
                "message_id": "msg_1",
                "conversation_id": "conv_1",
                "response": "您好！很高兴为您服务。",
                "status": "success",
                "processing_time": 0.8
            },
            {
                "message_id": "msg_2",
                "conversation_id": "conv_2",
                "response": "我们的产品价格根据配置不同，基础版...",
                "status": "success",
                "processing_time": 1.1
            }
        ],
        "summary": {
            "total_messages": 2,
            "successful": 2,
            "failed": 0,
            "total_processing_time": 1.9,
            "total_tokens_used": 350
        }
    },
    "execution_time": 1.956
}
```

---

## 6. 错误码说明

### 6.1 认证相关错误
- `AUTH_001`: API密钥格式无效
- `AUTH_002`: API密钥已过期
- `AUTH_003`: API密钥权限不足
- `AUTH_004`: API密钥已禁用
- `AUTH_005`: API密钥不存在

### 6.2 租户管理错误
- `TENANT_001`: 租户不存在
- `TENANT_002`: 租户名称已存在
- `TENANT_003`: 租户状态无效
- `TENANT_004`: 租户类型不支持
- `TENANT_005`: 租户配额超限

### 6.3 Agent管理错误
- `AGENT_001`: Agent不存在
- `AGENT_002`: Agent名称已存在
- `AGENT_003`: Agent模板不存在
- `AGENT_004`: Agent配置无效
- `AGENT_005`: Agent状态不允许操作

### 6.4 API密钥管理错误
- `KEY_001`: API密钥不存在
- `KEY_002`: API密钥名称已存在
- `KEY_003`: API密钥已禁用
- `KEY_004`: API密钥配额超限
- `KEY_005`: API密钥权限配置无效

### 6.5 聊天功能错误
- `CHAT_001`: 消息格式无效
- `CHAT_002`: 消息内容为空
- `CHAT_003`: Agent不可用
- `CHAT_004`: 消息长度超限
- `CHAT_005`: 频率限制

### 6.6 系统错误
- `SYS_001`: 内部服务器错误
- `SYS_002`: 数据库连接错误
- `SYS_003`: 外部服务不可用
- `SYS_004`: 请求超时
- `SYS_005`: 服务维护中

---

## 7. 使用示例

### 7.1 完整的API调用流程

```python
import requests

# 1. 创建租户（无需认证）
tenant_response = requests.post("http://localhost:8000/api/v2/tenants", json={
    "tenant_name": "我的公司",
    "tenant_type": "enterprise",
    "contact_email": "admin@company.com"
})

tenant_id = tenant_response.json()["data"]["tenant_id"]
print(f"租户创建成功，ID: {tenant_id}")

# 2. 创建Agent（无需认证）
agent_response = requests.post("http://localhost:8000/api/v2/agents", json={
    "tenant_id": tenant_id,
    "name": "客服助手",
    "template_id": "customer_service_template"
})

agent_id = agent_response.json()["data"]["agent_id"]
print(f"Agent创建成功，ID: {agent_id}")

# 3. 创建API密钥（无需认证）
api_key_response = requests.post("http://localhost:8000/api/v2/api-keys", json={
    "tenant_id": tenant_id,
    "agent_id": agent_id,
    "name": "生产环境密钥",
    "permissions": ["chat"]
})

api_key = api_key_response.json()["data"]["api_key"]
print(f"API密钥创建成功: {api_key}")

# 4. 使用API密钥进行聊天
chat_response = requests.post("http://localhost:8000/api/v2/chat",
    json={
        "api_key": api_key,
        "message": "你好，请介绍一下产品功能",
        "conversation_id": "conv_12345",
        "user_id": "user_67890"
    })

print(chat_response.json())
```

### 7.2 API密钥验证流程

```python
import requests

# 验证API密钥
validation_response = requests.post("http://localhost:8000/api/v2/auth/validate-api-key",
    json={
        "api_key": "mmc_dGVuYW50X3h5ejc4OV9hZ2VudF9wcXIzNDVfOGY4YTliMmMzZF92MQ==",
        "required_permission": "chat"
    })

if validation_response.json()["success"]:
    # 密钥有效，可以使用聊天功能
    chat_response = requests.post("http://localhost:8000/api/v2/chat",
        json={
            "api_key": "mmc_dGVuYW50X3h5ejc4OV9hZ2VudF9wcXIzNDVfOGY4YTliMmMzZF92MQ==",
            "message": "你好"
        })
    print(chat_response.json())
```

---

## 8. 架构说明

### 8.1 内部服务架构
- **无需认证**: 所有接口都无需身份验证
- **网络安全**: 通过网络层面的访问控制确保服务安全
- **专用网络**: 仅限可信网络访问，通常通过VPN或防火墙规则

### 8.2 租户管理
- **直接创建**: 无需认证即可创建租户
- **资源隔离**: 完全的多租户数据隔离
- **生命周期管理**: 完整的租户生命周期支持

### 8.3 API设计原则
- **RESTful**: 遵循REST API设计原则
- **统一响应**: 标准化的成功和错误响应格式
- **版本控制**: 清晰的API版本管理
- **文档完整**: 详细的API文档和示例

### 8.4 安全考虑
- **网络隔离**: 通过防火墙、VPN控制访问权限
- **数据加密**: 敏感数据加密存储
- **日志记录**: 完整的操作日志记录
- **监控告警**: 服务状态监控和异常告警

---

**文档版本**: 2.0.0

**最后更新**: 2025-12-02

**重要变更**:
- 移除所有需要认证的接口
- 改为内部服务架构
- 所有接口均可直接访问
- 通过网络层面控制访问权限

**联系方式**: 如有API使用问题，请通过 https://github.com/your-org/maimbot/issues 反馈。