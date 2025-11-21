"""Agent registry and configuration resolution helpers."""

from __future__ import annotations

from threading import RLock
from typing import Dict, Iterable, List, Optional, Tuple
import threading
import weakref

from src.agent.agent import Agent
from src.isolation.isolation_context import create_isolation_context

if False:  # pragma: no cover - for type checkers without importing at runtime
    from src.config.config import Config


class AgentRegistry:
    """In-memory registry that stores Agent definitions and cached configs."""

    def __init__(self) -> None:
        self._agents: Dict[str, Agent] = {}
        self._config_cache: Dict[Tuple[int, str], "Config"] = {}
        self._lock = RLock()

    def register(self, agent: Agent, *, overwrite: bool = True) -> None:
        """Register or update an Agent definition."""

        with self._lock:
            if not overwrite and agent.agent_id in self._agents:
                return
            self._agents[agent.agent_id] = agent
            self._config_cache.clear()

    def register_many(self, agents: Iterable[Agent], *, overwrite: bool = True) -> None:
        """Register multiple agents at once."""

        for agent in agents:
            self.register(agent, overwrite=overwrite)

    def get(self, agent_id: str) -> Optional[Agent]:
        """Retrieve an Agent by id."""

        with self._lock:
            return self._agents.get(agent_id)

    def unregister(self, agent_id: str) -> None:
        """Remove an Agent from the registry."""

        with self._lock:
            if agent_id in self._agents:
                self._agents.pop(agent_id)
                self._config_cache.clear()

    def list_agents(self) -> List[Agent]:
        """Return all registered agents."""

        with self._lock:
            return list(self._agents.values())

    def clear(self) -> None:
        """Clear the registry and cached configs."""

        with self._lock:
            self._agents.clear()
            self._config_cache.clear()

    def resolve_config(self, agent_id: str, base_config: "Config") -> "Config":
        """Return the merged Config for the given agent."""

        cache_key = (id(base_config), agent_id)

        with self._lock:
            cached = self._config_cache.get(cache_key)
            if cached is not None:
                return cached

            agent = self._agents.get(agent_id)

        if not agent:
            # 缓存原始配置以避免重复查找
            with self._lock:
                self._config_cache[cache_key] = base_config
            return base_config

        merged = agent.build_config(base_config)

        with self._lock:
            self._config_cache[cache_key] = merged

        return merged


_registry = AgentRegistry()


def get_registry() -> AgentRegistry:
    """Return the global Agent registry instance."""

    return _registry


def register_agent(agent: Agent, *, overwrite: bool = True) -> None:
    get_registry().register(agent, overwrite=overwrite)


def register_agents(agents: Iterable[Agent], *, overwrite: bool = True) -> None:
    get_registry().register_many(agents, overwrite=overwrite)


def unregister_agent(agent_id: str) -> None:
    get_registry().unregister(agent_id)


def get_agent(agent_id: str) -> Optional[Agent]:
    return get_registry().get(agent_id)


def list_agents() -> List[Agent]:
    return get_registry().list_agents()


def clear_agents() -> None:
    get_registry().clear()


def resolve_agent_config(agent_id: str, base_config: "Config") -> "Config":
    """Shortcut helper to merge config for a specific agent."""

    return get_registry().resolve_config(agent_id, base_config)


# ----------------------------------------------------------------------
# 多租户隔离化智能体注册中心
# ----------------------------------------------------------------------


class IsolatedAgentRegistry:
    """支持T+A隔离的智能体注册中心。

    每个租户拥有独立的智能体注册表，确保不同租户间的智能体配置完全隔离。
    """

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self._agents: Dict[str, Agent] = {}
        self._config_cache: Dict[Tuple[int, str], "Config"] = {}
        self._lock = RLock()

        # 集成隔离上下文
        self.isolation_context = create_isolation_context(tenant_id, "system")

    def register(self, agent: Agent, *, overwrite: bool = True) -> None:
        """注册或更新一个智能体定义（带租户隔离验证）"""

        # 验证智能体是否属于当前租户
        if not self._validate_agent_access(agent):
            raise ValueError(f"Agent '{agent.agent_id}' 不属于租户 '{self.tenant_id}'")

        with self._lock:
            if not overwrite and agent.agent_id in self._agents:
                return
            self._agents[agent.agent_id] = agent
            self._config_cache.clear()

    def register_many(self, agents: Iterable[Agent], *, overwrite: bool = True) -> None:
        """批量注册多个智能体"""

        for agent in agents:
            self.register(agent, overwrite=overwrite)

    def get(self, agent_id: str) -> Optional[Agent]:
        """获取智能体定义（租户隔离）"""

        with self._lock:
            return self._agents.get(agent_id)

    def unregister(self, agent_id: str) -> None:
        """移除智能体定义"""

        with self._lock:
            if agent_id in self._agents:
                self._agents.pop(agent_id)
                self._config_cache.clear()

    def list_agents(self) -> List[Agent]:
        """返回当前租户的所有智能体"""

        with self._lock:
            return list(self._agents.values())

    def clear(self) -> None:
        """清理注册表和配置缓存"""

        with self._lock:
            self._agents.clear()
            self._config_cache.clear()

    def resolve_config(self, agent_id: str, base_config: "Config") -> "Config":
        """返回合并后的智能体配置（租户隔离）"""

        cache_key = (id(base_config), agent_id)

        with self._lock:
            cached = self._config_cache.get(cache_key)
            if cached is not None:
                return cached

            agent = self._agents.get(agent_id)

        if not agent:
            # 缓存原始配置以避免重复查找
            with self._lock:
                self._config_cache[cache_key] = base_config
            return base_config

        merged = agent.build_config(base_config)

        with self._lock:
            self._config_cache[cache_key] = merged

        return merged

    def _validate_agent_access(self, agent: Agent) -> bool:
        """验证智能体访问权限"""

        # 检查智能体的租户ID是否与当前租户匹配
        # 对于 'default' 租户，允许所有智能体
        if self.tenant_id == "default":
            return True

        # 对于其他租户，检查智能体的租户ID
        return getattr(agent, "tenant_id", None) == self.tenant_id

    def get_tenant_info(self) -> Dict[str, any]:
        """获取租户信息"""

        return {
            "tenant_id": self.tenant_id,
            "agent_count": len(self._agents),
            "config_cache_size": len(self._config_cache),
            "isolation_scope": str(self.isolation_context.scope),
        }

    def get_agent_count(self) -> int:
        """获取智能体数量"""

        with self._lock:
            return len(self._agents)

    def has_agent(self, agent_id: str) -> bool:
        """检查智能体是否存在"""

        with self._lock:
            return agent_id in self._agents


class IsolatedAgentRegistryManager:
    """隔离化智能体注册中心管理器，管理多个租户的注册中心实例"""

    def __init__(self):
        self._registries: Dict[str, IsolatedAgentRegistry] = {}
        self._lock = threading.RLock()
        self._weak_refs: Dict[str, weakref.ref] = {}

    def get_registry(self, tenant_id: str) -> IsolatedAgentRegistry:
        """获取租户的注册中心实例"""

        with self._lock:
            # 检查弱引用是否仍然有效
            if tenant_id in self._weak_refs:
                registry_ref = self._weak_refs[tenant_id]
                registry = registry_ref()
                if registry is not None:
                    return registry

            # 创建新的注册中心实例
            registry = IsolatedAgentRegistry(tenant_id)

            # 使用弱引用存储，避免内存泄漏
            self._registries[tenant_id] = registry
            self._weak_refs[tenant_id] = weakref.ref(registry)

            return registry

    def list_tenant_registries(self) -> List[str]:
        """列出所有租户ID"""

        with self._lock:
            return list(self._registries.keys())

    def clear_tenant_registry(self, tenant_id: str) -> bool:
        """清理指定租户的注册中心"""

        with self._lock:
            if tenant_id in self._registries:
                registry = self._registries.get(tenant_id)
                if registry:
                    registry.clear()
                del self._registries[tenant_id]
                if tenant_id in self._weak_refs:
                    del self._weak_refs[tenant_id]
                return True
            return False

    def clear_all_registries(self):
        """清理所有注册中心"""

        with self._lock:
            for registry in self._registries.values():
                if registry:
                    registry.clear()
            self._registries.clear()
            self._weak_refs.clear()

    def cleanup_expired_registries(self):
        """清理已过期的注册中心引用"""

        with self._lock:
            expired_tenants = []
            for tenant_id, ref in self._weak_refs.items():
                if ref() is None:
                    expired_tenants.append(tenant_id)

            for tenant_id in expired_tenants:
                if tenant_id in self._registries:
                    del self._registries[tenant_id]
                del self._weak_refs[tenant_id]

    def get_registry_stats(self) -> Dict[str, any]:
        """获取注册中心统计信息"""

        self.cleanup_expired_registries()

        stats = {"total_tenants": len(self._registries), "registries": {}}

        with self._lock:
            for tenant_id, registry in self._registries.items():
                if registry:
                    stats["registries"][tenant_id] = registry.get_tenant_info()

        return stats


# 全局隔离化智能体注册中心管理器
_isolated_registry_manager = IsolatedAgentRegistryManager()


def get_isolated_registry_manager() -> IsolatedAgentRegistryManager:
    """获取全局隔离化智能体注册中心管理器"""
    return _isolated_registry_manager


def get_isolated_registry(tenant_id: str) -> IsolatedAgentRegistry:
    """获取指定租户的隔离化智能体注册中心"""
    return _isolated_registry_manager.get_registry(tenant_id)


def register_isolated_agent(agent: Agent, tenant_id: str, *, overwrite: bool = True) -> None:
    """向指定租户注册智能体的便捷函数"""
    registry = get_isolated_registry(tenant_id)
    registry.register(agent, overwrite=overwrite)


def get_isolated_agent(agent_id: str, tenant_id: str) -> Optional[Agent]:
    """从指定租户获取智能体的便捷函数"""
    registry = get_isolated_registry(tenant_id)
    return registry.get(agent_id)


def list_isolated_agents(tenant_id: str) -> List[Agent]:
    """列出指定租户所有智能体的便捷函数"""
    registry = get_isolated_registry(tenant_id)
    return registry.list_agents()


def resolve_isolated_agent_config(agent_id: str, tenant_id: str, base_config: "Config") -> "Config":
    """解析指定租户智能体配置的便捷函数"""
    registry = get_isolated_registry(tenant_id)
    return registry.resolve_config(agent_id, base_config)


def clear_isolated_registry(tenant_id: str) -> bool:
    """清理指定租户注册中心的便捷函数"""
    return _isolated_registry_manager.clear_tenant_registry(tenant_id)


def get_isolated_registry_stats() -> Dict[str, any]:
    """获取隔离化注册中心统计信息的便捷函数"""
    return _isolated_registry_manager.get_registry_stats()
