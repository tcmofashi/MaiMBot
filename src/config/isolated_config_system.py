"""
多租户隔离配置系统主入口
提供向后兼容的配置访问接口，同时支持新的多租户隔离功能
"""

import os
from typing import Dict, Any

from src.common.logger import get_logger
from src.config.config import global_config, model_config, Config, APIAdapterConfig
from src.config.isolated_config_manager import get_isolated_config_manager, IsolatedConfigManager
from src.config.isolated_config_integration import (
    IsolatedConfigContext,
    create_isolated_config_context,
    GlobalConfigAccess,
)
from src.config.isolated_config_tools import (
    ConfigMigrationTool,
    ConfigExportImportTool,
    ConfigValidationTool,
    ConfigManagementTool,
    migrate_global_to_tenant,
)
from src.isolation.isolation_context import IsolationContext

logger = get_logger(__name__)


class IsolatedConfigSystem:
    """多租户隔离配置系统主类"""

    def __init__(self):
        self._initialized = False
        self._default_tenant = "default"
        self._default_agent = "default"

    def initialize(self, default_tenant: str = "default", default_agent: str = "default"):
        """初始化配置系统"""
        try:
            self._default_tenant = default_tenant
            self._default_agent = default_agent
            self._initialized = True

            # 确保默认租户配置存在
            self._ensure_default_config()

            logger.info(
                f"Isolated config system initialized with default tenant: {default_tenant}, agent: {default_agent}"
            )

        except Exception as e:
            logger.error(f"Failed to initialize isolated config system: {e}")
            raise

    def _ensure_default_config(self):
        """确保默认租户配置存在"""
        try:
            config_manager = get_isolated_config_manager(self._default_tenant, self._default_agent)

            # 检查是否有配置，如果没有则从全局配置迁移
            sample_config = config_manager.get_config("bot", "nickname")
            if sample_config is None:
                logger.info("No default config found, migrating from global config")
                migrate_global_to_tenant(self._default_tenant, self._default_agent, overwrite=False)

        except Exception as e:
            logger.error(f"Failed to ensure default config: {e}")

    def get_config_manager(self, tenant_id: str = None, agent_id: str = None) -> IsolatedConfigManager:
        """获取配置管理器"""
        if not self._initialized:
            self.initialize()

        tenant_id = tenant_id or self._default_tenant
        agent_id = agent_id or self._default_agent

        return get_isolated_config_manager(tenant_id, agent_id)

    def get_config(
        self,
        category: str,
        key: str,
        default: Any = None,
        tenant_id: str = None,
        agent_id: str = None,
        platform: str = None,
        isolation_context: IsolationContext = None,
    ) -> Any:
        """
        智能配置获取：
        - 优先使用isolation_context
        - 其次使用tenant_id/agent_id
        - 最后使用全局配置
        """
        if isolation_context:
            # 使用隔离上下文
            config_context = create_isolated_config_context(isolation_context)
            return config_context.get_config(category, key, default)

        elif tenant_id and agent_id:
            # 使用指定的租户和智能体
            config_manager = self.get_config_manager(tenant_id, agent_id)
            return config_manager.get_config(category, key, default, platform)

        else:
            # 使用全局配置
            return GlobalConfigAccess.get_config(None, category, key, default)

    def get_full_config(
        self,
        tenant_id: str = None,
        agent_id: str = None,
        platform: str = None,
        isolation_context: IsolationContext = None,
    ) -> Dict[str, Any]:
        """获取完整配置"""
        if isolation_context:
            config_context = create_isolated_config_context(isolation_context)
            return config_context.get_effective_config()

        elif tenant_id and agent_id:
            config_manager = self.get_config_manager(tenant_id, agent_id)
            return config_manager.get_effective_config(platform)

        else:
            return GlobalConfigAccess.get_full_config()

    def set_config(
        self,
        category: str,
        key: str,
        value: Any,
        tenant_id: str = None,
        agent_id: str = None,
        level: str = "agent",
        platform: str = None,
        description: str = None,
    ):
        """设置配置值"""
        tenant_id = tenant_id or self._default_tenant
        agent_id = agent_id or self._default_agent

        config_manager = self.get_config_manager(tenant_id, agent_id)
        config_manager.set_config(category, key, value, level, platform, description)

    # 向后兼容的全局配置访问
    @property
    def global_config(self) -> Config:
        """获取全局配置对象（向后兼容）"""
        return global_config

    @property
    def global_model_config(self) -> APIAdapterConfig:
        """获取全局模型配置对象（向后兼容）"""
        return model_config

    # 配置管理工具
    def migrate_from_global(self, tenant_id: str, agent_id: str, overwrite: bool = False):
        """从全局配置迁移"""
        return ConfigMigrationTool.migrate_from_global_config(tenant_id, agent_id, overwrite)

    def migrate_from_file(
        self,
        tenant_id: str,
        agent_id: str,
        config_file: str,
        level: str = "agent",
        platform: str = None,
        overwrite: bool = False,
    ):
        """从文件迁移配置"""
        return ConfigMigrationTool.migrate_from_file(tenant_id, agent_id, config_file, level, platform, overwrite)

    def export_configs(
        self, tenant_id: str, agent_id: str = None, platform: str = None, categories=None, include_history: bool = False
    ):
        """导出配置"""
        return ConfigExportImportTool.export_configs(tenant_id, agent_id, platform, categories, include_history)

    def import_configs(
        self, export_data: Dict[str, Any], target_tenant_id: str, overwrite: bool = False, create_agents: bool = True
    ):
        """导入配置"""
        return ConfigExportImportTool.import_configs(export_data, target_tenant_id, overwrite, create_agents)

    def validate_configs(self, tenant_id: str, agent_id: str = None):
        """验证配置"""
        return ConfigValidationTool.validate_tenant_config(tenant_id, agent_id)

    def check_consistency(self, tenant_id: str):
        """检查配置一致性"""
        return ConfigValidationTool.check_config_consistency(tenant_id)

    def cleanup_configs(self, tenant_id: str = None, days: int = 30):
        """清理过期配置"""
        return ConfigManagementTool.cleanup_expired_configs(tenant_id, days)

    def get_statistics(self, tenant_id: str = None):
        """获取配置统计"""
        return ConfigManagementTool.get_config_statistics(tenant_id)

    def reset_agent_config(self, tenant_id: str, agent_id: str, confirm: bool = False):
        """重置智能体配置"""
        return ConfigManagementTool.reset_agent_config(tenant_id, agent_id, confirm)


# 全局配置系统实例
_isolated_config_system = IsolatedConfigSystem()


def get_isolated_config_system() -> IsolatedConfigSystem:
    """获取全局隔离配置系统实例"""
    return _isolated_config_system


def initialize_isolated_config_system(default_tenant: str = "default", default_agent: str = "default"):
    """初始化隔离配置系统"""
    return _isolated_config_system.initialize(default_tenant, default_agent)


# 向后兼容的便捷函数
def get_isolated_config(
    category: str,
    key: str,
    default: Any = None,
    tenant_id: str = None,
    agent_id: str = None,
    platform: str = None,
    isolation_context: IsolationContext = None,
) -> Any:
    """便捷函数：获取隔离配置"""
    return _isolated_config_system.get_config(category, key, default, tenant_id, agent_id, platform, isolation_context)


def set_isolated_config(
    category: str,
    key: str,
    value: Any,
    tenant_id: str = None,
    agent_id: str = None,
    level: str = "agent",
    platform: str = None,
    description: str = None,
):
    """便捷函数：设置隔离配置"""
    return _isolated_config_system.set_config(category, key, value, tenant_id, agent_id, level, platform, description)


def get_isolated_full_config(
    tenant_id: str = None, agent_id: str = None, platform: str = None, isolation_context: IsolationContext = None
) -> Dict[str, Any]:
    """便捷函数：获取完整隔离配置"""
    return _isolated_config_system.get_full_config(tenant_id, agent_id, platform, isolation_context)


# 配置系统装饰器
def with_isolated_config(tenant_id: str = None, agent_id: str = None, platform: str = None):
    """为函数注入隔离配置的装饰器"""

    def decorator(func):
        def wrapper(*args, **kwargs):
            # 创建配置管理器并注入到函数参数中
            config_manager = _isolated_config_system.get_config_manager(tenant_id, agent_id)
            return func(config_manager, *args, **kwargs)

        return wrapper

    return decorator


async def async_with_isolated_config(tenant_id: str = None, agent_id: str = None, platform: str = None):
    """为异步函数注入隔离配置的装饰器"""

    def decorator(func):
        async def wrapper(*args, **kwargs):
            # 创建配置管理器并注入到函数参数中
            config_manager = _isolated_config_system.get_config_manager(tenant_id, agent_id)
            return await func(config_manager, *args, **kwargs)

        return wrapper

    return decorator


# 配置上下文管理器
class IsolatedConfigContext:
    """隔离配置上下文管理器"""

    def __init__(self, tenant_id: str, agent_id: str, platform: str = None):
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.platform = platform
        self.config_manager = None

    def __enter__(self) -> IsolatedConfigManager:
        self.config_manager = _isolated_config_system.get_config_manager(self.tenant_id, self.agent_id)
        return self.config_manager

    def __exit__(self, exc_type, exc_val, exc_tb):
        # 清理资源（如果需要）
        if self.config_manager:
            pass  # 配置管理器有内置的缓存管理


def isolated_config_context(tenant_id: str, agent_id: str, platform: str = None):
    """创建隔离配置上下文"""
    return IsolatedConfigContext(tenant_id, agent_id, platform)


# 初始化配置系统
try:
    # 从环境变量获取默认租户和智能体信息
    default_tenant = os.getenv("DEFAULT_TENANT", "default")
    default_agent = os.getenv("DEFAULT_AGENT", "default")

    # 初始化配置系统
    initialize_isolated_config_system(default_tenant, default_agent)

    logger.info(f"Multi-tenant isolated config system initialized with tenant={default_tenant}, agent={default_agent}")

except Exception as e:
    logger.error(f"Failed to initialize multi-tenant config system: {e}")
    # 继续运行，但记录错误
