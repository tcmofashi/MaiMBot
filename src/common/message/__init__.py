"""
Message模块 - 包含消息处理和Agent配置相关功能

主要功能：
1. WebSocket API服务器配置和消息处理
2. Agent配置数据模型（数据库驱动）
3. 配置融合器
4. Agent配置加载器（仅数据库）

使用示例：
```python
from src.common.message import get_global_api, load_agent_config, create_merged_agent_config

# 启动WebSocket服务器
api_server = get_global_api()

# 从数据库加载Agent配置
agent_config = await load_agent_config("agent_456")

# 创建融合配置
merged_config = await create_merged_agent_config("agent_456")
```
"""

__version__ = "0.2.0"

# API相关
from .api import get_global_api, MaimConfigClient, load_message_config

# Agent配置数据模型
from .agent_config import AgentConfig, PersonalityConfig, BotOverrides, ConfigOverrides, agent_config_to_dict

# 配置融合
from .config_merger import (
    ConfigMerger,
    get_config_merger,
    create_agent_config,
    create_agent_global_config,
    create_agent_model_config,
)

# 配置加载（数据库专用）
from .agent_config_loader import (
    AgentConfigLoader,
    get_agent_config_loader,
    load_agent_config,
    create_merged_agent_config,
    reload_agent_config,
    get_available_agents,
)

# 数据库配置加载器
from .db_agent_config_loader import (
    DatabaseAgentConfigLoader,
    get_db_agent_config_loader,
    load_agent_config_from_database,
    create_merged_config_from_database,
    get_available_agents_from_database,
)


__all__ = [
    # 版本信息
    "__version__",
    # API相关
    "get_global_api",
    "MaimConfigClient",
    "load_message_config",
    # Agent配置数据模型
    "AgentConfig",
    "PersonalityConfig",
    "BotOverrides",
    "ConfigOverrides",
    "agent_config_to_dict",
    # 配置融合
    "ConfigMerger",
    "get_config_merger",
    "create_agent_config",
    "create_agent_global_config",
    "create_agent_model_config",
    # 配置加载（数据库专用）
    "AgentConfigLoader",
    "get_agent_config_loader",
    "load_agent_config",
    "create_merged_agent_config",
    "reload_agent_config",
    "get_available_agents",
    # 数据库配置加载器
    "DatabaseAgentConfigLoader",
    "get_db_agent_config_loader",
    "load_agent_config_from_database",
    "create_merged_config_from_database",
    "get_available_agents_from_database",
]
