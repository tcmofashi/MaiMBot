import re
import json
import traceback
from typing import Union

from maim_message.message import SenderInfo, ReceiverInfo, UserInfo

from src.common.database.database_model import Messages, Images
from src.common.logger import get_logger
from .chat_stream import ChatStream
from .message import MessageSending, MessageRecv

logger = get_logger("message_storage")


class MessageStorage:
    @staticmethod
    def _serialize_keywords(keywords) -> str:
        """将关键词列表序列化为JSON字符串"""
        if isinstance(keywords, list):
            return json.dumps(keywords, ensure_ascii=False)
        return "[]"

    @staticmethod
    def _deserialize_keywords(keywords_str: str) -> list:
        """将JSON字符串反序列化为关键词列表"""
        if not keywords_str:
            return []
        try:
            return json.loads(keywords_str)
        except (json.JSONDecodeError, TypeError):
            return []

    @staticmethod
    async def store_message(message: Union[MessageSending, MessageRecv], chat_stream: ChatStream) -> None:
        """存储消息到数据库"""
        try:
            pattern = r"<MainRule>.*?</MainRule>|<schedule>.*?</schedule>|<UserMessage>.*?</UserMessage>"

            # print(message)

            processed_plain_text = message.processed_plain_text

            # print(processed_plain_text)

            if processed_plain_text:
                processed_plain_text = MessageStorage.replace_image_descriptions(processed_plain_text)
                filtered_processed_plain_text = re.sub(pattern, "", processed_plain_text, flags=re.DOTALL)
            else:
                filtered_processed_plain_text = ""

            if isinstance(message, MessageSending):
                display_message = message.display_message
                if display_message:
                    filtered_display_message = re.sub(pattern, "", display_message, flags=re.DOTALL)
                else:
                    filtered_display_message = ""
                interest_value = 0
                is_mentioned = False
                is_at = False
                reply_probability_boost = 0.0
                reply_to = message.reply_to
                priority_mode = ""
                priority_info = {}
                is_emoji = False
                is_picid = False
                is_notify = False
                is_command = False
                key_words = ""
                key_words_lite = ""
                selected_expressions = message.selected_expressions
            else:
                filtered_display_message = ""
                interest_value = message.interest_value
                is_mentioned = message.is_mentioned
                is_at = message.is_at
                reply_probability_boost = message.reply_probability_boost
                reply_to = ""
                priority_mode = message.priority_mode
                priority_info = message.priority_info
                is_emoji = message.is_emoji
                is_picid = message.is_picid
                is_notify = message.is_notify
                is_command = message.is_command
                # 序列化关键词列表为JSON字符串
                key_words = MessageStorage._serialize_keywords(message.key_words)
                key_words_lite = MessageStorage._serialize_keywords(message.key_words_lite)
                selected_expressions = ""

            chat_info_dict = chat_stream.to_dict()

            sender_info = message.message_info.sender_info or SenderInfo()
            sender_user = sender_info.user_info or UserInfo()
            sender_group = sender_info.group_info

            receiver_info = message.message_info.receiver_info or ReceiverInfo()
            receiver_user = receiver_info.user_info
            receiver_group = receiver_info.group_info

            sender_user_dict = sender_user.to_dict()
            sender_group_dict = sender_group.to_dict() if sender_group else {}
            receiver_user_dict = receiver_user.to_dict() if receiver_user else {}
            receiver_group_dict = receiver_group.to_dict() if receiver_group else {}

            # message_id 现在是 TextField，直接使用字符串值
            msg_id = message.message_info.message_id

            # 安全地获取 group_info, 如果为 None 则视为空字典
            group_info_from_chat = chat_info_dict.get("group_info") or {}
            # 安全地获取 user_info, 如果为 None 则视为空字典 (以防万一)
            user_info_from_chat = chat_info_dict.get("user_info") or {}

            # 获取隔离信息 - 从chat_stream中获取租户和智能体信息
            tenant_id = getattr(chat_stream, "tenant_id", None) or "default"
            agent_id = getattr(chat_stream, "agent_id", None) or "default"
            platform = getattr(chat_stream, "platform", "unknown")
            chat_stream_id = getattr(chat_stream, "stream_id", "unknown")

            # 额外防御：确保这些值不为None或空
            if not tenant_id or not isinstance(tenant_id, str):
                logger.warning(f"ChatStream缺少有效的tenant_id，使用默认值: {tenant_id}")
                tenant_id = "default"
            if not agent_id or not isinstance(agent_id, str):
                logger.warning(f"ChatStream缺少有效的agent_id，使用默认值: {agent_id}")
                agent_id = "default"

            Messages.create(
                # T+A+C+P 四维隔离字段
                tenant_id=tenant_id,
                agent_id=agent_id,
                platform=platform,
                chat_stream_id=chat_stream_id,
                message_id=msg_id,
                time=float(message.message_info.time),  # type: ignore
                chat_id=chat_stream.stream_id,
                # Flattened chat_info
                reply_to=reply_to,
                is_mentioned=is_mentioned,
                is_at=is_at,
                reply_probability_boost=reply_probability_boost,
                chat_info_stream_id=chat_info_dict.get("stream_id"),
                chat_info_platform=chat_info_dict.get("platform"),
                chat_info_user_platform=user_info_from_chat.get("platform"),
                chat_info_user_id=user_info_from_chat.get("user_id"),
                chat_info_user_nickname=user_info_from_chat.get("user_nickname"),
                chat_info_user_cardname=user_info_from_chat.get("user_cardname"),
                chat_info_group_platform=group_info_from_chat.get("platform"),
                chat_info_group_id=group_info_from_chat.get("group_id"),
                chat_info_group_name=group_info_from_chat.get("group_name"),
                chat_info_create_time=float(chat_info_dict.get("create_time", 0.0)),
                chat_info_last_active_time=float(chat_info_dict.get("last_active_time", 0.0)),
                # Flattened sender info
                user_platform=sender_user_dict.get("platform"),
                user_id=sender_user_dict.get("user_id"),
                user_nickname=sender_user_dict.get("user_nickname"),
                user_cardname=sender_user_dict.get("user_cardname"),
                sender_user_platform=sender_user_dict.get("platform"),
                sender_user_id=sender_user_dict.get("user_id"),
                sender_user_nickname=sender_user_dict.get("user_nickname"),
                sender_user_cardname=sender_user_dict.get("user_cardname"),
                sender_group_platform=sender_group_dict.get("platform"),
                sender_group_id=sender_group_dict.get("group_id"),
                sender_group_name=sender_group_dict.get("group_name"),
                receiver_user_platform=receiver_user_dict.get("platform"),
                receiver_user_id=receiver_user_dict.get("user_id"),
                receiver_user_nickname=receiver_user_dict.get("user_nickname"),
                receiver_user_cardname=receiver_user_dict.get("user_cardname"),
                receiver_group_platform=receiver_group_dict.get("platform"),
                receiver_group_id=receiver_group_dict.get("group_id"),
                receiver_group_name=receiver_group_dict.get("group_name"),
                # Text content
                processed_plain_text=filtered_processed_plain_text,
                display_message=filtered_display_message,
                interest_value=interest_value,
                priority_mode=priority_mode,
                priority_info=priority_info,
                is_emoji=is_emoji,
                is_picid=is_picid,
                is_notify=is_notify,
                is_command=is_command,
                key_words=key_words,
                key_words_lite=key_words_lite,
                selected_expressions=selected_expressions,
            )
        except Exception:
            logger.exception("存储消息失败")
            logger.error(f"消息：{message}")
            traceback.print_exc()

    # 如果需要其他存储相关的函数，可以在这里添加
    @staticmethod
    def update_message(mmc_message_id: str | None, qq_message_id: str | None) -> bool:
        """实时更新数据库的自身发送消息ID"""
        try:
            if not qq_message_id:
                logger.info("消息不存在message_id，无法更新")
                return False
            if matched_message := (
                Messages.select().where((Messages.message_id == mmc_message_id)).order_by(Messages.time.desc()).first()
            ):
                # 更新找到的消息记录
                Messages.update(message_id=qq_message_id).where(Messages.id == matched_message.id).execute()  # type: ignore
                logger.debug(f"更新消息ID成功: {matched_message.message_id} -> {qq_message_id}")
                return True
            else:
                logger.debug("未找到匹配的消息")
                return False

        except Exception as e:
            logger.error(f"更新消息ID失败: {e}")
            return False

    @staticmethod
    def replace_image_descriptions(text: str) -> str:
        """将[图片：描述]替换为[picid:image_id]"""
        # 先检查文本中是否有图片标记
        pattern = r"\[图片：([^\]]+)\]"
        matches = re.findall(pattern, text)

        if not matches:
            logger.debug("文本中没有图片标记，直接返回原文本")
            return text

        def replace_match(match):
            description = match.group(1).strip()
            try:
                image_record = (
                    Images.select().where(Images.description == description).order_by(Images.timestamp.desc()).first()
                )
                return f"[picid:{image_record.image_id}]" if image_record else match.group(0)
            except Exception:
                return match.group(0)

        return re.sub(r"\[图片：([^\]]+)\]", replace_match, text)
