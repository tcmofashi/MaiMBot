"""
配置系统与IsolationContext的集成模块
提供隔离感知的配置获取接口
"""

from typing import Optional, Dict, Any
from src.isolation.isolation_context import IsolationContext
from src.config.isolated_config_manager import get_isolated_config_manager, IsolatedConfigManager
from src.config.config import global_config
from src.common.logger import get_logger

logger = get_logger(__name__)


class IsolatedConfigContext:
    """隔离配置上下文，为IsolationContext提供配置访问能力"""

    def __init__(self, isolation_context: IsolationContext):
        self.isolation_context = isolation_context
        self.tenant_id = isolation_context.tenant_id
        self.agent_id = isolation_context.agent_id
        self.platform = isolation_context.platform

        # 获取隔离配置管理器
        self.config_manager = get_isolated_config_manager(self.tenant_id, self.agent_id)

    def get_config(self, category: str, key: str, default: Any = None) -> Any:
        """获取配置值（支持多级继承）"""
        return self.config_manager.get_config(category, key, default, self.platform)

    def get_bot_config(self, key: str, default: Any = None) -> Any:
        """获取bot配置"""
        return self.get_config("bot", key, default)

    def get_personality_config(self, key: str, default: Any = None) -> Any:
        """获取personality配置"""
        return self.get_config("personality", key, default)

    def get_chat_config(self, key: str, default: Any = None) -> Any:
        """获取chat配置"""
        return self.get_config("chat", key, default)

    def get_emoji_config(self, key: str, default: Any = None) -> Any:
        """获取emoji配置"""
        return self.get_config("emoji", key, default)

    def get_expression_config(self, key: str, default: Any = None) -> Any:
        """获取expression配置"""
        return self.get_config("expression", key, default)

    def get_memory_config(self, key: str, default: Any = None) -> Any:
        """获取memory配置"""
        return self.get_config("memory", key, default)

    def get_tool_config(self, key: str, default: Any = None) -> Any:
        """获取tool配置"""
        return self.get_config("tool", key, default)

    def get_voice_config(self, key: str, default: Any = None) -> Any:
        """获取voice配置"""
        return self.get_config("voice", key, default)

    def get_mood_config(self, key: str, default: Any = None) -> Any:
        """获取mood配置"""
        return self.get_config("mood", key, default)

    def get_maim_message_config(self, key: str, default: Any = None) -> Any:
        """获取maim_message配置"""
        return self.get_config("maim_message", key, default)

    def get_effective_config(self) -> Dict[str, Any]:
        """获取完整的有效配置"""
        return self.config_manager.get_effective_config(self.platform)

    def set_config(self, category: str, key: str, value: Any, level: str = "agent", description: str = None):
        """设置配置值"""
        self.config_manager.set_config(category, key, value, level, self.platform, description)

    def reload_config(self):
        """重新加载配置"""
        self.config_manager.reload_config()

    def subscribe_to_changes(self, config_key: str, callback):
        """订阅配置变更"""
        self.config_manager.subscribe_to_changes(config_key, callback)

    def unsubscribe_from_changes(self, config_key: str, callback):
        """取消订阅配置变更"""
        self.config_manager.unsubscribe_from_changes(config_key, callback)

    def get_config_history(self, category: str = None, key: str = None, limit: int = 100):
        """获取配置变更历史"""
        return self.config_manager.get_config_history(category, key, limit)


def create_isolated_config_context(isolation_context: IsolationContext) -> IsolatedConfigContext:
    """为隔离上下文创建配置上下文"""
    return IsolatedConfigContext(isolation_context)


# 扩展IsolationContext以支持配置管理
def extend_isolation_context_with_config():
    """扩展IsolationContext类，添加配置管理功能"""

    # 保存原始的__init__方法
    original_init = IsolationContext.__init__

    def new_init(self, tenant_id: str, agent_id: str, platform: str = None, chat_stream_id: str = None):
        """新的初始化方法，包含配置管理器"""
        # 调用原始初始化
        original_init(self, tenant_id, agent_id, platform, chat_stream_id)

        # 添加配置管理器到缓存
        def config_manager_factory():
            return get_isolated_config_manager(tenant_id, agent_id)

        self.get_cached_manager("config", config_manager_factory)

    # 替换__init__方法
    IsolationContext.__init__ = new_init

    # 添加配置相关方法
    def get_config_manager(self) -> IsolatedConfigManager:
        """获取隔离的配置管理器"""
        return self.get_cached_manager("config", lambda: get_isolated_config_manager(self.tenant_id, self.agent_id))

    def get_config_context(self) -> IsolatedConfigContext:
        """获取隔离配置上下文"""
        return IsolatedConfigContext(self)

    def get_config(self, category: str, key: str, default: Any = None) -> Any:
        """便捷方法：获取配置值"""
        config_context = self.get_config_context()
        return config_context.get_config(category, key, default)

    def get_effective_config(self) -> Dict[str, Any]:
        """便捷方法：获取完整有效配置"""
        config_context = self.get_config_context()
        return config_context.get_effective_config()

    def set_config(self, category: str, key: str, value: Any, level: str = "agent", description: str = None):
        """便捷方法：设置配置值"""
        config_context = self.get_config_context()
        config_context.set_config(category, key, value, level, self.platform, description)

    def reload_config(self):
        """便捷方法：重新加载配置"""
        config_manager = self.get_config_manager()
        config_manager.reload_config()

    # 将方法添加到类
    IsolationContext.get_config_manager = get_config_manager
    IsolationContext.get_config_context = get_config_context
    IsolationContext.get_config = get_config
    IsolationContext.get_effective_config = get_effective_config
    IsolationContext.set_config = set_config
    IsolationContext.reload_config = reload_config

    logger.info("Extended IsolationContext with config management capabilities")


# 配置访问装饰器
def with_isolated_config(func):
    """为函数注入隔离配置上下文的装饰器"""

    def wrapper(*args, **kwargs):
        # 检查第一个参数是否为IsolationContext
        if args and isinstance(args[0], IsolationContext):
            isolation_context = args[0]
            config_context = create_isolated_config_context(isolation_context)
            return func(config_context, *args[1:], **kwargs)
        else:
            raise ValueError("First argument must be an IsolationContext instance")

    return wrapper


async def async_with_isolated_config(func):
    """为异步函数注入隔离配置上下文的装饰器"""

    async def wrapper(*args, **kwargs):
        # 检查第一个参数是否为IsolationContext
        if args and isinstance(args[0], IsolationContext):
            isolation_context = args[0]
            config_context = create_isolated_config_context(isolation_context)
            return await func(config_context, *args[1:], **kwargs)
        else:
            raise ValueError("First argument must be an IsolationContext instance")

    return wrapper


# 向后兼容的配置访问函数
def get_isolated_config(isolation_context: IsolationContext, category: str, key: str, default: Any = None) -> Any:
    """向后兼容的配置访问函数"""
    config_context = create_isolated_config_context(isolation_context)
    return config_context.get_config(category, key, default)


def get_isolated_config_full(isolation_context: IsolationContext) -> Dict[str, Any]:
    """向后兼容的完整配置获取函数"""
    config_context = create_isolated_config_context(isolation_context)
    return config_context.get_effective_config()


# 全局配置访问增强
class GlobalConfigAccess:
    """全局配置访问类，提供隔离感知的配置访问"""

    @staticmethod
    def get_config(
        isolation_context: Optional[IsolationContext] = None, category: str = None, key: str = None, default: Any = None
    ) -> Any:
        """
        智能配置获取：
        - 如果提供了isolation_context，使用隔离配置
        - 如果没有isolation_context，使用全局配置
        """
        if isolation_context and category and key:
            # 使用隔离配置
            return get_isolated_config(isolation_context, category, key, default)
        elif category and key:
            # 使用全局配置
            try:
                if hasattr(global_config, category):
                    category_obj = getattr(global_config, category)
                    if hasattr(category_obj, key):
                        return getattr(category_obj, key)
            except Exception as e:
                logger.warning(f"Failed to get global config {category}.{key}: {e}")
            return default
        else:
            raise ValueError("Must provide either isolation_context or both category and key")

    @staticmethod
    def get_full_config(isolation_context: Optional[IsolationContext] = None) -> Dict[str, Any]:
        """
        智能完整配置获取：
        - 如果提供了isolation_context，获取隔离的完整配置
        - 如果没有isolation_context，获取全局配置
        """
        if isolation_context:
            return get_isolated_config_full(isolation_context)
        else:
            # 返回全局配置的字典表示
            try:
                return global_config.__dict__
            except Exception as e:
                logger.error(f"Failed to get global config dict: {e}")
                return {}


# 便捷函数
def get_config_for_context(isolation_context: IsolationContext) -> IsolatedConfigContext:
    """为指定隔离上下文获取配置上下文"""
    return create_isolated_config_context(isolation_context)


# 配置验证器
class ConfigValidator:
    """配置验证器"""

    @staticmethod
    def validate_isolation_config(isolation_context: IsolationContext) -> bool:
        """验证隔离配置的完整性"""
        try:
            config_context = create_isolated_config_context(isolation_context)

            # 检查必需的配置项
            required_configs = [
                ("bot", "platform"),
                ("bot", "nickname"),
                ("personality", "personality"),
                ("personality", "reply_style"),
            ]

            for category, key in required_configs:
                value = config_context.get_config(category, key)
                if value is None or (isinstance(value, str) and not value.strip()):
                    logger.warning(
                        f"Missing required config: {category}.{key} for {isolation_context.tenant_id}:{isolation_context.agent_id}"
                    )
                    return False

            return True

        except Exception as e:
            logger.error(f"Failed to validate isolation config: {e}")
            return False

    @staticmethod
    def validate_config_hierarchy(isolation_context: IsolationContext) -> Dict[str, Any]:
        """验证配置层级，返回配置来源信息"""
        try:
            config_context = create_isolated_config_context(isolation_context)
            config_manager = config_context.config_manager

            # 获取配置来源信息
            effective_config = config_manager.get_effective_config(isolation_context.platform)

            # 分析配置来源
            source_info = {}
            for category, configs in effective_config.items():
                source_info[category] = {}
                for key, _value in configs.items():
                    # 查询该配置的来源
                    source_value = config_manager._query_config_hierarchy(category, key, isolation_context.platform)
                    if source_value is not None:
                        # 确定来源级别（简化版本，避免循环导入）
                        if isolation_context.platform:
                            # 假设有平台特定配置
                            source_info[category][key] = "platform"
                        else:
                            source_info[category][key] = "agent"
                    else:
                        source_info[category][key] = "global"

            return source_info

        except Exception as e:
            logger.error(f"Failed to validate config hierarchy: {e}")
            return {}


# 初始化扩展
try:
    extend_isolation_context_with_config()
    logger.info("Successfully integrated config system with IsolationContext")
except Exception as e:
    logger.error(f"Failed to integrate config system with IsolationContext: {e}")
