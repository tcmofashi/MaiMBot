import re
import traceback
from typing import TYPE_CHECKING, Dict, Any

try:  # pragma: no cover - optional dependency
    from maim_message import UserInfo  # type: ignore
except ImportError:  # pragma: no cover - graceful degradation
    if TYPE_CHECKING:  # ensure proper typing when type checking
        from maim_message import UserInfo  # type: ignore
    else:

        class UserInfo:  # type: ignore[no-redef]
            """Minimal fallback to avoid hard dependency on maim_message."""

            def __init__(self, user_id: str | None = None, user_nickname: str | None = None, **_: object) -> None:
                self.user_id = user_id
                self.user_nickname = user_nickname


from src.chat.message_receive.message import MessageRecv
from src.chat.message_receive.storage import MessageStorage
from src.chat.heart_flow.heartflow import heartflow
from src.chat.utils.utils import is_mentioned_bot_in_message
from src.chat.utils.chat_message_builder import replace_user_references
from src.common.logger import get_logger
from src.person_info.person_info import Person
from src.common.database.database_model import Images
from src.isolation.isolation_context import create_isolation_context, get_isolation_context_manager

logger = get_logger("chat")


class HeartFCMessageReceiver:
    """心流处理器，负责处理接收到的消息并计算兴趣度"""

    def __init__(self):
        """初始化心流处理器，创建消息存储实例"""
        self.storage = MessageStorage()

    async def process_message(self, message: MessageRecv) -> None:
        """处理接收到的原始消息数据

        主要流程:
        1. 消息解析与初始化
        2. 消息缓冲处理
        3. 过滤检查
        4. 兴趣度计算
        5. 关系处理

        Args:
            message_data: 原始消息字符串
        """
        try:
            # 1. 消息解析与初始化
            sender_info = message.message_info.sender_info
            userinfo = sender_info.user_info if sender_info and sender_info.user_info else UserInfo()
            chat = message.chat_stream

            # 2. 计算at信息
            is_mentioned, is_at, reply_probability_boost = is_mentioned_bot_in_message(message)
            # print(f"is_mentioned: {is_mentioned}, is_at: {is_at}, reply_probability_boost: {reply_probability_boost}")
            message.is_mentioned = is_mentioned
            message.is_at = is_at
            message.reply_probability_boost = reply_probability_boost

            await self.storage.store_message(message, chat)

            await heartflow.get_or_create_heartflow_chat(chat.stream_id)  # type: ignore

            # 3. 日志记录
            mes_name = chat.group_info.group_name if chat.group_info else "私聊"

            # 用这个pattern截取出id部分，picid是一个list，并替换成对应的图片描述
            picid_pattern = r"\[picid:([^\]]+)\]"
            picid_list = re.findall(picid_pattern, message.processed_plain_text)

            # 创建替换后的文本
            processed_text = message.processed_plain_text
            if picid_list:
                for picid in picid_list:
                    image = Images.get_or_none(Images.image_id == picid)
                    if image and image.description:
                        # 将[picid:xxxx]替换成图片描述
                        processed_text = processed_text.replace(f"[picid:{picid}]", f"[图片：{image.description}]")
                    else:
                        # 如果没有找到图片描述，则移除[picid:xxxx]标记
                        processed_text = processed_text.replace(f"[picid:{picid}]", "[图片：网络不好，图片无法加载]")

            # 应用用户引用格式替换，将回复<aaa:bbb>和@<aaa:bbb>格式转换为可读格式
            processed_plain_text = replace_user_references(
                processed_text,
                message.message_info.platform,  # type: ignore
                replace_bot_name=True,
            )
            # if not processed_plain_text:
            # print(message)

            nickname = userinfo.user_nickname or ""
            logger.info(f"[{mes_name}]{nickname}:{processed_plain_text}")

            _ = Person.register_person(
                platform=message.message_info.platform,  # type: ignore
                user_id=userinfo.user_id,  # type: ignore
                nickname=nickname,  # type: ignore
            )

        except Exception as e:
            logger.error(f"消息处理失败: {e}")
            print(traceback.format_exc())


class IsolatedHeartFCMessageReceiver:
    """隔离化的心流处理器，支持T+A维度的多租户隔离"""

    def __init__(self, tenant_id: str, agent_id: str):
        """
        初始化隔离化的心流处理器

        Args:
            tenant_id: 租户标识
            agent_id: 智能体标识
        """
        self.tenant_id = tenant_id
        self.agent_id = agent_id

        # 创建隔离上下文
        self.isolation_context = create_isolation_context(tenant_id=tenant_id, agent_id=agent_id)

        # TODO: 创建隔离化的消息存储实例
        # 目前暂时使用原有存储，后续需要创建IsolatedMessageStorage
        self.storage = MessageStorage()

    async def process_message(self, message: MessageRecv) -> None:
        """
        处理接收到的消息，支持隔离上下文

        主要流程:
        1. 验证隔离权限
        2. 消息解析与初始化
        3. 创建隔离化的心流聊天实例
        4. 消息存储和处理

        Args:
            message: 接收到的消息对象
        """
        try:
            # 1. 验证隔离权限
            await self._validate_isolation_access(message)

            # 2. 消息解析与初始化
            sender_info = message.message_info.sender_info
            userinfo = sender_info.user_info if sender_info and sender_info.user_info else UserInfo()
            chat = message.chat_stream

            # 3. 计算at信息
            is_mentioned, is_at, reply_probability_boost = is_mentioned_bot_in_message(message)
            message.is_mentioned = is_mentioned
            message.is_at = is_at
            message.reply_probability_boost = reply_probability_boost

            # 4. 存储消息（带隔离上下文）
            await self._store_isolated_message(message, chat)

            # 5. 创建或获取隔离化的心流聊天实例
            await self._create_isolated_heartflow_chat(chat)

            # 6. 记录隔离日志
            await self._log_isolated_message(message, userinfo, chat)

        except Exception as e:
            logger.error(f"[隔离心流]消息处理失败: {e}")
            print(traceback.format_exc())

    async def _validate_isolation_access(self, message: MessageRecv) -> None:
        """验证消息访问权限"""
        # 如果消息带有隔离信息，验证是否匹配当前隔离上下文
        if hasattr(message, "tenant_id") and message.tenant_id:
            if message.tenant_id != self.tenant_id:
                raise PermissionError(f"租户权限不足: {message.tenant_id} != {self.tenant_id}")

        if hasattr(message, "agent_id") and message.agent_id:
            if message.agent_id != self.agent_id:
                raise PermissionError(f"智能体权限不足: {message.agent_id} != {self.agent_id}")

    async def _store_isolated_message(self, message: MessageRecv, chat) -> None:
        """存储隔离化的消息"""
        # TODO: 当MessageStorage支持隔离化后，传入隔离上下文
        # 目前暂时使用原有存储
        await self.storage.store_message(message, chat)

    async def _create_isolated_heartflow_chat(self, chat) -> None:
        """创建或获取隔离化的心流聊天实例"""
        from src.chat.heart_flow.isolated_heartflow import get_isolated_heartflow

        # 获取隔离化的心流实例
        isolated_heartflow = get_isolated_heartflow(self.tenant_id, self.agent_id)

        # 创建或获取隔离化的心流聊天
        await isolated_heartflow.get_or_create_heartflow_chat(chat.stream_id)

    async def _log_isolated_message(self, message: MessageRecv, userinfo, chat) -> None:
        """记录隔离化的消息日志"""
        mes_name = chat.group_info.group_name if chat.group_info else "私聊"

        # 用这个pattern截取出id部分，picid是一个list，并替换成对应的图片描述
        picid_pattern = r"\[picid:([^\]]+)\]"
        picid_list = re.findall(picid_pattern, message.processed_plain_text)

        # 创建替换后的文本
        processed_text = message.processed_plain_text
        if picid_list:
            for picid in picid_list:
                image = Images.get_or_none(Images.image_id == picid)
                if image and image.description:
                    # 将[picid:xxxx]替换成图片描述
                    processed_text = processed_text.replace(f"[picid:{picid}]", f"[图片：{image.description}]")
                else:
                    # 如果没有找到图片描述，则移除[picid:xxxx]标记
                    processed_text = processed_text.replace(f"[picid:{picid}]", "[图片：网络不好，图片无法加载]")

        # 应用用户引用格式替换，将回复<aaa:bbb>和@<aaa:bbb>格式转换为可读格式
        processed_plain_text = replace_user_references(
            processed_text,
            message.message_info.platform,  # type: ignore
            replace_bot_name=True,
        )

        nickname = userinfo.user_nickname or ""

        # 带隔离信息的日志
        logger.info(f"[隔离-{self.tenant_id}-{self.agent_id}][{mes_name}]{nickname}:{processed_plain_text}")

        # 注册用户信息
        _ = Person.register_person(
            platform=message.message_info.platform,  # type: ignore
            user_id=userinfo.user_id,  # type: ignore
            nickname=nickname,  # type: ignore
        )

    def get_isolation_info(self) -> Dict[str, Any]:
        """获取隔离信息"""
        return {
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "isolation_level": self.isolation_context.get_isolation_level().value,
            "scope": str(self.isolation_context.scope),
        }


# 隔离化心流处理器管理器
class IsolatedHeartFCMessageReceiverManager:
    """隔离化心流处理器管理器，管理多个租户+智能体的处理器实例"""

    def __init__(self):
        self._receivers: Dict[str, IsolatedHeartFCMessageReceiver] = {}
        self._context_manager = get_isolation_context_manager()

    def get_receiver(self, tenant_id: str, agent_id: str) -> IsolatedHeartFCMessageReceiver:
        """获取或创建隔离化的心流处理器"""
        key = f"{tenant_id}:{agent_id}"

        if key not in self._receivers:
            self._receivers[key] = IsolatedHeartFCMessageReceiver(tenant_id, agent_id)

        return self._receivers[key]

    def clear_tenant_receivers(self, tenant_id: str):
        """清理指定租户的所有处理器"""
        keys_to_remove = []
        for key in self._receivers:
            if key.startswith(f"{tenant_id}:"):
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self._receivers[key]

    def clear_all_receivers(self):
        """清理所有处理器"""
        self._receivers.clear()

    def get_receiver_count(self) -> int:
        """获取处理器数量"""
        return len(self._receivers)

    def list_active_tenants(self) -> list:
        """列出活跃的租户"""
        tenants = set()
        for key in self._receivers:
            tenant_id = key.split(":")[0]
            tenants.add(tenant_id)
        return list(tenants)


# 全局隔离化心流处理器管理器实例
_isolated_receiver_manager = IsolatedHeartFCMessageReceiverManager()


def get_isolated_heartfc_receiver(tenant_id: str, agent_id: str) -> IsolatedHeartFCMessageReceiver:
    """获取隔离化心流处理器的便捷函数"""
    return _isolated_receiver_manager.get_receiver(tenant_id, agent_id)


def get_isolated_receiver_manager() -> IsolatedHeartFCMessageReceiverManager:
    """获取隔离化心流处理器管理器"""
    return _isolated_receiver_manager


def clear_isolated_heartfc_receivers(tenant_id: str = None):
    """清理隔离化心流处理器"""
    if tenant_id:
        _isolated_receiver_manager.clear_tenant_receivers(tenant_id)
    else:
        _isolated_receiver_manager.clear_all_receivers()
