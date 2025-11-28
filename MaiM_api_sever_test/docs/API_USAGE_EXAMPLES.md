# MaiMBot API 使用示例

本文档提供了MaiMBot多租户API的详细使用示例，展示如何通过请求体参数传递租户和Agent信息。

## 概述

MaiMBot API支持两种版本：
- **v1**: 传统API，通过URL参数传递租户信息
- **v2**: 新版API，通过请求体参数传递租户和Agent信息（推荐）

## 认证方式

API支持多种认证方式：
1. JWT Token认证（推荐）
2. API Key认证
3. 请求体中的user_token
4. 请求体中的api_key

## API基础信息

- **基础URL**: `http://localhost:8095/api`
- **API版本**: v1, v2
- **认证**: Bearer Token 或 API Key
- **数据格式**: JSON

## 1. 用户注册和认证

### 1.1 用户注册

```bash
curl -X POST "http://localhost:8095/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "password123",
    "email": "test@example.com",
    "tenant_name": "测试租户",
    "tenant_type": "personal"
  }'
```

**响应示例**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400,
  "user_info": {
    "user_id": "user_abc123",
    "tenant_id": "tenant_def456",
    "username": "testuser",
    "email": "test@example.com",
    "tenant_name": "测试租户",
    "tenant_type": "personal",
    "api_key": "mb_xxxxxxxxxxxx",
    "status": "active"
  }
}
```

### 1.2 用户登录

```bash
curl -X POST "http://localhost:8095/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "password123"
  }'
```

### 1.3 获取当前用户信息

```bash
curl -X GET "http://localhost:8095/api/v1/auth/me" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

## 2. 租户管理

### 2.1 获取租户信息

```bash
curl -X GET "http://localhost:8095/api/v1/tenant" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### 2.2 更新租户信息

```bash
curl -X PUT "http://localhost:8095/api/v1/tenant" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_name": "新的租户名称",
    "email": "newemail@example.com"
  }'
```

### 2.3 获取租户统计信息

```bash
curl -X GET "http://localhost:8095/api/v1/tenant/stats" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

## 3. Agent管理

### 3.1 获取Agent模板列表

```bash
curl -X GET "http://localhost:8095/api/v1/agents/templates?category=general"
```

### 3.2 创建Agent（基于模板）

```bash
curl -X POST "http://localhost:8095/api/v1/agents" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "我的助手",
    "description": "一个友好的AI助手",
    "template_id": "friendly_assistant"
  }'
```

### 3.3 获取租户的Agent列表

```bash
curl -X GET "http://localhost:8095/api/v1/agents" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### 3.4 更新Agent配置

```bash
curl -X PUT "http://localhost:8095/api/v1/agents/agent_abc123" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "更新后的Agent名称",
    "description": "更新后的描述"
  }'
```

## 4. 聊天功能（v2 - 请求体参数）

### 4.1 基础聊天（请求体参数）

```bash
curl -X POST "http://localhost:8095/api/v2/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "你好，我想问一个问题",
    "tenant_id": "tenant_def456",
    "agent_id": "agent_abc123",
    "platform": "web",
    "user_id": "user_789"
  }'
```

**响应示例**:
```json
{
  "success": true,
  "message": "操作成功",
  "data": {
    "response": "你好！很高兴为你服务，请问有什么可以帮助你的吗？",
    "agent_id": "agent_abc123",
    "platform": "web",
    "chat_identifier": null,
    "tenant_id": "tenant_def456",
    "metadata": {
      "response_time": 1.23,
      "isolation_context": {
        "tenant_id": "tenant_def456",
        "agent_id": "agent_abc123",
        "platform": "web"
      }
    },
    "timestamp": "2024-01-01T12:00:00Z"
  },
  "request_id": "1704110400",
  "execution_time": 1.25
}
```

### 4.2 认证用户的聊天

```bash
curl -X POST "http://localhost:8095/api/v2/chat/auth" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "你好，我想问一个问题",
    "agent_id": "agent_abc123",
    "platform": "web"
  }'
```

### 4.3 使用API Key认证的聊天

```bash
curl -X POST "http://localhost:8095/api/v2/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "你好，我想问一个问题",
    "tenant_id": "tenant_def456",
    "agent_id": "agent_abc123",
    "api_key": "mb_xxxxxxxxxxxx"
  }'
```

### 4.4 批量聊天

```bash
curl -X POST "http://localhost:8095/api/v2/chat/batch" \
  -H "Content-Type: application/json" \
  -d '{
    "chat_requests": [
      {
        "message": "第一个问题",
        "tenant_id": "tenant_def456",
        "agent_id": "agent_abc123"
      },
      {
        "message": "第二个问题",
        "tenant_id": "tenant_def456",
        "agent_id": "agent_abc123"
      }
    ]
  }'
```

## 5. 获取Agent列表

### 5.1 通过查询参数获取

```bash
curl -X GET "http://localhost:8095/api/v2/chat-agents?tenant_id=tenant_def456"
```

## 6. 错误处理

### 6.1 认证错误

```json
{
  "error": {
    "code": 401,
    "message": "未提供有效的认证信息",
    "type": "http_error"
  }
}
```

### 6.2 权限错误

```json
{
  "error": {
    "code": 403,
    "message": "无权访问指定租户",
    "type": "http_error"
  }
}
```

### 6.3 资源不存在错误

```json
{
  "error": {
    "code": 404,
    "message": "智能体不存在: agent_invalid123",
    "type": "http_error"
  }
}
```

## 7. Python SDK 示例

```python
import requests
import json

class MaiBotAPIClient:
    def __init__(self, base_url="http://localhost:8095/api"):
        self.base_url = base_url
        self.access_token = None
        self.tenant_id = None

    def register(self, username, password, email=None, tenant_name=None):
        """用户注册"""
        url = f"{self.base_url}/v1/auth/register"
        data = {
            "username": username,
            "password": password,
            "email": email,
            "tenant_name": tenant_name or f"{username}的租户"
        }

        response = requests.post(url, json=data)
        result = response.json()

        if response.status_code == 201:
            self.access_token = result["access_token"]
            self.tenant_id = result["user_info"]["tenant_id"]

        return result

    def login(self, username, password):
        """用户登录"""
        url = f"{self.base_url}/v1/auth/login"
        data = {"username": username, "password": password}

        response = requests.post(url, json=data)
        result = response.json()

        if response.status_code == 200:
            self.access_token = result["access_token"]
            self.tenant_id = result["user_info"]["tenant_id"]

        return result

    def chat(self, message, agent_id="default", platform="web", user_id=None):
        """发送聊天消息（v2 API）"""
        url = f"{self.base_url}/v2/chat"

        headers = {"Content-Type": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        data = {
            "message": message,
            "tenant_id": self.tenant_id,
            "agent_id": agent_id,
            "platform": platform,
            "user_id": user_id
        }

        response = requests.post(url, json=data, headers=headers)
        return response.json()

    def get_agents(self):
        """获取Agent列表"""
        url = f"{self.base_url}/v1/agents"

        headers = {}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        response = requests.get(url, headers=headers)
        return response.json()

    def create_agent(self, name, template_id=None, description=None):
        """创建Agent"""
        url = f"{self.base_url}/v1/agents"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.access_token}"
        }

        data = {
            "name": name,
            "description": description,
            "template_id": template_id
        }

        response = requests.post(url, json=data, headers=headers)
        return response.json()

# 使用示例
if __name__ == "__main__":
    client = MaiBotAPIClient()

    # 注册用户
    register_result = client.register(
        username="testuser",
        password="password123",
        email="test@example.com",
        tenant_name="测试租户"
    )
    print("注册结果:", register_result)

    # 或者登录现有用户
    # login_result = client.login("testuser", "password123")
    # print("登录结果:", login_result)

    # 获取Agent模板
    # templates_response = requests.get(f"{client.base_url}/v1/agents/templates")
    # templates = templates_response.json()
    # print("可用模板:", templates)

    # 创建Agent
    agent_result = client.create_agent(
        name="我的助手",
        template_id="friendly_assistant",
        description="一个友好的AI助手"
    )
    print("创建Agent结果:", agent_result)

    # 发送聊天消息
    chat_result = client.chat(
        message="你好，请介绍一下自己",
        agent_id="agent_abc123"  # 使用实际创建的Agent ID
    )
    print("聊天结果:", chat_result)
```

## 8. 最佳实践

### 8.1 认证管理
- 使用JWT Token进行用户认证
- 妥善保存刷新令牌
- 定期轮换API密钥

### 8.2 错误处理
- 检查HTTP状态码
- 处理网络超时
- 实现重试机制

### 8.3 性能优化
- 使用批量聊天接口处理多条消息
- 缓存Agent模板信息
- 合理设置请求超时时间

### 8.4 安全考虑
- 使用HTTPS进行生产环境部署
- 验证输入参数
- 限制API调用频率

## 9. 故障排除

### 9.1 常见问题

**Q: 如何获取租户ID？**
A: 用户注册后会自动生成租户ID，也可以通过 `/api/v1/auth/me` 接口获取。

**Q: Agent ID在哪里获取？**
A: 创建Agent后会返回agent_id，也可以通过 `/api/v1/agents` 接口查看所有Agent。

**Q: 如何处理认证过期？**
A: 使用refresh_token重新获取access_token，或者重新登录。

**Q: 批量请求有限制吗？**
A: v1 API最多支持100条，v2 API最多支持50条。

### 9.2 调试技巧

1. 检查API响应中的metadata字段获取调试信息
2. 使用 `/api/health` 接口检查服务状态
3. 查看服务日志获取详细错误信息

## 10. 更多信息

- [API文档](http://localhost:8095/docs)
- [ReDoc文档](http://localhost:8095/redoc)
- [项目源码](https://github.com/MaiM-with-u/MaiBot)
