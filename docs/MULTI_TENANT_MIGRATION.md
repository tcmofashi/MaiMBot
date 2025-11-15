# MaiBot 多租户隔离数据库迁移指南

本文档介绍如何使用MaiBot的多租户隔离数据库迁移工具，将现有的数据库结构升级为支持T+A+C+P四维隔离的架构。

## 📋 目录

- [迁移概述](#迁移概述)
- [前置要求](#前置要求)
- [迁移步骤](#迁移步骤)
- [验证迁移](#验证迁移)
- [新功能使用](#新功能使用)
- [故障排除](#故障排除)

## 🎯 迁移概述

### 什么是T+A+C+P四维隔离？

- **T (Tenant)**: 租户隔离 - 不同租户的数据完全隔离
- **A (Agent)**: 智能体隔离 - 同一租户不同智能体的配置和记忆隔离
- **C (Chat)**: 聊天流隔离 - 基于聊天流ID的上下文隔离
- **P (Platform)**: 平台隔离 - QQ、Discord等不同通信平台的隔离

### 支持的表

迁移会影响以下数据库表：

- ✅ **ChatStreams** - 聊天流表（T+A+C+P）
- ✅ **Messages** - 消息记录表（T+A+C+P）
- ✅ **MemoryChest** - 记忆存储表（T+A+C+P，支持多级记忆）
- ✅ **AgentRecord** - 智能体配置表（T+A）
- ✅ **LLMUsage** - LLM使用量统计表（T+A+P）
- ✅ **Expression** - 表达风格表（T+A+C）
- ✅ **ActionRecords** - 动作记录表（T+A+C）
- ✅ **Jargon** - 黑话收集表（T+A+C）
- ✅ **PersonInfo** - 个人信息表（T）
- ✅ **GroupInfo** - 群组信息表（T）

## 🔧 前置要求

### 1. 数据库备份

**重要：迁移前请务必备份数据库！**

```bash
# SQLite 数据库备份
cp MaiBot.db MaiBot.db.backup.$(date +%Y%m%d_%H%M%S)

# 或者使用其他适合你数据库的备份方法
```

### 2. 环境准备

确保你有一个可运行的MaiBot环境：

```bash
# 确保Python环境正确
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

## 🚀 迁移步骤

### 步骤 1: 检查当前状态

```bash
# 检查迁移状态
python scripts/run_multi_tenant_migration.py --check
```

预期输出：
```
============================================================
MaiBot 多租户隔离迁移状态
============================================================
状态: ⚠️ 未迁移
信息: 数据库未完成多租户迁移
============================================================
```

### 步骤 2: 执行迁移

```bash
# 执行迁移（推荐）
python scripts/run_multi_tenant_migration.py --migrate

# 或强制执行（跳过安全检查）
python scripts/run_multi_tenant_migration.py --force
```

迁移过程包括：
1. ✅ 安全检查
2. ✅ 添加隔离字段
3. ✅ 迁移现有数据
4. ✅ 创建复合索引
5. ✅ 验证数据完整性

### 步骤 3: 验证迁移结果

```bash
# 再次检查状态
python scripts/run_multi_tenant_migration.py --check
```

成功迁移后的输出：
```
============================================================
MaiBot 多租户隔离迁移状态
============================================================
状态: ✅ 已完成
信息: 迁移完成

迁移记录:
  - 名称: multi_tenant_isolation
  - 版本: 1.0.0
  - 执行时间: 2025-01-11 12:00:00

表状态:
  ✅ chat_streams
  ✅ messages
  ✅ memory_chest
  ✅ agents
  ✅ llm_usage
  ✅ expression
  ✅ action_records
  ✅ jargon
  ✅ person_info
  ✅ group_info
============================================================
```

## 🔍 验证迁移

### 手动验证数据库结构

```sql
-- 检查 chat_streams 表结构
PRAGMA table_info(chat_streams);

-- 应该看到新增的字段：
-- tenant_id, agent_id, platform, chat_stream_id

-- 检查索引
PRAGMA index_list(chat_streams);

-- 应该看到复合索引：
-- idx_chat_streams_isolation
-- idx_chat_streams_tenant_agent
```

### 检查数据迁移

```sql
-- 验证现有数据已正确设置租户信息
SELECT
    tenant_id,
    agent_id,
    COUNT(*) as count
FROM chat_streams
GROUP BY tenant_id, agent_id;
```

## 📖 新功能使用

### 1. 使用隔离查询管理器

```python
from src.isolation.isolation_context import create_isolation_context
from src.common.database.isolation_query_examples import get_isolated_query_manager

# 创建隔离上下文
context = create_isolation_context(
    tenant_id="your_tenant",
    agent_id="your_agent",
    platform="qq"  # 可选
)

# 获取查询管理器
query_manager = get_isolated_query_manager(context)

# 查询聊天流（自动隔离）
chat_streams = query_manager.chat_streams.get_all_chat_streams()
print(f"找到 {len(chat_streams)} 个聊天流")

# 查询消息（自动隔离）
messages = query_manager.messages.get_recent_messages(hours=24)
print(f"最近24小时有 {len(messages)} 条消息")
```

### 2. 多层次记忆查询

```python
# 查询智能体级别的记忆
agent_memories = query_manager.memories.get_agent_memories(limit=10)

# 查询平台级别的记忆
platform_memories = query_manager.memories.get_platform_memories("qq", limit=5)

# 查询聊天流级别的记忆
chat_memories = query_manager.memories.get_chat_memories("chat123", limit=5)

# 搜索记忆内容
found_memories = query_manager.memories.search_memories("关键词", "agent")
```

### 3. 使用统计功能

```python
# 获取租户概览
overview = query_manager.get_tenant_overview()
print(f"租户概览: {overview}")

# 获取使用量统计
usage_stats = query_manager.usage.get_usage_statistics(days=30)
print(f"30天使用统计: {usage_stats}")
```

## 🛠 故障排除

### 常见问题

#### 1. 迁移失败：数据库连接错误

```
错误: 数据库连接失败
解决: 检查数据库配置和权限
```

#### 2. 迁移失败：表不存在

```
错误: 关键表 xxx 不存在
解决: 确保运行的是正确的数据库实例
```

#### 3. 迁移缓慢：大量数据

```
现象: 迁移过程很慢
原因: 数据量过大
建议:
- 先在小规模数据测试
- 考虑分批迁移
- 确保服务器资源充足
```

### 回滚操作

**警告：回滚操作会导致数据丢失，请谨慎操作！**

```python
# 检查是否可以回滚
from src.common.database.multi_tenant_migration import MultiTenantMigration

migration = MultiTenantMigration()
# SQLite限制：无法直接删除列，需要手动重建表
```

对于SQLite，回滚需要：
1. 恢复备份文件
2. 或手动重建表结构

### 获取帮助

如果遇到问题：

1. 📋 查看详细日志：
   ```bash
   tail -f logs/multi_tenant_migration.log
   ```

2. 🔍 检查数据库完整性：
   ```sql
   PRAGMA integrity_check;
   ```

3. 📞 联系开发团队，提供：
   - 错误日志
   - 数据库版本
   - 迁移前的表结构

## 📚 相关文档

- [refactor.md](../refactor.md) - 完整的多租户改造方案
- [isolation_context.py](../src/isolation/isolation_context.py) - 隔离上下文实现
- [isolation_query_examples.py](../src/common/database/isolation_query_examples.py) - 查询示例

## 🎉 迁移完成

恭喜！您已成功完成MaiBot的多租户隔离数据库迁移。现在您的系统支持：

- 🔒 完全的数据租户隔离
- 🤖 智能体级别的配置和记忆隔离
- 💬 聊天流级别的上下文隔离
- 🌐 平台级别的数据隔离
- ⚡ 优化的查询性能
- 🔄 向后兼容性

接下来可以继续按照refactor.md完成其他模块的多租户改造。