"""
隔离化的LLM客户端模块

实现支持T+A维度隔离的LLM客户端，提供租户级别的配额管理和计费功能。
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any, Set, Callable, TYPE_CHECKING
from threading import Lock

if TYPE_CHECKING:
    from .quota_manager import IsolatedQuotaManager

from src.common.logger import get_logger
from src.config.api_ada_configs import ModelInfo, APIProvider, TaskConfig
from src.isolation.isolation_context import IsolationContext, create_isolation_context
from .payload_content.message import Message, MessageBuilder
from .payload_content.tool_option import ToolOption
from .model_client.base_client import BaseClient, APIResponse, UsageRecord, client_registry
from .utils_model import RequestType
from .exceptions import (
    NetworkConnectionError,
    RespNotOkException,
    EmptyResponseException,
    ModelAttemptFailed,
)

logger = get_logger("isolated_llm_client")


class QuotaExceededError(Exception):
    """配额超限异常"""

    pass


class TenantQuotaStatus(Enum):
    """租户配额状态"""

    ACTIVE = "active"  # 正常
    WARNING = "warning"  # 警告（接近限额）
    EXCEEDED = "exceeded"  # 超限
    SUSPENDED = "suspended"  # 暂停


@dataclass
class TenantQuota:
    """租户配额配置"""

    tenant_id: str
    daily_token_limit: int = 1000000  # 每日token限制
    monthly_cost_limit: float = 100.0  # 每月费用限制
    daily_request_limit: int = 10000  # 每日请求次数限制
    warning_threshold: float = 0.8  # 警告阈值（80%）

    # 统计信息
    daily_tokens_used: int = 0
    daily_requests_used: int = 0
    monthly_cost_used: float = 0.0
    last_reset_date: datetime = field(default_factory=datetime.now)

    def reset_daily_usage(self):
        """重置每日使用量"""
        today = datetime.now().date()
        if self.last_reset_date.date() < today:
            self.daily_tokens_used = 0
            self.daily_requests_used = 0
            self.last_reset_date = datetime.now()

    def check_quota(self, tokens_needed: int) -> TenantQuotaStatus:
        """检查配额状态"""
        self.reset_daily_usage()

        # 检查每日token限制
        token_usage_ratio = self.daily_tokens_used / self.daily_token_limit if self.daily_token_limit > 0 else 0
        if self.daily_tokens_used + tokens_needed > self.daily_token_limit:
            return TenantQuotaStatus.EXCEEDED

        # 检查每月费用限制
        cost_usage_ratio = self.monthly_cost_used / self.monthly_cost_limit if self.monthly_cost_limit > 0 else 0
        if self.monthly_cost_used > self.monthly_cost_limit:
            return TenantQuotaStatus.EXCEEDED

        # 检查每日请求限制
        request_usage_ratio = self.daily_requests_used / self.daily_request_limit if self.daily_request_limit > 0 else 0
        if self.daily_requests_used >= self.daily_request_limit:
            return TenantQuotaStatus.EXCEEDED

        # 检查是否达到警告阈值
        max_ratio = max(token_usage_ratio, cost_usage_ratio, request_usage_ratio)
        if max_ratio >= self.warning_threshold:
            return TenantQuotaStatus.WARNING

        return TenantQuotaStatus.ACTIVE

    def record_usage(self, tokens_used: int, cost_incurred: float):
        """记录使用量"""
        self.reset_daily_usage()
        self.daily_tokens_used += tokens_used
        self.daily_requests_used += 1
        self.monthly_cost_used += cost_incurred


@dataclass
class IsolatedLLMRequest:
    """隔离化的LLM请求"""

    model_set: TaskConfig
    request_type: str
    tenant_id: str  # T: 租户隔离（用于配额和计费）
    agent_id: str  # A: 智能体隔离（用于配置选择）
    platform: str = "default"  # P: 平台隔离
    chat_stream_id: str = None  # C: 聊天流隔离

    # 请求参数
    priority: int = 0  # 请求优先级
    timeout: float = 300.0  # 请求超时时间（秒）
    retry_on_quota_exceeded: bool = True  # 配额超限时是否重试

    # 统计信息
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class IsolatedLLMClient:
    """隔离化的LLM客户端

    支持T+A维度的多租户隔离，实现配额管理和使用量统计。
    """

    def __init__(self, tenant_id: str, agent_id: str, isolation_context: Optional[IsolationContext] = None):
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.isolation_context = isolation_context or create_isolation_context(tenant_id=tenant_id, agent_id=agent_id)

        # 模型使用量记录（按租户+智能体隔离）
        self.model_usage: Dict[str, Tuple[int, int, int]] = {}
        """模型使用量记录，格式: {model_name: (total_tokens, penalty, usage_penalty)}"""

        # 请求队列管理
        self._request_queue: asyncio.Queue = asyncio.Queue()
        self._active_requests: Set[str] = set()
        self._request_results: Dict[str, Tuple[APIResponse, ModelInfo]] = {}

        # 配额检查
        self.quota_manager = IsolatedQuotaManager()

        # 线程安全锁
        self._usage_lock = Lock()
        self._queue_lock = Lock()

        logger.debug(f"创建隔离化LLM客户端: tenant={tenant_id}, agent={agent_id}")

    def _get_isolated_config(self, tenant_id: str, agent_id: str) -> TaskConfig:
        """根据隔离上下文获取配置"""
        try:
            # 尝试从隔离上下文获取配置
            if self.isolation_context and hasattr(self.isolation_context, "get_config_manager"):
                config_manager = self.isolation_context.get_config_manager()
                return config_manager.get_model_config()
        except Exception as e:
            logger.warning(f"获取隔离配置失败，使用默认配置: {e}")

        # 回退到默认配置
        from src.config.config import model_config

        return model_config.get_task_config("default")

    async def generate_response(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        raise_when_empty: bool = True,
        isolation_context: Optional[IsolationContext] = None,
    ) -> Tuple[str, Tuple[str, str, Optional[List[ToolOption]]]]:
        """生成响应（隔离化版本）"""
        start_time = time.time()
        context = isolation_context or self.isolation_context

        # 创建隔离化请求
        request = IsolatedLLMRequest(
            model_set=self._get_isolated_config(context.tenant_id, context.agent_id),
            request_type="response",
            tenant_id=context.tenant_id,
            agent_id=context.agent_id,
            platform=context.platform,
            chat_stream_id=context.chat_stream_id,
        )

        # 检查配额
        quota_status = self.quota_manager.check_quota(context.tenant_id, 1000)  # 估算token
        if quota_status == TenantQuotaStatus.EXCEEDED:
            raise QuotaExceededError(f"租户 {context.tenant_id} 配额已超限")
        elif quota_status == TenantQuotaStatus.WARNING:
            logger.warning(f"租户 {context.tenant_id} 配额即将超限")

        try:
            # 构建消息
            def message_factory(client: BaseClient) -> List[Message]:
                message_builder = MessageBuilder()
                message_builder.add_text_content(prompt)
                return [message_builder.build()]

            # 执行请求
            response, model_info = await self._execute_isolated_request(
                request=request,
                message_factory=message_factory,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
            )

            # 处理响应
            content = response.content or ""
            reasoning_content = response.reasoning_content or ""
            tool_calls = response.tool_calls

            # 记录使用量到租户维度
            if response.usage:
                await self._record_usage(
                    context.tenant_id, context.agent_id, model_info, response.usage, time.time() - start_time
                )

            logger.debug(f"隔离化LLM请求完成: tenant={context.tenant_id}, agent={context.agent_id}")
            return content or "", (reasoning_content, model_info.name, tool_calls)

        except Exception as e:
            logger.error(f"隔离化LLM请求失败: {e}")
            if raise_when_empty:
                raise
            return "", ("", "", None)

    async def get_embedding(
        self, embedding_input: str, isolation_context: Optional[IsolationContext] = None
    ) -> Tuple[List[float], str]:
        """获取嵌入向量（隔离化版本）"""
        start_time = time.time()
        context = isolation_context or self.isolation_context

        # 创建隔离化请求
        request = IsolatedLLMRequest(
            model_set=self._get_isolated_config(context.tenant_id, context.agent_id),
            request_type="embedding",
            tenant_id=context.tenant_id,
            agent_id=context.agent_id,
        )

        # 检查配额
        quota_status = self.quota_manager.check_quota(context.tenant_id, 100)
        if quota_status == TenantQuotaStatus.EXCEEDED:
            raise QuotaExceededError(f"租户 {context.tenant_id} 配额已超限")

        try:
            response, model_info = await self._execute_isolated_request(
                request=request, embedding_input=embedding_input
            )

            embedding = response.embedding
            if not embedding:
                raise RuntimeError("获取embedding失败")

            # 记录使用量
            if response.usage:
                await self._record_usage(
                    context.tenant_id, context.agent_id, model_info, response.usage, time.time() - start_time
                )

            return embedding, model_info.name

        except Exception as e:
            logger.error(f"隔离化embedding请求失败: {e}")
            raise

    async def _execute_isolated_request(
        self,
        request: IsolatedLLMRequest,
        message_factory: Optional[Callable[[BaseClient], List[Message]]] = None,
        tool_options: Optional[List[ToolOption]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[float] = None,
        embedding_input: Optional[str] = None,
    ) -> Tuple[APIResponse, ModelInfo]:
        """执行隔离化请求"""
        request.started_at = datetime.now()

        # 确定请求类型
        request_type = RequestType.RESPONSE if message_factory else RequestType.EMBEDDING

        # 获取模型使用量记录
        with self._usage_lock:
            if not self.model_usage:
                self.model_usage = {model: (0, 0, 0) for model in request.model_set.model_list}

        # 模型选择和请求执行（复用原有逻辑）
        failed_models_this_request: Set[str] = set()
        max_attempts = len(request.model_set.model_list)
        last_exception: Optional[Exception] = None

        for _attempt in range(max_attempts):
            model_info, api_provider, client = self._select_isolated_model(
                request.model_set, failed_models_this_request, request_type == RequestType.EMBEDDING
            )

            message_list = []
            if message_factory:
                message_list = message_factory(client)

            try:
                # 执行请求
                response = await self._attempt_isolated_request(
                    model_info=model_info,
                    api_provider=api_provider,
                    client=client,
                    request_type=request_type,
                    message_list=message_list,
                    tool_options=tool_options,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    embedding_input=embedding_input,
                )

                # 更新使用量统计
                with self._usage_lock:
                    total_tokens, penalty, usage_penalty = self.model_usage[model_info.name]
                    if response_usage := response.usage:
                        total_tokens += response_usage.total_tokens
                    self.model_usage[model_info.name] = (total_tokens, penalty, usage_penalty - 1)

                request.completed_at = datetime.now()
                return response, model_info

            except ModelAttemptFailed as e:
                last_exception = e.original_exception or e
                logger.warning(f"模型 '{model_info.name}' 尝试失败，切换到下一个模型。原因: {e}")

                # 更新惩罚值
                with self._usage_lock:
                    total_tokens, penalty, usage_penalty = self.model_usage[model_info.name]
                    self.model_usage[model_info.name] = (total_tokens, penalty + 1, usage_penalty - 1)

                failed_models_this_request.add(model_info.name)

                if isinstance(last_exception, RespNotOkException) and last_exception.status_code == 400:
                    continue

        logger.error(f"所有 {max_attempts} 个模型均尝试失败。")
        if last_exception:
            raise last_exception
        raise RuntimeError("隔离化请求失败，所有可用模型均已尝试失败。")

    def _select_isolated_model(
        self, model_set: TaskConfig, exclude_models: Optional[Set[str]] = None, force_new_client: bool = False
    ) -> Tuple[ModelInfo, APIProvider, BaseClient]:
        """选择模型（隔离化版本）"""
        with self._usage_lock:
            available_models = {
                model: scores
                for model, scores in self.model_usage.items()
                if not exclude_models or model not in exclude_models
            }

        if not available_models:
            raise RuntimeError("没有可用的模型可供选择。所有模型均已尝试失败。")

        least_used_model_name = min(
            available_models,
            key=lambda k: available_models[k][0] + available_models[k][1] * 300 + available_models[k][2] * 1000,
        )

        from src.config.config import model_config

        model_info = model_config.get_model_info(least_used_model_name)
        api_provider = model_config.get_provider(model_info.api_provider)
        client = client_registry.get_client_class_instance(api_provider, force_new=force_new_client)

        logger.debug(f"选择隔离化请求模型: {model_info.name}")

        with self._usage_lock:
            total_tokens, penalty, usage_penalty = self.model_usage[model_info.name]
            self.model_usage[model_info.name] = (total_tokens, penalty, usage_penalty + 1)

        return model_info, api_provider, client

    async def _attempt_isolated_request(
        self,
        model_info: ModelInfo,
        api_provider: APIProvider,
        client: BaseClient,
        request_type: RequestType,
        message_list: List[Message],
        tool_options: Optional[List[ToolOption]],
        temperature: Optional[float],
        max_tokens: Optional[float],
        embedding_input: Optional[str],
    ) -> APIResponse:
        """尝试在单个模型上执行请求（隔离化版本）"""
        retry_remain = api_provider.max_retry

        while retry_remain > 0:
            try:
                if request_type == RequestType.RESPONSE:
                    return await client.get_response(
                        model_info=model_info,
                        message_list=message_list,
                        tool_options=tool_options,
                        max_tokens=max_tokens or 1024,
                        temperature=temperature or 0.7,
                        extra_params=model_info.extra_params,
                    )
                elif request_type == RequestType.EMBEDDING:
                    assert embedding_input is not None, "嵌入输入不能为空"
                    return await client.get_embedding(
                        model_info=model_info,
                        embedding_input=embedding_input,
                        extra_params=model_info.extra_params,
                    )

            except (EmptyResponseException, NetworkConnectionError, RespNotOkException) as e:
                retry_remain -= 1
                if retry_remain <= 0:
                    raise ModelAttemptFailed(f"模型 '{model_info.name}' 重试耗尽", original_exception=e) from e

                logger.warning(f"模型 '{model_info.name}' 请求失败，重试中... 剩余次数: {retry_remain}")
                await asyncio.sleep(api_provider.retry_interval)

            except Exception as e:
                raise ModelAttemptFailed(f"模型 '{model_info.name}' 遇到硬错误", original_exception=e) from e

        raise ModelAttemptFailed(f"模型 '{model_info.name}' 未被尝试，因为重试次数已配置为0或更少。")

    async def _record_usage(
        self, tenant_id: str, agent_id: str, model_info: ModelInfo, usage: UsageRecord, time_cost: float
    ):
        """记录使用量到租户维度"""
        try:
            # 计算费用
            input_cost = (usage.prompt_tokens / 1000000) * model_info.price_in
            output_cost = (usage.completion_tokens / 1000000) * model_info.price_out
            total_cost = round(input_cost + output_cost, 6)

            # 更新配额管理器
            self.quota_manager.record_usage(tenant_id, usage.total_tokens, total_cost)

            # 记录到数据库（包含隔离信息）
            from .utils import llm_usage_recorder

            llm_usage_recorder.record_usage_to_database(
                model_info=model_info,
                model_usage=usage,
                user_id=f"{tenant_id}:{agent_id}",  # 使用隔离标识
                request_type=f"isolated_{self.isolation_context.platform or 'default'}",
                endpoint="/chat/completions",
                time_cost=time_cost,
            )

            logger.debug(
                f"记录隔离化使用量 - 租户: {tenant_id}, 智能体: {agent_id}, "
                f"模型: {usage.model_name}, Tokens: {usage.total_tokens}, 费用: {total_cost}"
            )

        except Exception as e:
            logger.error(f"记录隔离化使用量失败: {e}")

    def get_usage_stats(self) -> Dict[str, Any]:
        """获取使用统计"""
        with self._usage_lock:
            return {
                "tenant_id": self.tenant_id,
                "agent_id": self.agent_id,
                "model_usage": dict(self.model_usage),
                "quota_status": self.quota_manager.get_quota_status(self.tenant_id),
            }


class IsolatedLLMClientManager:
    """隔离化LLM客户端管理器

    管理多个租户+智能体组合的LLM客户端实例。
    """

    def __init__(self):
        self._clients: Dict[str, IsolatedLLMClient] = {}
        self._lock = Lock()

    def get_client(
        self, tenant_id: str, agent_id: str, isolation_context: Optional[IsolationContext] = None
    ) -> IsolatedLLMClient:
        """获取隔离化LLM客户端"""
        key = f"{tenant_id}:{agent_id}"

        with self._lock:
            if key not in self._clients:
                self._clients[key] = IsolatedLLMClient(
                    tenant_id=tenant_id, agent_id=agent_id, isolation_context=isolation_context
                )

            return self._clients[key]

    def clear_client(self, tenant_id: str, agent_id: str):
        """清理客户端实例"""
        key = f"{tenant_id}:{agent_id}"

        with self._lock:
            if key in self._clients:
                del self._clients[key]
                logger.debug(f"清理隔离化LLM客户端: {key}")

    def clear_tenant_clients(self, tenant_id: str):
        """清理租户的所有客户端"""
        with self._lock:
            keys_to_remove = [key for key in self._clients.keys() if key.startswith(f"{tenant_id}:")]

            for key in keys_to_remove:
                del self._clients[key]
                logger.debug(f"清理租户客户端: {key}")

    def get_stats(self) -> Dict[str, Any]:
        """获取管理器统计信息"""
        with self._lock:
            return {
                "total_clients": len(self._clients),
                "clients": {key: client.get_usage_stats() for key, client in self._clients.items()},
            }


# 全局隔离化LLM客户端管理器
_isolated_client_manager = IsolatedLLMClientManager()


def get_isolated_llm_client(
    tenant_id: str, agent_id: str, isolation_context: Optional[IsolationContext] = None
) -> IsolatedLLMClient:
    """获取隔离化LLM客户端（便捷函数）"""
    return _isolated_client_manager.get_client(tenant_id, agent_id, isolation_context)


def clear_isolated_llm_client(tenant_id: str, agent_id: str):
    """清理隔离化LLM客户端（便捷函数）"""
    _isolated_client_manager.clear_client(tenant_id, agent_id)


def clear_tenant_llm_clients(tenant_id: str):
    """清理租户的所有LLM客户端（便捷函数）"""
    _isolated_client_manager.clear_tenant_clients(tenant_id)


def get_llm_client_stats() -> Dict[str, Any]:
    """获取LLM客户端统计信息（便捷函数）"""
    return _isolated_client_manager.get_stats()


# 导入配额管理器（延迟导入避免循环依赖）
# 由于循环依赖问题，这个导入在类定义后进行
from .quota_manager import IsolatedQuotaManager  # type: ignore  # noqa: E402
