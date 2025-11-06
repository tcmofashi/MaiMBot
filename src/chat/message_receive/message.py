import time
import urllib3

from rich.traceback import install
from typing import Optional, Any, List, Dict
from maim_message import (
    Seg,
    UserInfo,
    GroupInfo,
    BaseMessageInfo,
    MessageBase,
    SenderInfo,
    ReceiverInfo,
)

from src.common.logger import get_logger
from src.chat.utils.utils_image import get_image_manager
from src.chat.utils.utils_voice import get_voice_text
from .chat_stream import ChatStream

install(extra_lines=3)

logger = get_logger("chat_message")

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class MaiMessageBase(MessageBase):
    """统一的消息基类，负责消息段解析与通用结构。"""

    def __init__(
        self,
        *,
        message_info: BaseMessageInfo,
        message_segment: Seg,
        chat_stream: ChatStream,
        raw_message: Optional[str] = None,
        reply: Optional["MaiMessageBase"] = None,
        processed_plain_text: str = "",
    ):
        super().__init__(
            message_info=message_info,
            message_segment=message_segment,
            raw_message=raw_message,
        )
        self.chat_stream = chat_stream
        self.reply = reply
        self.processed_plain_text = processed_plain_text

    def update_chat_stream(self, chat_stream: ChatStream) -> None:
        self.chat_stream = chat_stream

    async def process(self) -> None:
        self.processed_plain_text = await self._process_message_segments(self.message_segment)

    async def _process_message_segments(self, segment: Seg) -> str:
        if segment.type == "seglist":
            segments_text: List[str] = []
            for seg in segment.data:
                processed = await self._process_message_segments(seg)  # type: ignore[arg-type]
                if processed:
                    segments_text.append(processed)
            return " ".join(segments_text)
        if segment.type == "forward":
            segments_text: List[str] = []
            cfg = self.chat_stream.get_effective_config()
            nickname = getattr(cfg.bot, "nickname", "Mai")
            for node_dict in segment.data:
                node_message = MessageBase.from_dict(node_dict)  # type: ignore[arg-type]
                processed_text = await self._process_message_segments(node_message.message_segment)
                if processed_text:
                    segments_text.append(f"{nickname}: {processed_text}")
            return "[合并消息]: " + "\n--  ".join(segments_text)
        return await self._resolve_segment_text(segment)

    async def _resolve_segment_text(self, segment: Seg) -> str:
        raise NotImplementedError

    def generate_detailed_text(self) -> str:
        info = self.message_info.sender_info
        platform = self.message_info.platform or "unknown"
        timestamp = self.message_info.time

        user_id = ""
        nickname = ""
        card = ""
        if info and info.user_info:
            user_id = info.user_info.user_id or ""
            nickname = info.user_info.user_nickname or ""
            card = info.user_info.user_cardname or ""

        return f"[{timestamp}]，<{platform}:{user_id}:{nickname}:{card}> 说：{self.processed_plain_text}\n"

    # 兼容旧代码
    def _generate_detailed_text(self) -> str:  # pragma: no cover - 兼容旧接口
        return self.generate_detailed_text()


class MessageRecv(MaiMessageBase):
    """接收消息类"""

    def __init__(
        self,
        *,
        message_info: BaseMessageInfo,
        message_segment: Seg,
        chat_stream: ChatStream,
        raw_message: Optional[str] = None,
        processed_plain_text: str = "",
    ):
        super().__init__(
            message_info=message_info,
            message_segment=message_segment,
            chat_stream=chat_stream,
            raw_message=raw_message,
            processed_plain_text=processed_plain_text,
        )

        self.is_emoji = False
        self.has_emoji = False
        self.is_picid = False
        self.has_picid = False
        self.is_voice = False
        self.is_mentioned: Optional[bool | float] = None
        self.is_at = False
        self.reply_probability_boost = 0.0
        self.is_notify = False
        self.is_command = False
        self.priority_mode = "interest"
        self.priority_info: Optional[Dict[str, Any]] = None
        self.interest_value: Optional[float] = None
        self.key_words: List[str] = []
        self.key_words_lite: List[str] = []

        self._ensure_legacy_fields()

    def _ensure_legacy_fields(self) -> None:
        """为仍依赖旧字段的模块补齐 user_info/group_info。"""

        sender = self.message_info.sender_info
        if sender and sender.user_info and not self.message_info.user_info:
            self.message_info.user_info = UserInfo.from_dict(sender.user_info.to_dict())
        if sender and sender.group_info and not self.message_info.group_info:
            self.message_info.group_info = GroupInfo.from_dict(sender.group_info.to_dict())

        if not self.message_info.group_info:
            chat_group = getattr(self.chat_stream, "group_info", None)
            if chat_group:
                self.message_info.group_info = GroupInfo.from_dict(chat_group.to_dict())

        if not self.message_info.user_info:
            chat_user = getattr(self.chat_stream, "user_info", None)
            if chat_user:
                self.message_info.user_info = UserInfo.from_dict(chat_user.to_dict())

        if self.message_info.user_info and self.message_info.user_info.user_id is not None:
            self.message_info.user_info.user_id = str(self.message_info.user_info.user_id)
        if self.message_info.group_info and self.message_info.group_info.group_id is not None:
            self.message_info.group_info.group_id = str(self.message_info.group_info.group_id)

    @staticmethod
    def _extract_agent_id(message_info: BaseMessageInfo, message_dict: dict[str, Any]) -> str:
        receiver = message_info.receiver_info
        if receiver and receiver.user_info and receiver.user_info.user_id:
            return str(receiver.user_info.user_id)

        additional = message_dict.get("message_info", {}).get("additional_config") or {}
        if isinstance(additional, dict) and additional.get("agent_id"):
            return str(additional["agent_id"])
        return "default"

    def _apply_initial_payload(self, message_dict: dict[str, Any]) -> None:
        self.processed_plain_text = message_dict.get("processed_plain_text", "")

        try:
            msg_info_dict = message_dict.get("message_info", {})
            add_cfg = msg_info_dict.get("additional_config") or {}
            if isinstance(add_cfg, dict) and add_cfg.get("at_bot"):
                self.is_mentioned = True
        except Exception:
            logger.debug("additional_config 解析失败", exc_info=True)

    @classmethod
    async def from_dict(cls, message_dict: dict[str, Any]) -> "MessageRecv":
        message_info = BaseMessageInfo.from_dict(message_dict.get("message_info", {}))
        message_segment = Seg.from_dict(message_dict.get("message_segment", {}))
        raw_message = message_dict.get("raw_message")

        if not message_info.sender_info and (message_info.user_info or message_info.group_info):
            message_info.sender_info = SenderInfo(
                user_info=message_info.user_info,
                group_info=message_info.group_info,
            )

        sender = message_info.sender_info or SenderInfo()
        sender_user = sender.user_info or message_info.user_info or UserInfo()
        sender_group = sender.group_info or message_info.group_info

        agent_id = cls._extract_agent_id(message_info, message_dict)

        from .chat_stream import get_chat_manager

        chat_manager = get_chat_manager()
        chat_stream = await chat_manager.get_or_create_stream(
            platform=message_info.platform or sender_user.platform or "unknown",
            user_info=sender_user,
            group_info=sender_group,
            agent_id=agent_id,
        )

        # 确保 ChatStream 关联的 Agent 已注册
        try:
            from src.agent.manager import get_agent_manager

            agent_manager = get_agent_manager()
            agent_obj = agent_manager.get_agent(agent_id)
            if agent_obj is None:
                agent_obj = agent_manager.get_agent("default")
            if agent_obj is not None:
                from src.agent.registry import register_agent

                register_agent(agent_obj)
        except ImportError:  # pragma: no cover - 防御性处理
            pass

        if not message_info.receiver_info:
            message_info.receiver_info = chat_stream.build_bot_info(info_cls=ReceiverInfo)
        if not message_info.sender_info:
            message_info.sender_info = SenderInfo(
                group_info=sender_group,
                user_info=sender_user,
            )

        has_sender_user_payload = any(
            [
                getattr(sender_user, "platform", None),
                getattr(sender_user, "user_id", None),
                getattr(sender_user, "user_nickname", None),
                getattr(sender_user, "user_cardname", None),
            ]
        )
        if has_sender_user_payload and not message_info.user_info:
            message_info.user_info = sender_user

        has_sender_group_payload = sender_group and any(
            [
                getattr(sender_group, "platform", None),
                getattr(sender_group, "group_id", None),
                getattr(sender_group, "group_name", None),
            ]
        )
        if has_sender_group_payload and not message_info.group_info:
            message_info.group_info = sender_group

        instance = cls(
            message_info=message_info,
            message_segment=message_segment,
            chat_stream=chat_stream,
            raw_message=raw_message,
            processed_plain_text=message_dict.get("processed_plain_text", ""),
        )
        instance._apply_initial_payload(message_dict)
        return instance

    async def _resolve_segment_text(self, segment: Seg) -> str:
        try:
            if segment.type == "text":
                self.is_picid = False
                self.is_emoji = False
                return segment.data  # type: ignore[return-value]
            if segment.type == "image":
                if isinstance(segment.data, str):
                    self.has_picid = True
                    self.is_picid = True
                    self.is_emoji = False
                    image_manager = get_image_manager()
                    _, processed_text = await image_manager.process_image(segment.data)
                    return processed_text
                return "[发了一张图片，网卡了加载不出来]"
            if segment.type == "emoji":
                self.has_emoji = True
                self.is_emoji = True
                self.is_picid = False
                self.is_voice = False
                if isinstance(segment.data, str):
                    return await get_image_manager().get_emoji_description(segment.data)
                return "[发了一个表情包，网卡了加载不出来]"
            if segment.type == "voice":
                self.is_picid = False
                self.is_emoji = False
                self.is_voice = True
                if isinstance(segment.data, str):
                    return await get_voice_text(segment.data)
                return "[发了一段语音，网卡了加载不出来]"
            if segment.type == "mention_bot":
                self.is_picid = False
                self.is_emoji = False
                self.is_voice = False
                try:
                    self.is_mentioned = float(segment.data)  # type: ignore[arg-type]
                except Exception:
                    self.is_mentioned = True
                return ""
            if segment.type == "priority_info":
                self.is_picid = False
                self.is_emoji = False
                self.is_voice = False
                if isinstance(segment.data, dict):
                    self.priority_mode = "priority"
                    self.priority_info = segment.data
                return ""
            return ""
        except Exception as exc:  # pragma: no cover - 日志兜底
            logger.error(
                "处理消息段失败: %s, 类型: %s, 数据: %s",
                exc,
                segment.type,
                segment.data,
            )
            return f"[处理失败的{segment.type}消息]"


@dataclass
class MessageRecvS4U(MessageRecv):
    def __init__(self, message_dict: dict[str, Any]):
        super().__init__(message_dict)
        self.is_gift = False
        self.is_fake_gift = False
        self.is_superchat = False
        self.gift_info = None
        self.gift_name = None
        self.gift_count: Optional[str] = None
        self.superchat_info = None
        self.superchat_price = None
        self.superchat_message_text = None
        self.is_screen = False
        self.is_internal = False
        self.voice_done = None

        self.chat_info = None

    async def process(self) -> None:
        self.processed_plain_text = await self._process_message_segments(self.message_segment)

    async def _process_single_segment(self, segment: Seg) -> str:
        """处理单个消息段

        Args:
            segment: 消息段

        Returns:
            str: 处理后的文本
        """
        try:
            if segment.type == "text":
                self.is_voice = False
                self.is_picid = False
                self.is_emoji = False
                return segment.data  # type: ignore[return-value]
            if segment.type == "image":
                if isinstance(segment.data, str):
                    self.has_picid = True
                    self.is_picid = True
                    self.is_emoji = False
                    image_manager = get_image_manager()
                    _, processed_text = await image_manager.process_image(segment.data)
                    return processed_text
                return "[发了一张图片，网卡了加载不出来]"
            if segment.type == "emoji":
                self.has_emoji = True
                self.is_emoji = True
                self.is_picid = False
                if isinstance(segment.data, str):
                    return await get_image_manager().get_emoji_description(segment.data)
                return "[发了一个表情包，网卡了加载不出来]"
            if segment.type == "voice":
                self.is_picid = False
                self.is_emoji = False
                self.is_voice = True
                if isinstance(segment.data, str):
                    return await get_voice_text(segment.data)
                return "[发了一段语音，网卡了加载不出来]"
            if segment.type == "mention_bot":
                self.is_picid = False
                self.is_emoji = False
                self.is_voice = False
                try:
                    self.is_mentioned = float(segment.data)  # type: ignore[arg-type]
                except Exception:
                    self.is_mentioned = True
                return ""
            if segment.type == "priority_info":
                self.is_picid = False
                self.is_emoji = False
                if isinstance(segment.data, dict):
                    self.priority_mode = "priority"
                    self.priority_info = segment.data
                return ""
            return ""
        except Exception as exc:  # pragma: no cover - 日志兜底
            logger.error(
                "处理消息段失败: %s, 类型: %s, 数据: %s",
                exc,
                segment.type,
                segment.data,
            )
            return f"[处理失败的{segment.type}消息]"


class MessageSending(MaiMessageBase):
    """发送消息类"""

    def __init__(
        self,
        message_id: str,
        chat_stream: ChatStream,
        bot_user_info: UserInfo,
        sender_info: Optional[UserInfo],
        message_segment: Seg,
        display_message: str = "",
        reply: Optional[MessageRecv] = None,
        is_head: bool = False,
        is_emoji: bool = False,
        thinking_start_time: float = 0,
        apply_set_reply_logic: bool = False,
        reply_to: Optional[str] = None,
        selected_expressions: Optional[List[int]] = None,
        timestamp: Optional[float] = None,
    ):
        message_info = BaseMessageInfo(
            platform=chat_stream.platform,
            message_id=message_id,
            time=timestamp if timestamp is not None else round(time.time(), 3),
            sender_info=chat_stream.build_bot_info(info_cls=SenderInfo),
            receiver_info=chat_stream.build_chat_info(info_cls=ReceiverInfo),
            template_info=None,
            format_info=None,
        )

        super().__init__(
            message_info=message_info,
            message_segment=message_segment,
            chat_stream=chat_stream,
            reply=reply,
        )

        self.sender_info = sender_info
        self.reply_to_message_id = reply.message_info.message_id if reply else None
        self.is_head = is_head
        self.is_emoji = is_emoji
        self.apply_set_reply_logic = apply_set_reply_logic
        self.reply_to = reply_to
        self.display_message = display_message
        self.interest_value = 0.0
        self.selected_expressions = selected_expressions
        self.thinking_start_time = thinking_start_time
        self.thinking_time = 0.0

    def build_reply(self) -> None:
        if self.reply:
            self.reply_to_message_id = self.reply.message_info.message_id
            self.message_segment = Seg(
                type="seglist",
                data=[
                    Seg(type="reply", data=self.reply.message_info.message_id),  # type: ignore[arg-type]
                    self.message_segment,
                ],
            )

    def update_thinking_time(self) -> float:
        self.thinking_time = round(time.time() - self.thinking_start_time, 2)
        return self.thinking_time

    async def _resolve_segment_text(self, segment: Seg) -> str:
        try:
            if segment.type == "text":
                return segment.data  # type: ignore[return-value]
            if segment.type == "image":
                if isinstance(segment.data, str):
                    return await get_image_manager().get_image_description(segment.data)
                return "[图片，网卡了加载不出来]"
            if segment.type == "emoji":
                if isinstance(segment.data, str):
                    return await get_image_manager().get_emoji_tag(segment.data)
                return "[表情，网卡了加载不出来]"
            if segment.type == "voice":
                if isinstance(segment.data, str):
                    return await get_voice_text(segment.data)
                return "[发了一段语音，网卡了加载不出来]"
            if segment.type == "at":
                return f"[@{segment.data}]"
            if segment.type == "reply":
                if self.reply and hasattr(self.reply, "processed_plain_text"):
                    sender_info = self.reply.message_info.sender_info
                    user_info = sender_info.user_info if sender_info else None
                    nickname = user_info.user_nickname if user_info else ""
                    user_id = user_info.user_id if user_info else ""
                    return f"[回复<{nickname}:{user_id}> 的消息：{self.reply.processed_plain_text}]"
                return ""
            return f"[{segment.type}:{segment.data}]"
        except Exception as exc:  # pragma: no cover - 日志兜底
            logger.error(
                "处理发送段失败: %s, 类型: %s, 数据: %s",
                exc,
                segment.type,
                segment.data,
            )
            return f"[处理失败的{segment.type}消息]"

    async def process(self) -> None:
        if self.message_segment:
            self.processed_plain_text = await self._process_message_segments(self.message_segment)

    def is_private_message(self) -> bool:
        receiver = self.message_info.receiver_info
        return not (receiver and receiver.group_info and receiver.group_info.group_id)


class MessageSet:
    """消息集合类，可以存储多个发送消息"""

    def __init__(self, chat_stream: ChatStream, message_id: str):
        self.chat_stream = chat_stream
        self.message_id = message_id
        self.messages: List[MessageSending] = []
        self.time = round(time.time(), 3)

    def add_message(self, message: MessageSending) -> None:
        if not isinstance(message, MessageSending):
            raise TypeError("MessageSet只能添加MessageSending类型的消息")
        self.messages.append(message)
        self.messages.sort(key=lambda x: x.message_info.time or 0.0)

    def get_message_by_index(self, index: int) -> Optional[MessageSending]:
        return self.messages[index] if 0 <= index < len(self.messages) else None

    def get_message_by_time(self, target_time: float) -> Optional[MessageSending]:
        if not self.messages:
            return None
        left, right = 0, len(self.messages) - 1
        while left < right:
            mid = (left + right) // 2
            if (self.messages[mid].message_info.time or 0.0) < target_time:
                left = mid + 1
            else:
                right = mid
        return self.messages[left]

    def clear_messages(self) -> None:
        self.messages.clear()

    def remove_message(self, message: MessageSending) -> bool:
        if message in self.messages:
            self.messages.remove(message)
            return True
        return False

    def __str__(self) -> str:
        return f"MessageSet(id={self.message_id}, count={len(self.messages)})"

    def __len__(self) -> int:
        return len(self.messages)


async def message_recv_from_dict(message_dict: dict[str, Any]) -> MessageRecv:
    return await MessageRecv.from_dict(message_dict)


def message_from_db_dict(db_dict: dict) -> MessageRecv:
    """从数据库字典创建MessageRecv实例"""

    sender_user_data = {
        "platform": db_dict.get("sender_user_platform") or db_dict.get("user_platform"),
        "user_id": db_dict.get("sender_user_id") or db_dict.get("user_id"),
        "user_nickname": db_dict.get("sender_user_nickname") or db_dict.get("user_nickname"),
        "user_cardname": db_dict.get("sender_user_cardname") or db_dict.get("user_cardname"),
    }

    sender_group_data = {
        "platform": db_dict.get("sender_group_platform") or db_dict.get("chat_info_group_platform"),
        "group_id": db_dict.get("sender_group_id") or db_dict.get("chat_info_group_id"),
        "group_name": db_dict.get("sender_group_name") or db_dict.get("chat_info_group_name"),
    }

    receiver_user_data = {
        "platform": db_dict.get("receiver_user_platform"),
        "user_id": db_dict.get("receiver_user_id"),
        "user_nickname": db_dict.get("receiver_user_nickname"),
        "user_cardname": db_dict.get("receiver_user_cardname"),
    }

    receiver_group_data = {
        "platform": db_dict.get("receiver_group_platform"),
        "group_id": db_dict.get("receiver_group_id"),
        "group_name": db_dict.get("receiver_group_name"),
    }

    def _has_meaningful_value(data: Dict[str, Any]) -> bool:
        return any(value not in (None, "") for value in data.values())

    sender_info = SenderInfo(
        user_info=UserInfo.from_dict(sender_user_data) if _has_meaningful_value(sender_user_data) else None,
        group_info=GroupInfo.from_dict(sender_group_data) if _has_meaningful_value(sender_group_data) else None,
    )

    receiver_info = None
    if _has_meaningful_value(receiver_user_data) or _has_meaningful_value(receiver_group_data):
        receiver_info = ReceiverInfo(
            user_info=UserInfo.from_dict(receiver_user_data) if _has_meaningful_value(receiver_user_data) else None,
            group_info=GroupInfo.from_dict(receiver_group_data) if _has_meaningful_value(receiver_group_data) else None,
        )

    chat_stream_dict = {
        "stream_id": db_dict.get("chat_id"),
        "platform": db_dict.get("chat_info_platform"),
        "user_info": {
            "platform": db_dict.get("chat_info_user_platform"),
            "user_id": db_dict.get("chat_info_user_id"),
            "user_nickname": db_dict.get("chat_info_user_nickname"),
            "user_cardname": db_dict.get("chat_info_user_cardname"),
        },
        "group_info": {
            "platform": db_dict.get("chat_info_group_platform"),
            "group_id": db_dict.get("chat_info_group_id"),
            "group_name": db_dict.get("chat_info_group_name"),
        },
        "agent_id": db_dict.get("agent_id", "default"),
        "create_time": db_dict.get("chat_info_create_time", 0.0),
        "last_active_time": db_dict.get("chat_info_last_active_time", 0.0),
    }

    chat_stream = ChatStream.from_dict(chat_stream_dict)

    message_info = BaseMessageInfo(
        platform=db_dict.get("chat_info_platform"),
        message_id=db_dict.get("message_id"),
        time=db_dict.get("time"),
        sender_info=sender_info,
        receiver_info=receiver_info or chat_stream.build_bot_info(info_cls=ReceiverInfo),
    )

    segment = Seg(type="text", data=db_dict.get("processed_plain_text", ""))
    message = MessageRecv(
        message_info=message_info,
        message_segment=segment,
        chat_stream=chat_stream,
        processed_plain_text=db_dict.get("processed_plain_text", ""),
    )

    message.interest_value = db_dict.get("interest_value", 0.0)
    message.is_mentioned = db_dict.get("is_mentioned")
    message.priority_mode = db_dict.get("priority_mode", "interest")
    message.priority_info = db_dict.get("priority_info")
    message.is_emoji = db_dict.get("is_emoji", False)
    message.is_picid = db_dict.get("is_picid", False)

    return message
