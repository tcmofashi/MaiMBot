"""
扩展的事件类型定义
包含原有事件类型和新增的隔离相关事件类型
"""

from typing import Optional
from enum import Enum

# 为了向后兼容，提供EventType别名
EventType = None


class IsolatedEventType(Enum):
    """
    隔离化事件类型枚举类
    包含原有事件类型和新增的隔离相关事件类型
    """

    # 基础系统事件（向后兼容）
    ON_START = "on_start"  # 系统启动事件
    ON_STOP = "on_stop"  # 系统停止事件
    ON_MESSAGE = "on_message"  # 消息事件
    ON_PLAN = "on_plan"  # 规划事件
    POST_LLM = "post_llm"  # LLM后处理事件
    AFTER_LLM = "after_llm"  # LLM后事件

    # 隔离化消息事件
    ON_ISOLATED_MESSAGE = "on_isolated_message"  # 隔离化消息事件
    ON_TENANT_MESSAGE = "on_tenant_message"  # 租户级别消息事件
    ON_AGENT_MESSAGE = "on_agent_message"  # 智能体级别消息事件
    ON_PLATFORM_MESSAGE = "on_platform_message"  # 平台级别消息事件
    ON_CHAT_STREAM_MESSAGE = "on_chat_stream_message"  # 聊天流级别消息事件

    # 智能体配置变更事件
    ON_AGENT_CONFIG_CHANGE = "on_agent_config_change"  # 智能体配置变更事件
    ON_AGENT_CREATED = "on_agent_created"  # 智能体创建事件
    ON_AGENT_UPDATED = "on_agent_updated"  # 智能体更新事件
    ON_AGENT_DELETED = "on_agent_deleted"  # 智能体删除事件
    ON_AGENT_ACTIVATED = "on_agent_activated"  # 智能体激活事件
    ON_AGENT_DEACTIVATED = "on_agent_deactivated"  # 智能体停用事件

    # 平台相关事件
    ON_PLATFORM_SWITCH = "on_platform_switch"  # 平台切换事件
    ON_PLATFORM_CONNECTED = "on_platform_connected"  # 平台连接事件
    ON_PLATFORM_DISCONNECTED = "on_platform_disconnected"  # 平台断开连接事件
    ON_PLATFORM_ERROR = "on_platform_error"  # 平台错误事件

    # 聊天流生命周期事件
    ON_CHAT_STREAM_CREATED = "on_chat_stream_created"  # 聊天流创建事件
    ON_CHAT_STREAM_DESTROYED = "on_chat_stream_destroyed"  # 聊天流销毁事件
    ON_CHAT_STREAM_UPDATED = "on_chat_stream_updated"  # 聊天流更新事件
    ON_CHAT_STREAM_ARCHIVED = "on_chat_stream_archived"  # 聊天流归档事件

    # 记忆系统事件
    ON_MEMORY_UPDATE = "on_memory_update"  # 记忆更新事件
    ON_MEMORY_CREATED = "on_memory_created"  # 记忆创建事件
    ON_MEMORY_DELETED = "on_memory_deleted"  # 记忆删除事件
    ON_MEMORY_AGGREGATED = "on_memory_aggregated"  # 记忆聚合事件
    ON_MEMORY_CONFLICT = "on_memory_conflict"  # 记忆冲突事件

    # 租户管理事件
    ON_TENANT_CREATED = "on_tenant_created"  # 租户创建事件
    ON_TENANT_UPDATED = "on_tenant_updated"  # 租户更新事件
    ON_TENANT_DELETED = "on_tenant_deleted"  # 租户删除事件
    ON_TENANT_SUSPENDED = "on_tenant_suspended"  # 租户暂停事件
    ON_TENANT_RESUMED = "on_tenant_resumed"  # 租户恢复事件

    # 配置管理事件
    ON_CONFIG_LOADED = "on_config_loaded"  # 配置加载事件
    ON_CONFIG_CHANGED = "on_config_changed"  # 配置变更事件
    ON_CONFIG_VALIDATED = "on_config_validated"  # 配置验证事件
    ON_CONFIG_MIGRATED = "on_config_migrated"  # 配置迁移事件

    # 插件系统事件
    ON_PLUGIN_INSTALLED = "on_plugin_installed"  # 插件安装事件
    ON_PLUGIN_UNINSTALLED = "on_plugin_uninstalled"  # 插件卸载事件
    ON_PLUGIN_ENABLED = "on_plugin_enabled"  # 插件启用事件
    ON_PLUGIN_DISABLED = "on_plugin_disabled"  # 插件禁用事件
    ON_PLUGIN_UPDATED = "on_plugin_updated"  # 插件更新事件

    # 系统监控事件
    ON_SYSTEM_STARTUP = "on_system_startup"  # 系统启动事件
    ON_SYSTEM_SHUTDOWN = "on_system_shutdown"  # 系统关闭事件
    ON_HEALTH_CHECK = "on_health_check"  # 健康检查事件
    ON_RESOURCE_WARNING = "on_resource_warning"  # 资源警告事件
    ON_ERROR_OCCURRED = "on_error_occurred"  # 错误发生事件

    # 安全相关事件
    ON_SECURITY_ALERT = "on_security_alert"  # 安全警报事件
    ON_ACCESS_DENIED = "on_access_denied"  # 访问拒绝事件
    ON_RATE_LIMIT_EXCEEDED = "on_rate_limit_exceeded"  # 速率限制超出事件
    ON_UNAUTHORIZED_ACCESS = "on_unauthorized_access"  # 未授权访问事件

    # 数据同步事件
    ON_DATA_SYNC = "on_data_sync"  # 数据同步事件
    ON_DATA_BACKUP = "on_data_backup"  # 数据备份事件
    ON_DATA_RESTORE = "on_data_restore"  # 数据恢复事件
    ON_DATA_MIGRATION = "on_data_migration"  # 数据迁移事件

    def __str__(self) -> str:
        return self.value

    @property
    def is_isolation_event(self) -> bool:
        """判断是否为隔离相关事件"""
        isolation_prefixes = ["on_isolated_", "on_tenant_", "on_agent_", "on_platform_", "on_chat_stream_"]
        return any(self.value.startswith(prefix) for prefix in isolation_prefixes)

    @property
    def is_lifecycle_event(self) -> bool:
        """判断是否为生命周期事件"""
        lifecycle_suffixes = [
            "_created",
            "_updated",
            "_deleted",
            "_activated",
            "_deactivated",
            "_connected",
            "_disconnected",
            "_started",
            "_stopped",
        ]
        return any(self.value.endswith(suffix) for suffix in lifecycle_suffixes)

    @property
    def is_system_event(self) -> bool:
        """判断是否为系统级事件"""
        system_prefixes = ["on_system_", "on_config_", "on_plugin_", "on_security_", "on_data_"]
        return any(self.value.startswith(prefix) for prefix in system_prefixes)

    @property
    def requires_isolation_context(self) -> bool:
        """判断事件是否需要隔离上下文"""
        # 隔离相关事件和租户/智能体相关事件需要隔离上下文
        return self.is_isolation_event or self.value in [
            "on_agent_config_change",
            "on_memory_update",
            "on_memory_created",
            "on_memory_deleted",
            "on_memory_aggregated",
            "on_memory_conflict",
        ]

    @property
    def event_priority(self) -> int:
        """获取事件优先级（数值越高优先级越高）"""
        priority_map = {
            # 高优先级事件
            "on_security_alert": 100,
            "on_error_occurred": 90,
            "on_access_denied": 85,
            "on_unauthorized_access": 85,
            "on_rate_limit_exceeded": 80,
            "on_resource_warning": 75,
            # 中优先级事件
            "on_system_startup": 70,
            "on_system_shutdown": 70,
            "on_agent_created": 65,
            "on_agent_deleted": 65,
            "on_tenant_created": 60,
            "on_tenant_deleted": 60,
            "on_platform_connected": 55,
            "on_platform_disconnected": 55,
            "on_config_changed": 50,
            # 普通优先级事件
            "on_isolated_message": 30,
            "on_tenant_message": 25,
            "on_agent_message": 20,
            "on_platform_message": 15,
            "on_chat_stream_message": 10,
            "on_memory_update": 20,
            "on_memory_created": 20,
            "on_memory_deleted": 20,
            # 低优先级事件
            "on_health_check": 5,
            "on_data_sync": 5,
            "on_data_backup": 3,
            "on_data_restore": 3,
        }
        return priority_map.get(self.value, 10)

    def get_required_isolation_level(self) -> Optional[str]:
        """获取事件要求的隔离级别"""
        level_map = {
            # 租户级别事件
            "on_tenant_message": "tenant",
            "on_tenant_created": "tenant",
            "on_tenant_updated": "tenant",
            "on_tenant_deleted": "tenant",
            "on_tenant_suspended": "tenant",
            "on_tenant_resumed": "tenant",
            # 智能体级别事件
            "on_agent_message": "agent",
            "on_agent_config_change": "agent",
            "on_agent_created": "agent",
            "on_agent_updated": "agent",
            "on_agent_deleted": "agent",
            "on_agent_activated": "agent",
            "on_agent_deactivated": "agent",
            "on_memory_update": "agent",
            "on_memory_created": "agent",
            "on_memory_deleted": "agent",
            "on_memory_aggregated": "agent",
            # 平台级别事件
            "on_platform_message": "platform",
            "on_platform_switch": "platform",
            "on_platform_connected": "platform",
            "on_platform_disconnected": "platform",
            "on_platform_error": "platform",
            # 聊天流级别事件
            "on_chat_stream_message": "chat",
            "on_chat_stream_created": "chat",
            "on_chat_stream_destroyed": "chat",
            "on_chat_stream_updated": "chat",
            "on_chat_stream_archived": "chat",
            "on_memory_conflict": "chat",
            # 隔离化事件（根据上下文确定级别）
            "on_isolated_message": "context",
        }
        return level_map.get(self.value)

    def can_cross_isolation_boundary(self) -> bool:
        """判断事件是否可以跨越隔离边界"""
        # 某些系统级事件可以跨隔离边界传播
        cross_boundary_events = {
            "on_system_startup",
            "on_system_shutdown",
            "on_health_check",
            "on_config_loaded",
            "on_config_changed",
            "on_security_alert",
            "on_error_occurred",
            "on_resource_warning",
        }
        return self.value in cross_boundary_events

    def get_event_description(self) -> str:
        """获取事件描述"""
        descriptions = {
            # 隔离化消息事件
            "on_isolated_message": "隔离化消息处理事件",
            "on_tenant_message": "租户级别消息事件",
            "on_agent_message": "智能体级别消息事件",
            "on_platform_message": "平台级别消息事件",
            "on_chat_stream_message": "聊天流级别消息事件",
            # 智能体配置变更事件
            "on_agent_config_change": "智能体配置变更事件",
            "on_agent_created": "智能体创建事件",
            "on_agent_updated": "智能体更新事件",
            "on_agent_deleted": "智能体删除事件",
            "on_agent_activated": "智能体激活事件",
            "on_agent_deactivated": "智能体停用事件",
            # 平台相关事件
            "on_platform_switch": "平台切换事件",
            "on_platform_connected": "平台连接事件",
            "on_platform_disconnected": "平台断开连接事件",
            "on_platform_error": "平台错误事件",
            # 聊天流生命周期事件
            "on_chat_stream_created": "聊天流创建事件",
            "on_chat_stream_destroyed": "聊天流销毁事件",
            "on_chat_stream_updated": "聊天流更新事件",
            "on_chat_stream_archived": "聊天流归档事件",
            # 记忆系统事件
            "on_memory_update": "记忆更新事件",
            "on_memory_created": "记忆创建事件",
            "on_memory_deleted": "记忆删除事件",
            "on_memory_aggregated": "记忆聚合事件",
            "on_memory_conflict": "记忆冲突事件",
            # 租户管理事件
            "on_tenant_created": "租户创建事件",
            "on_tenant_updated": "租户更新事件",
            "on_tenant_deleted": "租户删除事件",
            "on_tenant_suspended": "租户暂停事件",
            "on_tenant_resumed": "租户恢复事件",
            # 配置管理事件
            "on_config_loaded": "配置加载事件",
            "on_config_changed": "配置变更事件",
            "on_config_validated": "配置验证事件",
            "on_config_migrated": "配置迁移事件",
            # 插件系统事件
            "on_plugin_installed": "插件安装事件",
            "on_plugin_uninstalled": "插件卸载事件",
            "on_plugin_enabled": "插件启用事件",
            "on_plugin_disabled": "插件禁用事件",
            "on_plugin_updated": "插件更新事件",
            # 系统监控事件
            "on_system_startup": "系统启动事件",
            "on_system_shutdown": "系统关闭事件",
            "on_health_check": "健康检查事件",
            "on_resource_warning": "资源警告事件",
            "on_error_occurred": "错误发生事件",
            # 安全相关事件
            "on_security_alert": "安全警报事件",
            "on_access_denied": "访问拒绝事件",
            "on_rate_limit_exceeded": "速率限制超出事件",
            "on_unauthorized_access": "未授权访问事件",
            # 数据同步事件
            "on_data_sync": "数据同步事件",
            "on_data_backup": "数据备份事件",
            "on_data_restore": "数据恢复事件",
            "on_data_migration": "数据迁移事件",
        }
        return descriptions.get(self.value, "未知事件类型")


# 事件类型分组
EVENT_TYPE_GROUPS = {
    "message": [
        IsolatedEventType.ON_ISOLATED_MESSAGE,
        IsolatedEventType.ON_TENANT_MESSAGE,
        IsolatedEventType.ON_AGENT_MESSAGE,
        IsolatedEventType.ON_PLATFORM_MESSAGE,
        IsolatedEventType.ON_CHAT_STREAM_MESSAGE,
    ],
    "agent": [
        IsolatedEventType.ON_AGENT_CONFIG_CHANGE,
        IsolatedEventType.ON_AGENT_CREATED,
        IsolatedEventType.ON_AGENT_UPDATED,
        IsolatedEventType.ON_AGENT_DELETED,
        IsolatedEventType.ON_AGENT_ACTIVATED,
        IsolatedEventType.ON_AGENT_DEACTIVATED,
    ],
    "platform": [
        IsolatedEventType.ON_PLATFORM_SWITCH,
        IsolatedEventType.ON_PLATFORM_CONNECTED,
        IsolatedEventType.ON_PLATFORM_DISCONNECTED,
        IsolatedEventType.ON_PLATFORM_ERROR,
    ],
    "chat_stream": [
        IsolatedEventType.ON_CHAT_STREAM_CREATED,
        IsolatedEventType.ON_CHAT_STREAM_DESTROYED,
        IsolatedEventType.ON_CHAT_STREAM_UPDATED,
        IsolatedEventType.ON_CHAT_STREAM_ARCHIVED,
    ],
    "memory": [
        IsolatedEventType.ON_MEMORY_UPDATE,
        IsolatedEventType.ON_MEMORY_CREATED,
        IsolatedEventType.ON_MEMORY_DELETED,
        IsolatedEventType.ON_MEMORY_AGGREGATED,
        IsolatedEventType.ON_MEMORY_CONFLICT,
    ],
    "tenant": [
        IsolatedEventType.ON_TENANT_CREATED,
        IsolatedEventType.ON_TENANT_UPDATED,
        IsolatedEventType.ON_TENANT_DELETED,
        IsolatedEventType.ON_TENANT_SUSPENDED,
        IsolatedEventType.ON_TENANT_RESUMED,
    ],
    "config": [
        IsolatedEventType.ON_CONFIG_LOADED,
        IsolatedEventType.ON_CONFIG_CHANGED,
        IsolatedEventType.ON_CONFIG_VALIDATED,
        IsolatedEventType.ON_CONFIG_MIGRATED,
    ],
    "plugin": [
        IsolatedEventType.ON_PLUGIN_INSTALLED,
        IsolatedEventType.ON_PLUGIN_UNINSTALLED,
        IsolatedEventType.ON_PLUGIN_ENABLED,
        IsolatedEventType.ON_PLUGIN_DISABLED,
        IsolatedEventType.ON_PLUGIN_UPDATED,
    ],
    "system": [
        IsolatedEventType.ON_SYSTEM_STARTUP,
        IsolatedEventType.ON_SYSTEM_SHUTDOWN,
        IsolatedEventType.ON_HEALTH_CHECK,
        IsolatedEventType.ON_RESOURCE_WARNING,
        IsolatedEventType.ON_ERROR_OCCURRED,
    ],
    "security": [
        IsolatedEventType.ON_SECURITY_ALERT,
        IsolatedEventType.ON_ACCESS_DENIED,
        IsolatedEventType.ON_RATE_LIMIT_EXCEEDED,
        IsolatedEventType.ON_UNAUTHORIZED_ACCESS,
    ],
    "data": [
        IsolatedEventType.ON_DATA_SYNC,
        IsolatedEventType.ON_DATA_BACKUP,
        IsolatedEventType.ON_DATA_RESTORE,
        IsolatedEventType.ON_DATA_MIGRATION,
    ],
}


def get_event_types_by_group(group_name: str) -> list:
    """根据分组名称获取事件类型列表"""
    return EVENT_TYPE_GROUPS.get(group_name, [])


def is_event_in_group(event_type: IsolatedEventType, group_name: str) -> bool:
    """检查事件是否属于指定分组"""
    return event_type in EVENT_TYPE_GROUPS.get(group_name, [])


def get_all_event_types() -> list:
    """获取所有事件类型"""
    return list(IsolatedEventType)


def get_high_priority_events() -> list:
    """获取高优先级事件类型"""
    return [event for event in IsolatedEventType if event.event_priority >= 70]


def get_isolation_events() -> list:
    """获取所有隔离相关事件类型"""
    return [event for event in IsolatedEventType if event.is_isolation_event]


def get_lifecycle_events() -> list:
    """获取所有生命周期事件类型"""
    return [event for event in IsolatedEventType if event.is_lifecycle_event]


def get_system_events() -> list:
    """获取所有系统级事件类型"""
    return [event for event in IsolatedEventType if event.is_system_event]


def get_events_requiring_isolation_context() -> list:
    """获取需要隔离上下文的事件类型"""
    return [event for event in IsolatedEventType if event.requires_isolation_context]


# 兼容性别名
OnStartEvent = IsolatedEventType.ON_START
OnStopEvent = IsolatedEventType.ON_STOP

# 设置EventType别名以保持向后兼容
EventType = IsolatedEventType
OnMessageEvent = IsolatedEventType.ON_MESSAGE
OnPlanEvent = IsolatedEventType.ON_PLAN
PostLLMEvent = IsolatedEventType.POST_LLM
AfterLLMEvent = IsolatedEventType.AFTER_LLM
# 暂时注释掉不存在的类型
# PostSendPreProcessEvent = IsolatedEventType.POST_SEND_PRE_PROCESS
# PostSendEvent = IsolatedEventType.POST_SEND
# AfterSendEvent = IsolatedEventType.AFTER_SEND
