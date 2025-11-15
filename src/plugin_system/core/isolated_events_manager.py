"""
多租户隔离事件管理器
支持T+A+C+P四维隔离的事件处理系统，确保不同租户、智能体、平台和聊天流的事件处理相互隔离
"""

import asyncio
import contextlib
import hashlib
import threading
import time
import weakref
from typing import List, Dict, Optional, Type, Tuple, Any
from dataclasses import dataclass, field

try:
    from typing import TYPE_CHECKING
except ImportError:
    TYPE_CHECKING = False

if TYPE_CHECKING:
    from src.common.data_models.llm_data_model import LLMGenerationDataModel

from src.chat.message_receive.message import MessageRecv, MessageSending
from src.common.logger import get_logger
from src.plugin_system.base.component_types import EventType, EventHandlerInfo, MaiMessages, CustomEventHandlerResult
from src.plugin_system.base.base_events_handler import BaseEventHandler
from src.isolation.isolation_context import IsolationContext

logger = get_logger("isolated_events_manager")


@dataclass
class IsolatedEventHandler:
    """隔离化事件处理器包装"""

    handler: BaseEventHandler
    isolation_context: IsolationContext
    subscribed_at: float = field(default_factory=time.time)

    def __post_init__(self):
        self.handler.set_isolation_context(self.isolation_context)

    def validate_access(self, event_context: IsolationContext) -> bool:
        """验证是否有权限处理该事件"""
        return (
            self.isolation_context.tenant_id == event_context.tenant_id
            and self.isolation_context.agent_id == event_context.agent_id
        )

    def can_handle_event(
        self, event_type: str, platform: Optional[str] = None, chat_stream_id: Optional[str] = None
    ) -> bool:
        """检查是否可以处理指定事件"""
        # 基础事件类型匹配
        if str(self.handler.event_type) != event_type:
            return False

        # 平台过滤
        if platform and self.isolation_context.platform and self.isolation_context.platform != platform:
            return False

        # 聊天流过滤
        if (
            chat_stream_id
            and self.isolation_context.chat_stream_id
            and self.isolation_context.chat_stream_id != chat_stream_id
        ):
            return False

        return True


@dataclass
class IsolatedEvent:
    """隔离化事件对象"""

    event_type: str
    data: Dict[str, Any]
    isolation_context: IsolationContext
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default="")

    def __post_init__(self):
        if not self.event_id:
            # 生成唯一的事件ID
            scope_str = str(self.isolation_context.scope)
            content = f"{scope_str}:{self.event_type}:{self.timestamp}"
            self.event_id = hashlib.md5(content.encode()).hexdigest()[:16]

    def get_scope_key(self) -> str:
        """获取事件的范围键"""
        return str(self.isolation_context.scope)

    def copy_for_context(self, new_context: IsolationContext) -> "IsolatedEvent":
        """为新的隔离上下文复制事件"""
        return IsolatedEvent(
            event_type=self.event_type,
            data=self.data.copy(),
            isolation_context=new_context,
            timestamp=self.timestamp,
            event_id=self.event_id,
        )


class IsolatedEventsManager:
    """隔离化事件管理器

    支持T+A+C+P四维隔离的事件处理系统
    每个租户+智能体组合拥有独立的事件处理器和事件历史
    """

    def __init__(self, tenant_id: str, agent_id: str):
        self.tenant_id = tenant_id
        self.agent_id = agent_id

        # 创建基础隔离上下文
        self.isolation_context = IsolationContext(tenant_id, agent_id)

        # 事件处理器存储：按事件类型和隔离范围组织
        self._event_handlers: Dict[str, Dict[str, List[IsolatedEventHandler]]] = {}

        # 事件处理器映射表
        self._handler_mapping: Dict[str, Type[BaseEventHandler]] = {}

        # 正在处理的任务
        self._handler_tasks: Dict[str, List[asyncio.Task]] = {}

        # 事件结果历史记录：按隔离范围存储
        self._events_result_history: Dict[str, Dict[str, List[CustomEventHandlerResult]]] = {}

        # 历史记录启用映射
        self._history_enable_map: Dict[str, bool] = {}

        # 线程安全锁
        self._lock = threading.RLock()

        # 初始化基础事件类型
        self._register_base_events()

    def _register_base_events(self):
        """注册基础事件类型"""
        for event in EventType:
            self.register_event(str(event.value), enable_history_result=False)

    def _get_scope_key(self, platform: Optional[str] = None, chat_stream_id: Optional[str] = None) -> str:
        """生成隔离范围键"""
        if chat_stream_id:
            return f"{self.tenant_id}:{self.agent_id}:{platform or '*'}:{chat_stream_id}"
        elif platform:
            return f"{self.tenant_id}:{self.agent_id}:{platform}:*"
        else:
            return f"{self.tenant_id}:{self.agent_id}:*:*"

    def register_event(self, event_type: str, enable_history_result: bool = False):
        """注册事件类型"""
        with self._lock:
            if event_type not in self._event_handlers:
                self._event_handlers[event_type] = {}
                self._history_enable_map[event_type] = enable_history_result
                if enable_history_result:
                    self._events_result_history[event_type] = {}

    def register_event_subscriber(
        self,
        handler_info: EventHandlerInfo,
        handler_class: Type[BaseEventHandler],
        platform: Optional[str] = None,
        chat_stream_id: Optional[str] = None,
    ) -> bool:
        """注册事件处理器"""
        if not issubclass(handler_class, BaseEventHandler):
            logger.error(f"类 {handler_class.__name__} 不是 BaseEventHandler 的子类")
            return False

        handler_name = handler_info.name

        with self._lock:
            if handler_name in self._handler_mapping:
                logger.warning(f"事件处理器 {handler_name} 已存在，跳过注册")
                return False

            event_type_str = str(handler_info.event_type)
            if event_type_str not in self._history_enable_map:
                logger.error(f"事件类型 {event_type_str} 未注册，无法为其注册处理器 {handler_name}")
                return False

            # 创建隔离化事件处理器
            scope_context = IsolationContext(
                tenant_id=self.tenant_id, agent_id=self.agent_id, platform=platform, chat_stream_id=chat_stream_id
            )

            isolated_handler = IsolatedEventHandler(handler=handler_class(), isolation_context=scope_context)

            # 设置插件名称
            isolated_handler.handler.set_plugin_name(handler_info.plugin_name or "unknown")

            # 存储处理器
            scope_key = self._get_scope_key(platform, chat_stream_id)
            if scope_key not in self._event_handlers[event_type_str]:
                self._event_handlers[event_type_str][scope_key] = []

            self._event_handlers[event_type_str][scope_key].append(isolated_handler)

            # 按权重排序
            self._event_handlers[event_type_str][scope_key].sort(key=lambda x: x.handler.weight, reverse=True)

            # 记录映射关系
            self._handler_mapping[handler_name] = handler_class

            logger.info(f"已注册隔离化事件处理器 {handler_name} 到范围 {scope_key}")
            return True

    async def handle_isolated_events(
        self,
        event_type: EventType,
        isolation_context: IsolationContext,
        message: Optional[MessageRecv | MessageSending] = None,
        llm_prompt: Optional[str] = None,
        llm_response: Optional["LLMGenerationDataModel"] = None,
        stream_id: Optional[str] = None,
        action_usage: Optional[List[str]] = None,
        **kwargs,
    ) -> Tuple[bool, Optional[MaiMessages]]:
        """处理隔离化事件"""
        from src.plugin_system.core import component_registry

        # 验证隔离权限
        if not self._validate_isolation_access(isolation_context):
            logger.warning(f"事件处理权限验证失败: {isolation_context.scope}")
            return True, None

        event_type_str = str(event_type.value)
        continue_flag = True

        # 准备消息
        transformed_message = self._prepare_message(
            event_type, isolation_context, message, llm_prompt, llm_response, stream_id, action_usage
        )
        if transformed_message:
            transformed_message = transformed_message.deepcopy()

        # 获取相关的事件处理器
        relevant_handlers = self._get_relevant_handlers(event_type_str, isolation_context)

        if not relevant_handlers:
            return True, None

        current_stream_id = transformed_message.stream_id if transformed_message else None
        modified_message: Optional[MaiMessages] = None

        for isolated_handler in relevant_handlers:
            # 前置检查
            if current_stream_id and self._is_handler_disabled(
                current_stream_id, isolated_handler.handler.handler_name
            ):
                continue

            # 加载插件配置
            plugin_config = component_registry.get_plugin_config(isolated_handler.handler.plugin_name) or {}
            isolated_handler.handler.set_plugin_config(plugin_config)

            # 分发任务
            if isolated_handler.handler.intercept_message or event_type == EventType.ON_STOP:
                # 阻塞执行
                should_continue, modified_message = await self._dispatch_intercepting_handler_task(
                    isolated_handler, event_type_str, modified_message or transformed_message
                )
                continue_flag = continue_flag and should_continue
            else:
                # 异步执行
                self._dispatch_handler_task(isolated_handler, event_type_str, transformed_message)

        return continue_flag, modified_message

    def _validate_isolation_access(self, context: IsolationContext) -> bool:
        """验证隔离访问权限"""
        return context.tenant_id == self.tenant_id and context.agent_id == self.agent_id

    def _get_relevant_handlers(self, event_type: str, context: IsolationContext) -> List[IsolatedEventHandler]:
        """获取相关的事件处理器"""
        relevant_handlers = []

        # 精确匹配
        exact_scope = self._get_scope_key(context.platform, context.chat_stream_id)
        if exact_scope in self._event_handlers.get(event_type, {}):
            relevant_handlers.extend(self._event_handlers[event_type][exact_scope])

        # 平台级别匹配
        if context.platform:
            platform_scope = self._get_scope_key(context.platform, None)
            if platform_scope in self._event_handlers.get(event_type, {}):
                relevant_handlers.extend(self._event_handlers[event_type][platform_scope])

        # 租户级别匹配
        tenant_scope = self._get_scope_key()
        if tenant_scope in self._event_handlers.get(event_type, {}):
            relevant_handlers.extend(self._event_handlers[event_type][tenant_scope])

        return relevant_handlers

    def _is_handler_disabled(self, stream_id: str, handler_name: str) -> bool:
        """检查处理器是否被禁用"""
        # 这里可以集成全局公告管理器的逻辑
        return False

    def _prepare_message(
        self,
        event_type: EventType,
        isolation_context: IsolationContext,
        message: Optional[MessageRecv | MessageSending] = None,
        llm_prompt: Optional[str] = None,
        llm_response: Optional["LLMGenerationDataModel"] = None,
        stream_id: Optional[str] = None,
        action_usage: Optional[List[str]] = None,
    ) -> Optional[MaiMessages]:
        """准备和转换消息对象"""
        # 实现消息转换逻辑（复用原有逻辑）
        if message:
            return self._transform_event_message(message, llm_prompt, llm_response)

        if event_type not in [EventType.ON_START, EventType.ON_STOP]:
            assert stream_id, "如果没有消息，必须为非启动/关闭事件提供流ID"
            # 这里可以添加从stream_id获取消息的逻辑
            pass

        return None

    def _transform_event_message(
        self,
        message: MessageRecv | MessageSending,
        llm_prompt: Optional[str] = None,
        llm_response: Optional["LLMGenerationDataModel"] = None,
    ) -> MaiMessages:
        """转换事件消息格式（复用原有逻辑）"""
        # 这里实现消息转换逻辑，参考原有实现
        # 为了简化，这里返回一个基本的MaiMessages对象
        return MaiMessages(
            raw_message=getattr(message, "raw_message", ""),
            plain_text=getattr(message, "processed_plain_text", ""),
        )

    def _dispatch_handler_task(
        self, isolated_handler: IsolatedEventHandler, event_type: str, message: Optional[MaiMessages] = None
    ):
        """分发非阻塞事件处理任务"""
        try:
            task = asyncio.create_task(isolated_handler.handler.execute(message))

            task_name = f"{isolated_handler.handler.plugin_name}-{isolated_handler.handler.handler_name}"
            task.set_name(task_name)
            task.add_done_callback(lambda t: self._task_done_callback(t, event_type, isolated_handler))

            self._handler_tasks.setdefault(isolated_handler.handler.handler_name, []).append(task)
        except Exception as e:
            logger.error(
                f"创建隔离化事件处理任务 {isolated_handler.handler.handler_name} 时发生异常: {e}", exc_info=True
            )

    async def _dispatch_intercepting_handler_task(
        self, isolated_handler: IsolatedEventHandler, event_type: str, message: Optional[MaiMessages] = None
    ) -> Tuple[bool, Optional[MaiMessages]]:
        """分发并等待阻塞事件处理器"""
        try:
            result = await isolated_handler.handler.execute(message)

            expected_fields = ["success", "continue_processing", "return_message", "custom_result", "modified_message"]

            if not isinstance(result, tuple) or len(result) != 5:
                if isinstance(result, tuple):
                    annotated = ", ".join(f"{name}={val!r}" for name, val in zip(expected_fields, result, strict=True))
                    actual_desc = f"{len(result)} 个元素 ({annotated})"
                else:
                    actual_desc = f"非 tuple 类型: {type(result)}"

                logger.error(
                    f"[{self.__class__.__name__}] 隔离化EventHandler {isolated_handler.handler.handler_name} 返回值不符合预期:\n"
                    f"  模块来源: {isolated_handler.handler.__class__.__module__}.{isolated_handler.handler.__class__.__name__}\n"
                    f"  期望: 5 个元素 ({', '.join(expected_fields)})\n"
                    f"  实际: {actual_desc}"
                )
                return True, None

            success, continue_processing, return_message, custom_result, modified_message = result

            if not success:
                logger.error(f"隔离化EventHandler {isolated_handler.handler.handler_name} 执行失败: {return_message}")
            else:
                logger.debug(f"隔离化EventHandler {isolated_handler.handler.handler_name} 执行成功: {return_message}")

            # 存储历史结果
            if self._history_enable_map.get(event_type, False) and custom_result:
                scope_key = str(isolated_handler.isolation_context.scope)
                if scope_key not in self._events_result_history[event_type]:
                    self._events_result_history[event_type][scope_key] = []
                self._events_result_history[event_type][scope_key].append(custom_result)

            return continue_processing, modified_message

        except Exception as e:
            logger.error(f"隔离化EventHandler {isolated_handler.handler.handler_name} 发生异常: {e}", exc_info=True)
            return True, None

    def _task_done_callback(self, task: asyncio.Task, event_type: str, isolated_handler: IsolatedEventHandler):
        """任务完成回调"""
        task_name = task.get_name() or "Unknown Task"
        try:
            success, _, result, custom_result, _ = task.result()
            if success:
                logger.debug(f"隔离化事件处理任务 {task_name} 已成功完成: {result}")
            else:
                logger.error(f"隔离化事件处理任务 {task_name} 执行失败: {result}")

            # 存储历史结果
            if self._history_enable_map.get(event_type, False) and custom_result:
                scope_key = str(isolated_handler.isolation_context.scope)
                if scope_key not in self._events_result_history[event_type]:
                    self._events_result_history[event_type][scope_key] = []
                self._events_result_history[event_type][scope_key].append(custom_result)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"隔离化事件处理任务 {task_name} 发生异常: {e}")
        finally:
            with contextlib.suppress(ValueError, KeyError):
                if isolated_handler.handler.handler_name in self._handler_tasks:
                    self._handler_tasks[isolated_handler.handler.handler_name].remove(task)

    async def cancel_handler_tasks(self, handler_name: str) -> None:
        """取消事件处理器的所有任务"""
        tasks_to_be_cancelled = self._handler_tasks.get(handler_name, [])
        if remaining_tasks := [task for task in tasks_to_be_cancelled if not task.done()]:
            for task in remaining_tasks:
                task.cancel()
            try:
                await asyncio.wait_for(asyncio.gather(*remaining_tasks, return_exceptions=True), timeout=5)
                logger.info(f"已取消隔离化事件处理器 {handler_name} 的所有任务")
            except asyncio.TimeoutError:
                logger.warning(f"取消隔离化事件处理器 {handler_name} 的任务超时，开始强制取消")
            except Exception as e:
                logger.error(f"取消隔离化事件处理器 {handler_name} 的任务时发生异常: {e}")

        if handler_name in self._handler_tasks:
            del self._handler_tasks[handler_name]

    async def get_event_result_history(
        self, event_type: str, platform: Optional[str] = None, chat_stream_id: Optional[str] = None
    ) -> List[CustomEventHandlerResult]:
        """获取事件结果历史记录"""
        if event_type not in self._history_enable_map:
            raise ValueError(f"事件类型 {event_type} 未注册")

        if not self._history_enable_map[event_type]:
            raise ValueError(f"事件类型 {event_type} 的历史记录未启用")

        scope_key = self._get_scope_key(platform, chat_stream_id)
        return self._events_result_history.get(event_type, {}).get(scope_key, [])

    async def clear_event_result_history(
        self, event_type: str, platform: Optional[str] = None, chat_stream_id: Optional[str] = None
    ) -> None:
        """清空事件结果历史记录"""
        if event_type not in self._history_enable_map:
            raise ValueError(f"事件类型 {event_type} 未注册")

        if not self._history_enable_map[event_type]:
            raise ValueError(f"事件类型 {event_type} 的历史记录未启用")

        scope_key = self._get_scope_key(platform, chat_stream_id)
        if event_type in self._events_result_history and scope_key in self._events_result_history[event_type]:
            self._events_result_history[event_type][scope_key] = []

    def get_handler_count(self, event_type: str = None) -> int:
        """获取处理器数量"""
        if event_type:
            return sum(len(handlers) for handlers in self._event_handlers.get(event_type, {}).values())
        else:
            return sum(
                sum(len(handlers) for handlers in event_handlers.values())
                for event_handlers in self._event_handlers.values()
            )

    def get_isolation_info(self) -> Dict[str, Any]:
        """获取隔离信息"""
        return {
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "registered_events": list(self._history_enable_map.keys()),
            "handler_count": self.get_handler_count(),
            "active_tasks": sum(len(tasks) for tasks in self._handler_tasks.values()),
        }


class IsolatedEventsManagerManager:
    """隔离化事件管理器管理器

    管理所有租户+智能体组合的事件管理器实例
    """

    def __init__(self):
        self._managers: Dict[str, IsolatedEventsManager] = {}
        self._lock = threading.RLock()
        self._weak_refs: Dict[str, weakref.ref] = {}

    def _get_manager_key(self, tenant_id: str, agent_id: str) -> str:
        """生成管理器键"""
        return f"{tenant_id}:{agent_id}"

    def get_isolated_events_manager(self, tenant_id: str, agent_id: str) -> IsolatedEventsManager:
        """获取隔离化事件管理器实例"""
        manager_key = self._get_manager_key(tenant_id, agent_id)

        with self._lock:
            # 检查弱引用
            if manager_key in self._weak_refs:
                manager_ref = self._weak_refs[manager_key]
                manager = manager_ref()
                if manager is not None:
                    return manager

            # 创建新管理器
            manager = IsolatedEventsManager(tenant_id, agent_id)
            self._weak_refs[manager_key] = weakref.ref(manager)

            logger.info(f"创建隔离化事件管理器: {manager_key}")
            return manager

    def clear_tenant_managers(self, tenant_id: str):
        """清理指定租户的所有事件管理器"""
        with self._lock:
            keys_to_remove = []
            for key in self._weak_refs.keys():
                if key.startswith(f"{tenant_id}:"):
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                del self._weak_refs[key]

            logger.info(f"已清理租户 {tenant_id} 的所有事件管理器")

    def cleanup_expired_managers(self):
        """清理过期的事件管理器引用"""
        with self._lock:
            expired_keys = []
            for key, ref in self._weak_refs.items():
                if ref() is None:
                    expired_keys.append(key)

            for key in expired_keys:
                del self._weak_refs[key]

    def get_manager_stats(self) -> Dict[str, Any]:
        """获取管理器统计信息"""
        self.cleanup_expired_managers()

        stats = {}
        with self._lock:
            for key, ref in self._weak_refs.items():
                manager = ref()
                if manager:
                    stats[key] = manager.get_isolation_info()

        return stats

    async def shutdown_all_managers(self):
        """关闭所有事件管理器"""
        with self._lock:
            for _key, ref in self._weak_refs.items():
                manager = ref()
                if manager:
                    # 取消所有任务
                    for handler_name in list(manager._handler_tasks.keys()):
                        await manager.cancel_handler_tasks(handler_name)

            self._weak_refs.clear()
            logger.info("已关闭所有隔离化事件管理器")


# 全局管理器实例
_global_events_manager_manager = IsolatedEventsManagerManager()


def get_isolated_events_manager(tenant_id: str, agent_id: str) -> IsolatedEventsManager:
    """获取隔离化事件管理器的便捷函数"""
    return _global_events_manager_manager.get_isolated_events_manager(tenant_id, agent_id)


def clear_isolated_events_manager(tenant_id: str, agent_id: Optional[str] = None):
    """清理隔离化事件管理器"""
    if agent_id:
        manager_key = f"{tenant_id}:{agent_id}"
        with _global_events_manager_manager._lock:
            if manager_key in _global_events_manager_manager._weak_refs:
                del _global_events_manager_manager._weak_refs[manager_key]
    else:
        _global_events_manager_manager.clear_tenant_managers(tenant_id)


def get_events_manager_stats() -> Dict[str, Any]:
    """获取事件管理器统计信息"""
    return _global_events_manager_manager.get_manager_stats()


async def shutdown_all_events_managers():
    """关闭所有事件管理器"""
    await _global_events_manager_manager.shutdown_all_managers()
