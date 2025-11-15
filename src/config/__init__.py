"""
配置系统模块
提供向后兼容的配置访问，同时支持多租户隔离功能
"""

# 导入原有的配置对象（向后兼容）
from src.config.config import (
    global_config,
    load_config,
    Config,
    MMC_VERSION,
    model_config,
    api_ada_load_config,
    APIAdapterConfig,
)

# 导入新的多租户配置系统
from src.config.isolated_config_system import (
    get_isolated_config_system,
    get_isolated_config,
    set_isolated_config,
    get_isolated_full_config,
    initialize_isolated_config_system,
    isolated_config_context,
    with_isolated_config,
)

# 版本信息
__version__ = "1.0.0"


# 向后兼容的配置访问
def get_config(category: str, key: str = None, default=None):
    """
    向后兼容的配置访问函数

    Args:
        category: 配置分类名，如 'bot', 'personality' 等
        key: 配置键名，如果为None则返回整个分类的配置对象
        default: 默认值

    Returns:
        配置值或配置对象
    """
    if key is None:
        # 返回整个分类的配置对象
        if hasattr(global_config, category):
            return getattr(global_config, category)
        else:
            return default

    # 返回具体的配置值
    try:
        category_obj = getattr(global_config, category)
        if hasattr(category_obj, key):
            return getattr(category_obj, key)
        else:
            return default
    except (AttributeError, TypeError):
        return default


def set_config(category: str, key: str, value):
    """
    向后兼容的配置设置函数（仅影响内存中的全局配置）

    注意：这不会持久化到数据库，仅用于临时修改

    Args:
        category: 配置分类名
        key: 配置键名
        value: 配置值
    """
    try:
        category_obj = getattr(global_config, category)
        if hasattr(category_obj, key):
            setattr(category_obj, key, value)
        else:
            raise AttributeError(f"Config {category}.{key} does not exist")
    except AttributeError as e:
        raise ValueError(f"Failed to set config {category}.{key}: {e}")


def get_tenant_config(tenant_id: str, agent_id: str = "default", category: str = None, key: str = None, default=None):
    """
    获取租户特定的配置

    Args:
        tenant_id: 租户ID
        agent_id: 智能体ID
        category: 配置分类名
        key: 配置键名
        default: 默认值

    Returns:
        配置值
    """
    if category and key:
        return get_isolated_config(category, key, default, tenant_id, agent_id)
    elif category:
        # 返回整个分类的配置
        full_config = get_isolated_full_config(tenant_id, agent_id)
        return full_config.get(category, {})
    else:
        # 返回完整配置
        return get_isolated_full_config(tenant_id, agent_id)


def set_tenant_config(tenant_id: str, agent_id: str, category: str, key: str, value, level: str = "agent"):
    """
    设置租户特定的配置

    Args:
        tenant_id: 租户ID
        agent_id: 智能体ID
        category: 配置分类名
        key: 配置键名
        value: 配置值
        level: 配置级别 ('tenant', 'agent', 'platform')
    """
    return set_isolated_config(category, key, value, tenant_id, agent_id, level)


# 便捷的配置访问函数
def get_bot_config(key: str = None, default=None, tenant_id: str = None, agent_id: str = None):
    """获取bot配置"""
    if tenant_id and agent_id:
        return get_tenant_config(tenant_id, agent_id, "bot", key, default)
    else:
        return get_config("bot", key, default)


def get_personality_config(key: str = None, default=None, tenant_id: str = None, agent_id: str = None):
    """获取personality配置"""
    if tenant_id and agent_id:
        return get_tenant_config(tenant_id, agent_id, "personality", key, default)
    else:
        return get_config("personality", key, default)


def get_chat_config(key: str = None, default=None, tenant_id: str = None, agent_id: str = None):
    """获取chat配置"""
    if tenant_id and agent_id:
        return get_tenant_config(tenant_id, agent_id, "chat", key, default)
    else:
        return get_config("chat", key, default)


def get_emoji_config(key: str = None, default=None, tenant_id: str = None, agent_id: str = None):
    """获取emoji配置"""
    if tenant_id and agent_id:
        return get_tenant_config(tenant_id, agent_id, "emoji", key, default)
    else:
        return get_config("emoji", key, default)


def get_expression_config(key: str = None, default=None, tenant_id: str = None, agent_id: str = None):
    """获取expression配置"""
    if tenant_id and agent_id:
        return get_tenant_config(tenant_id, agent_id, "expression", key, default)
    else:
        return get_config("expression", key, default)


def get_memory_config(key: str = None, default=None, tenant_id: str = None, agent_id: str = None):
    """获取memory配置"""
    if tenant_id and agent_id:
        return get_tenant_config(tenant_id, agent_id, "memory", key, default)
    else:
        return get_config("memory", key, default)


def get_tool_config(key: str = None, default=None, tenant_id: str = None, agent_id: str = None):
    """获取tool配置"""
    if tenant_id and agent_id:
        return get_tenant_config(tenant_id, agent_id, "tool", key, default)
    else:
        return get_config("tool", key, default)


def get_voice_config(key: str = None, default=None, tenant_id: str = None, agent_id: str = None):
    """获取voice配置"""
    if tenant_id and agent_id:
        return get_tenant_config(tenant_id, agent_id, "voice", key, default)
    else:
        return get_config("voice", key, default)


def get_mood_config(key: str = None, default=None, tenant_id: str = None, agent_id: str = None):
    """获取mood配置"""
    if tenant_id and agent_id:
        return get_tenant_config(tenant_id, agent_id, "mood", key, default)
    else:
        return get_config("mood", key, default)


# 导出主要的类和函数
__all__ = [
    # 向后兼容的全局配置
    "global_config",
    "model_config",
    "load_config",
    "api_ada_load_config",
    "Config",
    "APIAdapterConfig",
    "MMC_VERSION",
    # 多租户配置系统
    "get_isolated_config_system",
    "get_isolated_config",
    "set_isolated_config",
    "get_isolated_full_config",
    "initialize_isolated_config_system",
    "isolated_config_context",
    "with_isolated_config",
    # 便捷函数
    "get_config",
    "set_config",
    "get_tenant_config",
    "set_tenant_config",
    "get_bot_config",
    "get_personality_config",
    "get_chat_config",
    "get_emoji_config",
    "get_expression_config",
    "get_memory_config",
    "get_tool_config",
    "get_voice_config",
    "get_mood_config",
]


# 模块初始化时自动初始化配置系统
try:
    # 初始化多租户配置系统
    initialize_isolated_config_system()
except Exception as e:
    import sys

    print(f"Warning: Failed to initialize isolated config system: {e}", file=sys.stderr)
    # 暂时禁用多租户系统以确保基础功能正常工作
    pass
