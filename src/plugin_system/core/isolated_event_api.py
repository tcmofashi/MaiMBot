"""
隔离化事件系统便捷API接口
提供简单易用的事件发布、订阅、查询和管理功能
"""

from typing import Dict, List, Any, Optional, Union, Callable
from datetime import datetime, timedelta
from functools import wraps

try:
    from typing import TYPE_CHECKING
except ImportError:
    TYPE_CHECKING = False

if TYPE_CHECKING:
    from src.chat.message_receive.message import MessageRecv, MessageSending

from src.common.logger import get_logger
from src.isolation.isolation_context import IsolationContext, create_isolation_context
from src.plugin_system.core.event_types import IsolatedEventType
from src.plugin_system.core.isolated_event import (
    IsolatedEvent,
    EventPriority,
    create_isolated_event,
    create_event_subscription,
)
from src.plugin_system.core.isolated_events_manager import _global_events_manager_manager
from src.plugin_system.core.event_result import query_event_results, get_isolated_result_manager

logger = get_logger("isolated_event_api")


# 便捷的事件发布函数
async def publish_isolated_event(
    event_type: Union[IsolatedEventType, str],
    data: Dict[str, Any],
    tenant_id: str,
    agent_id: str,
    platform: Optional[str] = None,
    chat_stream_id: Optional[str] = None,
    priority: EventPriority = EventPriority.NORMAL,
    **kwargs,
) -> bool:
    """发布隔离化事件的便捷函数

    Args:
        event_type: 事件类型
        data: 事件数据
        tenant_id: 租户ID
        agent_id: 智能体ID
        platform: 平台ID
        chat_stream_id: 聊天流ID
        priority: 事件优先级
        **kwargs: 额外参数

    Returns:
        bool: 是否发布成功
    """
    try:
        # 创建隔离上下文
        isolation_context = create_isolation_context(
            tenant_id=tenant_id, agent_id=agent_id, platform=platform, chat_stream_id=chat_stream_id
        )

        # 创建事件对象
        event = create_isolated_event(
            event_type=event_type, data=data, isolation_context=isolation_context, priority=priority, **kwargs
        )

        # 获取事件管理器并发布事件
        # 这里需要实现具体的事件发布逻辑
        # 暂时返回True表示成功
        logger.info(f"发布隔离化事件: {event.event_type} -> {event.get_scope_key()}")
        return True

    except Exception as e:
        logger.error(f"发布隔离化事件失败: {event_type}, 错误: {e}")
        return False


async def publish_message_event(
    message: Union["MessageRecv", "MessageSending"],
    tenant_id: str,
    agent_id: str,
    event_type: IsolatedEventType = IsolatedEventType.ON_ISOLATED_MESSAGE,
    **kwargs,
) -> bool:
    """发布消息事件的便捷函数

    Args:
        message: 消息对象
        tenant_id: 租户ID
        agent_id: 智能体ID
        event_type: 事件类型
        **kwargs: 额外参数

    Returns:
        bool: 是否发布成功
    """
    try:
        # 从消息中提取平台和聊天流信息
        platform = None
        chat_stream_id = None

        if hasattr(message, "message_info") and message.message_info:
            if message.message_info.platform:
                platform = message.message_info.platform

        if hasattr(message, "chat_stream") and message.chat_stream:
            chat_stream_id = message.chat_stream.stream_id

        return await publish_isolated_event(
            event_type=event_type,
            data={"message": message},
            tenant_id=tenant_id,
            agent_id=agent_id,
            platform=platform,
            chat_stream_id=chat_stream_id,
            **kwargs,
        )

    except Exception as e:
        logger.error(f"发布消息事件失败: {event_type}, 错误: {e}")
        return False


# 便捷的事件订阅函数
def subscribe_to_events(
    event_types: List[Union[IsolatedEventType, str]],
    handler: Callable[[IsolatedEvent], Any],
    tenant_id: str,
    agent_id: str,
    platform: Optional[str] = None,
    chat_stream_id: Optional[str] = None,
    filters: Optional[Dict[str, Any]] = None,
    priority: EventPriority = EventPriority.NORMAL,
) -> str:
    """订阅事件的便捷函数

    Args:
        event_types: 事件类型列表
        handler: 事件处理函数
        tenant_id: 租户ID
        agent_id: 智能体ID
        platform: 平台ID
        chat_stream_id: 聊天流ID
        filters: 过滤条件
        priority: 优先级

    Returns:
        str: 订阅ID
    """
    try:
        # 创建隔离上下文
        isolation_context = create_isolation_context(
            tenant_id=tenant_id, agent_id=agent_id, platform=platform, chat_stream_id=chat_stream_id
        )

        # 创建事件订阅
        subscription = create_event_subscription(
            subscriber_id=f"{tenant_id}:{agent_id}",
            event_types=event_types,
            isolation_context=isolation_context,
            handler=handler,
            filters=filters,
            priority=priority,
        )

        # 这里需要实现具体的订阅逻辑
        # 暂时返回订阅ID
        logger.info(f"订阅事件: {event_types} -> {subscription.get_scope_key()}")
        return subscription.subscription_id

    except Exception as e:
        logger.error(f"订阅事件失败: {event_types}, 错误: {e}")
        return ""


def subscribe_to_message_events(
    handler: Callable[[IsolatedEvent], Any], tenant_id: str, agent_id: str, platform: Optional[str] = None, **kwargs
) -> str:
    """订阅消息事件的便捷函数

    Args:
        handler: 事件处理函数
        tenant_id: 租户ID
        agent_id: 智能体ID
        platform: 平台ID
        **kwargs: 额外参数

    Returns:
        str: 订阅ID
    """
    return subscribe_to_events(
        event_types=[IsolatedEventType.ON_ISOLATED_MESSAGE, IsolatedEventType.ON_MESSAGE],
        handler=handler,
        tenant_id=tenant_id,
        agent_id=agent_id,
        platform=platform,
        **kwargs,
    )


# 事件查询函数
def get_event_history(
    tenant_id: str,
    agent_id: str,
    event_type: Optional[str] = None,
    platform: Optional[str] = None,
    chat_stream_id: Optional[str] = None,
    limit: Optional[int] = 100,
    hours: Optional[int] = 24,
) -> List[Dict[str, Any]]:
    """获取事件历史记录的便捷函数

    Args:
        tenant_id: 租户ID
        agent_id: 智能体ID
        event_type: 事件类型
        platform: 平台ID
        chat_stream_id: 聊天流ID
        limit: 限制数量
        hours: 时间范围（小时）

    Returns:
        List[Dict]: 事件历史记录
    """
    try:
        # 创建隔离上下文
        isolation_context = create_isolation_context(
            tenant_id=tenant_id, agent_id=agent_id, platform=platform, chat_stream_id=chat_stream_id
        )

        # 计算时间范围
        start_time = datetime.now() - timedelta(hours=hours) if hours else None
        end_time = datetime.now()

        # 查询事件结果
        results = query_event_results(
            isolation_context=isolation_context,
            event_type=event_type,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )

        # 转换为字典格式
        return [result.to_dict() for result in results]

    except Exception as e:
        logger.error(f"获取事件历史失败: {event_type}, 错误: {e}")
        return []


def get_event_statistics(
    tenant_id: str, agent_id: str, platform: Optional[str] = None, chat_stream_id: Optional[str] = None
) -> Dict[str, Any]:
    """获取事件统计信息的便捷函数

    Args:
        tenant_id: 租户ID
        agent_id: 智能体ID
        platform: 平台ID
        chat_stream_id: 聊天流ID

    Returns:
        Dict: 统计信息
    """
    try:
        # 创建隔离上下文
        isolation_context = create_isolation_context(
            tenant_id=tenant_id, agent_id=agent_id, platform=platform, chat_stream_id=chat_stream_id
        )

        # 获取事件结果管理器
        result_manager = get_isolated_result_manager()

        # 获取统计信息
        return result_manager.get_statistics(isolation_context)

    except Exception as e:
        logger.error(f"获取事件统计失败: 错误: {e}")
        return {}


# 装饰器函数
def event_handler(
    event_types: List[Union[IsolatedEventType, str]],
    tenant_id: str,
    agent_id: str,
    platform: Optional[str] = None,
    **kwargs,
):
    """事件处理器装饰器

    Args:
        event_types: 事件类型列表
        tenant_id: 租户ID
        agent_id: 智能体ID
        platform: 平台ID
        **kwargs: 额外参数
    """

    def decorator(func):
        # 自动注册事件处理器
        subscription_id = subscribe_to_events(
            event_types=event_types, handler=func, tenant_id=tenant_id, agent_id=agent_id, platform=platform, **kwargs
        )

        @wraps(func)
        async def wrapper(event: IsolatedEvent):
            try:
                return await func(event)
            except Exception as e:
                logger.error(f"事件处理器执行失败: {func.__name__}, 事件: {event.event_id}, 错误: {e}")
                raise

        # 保存订阅ID到函数属性
        wrapper._subscription_id = subscription_id
        wrapper._event_types = event_types
        wrapper._isolation_context = create_isolation_context(tenant_id=tenant_id, agent_id=agent_id, platform=platform)

        return wrapper

    return decorator


def message_event_handler(tenant_id: str, agent_id: str, platform: Optional[str] = None, **kwargs):
    """消息事件处理器装饰器

    Args:
        tenant_id: 租户ID
        agent_id: 智能体ID
        platform: 平台ID
        **kwargs: 额外参数
    """
    return event_handler(
        event_types=[IsolatedEventType.ON_ISOLATED_MESSAGE, IsolatedEventType.ON_MESSAGE],
        tenant_id=tenant_id,
        agent_id=agent_id,
        platform=platform,
        **kwargs,
    )


# 系统管理函数
async def cleanup_events(tenant_id: str, agent_id: Optional[str] = None, older_than_hours: int = 24) -> int:
    """清理旧事件数据

    Args:
        tenant_id: 租户ID
        agent_id: 智能体ID（可选）
        older_than_hours: 清理多少小时前的事件

    Returns:
        int: 清理的事件数量
    """
    try:
        count = 0

        if agent_id:
            # 清理特定智能体的事件
            # 这里需要实现具体的清理逻辑
            # count = get_isolated_events_manager(tenant_id, agent_id).cleanup_old_events(older_than_hours)
            pass
        else:
            # 清理租户下所有智能体的事件
            manager_stats = _global_events_manager_manager.get_manager_stats()
            for key, _stats in manager_stats.items():
                if key.startswith(f"{tenant_id}:"):
                    # 这里需要实现具体的清理逻辑
                    # count += manager.cleanup_old_events(older_than_hours)
                    pass

        logger.info(f"清理了租户 {tenant_id} 的 {count} 个旧事件")
        return count

    except Exception as e:
        logger.error(f"清理事件失败: {e}")
        return 0


def clear_events(
    tenant_id: str, agent_id: Optional[str] = None, platform: Optional[str] = None, chat_stream_id: Optional[str] = None
) -> int:
    """清空事件数据

    Args:
        tenant_id: 租户ID
        agent_id: 智能体ID（可选）
        platform: 平台ID（可选）
        chat_stream_id: 聊天流ID（可选）

    Returns:
        int: 清理的事件数量
    """
    try:
        count = 0

        if agent_id:
            # 清理特定智能体的事件
            isolation_context = create_isolation_context(
                tenant_id=tenant_id, agent_id=agent_id, platform=platform, chat_stream_id=chat_stream_id
            )
            result_manager = get_isolated_result_manager()
            count = result_manager.clear_results(isolation_context)
        else:
            # 清理租户下所有智能体的事件
            result_manager = get_isolated_result_manager()
            result_manager.cleanup_tenant_results(tenant_id)
            count = 1  # 表示清理操作已执行

        logger.info(f"清空了租户 {tenant_id} 的事件数据")
        return count

    except Exception as e:
        logger.error(f"清空事件失败: {e}")
        return 0


# 健康检查和监控函数
def get_system_health() -> Dict[str, Any]:
    """获取事件系统健康状态

    Returns:
        Dict: 健康状态信息
    """
    try:
        health = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "managers": {},
            "total_events": 0,
            "active_subscriptions": 0,
        }

        # 获取所有事件管理器的统计信息
        manager_stats = _global_events_manager_manager.get_manager_stats()
        for key, stats in manager_stats.items():
            health["managers"][key] = stats
            health["total_events"] += stats.get("handler_count", 0)

        # 这里可以添加更多的健康检查逻辑

        return health

    except Exception as e:
        logger.error(f"获取系统健康状态失败: {e}")
        return {"status": "unhealthy", "timestamp": datetime.now().isoformat(), "error": str(e)}


async def health_check() -> bool:
    """执行健康检查

    Returns:
        bool: 是否健康
    """
    try:
        health = get_system_health()
        return health["status"] == "healthy"
    except Exception:
        return False


# 批量操作函数
async def batch_publish_events(events: List[Dict[str, Any]], tenant_id: str, agent_id: str) -> Dict[str, int]:
    """批量发布事件

    Args:
        events: 事件列表
        tenant_id: 租户ID
        agent_id: 智能体ID

    Returns:
        Dict: 发布结果统计
    """
    results = {"success": 0, "failed": 0}

    for event_data in events:
        try:
            success = await publish_isolated_event(
                event_type=event_data.get("event_type"),
                data=event_data.get("data", {}),
                tenant_id=tenant_id,
                agent_id=agent_id,
                **event_data.get("kwargs", {}),
            )

            if success:
                results["success"] += 1
            else:
                results["failed"] += 1

        except Exception as e:
            logger.error(f"批量发布事件失败: {e}")
            results["failed"] += 1

    return results


def batch_get_event_history(tenant_id: str, agent_ids: List[str], **kwargs) -> Dict[str, List[Dict[str, Any]]]:
    """批量获取多个智能体的事件历史

    Args:
        tenant_id: 租户ID
        agent_ids: 智能体ID列表
        **kwargs: 查询参数

    Returns:
        Dict: 每个智能体的事件历史
    """
    results = {}

    for agent_id in agent_ids:
        try:
            history = get_event_history(tenant_id=tenant_id, agent_id=agent_id, **kwargs)
            results[agent_id] = history
        except Exception as e:
            logger.error(f"获取智能体 {agent_id} 事件历史失败: {e}")
            results[agent_id] = []

    return results


# 工具函数
def create_event_context(
    tenant_id: str, agent_id: str, platform: Optional[str] = None, chat_stream_id: Optional[str] = None
) -> IsolationContext:
    """创建事件隔离上下文的便捷函数"""
    return create_isolation_context(
        tenant_id=tenant_id, agent_id=agent_id, platform=platform, chat_stream_id=chat_stream_id
    )


def validate_event_permissions(event: IsolatedEvent, tenant_id: str, agent_id: str) -> bool:
    """验证事件权限的便捷函数"""
    return event.isolation_context.tenant_id == tenant_id and event.isolation_context.agent_id == agent_id


# 导出的便捷函数列表
__all__ = [
    # 事件发布
    "publish_isolated_event",
    "publish_message_event",
    # 事件订阅
    "subscribe_to_events",
    "subscribe_to_message_events",
    # 事件查询
    "get_event_history",
    "get_event_statistics",
    # 装饰器
    "event_handler",
    "message_event_handler",
    # 系统管理
    "cleanup_events",
    "clear_events",
    # 健康检查
    "get_system_health",
    "health_check",
    # 批量操作
    "batch_publish_events",
    "batch_get_event_history",
    # 工具函数
    "create_event_context",
    "validate_event_permissions",
]
