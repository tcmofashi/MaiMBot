"""
多租户消息系统便捷API接口
提供简单易用的函数来处理多租户消息
"""

from typing import Dict, Any, Optional, List, Callable, Union
from dataclasses import dataclass
from datetime import datetime

from .multi_tenant_adapter import TenantMessageConfig, MessagePriority, get_multi_tenant_adapter
from .tenant_message_server import get_tenant_message_server
from maim_message.tenant_client import TenantMessageClient, ClientConfig
from .message_router import RouteRule, RouteAction, RouteTarget, get_message_router
from ..isolation import IsolationContext, create_isolation_context
from ..chat.message_receive.message import MessageSending
from ..common.logger import get_logger

logger = get_logger("multi_tenant_api")


@dataclass
class TenantSystemConfig:
    """租户系统配置"""

    enable_server: bool = False
    server_host: str = "localhost"
    server_port: int = 8091
    enable_router: bool = True
    router_workers: int = 3
    enable_adapter: bool = True
    auto_start: bool = True


# 全局系统状态
_system_config: Optional[TenantSystemConfig] = None
_server_clients: Dict[str, TenantMessageClient] = {}  # tenant_id -> client


async def initialize_multi_tenant_system(config: TenantSystemConfig) -> bool:
    """初始化多租户系统"""
    global _system_config

    try:
        _system_config = config
        logger.info("开始初始化多租户系统")

        # 初始化适配器
        if config.enable_adapter:
            adapter = get_multi_tenant_adapter()
            await adapter.initialize()
            logger.info("多租户适配器初始化完成")

        # 初始化路由器
        if config.enable_router:
            router = get_message_router()
            await router.start_processors(config.router_workers)
            logger.info(f"消息路由器启动完成，工作线程数: {config.router_workers}")

        # 初始化服务器
        if config.enable_server:
            server = get_tenant_message_server()
            await server.start()
            logger.info(f"租户消息服务器启动完成: {config.server_host}:{config.server_port}")

        logger.info("多租户系统初始化完成")
        return True

    except Exception as e:
        logger.error(f"初始化多租户系统失败: {e}")
        return False


async def shutdown_multi_tenant_system():
    """关闭多租户系统"""
    global _system_config, _server_clients

    try:
        logger.info("开始关闭多租户系统")

        # 关闭所有客户端连接
        for client in _server_clients.values():
            await client.disconnect()
        _server_clients.clear()

        # 关闭服务器
        if _system_config and _system_config.enable_server:
            server = get_tenant_message_server()
            await server.stop()

        # 关闭路由器
        if _system_config and _system_config.enable_router:
            router = get_message_router()
            await router.stop_processors()

        # 清理适配器
        if _system_config and _system_config.enable_adapter:
            adapter = get_multi_tenant_adapter()
            # 清理所有租户资源
            for tenant_id in list(adapter.tenant_configs.keys()):
                await adapter.cleanup_tenant(tenant_id)

        logger.info("多租户系统关闭完成")

    except Exception as e:
        logger.error(f"关闭多租户系统失败: {e}")


# 租户管理API
async def register_tenant(
    tenant_id: str,
    server_url: str,
    api_key: Optional[str] = None,
    platforms: Optional[List[str]] = None,
    allowed_agents: Optional[List[str]] = None,
    **kwargs,
) -> bool:
    """注册租户"""
    try:
        config = TenantMessageConfig(
            tenant_id=tenant_id,
            server_url=server_url,
            api_key=api_key,
            platforms=platforms or [],
            allowed_agents=set(allowed_agents or ["default"]),
            **kwargs,
        )

        adapter = get_multi_tenant_adapter()
        adapter.register_tenant(config)

        # 如果启用了服务器，也注册到服务器
        if _system_config and _system_config.enable_server:
            server = get_tenant_message_server()
            server.register_tenant(config, api_key or f"default_key_{tenant_id}")

        # 如果需要，创建客户端连接
        if server_url and server_url.startswith("ws://"):
            config = ClientConfig(
                tenant_id=tenant_id,
                agent_id="default",  # 使用默认agent_id
                platform="default",  # 使用默认platform
                server_url=server_url,
                api_key=api_key
            )
            client = TenantMessageClient(config)
            await client.connect()
            _server_clients[tenant_id] = client

        logger.info(f"注册租户成功: {tenant_id}")
        return True

    except Exception as e:
        logger.error(f"注册租户失败 {tenant_id}: {e}")
        return False


async def unregister_tenant(tenant_id: str) -> bool:
    """注销租户"""
    try:
        adapter = get_multi_tenant_adapter()
        adapter.unregister_tenant(tenant_id)

        if _system_config and _system_config.enable_server:
            server = get_tenant_message_server()
            server.unregister_tenant(tenant_id)

        # 断开客户端连接
        if tenant_id in _server_clients:
            await _server_clients[tenant_id].disconnect()
            del _server_clients[tenant_id]

        logger.info(f"注销租户成功: {tenant_id}")
        return True

    except Exception as e:
        logger.error(f"注销租户失败 {tenant_id}: {e}")
        return False


# 消息处理API
async def process_tenant_message(
    message_data: Dict[str, Any],
    tenant_id: str,
    agent_id: str = "default",
    platform: str = "unknown",
    chat_stream_id: Optional[str] = None,
    priority: MessagePriority = MessagePriority.NORMAL,
) -> bool:
    """处理租户消息"""
    try:
        # 确保消息数据包含必要的字段
        message_data.update(
            {"tenant_id": tenant_id, "agent_id": agent_id, "platform": platform, "chat_stream_id": chat_stream_id}
        )

        adapter = get_multi_tenant_adapter()
        return await adapter.process_isolated_message(message_data, tenant_id, agent_id, priority)

    except Exception as e:
        logger.error(f"处理租户消息失败: {e}")
        return False


async def send_tenant_message(
    message: Union[MessageSending, Dict[str, Any]],
    tenant_id: str,
    agent_id: str = "default",
    platform: str = "unknown",
    priority: MessagePriority = MessagePriority.NORMAL,
) -> bool:
    """发送租户消息"""
    try:
        # 如果传入的是字典，创建MessageSending对象
        if isinstance(message, dict):
            message = MessageSending.from_dict(message)

        isolation_context = create_isolation_context(tenant_id=tenant_id, agent_id=agent_id, platform=platform)

        adapter = get_multi_tenant_adapter()
        return await adapter.send_isolated_message(message, isolation_context, priority)

    except Exception as e:
        logger.error(f"发送租户消息失败: {e}")
        return False


async def broadcast_to_tenant(
    tenant_id: str, platform: str, message_data: Dict[str, Any], exclude_agent: Optional[str] = None
) -> bool:
    """向租户广播消息"""
    try:
        adapter = get_multi_tenant_adapter()
        return await adapter.broadcast_to_tenant(tenant_id, platform, message_data, exclude_agent)

    except Exception as e:
        logger.error(f"租户消息广播失败: {e}")
        return False


async def broadcast_to_platform(
    platform: str, message_data: Dict[str, Any], exclude_tenant: Optional[str] = None
) -> int:
    """向平台广播消息"""
    try:
        if not _system_config or not _system_config.enable_server:
            logger.warning("租户消息服务器未启用")
            return 0

        server = get_tenant_message_server()
        return await server.broadcast_to_platform(platform, message_data, exclude_tenant)

    except Exception as e:
        logger.error(f"平台消息广播失败: {e}")
        return 0


# 路由管理API
def add_route_rule(
    rule_id: str,
    name: str,
    target_type: RouteTarget,
    target_pattern: str,
    conditions: Optional[Dict[str, Any]] = None,
    priority: int = 0,
) -> bool:
    """添加路由规则"""
    try:
        rule = RouteRule(
            rule_id=rule_id,
            name=name,
            target_type=target_type,
            target_pattern=target_pattern,
            conditions=conditions or {},
            priority=priority,
        )

        router = get_message_router()
        router.add_rule(rule)
        return True

    except Exception as e:
        logger.error(f"添加路由规则失败: {e}")
        return False


def remove_route_rule(rule_id: str) -> bool:
    """移除路由规则"""
    try:
        router = get_message_router()
        router.remove_rule(rule_id)
        return True

    except Exception as e:
        logger.error(f"移除路由规则失败: {e}")
        return False


def add_route_action(action_id: str, name: str, action_type: str, parameters: Optional[Dict[str, Any]] = None) -> bool:
    """添加路由动作"""
    try:
        action = RouteAction(action_id=action_id, name=name, action_type=action_type, parameters=parameters or {})

        router = get_message_router()
        router.add_action(action)
        return True

    except Exception as e:
        logger.error(f"添加路由动作失败: {e}")
        return False


async def route_message(
    message_data: Dict[str, Any], context: Dict[str, Any], priority: MessagePriority = MessagePriority.NORMAL
) -> List[str]:
    """路由消息"""
    try:
        router = get_message_router()
        return router.route_message(message_data, context, priority)

    except Exception as e:
        logger.error(f"消息路由失败: {e}")
        return []


# 统计和监控API
def get_system_stats() -> Dict[str, Any]:
    """获取系统统计信息"""
    stats = {"adapter": {}, "router": {}, "server": {}, "clients": {}}

    try:
        # 适配器统计
        adapter = get_multi_tenant_adapter()
        stats["adapter"] = {"tenants": len(adapter.tenant_configs), "tenant_stats": adapter.get_all_stats()}

        # 路由器统计
        router = get_message_router()
        stats["router"] = router.get_stats()
        stats["router"]["rule_stats"] = router.get_rule_stats()

        # 服务器统计
        if _system_config and _system_config.enable_server:
            server = get_tenant_message_server()
            stats["server"] = server.get_stats()

        # 客户端统计
        for tenant_id, client in _server_clients.items():
            stats["clients"][tenant_id] = client.get_stats()

    except Exception as e:
        logger.error(f"获取系统统计信息失败: {e}")

    return stats


def get_tenant_stats(tenant_id: str) -> Optional[Dict[str, Any]]:
    """获取租户统计信息"""
    try:
        adapter = get_multi_tenant_adapter()
        return adapter.get_tenant_stats(tenant_id)

    except Exception as e:
        logger.error(f"获取租户统计信息失败: {e}")
        return None


def list_tenants() -> List[str]:
    """列出所有租户"""
    try:
        adapter = get_multi_tenant_adapter()
        return list(adapter.tenant_configs.keys())

    except Exception as e:
        logger.error(f"列出租户失败: {e}")
        return []


def list_route_rules() -> List[Dict[str, Any]]:
    """列出所有路由规则"""
    try:
        router = get_message_router()
        return router.export_rules()

    except Exception as e:
        logger.error(f"列出路由规则失败: {e}")
        return []


# 资源管理API
async def cleanup_tenant_resources(tenant_id: str) -> bool:
    """清理租户资源"""
    try:
        adapter = get_multi_tenant_adapter()
        await adapter.cleanup_tenant(tenant_id)

        # 断开客户端连接
        if tenant_id in _server_clients:
            await _server_clients[tenant_id].disconnect()
            del _server_clients[tenant_id]

        logger.info(f"清理租户资源完成: {tenant_id}")
        return True

    except Exception as e:
        logger.error(f"清理租户资源失败 {tenant_id}: {e}")
        return False


async def cleanup_all_resources():
    """清理所有资源"""
    try:
        tenant_ids = list_tenants()
        for tenant_id in tenant_ids:
            await cleanup_tenant_resources(tenant_id)

        logger.info("清理所有资源完成")

    except Exception as e:
        logger.error(f"清理所有资源失败: {e}")


# 便捷的批量操作API
async def register_multiple_tenants(tenant_configs: List[Dict[str, Any]]) -> Dict[str, bool]:
    """批量注册租户"""
    results = {}
    for config in tenant_configs:
        tenant_id = config.get("tenant_id")
        if tenant_id:
            results[tenant_id] = await register_tenant(**config)
    return results


async def send_bulk_messages(messages: List[Dict[str, Any]]) -> List[bool]:
    """批量发送消息"""
    results = []
    for message in messages:
        result = await send_tenant_message(**message)
        results.append(result)
    return results


# 配置管理API
def update_system_config(config: TenantSystemConfig):
    """更新系统配置"""
    global _system_config
    _system_config = config
    logger.info("系统配置已更新")


def get_system_config() -> Optional[TenantSystemConfig]:
    """获取系统配置"""
    return _system_config


# 向后兼容性API
async def process_isolated_message(
    message_data: Dict[str, Any],
    isolation_context: IsolationContext,
    priority: MessagePriority = MessagePriority.NORMAL,
) -> bool:
    """向后兼容：处理隔离消息"""
    return await process_tenant_message(
        message_data=message_data,
        tenant_id=isolation_context.tenant_id,
        agent_id=isolation_context.agent_id,
        platform=isolation_context.platform,
        chat_stream_id=isolation_context.chat_stream_id,
        priority=priority,
    )


async def send_isolated_message(
    message: MessageSending, isolation_context: IsolationContext, priority: MessagePriority = MessagePriority.NORMAL
) -> bool:
    """向后兼容：发送隔离消息"""
    return await send_tenant_message(
        message=message,
        tenant_id=isolation_context.tenant_id,
        agent_id=isolation_context.agent_id,
        platform=isolation_context.platform,
        priority=priority,
    )


# 事件回调管理API
def set_message_received_callback(callback: Callable):
    """设置消息接收回调"""
    adapter = get_multi_tenant_adapter()
    adapter.on_message_received = callback

    if _system_config and _system_config.enable_server:
        server = get_tenant_message_server()
        server.on_message_received = callback


def set_message_sent_callback(callback: Callable):
    """设置消息发送回调"""
    adapter = get_multi_tenant_adapter()
    adapter.on_message_sent = callback


def set_error_callback(callback: Callable):
    """设置错误回调"""
    adapter = get_multi_tenant_adapter()
    adapter.on_error = callback

    if _system_config and _system_config.enable_server:
        server = get_tenant_message_server()
        server.on_error = callback


# 调试和诊断API
async def test_tenant_connection(tenant_id: str) -> bool:
    """测试租户连接"""
    try:
        if tenant_id in _server_clients:
            client = _server_clients[tenant_id]
            return client._is_connected()

        # 如果没有客户端连接，尝试创建临时连接进行测试
        adapter = get_multi_tenant_adapter()
        if tenant_id in adapter.tenant_configs:
            config = adapter.tenant_configs[tenant_id]
            client_config = ClientConfig(
                tenant_id=tenant_id,
                agent_id="default",
                platform="default",
                server_url=config.server_url,
                api_key=config.api_key
            )
            client = TenantMessageClient(client_config)
            connected = await client.connect()
            if connected:
                # 等待连接确认
                await client._wait_for_connection_confirmation()
                await client.disconnect()
                return True
            else:
                return False

        return False

    except Exception as e:
        logger.error(f"测试租户连接失败 {tenant_id}: {e}")
        return False


def get_diagnostics() -> Dict[str, Any]:
    """获取诊断信息"""
    diagnostics = {
        "timestamp": datetime.now().isoformat(),
        "system_config": {
            "enable_server": _system_config.enable_server if _system_config else False,
            "enable_router": _system_config.enable_router if _system_config else False,
            "enable_adapter": _system_config.enable_adapter if _system_config else False,
        },
        "components": {
            "adapter_initialized": False,
            "router_running": False,
            "server_running": False,
            "active_clients": len(_server_clients),
        },
    }

    try:
        # 检查各组件状态
        adapter = get_multi_tenant_adapter()
        diagnostics["components"]["adapter_initialized"] = adapter._initialized

        router = get_message_router()
        diagnostics["components"]["router_running"] = router._running

        if _system_config and _system_config.enable_server:
            server = get_tenant_message_server()
            diagnostics["components"]["server_running"] = server._running

    except Exception as e:
        diagnostics["error"] = str(e)

    return diagnostics
