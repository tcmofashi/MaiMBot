"""
事件系统向后兼容性支持
确保原有的事件系统API能够无缝迁移到新的隔离化架构
"""

from typing import Dict, List, Optional, Tuple, Any

try:
    from typing import TYPE_CHECKING
except ImportError:
    TYPE_CHECKING = False

if TYPE_CHECKING:
    from src.chat.message_receive.message import MessageRecv, MessageSending
    from src.common.data_models.llm_data_model import LLMGenerationDataModel

from src.common.logger import get_logger
from src.isolation.isolation_context import create_isolation_context
from src.plugin_system.base.component_types import EventType, EventHandlerInfo, MaiMessages
from src.plugin_system.core.events_manager import EventsManager
from src.plugin_system.core.isolated_events_manager import get_isolated_events_manager
from src.plugin_system.core.isolated_event_api import publish_isolated_event, subscribe_to_events, get_event_history

logger = get_logger("events_compatibility")


class CompatibleEventsManager(EventsManager):
    """兼容性事件管理器

    继承原有的EventsManager，提供向后兼容的API，
    同时内部使用新的隔离化事件系统
    """

    def __init__(self):
        super().__init__()
        self._default_tenant_id = "default"
        self._default_agent_id = "default"

        # 为向后兼容创建默认的事件管理器
        self._isolated_manager = get_isolated_events_manager(self._default_tenant_id, self._default_agent_id)

    def set_default_isolation(self, tenant_id: str = "default", agent_id: str = "default"):
        """设置默认隔离参数"""
        self._default_tenant_id = tenant_id
        self._default_agent_id = agent_id
        self._isolated_manager = get_isolated_events_manager(tenant_id, agent_id)

    async def handle_mai_events(
        self,
        event_type: EventType,
        message: Optional["MessageRecv | MessageSending"] = None,
        llm_prompt: Optional[str] = None,
        llm_response: Optional["LLMGenerationDataModel"] = None,
        stream_id: Optional[str] = None,
        action_usage: Optional[List[str]] = None,
    ) -> Tuple[bool, Optional[MaiMessages]]:
        """兼容性的事件处理方法

        在保持原有API的同时，使用新的隔离化事件系统
        """
        try:
            # 创建默认隔离上下文
            isolation_context = create_isolation_context(
                tenant_id=self._default_tenant_id, agent_id=self._default_agent_id
            )

            # 如果有消息，尝试从中提取隔离信息
            if message:
                if hasattr(message, "tenant_id"):
                    isolation_context.tenant_id = message.tenant_id
                if hasattr(message, "agent_id"):
                    isolation_context.agent_id = message.agent_id
                if hasattr(message, "platform"):
                    isolation_context.platform = message.platform
                if hasattr(message, "chat_stream") and message.chat_stream:
                    isolation_context.chat_stream_id = message.chat_stream.stream_id

            # 发布隔离化事件
            await publish_isolated_event(
                event_type=event_type,
                data={
                    "message": message,
                    "llm_prompt": llm_prompt,
                    "llm_response": llm_response,
                    "stream_id": stream_id,
                    "action_usage": action_usage,
                },
                tenant_id=isolation_context.tenant_id,
                agent_id=isolation_context.agent_id,
                platform=isolation_context.platform,
                chat_stream_id=isolation_context.chat_stream_id,
            )

            # 使用原有的处理逻辑作为回退
            return await super().handle_mai_events(
                event_type, message, llm_prompt, llm_response, stream_id, action_usage
            )

        except Exception as e:
            logger.warning(f"隔离化事件处理失败，回退到原有系统: {e}")
            # 回退到原有的处理逻辑
            return await super().handle_mai_events(
                event_type, message, llm_prompt, llm_response, stream_id, action_usage
            )

    def register_event_subscriber(self, handler_info: EventHandlerInfo, handler_class: type) -> bool:
        """兼容性的事件处理器注册"""
        try:
            # 使用原有的注册方式
            success = super().register_event_subscriber(handler_info, handler_class)

            if success:
                # 同时注册到隔离化系统
                subscribe_to_events(
                    event_types=[handler_info.event_type],
                    handler=lambda event: self._handle_isolated_event(event, handler_class),
                    tenant_id=self._default_tenant_id,
                    agent_id=self._default_agent_id,
                )

            return success

        except Exception as e:
            logger.error(f"注册兼容性事件处理器失败: {e}")
            return super().register_event_subscriber(handler_info, handler_class)

    async def _handle_isolated_event(self, isolated_event, handler_class):
        """处理隔离化事件的兼容性方法"""
        try:
            # 创建事件处理器实例
            handler_instance = handler_class()

            # 转换隔离化事件为原有格式
            message = isolated_event.data.get("message")
            if message:
                # 使用原有的事件处理逻辑
                await handler_instance.execute(message)

        except Exception as e:
            logger.error(f"处理隔离化事件失败: {e}")


# 创建兼容性包装器
def create_compatible_events_manager() -> CompatibleEventsManager:
    """创建兼容性事件管理器"""
    return CompatibleEventsManager()


# 原有全局变量保持不变
events_manager = CompatibleEventsManager()


def get_events_manager() -> EventsManager:
    """获取事件管理器的兼容性函数"""
    return events_manager


# 便捷函数保持兼容性
async def handle_events(event_type: EventType, **kwargs) -> Tuple[bool, Optional[MaiMessages]]:
    """处理事件的兼容性函数"""
    return await events_manager.handle_mai_events(event_type, **kwargs)


def register_event_handler(handler_info: EventHandlerInfo, handler_class: type) -> bool:
    """注册事件处理器的兼容性函数"""
    return events_manager.register_event_subscriber(handler_info, handler_class)


# 装饰器兼容性
def event_handler_compatible(event_type: EventType, **kwargs):
    """事件处理器装饰器的兼容性版本"""

    def decorator(cls):
        # 创建处理器信息
        handler_info = EventHandlerInfo(
            name=cls.__name__,
            event_type=event_type,
            plugin_name=kwargs.get("plugin_name", ""),
            description=kwargs.get("description", ""),
            **kwargs,
        )

        # 注册处理器
        events_manager.register_event_subscriber(handler_info, cls)
        return cls

    return decorator


# 迁移辅助函数
def migrate_to_isolated_events(tenant_id: str = "default", agent_id: str = "default"):
    """迁移到隔离化事件系统的辅助函数"""
    try:
        # 设置默认隔离参数
        events_manager.set_default_isolation(tenant_id, agent_id)

        logger.info(f"已迁移到隔离化事件系统: 租户={tenant_id}, 智能体={agent_id}")
        return True

    except Exception as e:
        logger.error(f"迁移到隔离化事件系统失败: {e}")
        return False


def check_migration_status() -> Dict[str, Any]:
    """检查迁移状态"""
    return {
        "compatible_manager_active": isinstance(events_manager, CompatibleEventsManager),
        "default_tenant": events_manager._default_tenant_id,
        "default_agent": events_manager._default_agent_id,
        "isolated_manager_active": events_manager._isolated_manager is not None,
    }


# 渐进式迁移支持
class MigrationHelper:
    """迁移辅助类"""

    @staticmethod
    async def test_isolated_events(tenant_id: str, agent_id: str) -> bool:
        """测试隔离化事件系统"""
        try:
            # 发布测试事件
            success = await publish_isolated_event(
                event_type=EventType.ON_START, data={"test": True}, tenant_id=tenant_id, agent_id=agent_id
            )

            if success:
                # 查询测试事件
                history = get_event_history(tenant_id, agent_id, event_type=EventType.ON_START.value)
                return len(history) > 0

            return False

        except Exception as e:
            logger.error(f"测试隔离化事件系统失败: {e}")
            return False

    @staticmethod
    def compare_systems(tenant_id: str, agent_id: str) -> Dict[str, Any]:
        """比较原有系统和隔离化系统的性能"""
        return {
            "legacy_system": {
                "handler_count": len(events_manager._events_subscribers),
                "active_tasks": sum(len(tasks) for tasks in events_manager._handler_tasks.values()),
            },
            "isolated_system": {
                "manager_exists": events_manager._isolated_manager is not None,
                "statistics": events_manager._isolated_manager.get_isolation_info()
                if events_manager._isolated_manager
                else {},
            },
        }

    @staticmethod
    def get_migration_recommendations() -> List[str]:
        """获取迁移建议"""
        recommendations = []

        status = check_migration_status()
        if not status["compatible_manager_active"]:
            recommendations.append("启用兼容性事件管理器")

        if status["default_tenant"] == "default":
            recommendations.append("设置自定义租户ID")

        if status["default_agent"] == "default":
            recommendations.append("设置自定义智能体ID")

        if not status["isolated_manager_active"]:
            recommendations.append("激活隔离化事件管理器")

        if not recommendations:
            recommendations.append("系统已完全迁移到隔离化架构")

        return recommendations


# 自动迁移检查
def auto_migration_check():
    """自动迁移检查"""
    try:
        helper = MigrationHelper()
        recommendations = helper.get_migration_recommendations()

        if recommendations and recommendations != ["系统已完全迁移到隔离化架构"]:
            logger.warning("事件系统迁移建议:")
            for rec in recommendations:
                logger.warning(f"  - {rec}")

        # 如果使用默认参数，建议进行迁移
        status = check_migration_status()
        if status["default_tenant"] == "default" or status["default_agent"] == "default":
            logger.info("建议调用 migrate_to_isolated_events(tenant_id, agent_id) 来完成迁移")

    except Exception as e:
        logger.error(f"自动迁移检查失败: {e}")


# 在模块加载时执行检查
auto_migration_check()


# 导出的兼容性API
__all__ = [
    "CompatibleEventsManager",
    "create_compatible_events_manager",
    "events_manager",
    "get_events_manager",
    "handle_events",
    "register_event_handler",
    "event_handler_compatible",
    "migrate_to_isolated_events",
    "check_migration_status",
    "MigrationHelper",
    "auto_migration_check",
]
