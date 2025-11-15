"""
插件核心管理模块

提供插件的加载、注册和管理功能
包含多租户隔离的事件系统
"""

from src.plugin_system.core.plugin_manager import plugin_manager
from src.plugin_system.core.component_registry import component_registry
from src.plugin_system.core.events_manager import events_manager
from src.plugin_system.core.global_announcement_manager import global_announcement_manager

# 隔离化事件系统
from src.plugin_system.core.isolated_events_manager import (
    IsolatedEventsManager,
    get_isolated_events_manager,
    clear_isolated_events_manager,
    get_events_manager_stats,
    shutdown_all_events_managers,
)

try:
    from src.plugin_system.core.event_types import (
        EventType,
        IsolatedEventType,
        get_event_types_by_group,
        get_all_event_types,
        get_high_priority_events,
        get_isolation_events,
        get_events_requiring_isolation_context,
    )
except Exception as e:
    import sys

    print(f"Warning: Failed to import isolated event types: {e}", file=sys.stderr)
    # 回退到基础事件类型
    from src.plugin_system.base.component_types import EventType

    IsolatedEventType = EventType

    # 提供空的函数实现
    def get_event_types_by_group(*args, **kwargs):
        return []

    def get_all_event_types(*args, **kwargs):
        return []

    def get_high_priority_events(*args, **kwargs):
        return []

    def get_isolation_events(*args, **kwargs):
        return []

    def get_events_requiring_isolation_context(*args, **kwargs):
        return []


from src.plugin_system.core.isolated_event import (
    IsolatedEvent,
    EventSubscription,
    EventPriority,
    create_isolated_event,
    create_event_subscription,
)
from src.plugin_system.core.event_result import (
    EventResult,
    ResultStatus,
    create_event_result,
    store_event_result,
    get_event_results,
    query_event_results,
)
from src.plugin_system.core.isolated_event_api import (
    publish_isolated_event,
    publish_message_event,
    subscribe_to_events,
    subscribe_to_message_events,
    get_event_history,
    get_event_statistics,
    event_handler,
    message_event_handler,
    cleanup_events,
    clear_events,
    get_system_health,
    health_check,
    batch_publish_events,
    batch_get_event_history,
    create_event_context,
    validate_event_permissions,
)
from src.plugin_system.core.events_compatibility import (
    CompatibleEventsManager,
    create_compatible_events_manager,
    migrate_to_isolated_events,
    check_migration_status,
    MigrationHelper,
    auto_migration_check,
)

__all__ = [
    # 原有核心模块
    "plugin_manager",
    "component_registry",
    "events_manager",
    "global_announcement_manager",
    # 隔离化事件管理器
    "IsolatedEventsManager",
    "get_isolated_events_manager",
    "clear_isolated_events_manager",
    "get_events_manager_stats",
    "shutdown_all_events_managers",
    # 扩展事件类型
    "EventType",
    "get_event_types_by_group",
    "get_all_event_types",
    "get_high_priority_events",
    "get_isolation_events",
    "get_events_requiring_isolation_context",
    # 隔离化事件类
    "IsolatedEvent",
    "EventSubscription",
    "EventPriority",
    "create_isolated_event",
    "create_event_subscription",
    # 事件结果
    "EventResult",
    "ResultStatus",
    "create_event_result",
    "store_event_result",
    "get_event_results",
    "query_event_results",
    # 便捷API
    "publish_isolated_event",
    "publish_message_event",
    "subscribe_to_events",
    "subscribe_to_message_events",
    "get_event_history",
    "get_event_statistics",
    "event_handler",
    "message_event_handler",
    "cleanup_events",
    "clear_events",
    "get_system_health",
    "health_check",
    "batch_publish_events",
    "batch_get_event_history",
    "create_event_context",
    "validate_event_permissions",
    # 向后兼容性
    "CompatibleEventsManager",
    "create_compatible_events_manager",
    "migrate_to_isolated_events",
    "check_migration_status",
    "MigrationHelper",
    "auto_migration_check",
]
