"""Agent related helpers and registry exports."""

from .agent import Agent
from .loader import load_agents_from_directory
from .manager import (
    AgentManager,
    get_agent_manager,
    # 新增隔离化智能体管理器
    IsolatedAgentManager,
    get_isolated_agent_manager,
    get_isolated_agent_manager_manager,
    get_isolated_tenant_agent,
    list_isolated_tenant_agents,
    clear_isolated_agent_manager,
    get_isolated_manager_stats,
    initialize_isolated_agent_manager,
)
from .registry import (
    # 原有API - 保持向后兼容
    clear_agents,
    get_agent,
    get_registry,
    list_agents,
    register_agent,
    register_agents,
    resolve_agent_config,
    unregister_agent,
    # 新增隔离化智能体注册中心
    IsolatedAgentRegistry,
    get_isolated_registry_manager,
    get_isolated_registry,
    register_isolated_agent,
    get_isolated_agent,
    list_isolated_agents,
    resolve_isolated_agent_config,
    clear_isolated_registry,
    get_isolated_registry_stats,
)
from .isolated_agent_config import (
    # 智能体配置管理工具
    IsolatedAgentConfigManager,
    get_isolated_agent_config_manager,
    create_tenant_agent,
    get_tenant_agent,
    update_tenant_agent,
    delete_tenant_agent,
    list_tenant_agents,
    get_tenant_agent_config_stats,
)
from .isolated_agent_instance import (
    # 智能体实例管理
    IsolatedAgentInstance,
    IsolatedAgentInstanceManager,
    get_global_instance_manager,
    get_agent_instance,
    get_tenant_agent_instance,
    remove_agent_instance,
    clear_tenant_agent_instances,
    get_instance_management_stats,
)

__all__ = [
    # 原有API - 保持向后兼容
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
    # 隔离化智能体管理器
    "IsolatedAgentManager",
    "get_isolated_agent_manager",
    "get_isolated_agent_manager_manager",
    "get_isolated_tenant_agent",
    "list_isolated_tenant_agents",
    "clear_isolated_agent_manager",
    "get_isolated_manager_stats",
    "initialize_isolated_agent_manager",
    # 隔离化智能体注册中心
    "IsolatedAgentRegistry",
    "get_isolated_registry_manager",
    "get_isolated_registry",
    "register_isolated_agent",
    "get_isolated_agent",
    "list_isolated_agents",
    "resolve_isolated_agent_config",
    "clear_isolated_registry",
    "get_isolated_registry_stats",
    # 智能体配置管理
    "IsolatedAgentConfigManager",
    "get_isolated_agent_config_manager",
    "create_tenant_agent",
    "get_tenant_agent",
    "update_tenant_agent",
    "delete_tenant_agent",
    "list_tenant_agents",
    "get_tenant_agent_config_stats",
    # 智能体实例管理
    "IsolatedAgentInstance",
    "IsolatedAgentInstanceManager",
    "get_global_instance_manager",
    "get_agent_instance",
    "get_tenant_agent_instance",
    "remove_agent_instance",
    "clear_tenant_agent_instances",
    "get_instance_management_stats",
]
