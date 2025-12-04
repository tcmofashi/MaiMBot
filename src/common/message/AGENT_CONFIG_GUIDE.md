# Agent专用配置获取指南

## 概述

本指南详细介绍如何从数据库获取Agent专用的global_config和model_config配置，实现Agent级别个性化配置。

## 核心概念

### 配置层次结构
1. **基础配置** - MaiMBot的全局默认配置
2. **Agent配置** - 数据库中存储的Agent特定配置
3. **融合配置** - 基础配置与Agent配置融合后的最终配置

### 配置融合规则
- **Agent配置优先级**: 数据库中的Agent配置覆盖基础配置
- **递归合并**: 支持深层嵌套配置的智能合并
- **类型安全**: 保持配置对象的类型完整性

## 主要API接口

### 1. 获取Agent配置对象
```python
from src.common.message import load_agent_config

# 获取Agent原始配置对象
agent_config = await load_agent_config("agent_123")
if agent_config:
    print(f"Agent名称: {agent_config.name}")
    print(f"人格描述: {agent_config.persona.personality}")
```

### 2. 获取融合后的完整配置
```python
from src.common.message import create_merged_agent_config

# 获取融合后的完整配置（推荐）
merged_config = await create_merged_agent_config("agent_123")
if merged_config:
    # merged_config包含所有配置模块的完整融合结果
    bot_config = merged_config["bot"]
    personality_config = merged_config["personality"]
    chat_config = merged_config["chat"]
    # ... 其他配置模块
```

### 3. 获取global_config（全局配置）
```python
from src.common.message import create_agent_global_config

# 获取Agent专用的global_config
agent_global_config = await create_agent_global_config("agent_123")
if agent_global_config:
    # 包含Bot、Personality、Chat等基础配置模块
    print(f"Bot平台: {agent_global_config.bot.platform}")
    print(f"昵称: {agent_global_config.bot.nickname}")
    print(f"人格: {agent_global_config.personality.personality}")
```

### 4. 获取model_config（模型配置）
```python
from src.common.message import create_agent_model_config

# 获取Agent专用的model_config
agent_model_config = await create_agent_model_config("agent_123")
if agent_model_config:
    # 包含LLM模型相关配置
    print(f"模型名称: {agent_model_config.model_name}")
    print(f"温度设置: {agent_model_config.temperature}")
```

## 使用示例

### 完整的Agent配置获取流程
```python
import asyncio
from src.common.message import (
    load_agent_config,
    create_merged_agent_config,
    create_agent_global_config,
    create_agent_model_config,
    get_db_agent_config_loader
)

async def setup_agent_config(agent_id: str):
    """完整的Agent配置获取流程"""

    # 1. 检查数据库可用性
    db_loader = get_db_agent_config_loader()
    if not db_loader.is_available():
        print("❌ 数据库模块不可用")
        return None, None

    # 2. 获取Agent原始配置
    agent_config = await load_agent_config(agent_id)
    if not agent_config:
        print(f"❌ Agent配置不存在: {agent_id}")
        return None, None

    print(f"✅ 成功加载Agent配置: {agent_config.name}")

    # 3. 获取融合后的global_config
    agent_global_config = await create_agent_global_config(agent_id)
    if not agent_global_config:
        print("❌ 创建global_config失败")
        return None, None

    # 4. 获取融合后的model_config
    agent_model_config = await create_agent_model_config(agent_id)
    if not agent_model_config:
        print("❌ 创建model_config失败")
        return None, None

    print("✅ 成功创建Agent专用配置")
    return agent_global_config, agent_model_config

# 使用示例
async def main():
    agent_id = "agent_123"
    global_config, model_config = await setup_agent_config(agent_id)

    if global_config and model_config:
        print(f"Agent {agent_id} 配置加载完成:")
        print(f"  - 平台: {global_config.bot.platform}")
        print(f"  - 昵称: {global_config.bot.nickname}")
        print(f"  - 人格: {global_config.personality.personality[:50]}...")
        print(f"  - 模型: {model_config.model_name}")
        print(f"  - 温度: {model_config.temperature}")

if __name__ == "__main__":
    asyncio.run(main())
```

### 配置重载机制
```python
from src.common.message import reload_agent_config, create_agent_global_config

async def reload_agent_setup(agent_id: str):
    """重新加载Agent配置"""

    print(f"🔄 重新加载Agent配置: {agent_id}")

    # 重新加载配置（从数据库获取最新配置）
    reloaded_config = await reload_agent_config(agent_id)
    if reloaded_config:
        print("✅ 配置重载成功")

        # 重新创建global_config和model_config
        global_config = await create_agent_global_config(agent_id)
        model_config = await create_agent_model_config(agent_id)

        return global_config, model_config
    else:
        print("❌ 配置重载失败")
        return None, None
```

## 配置模块详解

### global_config 包含的模块
- **bot**: Bot基础配置（平台、账号、昵称等）
- **personality**: 人格配置（性格、回复风格、兴趣等）
- **chat**: 聊天配置（上下文长度、规划器大小等）
- **relationship**: 关系配置
- **expression**: 表达配置
- **memory**: 记忆配置
- **mood**: 情绪配置
- **emoji**: 表情包配置
- **tool**: 工具配置
- **voice**: 语音配置
- **keyword_reaction**: 关键词反应配置

### model_config 包含的模块
- **model_name**: 模型名称
- **temperature**: 温度设置
- **max_tokens**: 最大token数
- **top_p**: top_p参数
- **frequency_penalty**: 频率惩罚
- **presence_penalty**: 存在惩罚
- **其他LLM参数**

## 错误处理

### 常见错误处理
```python
from src.common.message import load_agent_config, get_db_agent_config_loader

async def safe_load_agent_config(agent_id: str):
    """安全的Agent配置加载"""

    # 1. 检查数据库可用性
    db_loader = get_db_agent_config_loader()
    if not db_loader.is_available():
        raise Exception("数据库模块不可用，请检查maim_db安装")

    # 2. 加载Agent配置
    agent_config = await load_agent_config(agent_id)
    if not agent_config:
        raise Exception(f"Agent配置不存在或加载失败: {agent_id}")

    return agent_config

# 使用示例
async def example_with_error_handling():
    try:
        agent_config = await safe_load_agent_config("agent_123")
        print(f"✅ 成功加载: {agent_config.name}")

    except Exception as e:
        print(f"❌ 配置加载失败: {e}")
        # 可以在这里实现降级逻辑或错误恢复
```

### 数据库连接问题处理
```python
async def check_database_health():
    """检查数据库健康状态"""
    from src.common.message import get_db_agent_config_loader

    db_loader = get_db_agent_config_loader()

    if db_loader.is_available():
        print("✅ 数据库连接正常")
        return True
    else:
        print("❌ 数据库连接异常")
        print("可能的原因:")
        print("  - maim_db模块未安装")
        print("  - 数据库连接参数错误")
        print("  - 数据库服务未启动")
        return False
```

## 性能优化建议

### 1. 配置缓存策略
```python
# 虽然系统是无缓存的实时加载，但可以在应用层实现缓存
import asyncio
from typing import Dict, Any
from src.common.message import create_agent_global_config

class AgentConfigCache:
    def __init__(self, ttl: int = 300):  # 5分钟TTL
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.ttl = ttl

    async def get_config(self, agent_id: str):
        # 检查缓存
        if agent_id in self.cache:
            cached_time, config = self.cache[agent_id]
            if asyncio.get_event_loop().time() - cached_time < self.ttl:
                return config

        # 加载新配置
        config = await create_agent_global_config(agent_id)
        if config:
            self.cache[agent_id] = (asyncio.get_event_loop().time(), config)

        return config

# 使用示例
config_cache = AgentConfigCache()
agent_config = await config_cache.get_config("agent_123")
```

### 2. 批量配置加载
```python
from src.common.message import get_available_agents

async def load_multiple_agents_config():
    """批量加载多个Agent配置"""

    # 获取所有可用Agent
    agents_info = await get_available_agents()
    if not agents_info or "agents" not in agents_info:
        return {}

    agent_ids = [agent["agent_id"] for agent in agents_info["agents"]]
    configs = {}

    # 并行加载配置
    tasks = [
        create_agent_global_config(agent_id)
        for agent_id in agent_ids
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for agent_id, result in zip(agent_ids, results):
        if isinstance(result, Exception):
            print(f"❌ 加载Agent {agent_id} 配置失败: {result}")
        else:
            configs[agent_id] = result
            print(f"✅ 成功加载Agent {agent_id} 配置")

    return configs
```

## 最佳实践

### 1. 配置验证
```python
def validate_agent_config(global_config, model_config) -> bool:
    """验证配置完整性"""

    # 检查必需字段
    required_fields = [
        ("global_config", global_config, ["bot", "personality"]),
        ("model_config", model_config, ["model_name"])
    ]

    for config_name, config, fields in required_fields:
        if not config:
            print(f"❌ {config_name} 不能为空")
            return False

        for field in fields:
            if not hasattr(config, field):
                print(f"❌ {config_name} 缺少必需字段: {field}")
                return False

    print("✅ 配置验证通过")
    return True
```

### 2. 配置更新监听
```python
async def watch_agent_config_changes(agent_id: str, interval: int = 60):
    """监听Agent配置变化"""

    last_config_hash = None

    while True:
        try:
            # 获取当前配置
            current_config = await create_agent_global_config(agent_id)

            # 计算配置哈希
            import hashlib
            import json
            config_str = json.dumps(current_config.__dict__, sort_keys=True)
            current_hash = hashlib.md5(config_str.encode()).hexdigest()

            # 检查是否有变化
            if last_config_hash and current_hash != last_config_hash:
                print(f"🔄 Agent {agent_id} 配置已更新")
                # 这里可以触发配置重载逻辑

            last_config_hash = current_hash
            await asyncio.sleep(interval)

        except Exception as e:
            print(f"❌ 监听配置变化时出错: {e}")
            await asyncio.sleep(interval)
```

## 故障排除

### 常见问题及解决方案

1. **Agent配置不存在**
   ```python
   # 检查Agent是否存在
   from src.common.message import get_available_agents
   agents = await get_available_agents()
   available_ids = [a["agent_id"] for a in agents.get("agents", [])]

   if agent_id not in available_ids:
       print(f"Agent {agent_id} 不存在")
       print(f"可用Agent: {available_ids}")
   ```

2. **配置融合失败**
   ```python
   # 检查基础配置是否正常
   try:
       from src.config.config import global_config
       print(f"基础配置加载成功，包含模块: {list(global_config.__dict__.keys())}")
   except Exception as e:
       print(f"基础配置加载失败: {e}")
   ```

3. **数据库连接问题**
   ```python
   # 详细检查数据库状态
   from src.common.message import get_db_agent_config_loader

   db_loader = get_db_agent_config_loader()
   print(f"数据库模块导入状态: {db_loader.is_available()}")

   if not db_loader.is_available():
       print("请检查:")
       print("1. maim_db模块是否正确安装")
       print("2. 数据库连接参数是否正确")
       print("3. 数据库服务是否正常运行")
   ```

---

更多详细信息请参考：
- [Agent配置数据模型](agent_config.py)
- [数据库加载器](db_agent_config_loader.py)
- [配置融合器](config_merger.py)
- [使用示例](example_usage.py)