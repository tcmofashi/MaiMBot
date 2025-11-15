"""
消息转换器
实现传统消息到隔离化消息的转换和批量处理
"""

import asyncio
from typing import Optional, List, Dict, Any, Union, TypeVar, Generic
from dataclasses import dataclass, field
from datetime import datetime
import uuid


from src.common.logger import get_logger
from .message import MessageRecv
from .isolated_message import IsolatedMessageRecv, IsolationMetadata
from .message_validator import validate_message, ValidationResult

# 导入隔离上下文
try:
    from ..isolation import IsolationContext, IsolationLevel, create_isolation_context, generate_isolated_id
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

    def generate_isolated_id(*args):
        return uuid.uuid4().hex


T = TypeVar("T", MessageRecv, IsolatedMessageRecv, Dict[str, Any])

logger = get_logger("message_converter")


@dataclass
class ConversionConfig:
    """转换配置"""

    default_tenant_id: str = "default"
    default_agent_id: str = "default"
    auto_create_context: bool = True
    validate_before_convert: bool = True
    validate_after_convert: bool = True
    preserve_original: bool = True
    conversion_mode: str = "smart"  # smart, force, gentle
    error_handling: str = "raise"  # raise, log, ignore
    batch_size: int = 100
    max_workers: int = 4
    timeout: Optional[float] = 30.0

    def __post_init__(self):
        """验证配置"""
        if self.conversion_mode not in ["smart", "force", "gentle"]:
            raise ValueError(f"无效的转换模式: {self.conversion_mode}")

        if self.error_handling not in ["raise", "log", "ignore"]:
            raise ValueError(f"无效的错误处理模式: {self.error_handling}")


@dataclass
class ConversionResult(Generic[T]):
    """转换结果"""

    success: bool
    original: T
    converted: Optional[Union[IsolatedMessageRecv, MessageRecv, Dict[str, Any]]] = None
    validation_result: Optional[ValidationResult] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    conversion_time: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

    def add_error(self, error: str) -> None:
        """添加错误"""
        self.errors.append(error)
        self.success = False

    def add_warning(self, warning: str) -> None:
        """添加警告"""
        self.warnings.append(warning)

    def has_issues(self) -> bool:
        """是否有问题"""
        return len(self.errors) > 0 or len(self.warnings) > 0


@dataclass
class BatchConversionResult:
    """批量转换结果"""

    total_count: int
    success_count: int
    failure_count: int
    results: List[ConversionResult] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None

    @property
    def success_rate(self) -> float:
        """成功率"""
        return self.success_count / self.total_count if self.total_count > 0 else 0.0

    @property
    def duration(self) -> float:
        """转换耗时"""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0

    def get_summary(self) -> str:
        """获取摘要"""
        return (
            f"批量转换完成: {self.success_count}/{self.total_count} 成功 "
            f"({self.success_rate:.1%}), 耗时 {self.duration:.2f}s"
        )


class MessageConverter:
    """消息转换器"""

    def __init__(self, config: Optional[ConversionConfig] = None):
        self.config = config or ConversionConfig()
        self._conversion_stats = {
            "total_conversions": 0,
            "successful_conversions": 0,
            "failed_conversions": 0,
            "total_time": 0.0,
        }

    async def convert_to_isolated_message(
        self,
        message: Union[MessageRecv, Dict[str, Any]],
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        platform: Optional[str] = None,
        **kwargs,
    ) -> ConversionResult[MessageRecv]:
        """
        将消息转换为隔离化消息

        Args:
            message: 源消息（MessageRecv对象或字典）
            tenant_id: 目标租户ID
            agent_id: 目标智能体ID
            platform: 目标平台
            **kwargs: 其他参数

        Returns:
            转换结果
        """
        start_time = datetime.now()

        try:
            result = ConversionResult[MessageRecv](success=False, original=message)

            # 验证输入
            if self.config.validate_before_convert:
                if isinstance(message, dict):
                    from .message_validator import validate_message_data

                    validation = await validate_message_data(message)
                else:
                    validation = validate_message(message)

                if not validation.is_valid:
                    result.add_error("消息验证失败")
                    result.errors.extend([str(error) for error in validation.errors])
                    return result

                result.validation_result = validation
                result.warnings.extend([str(warning) for warning in validation.warnings])

            # 解析隔离信息
            tenant_id, agent_id, platform = self._resolve_isolation_info(message, tenant_id, agent_id, platform)

            # 执行转换
            if isinstance(message, dict):
                converted = self._convert_dict_to_isolated(message, tenant_id, agent_id, platform, **kwargs)
            elif isinstance(message, MessageRecv):
                converted = self._convert_message_to_isolated(message, tenant_id, agent_id, platform, **kwargs)
            else:
                result.add_error(f"不支持的消息类型: {type(message)}")
                return result

            # 验证转换结果
            if self.config.validate_after_convert and converted:
                validation = validate_message(converted)
                if not validation.is_valid:
                    result.add_error("转换后的消息验证失败")
                    result.errors.extend([str(error) for error in validation.errors])
                else:
                    result.warnings.extend([str(warning) for warning in validation.warnings])

            if converted:
                result.converted = converted
                result.success = True
                result.metadata.update(
                    {
                        "tenant_id": tenant_id,
                        "agent_id": agent_id,
                        "platform": platform,
                        "conversion_mode": self.config.conversion_mode,
                    }
                )

            # 更新统计
            self._update_stats(result.success, start_time)

            result.conversion_time = (datetime.now() - start_time).total_seconds()
            return result

        except Exception as e:
            error_msg = f"转换过程中发生错误: {str(e)}"
            logger.error(error_msg, exc_info=True)

            result = ConversionResult[MessageRecv](
                success=False, original=message, conversion_time=(datetime.now() - start_time).total_seconds()
            )
            result.add_error(error_msg)

            if self.config.error_handling == "raise":
                raise
            elif self.config.error_handling == "log":
                logger.error(error_msg, exc_info=True)

            return result

    def convert_to_legacy_message(
        self, message: IsolatedMessageRecv, preserve_isolation: bool = False
    ) -> ConversionResult[IsolatedMessageRecv]:
        """
        将隔离化消息转换为传统消息

        Args:
            message: 隔离化消息
            preserve_isolation: 是否保留隔离信息

        Returns:
            转换结果
        """
        start_time = datetime.now()

        try:
            result = ConversionResult[IsolatedMessageRecv](success=False, original=message)

            # 验证输入
            if self.config.validate_before_convert:
                from .message_validator import validate_isolated_message

                validation = validate_isolated_message(message)
                if not validation.is_valid:
                    result.add_error("隔离化消息验证失败")
                    result.errors.extend([str(error) for error in validation.errors])
                    return result

            # 执行转换
            converted = self._convert_isolated_to_legacy(message, preserve_isolation)

            if converted:
                result.converted = converted
                result.success = True
                result.metadata.update(
                    {
                        "preserve_isolation": preserve_isolation,
                        "original_isolated_id": getattr(message, "isolated_message_id", None),
                    }
                )

            # 更新统计
            self._update_stats(result.success, start_time)

            result.conversion_time = (datetime.now() - start_time).total_seconds()
            return result

        except Exception as e:
            error_msg = f"转换过程中发生错误: {str(e)}"
            logger.error(error_msg, exc_info=True)

            result = ConversionResult[IsolatedMessageRecv](
                success=False, original=message, conversion_time=(datetime.now() - start_time).total_seconds()
            )
            result.add_error(error_msg)

            if self.config.error_handling == "raise":
                raise
            elif self.config.error_handling == "log":
                logger.error(error_msg, exc_info=True)

            return result

    async def batch_convert_to_isolated(
        self,
        messages: List[Union[MessageRecv, Dict[str, Any]]],
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        platform: Optional[str] = None,
        **kwargs,
    ) -> BatchConversionResult:
        """
        批量转换为隔离化消息

        Args:
            messages: 消息列表
            tenant_id: 租户ID
            agent_id: 智能体ID
            platform: 平台
            **kwargs: 其他参数

        Returns:
            批量转换结果
        """
        batch_result = BatchConversionResult(total_count=len(messages), success_count=0, failure_count=0)

        try:
            if self.config.batch_size <= 1 or len(messages) <= self.config.batch_size:
                # 串行处理
                for message in messages:
                    result = await self.convert_to_isolated_message(message, tenant_id, agent_id, platform, **kwargs)
                    batch_result.results.append(result)
                    if result.success:
                        batch_result.success_count += 1
                    else:
                        batch_result.failure_count += 1
            else:
                # 并行处理
                semaphore = asyncio.Semaphore(self.config.max_workers)
                tasks = []

                for message in messages:

                    async def convert_with_semaphore(msg):
                        async with semaphore:
                            return await self.convert_to_isolated_message(msg, tenant_id, agent_id, platform, **kwargs)

                    tasks.append(convert_with_semaphore(message))

                # 分批执行
                for i in range(0, len(tasks), self.config.batch_size):
                    batch_tasks = tasks[i : i + self.config.batch_size]
                    if self.config.timeout:
                        batch_results = await asyncio.wait_for(
                            asyncio.gather(*batch_tasks, return_exceptions=True), timeout=self.config.timeout
                        )
                    else:
                        batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

                    for batch_result_item in batch_results:
                        if isinstance(batch_result_item, Exception):
                            # 处理异常
                            error_result = ConversionResult(success=False, original=None, conversion_time=0.0)
                            error_result.add_error(f"转换异常: {str(batch_result_item)}")
                            batch_result.results.append(error_result)
                            batch_result.failure_count += 1
                        else:
                            batch_result.results.append(batch_result_item)
                            if batch_result_item.success:
                                batch_result.success_count += 1
                            else:
                                batch_result.failure_count += 1

            batch_result.end_time = datetime.now()
            batch_result.metadata.update(
                {
                    "batch_size": self.config.batch_size,
                    "max_workers": self.config.max_workers,
                    "conversion_mode": self.config.conversion_mode,
                    "tenant_id": tenant_id,
                    "agent_id": agent_id,
                    "platform": platform,
                }
            )

            logger.info(batch_result.get_summary())
            return batch_result

        except Exception as e:
            error_msg = f"批量转换过程中发生错误: {str(e)}"
            logger.error(error_msg, exc_info=True)
            batch_result.end_time = datetime.now()
            batch_result.metadata["error"] = error_msg

            if self.config.error_handling == "raise":
                raise

            return batch_result

    def _resolve_isolation_info(
        self,
        message: Union[MessageRecv, Dict[str, Any]],
        tenant_id: Optional[str],
        agent_id: Optional[str],
        platform: Optional[str],
    ) -> tuple[str, str, Optional[str]]:
        """解析隔离信息"""
        # 从消息中提取现有信息
        if isinstance(message, MessageRecv):
            extracted_tenant = getattr(message, "tenant_id", None)
            extracted_agent = getattr(message, "agent_id", None)
            extracted_platform = getattr(message.chat_stream, "platform", None) if message.chat_stream else None
        elif isinstance(message, dict):
            extracted_tenant = message.get("tenant_id")
            extracted_agent = message.get("agent_id")
            extracted_platform = None  # 从字典中难以提取，保持None
        else:
            extracted_tenant = extracted_agent = extracted_platform = None

        # 应用转换策略
        if self.config.conversion_mode == "smart":
            # 智能模式：优先使用消息中的信息，其次是传入参数，最后使用默认值
            final_tenant = extracted_tenant or tenant_id or self.config.default_tenant_id
            final_agent = extracted_agent or agent_id or self.config.default_agent_id
            final_platform = extracted_platform or platform
        elif self.config.conversion_mode == "force":
            # 强制模式：使用传入参数或默认值，忽略消息中的信息
            final_tenant = tenant_id or self.config.default_tenant_id
            final_agent = agent_id or self.config.default_agent_id
            final_platform = platform
        else:  # gentle
            # 温和模式：只在没有信息时才使用传入参数
            final_tenant = extracted_tenant or tenant_id or self.config.default_tenant_id
            final_agent = extracted_agent or agent_id or self.config.default_agent_id
            final_platform = extracted_platform or platform

        return final_tenant, final_agent, final_platform

    def _convert_dict_to_isolated(
        self, message_dict: Dict[str, Any], tenant_id: str, agent_id: str, platform: Optional[str], **kwargs
    ) -> Optional[IsolatedMessageRecv]:
        """将字典转换为隔离化消息"""
        try:
            # 创建隔离元数据
            isolation_metadata = IsolationMetadata(
                tenant_id=tenant_id,
                agent_id=agent_id,
                platform=platform,
                isolation_level=kwargs.get("isolation_level", IsolationLevel.AGENT),
            )

            # 从字典创建隔离化消息
            isolated_message = IsolatedMessageRecv.from_isolated_dict(message_dict)

            # 更新隔离信息
            isolated_message.tenant_id = tenant_id
            isolated_message.agent_id = agent_id
            isolated_message.isolation_metadata = isolation_metadata

            # 重新创建隔离上下文
            if isolated_message.chat_stream:
                chat_stream_id = getattr(isolated_message.chat_stream, "stream_id", None)
                isolated_message.isolation_context = create_isolation_context(
                    tenant_id=tenant_id, agent_id=agent_id, platform=platform, chat_stream_id=chat_stream_id
                )

            return isolated_message

        except Exception as e:
            logger.error(f"字典转隔离化消息失败: {e}", exc_info=True)
            return None

    def _convert_message_to_isolated(
        self, message: MessageRecv, tenant_id: str, agent_id: str, platform: Optional[str], **kwargs
    ) -> Optional[IsolatedMessageRecv]:
        """将MessageRecv转换为隔离化消息"""
        try:
            # 创建隔离元数据
            isolation_metadata = IsolationMetadata(
                tenant_id=tenant_id,
                agent_id=agent_id,
                platform=platform or getattr(message.chat_stream, "platform", None) if message.chat_stream else None,
                chat_stream_id=getattr(message.chat_stream, "stream_id", None) if message.chat_stream else None,
                isolation_level=kwargs.get("isolation_level", IsolationLevel.AGENT),
            )

            # 创建隔离上下文
            chat_stream_id = getattr(message.chat_stream, "stream_id", None) if message.chat_stream else None
            isolation_context = create_isolation_context(
                tenant_id=tenant_id, agent_id=agent_id, platform=platform, chat_stream_id=chat_stream_id
            )

            # 创建隔离化消息
            isolated_message = IsolatedMessageRecv(
                message_info=message.message_info,
                message_segment=message.message_segment,
                chat_stream=message.chat_stream,
                raw_message=getattr(message, "raw_message", None),
                processed_plain_text=message.processed_plain_text,
                tenant_id=tenant_id,
                agent_id=agent_id,
                isolation_context=isolation_context,
                isolation_metadata=isolation_metadata,
                auto_create_context=False,
                validate_isolation=False,
            )

            # 复制其他属性
            for attr_name in dir(message):
                if not attr_name.startswith("_") and attr_name not in [
                    "message_info",
                    "message_segment",
                    "chat_stream",
                    "raw_message",
                    "processed_plain_text",
                    "tenant_id",
                    "agent_id",
                    "isolation_context",
                ]:
                    try:
                        setattr(isolated_message, attr_name, getattr(message, attr_name))
                    except Exception:
                        pass  # 忽略无法复制的属性

            return isolated_message

        except Exception as e:
            logger.error(f"MessageRecv转隔离化消息失败: {e}", exc_info=True)
            return None

    def _convert_isolated_to_legacy(
        self, message: IsolatedMessageRecv, preserve_isolation: bool
    ) -> Optional[MessageRecv]:
        """将隔离化消息转换为传统消息"""
        try:
            # 创建传统消息
            legacy_message = MessageRecv(
                message_info=message.message_info,
                message_segment=message.message_segment,
                chat_stream=message.chat_stream,
                raw_message=getattr(message, "raw_message", None),
                processed_plain_text=message.processed_plain_text,
                tenant_id=message.tenant_id if preserve_isolation else None,
                agent_id=message.agent_id if preserve_isolation else None,
                isolation_context=message.isolation_context if preserve_isolation else None,
            )

            # 复制其他属性
            for attr_name in dir(message):
                if not attr_name.startswith("_") and attr_name not in [
                    "message_info",
                    "message_segment",
                    "chat_stream",
                    "raw_message",
                    "processed_plain_text",
                    "tenant_id",
                    "agent_id",
                    "isolation_context",
                    "isolation_metadata",
                    "isolated_message_id",
                ]:
                    try:
                        setattr(legacy_message, attr_name, getattr(message, attr_name))
                    except Exception:
                        pass  # 忽略无法复制的属性

            return legacy_message

        except Exception as e:
            logger.error(f"隔离化消息转传统消息失败: {e}", exc_info=True)
            return None

    def _update_stats(self, success: bool, start_time: datetime) -> None:
        """更新统计信息"""
        self._conversion_stats["total_conversions"] += 1
        if success:
            self._conversion_stats["successful_conversions"] += 1
        else:
            self._conversion_stats["failed_conversions"] += 1

        conversion_time = (datetime.now() - start_time).total_seconds()
        self._conversion_stats["total_time"] += conversion_time

    def get_conversion_stats(self) -> Dict[str, Any]:
        """获取转换统计"""
        stats = self._conversion_stats.copy()
        if stats["total_conversions"] > 0:
            stats["success_rate"] = stats["successful_conversions"] / stats["total_conversions"]
            stats["average_time"] = stats["total_time"] / stats["total_conversions"]
        else:
            stats["success_rate"] = 0.0
            stats["average_time"] = 0.0

        return stats

    def reset_stats(self) -> None:
        """重置统计信息"""
        self._conversion_stats = {
            "total_conversions": 0,
            "successful_conversions": 0,
            "failed_conversions": 0,
            "total_time": 0.0,
        }


# 全局转换器实例
_message_converter = None


def get_message_converter(config: Optional[ConversionConfig] = None) -> MessageConverter:
    """获取全局消息转换器实例"""
    global _message_converter
    if _message_converter is None or config is not None:
        _message_converter = MessageConverter(config)
    return _message_converter


async def convert_to_isolated_message(
    message: Union[MessageRecv, Dict[str, Any]],
    tenant_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    platform: Optional[str] = None,
    **kwargs,
) -> ConversionResult[MessageRecv]:
    """转换为隔离化消息（便捷函数）"""
    converter = get_message_converter()
    return await converter.convert_to_isolated_message(message, tenant_id, agent_id, platform, **kwargs)


def convert_to_legacy_message(
    message: IsolatedMessageRecv, preserve_isolation: bool = False
) -> ConversionResult[IsolatedMessageRecv]:
    """转换为传统消息（便捷函数）"""
    converter = get_message_converter()
    return converter.convert_to_legacy_message(message, preserve_isolation)


async def batch_convert_to_isolated(
    messages: List[Union[MessageRecv, Dict[str, Any]]],
    tenant_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    platform: Optional[str] = None,
    **kwargs,
) -> BatchConversionResult:
    """批量转换为隔离化消息（便捷函数）"""
    converter = get_message_converter()
    return await converter.batch_convert_to_isolated(messages, tenant_id, agent_id, platform, **kwargs)
