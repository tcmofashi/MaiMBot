"""
智能体配置管理工具
支持T+A维度的隔离化智能体配置管理
"""

from typing import Dict, Any, Optional, List
from dataclasses import asdict

from src.agent.agent import Agent
from src.agent.registry import get_isolated_registry
from src.agent.manager import get_isolated_agent_manager
from src.config.config import Config
from src.config.official_configs import PersonalityConfig
from src.isolation.isolation_context import create_isolation_context


class IsolatedAgentConfigManager:
    """隔离化智能体配置管理器"""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.isolation_context = create_isolation_context(tenant_id, "system")

        # 获取隔离化的注册中心和管理器
        self.registry = get_isolated_registry(tenant_id)
        self.agent_manager = get_isolated_agent_manager(tenant_id)

    def create_agent_config(
        self,
        agent_id: str,
        name: str,
        persona_config: Optional[Dict[str, Any]] = None,
        bot_overrides: Optional[Dict[str, Any]] = None,
        config_overrides: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        description: str = "",
    ) -> Agent:
        """创建智能体配置"""

        # 使用默认人格配置
        if persona_config is None:
            persona_config = {}

        persona = PersonalityConfig.from_dict(persona_config)

        # 创建智能体实例，添加租户前缀
        full_agent_id = f"{self.tenant_id}:{agent_id}" if not agent_id.startswith(f"{self.tenant_id}:") else agent_id

        agent = Agent(
            agent_id=full_agent_id,
            name=name,
            persona=persona,
            bot_overrides=bot_overrides or {},
            config_overrides=config_overrides or {},
            tags=tags or [],
            description=description,
        )

        # 注册到租户注册中心
        self.registry.register(agent)

        # 持久化到数据库
        self.agent_manager.upsert_agent(agent)

        return agent

    def get_agent_config(self, agent_id: str) -> Optional[Agent]:
        """获取智能体配置"""
        full_agent_id = f"{self.tenant_id}:{agent_id}" if not agent_id.startswith(f"{self.tenant_id}:") else agent_id
        return self.registry.get(full_agent_id)

    def update_agent_config(
        self,
        agent_id: str,
        name: Optional[str] = None,
        persona_config: Optional[Dict[str, Any]] = None,
        bot_overrides: Optional[Dict[str, Any]] = None,
        config_overrides: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        description: Optional[str] = None,
    ) -> Optional[Agent]:
        """更新智能体配置"""

        full_agent_id = f"{self.tenant_id}:{agent_id}" if not agent_id.startswith(f"{self.tenant_id}:") else agent_id
        agent = self.registry.get(full_agent_id)

        if not agent:
            return None

        # 更新各字段
        if name is not None:
            agent.name = name

        if persona_config is not None:
            agent.persona = PersonalityConfig.from_dict(persona_config)

        if bot_overrides is not None:
            agent.bot_overrides = bot_overrides

        if config_overrides is not None:
            agent.config_overrides = config_overrides

        if tags is not None:
            agent.tags = tags

        if description is not None:
            agent.description = description

        # 重新注册和持久化
        self.registry.register(agent, overwrite=True)
        self.agent_manager.upsert_agent(agent, register=False)

        return agent

    def delete_agent_config(self, agent_id: str) -> bool:
        """删除智能体配置"""
        full_agent_id = f"{self.tenant_id}:{agent_id}" if not agent_id.startswith(f"{self.tenant_id}:") else agent_id

        # 从注册中心移除
        self.registry.unregister(full_agent_id)

        # 从数据库删除
        return self.agent_manager.delete_agent(full_agent_id)

    def list_agent_configs(self) -> List[Agent]:
        """列出所有智能体配置"""
        return self.registry.list_agents()

    def get_effective_config(self, agent_id: str, base_config: Config) -> Config:
        """获取智能体的有效配置（包含所有覆盖项）"""
        full_agent_id = f"{self.tenant_id}:{agent_id}" if not agent_id.startswith(f"{self.tenant_id}:") else agent_id
        return self.registry.resolve_config(full_agent_id, base_config)

    def export_agent_config(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """导出智能体配置为字典"""
        agent = self.get_agent_config(agent_id)
        if not agent:
            return None

        return {
            "agent_id": agent.agent_id,
            "name": agent.name,
            "description": agent.description,
            "tags": list(agent.tags),
            "persona": asdict(agent.persona),
            "bot_overrides": agent.bot_overrides,
            "config_overrides": agent.config_overrides,
        }

    def import_agent_config(self, config_dict: Dict[str, Any]) -> Agent:
        """从字典导入智能体配置"""
        return self.create_agent_config(
            agent_id=config_dict["agent_id"],
            name=config_dict["name"],
            persona_config=config_dict.get("persona", {}),
            bot_overrides=config_dict.get("bot_overrides", {}),
            config_overrides=config_dict.get("config_overrides", {}),
            tags=config_dict.get("tags", []),
            description=config_dict.get("description", ""),
        )

    def validate_agent_config(self, config_dict: Dict[str, Any]) -> List[str]:
        """验证智能体配置"""
        errors = []

        # 必需字段检查
        if not config_dict.get("agent_id"):
            errors.append("agent_id 是必需的")

        if not config_dict.get("name"):
            errors.append("name 是必需的")

        # 人格配置验证
        persona = config_dict.get("persona", {})
        if not isinstance(persona, dict):
            errors.append("persona 必须是字典类型")

        # 覆盖配置验证
        for override_field in ["bot_overrides", "config_overrides"]:
            override_value = config_dict.get(override_field, {})
            if override_value is not None and not isinstance(override_value, dict):
                errors.append(f"{override_field} 必须是字典类型或 null")

        # 标签验证
        tags = config_dict.get("tags", [])
        if tags is not None and not isinstance(tags, list):
            errors.append("tags 必须是列表类型或 null")

        return errors

    def clone_agent_config(self, source_agent_id: str, new_agent_id: str, new_name: str) -> Optional[Agent]:
        """克隆智能体配置"""
        source_config = self.export_agent_config(source_agent_id)
        if not source_config:
            return None

        # 清理不需要克隆的字段
        source_config.pop("agent_id", None)
        source_config.pop("name", None)

        return self.create_agent_config(agent_id=new_agent_id, name=new_name, **source_config)

    def get_tenant_config_stats(self) -> Dict[str, Any]:
        """获取租户配置统计信息"""
        agents = self.list_agent_configs()

        stats = {
            "tenant_id": self.tenant_id,
            "total_agents": len(agents),
            "agents_with_custom_personas": 0,
            "agents_with_bot_overrides": 0,
            "agents_with_config_overrides": 0,
            "agents_by_tags": {},
            "isolation_scope": str(self.isolation_context.scope),
        }

        for agent in agents:
            # 统计自定义人格
            if hasattr(agent, "persona") and agent.persona:
                stats["agents_with_custom_personas"] += 1

            # 统计覆盖配置
            if agent.bot_overrides:
                stats["agents_with_bot_overrides"] += 1

            if agent.config_overrides:
                stats["agents_with_config_overrides"] += 1

            # 统计标签
            for tag in agent.tags:
                stats["agents_by_tags"][tag] = stats["agents_by_tags"].get(tag, 0) + 1

        return stats


# 便捷函数
def get_isolated_agent_config_manager(tenant_id: str) -> IsolatedAgentConfigManager:
    """获取隔离化智能体配置管理器的便捷函数"""
    return IsolatedAgentConfigManager(tenant_id)


def create_tenant_agent(
    tenant_id: str, agent_id: str, name: str, persona_config: Optional[Dict[str, Any]] = None, **kwargs
) -> Agent:
    """创建租户智能体的便捷函数"""
    manager = get_isolated_agent_config_manager(tenant_id)
    return manager.create_agent_config(agent_id, name, persona_config, **kwargs)


def get_tenant_agent(tenant_id: str, agent_id: str) -> Optional[Agent]:
    """获取租户智能体的便捷函数"""
    manager = get_isolated_agent_config_manager(tenant_id)
    return manager.get_agent_config(agent_id)


def update_tenant_agent(tenant_id: str, agent_id: str, **kwargs) -> Optional[Agent]:
    """更新租户智能体的便捷函数"""
    manager = get_isolated_agent_config_manager(tenant_id)
    return manager.update_agent_config(agent_id, **kwargs)


def delete_tenant_agent(tenant_id: str, agent_id: str) -> bool:
    """删除租户智能体的便捷函数"""
    manager = get_isolated_agent_config_manager(tenant_id)
    return manager.delete_agent_config(agent_id)


def list_tenant_agents(tenant_id: str) -> List[Agent]:
    """列出租户所有智能体的便捷函数"""
    manager = get_isolated_agent_config_manager(tenant_id)
    return manager.list_agent_configs()


def get_tenant_agent_config_stats(tenant_id: str) -> Dict[str, Any]:
    """获取租户智能体配置统计信息的便捷函数"""
    manager = get_isolated_agent_config_manager(tenant_id)
    return manager.get_tenant_config_stats()
