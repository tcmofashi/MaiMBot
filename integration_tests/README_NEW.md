# MaiMBot 集成测试系统

本文档介绍如何使用MaiMBot的集成测试系统，该系统实现了完整的多租户API测试流程。

## 功能概述

集成测试系统包含以下核心功能：

1. **多用户多Agent注册** - 通过配置器API注册测试用户并创建Agent
2. **WebSocket多路连接对话** - 使用maim_message创建多个WebSocket连接进行对话测试
3. **测试数据清理** - 自动清理测试创建的用户、Agent和相关聊天历史
4. **一键启动脚本** - 同时启动配置器后端和回复后端

## 系统架构

```
集成测试系统
├── api_client.py          # 配置器API客户端
├── websocket_test.py       # WebSocket多路连接测试
├── cleanup_test.py         # 测试数据清理功能
├── test_runner.py          # 主测试运行器
├── start_servers.py         # 一键启动脚本
├── start_servers.sh         # Bash版本启动脚本
└── README_NEW.md           # 使用说明文档
```

## 快速开始

### 1. 使用一键启动脚本

**Bash版本:**
```bash
# 启动双后端服务
bash start_servers.sh start

# 查看服务状态
bash start_servers.sh status

# 运行集成测试
bash start_servers.sh test

# 停止服务
bash start_servers.sh stop
```

**Python版本:**
```bash
# 启动双后端服务
python start_servers.py start

# 查看服务状态
python start_servers.py status

# 运行集成测试
python start_servers.py test

# 停止服务
python start_servers.py stop
```

### 2. 手动启动服务

**启动配置器后端:**
```bash
cd /path/to/MaiMBot
python -m src.api.main
# 服务将在 http://localhost:8000 启动
```

**启动回复后端:**
```bash
cd /path/to/MaiMBot
python bot.py
# 服务将在 http://localhost:8095 启动
```

### 3. 运行集成测试

```bash
# 运行默认测试 (3用户，每用户2Agent)
python integration_tests/test_runner.py

# 自定义测试参数
python integration_tests/test_runner.py --users 5 --agents 3

# 运行测试但不清理数据
python integration_tests/test_runner.py --no-cleanup
```

## 详细使用说明

### API客户端 (api_client.py)

用于与配置器后端交互，支持：

- 用户注册和登录
- Agent创建和管理
- 获取用户统计信息

**示例代码:**
```python
from integration_tests.api_client import create_test_scenario

# 创建测试场景
users, agents = await create_test_scenario(
    config_api_url="http://localhost:8000",
    user_count=3,
    agents_per_user=2
)

print(f"创建了 {len(users)} 个用户和 {len(agents)} 个Agent")
```

### WebSocket测试 (websocket_test.py)

创建多个WebSocket连接与回复后端进行对话测试：

- 支持并发连接
- 使用真实用户和Agent配置
- 多种对话场景
- 响应时间统计

**示例代码:**
```python
from integration_tests.websocket_test import run_websocket_tests

# 运行WebSocket测试
results = await run_websocket_tests(users, agents)
print(f"成功对话: {results['successful_conversations']}")
```

### 数据清理 (cleanup_test.py)

清理测试创建的数据，支持：

- 按用户列表清理
- 按租户ID清理
- 按用户名前缀清理
- 生成清理报告

**示例代码:**
```python
from integration_tests.cleanup_test import cleanup_test_scenario

# 清理测试数据
results = await cleanup_test_scenario(users, agents, save_report=True)
print(f"清理完成: {results['users']['users_cleaned']} 用户")
```

### 测试运行器 (test_runner.py)

协调整个测试流程：

- 自动启动服务器
- 执行完整测试流程
- 生成测试报告
- 自动清理资源

**示例代码:**
```python
from integration_tests.test_runner import run_integration_test

# 运行完整集成测试
results = await run_integration_test(
    user_count=3,
    agents_per_user=2,
    cleanup_after=True
)

print(f"测试{'成功' if results['success'] else '失败'}")
```

## 测试流程详解

### 1. 用户注册阶段
```
1. 生成测试用户数据 (username, password, email)
2. 调用配置器API注册用户
3. 获取JWT Token和API密钥
4. 保存用户认证信息
```

### 2. Agent创建阶段
```
1. 获取可用的Agent模板列表
2. 为每个用户创建多个Agent
3. 验证Agent创建成功
4. 记录Agent配置信息
```

### 3. WebSocket对话阶段
```
1. 为每个用户-Agent组合创建WebSocket连接
2. 发送测试消息 (基于不同Agent类型的对话主题)
3. 接收并记录回复消息
4. 统计响应时间和成功率
```

### 4. 数据清理阶段
```
1. 清理聊天历史记录 (messages, chat_streams)
2. 清理Agent配置 (agents)
3. 清理用户会话 (user_sessions)
4. 清理用户数据 (tenant_users)
5. 生成清理报告
```

## 测试数据说明

### 用户数据结构
- **用户名**: testuser_001, testuser_002, ...
- **密码**: testpass123 (固定)
- **邮箱**: testuser_001@example.com
- **租户名**: 测试租户_001, 测试租户_002, ...

### Agent配置
- **友好助手** (friendly_assistant): 日常对话
- **专业专家** (professional_expert): 技术咨询
- **创意伙伴** (creative_companion): 创意灵感
- **贴心朋友** (caring_friend): 情感陪伴
- **高效助手** (efficient_helper): 快速解答

### 对话场景
每个Agent类型都有对应的对话主题：
- 友好助手: 自我介绍、兴趣爱好、建议等
- 专业专家: AI技术、机器学习、深度学习等
- 创意伙伴: 故事创作、创意灵感等
- 贴心朋友: 心情关心、积极心态等
- 高效助手: 工作效率、时间管理等

## 日志和报告

### 日志文件
- `logs/startup.log` - 启动日志
- `logs/config_backend.log` - 配置器后端日志
- `logs/reply_backend.log` - 回复后端日志
- `integration_test.log` - 集成测试日志

### 测试报告
- `integration_test_results_*.json` - 详细测试结果
- `cleanup_report_*.json` - 数据清理报告

### 日志级别
- `INFO`: 正常操作信息
- `WARNING`: 警告信息
- `ERROR`: 错误信息
- `DEBUG`: 详细调试信息

## 故障排除

### 常见问题

**1. 端口占用**
```bash
# 查看端口占用
lsof -i :8000  # 配置器后端
lsof -i :8095  # 回复后端

# 强制停止占用进程
lsof -ti :8000 | xargs kill -9
lsof -ti :8095 | xargs kill -9
```

**2. 服务启动失败**
```bash
# 检查conda环境
conda activate maibot

# 检查Python路径
python -c "import sys; print(sys.path)"

# 检查依赖
pip list | grep fastapi
pip list | grep websockets
```

**3. WebSocket连接失败**
```bash
# 检查回复后端状态
curl http://localhost:8095/api/health

# 检查WebSocket连接
python -c "import websockets; print(websockets.__version__)"
```

**4. 数据清理失败**
```bash
# 手动检查数据库
sqlite3 MaiBot.db ".tables"

# 检查测试数据
sqlite3 MaiBot.db "SELECT COUNT(*) FROM tenant_users WHERE username LIKE 'testuser%';"
```

### 调试模式

启用详细日志：
```bash
# 修改日志级别
export LOG_LEVEL=DEBUG

# 运行测试
python integration_tests/test_runner.py --users 1 --agents 1
```

## 开发指南

### 添加新的测试场景

1. 在 `websocket_test.py` 中添加新的对话主题
2. 在 `api_client.py` 中添加新的API操作
3. 在 `test_runner.py` 中添加新的测试指标

### 扩展Agent模板

1. 在 `src/api/init_agent_templates.py` 中添加新模板
2. 更新 `websocket_test.py` 中的对话主题
3. 测试新模板的功能

### 性能优化

1. 调整并发用户数量
2. 优化WebSocket连接管理
3. 增加响应时间阈值设置

## 总结

MaiMBot集成测试系统提供了完整的多租户API测试能力，支持：

- ✅ 真实API调用测试
- ✅ WebSocket多路连接
- ✅ 自动化数据清理
- ✅ 详细测试报告
- ✅ 一键启动停止

该系统确保了MaiMBot多租户架构的功能完整性和稳定性，为开发和部署提供了可靠的测试保障。