"""
隔离化消息接收类
提供完整的T+A+C+P四维隔离支持
"""

import copy
import hashlib
from typing import Optional, Any, List, Dict, Callable
from dataclasses import dataclass, field
from datetime import datetime

from maim_message.message import (
    Seg,
    UserInfo,
    BaseMessageInfo,
)

from src.common.logger import get_logger
from .chat_stream import ChatStream
from .message import MessageRecv

# 导入隔离上下文
try:
    from ..isolation import (
        IsolationContext,
        IsolationScope,
        IsolationLevel,
        create_isolation_context,
        IsolationValidator,
        parse_isolation_scope,
        generate_isolated_id,
    )
except ImportError:
    # 兼容性处理
    class IsolationContext:
        def __init__(self, *args, **kwargs):
            self.tenant_id = kwargs.get("tenant_id")
            self.agent_id = kwargs.get("agent_id")
            self.platform = kwargs.get("platform")
            self.chat_stream_id = kwargs.get("chat_stream_id")

    class IsolationScope:
        def __init__(self, tenant_id, agent_id, platform=None, chat_stream_id=None):
            self.tenant_id = tenant_id
            self.agent_id = agent_id
            self.platform = platform
            self.chat_stream_id = chat_stream_id

    class IsolationLevel:
        TENANT = "tenant"
        AGENT = "agent"
        PLATFORM = "platform"
        CHAT = "chat"

    def create_isolation_context(*args, **kwargs):
        return IsolationContext(*args, **kwargs)

    def parse_isolation_scope(scope_str):
        return None

    def generate_isolated_id(*args):
        return hashlib.sha256("|".join(args).encode()).hexdigest()

    class IsolationValidator:
        def validate_message(self, message):
            class ValidationResult:
                def __init__(self):
                    self.is_valid = True
                    self.errors = []

            return ValidationResult()


logger = get_logger("isolated_message")


@dataclass
class IsolationMetadata:
    """隔离元数据"""

    tenant_id: str
    agent_id: str
    platform: Optional[str] = None
    chat_stream_id: Optional[str] = None
    isolation_level: str = IsolationLevel.AGENT
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "platform": self.platform,
            "chat_stream_id": self.chat_stream_id,
            "isolation_level": self.isolation_level,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IsolationMetadata":
        """从字典创建"""
        return cls(
            tenant_id=data["tenant_id"],
            agent_id=data["agent_id"],
            platform=data.get("platform"),
            chat_stream_id=data.get("chat_stream_id"),
            isolation_level=data.get("isolation_level", IsolationLevel.AGENT),
            created_at=datetime.fromisoformat(data.get("created_at", datetime.now().isoformat())),
            metadata=data.get("metadata", {}),
        )


class IsolatedMessageRecv(MessageRecv):
    """
    隔离化消息接收类
    完全支持T+A+C+P四维隔离的消息处理
    """

    def __init__(
        self,
        *,
        message_info: BaseMessageInfo,
        message_segment: Seg,
        chat_stream: ChatStream,
        raw_message: Optional[str] = None,
        processed_plain_text: str = "",
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        isolation_context: Optional[IsolationContext] = None,
        isolation_metadata: Optional[IsolationMetadata] = None,
        auto_create_context: bool = True,
        validate_isolation: bool = True,
    ):
        """
        初始化隔离化消息接收类

        Args:
            message_info: 消息信息
            message_segment: 消息段
            chat_stream: 聊天流
            raw_message: 原始消息
            processed_plain_text: 处理后的纯文本
            tenant_id: 租户ID
            agent_id: 智能体ID
            isolation_context: 隔离上下文
            isolation_metadata: 隔离元数据
            auto_create_context: 是否自动创建隔离上下文
            validate_isolation: 是否验证隔离信息
        """
        # 确保隔离信息完整
        tenant_id, agent_id, isolation_context = self._ensure_isolation_info(
            tenant_id, agent_id, isolation_context, chat_stream, message_info
        )

        # 调用父类初始化
        super().__init__(
            message_info=message_info,
            message_segment=message_segment,
            chat_stream=chat_stream,
            raw_message=raw_message,
            processed_plain_text=processed_plain_text,
            tenant_id=tenant_id,
            agent_id=agent_id,
            isolation_context=isolation_context,
        )

        # 隔离元数据
        self.isolation_metadata = isolation_metadata or IsolationMetadata(
            tenant_id=self.tenant_id,
            agent_id=self.agent_id,
            platform=getattr(chat_stream, "platform", None),
            chat_stream_id=getattr(chat_stream, "stream_id", None),
            isolation_level=isolation_metadata.isolation_level if isolation_metadata else IsolationLevel.AGENT,
        )

        # 验证隔离信息
        if validate_isolation and not self.validate_isolation():
            logger.warning(f"消息隔离验证失败: {self.get_isolation_info()}")

        # 生成隔离化ID
        self.isolated_message_id = self._generate_isolated_id()

        # 隔离验证器
        self.validator = IsolationValidator() if callable(IsolationValidator) else None

        # 隔离相关标志
        self.is_cross_tenant = False
        self.is_cross_agent = False
        self.is_cross_platform = False

        # 隔离处理回调
        self.isolation_callbacks: List[Callable] = []

    def _ensure_isolation_info(
        self,
        tenant_id: Optional[str],
        agent_id: Optional[str],
        isolation_context: Optional[IsolationContext],
        chat_stream: ChatStream,
        message_info: BaseMessageInfo,
    ) -> tuple[str, str, IsolationContext]:
        """确保隔离信息完整"""
        # 从现有来源提取信息
        if not tenant_id:
            tenant_id = self._extract_tenant_id(message_info, chat_stream) or "default"

        if not agent_id:
            agent_id = self._extract_agent_id(message_info, {}) or getattr(chat_stream, "agent_id", None) or "default"

        # 创建隔离上下文
        if not isolation_context:
            platform = getattr(chat_stream, "platform", None)
            chat_stream_id = getattr(chat_stream, "stream_id", None)
            isolation_context = create_isolation_context(
                tenant_id=tenant_id, agent_id=agent_id, platform=platform, chat_stream_id=chat_stream_id
            )

        return tenant_id, agent_id, isolation_context

    def _extract_tenant_id(self, message_info: BaseMessageInfo, chat_stream: ChatStream) -> Optional[str]:
        """从消息信息中提取租户ID"""
        # 从消息附加配置中提取
        if hasattr(message_info, "additional_config"):
            additional = getattr(message_info.additional_config, "__dict__", {})
            if isinstance(additional, dict) and additional.get("tenant_id"):
                return str(additional["tenant_id"])

        # 从聊天流中提取
        if hasattr(chat_stream, "tenant_id"):
            return chat_stream.tenant_id

        # 从接收者信息中提取
        receiver = message_info.receiver_info
        if receiver and receiver.user_info:
            # 这里可以根据业务逻辑提取租户ID
            pass

        return None

    def _generate_isolated_id(self) -> str:
        """生成隔离化消息ID"""
        components = [
            self.tenant_id or "unknown",
            self.agent_id or "unknown",
            getattr(self.chat_stream, "platform", "unknown") if self.chat_stream else "unknown",
            getattr(self.chat_stream, "stream_id", "unknown") if self.chat_stream else "unknown",
            self.message_info.message_id or "unknown",
            str(self.message_info.time or 0),
        ]
        return generate_isolated_id(*components)

    def validate_isolation(self) -> bool:
        """验证隔离信息的有效性"""
        try:
            # 基本验证
            if not self.tenant_id or not self.agent_id:
                logger.warning("缺少必要的隔离信息: tenant_id或agent_id")
                return False

            # 上下文验证
            if self.isolation_context:
                context_valid = (
                    self.isolation_context.tenant_id == self.tenant_id
                    and self.isolation_context.agent_id == self.agent_id
                )
                if not context_valid:
                    logger.warning("隔离上下文与消息隔离信息不匹配")
                    return False

            # 元数据验证
            if self.isolation_metadata:
                metadata_valid = (
                    self.isolation_metadata.tenant_id == self.tenant_id
                    and self.isolation_metadata.agent_id == self.agent_id
                )
                if not metadata_valid:
                    logger.warning("隔离元数据与消息隔离信息不匹配")
                    return False

            # 使用验证器验证
            if self.validator:
                validation_result = self.validator.validate_message(self)
                if not validation_result.is_valid:
                    logger.warning(f"隔离验证器验证失败: {validation_result.errors}")
                    return False

            return True

        except Exception as e:
            logger.error(f"隔离验证过程中发生错误: {e}", exc_info=True)
            return False

    def get_isolation_metadata(self) -> IsolationMetadata:
        """获取隔离元数据"""
        return self.isolation_metadata

    def get_isolation_level(self) -> str:
        """获取隔离级别"""
        return self.isolation_metadata.isolation_level if self.isolation_metadata else IsolationLevel.AGENT

    def get_isolation_scope(self) -> IsolationScope:
        """获取隔离范围对象"""
        if self.isolation_context and hasattr(self.isolation_context, "scope"):
            return self.isolation_context.scope

        return IsolationScope(
            tenant_id=self.tenant_id,
            agent_id=self.agent_id,
            platform=getattr(self.chat_stream, "platform", None) if self.chat_stream else None,
            chat_stream_id=getattr(self.chat_stream, "stream_id", None) if self.chat_stream else None,
        )

    def get_isolated_message_id(self) -> str:
        """获取隔离化消息ID"""
        return self.isolated_message_id

    def can_access_isolation(self, tenant_id: str, agent_id: str, platform: str = None) -> bool:
        """检查是否可以访问特定隔离环境"""
        # 检查租户权限
        if self.tenant_id != tenant_id:
            return False

        # 检查智能体权限
        if self.agent_id != agent_id:
            return False

        # 检查平台权限（如果指定）
        if platform:
            message_platform = getattr(self.chat_stream, "platform", None)
            if message_platform and message_platform != platform:
                return False

        return True

    def add_isolation_callback(self, callback: Callable[["IsolatedMessageRecv"], None]) -> None:
        """添加隔离处理回调"""
        if callable(callback):
            self.isolation_callbacks.append(callback)

    def trigger_isolation_callbacks(self) -> None:
        """触发隔离处理回调"""
        for callback in self.isolation_callbacks:
            try:
                callback(self)
            except Exception as e:
                logger.error(f"执行隔离回调时发生错误: {e}", exc_info=True)

    def mark_cross_isolation(self, tenant: bool = False, agent: bool = False, platform: bool = False) -> None:
        """标记跨隔离边界的消息"""
        self.is_cross_tenant = tenant
        self.is_cross_agent = agent
        self.is_cross_platform = platform

    def is_cross_isolation_message(self) -> bool:
        """检查是否为跨隔离边界消息"""
        return self.is_cross_tenant or self.is_cross_agent or self.is_cross_platform

    def create_isolated_copy(self, tenant_id: str = None, agent_id: str = None) -> "IsolatedMessageRecv":
        """创建隔离化副本"""
        # 深拷贝消息
        copied = copy.deepcopy(self)

        # 更新隔离信息
        if tenant_id:
            copied.tenant_id = tenant_id
            copied.isolation_metadata.tenant_id = tenant_id
            if copied.isolation_context:
                copied.isolation_context.tenant_id = tenant_id

        if agent_id:
            copied.agent_id = agent_id
            copied.isolation_metadata.agent_id = agent_id
            if copied.isolation_context:
                copied.isolation_context.agent_id = agent_id

        # 重新生成隔离化ID
        copied.isolated_message_id = copied._generate_isolated_id()

        return copied

    def to_isolated_dict(self) -> Dict[str, Any]:
        """转换为包含隔离信息的字典"""
        base_dict = {
            "message_info": self.message_info.to_dict() if hasattr(self.message_info, "to_dict") else {},
            "message_segment": self.message_segment.to_dict() if hasattr(self.message_segment, "to_dict") else {},
            "chat_stream": self.chat_stream.to_dict() if hasattr(self.chat_stream, "to_dict") else {},
            "raw_message": self.raw_message,
            "processed_plain_text": self.processed_plain_text,
        }

        # 添加隔离信息
        base_dict.update(
            {
                "tenant_id": self.tenant_id,
                "agent_id": self.agent_id,
                "isolation_metadata": self.isolation_metadata.to_dict(),
                "isolated_message_id": self.isolated_message_id,
                "isolation_level": self.get_isolation_level(),
                "isolation_scope": str(self.get_isolation_scope()),
                "cross_isolation": {
                    "tenant": self.is_cross_tenant,
                    "agent": self.is_cross_agent,
                    "platform": self.is_cross_platform,
                },
            }
        )

        return base_dict

    @classmethod
    async def from_isolated_dict(cls, data: Dict[str, Any]) -> "IsolatedMessageRecv":
        """从隔离化字典创建实例"""
        from .chat_stream import get_chat_manager

        # 解析基本信息
        message_info = BaseMessageInfo.from_dict(data.get("message_info", {}))
        message_segment = Seg.from_dict(data.get("message_segment", {}))
        chat_stream_dict = data.get("chat_stream", {})

        # 创建聊天流
        if chat_stream_dict:
            chat_stream = ChatStream.from_dict(chat_stream_dict)
        else:
            # 创建默认聊天流
            chat_manager = get_chat_manager()

            # 确保有有效的用户信息 - 优先使用sender_info
            user_info = None
            group_info = None

            # 从sender_info提取用户信息（新的标准方式）
            if (
                hasattr(message_info, "sender_info")
                and message_info.sender_info
                and message_info.sender_info.user_info
                and message_info.sender_info.user_info.user_id
            ):
                user_info = message_info.sender_info.user_info

            # 从sender_info提取群组信息
            if (
                hasattr(message_info, "sender_info")
                and message_info.sender_info
                and message_info.sender_info.group_info
            ):
                group_info = message_info.sender_info.group_info

            # 如果没有找到用户信息，创建默认用户信息
            if not user_info or not user_info.user_id:
                user_info = UserInfo(
                    platform=data.get("platform", "test"),
                    user_id=data.get("user_id", f"user_{data.get('agent_id', 'default')}"),
                    user_nickname=data.get("user_nickname", "Test User"),
                )

            chat_stream = await chat_manager.get_or_create_stream(
                platform=message_info.platform or data.get("platform", "test"),
                user_info=user_info,
                group_info=group_info,
                agent_id=data.get("agent_id", "default"),
            )

        # 解析隔离元数据
        isolation_metadata = None
        if "isolation_metadata" in data:
            isolation_metadata = IsolationMetadata.from_dict(data["isolation_metadata"])

        # 创建实例
        instance = cls(
            message_info=message_info,
            message_segment=message_segment,
            chat_stream=chat_stream,
            raw_message=data.get("raw_message"),
            processed_plain_text=data.get("processed_plain_text", ""),
            tenant_id=data.get("tenant_id"),
            agent_id=data.get("agent_id"),
            isolation_metadata=isolation_metadata,
            auto_create_context=False,
            validate_isolation=False,
        )

        # 恢复跨隔离标记
        cross_isolation = data.get("cross_isolation", {})
        instance.mark_cross_isolation(
            tenant=cross_isolation.get("tenant", False),
            agent=cross_isolation.get("agent", False),
            platform=cross_isolation.get("platform", False),
        )

        return instance

    async def process_with_isolation(self) -> None:
        """带隔离处理的消息处理"""
        import time

        start_time = time.time()

        logger.info(f"[隔离化消息处理] 开始处理隔离化消息 - ID: {self.isolated_message_id}")
        logger.debug(
            f"[隔离化消息处理] 隔离信息: 租户={self.tenant_id}, 智能体={self.agent_id}, 平台={getattr(self.chat_stream, 'platform', None) if self.chat_stream else None}"
        )

        try:
            # 触发隔离前回调
            callback_start = time.time()
            logger.debug(f"[隔离化消息处理] 开始触发隔离前回调 - 消息ID: {self.isolated_message_id}")
            self.trigger_isolation_callbacks()
            callback_duration = time.time() - callback_start
            logger.debug(
                f"[隔离化消息处理] 隔离前回调完成 - 消息ID: {self.isolated_message_id}, 耗时: {callback_duration:.3f}秒"
            )

            # 执行消息处理
            process_start = time.time()
            logger.info(f"[隔离化消息处理] 开始执行基础消息处理 - 消息ID: {self.isolated_message_id}")
            await self.process()
            process_duration = time.time() - process_start
            logger.info(
                f"[隔离化消息处理] 基础消息处理完成 - 消息ID: {self.isolated_message_id}, 耗时: {process_duration:.3f}秒"
            )

            # 基础消息处理完成后，调用隔离化心流处理器
            try:
                from src.chat.heart_flow.heartflow_message_processor import get_isolated_heartfc_receiver

                logger.info(f"[隔离化消息处理] 开始调用隔离化心流处理器 - 消息ID: {self.isolated_message_id}")

                # 获取隔离化心流处理器
                isolated_receiver = get_isolated_heartfc_receiver(self.tenant_id, self.agent_id)

                # 调用隔离化心流处理器处理消息
                await isolated_receiver.process_message(self)
                logger.info(f"[隔离化消息处理] 隔离化心流处理器处理完成 - 消息ID: {self.isolated_message_id}")

            except Exception as e:
                logger.error(
                    f"[隔离化消息处理] 隔离化心流处理器处理失败 - 消息ID: {self.isolated_message_id}, 异常: {e}",
                    exc_info=True,
                )
                # 不抛出异常，避免影响主流程

            # 隔离后处理
            if self.is_cross_isolation_message():
                logger.info(
                    f"[隔离化消息处理] 处理跨隔离消息 - 消息ID: {self.isolated_message_id}, 隔离信息: {self.get_isolation_info()}"
                )

            total_duration = time.time() - start_time
            logger.info(
                f"[隔离化消息处理] 隔离化消息处理完成 - 消息ID: {self.isolated_message_id}, 总耗时: {total_duration:.3f}秒"
            )

        except Exception as e:
            total_duration = time.time() - start_time
            logger.error(
                f"[隔离化消息处理] 隔离化消息处理失败 - 消息ID: {self.isolated_message_id}, 异常: {str(e)}, 耗时: {total_duration:.3f}秒",
                exc_info=True,
            )
            raise

    def __str__(self) -> str:
        """字符串表示"""
        return (
            f"IsolatedMessageRecv(id={self.isolated_message_id}, "
            f"tenant={self.tenant_id}, agent={self.agent_id}, "
            f"platform={getattr(self.chat_stream, 'platform', None) if self.chat_stream else None})"
        )

    def __repr__(self) -> str:
        """详细字符串表示"""
        return (
            f"IsolatedMessageRecv(isolated_message_id='{self.isolated_message_id}', "
            f"tenant_id='{self.tenant_id}', agent_id='{self.agent_id}', "
            f"isolation_level='{self.get_isolation_level()}', "
            f"message_id='{self.message_info.message_id}')"
        )
