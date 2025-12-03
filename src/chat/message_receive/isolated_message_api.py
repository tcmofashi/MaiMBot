"""
隔离化消息便捷API接口
提供便捷的函数：create_isolated_message(), convert_to_isolated_message() 等
"""

import asyncio
import time
from typing import Optional, List, Dict, Any, Union, Callable, TypeVar, overload
from dataclasses import dataclass
from datetime import datetime
from functools import wraps
import uuid

from maim_message.message import (
    Seg,
    BaseMessageInfo,
)

from src.common.logger import get_logger
from .message import MessageRecv
from .isolated_message import IsolatedMessageRecv, IsolationMetadata
from .message_validator import validate_message, ValidationResult
from .message_converter import (
    batch_convert_to_isolated,
    ConversionResult,
    BatchConversionResult,
    ConversionConfig,
    get_message_converter,
)

# 导入隔离上下文
try:
    from ..isolation import (
        IsolationContext,
        IsolationLevel,
        create_isolation_context,
        get_isolation_context,
        with_isolation_context,
        async_with_isolation_context,
    )
except ImportError:
    # 兼容性处理
    class IsolationContext:
        def __init__(self, *args, **kwargs):
            self.tenant_id = kwargs.get("tenant_id")
            self.agent_id = kwargs.get("agent_id")
            self.platform = kwargs.get("platform")
            self.chat_stream_id = kwargs.get("chat_stream_id")

    def create_isolation_context(*args, **kwargs):
        return IsolationContext(*args, **kwargs)

    def get_isolation_context(*args, **kwargs):
        return None

    def with_isolation_context(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    def async_with_isolation_context(*args, **kwargs):
        def decorator(func):
            return func

        return decorator


logger = get_logger("isolated_message_api")

# 类型变量
T = TypeVar("T", MessageRecv, Dict[str, Any])


@dataclass
class MessageStats:
    """消息统计信息"""

    total_messages: int = 0
    isolated_messages: int = 0
    legacy_messages: int = 0
    validation_errors: int = 0
    conversion_errors: int = 0
    last_activity: Optional[datetime] = None
    tenant_stats: Dict[str, int] = None
    agent_stats: Dict[str, int] = None

    def __post_init__(self):
        if self.tenant_stats is None:
            self.tenant_stats = {}
        if self.agent_stats is None:
            self.agent_stats = {}

    def update(self, message: Union[MessageRecv, IsolatedMessageRecv]) -> None:
        """更新统计信息"""
        self.total_messages += 1
        self.last_activity = datetime.now()

        if isinstance(message, IsolatedMessageRecv):
            self.isolated_messages += 1
            # 更新租户统计
            tenant_id = getattr(message, "tenant_id", "unknown")
            self.tenant_stats[tenant_id] = self.tenant_stats.get(tenant_id, 0) + 1
            # 更新智能体统计
            agent_id = getattr(message, "agent_id", "unknown")
            self.agent_stats[agent_id] = self.agent_stats.get(agent_id, 0) + 1
        else:
            self.legacy_messages += 1

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "total_messages": self.total_messages,
            "isolated_messages": self.isolated_messages,
            "legacy_messages": self.legacy_messages,
            "validation_errors": self.validation_errors,
            "conversion_errors": self.conversion_errors,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
            "tenant_stats": self.tenant_stats,
            "agent_stats": self.agent_stats,
            "isolation_rate": self.isolated_messages / self.total_messages if self.total_messages > 0 else 0.0,
        }


class MessageAPIManager:
    """消息API管理器"""

    def __init__(self):
        self._stats = MessageStats()
        self._config = ConversionConfig()
        self._converter = get_message_converter(self._config)
        self._cache: Dict[str, Union[MessageRecv, IsolatedMessageRecv]] = {}
        self._cache_ttl = 3600  # 1小时
        self._max_cache_size = 1000

    def get_stats(self) -> MessageStats:
        """获取统计信息"""
        return self._stats

    def update_config(self, **kwargs) -> None:
        """更新配置"""
        for key, value in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)

        # 重新创建转换器
        self._converter = get_message_converter(self._config)

    def _cache_message(self, message: Union[MessageRecv, IsolatedMessageRecv], cache_key: str = None) -> str:
        """缓存消息"""
        if len(self._cache) >= self._max_cache_size:
            # 清理最旧的缓存
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]

        if cache_key is None:
            cache_key = str(uuid.uuid4())

        self._cache[cache_key] = {"message": message, "timestamp": time.time()}

        return cache_key

    def _get_cached_message(self, cache_key: str) -> Optional[Union[MessageRecv, IsolatedMessageRecv]]:
        """获取缓存的消息"""
        if cache_key in self._cache:
            cache_entry = self._cache[cache_key]
            if time.time() - cache_entry["timestamp"] < self._cache_ttl:
                return cache_entry["message"]
            else:
                del self._cache[cache_key]  # 过期清理

        return None


# 全局API管理器
_api_manager = MessageAPIManager()


def get_api_manager() -> MessageAPIManager:
    """获取API管理器"""
    return _api_manager


# 便捷函数
def create_isolated_message(
    message_info: BaseMessageInfo,
    message_segment: Seg,
    chat_stream,  # ChatStream类型，避免循环导入
    tenant_id: str,
    agent_id: str,
    raw_message: Optional[str] = None,
    processed_plain_text: str = "",
    platform: Optional[str] = None,
    **kwargs,
) -> IsolatedMessageRecv:
    """
    创建隔离化消息

    Args:
        message_info: 消息信息
        message_segment: 消息段
        chat_stream: 聊天流
        tenant_id: 租户ID
        agent_id: 智能体ID
        raw_message: 原始消息
        processed_plain_text: 处理后的纯文本
        platform: 平台
        **kwargs: 其他参数

    Returns:
        隔离化消息实例
    """
    try:
        # 创建隔离元数据
        isolation_metadata = IsolationMetadata(
            tenant_id=tenant_id,
            agent_id=agent_id,
            platform=platform,
            chat_stream_id=getattr(chat_stream, "stream_id", None) if chat_stream else None,
            isolation_level=kwargs.get("isolation_level", IsolationLevel.AGENT),
            metadata=kwargs.get("metadata", {}),
        )

        # 创建隔离上下文
        isolation_context = create_isolation_context(
            tenant_id=tenant_id,
            agent_id=agent_id,
            platform=platform,
            chat_stream_id=getattr(chat_stream, "stream_id", None) if chat_stream else None,
        )

        # 创建隔离化消息
        isolated_message = IsolatedMessageRecv(
            message_info=message_info,
            message_segment=message_segment,
            chat_stream=chat_stream,
            raw_message=raw_message,
            processed_plain_text=processed_plain_text,
            tenant_id=tenant_id,
            agent_id=agent_id,
            isolation_context=isolation_context,
            isolation_metadata=isolation_metadata,
            **kwargs,
        )

        # 更新统计
        _api_manager._stats.update(isolated_message)

        logger.info(f"创建隔离化消息: tenant={tenant_id}, agent={agent_id}")
        return isolated_message

    except Exception as e:
        logger.error(f"创建隔离化消息失败: {e}", exc_info=True)
        raise


@overload
async def convert_to_isolated_message(
    message: MessageRecv,
    tenant_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    platform: Optional[str] = None,
    **kwargs,
) -> ConversionResult[MessageRecv]: ...


@overload
async def convert_to_isolated_message(
    message: Dict[str, Any],
    tenant_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    platform: Optional[str] = None,
    **kwargs,
) -> ConversionResult[Dict[str, Any]]: ...


async def convert_to_isolated_message(
    message: Union[MessageRecv, Dict[str, Any]],
    tenant_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    platform: Optional[str] = None,
    **kwargs,
) -> ConversionResult:
    """
    转换为隔离化消息（便捷函数）

    Args:
        message: 源消息
        tenant_id: 租户ID
        agent_id: 智能体ID
        platform: 平台
        **kwargs: 其他参数

    Returns:
        转换结果
    """
    result = await _api_manager._converter.convert_to_isolated_message(message, tenant_id, agent_id, platform, **kwargs)

    if result.success and result.converted:
        _api_manager._stats.update(result.converted)
    else:
        _api_manager._stats.conversion_errors += 1

    return result


async def create_isolated_message_async(
    message_info: BaseMessageInfo, message_segment: Seg, chat_stream, tenant_id: str, agent_id: str, **kwargs
) -> IsolatedMessageRecv:
    """异步创建隔离化消息"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, create_isolated_message, message_info, message_segment, chat_stream, tenant_id, agent_id, **kwargs
    )


async def process_isolated_message(
    message: Union[MessageRecv, Dict[str, Any]],
    tenant_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    platform: Optional[str] = None,
    validate_before: bool = True,
    validate_after: bool = True,
    **kwargs,
) -> Optional[IsolatedMessageRecv]:
    """
    处理隔离化消息（转换+验证）

    Args:
        message: 源消息
        tenant_id: 租户ID
        agent_id: 智能体ID
        platform: 平台
        validate_before: 是否在转换前验证
        validate_after: 是否在转换后验证
        **kwargs: 其他参数

    Returns:
        处理后的隔离化消息
    """
    try:
        # 临时更新配置
        original_config = _api_manager._config
        _api_manager._config.validate_before_convert = validate_before
        _api_manager._config.validate_after_convert = validate_after

        # 转换消息
        result = await convert_to_isolated_message(message, tenant_id, agent_id, platform, **kwargs)

        if not result.success:
            logger.error(f"消息转换失败: {result.errors}")
            return None

        isolated_message = result.converted
        if not isolated_message:
            logger.error("转换结果为空")
            return None

        # 处理消息
        if isinstance(isolated_message, IsolatedMessageRecv):
            await isolated_message.process_with_isolation()
        else:
            await isolated_message.process()

        logger.info(f"成功处理隔离化消息: {isolated_message.get_isolated_message_id()}")
        return isolated_message

    except Exception as e:
        logger.error(f"处理隔离化消息失败: {e}", exc_info=True)
        return None

    finally:
        # 恢复原始配置
        _api_manager._config = original_config


async def batch_process_isolated_messages(
    messages: List[Union[MessageRecv, Dict[str, Any]]],
    tenant_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    platform: Optional[str] = None,
    **kwargs,
) -> BatchConversionResult:
    """
    批量处理隔离化消息

    Args:
        messages: 消息列表
        tenant_id: 租户ID
        agent_id: 智能体ID
        platform: 平台
        **kwargs: 其他参数

    Returns:
        批量转换结果
    """
    # 批量转换
    batch_result = await batch_convert_to_isolated(messages, tenant_id, agent_id, platform, **kwargs)

    # 批量处理
    processed_count = 0
    for result in batch_result.results:
        if result.success and result.converted:
            try:
                if isinstance(result.converted, IsolatedMessageRecv):
                    await result.converted.process_with_isolation()
                else:
                    await result.converted.process()
                processed_count += 1
            except Exception as e:
                logger.error(f"处理消息失败: {e}", exc_info=True)
                result.add_error(f"处理失败: {str(e)}")

    batch_result.metadata["processed_count"] = processed_count
    logger.info(f"批量处理完成: {processed_count}/{batch_result.total_count}")

    return batch_result


def validate_isolated_message(message: Union[MessageRecv, IsolatedMessageRecv]) -> ValidationResult:
    """验证隔离化消息（便捷函数）"""
    if isinstance(message, IsolatedMessageRecv):
        # 调用消息对象的验证方法，而不是递归调用自己
        return message.validate()
    else:
        return validate_message(message)


def get_message_stats() -> Dict[str, Any]:
    """获取消息统计信息"""
    return _api_manager.get_stats().to_dict()


def clear_message_stats() -> None:
    """清空消息统计信息"""
    _api_manager._stats = MessageStats()


def update_message_api_config(**kwargs) -> None:
    """更新消息API配置"""
    _api_manager.update_config(**kwargs)


# 装饰器
def isolated_message_handler(
    tenant_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    platform: Optional[str] = None,
    auto_convert: bool = True,
    validate: bool = True,
):
    """
    隔离化消息处理装饰器

    Args:
        tenant_id: 租户ID
        agent_id: 智能体ID
        platform: 平台
        auto_convert: 是否自动转换
        validate: 是否验证
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # 查找消息参数
            message = None
            for arg in args:
                if isinstance(arg, (MessageRecv, IsolatedMessageRecv, dict)):
                    message = arg
                    break

            if message is None:
                # 尝试从kwargs中获取
                message = kwargs.get("message") or kwargs.get("msg")

            if message is None:
                logger.warning("装饰器未找到消息参数")
                return await func(*args, **kwargs)

            # 转换消息
            if auto_convert and not isinstance(message, IsolatedMessageRecv):
                result = await convert_to_isolated_message(message, tenant_id, agent_id, platform)
                if result.success and result.converted:
                    message = result.converted
                elif validate:
                    logger.error(f"消息转换失败: {result.errors}")
                    raise ValueError(f"消息转换失败: {result.errors}")

            # 验证消息
            if validate:
                validation = validate_isolated_message(message)
                if not validation.is_valid:
                    logger.error(f"消息验证失败: {validation.errors}")
                    raise ValueError(f"消息验证失败: {validation.errors}")

            # 更新函数调用参数
            new_args = list(args)
            if message in args:
                idx = args.index(message)
                new_args[idx] = message
                args = tuple(new_args)
            else:
                kwargs["message"] = message

            return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # 同步版本的简化实现
            logger.warning("同步装饰器仅提供基本功能")
            return func(*args, **kwargs)

        # 根据函数类型返回对应的包装器
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def with_message_isolation(tenant_id: str, agent_id: str, platform: Optional[str] = None):
    """
    带消息隔离的上下文装饰器

    Args:
        tenant_id: 租户ID
        agent_id: 智能体ID
        platform: 平台
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 创建隔离上下文
            isolation_context = create_isolation_context(tenant_id=tenant_id, agent_id=agent_id, platform=platform)

            # 将隔离上下文添加到kwargs中
            kwargs["isolation_context"] = isolation_context

            return func(*args, **kwargs)

        return wrapper

    return decorator


# 上下文管理器
class IsolatedMessageContext:
    """隔离化消息上下文管理器"""

    def __init__(self, tenant_id: str, agent_id: str, platform: Optional[str] = None, auto_validate: bool = True):
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.platform = platform
        self.auto_validate = auto_validate
        self.isolation_context = create_isolation_context(tenant_id=tenant_id, agent_id=agent_id, platform=platform)
        self.created_messages: List[IsolatedMessageRecv] = []

    def create_message(
        self, message_info: BaseMessageInfo, message_segment: Seg, chat_stream, **kwargs
    ) -> IsolatedMessageRecv:
        """创建隔离化消息"""
        message = create_isolated_message(
            message_info=message_info,
            message_segment=message_segment,
            chat_stream=chat_stream,
            tenant_id=self.tenant_id,
            agent_id=self.agent_id,
            platform=self.platform,
            **kwargs,
        )

        if self.auto_validate:
            validation = validate_isolated_message(message)
            if not validation.is_valid:
                logger.error(f"消息验证失败: {validation.errors}")
                raise ValueError(f"消息验证失败: {validation.errors}")

        self.created_messages.append(message)
        return message

    async def convert_message(self, message: Union[MessageRecv, Dict[str, Any]], **kwargs) -> ConversionResult:
        """转换消息"""
        result = await convert_to_isolated_message(
            message, tenant_id=self.tenant_id, agent_id=self.agent_id, platform=self.platform, **kwargs
        )

        if result.success and result.converted:
            self.created_messages.append(result.converted)

        return result

    def get_created_messages(self) -> List[IsolatedMessageRecv]:
        """获取创建的消息列表"""
        return self.created_messages.copy()

    def get_stats(self) -> Dict[str, Any]:
        """获取上下文统计"""
        return {
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "platform": self.platform,
            "created_messages_count": len(self.created_messages),
            "isolation_context": str(self.isolation_context),
        }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # 清理资源
        self.created_messages.clear()
        if exc_type:
            logger.error(f"隔离化消息上下文异常: {exc_val}")
        return False


# 系统管理函数
async def cleanup_isolated_messages(
    tenant_id: Optional[str] = None, agent_id: Optional[str] = None, older_than_hours: int = 24
) -> Dict[str, Any]:
    """
    清理隔离化消息

    Args:
        tenant_id: 租户ID（可选）
        agent_id: 智能体ID（可选）
        older_than_hours: 清理多少小时前的消息

    Returns:
        清理结果
    """
    # 清理缓存
    cache_size_before = len(_api_manager._cache)
    _api_manager._cache.clear()
    cache_size_after = len(_api_manager._cache)

    # 这里可以添加更多清理逻辑，比如数据库清理等

    result = {
        "cache_cleared": cache_size_before - cache_size_after,
        "tenant_id": tenant_id,
        "agent_id": agent_id,
        "older_than_hours": older_than_hours,
        "timestamp": datetime.now().isoformat(),
    }

    logger.info(f"清理隔离化消息完成: {result}")
    return result


async def isolated_message_health_check() -> Dict[str, Any]:
    """
    隔离化消息系统健康检查

    Returns:
        健康检查结果
    """
    stats = get_message_stats()
    converter_stats = _api_manager._converter.get_conversion_stats()

    health_info = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "message_stats": stats,
        "converter_stats": converter_stats,
        "cache_size": len(_api_manager._cache),
        "max_cache_size": _api_manager._max_cache_size,
        "cache_ttl": _api_manager._cache_ttl,
    }

    # 检查健康指标
    if stats.get("validation_errors", 0) > 100:
        health_info["status"] = "warning"
        health_info["warnings"] = ["验证错误过多"]

    if converter_stats.get("success_rate", 1.0) < 0.9:
        health_info["status"] = "warning"
        health_info.setdefault("warnings", []).append("转换成功率过低")

    return health_info


# 导出的便捷函数
__all__ = [
    # 核心函数
    "create_isolated_message",
    "convert_to_isolated_message",
    "process_isolated_message",
    "batch_process_isolated_messages",
    # 验证函数
    "validate_isolated_message",
    # 统计函数
    "get_message_stats",
    "clear_message_stats",
    "update_message_api_config",
    # 装饰器和上下文
    "isolated_message_handler",
    "with_message_isolation",
    "IsolatedMessageContext",
    # 系统管理
    "cleanup_isolated_messages",
    "isolated_message_health_check",
    "get_api_manager",
]
