"""Agent registry and configuration resolution helpers."""

from __future__ import annotations

from threading import RLock
from typing import Dict, Iterable, List, Optional, Tuple

from src.agent.agent import Agent

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
