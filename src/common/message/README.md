# Agent配置系统（数据库版）

## 概述

本模块提供了数据库驱动的Agent配置管理功能，专门用于从maim_db数据库加载结构化的Agent配置，并与MaiMBot的基础配置进行融合。采用数据库优先的架构设计，确保配置的一致性和可管理性。

## 主要功能

### 1. 数据库专用
- **数据库驱动**: 仅从maim_db数据库加载结构化Agent配置
- **高性能**: 直接数据库访问，无中间层
- **类型安全**: 基于数据库模型的强类型配置

### 2. 配置融合
- 自动将Agent配置与MaiMBot基础配置融合
- 支持递归深度合并
- 保持配置对象的类型安全
- Agent配置优先级最高

### 3. 实时加载
- 无缓存设计，确保配置实时性
- 支持配置热重载
- 直接从数据库获取最新配置

### 4. 错误处理
- 完整的异常处理机制
- 数据库连接检测
- 详细的日志记录

## 使用方式

### 基本用法

```python
from src.common.message import (
    load_agent_config,
    create_merged_agent_config,
    get_available_agents
)

# 1. 从数据库加载Agent配置
agent_config = await load_agent_config("agent_456")

# 2. 创建融合配置
merged_config = await create_merged_agent_config("agent_456")

# 3. 获取可用Agent列表
agents = await get_available_agents()
```

### 数据库加载器使用

```python
from src.common.message import (
    load_agent_config_from_database,
    create_merged_config_from_database,
    get_db_agent_config_loader
)

# 检查数据库可用性
db_loader = get_db_agent_config_loader()
if db_loader.is_available():
    # 从数据库加载配置
    agent_config = await load_agent_config_from_database("agent_123")

    # 创建融合配置
    merged_config = await create_merged_config_from_database("agent_123")

    # 获取所有可用Agent
    available_agents = await db_loader.get_available_agents_from_database()
    print(f"可用Agent: {available_agents}")
else:
    print("数据库模块不可用")
```

### 配置重载

```python
from src.common.message import reload_agent_config

# 重新加载Agent配置（获取最新数据库配置）
reloaded_config = await reload_agent_config("agent_123")
if reloaded_config:
    print("配置重载成功")
else:
    print("配置重载失败")
```

## 配置结构

### AgentConfig主结构

```python
@dataclass
class AgentConfig:
    # 核心字段
    agent_id: str           # Agent唯一标识，格式: tenant_id:agent_id
    name: str               # Agent显示名称
    description: str         # 简要描述
    tags: List[str]         # 标签列表

    # 配置覆盖字段
    persona: PersonalityConfig      # 人格配置
    bot_overrides: BotOverrides     # Bot基础配置覆盖
    config_overrides: ConfigOverrides # 整体配置系统覆盖
```

### 人格配置

```python
@dataclass
class PersonalityConfig:
    personality: str        # 人格核心描述
    reply_style: str         # 回复风格
    interest: str            # 兴趣领域
    plan_style: str          # 群聊行为风格
    private_plan_style: str  # 私聊行为风格
    visual_style: str        # 视觉风格
    states: List[str]        # 状态列表
    state_probability: float # 状态切换概率
```

### 配置覆盖

支持以下配置类型的覆盖：
- **ChatConfig**: 聊天配置（上下文长度、规划器大小等）
- **BotConfig**: Bot基础配置（平台、昵称等）
- **ExpressionConfig**: 表达配置
- **MemoryConfig**: 记忆配置
- **MoodConfig**: 情绪配置
- **EmojiConfig**: 表情包配置
- **ToolConfig**: 工具配置
- **VoiceConfig**: 语音配置
- **PluginConfig**: 插件配置
- **KeywordReactionConfig**: 关键词反应配置
- **RelationshipConfig**: 关系配置

## 数据库架构

### 数据库模型
本模块基于maim_db数据库的以下模型进行配置管理：

- `PersonalityConfig`: 人格配置表
- `BotConfigOverrides`: Bot配置覆盖表
- `ChatConfigOverrides`: 聊天配置覆盖表
- `ExpressionConfigOverrides`: 表达配置覆盖表
- `MemoryConfigOverrides`: 记忆配置覆盖表
- `MoodConfigOverrides`: 情绪配置覆盖表
- `EmojiConfigOverrides`: 表情包配置覆盖表
- `ToolConfigOverrides`: 工具配置覆盖表
- `VoiceConfigOverrides`: 语音配置覆盖表
- `PluginConfigOverrides`: 插件配置覆盖表
- `KeywordReactionConfigOverrides`: 关键词反应配置覆盖表
- `RelationshipConfigOverrides`: 关系配置覆盖表

### 数据库特性
- 自动JSON字段解析和序列化
- agent_id索引和多租户支持
- 创建时间和更新时间追踪
- 关系模型自动注入agent_id

## 配置融合规则

### 优先级（从高到低）
1. **Agent配置覆盖** (`config_overrides`)
2. **MaiMBot基础配置** (`global_config`)

### 融合逻辑
- 数值类型：Agent配置覆盖基础配置
- 对象类型：递归深度合并
- 数组类型：完全替换
- None值：跳过不覆盖

## 实时配置策略

### 无缓存设计
- **实时加载**: 每次都从数据库获取最新配置
- **配置热重载**: 支持运行时配置更新
- **数据一致性**: 确保配置的实时性和一致性

### 配置操作
```python
from src.common.message import get_agent_config_loader, reload_agent_config

loader = get_agent_config_loader()

# 重新加载配置（获取最新数据库配置）
reloaded_config = await reload_agent_config("agent_123")

# 数据库模式无需清除缓存
loader.clear_all_cache()  # 输出: "数据库模式无需清除缓存"
```

## 错误处理

### 错误处理策略
1. **数据库不可用** → 返回None并记录错误
2. **配置加载失败** → 返回None并记录详细错误
3. **融合失败** → 返回None并记录详细错误
4. **数据库连接异常** → 记录错误并等待重试

### 日志记录
- 详细的成功/失败日志
- 配置加载性能监控
- 错误堆栈追踪

## 性能优化

### 推荐做法
1. **数据库索引**: 确保agent_id字段有索引
2. **批量操作**: 一次加载多个Agent配置
3. **异步加载**: 使用异步接口避免阻塞
4. **连接池**: 使用数据库连接池提高性能

### 性能监控
```python
# 检查数据库可用性
from src.common.message import get_db_agent_config_loader

db_loader = get_db_agent_config_loader()
print(f"数据库可用性: {db_loader.is_available()}")
```

## 最佳实践

### 1. 配置管理
- 使用数据库迁移管理配置变更
- 定期备份重要配置数据
- 遵循数据库命名规范

### 2. 错误处理
- 始终检查返回值是否为None
- 提供合理的默认配置
- 实现数据库重连机制

### 3. 性能优化
- 优化数据库查询性能
- 避免重复加载相同配置
- 使用异步数据库操作

### 4. 安全考虑
- 验证配置数据合法性
- 限制数据库访问权限
- 加密敏感配置字段

## 故障排除

### 常见问题

1. **数据库模块不可用**
   ```python
   from src.common.message import get_db_agent_config_loader
   loader = get_db_agent_config_loader()
   print(f"数据库可用性: {loader.is_available()}")
   ```

2. **配置加载失败**
   - 检查数据库连接
   - 验证agent_id是否存在
   - 查看详细错误日志

3. **配置融合失败**
   - 检查配置数据格式
   - 验证必填字段
   - 查看详细错误日志

### 调试技巧

```python
# 启用详细日志
import logging
logging.basicConfig(level=logging.DEBUG)

# 检查配置加载过程
from src.common.message import get_agent_config_loader
loader = get_agent_config_loader()

# 手动加载和检查
agent_config = await load_agent_config("test_agent")
print(f"加载结果: {agent_config}")
```

## 更新日志

### v2.0.0
- 重构为数据库专用架构
- 移除所有多数据源支持
- 优化配置加载性能
- 强化类型安全
- 简化API接口

### v1.0.0
- 初始版本发布
- 支持多数据源配置加载
- 实现配置融合机制
- 添加缓存和错误处理
- 支持数据库结构化配置

---

更多详细信息请参考代码注释和示例代码。