# MaiBot 多租户集成测试

已成功创建完整的多租户多智能体集成测试框架，模仿 mock_client 架构设计。

## 📁 文件结构

```
integration_tests/               # 集成测试模块
├── __init__.py                 # 模块初始化
├── config.py                   # 配置管理 (租户、智能体、场景配置)
├── message_generator.py        # LLM消息生成器 (支持OpenAI API和模拟消息)
├── client.py                   # 多租户测试客户端 (并发测试、结果统计)
├── main.py                     # 命令行入口 (完整参数支持)
├── test_config.toml           # 默认测试配置
└── README.md                  # 详细文档

run_integration_tests.py       # 简化运行脚本
```

## 🎯 核心特性

### ✅ 多租户隔离测试
- **租户A (科技公司)**: 技术助手智能体 + QQ平台
- **租户B (教育机构)**: 教育导师智能体 + 微信平台
- **租户C (个人用户)**: 通用伙伴智能体 + Discord平台

### ✅ 真实场景模拟
- **技术讨论群**: Python编程、算法优化、系统架构讨论
- **一对一教学**: 数学问题、学习方法、考试辅导
- **日常聊天**: 电影推荐、兴趣爱好、游戏讨论

### ✅ LLM驱动消息生成
- 支持OpenAI API生成真实对话消息
- 智能回退到预定义模板消息
- 根据智能体性格和场景定制消息风格

### ✅ 并发性能测试
- 支持多用户并发消息发送
- 实时性能指标统计 (成功率、消息速率)
- 详细的错误分析和报告

## 🚀 快速使用

### 1. 简单运行 (推荐)
```bash
# 使用默认配置运行场景测试
python run_integration_tests.py
```

### 2. 完整命令行
```bash
# 运行所有测试
python -m integration_tests.main

# 运行并发测试 (10个并发用户)
python -m integration_tests.main --mode concurrent --concurrent-users 10

# 使用自定义配置文件
python -m integration_tests.main --config my_config.toml --output results.json
```

### 3. 创建自定义配置
```bash
# 创建配置模板
python -m integration_tests.main --create-config my_test.toml
```

## 📊 测试报告示例

```
=== 多租户集成测试报告 ===
测试时间: 2024-01-15 14:30:25
测试场景数: 3

=== 总体统计 ===
总发送消息数: 47
总接收消息数: 38
总错误数: 2
总体成功率: 80.85%

=== 场景详情 ===
场景: 技术讨论群
  租户: tenant_a
  智能体: assistant_tech
  平台: qq
  发送消息: 15
  接收消息: 12
  成功率: 80.00%
  耗时: 12.34秒

=== 关键指标 ===
并发用户数: 3
总消息数: 47
成功率: 80.85%
消息速率: 3.81 msg/s
测试耗时: 12.34 秒
```

## 🔧 配置自定义

### 修改测试场景
编辑 `integration_tests/test_config.toml`:

```toml
[[scenarios]]
name = "自定义场景"
description = "我的测试场景"
tenant_id = "tenant_a"        # 选择租户
agent_id = "assistant_tech"   # 选择智能体
platform = "qq"               # 选择平台
user_id = "test_user_001"
message_count = 20
conversation_topics = ["主题1", "主题2", "主题3"]
```

### 修改并发参数
```toml
[settings]
concurrent_users = 5          # 并发用户数
message_delay_min = 0.5       # 消息延迟(秒)
message_delay_max = 2.0
log_level = "INFO"
```

### 配置LLM (可选)
```toml
[llm]
model_name = "gpt-3.5-turbo"
api_key = "your-openai-api-key"  # 设置后使用真实LLM生成消息
temperature = 0.8
max_tokens = 200
```

## 🧪 测试覆盖范围

### 多租户隔离 ✅
- 不同租户的数据完全隔离
- 租户级别的配置和记忆隔离
- 跨租户消息不会相互干扰

### 多智能体场景 ✅
- 技术助手: 专业、严谨、技术导向
- 教育导师: 耐心、亲切、教学导向
- 通用伙伴: 友善、幽默、日常导向

### 多平台支持 ✅
- QQ群聊场景
- 微信私聊场景
- Discord群组场景

### 并发压力测试 ✅
- 多用户同时发送消息
- 高并发下的系统稳定性
- 性能指标实时监控

## 📝 使用建议

1. **首次使用**: 运行 `python run_integration_tests.py` 体验基础功能
2. **性能测试**: 使用 `--mode concurrent --concurrent-users 20` 进行压力测试
3. **自定义场景**: 复制 `test_config.toml` 并修改配置文件
4. **持续集成**: 在CI/CD中集成集成测试确保代码质量

## 🐛 故障排除

- **LLM API不可用**: 自动使用模拟消息，不影响测试
- **服务器连接失败**: 检查MaiBot是否正常运行
- **配置文件错误**: 使用 `--create-config` 重新生成配置

这个集成测试框架为MaiBot的多租户架构提供了全面的测试覆盖，确保系统的稳定性和正确性。