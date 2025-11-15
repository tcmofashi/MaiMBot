"""
隔离化事件类定义
包含隔离上下文的事件对象和事件处理器
"""

import time
import uuid
import hashlib
from typing import Dict, List, Any, Optional, Callable, Union, Set
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from enum import Enum

try:
    from typing import TYPE_CHECKING
except ImportError:
    TYPE_CHECKING = False

if TYPE_CHECKING:
    from src.chat.message_receive.message import MessageRecv, MessageSending

from src.common.logger import get_logger
from src.isolation.isolation_context import IsolationContext, IsolationLevel, IsolationValidator
from src.plugin_system.core.event_types import IsolatedEventType

logger = get_logger("isolated_event")


class EventStatus(Enum):
    """事件状态枚举"""

    PENDING = "pending"  # 等待处理
    PROCESSING = "processing"  # 正在处理
    COMPLETED = "completed"  # 处理完成
    FAILED = "failed"  # 处理失败
    CANCELLED = "cancelled"  # 已取消
    TIMEOUT = "timeout"  # 处理超时


class EventPriority(Enum):
    """事件优先级枚举"""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class EventMetadata:
    """事件元数据"""

    source: str = ""  # 事件源
    tags: Set[str] = field(default_factory=set)  # 事件标签
    retry_count: int = 0  # 重试次数
    max_retries: int = 3  # 最大重试次数
    timeout: Optional[float] = None  # 超时时间（秒）
    correlation_id: Optional[str] = None  # 关联ID
    parent_event_id: Optional[str] = None  # 父事件ID
    trace_id: Optional[str] = None  # 追踪ID


class IsolatedEvent:
    """隔离化事件对象

    包含隔离上下文的事件数据，确保事件处理的多租户隔离
    """

    def __init__(
        self,
        event_type: Union[IsolatedEventType, str],
        data: Dict[str, Any],
        isolation_context: IsolationContext,
        priority: EventPriority = EventPriority.NORMAL,
        metadata: Optional[EventMetadata] = None,
        **kwargs,
    ):
        self.event_type = event_type.value if isinstance(event_type, IsolatedEventType) else event_type
        self.data = data or {}
        self.isolation_context = isolation_context
        self.priority = priority
        self.metadata = metadata or EventMetadata()

        # 事件基本信息
        self.event_id = str(uuid.uuid4())
        self.timestamp = time.time()
        self.status = EventStatus.PENDING

        # 处理相关信息
        self.processed_by: List[str] = []  # 处理器列表
        self.results: List[Any] = []  # 处理结果列表
        self.errors: List[Exception] = []  # 错误列表
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None

        # 更新额外数据
        if kwargs:
            self.data.update(kwargs)

        # 如果没有提供追踪ID，生成一个
        if not self.metadata.trace_id:
            self.metadata.trace_id = self._generate_trace_id()

    def _generate_trace_id(self) -> str:
        """生成追踪ID"""
        content = f"{self.event_id}:{self.timestamp}:{str(self.isolation_context.scope)}"
        return hashlib.md5(content.encode()).hexdigest()[:16]

    def get_scope_key(self) -> str:
        """获取事件的范围键"""
        return str(self.isolation_context.scope)

    def get_isolation_level(self) -> IsolationLevel:
        """获取事件的隔离级别"""
        return self.isolation_context.get_isolation_level()

    def can_be_processed_by(self, handler_context: IsolationContext) -> bool:
        """检查事件是否可以被指定上下文的处理器处理"""
        return IsolationValidator.validate_tenant_access(handler_context, self.isolation_context.tenant_id)

    def should_cross_isolation_boundary(self) -> bool:
        """判断事件是否应该跨越隔离边界"""
        # 某些系统级事件可以跨隔离边界
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
        return self.event_type in cross_boundary_events

    def add_tag(self, tag: str):
        """添加事件标签"""
        self.metadata.tags.add(tag)

    def has_tag(self, tag: str) -> bool:
        """检查是否包含指定标签"""
        return tag in self.metadata.tags

    def set_correlation_id(self, correlation_id: str):
        """设置关联ID"""
        self.metadata.correlation_id = correlation_id

    def set_parent_event(self, parent_event_id: str):
        """设置父事件"""
        self.metadata.parent_event_id = parent_event_id

    def mark_processing_start(self):
        """标记开始处理"""
        self.status = EventStatus.PROCESSING
        self.start_time = time.time()

    def mark_processing_complete(self, result: Any = None):
        """标记处理完成"""
        self.status = EventStatus.COMPLETED
        self.end_time = time.time()
        if result is not None:
            self.results.append(result)

    def mark_processing_failed(self, error: Exception):
        """标记处理失败"""
        self.status = EventStatus.FAILED
        self.end_time = time.time()
        self.errors.append(error)

    def mark_processing_cancelled(self):
        """标记处理取消"""
        self.status = EventStatus.CANCELLED
        self.end_time = time.time()

    def get_processing_duration(self) -> Optional[float]:
        """获取处理时长"""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None

    def add_processor(self, processor_name: str):
        """添加处理器到处理列表"""
        if processor_name not in self.processed_by:
            self.processed_by.append(processor_name)

    def add_result(self, result: Any, processor_name: str):
        """添加处理结果"""
        self.results.append({"processor": processor_name, "result": result, "timestamp": time.time()})

    def add_error(self, error: Exception, processor_name: str):
        """添加错误信息"""
        self.errors.append({"processor": processor_name, "error": error, "timestamp": time.time()})

    def can_retry(self) -> bool:
        """判断是否可以重试"""
        return self.metadata.retry_count < self.metadata.max_retries and self.status in [
            EventStatus.FAILED,
            EventStatus.TIMEOUT,
        ]

    def increment_retry_count(self):
        """增加重试次数"""
        self.metadata.retry_count += 1
        self.status = EventStatus.PENDING

    def is_timeout(self) -> bool:
        """判断是否超时"""
        if not self.metadata.timeout or not self.start_time:
            return False
        return time.time() - self.start_time > self.metadata.timeout

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "data": self.data,
            "isolation_context": {
                "tenant_id": self.isolation_context.tenant_id,
                "agent_id": self.isolation_context.agent_id,
                "platform": self.isolation_context.platform,
                "chat_stream_id": self.isolation_context.chat_stream_id,
            },
            "priority": self.priority.value,
            "status": self.status.value,
            "timestamp": self.timestamp,
            "metadata": {
                "source": self.metadata.source,
                "tags": list(self.metadata.tags),
                "retry_count": self.metadata.retry_count,
                "max_retries": self.metadata.max_retries,
                "timeout": self.metadata.timeout,
                "correlation_id": self.metadata.correlation_id,
                "parent_event_id": self.metadata.parent_event_id,
                "trace_id": self.metadata.trace_id,
            },
            "processed_by": self.processed_by,
            "results_count": len(self.results),
            "errors_count": len(self.errors),
            "processing_duration": self.get_processing_duration(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], isolation_context: IsolationContext) -> "IsolatedEvent":
        """从字典创建事件对象"""
        metadata = EventMetadata(
            source=data.get("metadata", {}).get("source", ""),
            tags=set(data.get("metadata", {}).get("tags", [])),
            retry_count=data.get("metadata", {}).get("retry_count", 0),
            max_retries=data.get("metadata", {}).get("max_retries", 3),
            timeout=data.get("metadata", {}).get("timeout"),
            correlation_id=data.get("metadata", {}).get("correlation_id"),
            parent_event_id=data.get("metadata", {}).get("parent_event_id"),
            trace_id=data.get("metadata", {}).get("trace_id"),
        )

        event = cls(
            event_type=data["event_type"],
            data=data["data"],
            isolation_context=isolation_context,
            priority=EventPriority(data.get("priority", EventPriority.NORMAL.value)),
            metadata=metadata,
        )

        event.event_id = data["event_id"]
        event.timestamp = data["timestamp"]
        event.status = EventStatus(data.get("status", EventStatus.PENDING.value))
        event.processed_by = data.get("processed_by", [])

        return event

    def copy_for_context(self, new_context: IsolationContext) -> "IsolatedEvent":
        """为新的隔离上下文复制事件"""
        new_event = IsolatedEvent(
            event_type=self.event_type,
            data=self.data.copy(),
            isolation_context=new_context,
            priority=self.priority,
            metadata=EventMetadata(
                source=self.metadata.source,
                tags=self.metadata.tags.copy(),
                retry_count=self.metadata.retry_count,
                max_retries=self.metadata.max_retries,
                timeout=self.metadata.timeout,
                correlation_id=self.metadata.correlation_id,
                parent_event_id=self.event_id,  # 设置原事件为父事件
                trace_id=self.metadata.trace_id,
            ),
        )
        return new_event


class IsolatedEventHandler(ABC):
    """隔离化事件处理器抽象基类"""

    def __init__(self, isolation_context: IsolationContext):
        self.isolation_context = isolation_context
        self.handler_id = str(uuid.uuid4())
        self.enabled = True
        self.supported_event_types: Set[str] = set()

    @abstractmethod
    async def handle(self, event: IsolatedEvent) -> Any:
        """处理事件的抽象方法"""
        pass

    def can_handle_event(self, event: IsolatedEvent) -> bool:
        """检查是否可以处理指定事件"""
        if not self.enabled:
            return False

        if not self.can_handle_isolation(event):
            return False

        return event.event_type in self.supported_event_types

    def can_handle_isolation(self, event: IsolatedEvent) -> bool:
        """检查是否可以处理事件的隔离级别"""
        return IsolationValidator.validate_tenant_access(self.isolation_context, event.isolation_context.tenant_id)

    def validate_event_permissions(self, event: IsolatedEvent) -> bool:
        """验证事件处理权限"""
        # 基础权限验证
        if not self.can_handle_isolation(event):
            return False

        # 跨隔离边界验证
        if not event.should_cross_isolation_boundary():
            return (
                self.isolation_context.tenant_id == event.isolation_context.tenant_id
                and self.isolation_context.agent_id == event.isolation_context.agent_id
            )

        return True

    async def safe_handle(self, event: IsolatedEvent) -> Any:
        """安全地处理事件"""
        if not self.validate_event_permissions(event):
            raise PermissionError(f"无权限处理事件 {event.event_id}")

        event.mark_processing_start()
        event.add_processor(self.__class__.__name__)

        try:
            # 检查超时
            if event.is_timeout():
                raise TimeoutError(f"事件处理超时: {event.event_id}")

            # 执行处理逻辑
            result = await self.handle(event)

            event.mark_processing_complete(result)
            event.add_result(result, self.__class__.__name__)

            return result

        except Exception as e:
            event.mark_processing_failed(e)
            event.add_error(e, self.__class__.__name__)

            # 检查是否可以重试
            if event.can_retry():
                event.increment_retry_count()
                logger.warning(f"事件处理失败，准备重试: {event.event_id}, 重试次数: {event.metadata.retry_count}")
                return await self.safe_handle(event)

            logger.error(f"事件处理最终失败: {event.event_id}, 错误: {e}")
            raise

    def enable(self):
        """启用处理器"""
        self.enabled = True

    def disable(self):
        """禁用处理器"""
        self.enabled = False

    def add_supported_event_type(self, event_type: Union[IsolatedEventType, str]):
        """添加支持的事件类型"""
        event_type_str = event_type.value if isinstance(event_type, IsolatedEventType) else event_type
        self.supported_event_types.add(event_type_str)

    def remove_supported_event_type(self, event_type: Union[IsolatedEventType, str]):
        """移除支持的事件类型"""
        event_type_str = event_type.value if isinstance(event_type, IsolatedEventType) else event_type
        self.supported_event_types.discard(event_type_str)

    def get_handler_info(self) -> Dict[str, Any]:
        """获取处理器信息"""
        return {
            "handler_id": self.handler_id,
            "handler_type": self.__class__.__name__,
            "isolation_context": {
                "tenant_id": self.isolation_context.tenant_id,
                "agent_id": self.isolation_context.agent_id,
                "platform": self.isolation_context.platform,
                "chat_stream_id": self.isolation_context.chat_stream_id,
            },
            "enabled": self.enabled,
            "supported_event_types": list(self.supported_event_types),
        }


class EventSubscription:
    """事件订阅信息"""

    def __init__(
        self,
        subscriber_id: str,
        event_types: List[Union[IsolatedEventType, str]],
        isolation_context: IsolationContext,
        handler: Callable[[IsolatedEvent], Any],
        filters: Optional[Dict[str, Any]] = None,
        priority: EventPriority = EventPriority.NORMAL,
    ):
        self.subscription_id = str(uuid.uuid4())
        self.subscriber_id = subscriber_id
        self.event_types = [et.value if isinstance(et, IsolatedEventType) else et for et in event_types]
        self.isolation_context = isolation_context
        self.handler = handler
        self.filters = filters or {}
        self.priority = priority
        self.created_at = time.time()
        self.active = True

    def matches_event(self, event: IsolatedEvent) -> bool:
        """检查订阅是否匹配事件"""
        if not self.active:
            return False

        # 检查事件类型
        if event.event_type not in self.event_types:
            return False

        # 检查隔离权限
        if not self._matches_isolation(event):
            return False

        # 检查过滤器
        if not self._matches_filters(event):
            return False

        return True

    def _matches_isolation(self, event: IsolatedEvent) -> bool:
        """检查隔离匹配"""
        return (
            self.isolation_context.tenant_id == event.isolation_context.tenant_id
            and self.isolation_context.agent_id == event.isolation_context.agent_id
        )

    def _matches_filters(self, event: IsolatedEvent) -> bool:
        """检查过滤器匹配"""
        for key, value in self.filters.items():
            if key == "platform" and value:
                if event.isolation_context.platform != value:
                    return False
            elif key == "tags" and isinstance(value, list):
                if not all(tag in event.metadata.tags for tag in value):
                    return False
            elif key in event.data:
                if event.data[key] != value:
                    return False

        return True

    async def handle_event(self, event: IsolatedEvent) -> Any:
        """处理事件"""
        if not self.matches_event(event):
            return None

        try:
            return await self.handler(event)
        except Exception as e:
            logger.error(f"事件订阅处理失败: {self.subscription_id}, 事件: {event.event_id}, 错误: {e}")
            raise

    def get_subscription_info(self) -> Dict[str, Any]:
        """获取订阅信息"""
        return {
            "subscription_id": self.subscription_id,
            "subscriber_id": self.subscriber_id,
            "event_types": self.event_types,
            "isolation_context": {
                "tenant_id": self.isolation_context.tenant_id,
                "agent_id": self.isolation_context.agent_id,
                "platform": self.isolation_context.platform,
                "chat_stream_id": self.isolation_context.chat_stream_id,
            },
            "filters": self.filters,
            "priority": self.priority.value,
            "created_at": self.created_at,
            "active": self.active,
        }


# 工具函数
def create_isolated_event(
    event_type: Union[IsolatedEventType, str], data: Dict[str, Any], isolation_context: IsolationContext, **kwargs
) -> IsolatedEvent:
    """创建隔离化事件的便捷函数"""
    return IsolatedEvent(event_type, data, isolation_context, **kwargs)


def create_event_subscription(
    subscriber_id: str,
    event_types: List[Union[IsolatedEventType, str]],
    isolation_context: IsolationContext,
    handler: Callable[[IsolatedEvent], Any],
    **kwargs,
) -> EventSubscription:
    """创建事件订阅的便捷函数"""
    return EventSubscription(subscriber_id, event_types, isolation_context, handler, **kwargs)


def create_message_event(
    message: Union["MessageRecv", "MessageSending"],
    isolation_context: IsolationContext,
    event_type: IsolatedEventType = IsolatedEventType.ON_ISOLATED_MESSAGE,
    **kwargs,
) -> IsolatedEvent:
    """创建消息事件的便捷函数"""
    data = {"message": message, "message_type": type(message).__name__, **kwargs}
    return create_isolated_event(event_type, data, isolation_context)


def create_system_event(
    event_type: Union[IsolatedEventType, str],
    isolation_context: IsolationContext,
    data: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> IsolatedEvent:
    """创建系统事件的便捷函数"""
    data = data or {}
    data.update(kwargs)
    return create_isolated_event(event_type, data, isolation_context)
