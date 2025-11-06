import asyncio
import hashlib
import time
from typing import Dict, Optional, TYPE_CHECKING, List
from rich.traceback import install
from maim_message import GroupInfo, UserInfo, SenderInfo, ReceiverInfo

from src.common.logger import get_logger
from src.common.database.database import db
from src.common.database.database_model import ChatStreams  # 新增导入

# 避免循环导入，使用TYPE_CHECKING进行类型提示
if TYPE_CHECKING:
    from .message import MessageRecv
    from src.agent.agent import Agent
    from src.config.config import Config


install(extra_lines=3)


logger = get_logger("chat_stream")


class ChatMessageContext:
    """聊天消息上下文，存储消息的上下文信息"""

    def __init__(self, message: "MessageRecv"):
        self.message = message

    def get_template_name(self) -> Optional[str]:
        """获取模板名称"""
        if self.message.message_info.template_info and not self.message.message_info.template_info.template_default:
            return self.message.message_info.template_info.template_name  # type: ignore
        return None

    def get_last_message(self) -> "MessageRecv":
        """获取最后一条消息"""
        return self.message

    def check_types(self, types: list) -> bool:
        # sourcery skip: invert-any-all, use-any, use-next
        """检查消息类型"""
        if not self.message.message_info.format_info.accept_format:  # type: ignore
            return False
        for t in types:
            if t not in self.message.message_info.format_info.accept_format:  # type: ignore
                return False
        return True

    def get_priority_mode(self) -> str:
        """获取优先级模式"""
        return self.message.priority_mode

    def get_priority_info(self) -> Optional[dict]:
        """获取优先级信息"""
        if hasattr(self.message, "priority_info") and self.message.priority_info:
            return self.message.priority_info
        return None


class ChatStream:
    """聊天流对象，存储一个完整的聊天上下文"""

    def __init__(
        self,
        stream_id: str,
        platform: str,
        user_info: UserInfo,
        group_info: Optional[GroupInfo] = None,
        agent_id: str = "default",
        data: Optional[dict] = None,
    ):
        self.stream_id = stream_id
        self.platform = platform
        self.user_info = user_info
        self.group_info = group_info
        self._agent_id = "default"
        self._config_cache: Optional["Config"] = None
        self._config_cache_base_id: Optional[int] = None
        self._agent_cache: Optional["Agent"] = None
        self.agent_id = data.get("agent_id", agent_id) if data else agent_id
        self.create_time = data.get("create_time", time.time()) if data else time.time()
        self.last_active_time = data.get("last_active_time", self.create_time) if data else self.create_time
        self.saved = False
        self.context: ChatMessageContext = None  # type: ignore # 用于存储该聊天的上下文信息

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @agent_id.setter
    def agent_id(self, value: str) -> None:
        normalized = str(value) if value else "default"
        if getattr(self, "_agent_id", None) == normalized:
            return
        self._agent_id = normalized
        self._config_cache = None
        self._config_cache_base_id = None
        self._agent_cache = None

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "stream_id": self.stream_id,
            "platform": self.platform,
            "user_info": self.user_info.to_dict() if self.user_info else None,
            "group_info": self.group_info.to_dict() if self.group_info else None,
            "agent_id": self.agent_id,
            "create_time": self.create_time,
            "last_active_time": self.last_active_time,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ChatStream":
        """从字典创建实例"""
        user_info = UserInfo.from_dict(data.get("user_info", {})) if data.get("user_info") else None
        group_info = GroupInfo.from_dict(data.get("group_info", {})) if data.get("group_info") else None
        agent_id = data.get("agent_id", "default")

        return cls(
            stream_id=data["stream_id"],
            platform=data["platform"],
            user_info=user_info,  # type: ignore
            group_info=group_info,
            agent_id=agent_id,
            data=data,
        )

    def clone(self) -> "ChatStream":
        """创建当前聊天流的独立副本，避免外部修改影响缓存。"""

        cloned = ChatStream.from_dict(self.to_dict())
        cloned.context = self.context
        return cloned

    def update_active_time(self):
        """更新最后活跃时间"""
        self.last_active_time = time.time()
        self.saved = False

    def set_context(self, message: "MessageRecv"):
        """设置聊天消息上下文"""
        self.context = ChatMessageContext(message)

    def build_bot_info(self, info_cls: type[SenderInfo] | type[ReceiverInfo] = SenderInfo):
        """构造当前聊天流中机器人侧的 Info 对象。"""

        cfg = self.get_effective_config()
        agent = self.get_agent()

        agent_name = agent.name if agent else None
        agent_identifier = agent.agent_id if agent else None

        nickname = agent_name or getattr(cfg.bot, "nickname", None) or "Mai"
        user_id = agent_identifier or getattr(cfg.bot, "qq_account", None) or self.agent_id
        bot_user = UserInfo(
            platform=self.platform,
            user_id=str(user_id),
            user_nickname=nickname,
            user_cardname=nickname,
        )
        group = None
        if self.group_info:
            group = GroupInfo.from_dict(self.group_info.to_dict())
        return info_cls(group_info=group, user_info=bot_user)

    def build_chat_info(self, info_cls: type[SenderInfo] | type[ReceiverInfo] = ReceiverInfo):
        """构造当前聊天流对端的 Info 对象。"""

        if self.group_info:
            group = GroupInfo.from_dict(self.group_info.to_dict())
            return info_cls(group_info=group, user_info=None)

        user = None
        if self.user_info:
            user = UserInfo.from_dict(self.user_info.to_dict())
        return info_cls(group_info=None, user_info=user)

    def get_effective_config(self, *, refresh: bool = False):
        """返回当前聊天流对应的配置（包含 Agent 覆盖）。"""

        from src.config.config import global_config
        from src.agent.registry import resolve_agent_config

        base_config = global_config
        base_id = id(base_config)

        if not refresh and self._config_cache is not None and self._config_cache_base_id == base_id:
            logger.info("ChatStream[%s] 使用缓存配置 agent_id=%s", self.stream_id, self.agent_id)
            return self._config_cache

        merged_config = resolve_agent_config(self.agent_id, base_config)

        self._config_cache = merged_config
        self._config_cache_base_id = base_id
        logger.info("ChatStream[%s] 重新构建配置 agent_id=%s base_id=%s", self.stream_id, self.agent_id, base_id)
        return merged_config

    def get_agent(self, *, refresh: bool = False) -> Optional["Agent"]:
        """获取当前聊天流关联的 Agent 对象。"""

        if not refresh and self._agent_cache is not None:
            return self._agent_cache

        agent_obj: Optional["Agent"] = None
        used_default = False
        try:
            from src.agent.manager import get_agent_manager

            agent_manager = get_agent_manager()
            agent_obj = agent_manager.get_agent(self.agent_id)

            if agent_obj is None and self.agent_id != "default":
                agent_obj = agent_manager.get_agent("default")
                used_default = agent_obj is not None

        except ImportError:  # pragma: no cover - 防御性处理
            agent_obj = None

        self._agent_cache = agent_obj
        if agent_obj is None:
            logger.info("ChatStream[%s] 未找到可用 Agent，agent_id=%s", self.stream_id, self.agent_id)
        else:
            logger.info(
                "ChatStream[%s] 获取 Agent 成功 agent_id=%s (fallback_default=%s)",
                self.stream_id,
                agent_obj.agent_id,
                used_default,
            )
        return agent_obj

    @property
    def agent(self) -> Optional["Agent"]:
        """Convenience property for accessing the current Agent 对象。"""

        return self.get_agent()


class ChatManager:
    """聊天管理器，管理所有聊天流"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.streams: Dict[str, ChatStream] = {}  # stream_id -> ChatStream
            self.last_messages: Dict[str, "MessageRecv"] = {}  # stream_id -> last_message
            try:
                db.connect(reuse_if_open=True)
                # 确保 ChatStreams 表存在
                db.create_tables([ChatStreams], safe=True)
            except Exception as e:
                logger.error(f"数据库连接或 ChatStreams 表创建失败: {e}")

            self._initialized = True
            # 在事件循环中启动初始化
            # asyncio.create_task(self._initialize())
            # # 启动自动保存任务
            # asyncio.create_task(self._auto_save_task())

    async def _initialize(self):
        """异步初始化"""
        try:
            await self.load_all_streams()
            logger.info(f"聊天管理器已启动，已加载 {len(self.streams)} 个聊天流")
        except Exception as e:
            logger.error(f"聊天管理器启动失败: {str(e)}")

    async def _auto_save_task(self):
        """定期自动保存所有聊天流"""
        while True:
            await asyncio.sleep(300)  # 每5分钟保存一次
            try:
                await self._save_all_streams()
                logger.info("聊天流自动保存完成")
            except Exception as e:
                logger.error(f"聊天流自动保存失败: {str(e)}")

    def register_message(self, message: "MessageRecv"):
        """注册消息到聊天流"""

        agent_id = "default"
        if message.message_info.receiver_info and message.message_info.receiver_info.user_info:
            candidate_id = str(message.message_info.receiver_info.user_info.user_id or "default")

            try:
                from src.agent.manager import get_agent_manager

                agent_manager = get_agent_manager()
                if agent_manager.agent_exists(candidate_id):
                    agent_id = candidate_id
            except ImportError:  # pragma: no cover - 防御性处理
                agent_id = candidate_id or "default"

        sender_info = message.message_info.sender_info
        user_info = sender_info.user_info if sender_info else message.message_info.user_info
        group_info = sender_info.group_info if sender_info else message.message_info.group_info

        if message.chat_stream:
            stream_id = message.chat_stream.stream_id
        else:
            try:
                stream_id = self._generate_stream_id(
                    platform=message.message_info.platform or "unknown",
                    user_info=user_info,
                    group_info=group_info,
                    agent_id=agent_id,
                )
            except ValueError as exc:
                logger.error(f"无法注册消息对应的聊天流: {exc}")
                return

        if message.chat_stream and stream_id not in self.streams:
            # 缓存未命中但消息中已有chat_stream，存入缓存便于后续扩展
            cached_stream = message.chat_stream.clone()
            cached_stream.set_context(message)
            self.streams[stream_id] = cached_stream
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._save_stream(cached_stream))
            except RuntimeError:
                # 当前上下文没有事件循环，延迟保存将由后续异步流程完成
                pass
        elif stream_id in self.streams:
            self.streams[stream_id].set_context(message)

        self.last_messages[stream_id] = message

    @staticmethod
    def _generate_stream_id(
        platform: str,
        user_info: Optional[UserInfo],
        group_info: Optional[GroupInfo] = None,
        agent_id: str = "default",
    ) -> str:
        """生成聊天流唯一ID"""
        if not user_info and not group_info:
            raise ValueError("用户信息或群组信息必须提供以构造chat_stream")

        def _normalize(value: Optional[str], fallback: str) -> str:
            if value is None or value == "":
                return fallback
            return str(value)

        norm_agent = _normalize(agent_id, "default")
        norm_platform = _normalize(platform, "unknown")

        components = [norm_agent]
        if group_info:
            norm_group = _normalize(group_info.group_id, "unknown_group")
            components.extend([norm_platform, norm_group])
        else:
            if not user_info or not user_info.user_id:
                raise ValueError("私聊chat_stream需要提供有效的用户ID")
            norm_user = _normalize(user_info.user_id, "unknown_user")
            components.extend([norm_platform, norm_user, "private"])

        # 使用MD5生成唯一ID
        key = "_".join(components)
        return hashlib.md5(key.encode()).hexdigest()

    def get_stream_id(self, platform: str, id: str, is_group: bool = True, agent_id: str = "default") -> str:
        """获取聊天流ID"""
        user_info = UserInfo(platform=platform, user_id=id) if not is_group else None
        group_info = GroupInfo(platform=platform, group_id=id) if is_group else None
        return self._generate_stream_id(
            platform=platform,
            user_info=user_info,
            group_info=group_info,
            agent_id=agent_id,
        )

    async def get_or_create_stream(
        self,
        platform: str,
        user_info: UserInfo,
        group_info: Optional[GroupInfo] = None,
        agent_id: str = "default",
    ) -> ChatStream:
        """获取或创建聊天流

        Args:
            platform: 平台标识
            user_info: 用户信息
            group_info: 群组信息（可选）

        Returns:
            ChatStream: 聊天流对象
        """
        # 生成stream_id
        try:
            stream_id = self._generate_stream_id(platform, user_info, group_info, agent_id=agent_id)

            stream = self.streams.get(stream_id)
            if not stream:

                def _db_find_stream_sync(s_id: str):
                    return ChatStreams.get_or_none(ChatStreams.stream_id == s_id)

                model_instance = await asyncio.to_thread(_db_find_stream_sync, stream_id)

                if model_instance:
                    user_info_data = {
                        "platform": model_instance.user_platform,
                        "user_id": model_instance.user_id,
                        "user_nickname": model_instance.user_nickname,
                        "user_cardname": model_instance.user_cardname or "",
                    }
                    group_info_data = None
                    if model_instance.group_id:
                        group_info_data = {
                            "platform": model_instance.group_platform,
                            "group_id": model_instance.group_id,
                            "group_name": model_instance.group_name,
                        }

                    stream = ChatStream.from_dict(
                        {
                            "stream_id": model_instance.stream_id,
                            "platform": model_instance.platform,
                            "user_info": user_info_data,
                            "group_info": group_info_data,
                            "agent_id": getattr(model_instance, "agent_id", agent_id),
                            "create_time": model_instance.create_time,
                            "last_active_time": model_instance.last_active_time,
                        }
                    )
                    stream.saved = True
                else:
                    stream = ChatStream(
                        stream_id=stream_id,
                        platform=platform,
                        user_info=user_info,
                        group_info=group_info,
                        agent_id=agent_id,
                    )

            # 用最新信息更新缓存中的stream
            if user_info and user_info.user_id:
                stream.user_info = user_info
            if group_info:
                stream.group_info = group_info
            stream.agent_id = agent_id or stream.agent_id
            stream.update_active_time()

            from .message import MessageRecv  # 延迟导入，避免循环引用

            context_msg = self.last_messages.get(stream_id)
            if context_msg and isinstance(context_msg, MessageRecv):
                stream.set_context(context_msg)

            # 保存至缓存与数据库
            self.streams[stream_id] = stream
            await self._save_stream(stream)

            return stream.clone()

        except Exception as e:
            logger.error(f"获取或创建聊天流失败: {e}", exc_info=True)
            raise e

    def get_stream(self, stream_id: str) -> Optional[ChatStream]:
        """通过stream_id获取聊天流"""

        stream = self.streams.get(stream_id)
        if not stream:
            model_instance = ChatStreams.get_or_none(ChatStreams.stream_id == stream_id)
            if not model_instance:
                return None
            user_info_data = {
                "platform": model_instance.user_platform,
                "user_id": model_instance.user_id,
                "user_nickname": model_instance.user_nickname,
                "user_cardname": model_instance.user_cardname or "",
            }
            group_info_data = None
            if model_instance.group_id:
                group_info_data = {
                    "platform": model_instance.group_platform,
                    "group_id": model_instance.group_id,
                    "group_name": model_instance.group_name,
                }
            stream = ChatStream.from_dict(
                {
                    "stream_id": model_instance.stream_id,
                    "platform": model_instance.platform,
                    "user_info": user_info_data,
                    "group_info": group_info_data,
                    "agent_id": getattr(model_instance, "agent_id", "default"),
                    "create_time": model_instance.create_time,
                    "last_active_time": model_instance.last_active_time,
                }
            )
            stream.saved = True
            self.streams[stream_id] = stream

        if stream_id in self.last_messages:
            stream.set_context(self.last_messages[stream_id])

        return stream.clone()

    def get_stream_by_info(
        self,
        platform: str,
        user_info: UserInfo,
        group_info: Optional[GroupInfo] = None,
        agent_id: str = "default",
    ) -> Optional[ChatStream]:
        """通过信息获取聊天流"""
        stream_id = self._generate_stream_id(platform, user_info, group_info, agent_id=agent_id)
        return self.get_stream(stream_id)

    def list_streams(self) -> List[ChatStream]:
        """获取当前缓存中的所有聊天流副本。"""

        return [stream.clone() for stream in self.streams.values()]

    def get_stream_name(self, stream_id: str) -> Optional[str]:
        """根据 stream_id 获取聊天流名称"""
        stream = self.get_stream(stream_id)
        if not stream:
            return None

        if stream.group_info and stream.group_info.group_name:
            return stream.group_info.group_name
        elif stream.user_info and stream.user_info.user_nickname:
            return f"{stream.user_info.user_nickname}的私聊"
        else:
            return None

    @staticmethod
    async def _save_stream(stream: ChatStream):
        """保存聊天流到数据库"""
        if stream.saved:
            return
        stream_data_dict = stream.to_dict()

        def _db_save_stream_sync(s_data_dict: dict):
            user_info_d = s_data_dict.get("user_info")
            group_info_d = s_data_dict.get("group_info")

            fields_to_save = {
                "platform": s_data_dict["platform"],
                "create_time": s_data_dict["create_time"],
                "last_active_time": s_data_dict["last_active_time"],
                "agent_id": s_data_dict.get("agent_id"),
                "user_platform": user_info_d["platform"] if user_info_d else "",
                "user_id": user_info_d["user_id"] if user_info_d else "",
                "user_nickname": user_info_d["user_nickname"] if user_info_d else "",
                "user_cardname": user_info_d.get("user_cardname", "") if user_info_d else None,
                "group_platform": group_info_d["platform"] if group_info_d else "",
                "group_id": group_info_d["group_id"] if group_info_d else "",
                "group_name": group_info_d["group_name"] if group_info_d else "",
            }

            ChatStreams.replace(stream_id=s_data_dict["stream_id"], **fields_to_save).execute()

        try:
            await asyncio.to_thread(_db_save_stream_sync, stream_data_dict)
            stream.saved = True
        except Exception as e:
            logger.error(f"保存聊天流 {stream.stream_id} 到数据库失败 (Peewee): {e}", exc_info=True)

    async def _save_all_streams(self):
        """保存所有聊天流"""
        for stream in self.streams.values():
            await self._save_stream(stream)

    async def load_all_streams(self):
        """从数据库加载所有聊天流"""
        logger.info("正在从数据库加载所有聊天流")

        def _db_load_all_streams_sync():
            loaded_streams_data = []
            for model_instance in ChatStreams.select():
                user_info_data = {
                    "platform": model_instance.user_platform,
                    "user_id": model_instance.user_id,
                    "user_nickname": model_instance.user_nickname,
                    "user_cardname": model_instance.user_cardname or "",
                }
                group_info_data = None
                if model_instance.group_id:
                    group_info_data = {
                        "platform": model_instance.group_platform,
                        "group_id": model_instance.group_id,
                        "group_name": model_instance.group_name,
                    }

                data_for_from_dict = {
                    "stream_id": model_instance.stream_id,
                    "platform": model_instance.platform,
                    "user_info": user_info_data,
                    "group_info": group_info_data,
                    "agent_id": getattr(model_instance, "agent_id", "default"),
                    "create_time": model_instance.create_time,
                    "last_active_time": model_instance.last_active_time,
                }
                loaded_streams_data.append(data_for_from_dict)
            return loaded_streams_data

        try:
            all_streams_data_list = await asyncio.to_thread(_db_load_all_streams_sync)
            self.streams.clear()
            for data in all_streams_data_list:
                stream = ChatStream.from_dict(data)
                stream.saved = True
                self.streams[stream.stream_id] = stream
                if stream.stream_id in self.last_messages:
                    stream.set_context(self.last_messages[stream.stream_id])
        except Exception as e:
            logger.error(f"从数据库加载所有聊天流失败 (Peewee): {e}", exc_info=True)


chat_manager = None


def get_chat_manager():
    global chat_manager
    if chat_manager is None:
        chat_manager = ChatManager()
    return chat_manager


def resolve_config_for_stream(stream_id: Optional[str] = None):
    """Get the effective configuration for the specified chat stream.

    Falls back to the global configuration when the stream is missing.
    """

    try:
        if stream_id:
            manager = get_chat_manager()
            stream = manager.get_stream(stream_id)
            if stream:
                return stream.get_effective_config()
    except Exception:
        logger.debug("resolve_config_for_stream: 使用全局配置作为回退", exc_info=True)

    from src.config.config import global_config  # 延迟导入以避免循环引用

    return global_config
