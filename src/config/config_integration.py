"""
配置系统集成模块
将简化配置系统集成到现有系统中，替换原有的复杂配置系统
"""

from typing import Dict, Any, Optional
import threading
import logging

from .simplified_config_manager import SimplifiedConfigManager, get_simplified_config_manager as get_config_manager
from .simplified_config_wrapper import (
    SimplifiedUnifiedConfigWrapper,
    SimplifiedChatConfigWrapper,
)

logger = logging.getLogger(__name__)


class ConfigIntegration:
    """配置系统集成类，负责新旧配置系统的平滑过渡"""

    def __init__(self):
        self._simplified_managers: Dict[str, SimplifiedConfigManager] = {}
        self._lock = threading.RLock()
        self._integration_enabled = False

    def enable_integration(self):
        """启用配置系统集成"""
        with self._lock:
            self._integration_enabled = True
            logger.info("配置系统集成已启用")

    def disable_integration(self):
        """禁用配置系统集成"""
        with self._lock:
            self._integration_enabled = False
            logger.info("配置系统集成已禁用")

    def is_integration_enabled(self) -> bool:
        """检查集成是否启用"""
        return self._integration_enabled

    def get_config_manager(self, tenant_id: str, agent_id: str) -> SimplifiedConfigManager:
        """获取简化配置管理器实例"""
        key = f"{tenant_id}:{agent_id}"

        with self._lock:
            if key not in self._simplified_managers:
                self._simplified_managers[key] = SimplifiedConfigManager(tenant_id, agent_id)
                logger.info(f"创建简化配置管理器: {key}")

            return self._simplified_managers[key]

    def get_unified_config(self, tenant_id: str, agent_id: str) -> SimplifiedUnifiedConfigWrapper:
        """获取统一配置包装器"""
        if not self._integration_enabled:
            logger.warning("配置系统集成未启用，回退到原有系统")
            return self._get_legacy_config(tenant_id, agent_id)

        try:
            manager = self.get_config_manager(tenant_id, agent_id)
            return manager.get_unified_config()
        except Exception as e:
            logger.error(f"获取简化配置失败，回退到原有系统: {e}")
            return self._get_legacy_config(tenant_id, agent_id)

    def get_chat_config(self, tenant_id: str, agent_id: str) -> SimplifiedChatConfigWrapper:
        """获取聊天配置包装器"""
        if not self._integration_enabled:
            logger.warning("配置系统集成未启用，回退到原有系统")
            return self._get_legacy_chat_config(tenant_id, agent_id)

        try:
            manager = self.get_config_manager(tenant_id, agent_id)
            return manager.get_chat_config()
        except Exception as e:
            logger.error(f"获取简化聊天配置失败，回退到原有系统: {e}")
            return self._get_legacy_chat_config(tenant_id, agent_id)

    def _get_legacy_config(self, tenant_id: str, agent_id: str):
        """回退到原有的配置系统"""
        try:
            from .config_wrapper import UnifiedConfigWrapper

            return UnifiedConfigWrapper(tenant_id, agent_id)
        except ImportError:
            logger.error("无法导入原有配置系统")
            return None

    def _get_legacy_chat_config(self, tenant_id: str, agent_id: str):
        """回退到原有的聊天配置系统"""
        try:
            from .config_wrapper import ChatConfigWrapper

            return ChatConfigWrapper(tenant_id, agent_id)
        except ImportError:
            logger.error("无法导入原有聊天配置系统")
            return None

    def clear_cache(self, tenant_id: Optional[str] = None, agent_id: Optional[str] = None):
        """清理配置缓存"""
        with self._lock:
            if tenant_id and agent_id:
                key = f"{tenant_id}:{agent_id}"
                if key in self._simplified_managers:
                    del self._simplified_managers[key]
                    logger.info(f"清理配置缓存: {key}")
            else:
                self._simplified_managers.clear()
                logger.info("清理所有配置缓存")

    def get_integration_status(self) -> Dict[str, Any]:
        """获取集成状态信息"""
        with self._lock:
            return {
                "integration_enabled": self._integration_enabled,
                "cached_managers": len(self._simplified_managers),
                "manager_keys": list(self._simplified_managers.keys()),
            }


# 全局配置集成实例
_config_integration = ConfigIntegration()


def enable_config_integration():
    """启用配置系统集成"""
    _config_integration.enable_integration()


def disable_config_integration():
    """禁用配置系统集成"""
    _config_integration.disable_config_integration()


def get_config_manager(tenant_id: str, agent_id: str) -> SimplifiedConfigManager:
    """获取简化配置管理器实例"""
    return _config_integration.get_config_manager(tenant_id, agent_id)


def get_unified_config(tenant_id: str, agent_id: str) -> SimplifiedUnifiedConfigWrapper:
    """获取统一配置包装器"""
    return _config_integration.get_unified_config(tenant_id, agent_id)


def get_chat_config(tenant_id: str, agent_id: str) -> SimplifiedChatConfigWrapper:
    """获取聊天配置包装器"""
    return _config_integration.get_chat_config(tenant_id, agent_id)


def clear_config_cache(tenant_id: Optional[str] = None, agent_id: Optional[str] = None):
    """清理配置缓存"""
    _config_integration.clear_cache(tenant_id, agent_id)


def get_integration_status() -> Dict[str, Any]:
    """获取集成状态信息"""
    return _config_integration.get_integration_status()


# 向后兼容的函数
def create_simplified_config_manager(tenant_id: str, agent_id: str) -> SimplifiedConfigManager:
    """创建简化配置管理器（向后兼容）"""
    return get_config_manager(tenant_id, agent_id)


def create_simplified_unified_config(tenant_id: str, agent_id: str) -> SimplifiedUnifiedConfigWrapper:
    """创建简化统一配置（向后兼容）"""
    return get_unified_config(tenant_id, agent_id)


def create_simplified_chat_config(tenant_id: str, agent_id: str) -> SimplifiedChatConfigWrapper:
    """创建简化聊天配置（向后兼容）"""
    return get_chat_config(tenant_id, agent_id)


def is_integration_enabled() -> bool:
    """检查配置系统集成是否启用（模块级别函数）"""
    return _config_integration.is_integration_enabled()


# 自动启用配置系统集成
enable_config_integration()
