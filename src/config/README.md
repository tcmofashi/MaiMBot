# 多租户隔离配置系统

本文档介绍MaiBot的多租户隔离配置系统，该系统支持T+A+P三维隔离（租户+智能体+平台）的多层配置继承。

## 概述

多租户隔离配置系统为MaiBot提供了完整的配置管理解决方案，支持：

- **三维隔离**：租户(Tenant) + 智能体(Agent) + 平台(Platform)
- **多层继承**：Global < Tenant < Agent < Platform
- **动态加载**：支持运行时配置热加载
- **缓存优化**：智能缓存机制提高性能
- **向后兼容**：完全兼容现有配置系统

## 架构设计

### 配置层级结构

```
Global（全局配置）
├── Tenant（租户配置）
│   ├── Agent（智能体配置）
│   │   └── Platform（平台配置）
│   └── Platform（平台配置）
└── Agent（智能体配置）
    └── Platform（平台配置）
```

配置继承优先级：Platform > Agent > Tenant > Global

### 核心组件

1. **IsolatedConfigManager** - 隔离配置管理器
2. **IsolatedConfigModels** - 数据库模型
3. **IsolatedConfigIntegration** - IsolationContext集成
4. **IsolatedConfigTools** - 配置管理工具
5. **IsolatedConfigSystem** - 系统主入口

## 快速开始

### 基础使用

```python
from src.config import get_tenant_config, set_tenant_config

# 获取租户配置
nickname = get_tenant_config("tenant1", "agent1", "bot", "nickname", "默认助手")

# 设置租户配置
set_tenant_config("tenant1", "agent1", "bot", "nickname", "智能助手", level="agent")
```

### 使用IsolationContext

```python
from src.isolation.isolation_context import create_isolation_context

# 创建隔离上下文
context = create_isolation_context("tenant1", "agent1", platform="qq")

# 直接获取配置
nickname = context.get_config("bot", "nickname")

# 设置配置
context.set_config("bot", "nickname", "QQ助手", level="platform")
```

### 使用配置管理器

```python
from src.config.isolated_config_manager import get_isolated_config_manager

# 获取配置管理器
config_manager = get_isolated_config_manager("tenant1", "agent1")

# 获取配置
nickname = config_manager.get_config("bot", "nickname", "默认助手")

# 设置配置
config_manager.set_config("bot", "nickname", "智能助手", level="agent")

# 获取完整有效配置
full_config = config_manager.get_effective_config()
```

## 配置继承示例

```python
from src.config.isolated_config_system import get_isolated_config_system

config_system = get_isolated_config_system()

# 1. 设置租户级别配置
config_system.set_config("bot", "nickname", "通用助手", tenant_id="tenant1", level="tenant")
config_system.set_config("chat", "max_length", 300, tenant_id="tenant1", level="tenant")

# 2. 设置智能体级别配置（覆盖租户配置）
config_system.set_config("bot", "nickname", "客服助手", tenant_id="tenant1", agent_id="agent1", level="agent")

# 3. 设置平台级别配置（覆盖智能体配置）
config_system.set_config("bot", "nickname", "QQ客服助手",
                        tenant_id="tenant1", agent_id="agent1",
                        level="platform", platform="qq")

# 查看继承效果
config_manager = get_isolated_config_manager("tenant1", "agent1")

qq_nickname = config_manager.get_config("bot", "nickname", platform="qq")  # "QQ客服助手"
wx_nickname = config_manager.get_config("bot", "nickname", platform="wx")  # "客服助手"
max_length = config_manager.get_config("chat", "max_length")  # 300 (来自租户配置)
```

## 配置管理工具

### 配置迁移

```python
from src.config.isolated_config_tools import migrate_global_to_tenant

# 从全局配置迁移到租户配置
result = migrate_global_to_tenant("tenant1", "agent1", overwrite=False)
print(f"迁移结果: {result}")
```

### 配置验证

```python
from src.config.isolated_config_system import get_isolated_config_system

config_system = get_isolated_config_system()

# 验证配置完整性
validation_result = config_system.validate_configs("tenant1", "agent1")
if not validation_result['valid']:
    print(f"配置验证失败: {validation_result['missing_configs']}")
```

### 配置导出导入

```python
# 导出配置
export_data = config_system.export_configs("tenant1", "agent1")

# 导入到另一个租户
import_result = config_system.import_configs(export_data, "tenant2", overwrite=False)
```

### 配置统计

```python
# 获取配置统计信息
stats = config_system.get_statistics()
print(f"租户数: {stats['tenants']}")
print(f"智能体数: {stats['agents']}")
print(f"配置项数: {stats['agent_configs']}")
```

## 数据库模型

### IsolatedConfigBase

配置基类，包含基础字段：

- `tenant_id` - 租户ID
- `agent_id` - 智能体ID
- `platform` - 平台ID（可选）
- `config_level` - 配置级别
- `config_category` - 配置分类
- `config_key` - 配置键
- `config_value` - 配置值
- `config_type` - 配置类型

### 具体模型

- `TenantConfig` - 租户级别配置
- `AgentConfig` - 智能体级别配置
- `PlatformConfig` - 平台级别配置
- `ConfigTemplate` - 配置模板
- `ConfigHistory` - 配置变更历史

## 缓存机制

系统实现了智能缓存机制：

- **内存缓存**：配置值缓存，提高访问速度
- **TTL机制**：可配置的缓存过期时间
- **自动失效**：配置变更时自动失效相关缓存
- **分层缓存**：不同隔离级别的配置独立缓存

```python
# 手动清理缓存
config_manager.cache_manager.invalidate("pattern")

# 重新加载配置
config_manager.reload_config()
```

## 配置变更通知

支持配置变更的实时通知：

```python
def on_config_change(config_key, old_value, new_value, context):
    print(f"配置变更: {config_key} = {old_value} -> {new_value}")

# 订阅配置变更
config_manager.subscribe_to_changes("bot.nickname", on_config_change)

# 取消订阅
config_manager.unsubscribe_from_changes("bot.nickname", on_config_change)
```

## 向后兼容性

新配置系统完全向后兼容现有代码：

```python
# 现有代码继续工作
from src.config import global_config
nickname = global_config.bot.nickname

# 新的便捷函数
from src.config import get_config, get_bot_config
nickname = get_config("bot", "nickname")  # 等同于上面
nickname = get_bot_config("nickname")     # 更简洁

# 多租户配置
nickname = get_bot_config("nickname", tenant_id="tenant1", agent_id="agent1")
```

## 配置文件结构

支持的配置文件格式：

- TOML格式（推荐）
- JSON格式

### 租户配置文件结构

```
config/
├── tenants/
│   └── {tenant_id}/
│       ├── tenant_config.toml      # 租户级别配置
│       └── agents/
│           └── {agent_id}/
│               └── agent_config.toml  # 智能体级别配置
```

### 配置文件示例

```toml
# tenant_config.toml
[inner]
version = "1.0.0"

[bot]
platform = "qq"
nickname = "租户助手"

[personality]
personality = "是一个友好的智能助手"
reply_style = "简洁明了的回复风格"
```

## 性能优化

### 缓存策略

- **默认TTL**: 5分钟
- **自动清理**: 每10分钟清理过期缓存
- **内存限制**: 基于LRU的缓存淘汰策略

### 数据库优化

- **复合索引**: 针对隔离字段创建复合索引
- **分页查询**: 大量配置的分页加载
- **连接池**: 数据库连接池管理

## 错误处理

### 常见错误

1. **配置不存在**
   ```python
   value = config_manager.get_config("category", "key", "default_value")
   ```

2. **权限错误**
   ```python
   # 验证租户权限
   if not validator.validate_tenant_access(context, target_tenant):
       raise PermissionError("租户权限不足")
   ```

3. **配置格式错误**
   ```python
   try:
       value = config_manager.get_config("category", "key")
   except ValueError as e:
       logger.error(f"配置格式错误: {e}")
   ```

## 最佳实践

### 1. 配置层级设计

- **Global**: 系统默认配置
- **Tenant**: 租户通用配置
- **Agent**: 智能体特定配置
- **Platform**: 平台特定配置

### 2. 配置命名规范

- 使用小写字母和下划线
- 按功能模块分类
- 使用有意义的名称

```python
# 好的命名
config_manager.set_config("bot", "max_message_length", 1000)
config_manager.set_config("memory", "retention_days", 30)

# 避免的命名
config_manager.set_config("bot", "maxLength", 1000)  # 驼峰命名
config_manager.set_config("misc", "temp_setting", 123)  # 模糊分类
```

### 3. 配置验证

```python
# 设置配置前验证
def validate_nickname(value):
    if not isinstance(value, str) or len(value.strip()) == 0:
        raise ValueError("昵称不能为空")
    if len(value) > 20:
        raise ValueError("昵称不能超过20个字符")

try:
    validate_nickname("新昵称")
    config_manager.set_config("bot", "nickname", "新昵称")
except ValueError as e:
    logger.error(f"配置验证失败: {e}")
```

### 4. 配置迁移

```python
# 生产环境配置迁移
def safe_migrate_config(tenant_id, agent_id):
    try:
        # 1. 验证现有配置
        validation = validate_tenant_configs(tenant_id, agent_id)
        if validation['valid']:
            logger.info("配置已存在且有效，跳过迁移")
            return

        # 2. 备份现有配置（如果有）
        # backup_existing_config(tenant_id, agent_id)

        # 3. 执行迁移
        result = migrate_global_to_tenant(tenant_id, agent_id, overwrite=False)

        # 4. 验证迁移结果
        validation = validate_tenant_configs(tenant_id, agent_id)
        if validation['valid']:
            logger.info(f"配置迁移成功: {result}")
        else:
            logger.error(f"配置迁移失败: {validation['errors']}")

    except Exception as e:
        logger.error(f"配置迁移异常: {e}")
        # rollback_migration(tenant_id, agent_id)
```

## 监控和调试

### 配置监控

```python
# 获取配置统计
stats = config_system.get_statistics()
logger.info(f"配置统计: {stats}")

# 监控配置变更
def monitor_config_changes():
    history = config_manager.get_config_history(limit=10)
    for record in history:
        logger.info(f"配置变更: {record['category']}.{record['key']} = {record['new_value']}")
```

### 调试工具

```python
# 检查配置来源
from src.config.isolated_config_integration import ConfigValidator

validator = ConfigValidator()
source_info = validator.validate_config_hierarchy(context)
print(f"配置来源: {source_info}")

# 检查缓存状态
cache_stats = config_manager.cache_manager._cache
print(f"缓存条目数: {len(cache_stats)}")
```

## 故障排除

### 常见问题

1. **配置未生效**
   - 检查配置层级是否正确
   - 验证配置权限
   - 检查缓存是否需要清理

2. **性能问题**
   - 检查缓存命中率
   - 监控数据库查询性能
   - 调整缓存TTL

3. **内存使用过高**
   - 清理过期缓存
   - 调整缓存大小限制
   - 检查内存泄漏

### 日志配置

```python
import logging
logging.getLogger('src.config').setLevel(logging.DEBUG)
```

## 扩展开发

### 自定义配置验证器

```python
class CustomConfigValidator:
    def validate_config(self, category, key, value):
        # 自定义验证逻辑
        return True, "验证通过"
```

### 自定义配置源

```python
class CustomConfigSource:
    def load_config(self, tenant_id, agent_id, platform=None):
        # 从自定义源加载配置
        return {}
```

## 版本历史

- **v1.0.0**: 初始版本，支持基础多租户隔离
- **v1.1.0**: 添加配置缓存和性能优化
- **v1.2.0**: 支持配置热加载和变更通知

## 贡献指南

欢迎贡献代码和提出改进建议。请确保：

1. 遵循现有代码风格
2. 添加适当的测试
3. 更新相关文档
4. 保持向后兼容性

## 许可证

本配置系统遵循MaiBot项目的许可证。