"""
Agent配置加载器
仅从数据库加载Agent配置并与基础配置融合
"""

from typing import Dict, Any, Optional

from .agent_config import AgentConfig
from .db_agent_config_loader import load_agent_config_from_database, get_db_agent_config_loader
from src.common.logger import get_logger


class AgentConfigLoader:
    """Agent配置加载器 - 仅支持数据库"""

    def __init__(self):
        self.logger = get_logger("agent_config_loader")
        self._db_loader = get_db_agent_config_loader()

    def is_available(self) -> bool:
        """检查数据库模块是否可用"""
        return self._db_loader.is_available()

    async def load_agent_config(self, agent_id: str) -> Optional[AgentConfig]:
        """
        从数据库加载Agent配置

        Args:
            agent_id: Agent ID

        Returns:
            AgentConfig对象或None
        """
        if not self._db_loader.is_available():
            self.logger.error("数据库模块不可用，无法加载Agent配置")
            return None

        try:
            agent_config = await load_agent_config_from_database(agent_id)
            if agent_config:
                self.logger.info(f"成功从数据库加载Agent配置: {agent_id}")
            return agent_config

        except Exception as e:
            self.logger.error(f"从数据库加载Agent配置失败: {e}")
            return None

    async def create_merged_global_config(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        创建融合后的全局配置

        Args:
            agent_id: Agent ID

        Returns:
            融合后的配置字典或None
        """
        agent_config = await self.load_agent_config(agent_id)
        if not agent_config:
            self.logger.error(f"无法从数据库加载Agent配置: {agent_id}")
            return None

        try:
            # 创建融合配置
            from .config_merger import create_agent_config

            merged_config = create_agent_config(agent_config)
            self.logger.info(f"成功创建Agent {agent_id} 的融合配置")
            return merged_config

        except Exception as e:
            self.logger.error(f"创建融合配置失败: {e}")
            return None

    async def reload_agent_config(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        重新加载Agent配置

        Args:
            agent_id: Agent ID

        Returns:
            融合后的配置字典或None
        """
        self.logger.info(f"重新加载Agent配置: {agent_id}")

        return await self.create_merged_global_config(agent_id)

    async def get_available_agents(self) -> Optional[Dict[str, Any]]:
        """获取可用的Agent列表"""
        if not self._db_loader.is_available():
            self.logger.error("数据库模块不可用")
            return None

        try:
            agent_ids = await self._db_loader.get_available_agents_from_database()
            return {"agents": [{"agent_id": aid} for aid in agent_ids]}

        except Exception as e:
            self.logger.error(f"获取Agent列表失败: {e}")
            return None

    def clear_all_cache(self) -> None:
        """清除所有缓存"""
        # 数据库模式不需要缓存
        self.logger.info("数据库模式无需清除缓存")


# 全局Agent配置加载器实例
_agent_config_loader = None


def get_agent_config_loader() -> AgentConfigLoader:
    """获取Agent配置加载器实例"""
    global _agent_config_loader
    if _agent_config_loader is None:
        _agent_config_loader = AgentConfigLoader()
    return _agent_config_loader


# 便捷函数
async def load_agent_config(agent_id: str) -> Optional[AgentConfig]:
    """从数据库加载Agent配置的便捷函数"""
    loader = get_agent_config_loader()
    return await loader.load_agent_config(agent_id)


async def create_merged_agent_config(agent_id: str) -> Optional[Dict[str, Any]]:
    """从数据库创建融合Agent配置的便捷函数"""
    loader = get_agent_config_loader()
    return await loader.create_merged_global_config(agent_id)


async def reload_agent_config(agent_id: str) -> Optional[Dict[str, Any]]:
    """重新加载Agent配置的便捷函数"""
    loader = get_agent_config_loader()
    return await loader.reload_agent_config(agent_id)


async def get_available_agents() -> Optional[Dict[str, Any]]:
    """获取可用Agent列表的便捷函数"""
    loader = get_agent_config_loader()
    return await loader.get_available_agents()
