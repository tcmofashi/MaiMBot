# MaiBot 多租户隔离架构 API 参考文档

## 📋 目录

- [API概述](#api概述)
- [认证和授权](#认证和授权)
- [基础API](#基础api)
- [多租户管理API](#多租户管理api)
- [智能体管理API](#智能体管理api)
- [聊天和消息API](#聊天和消息api)
- [记忆系统API](#记忆系统api)
- [心流处理API](#心流处理api)
- [表情系统API](#表情系统api)
- [插件系统API](#插件系统api)
- [配置管理API](#配置管理api)
- [监控和统计API](#监控和统计api)
- [错误处理](#错误处理)
- [最佳实践](#最佳实践)

## 🎯 API概述

MaiBot多租户隔离架构提供了完整的RESTful API体系，支持T+A+C+P四维隔离的所有功能。

### API设计原则

- **RESTful设计**: 遵循REST架构风格
- **版本控制**: 支持API版本管理 (`/api/v1/`)
- **统一响应格式**: 标准化的JSON响应结构
- **错误处理**: 完善的错误码和错误信息
- **隔离优先**: 所有API自动应用租户隔离
- **向后兼容**: 保持API向后兼容性

### 基础URL

```
开发环境: http://localhost:8080/api/v1
生产环境: https://your-domain.com/api/v1
```

### 通用响应格式

```json
{
  "success": true,
  "data": {},
  "message": "操作成功",
  "timestamp": "2025-01-11T12:00:00Z",
  "request_id": "req_123456789"
}
```

错误响应格式:

```json
{
  "success": false,
  "error": {
    "code": "TENANT_NOT_FOUND",
    "message": "租户不存在",
    "details": {}
  },
  "timestamp": "2025-01-11T12:00:00Z",
  "request_id": "req_123456789"
}
```

## 🔐 认证和授权

### 1. JWT认证

```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "tenant_id": "tenant_001",
  "username": "admin",
  "password": "password"
}
```

响应:

```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "expires_in": 86400,
    "tenant_info": {
      "tenant_id": "tenant_001",
      "name": "示例租户",
      "permissions": ["admin", "read", "write"]
    }
  }
}
```

### 2. API认证头

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
X-Tenant-ID: tenant_001
X-Agent-ID: agent_001  // 可选
```

### 3. 刷新Token

```http
POST /api/v1/auth/refresh
Content-Type: application/json

{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

## 🏗️ 基础API

### 1. 健康检查

```http
GET /api/v1/health
```

响应:

```json
{
  "success": true,
  "data": {
    "status": "healthy",
    "version": "1.0.0",
    "uptime": 3600,
    "components": {
      "database": "healthy",
      "redis": "healthy",
      "llm_service": "healthy"
    }
  }
}
```

### 2. 系统信息

```http
GET /api/v1/system/info
```

响应:

```json
{
  "success": true,
  "data": {
    "version": "1.0.0",
    "multi_tenant_enabled": true,
    "supported_platforms": ["qq", "discord", "slack"],
    "max_tenants": 1000,
    "current_tenants": 15
  }
}
```

### 3. 就绪检查

```http
GET /api/v1/ready
```

## 🏢 多租户管理API

### 1. 获取租户列表

```http
GET /api/v1/tenants?page=1&limit=20&search=关键词
```

响应:

```json
{
  "success": true,
  "data": {
    "tenants": [
      {
        "tenant_id": "tenant_001",
        "name": "示例租户",
        "description": "这是一个示例租户",
        "status": "active",
        "created_at": "2025-01-01T00:00:00Z",
        "agent_count": 5,
        "chat_stream_count": 23,
        "storage_used_mb": 1024
      }
    ],
    "pagination": {
      "page": 1,
      "limit": 20,
      "total": 15,
      "pages": 1
    }
  }
}
```

### 2. 创建租户

```http
POST /api/v1/tenants
Content-Type: application/json

{
  "tenant_id": "new_tenant",
  "name": "新租户",
  "description": "新创建的租户",
  "settings": {
    "max_agents": 10,
    "max_chat_streams": 100,
    "allowed_platforms": ["qq", "discord"],
    "quotas": {
      "daily_llm_requests": 1000,
      "monthly_tokens": 100000
    }
  }
}
```

### 3. 获取租户详情

```http
GET /api/v1/tenants/{tenant_id}
```

### 4. 更新租户

```http
PUT /api/v1/tenants/{tenant_id}
Content-Type: application/json

{
  "name": "更新后的租户名称",
  "description": "更新后的描述",
  "settings": {
    "max_agents": 20
  }
}
```

### 5. 删除租户

```http
DELETE /api/v1/tenants/{tenant_id}
```

### 6. 租户统计

```http
GET /api/v1/tenants/{tenant_id}/statistics
```

响应:

```json
{
  "success": true,
  "data": {
    "tenant_id": "tenant_001",
    "overview": {
      "agents_count": 5,
      "chat_streams_count": 23,
      "total_messages": 15420,
      "total_memory_items": 892
    },
    "usage": {
      "llm_requests_today": 245,
      "llm_tokens_this_month": 45678,
      "storage_used_mb": 1024,
      "api_calls_today": 892
    },
    "activity": {
      "active_chats_24h": 8,
      "active_agents_24h": 3,
      "last_activity": "2025-01-11T11:45:00Z"
    }
  }
}
```

## 🤖 智能体管理API

### 1. 获取智能体列表

```http
GET /api/v1/agents?page=1&limit=20&status=active
```

响应:

```json
{
  "success": true,
  "data": {
    "agents": [
      {
        "agent_id": "agent_001",
        "name": "助手小智",
        "description": "通用助手智能体",
        "status": "active",
        "platform": "qq",
        "created_at": "2025-01-01T00:00:00Z",
        "last_active": "2025-01-11T11:30:00Z",
        "message_count": 5234,
        "memory_count": 156
      }
    ]
  }
}
```

### 2. 创建智能体

```http
POST /api/v1/agents
Content-Type: application/json

{
  "agent_id": "new_agent",
  "name": "新智能体",
  "description": "新创建的智能体",
  "platform": "qq",
  "config": {
    "personality": "friendly",
    "response_style": "casual",
    "memory_config": {
      "max_short_term": 100,
      "max_long_term": 1000
    },
    "llm_config": {
      "model": "gpt-3.5-turbo",
      "temperature": 0.7,
      "max_tokens": 2000
    }
  }
}
```

### 3. 获取智能体详情

```http
GET /api/v1/agents/{agent_id}
```

### 4. 更新智能体

```http
PUT /api/v1/agents/{agent_id}
Content-Type: application/json

{
  "name": "更新后的名称",
  "config": {
    "personality": "professional"
  }
}
```

### 5. 删除智能体

```http
DELETE /api/v1/agents/{agent_id}
```

### 6. 智能体配置

```http
GET /api/v1/agents/{agent_id}/config
PUT /api/v1/agents/{agent_id}/config
```

## 💬 聊天和消息API

### 1. 发送消息

```http
POST /api/v1/chat/send
Content-Type: application/json

{
  "chat_stream_id": "chat_001",
  "message": "你好，我想问个问题",
  "sender_info": {
    "user_id": "user_123",
    "username": "张三",
    "group_id": "group_456"
  },
  "options": {
    "enable_memory": true,
    "enable_emoji": true,
    "priority": "normal"
  }
}
```

响应:

```json
{
  "success": true,
  "data": {
    "message_id": "msg_789",
    "response": "您好！很高兴为您服务，请问有什么可以帮助您的？",
    "processing_time_ms": 1250,
    "tokens_used": 156,
    "actions_taken": [
      {
        "type": "emoji_response",
        "emoji": "😊"
      },
      {
        "type": "memory_store",
        "memory_id": "mem_456"
      }
    ]
  }
}
```

### 2. 获取聊天历史

```http
GET /api/v1/chat/{chat_stream_id}/messages?page=1&limit=50&before=msg_123
```

### 3. 创建聊天流

```http
POST /api/v1/chat/streams
Content-Type: application/json

{
  "chat_stream_id": "new_chat",
  "platform": "qq",
  "chat_type": "group",  // group | private
  "participants": ["user_123", "user_456"],
  "metadata": {
    "group_name": "技术交流群",
    "description": "技术讨论群组"
  }
}
```

### 4. 获取聊天流列表

```http
GET /api/v1/chat/streams?platform=qq&status=active
```

### 5. 消息状态查询

```http
GET /api/v1/chat/messages/{message_id}/status
```

## 🧠 记忆系统API

### 1. 存储记忆

```http
POST /api/v1/memory/store
Content-Type: application/json

{
  "content": "用户喜欢谈论技术话题，特别是Python编程",
  "memory_type": "preference",  // preference | fact | conversation | emotion
  "importance": 0.8,  // 0.0 - 1.0
  "tags": ["技术", "Python", "偏好"],
  "metadata": {
    "source": "conversation",
    "confidence": 0.9
  }
}
```

### 2. 检索记忆

```http
GET /api/v1/memory/search?query=Python&limit=10&type=preference
```

响应:

```json
{
  "success": true,
  "data": {
    "memories": [
      {
        "memory_id": "mem_001",
        "content": "用户喜欢谈论技术话题，特别是Python编程",
        "memory_type": "preference",
        "importance": 0.8,
        "tags": ["技术", "Python", "偏好"],
        "created_at": "2025-01-10T15:30:00Z",
        "last_accessed": "2025-01-11T10:20:00Z",
        "access_count": 5
      }
    ],
    "total": 1
  }
}
```

### 3. 获取智能体记忆

```http
GET /api/v1/memory/agent/{agent_id}?type=long_term&limit=20
```

### 4. 更新记忆

```http
PUT /api/v1/memory/{memory_id}
Content-Type: application/json

{
  "content": "更新后的记忆内容",
  "importance": 0.9,
  "tags": ["更新", "标签"]
}
```

### 5. 删除记忆

```http
DELETE /api/v1/memory/{memory_id}
```

### 6. 记忆统计

```http
GET /api/v1/memory/statistics
```

响应:

```json
{
  "success": true,
  "data": {
    "total_memories": 892,
    "by_type": {
      "preference": 234,
      "fact": 456,
      "conversation": 156,
      "emotion": 46
    },
    "by_importance": {
      "high": 156,
      "medium": 456,
      "low": 280
    },
    "recent_activity": {
      "added_today": 12,
      "accessed_today": 45
    }
  }
}
```

## ❤️ 心流处理API

### 1. 处理消息

```http
POST /api/v1/heartflow/process
Content-Type: application/json

{
  "message": {
    "content": "今天天气真好啊",
    "sender_info": {
      "user_id": "user_123",
      "username": "张三"
    },
    "chat_stream_id": "chat_001"
  },
  "context": {
    "previous_messages": ["昨天在下雨"],
    "current_emotion": "happy"
  }
}
```

响应:

```json
{
  "success": true,
  "data": {
    "response": "是啊！阳光明媚的天气总是让人心情愉快。您有什么户外活动的计划吗？",
    "emotion": "happy",
    "actions": [
      {
        "type": "emoji_response",
        "emoji": "😊",
        "probability": 0.85
      },
      {
        "type": "memory_update",
        "content": "用户提到今天天气好，心情愉快",
        "importance": 0.6
      }
    ],
    "processing_details": {
      "intent_recognition": "weather_chat",
      "emotion_analysis": "positive",
      "response_generation_time_ms": 890
    }
  }
}
```

### 2. 获取心流状态

```http
GET /api/v1/heartflow/status/{chat_stream_id}
```

### 3. 设置心流配置

```http
PUT /api/v1/heartflow/config/{chat_stream_id}
Content-Type: application/json

{
  "emotion_sensitivity": 0.8,
  "memory_strength": 0.7,
  "response_style": "friendly",
  "enable_auto_emoji": true
}
```

### 4. 心流分析

```http
GET /api/v1/heartflow/analysis/{chat_stream_id}?period=24h
```

## 😊 表情系统API

### 1. 发送表情

```http
POST /api/v1/emoji/send
Content-Type: application/json

{
  "emoji": "😊",
  "chat_stream_id": "chat_001",
  "trigger_type": "auto",  // auto | manual
  "context": {
    "message_content": "太好了！",
    "emotion": "happy"
  }
}
```

### 2. 获取表情包

```http
GET /api/v1/emoji/packs?platform=qq&category=happy
```

### 3. 创建表情包

```http
POST /api/v1/emoji/packs
Content-Type: application/json

{
  "pack_id": "custom_pack",
  "name": "自定义表情包",
  "description": "我的自定义表情",
  "emojis": [
    {
      "emoji": "😊",
      "tags": ["开心", "友好"],
      "usage_weight": 0.8
    }
  ]
}
```

### 4. 表情使用统计

```http
GET /api/v1/emoji/statistics?period=7d
```

## 🔌 插件系统API

### 1. 获取插件列表

```http
GET /api/v1/plugins?status=enabled&category=message_processing
```

### 2. 安装插件

```http
POST /api/v1/plugins/install
Content-Type: application/json

{
  "plugin_file": "path/to/plugin.zip",
  "config": {
    "auto_enable": true,
    "permissions": ["message_read", "message_send"]
  }
}
```

### 3. 启用/禁用插件

```http
POST /api/v1/plugins/{plugin_id}/enable
POST /api/v1/plugins/{plugin_id}/disable
```

### 4. 插件配置

```http
GET /api/v1/plugins/{plugin_id}/config
PUT /api/v1/plugins/{plugin_id}/config
```

### 5. 执行插件动作

```http
POST /api/v1/plugins/{plugin_id}/execute
Content-Type: application/json

{
  "action": "process_message",
  "parameters": {
    "message": "Hello",
    "context": {}
  }
}
```

## ⚙️ 配置管理API

### 1. 获取配置

```http
GET /api/v1/config?category=llm&platform=qq
```

### 2. 更新配置

```http
PUT /api/v1/config
Content-Type: application/json

{
  "category": "llm",
  "platform": "qq",
  "config": {
    "model": "gpt-4",
    "temperature": 0.8,
    "max_tokens": 2000,
    "timeout_seconds": 30
  }
}
```

### 3. 重置配置

```http
POST /api/v1/config/reset?category=llm
```

### 4. 配置历史

```http
GET /api/v1/config/history?category=llm&limit=10
```

## 📊 监控和统计API

### 1. 系统状态

```http
GET /api/v1/monitor/status
```

响应:

```json
{
  "success": true,
  "data": {
    "system_health": "healthy",
    "uptime_seconds": 86400,
    "performance": {
      "avg_response_time_ms": 150,
      "requests_per_second": 25.5,
      "error_rate_percent": 0.1
    },
    "resources": {
      "cpu_usage_percent": 45.2,
      "memory_usage_percent": 67.8,
      "disk_usage_percent": 23.1
    },
    "services": {
      "database": "healthy",
      "redis": "healthy",
      "llm_service": "healthy"
    }
  }
}
```

### 2. 使用量统计

```http
GET /api/v1/stats/usage?period=30d&group_by=day
```

### 3. 租户统计

```http
GET /api/v1/stats/tenants?period=7d
```

### 4. API调用统计

```http
GET /api/v1/stats/api?endpoint=chat/send&period=24h
```

### 5. 性能指标

```http
GET /api/v1/stats/performance?period=1h
```

## ❌ 错误处理

### 错误码列表

| 错误码 | HTTP状态码 | 描述 |
|--------|------------|------|
| `SUCCESS` | 200 | 操作成功 |
| `VALIDATION_ERROR` | 400 | 请求参数验证失败 |
| `UNAUTHORIZED` | 401 | 未授权访问 |
| `FORBIDDEN` | 403 | 权限不足 |
| `TENANT_NOT_FOUND` | 404 | 租户不存在 |
| `AGENT_NOT_FOUND` | 404 | 智能体不存在 |
| `CHAT_STREAM_NOT_FOUND` | 404 | 聊天流不存在 |
| `RATE_LIMIT_EXCEEDED` | 429 | 请求频率超限 |
| `INTERNAL_ERROR` | 500 | 服务器内部错误 |
| `SERVICE_UNAVAILABLE` | 503 | 服务不可用 |
| `ISOLATION_VIOLATION` | 403 | 隔离规则违反 |
| `QUOTA_EXCEEDED` | 429 | 配额超限 |

### 错误响应示例

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "请求参数验证失败",
    "details": {
      "field": "message",
      "issue": "消息内容不能为空"
    }
  },
  "timestamp": "2025-01-11T12:00:00Z",
  "request_id": "req_123456789"
}
```

## 🎯 最佳实践

### 1. 认证和安全

- **始终使用HTTPS**: 生产环境必须使用SSL/TLS加密
- **Token管理**: 定期刷新access token，安全存储refresh token
- **权限控制**: 遵循最小权限原则
- **请求签名**: 重要操作建议使用请求签名

### 2. 性能优化

- **批量操作**: 使用批量API减少请求次数
- **分页查询**: 大数据量查询使用分页
- **缓存策略**: 合理使用缓存减少数据库访问
- **异步处理**: 长时间操作使用异步模式

### 3. 错误处理

- **重试机制**: 网络错误实现指数退避重试
- **优雅降级**: 服务不可用时提供备选方案
- **错误监控**: 集成错误监控和告警
- **用户友好**: 提供清晰的错误提示

### 4. 监控和调试

- **请求追踪**: 使用request_id追踪请求链路
- **性能监控**: 监控API响应时间和错误率
- **日志记录**: 记录关键操作和错误信息
- **健康检查**: 定期检查服务健康状态

### 5. 版本管理

- **API版本**: 使用URL路径版本控制 (`/api/v1/`)
- **向后兼容**: 新版本保持对旧版本的兼容
- **废弃通知**: 提前通知API废弃计划
- **迁移指南**: 提供版本迁移指南

### 6. 租户隔离

- **上下文传递**: 始终在请求头中传递租户信息
- **数据隔离**: 确保不同租户数据完全隔离
- **资源限制**: 实施租户级别的资源限制
- **审计日志**: 记录租户级别的操作日志

### 7. 开发建议

```python
# Python SDK 使用示例
import requests
from maibot_client import MaiBotClient

# 初始化客户端
client = MaiBotClient(
    base_url="https://api.example.com/api/v1",
    tenant_id="your_tenant_id",
    api_key="your_api_key"
)

# 发送消息
response = client.chat.send_message(
    chat_stream_id="chat_001",
    message="你好！",
    sender_info={
        "user_id": "user_123",
        "username": "张三"
    }
)

# 处理响应
if response.success:
    print(f"AI回复: {response.data.response}")
else:
    print(f"错误: {response.error.message}")
```

### 8. JavaScript SDK 使用示例

```javascript
// JavaScript SDK 使用示例
import { MaiBotClient } from 'maibot-js-sdk';

// 初始化客户端
const client = new MaiBotClient({
  baseURL: 'https://api.example.com/api/v1',
  tenantId: 'your_tenant_id',
  apiKey: 'your_api_key'
});

// 发送消息
try {
  const response = await client.chat.sendMessage({
    chatStreamId: 'chat_001',
    message: '你好！',
    senderInfo: {
      userId: 'user_123',
      username: '张三'
    }
  });

  console.log('AI回复:', response.data.response);
} catch (error) {
  console.error('错误:', error.message);
}
```

## 📞 技术支持

### 获取帮助

1. **API文档**: 本文档提供完整的API参考
2. **SDK文档**: 各语言SDK的详细使用说明
3. **示例代码**: GitHub仓库提供完整的示例代码
4. **社区支持**: 通过GitHub Issues获取社区支持

### 联系方式

- **技术支持邮箱**: support@mai-mai.org
- **GitHub Issues**: https://github.com/MaiM-with-u/MaiBot/issues
- **文档网站**: https://docs.mai-mai.org

---

## 📚 相关文档

- [多租户迁移指南](./MULTI_TENANT_MIGRATION.md)
- [部署指南](./DEPLOYMENT_GUIDE.md)
- [测试报告](./TEST_REPORT.md)
- [项目总结](./MULTI_TENANT_MIGRATION_SUMMARY.md)

---

**版本**: v1.0.0
**最后更新**: 2025-01-11
**API状态**: 稳定版本 ✅