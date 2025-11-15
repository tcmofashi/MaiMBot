"""
隔离化消息发送便捷API接口
提供便捷的函数：send_isolated_message(), get_isolated_sender() 等
实现发送状态跟踪和结果回调，提供发送统计和监控功能
"""

import asyncio
import threading
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from functools import wraps

from src.common.logger import get_logger
from src.chat.message_receive.message import MessageSending

# 导入隔离化组件
try:
    from src.isolation.isolation_context import IsolationContext, create_isolation_context
    from .isolated_uni_message_sender import get_isolated_message_sender, get_sender_manager, IsolatedMessageSender
    from .sending_permission_manager import get_sending_permission_manager
    from .sending_config_manager import get_sending_config_manager
    from .uni_message_sender import UniversalMessageSender

    ISOLATION_AVAILABLE = True
except ImportError:
    # 兼容性处理
    class IsolationContext:
        def __init__(self, *args, **kwargs):
            pass

    def create_isolation_context(*args, **kwargs):
        return None

    class IsolatedMessageSender:
        def __init__(self, *args, **kwargs):
            pass

    def get_isolated_message_sender(*args, **kwargs):
        return None

    def get_sender_manager(*args, **kwargs):
        return None

    def get_sending_permission_manager(*args, **kwargs):
        return None

    def get_sending_config_manager(*args, **kwargs):
        return None

    class UniversalMessageSender:
        def __init__(self, *args, **kwargs):
            pass

    ISOLATION_AVAILABLE = False

logger = get_logger("isolated_sending_api")


class SendStatus(Enum):
    """发送状态"""

    PENDING = "pending"  # 待发送
    SENDING = "sending"  # 发送中
    SUCCESS = "success"  # 发送成功
    FAILED = "failed"  # 发送失败
    CANCELLED = "cancelled"  # 已取消
    TIMEOUT = "timeout"  # 超时


@dataclass
class SendResult:
    """发送结果"""

    message_id: str
    tenant_id: str
    platform: str
    status: SendStatus
    success: bool
    error_message: Optional[str] = None
    send_time: Optional[datetime] = None
    complete_time: Optional[datetime] = None
    duration: Optional[float] = None
    retry_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.send_time and self.complete_time:
            self.duration = (self.complete_time - self.send_time).total_seconds()


@dataclass
class SendTask:
    """发送任务"""

    id: str
    message: MessageSending
    tenant_id: str
    platform: str
    priority: int = 0
    max_retries: int = 3
    timeout: float = 30.0
    callback: Optional[Callable[[SendResult], None]] = None
    created_at: datetime = field(default_factory=datetime.now)
    scheduled_at: Optional[datetime] = None
    attempts: int = 0
    last_attempt: Optional[datetime] = None


class IsolatedSendingSystem:
    """隔离化消息发送系统"""

    def __init__(self):
        self._task_queue: asyncio.Queue = asyncio.Queue()
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._completed_tasks: Dict[str, SendResult] = {}
        self._workers: List[asyncio.Task] = []
        self._max_workers = 5
        self._running = False
        self._lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def start(self):
        """启动发送系统"""
        with self._lock:
            if self._running:
                return

            self._running = True
            self._loop = asyncio.new_event_loop()
            threading.Thread(target=self._run_loop, daemon=True).start()
            logger.info("隔离化消息发送系统已启动")

    def stop(self):
        """停止发送系统"""
        with self._lock:
            if not self._running:
                return

            self._running = False
            if self._loop:
                # 取消所有工作任务
                for worker in self._workers:
                    if not worker.done():
                        worker.cancel()

                # 停止事件循环
                self._loop.call_soon_threadsafe(self._loop.stop)
                self._loop = None

            logger.info("隔离化消息发送系统已停止")

    def _run_loop(self):
        """运行事件循环"""
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._start_workers())

    async def _start_workers(self):
        """启动工作线程"""
        self._workers = [asyncio.create_task(self._worker(f"worker-{i}")) for i in range(self._max_workers)]
        logger.info(f"启动了 {self._max_workers} 个发送工作线程")

        # 等待所有工作任务完成
        await asyncio.gather(*self._workers, return_exceptions=True)

    async def _worker(self, name: str):
        """工作任务"""
        logger.debug(f"发送工作线程 {name} 已启动")
        while self._running:
            try:
                # 获取发送任务
                task = await asyncio.wait_for(self._task_queue.get(), timeout=1.0)
                await self._process_task(task)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"发送工作线程 {name} 处理任务时出错: {e}")

        logger.debug(f"发送工作线程 {name} 已停止")

    async def _process_task(self, task: SendTask):
        """处理发送任务"""
        try:
            task.attempts += 1
            task.last_attempt = datetime.now()

            # 获取隔离化发送器
            sender = get_isolated_message_sender(task.tenant_id, task.platform)
            if not sender:
                result = SendResult(
                    message_id=task.id,
                    tenant_id=task.tenant_id,
                    platform=task.platform,
                    status=SendStatus.FAILED,
                    success=False,
                    error_message="无法获取隔离化发送器",
                )
                self._complete_task(task, result)
                return

            # 创建发送结果对象
            result = SendResult(
                message_id=task.id,
                tenant_id=task.tenant_id,
                platform=task.platform,
                status=SendStatus.SENDING,
                success=False,
                send_time=datetime.now(),
            )

            # 执行发送
            try:
                success = await asyncio.wait_for(sender.send_message(task.message), timeout=task.timeout)
                result.status = SendStatus.SUCCESS if success else SendStatus.FAILED
                result.success = success
            except asyncio.TimeoutError:
                result.status = SendStatus.TIMEOUT
                result.success = False
                result.error_message = "发送超时"
            except Exception as e:
                result.status = SendStatus.FAILED
                result.success = False
                result.error_message = str(e)

            result.complete_time = datetime.now()
            result.retry_count = task.attempts - 1

            # 如果失败且可以重试，重新加入队列
            if not result.success and task.attempts < task.max_retries:
                # 计算重试延迟
                delay = min(2**task.attempts, 60)  # 指数退避，最大60秒
                task.scheduled_at = datetime.now().timestamp() + delay

                # 重新加入队列
                await self._task_queue.put(task)
                logger.info(
                    f"任务 {task.id} 发送失败，将在 {delay} 秒后重试 (第 {task.attempts}/{task.max_retries} 次)"
                )
                return

            # 完成任务
            self._complete_task(task, result)

        except Exception as e:
            logger.error(f"处理发送任务 {task.id} 时出错: {e}")
            result = SendResult(
                message_id=task.id,
                tenant_id=task.tenant_id,
                platform=task.platform,
                status=SendStatus.FAILED,
                success=False,
                error_message=f"处理任务出错: {e}",
            )
            self._complete_task(task, result)

    def _complete_task(self, task: SendTask, result: SendResult):
        """完成任务"""
        self._completed_tasks[task.id] = result

        # 调用回调函数
        if task.callback:
            try:
                task.callback(result)
            except Exception as e:
                logger.error(f"执行任务 {task.id} 的回调函数时出错: {e}")

        # 从运行任务中移除
        if task.id in self._running_tasks:
            del self._running_tasks[task.id]

        logger.debug(f"完成发送任务 {task.id}: {result.status.value}")

    def submit_task(self, task: SendTask) -> str:
        """
        提交发送任务

        Args:
            task: 发送任务

        Returns:
            str: 任务ID
        """
        if not self._running:
            logger.warning("发送系统未运行，无法提交任务")
            return ""

        # 异步提交任务
        if self._loop:
            self._loop.call_soon_threadsafe(lambda: asyncio.create_task(self._task_queue.put(task)))
            self._running_tasks[task.id] = None  # 标记为运行中
            logger.debug(f"提交发送任务: {task.id}")
            return task.id

        return ""

    def get_task_result(self, task_id: str) -> Optional[SendResult]:
        """
        获取任务结果

        Args:
            task_id: 任务ID

        Returns:
            Optional[SendResult]: 任务结果
        """
        return self._completed_tasks.get(task_id)

    def cancel_task(self, task_id: str) -> bool:
        """
        取消任务

        Args:
            task_id: 任务ID

        Returns:
            bool: 是否取消成功
        """
        # 如果任务还在运行中，标记为取消
        if task_id in self._running_tasks:
            # 创建取消结果
            result = SendResult(
                message_id=task_id,
                tenant_id="unknown",
                platform="unknown",
                status=SendStatus.CANCELLED,
                success=False,
                error_message="任务被取消",
            )
            self._completed_tasks[task_id] = result
            if task_id in self._running_tasks:
                del self._running_tasks[task_id]
            logger.info(f"取消发送任务: {task_id}")
            return True

        return False

    def get_system_stats(self) -> Dict[str, Any]:
        """获取系统统计"""
        return {
            "running": self._running,
            "active_workers": len([w for w in self._workers if not w.done()]),
            "queued_tasks": self._task_queue.qsize() if self._task_queue else 0,
            "running_tasks": len(self._running_tasks),
            "completed_tasks": len(self._completed_tasks),
            "max_workers": self._max_workers,
        }


# 全局发送系统实例
_sending_system = IsolatedSendingSystem()


def start_sending_system():
    """启动发送系统"""
    _sending_system.start()


def stop_sending_system():
    """停止发送系统"""
    _sending_system.stop()


def get_sending_system() -> IsolatedSendingSystem:
    """获取发送系统实例"""
    return _sending_system


# 便捷函数
async def send_isolated_message(message: MessageSending, tenant_id: str, platform: str, **kwargs) -> bool:
    """
    发送隔离化消息的便捷函数

    Args:
        message: 消息对象
        tenant_id: 租户ID
        platform: 平台标识
        **kwargs: 其他参数

    Returns:
        bool: 是否发送成功
    """
    try:
        sender = get_isolated_message_sender(tenant_id, platform)
        if not sender:
            logger.error(f"无法获取租户 {tenant_id} 平台 {platform} 的隔离化发送器")
            return False

        return await sender.send_message(message, **kwargs)

    except Exception as e:
        logger.error(f"发送隔离化消息失败: {e}")
        return False


def get_isolated_sender(tenant_id: str, platform: str) -> Optional[IsolatedMessageSender]:
    """
    获取隔离化消息发送器的便捷函数

    Args:
        tenant_id: 租户ID
        platform: 平台标识

    Returns:
        Optional[IsolatedMessageSender]: 隔离化消息发送器
    """
    try:
        return get_isolated_message_sender(tenant_id, platform)
    except Exception as e:
        logger.error(f"获取隔离化发送器失败: {e}")
        return None


async def send_isolated_message_async(
    message: MessageSending,
    tenant_id: str,
    platform: str,
    callback: Optional[Callable[[SendResult], None]] = None,
    priority: int = 0,
    max_retries: int = 3,
    timeout: float = 30.0,
) -> str:
    """
    异步发送隔离化消息（带回调）

    Args:
        message: 消息对象
        tenant_id: 租户ID
        platform: 平台标识
        callback: 回调函数
        priority: 优先级
        max_retries: 最大重试次数
        timeout: 超时时间

    Returns:
        str: 任务ID
    """
    if not ISOLATION_AVAILABLE:
        logger.error("隔离功能不可用")
        return ""

    # 启动发送系统（如果未启动）
    if not _sending_system._running:
        start_sending_system()

    # 创建发送任务
    task_id = f"task_{datetime.now().timestamp()}_{hash(str(message))}"
    task = SendTask(
        id=task_id,
        message=message,
        tenant_id=tenant_id,
        platform=platform,
        priority=priority,
        max_retries=max_retries,
        timeout=timeout,
        callback=callback,
    )

    # 提交任务
    return _sending_system.submit_task(task)


def get_send_result(task_id: str) -> Optional[SendResult]:
    """
    获取发送结果

    Args:
        task_id: 任务ID

    Returns:
        Optional[SendResult]: 发送结果
    """
    return _sending_system.get_task_result(task_id)


def cancel_send_task(task_id: str) -> bool:
    """
    取消发送任务

    Args:
        task_id: 任务ID

    Returns:
        bool: 是否取消成功
    """
    return _sending_system.cancel_task(task_id)


async def send_isolated_message_with_result(
    message: MessageSending, tenant_id: str, platform: str, timeout: float = 30.0, **kwargs
) -> SendResult:
    """
    发送隔离化消息并等待结果

    Args:
        message: 消息对象
        tenant_id: 租户ID
        platform: 平台标识
        timeout: 等待超时时间
        **kwargs: 其他参数

    Returns:
        SendResult: 发送结果
    """
    if not ISOLATION_AVAILABLE:
        return SendResult(
            message_id="error",
            tenant_id=tenant_id,
            platform=platform,
            status=SendStatus.FAILED,
            success=False,
            error_message="隔离功能不可用",
        )

    # 使用事件来等待结果
    result_event = asyncio.Event()
    result_container = {"result": None}

    def callback(result: SendResult):
        result_container["result"] = result
        result_event.set()

    # 异步发送
    task_id = await send_isolated_message_async(message, tenant_id, platform, callback=callback, **kwargs)

    if not task_id:
        return SendResult(
            message_id="error",
            tenant_id=tenant_id,
            platform=platform,
            status=SendStatus.FAILED,
            success=False,
            error_message="无法创建发送任务",
        )

    # 等待结果
    try:
        await asyncio.wait_for(result_event.wait(), timeout=timeout)
        return result_container["result"] or SendResult(
            message_id=task_id,
            tenant_id=tenant_id,
            platform=platform,
            status=SendStatus.FAILED,
            success=False,
            error_message="未知错误",
        )
    except asyncio.TimeoutError:
        # 取消任务
        cancel_send_task(task_id)
        return SendResult(
            message_id=task_id,
            tenant_id=tenant_id,
            platform=platform,
            status=SendStatus.TIMEOUT,
            success=False,
            error_message=f"等待超时 ({timeout}秒)",
        )


def get_isolated_sending_stats() -> Dict[str, Any]:
    """
    获取隔离化发送统计信息

    Returns:
        Dict[str, Any]: 统计信息
    """
    if not ISOLATION_AVAILABLE:
        return {"available": False}

    # 获取发送系统统计
    system_stats = _sending_system.get_system_stats()

    # 获取发送器管理器统计
    sender_manager = get_sender_manager()
    if sender_manager:
        manager_stats = sender_manager.get_system_stats()
        system_stats.update(manager_stats)

    # 添加可用性标志
    system_stats["available"] = True

    return system_stats


async def isolated_sending_health_check() -> Dict[str, Any]:
    """
    隔离化发送系统健康检查

    Returns:
        Dict[str, Any]: 健康状态
    """
    if not ISOLATION_AVAILABLE:
        return {"status": "unavailable", "reason": "隔离功能不可用"}

    try:
        # 检查发送系统状态
        system_stats = _sending_system.get_system_stats()

        # 检查发送器管理器
        sender_manager = get_sender_manager()
        manager_health = sender_manager.health_check() if sender_manager else {"status": "unavailable"}

        # 综合健康状态
        overall_status = "healthy"
        issues = []

        if not system_stats["running"]:
            overall_status = "unhealthy"
            issues.append("发送系统未运行")

        if system_stats["active_workers"] == 0:
            overall_status = "unhealthy"
            issues.append("没有活跃的工作线程")

        if manager_health.get("status") != "healthy":
            overall_status = "degraded"
            issues.append(f"发送器管理器状态: {manager_health.get('status')}")

        return {
            "status": overall_status,
            "system_stats": system_stats,
            "manager_health": manager_health,
            "issues": issues,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"健康检查出错: {e}")
        return {"status": "error", "error": str(e), "timestamp": datetime.now().isoformat()}


def cleanup_isolated_sending_resources(tenant_id: Optional[str] = None, platform: Optional[str] = None):
    """
    清理隔离化发送资源

    Args:
        tenant_id: 租户ID（可选）
        platform: 平台标识（可选）

    Returns:
        int: 清理的资源数量
    """
    if not ISOLATION_AVAILABLE:
        return 0

    try:
        cleaned_count = 0

        # 清理发送器管理器中的资源
        sender_manager = get_sender_manager()
        if sender_manager:
            if tenant_id and platform:
                # 清理特定发送器
                if sender_manager.remove_sender(tenant_id, platform):
                    cleaned_count += 1
            elif tenant_id:
                # 清理租户的所有发送器
                cleaned_count += sender_manager.clear_tenant_senders(tenant_id)
            else:
                # 清理所有过期的发送器
                cleaned_count += sender_manager.cleanup_expired_senders()

        # 清理发送系统中的已完成任务
        current_time = datetime.now()
        expired_tasks = []
        for task_id, result in _sending_system._completed_tasks.items():
            if result.complete_time:
                age_hours = (current_time - result.complete_time).total_seconds() / 3600
                if age_hours > 24:  # 24小时前的任务
                    expired_tasks.append(task_id)

        for task_id in expired_tasks:
            del _sending_system._completed_tasks[task_id]
            cleaned_count += 1

        logger.info(f"清理了 {cleaned_count} 个隔离化发送资源")
        return cleaned_count

    except Exception as e:
        logger.error(f"清理隔离化发送资源时出错: {e}")
        return 0


# 装饰器支持
def with_isolated_sending(tenant_id: str, platform: str):
    """
    隔离化发送装饰器

    Args:
        tenant_id: 租户ID
        platform: 平台标识
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 获取隔离化发送器
            sender = get_isolated_sender(tenant_id, platform)
            if not sender:
                logger.error(f"无法获取租户 {tenant_id} 平台 {platform} 的隔离化发送器")
                return False

            # 将发送器注入到函数参数中
            kwargs["isolated_sender"] = sender

            # 执行原函数
            return await func(*args, **kwargs)

        return wrapper

    return decorator


# 兼容性函数（确保向后兼容）
def create_isolated_sender_context(tenant_id: str, platform: str) -> "UniversalMessageSender":
    """
    创建隔离化发送器上下文（兼容性函数）

    Args:
        tenant_id: 租户ID
        platform: 平台标识

    Returns:
        UniversalMessageSender: 带隔离上下文的发送器
    """
    if not ISOLATION_AVAILABLE:
        return UniversalMessageSender()

    try:
        # 创建隔离上下文
        isolation_context = create_isolation_context(tenant_id, "system", platform)

        # 创建通用发送器并设置隔离上下文
        sender = UniversalMessageSender()
        sender.set_isolation_context(isolation_context)

        return sender

    except Exception as e:
        logger.error(f"创建隔离化发送器上下文失败: {e}")
        return UniversalMessageSender()


# 上下文管理器支持
class IsolatedSendingContext:
    """隔离化发送上下文管理器"""

    def __init__(self, tenant_id: str, platform: str):
        self.tenant_id = tenant_id
        self.platform = platform
        self.sender: Optional[IsolatedMessageSender] = None

    async def __aenter__(self):
        self.sender = get_isolated_sender(self.tenant_id, self.platform)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # 清理资源
        if self.sender:
            self.sender.clear_config_cache()

    async def send_message(self, message: MessageSending, **kwargs) -> bool:
        """发送消息"""
        if not self.sender:
            return False
        return await self.sender.send_message(message, **kwargs)

    def get_metrics(self) -> Dict[str, Any]:
        """获取发送指标"""
        if not self.sender:
            return {}
        return self.sender.get_metrics()

    def reset_metrics(self):
        """重置指标"""
        if self.sender:
            self.sender.reset_metrics()
