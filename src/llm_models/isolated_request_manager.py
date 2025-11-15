"""
隔离化请求管理模块

实现支持T+A维度的请求管理，包含优先级队列、配额检查和使用量记录功能。
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from collections import defaultdict, deque
from threading import Lock

from src.common.logger import get_logger
from src.config.api_ada_configs import ModelInfo, TaskConfig
from .payload_content.message import Message
from .payload_content.resp_format import RespFormat
from .payload_content.tool_option import ToolOption
from .model_client.base_client import BaseClient, APIResponse
from .quota_manager import get_quota_manager, QuotaAlertLevel

logger = get_logger("isolated_request_manager")


class RequestPriority(Enum):
    """请求优先级"""

    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class RequestStatus(Enum):
    """请求状态"""

    PENDING = "pending"  # 等待中
    QUEUED = "queued"  # 已排队
    PROCESSING = "processing"  # 处理中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败
    CANCELLED = "cancelled"  # 已取消
    TIMEOUT = "timeout"  # 超时


@dataclass
class IsolatedLLMRequest:
    """隔离化LLM请求"""

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # 隔离信息
    tenant_id: str = ""  # T: 租户隔离
    agent_id: str = ""  # A: 智能体隔离
    platform: str = "default"  # P: 平台隔离
    chat_stream_id: str = None  # C: 聊天流隔离

    # 请求配置
    model_set: TaskConfig = None
    request_type: str = "response"
    priority: RequestPriority = RequestPriority.NORMAL

    # 请求参数
    messages: List[Message] = field(default_factory=list)
    tool_options: List[ToolOption] = field(default_factory=list)
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    response_format: Optional[RespFormat] = None
    embedding_input: Optional[str] = None

    # 配额和限制
    timeout: float = 300.0  # 超时时间（秒）
    retry_on_quota_exceeded: bool = True  # 配额超限时是否重试
    max_retries: int = 3  # 最大重试次数

    # 状态和统计
    status: RequestStatus = RequestStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    queued_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # 结果信息
    response: Optional[APIResponse] = None
    model_info: Optional[ModelInfo] = None
    error: Optional[Exception] = None

    # 重试信息
    retry_count: int = 0
    last_retry_at: Optional[datetime] = None

    # 使用量统计
    tokens_used: int = 0
    cost_incurred: float = 0.0
    execution_time: float = 0.0

    # 回调函数
    completion_callback: Optional[Callable] = None
    progress_callback: Optional[Callable] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "request_id": self.request_id,
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "platform": self.platform,
            "chat_stream_id": self.chat_stream_id,
            "request_type": self.request_type,
            "priority": self.priority.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "queued_at": self.queued_at.isoformat() if self.queued_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "tokens_used": self.tokens_used,
            "cost_incurred": self.cost_incurred,
            "execution_time": self.execution_time,
            "retry_count": self.retry_count,
            "error": str(self.error) if self.error else None,
        }


class IsolatedRequestQueue:
    """隔离化请求队列"""

    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self._queues: Dict[RequestPriority, deque] = {priority: deque() for priority in RequestPriority}
        self._requests: Dict[str, IsolatedLLMRequest] = {}
        self._lock = Lock()

    def put(self, request: IsolatedLLMRequest) -> bool:
        """添加请求到队列"""
        with self._lock:
            if len(self._requests) >= self.max_size:
                logger.warning(f"请求队列已满，拒绝请求: {request.request_id}")
                return False

            request.queued_at = datetime.now()
            request.status = RequestStatus.QUEUED

            self._queues[request.priority].append(request.request_id)
            self._requests[request.request_id] = request

            logger.debug(f"请求入队: {request.request_id}, 优先级: {request.priority.name}")
            return True

    def get(self) -> Optional[IsolatedLLMRequest]:
        """从队列获取最高优先级请求"""
        with self._lock:
            # 按优先级顺序检查队列
            for priority in sorted(RequestPriority, key=lambda x: x.value, reverse=True):
                queue = self._queues[priority]
                if queue:
                    request_id = queue.popleft()
                    request = self._requests.pop(request_id)
                    if request:
                        request.status = RequestStatus.PROCESSING
                        request.started_at = datetime.now()
                        logger.debug(f"请求出队: {request.request_id}, 优先级: {priority.name}")
                        return request
            return None

    def get_by_id(self, request_id: str) -> Optional[IsolatedLLMRequest]:
        """根据ID获取请求"""
        with self._lock:
            return self._requests.get(request_id)

    def cancel(self, request_id: str) -> bool:
        """取消请求"""
        with self._lock:
            request = self._requests.get(request_id)
            if not request:
                return False

            if request.status in [RequestStatus.PENDING, RequestStatus.QUEUED]:
                request.status = RequestStatus.CANCELLED
                request.completed_at = datetime.now()

                # 从队列中移除
                self._queues[request.priority].remove(request_id)
                del self._requests[request_id]

                logger.info(f"请求已取消: {request_id}")
                return True
            return False

    def get_stats(self) -> Dict[str, Any]:
        """获取队列统计"""
        with self._lock:
            return {
                "total_requests": len(self._requests),
                "max_size": self.max_size,
                "queue_sizes": {priority.name: len(queue) for priority, queue in self._queues.items()},
                "status_counts": self._get_status_counts(),
            }

    def _get_status_counts(self) -> Dict[str, int]:
        """获取状态统计"""
        counts = defaultdict(int)
        for request in self._requests.values():
            counts[request.status.value] += 1
        return dict(counts)

    def cleanup_old_requests(self, max_age_hours: int = 24):
        """清理旧请求"""
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)

        with self._lock:
            old_requests = [
                request_id for request_id, request in self._requests.items() if request.created_at < cutoff_time
            ]

            for request_id in old_requests:
                request = self._requests.pop(request_id)
                if request and request.status == RequestStatus.QUEUED:
                    self._queues[request.priority].remove(request_id)

            if old_requests:
                logger.info(f"清理了 {len(old_requests)} 个旧请求")


class IsolatedRequestManager:
    """隔离化请求管理器

    管理多租户环境下的LLM请求，包含优先级队列、配额检查、使用量记录等功能。
    """

    def __init__(self, max_queue_size: int = 10000, max_concurrent_requests: int = 100):
        self.max_queue_size = max_queue_size
        self.max_concurrent_requests = max_concurrent_requests

        # 请求队列
        self._request_queue = IsolatedRequestQueue(max_queue_size)

        # 活跃请求
        self._active_requests: Dict[str, IsolatedLLMRequest] = {}

        # 处理器状态
        self._processing = False
        self._processor_task: Optional[asyncio.Task] = None

        # 配额管理器
        self._quota_manager = get_quota_manager()

        # 统计信息
        self._stats = {
            "total_requests": 0,
            "completed_requests": 0,
            "failed_requests": 0,
            "cancelled_requests": 0,
            "quota_exceeded_requests": 0,
        }

        # 线程安全锁
        self._lock = Lock()

        logger.debug("初始化隔离化请求管理器")

    async def submit_request(
        self,
        tenant_id: str,
        agent_id: str,
        model_set: TaskConfig,
        request_type: str = "response",
        priority: RequestPriority = RequestPriority.NORMAL,
        platform: str = "default",
        chat_stream_id: str = None,
        **kwargs,
    ) -> str:
        """提交请求"""
        request = IsolatedLLMRequest(
            tenant_id=tenant_id,
            agent_id=agent_id,
            platform=platform,
            chat_stream_id=chat_stream_id,
            model_set=model_set,
            request_type=request_type,
            priority=priority,
            **kwargs,
        )

        # 检查配额
        quota_status = self._quota_manager.check_quota(tenant_id, 1000)  # 估算token
        if quota_status == QuotaAlertLevel.EXCEEDED:
            request.status = RequestStatus.FAILED
            request.error = Exception("租户配额已超限")
            request.completed_at = datetime.now()
            self._stats["quota_exceeded_requests"] += 1

            logger.warning(f"请求被拒绝 - 配额超限: 租户={tenant_id}, 请求={request.request_id}")
            return request.request_id

        # 添加到队列
        if self._request_queue.put(request):
            with self._lock:
                self._stats["total_requests"] += 1

            # 启动处理器（如果未运行）
            await self._ensure_processor_running()

            logger.debug(f"请求已提交: {request.request_id}")
            return request.request_id
        else:
            request.status = RequestStatus.FAILED
            request.error = Exception("请求队列已满")
            request.completed_at = datetime.now()

            logger.error(f"请求被拒绝 - 队列已满: {request.request_id}")
            return request.request_id

    async def get_request_status(self, request_id: str) -> Optional[Dict[str, Any]]:
        """获取请求状态"""
        # 先检查活跃请求
        if request_id in self._active_requests:
            return self._active_requests[request_id].to_dict()

        # 再检查队列中的请求
        request = self._request_queue.get_by_id(request_id)
        if request:
            return request.to_dict()

        return None

    async def cancel_request(self, request_id: str) -> bool:
        """取消请求"""
        # 尝试从队列取消
        if self._request_queue.cancel(request_id):
            with self._lock:
                self._stats["cancelled_requests"] += 1
            return True

        # 尝试取消活跃请求（标记为取消，让处理器自然结束）
        if request_id in self._active_requests:
            request = self._active_requests[request_id]
            request.status = RequestStatus.CANCELLED
            logger.info(f"标记活跃请求为取消: {request_id}")
            return True

        return False

    async def get_tenant_requests(
        self, tenant_id: str, status: Optional[RequestStatus] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取租户请求列表"""
        requests = []

        # 收集活跃请求
        for request in self._active_requests.values():
            if request.tenant_id == tenant_id:
                if status is None or request.status == status:
                    requests.append(request.to_dict())

        if len(requests) < limit:
            # 这里简化处理，实际可以从队列获取详细信息
            pass

        return requests[:limit]

    def get_manager_stats(self) -> Dict[str, Any]:
        """获取管理器统计"""
        with self._lock:
            stats = dict(self._stats)
            stats.update(
                {
                    "queue_stats": self._request_queue.get_stats(),
                    "active_requests": len(self._active_requests),
                    "processing": self._processing,
                    "max_concurrent_requests": self.max_concurrent_requests,
                }
            )
            return stats

    async def _ensure_processor_running(self):
        """确保处理器运行"""
        if not self._processing or (self._processor_task and self._processor_task.done()):
            self._processing = True
            self._processor_task = asyncio.create_task(self._process_requests())
            logger.debug("启动请求处理器")

    async def _process_requests(self):
        """处理请求"""
        logger.info("请求处理器启动")

        try:
            while self._processing:
                # 检查并发限制
                if len(self._active_requests) >= self.max_concurrent_requests:
                    await asyncio.sleep(0.1)
                    continue

                # 获取下一个请求
                request = self._request_queue.get()
                if not request:
                    await asyncio.sleep(0.1)
                    continue

                # 处理请求
                asyncio.create_task(self._execute_request(request))

        except Exception as e:
            logger.error(f"请求处理器异常: {e}")
        finally:
            self._processing = False
            logger.info("请求处理器停止")

    async def _execute_request(self, request: IsolatedLLMRequest):
        """执行单个请求"""
        request_id = request.request_id

        try:
            # 添加到活跃请求
            self._active_requests[request_id] = request

            logger.debug(f"开始执行请求: {request_id}")

            # 创建隔离化LLM客户端
            from .isolated_llm_client import get_isolated_llm_client

            client = get_isolated_llm_client(tenant_id=request.tenant_id, agent_id=request.agent_id)

            # 执行请求
            if request.request_type == "response":
                # 构建消息工厂函数
                def message_factory(client_instance: BaseClient) -> List[Message]:
                    return request.messages

                response, model_info = await client._execute_isolated_request(
                    request=request,
                    message_factory=message_factory,
                    tool_options=request.tool_options or None,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                )
            elif request.request_type == "embedding":
                response, model_info = await client._execute_isolated_request(
                    request=request, embedding_input=request.embedding_input
                )
            else:
                raise ValueError(f"不支持的请求类型: {request.request_type}")

            # 更新请求结果
            request.response = response
            request.model_info = model_info
            request.status = RequestStatus.COMPLETED
            request.completed_at = datetime.now()

            # 更新使用量统计
            if response.usage:
                request.tokens_used = response.usage.total_tokens
                request.execution_time = (request.completed_at - request.started_at).total_seconds()

                # 计算费用
                if model_info:
                    input_cost = (response.usage.prompt_tokens / 1000000) * model_info.price_in
                    output_cost = (response.usage.completion_tokens / 1000000) * model_info.price_out
                    request.cost_incurred = round(input_cost + output_cost, 6)

            # 调用完成回调
            if request.completion_callback:
                try:
                    await request.completion_callback(request)
                except Exception as e:
                    logger.error(f"请求完成回调失败: {e}")

            with self._lock:
                self._stats["completed_requests"] += 1

            logger.debug(f"请求执行完成: {request_id}")

        except Exception as e:
            request.error = e
            request.status = RequestStatus.FAILED
            request.completed_at = datetime.now()

            with self._lock:
                self._stats["failed_requests"] += 1

            logger.error(f"请求执行失败: {request_id}, 错误: {e}")

        finally:
            # 从活跃请求移除
            if request_id in self._active_requests:
                del self._active_requests[request_id]

    def stop_processor(self):
        """停止处理器"""
        self._processing = False
        if self._processor_task:
            self._processor_task.cancel()
        logger.info("请求处理器停止信号已发送")

    def cleanup_old_requests(self, max_age_hours: int = 24):
        """清理旧请求"""
        self._request_queue.cleanup_old_requests(max_age_hours)

        # 清理活跃请求中的已完成请求
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        old_requests = [
            request_id
            for request_id, request in self._active_requests.items()
            if request.completed_at and request.completed_at < cutoff_time
        ]

        for request_id in old_requests:
            del self._active_requests[request_id]

        if old_requests:
            logger.info(f"清理了 {len(old_requests)} 个旧活跃请求")


# 全局请求管理器实例
_request_manager = IsolatedRequestManager()


def get_request_manager() -> IsolatedRequestManager:
    """获取全局请求管理器"""
    return _request_manager


async def submit_isolated_request(
    tenant_id: str,
    agent_id: str,
    model_set: TaskConfig,
    request_type: str = "response",
    priority: RequestPriority = RequestPriority.NORMAL,
    **kwargs,
) -> str:
    """提交隔离化请求（便捷函数）"""
    return await _request_manager.submit_request(
        tenant_id=tenant_id,
        agent_id=agent_id,
        model_set=model_set,
        request_type=request_type,
        priority=priority,
        **kwargs,
    )


async def get_request_info(request_id: str) -> Optional[Dict[str, Any]]:
    """获取请求信息（便捷函数）"""
    return await _request_manager.get_request_status(request_id)


async def cancel_isolated_request(request_id: str) -> bool:
    """取消隔离化请求（便捷函数）"""
    return await _request_manager.cancel_request(request_id)


def get_request_stats() -> Dict[str, Any]:
    """获取请求统计（便捷函数）"""
    return _request_manager.get_manager_stats()
