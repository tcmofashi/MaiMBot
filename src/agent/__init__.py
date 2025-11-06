"""Agent related helpers and registry exports."""

from .agent import Agent
from .loader import load_agents_from_directory
from .manager import AgentManager, get_agent_manager
from .registry import (
    clear_agents,
    get_agent,
    get_registry,
    list_agents,
    register_agent,
    register_agents,
    resolve_agent_config,
    unregister_agent,
)

__all__ = [
    "Agent",
    "clear_agents",
    "get_agent",
    "get_registry",
    "list_agents",
    "register_agent",
    "register_agents",
    "resolve_agent_config",
    "unregister_agent",
    "load_agents_from_directory",
    "AgentManager",
    "get_agent_manager",
]
