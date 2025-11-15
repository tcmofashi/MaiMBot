"""
隔离化的聊天流管理器
支持T+A+C+P四维隔离：租户(T) + 智能体(A) + 聊天流(C) + 平台(P)
"""

import asyncio
import hashlib
import time
from typing import Dict, Optional, TYPE_CHECKING
from rich.traceback import install
from maim_message import GroupInfo, UserInfo, SenderInfo, ReceiverInfo

from .isolation_context import IsolationContext, generate_isolated_id

# 避免循环导入，使用TYPE_CHECKING进行类型提示
if TYPE_CHECKING:
    from ..chat.message_receive.message import MessageRecv
    from ..agent.agent import Agent
    from ..config.config import Config

install(extra_lines=3)


from src.common.logger import get_logger

logger = get_logger("isolated_chat_stream")


class IsolatedChatMessageContext:
    """隔离化的聊天消息上下文，存储消息的上下文信息"""

    def __init__(self, message: "MessageRecv", isolation_context: IsolationContext):
        self.message = message
        self.isolation_context = isolation_context

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


class IsolatedChatStream:
    """隔离化的聊天流对象，支持T+A+C+P四维隔离"""

    def __init__(
        self,
        stream_id: str,
        platform: str,
        user_info: UserInfo,
        group_info: Optional[GroupInfo] = None,
        agent_id: str = "default",
        isolation_context: Optional[IsolationContext] = None,
        data: Optional[dict] = None,
    ):
        # 基础字段
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

        # 隔离上下文
        self.isolation_context = isolation_context
        self.context: Optional[IsolatedChatMessageContext] = None

        # 如果没有提供隔离上下文，从参数中创建
        if not self.isolation_context:
            # 从数据中提取租户ID
            tenant_id = data.get("tenant_id") if data else None
            chat_stream_id = data.get("chat_stream_id") if data else None

            if tenant_id:
                self.isolation_context = generate_isolated_id(
                    f"stream_{stream_id}",
                    IsolationContext(tenant_id, agent_id, platform, chat_stream_id),
                    "chat_stream",
                )[1]  # 提取scope部分
                # 注意：这里需要创建IsolationContext实例，但现在先简化处理
                from .isolation_context import create_isolation_context

                self.isolation_context = create_isolation_context(
                    tenant_id=tenant_id, agent_id=agent_id, platform=platform, chat_stream_id=chat_stream_id
                )

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

    @property
    def tenant_id(self) -> Optional[str]:
        """获取租户ID"""
        return self.isolation_context.tenant_id if self.isolation_context else None

    def get_isolation_scope(self) -> str:
        """获取隔离范围"""
        return str(self.isolation_context.scope) if self.isolation_context else "unknown"

    def to_dict(self) -> dict:
        """转换为字典格式"""
        result = {
            "stream_id": self.stream_id,
            "platform": self.platform,
            "user_info": self.user_info.to_dict() if self.user_info else None,
            "group_info": self.group_info.to_dict() if self.group_info else None,
            "agent_id": self.agent_id,
            "create_time": self.create_time,
            "last_active_time": self.last_active_time,
        }

        # 添加隔离字段
        if self.isolation_context:
            result.update(
                {
                    "tenant_id": self.isolation_context.tenant_id,
                    "platform": self.isolation_context.platform,
                    "chat_stream_id": self.isolation_context.chat_stream_id,
                    "isolation_scope": str(self.isolation_context.scope),
                    "isolation_level": self.isolation_context.get_isolation_level().value,
                }
            )

        return result

    @classmethod
    def from_dict(cls, data: dict) -> "IsolatedChatStream":
        """从字典创建实例"""
        user_info = UserInfo.from_dict(data.get("user_info", {})) if data.get("user_info") else None
        group_info = GroupInfo.from_dict(data.get("group_info", {})) if data.get("group_info") else None
        agent_id = data.get("agent_id", "default")
        tenant_id = data.get("tenant_id")
        chat_stream_id = data.get("chat_stream_id")

        # 创建隔离上下文
        isolation_context = None
        if tenant_id:
            from .isolation_context import create_isolation_context

            isolation_context = create_isolation_context(
                tenant_id=tenant_id, agent_id=agent_id, platform=data.get("platform"), chat_stream_id=chat_stream_id
            )

        return cls(
            stream_id=data["stream_id"],
            platform=data["platform"],
            user_info=user_info,  # type: ignore
            group_info=group_info,
            agent_id=agent_id,
            isolation_context=isolation_context,
            data=data,
        )

    def clone(self) -> "IsolatedChatStream":
        """创建当前聊天流的独立副本，避免外部修改影响缓存。"""
        cloned = IsolatedChatStream.from_dict(self.to_dict())
        cloned.context = self.context
        return cloned

    def update_active_time(self):
        """更新最后活跃时间"""
        self.last_active_time = time.time()
        self.saved = False

    def set_context(self, message: "MessageRecv"):
        """设置聊天消息上下文"""
        if self.isolation_context:
            self.context = IsolatedChatMessageContext(message, self.isolation_context)
        else:
            self.context = IsolatedChatMessageContext(message, None)

    def build_bot_info(self, info_cls: type[SenderInfo] | type[ReceiverInfo] = SenderInfo):
        """构造当前聊天流中机器人侧的 Info 对象。"""

        cfg = self.get_effective_config()
        return info_cls(
            user_info=UserInfo(
                platform=self.platform,
                user_id=cfg.bot.user_id if cfg.bot else "Mai",
                user_nickname=cfg.bot.nickname if cfg.bot else "Mai",
                user_cardname=cfg.bot.cardname if cfg.bot else "AI助手",
            ),
            group_info=(
                GroupInfo(
                    platform=self.platform,
                    group_id=self.group_info.group_id if self.group_info else "",
                    group_name=self.group_info.group_name if self.group_info else "群聊",
                )
                if self.group_info
                else None
            ),
        )

    def get_effective_config(self) -> "Config":
        """获取有效的配置（支持隔离上下文）"""
        if self.isolation_context and hasattr(self.isolation_context, "get_config_manager"):
            try:
                config_manager = self.isolation_context.get_config_manager()
                return config_manager.get_isolated_config()
            except Exception as e:
                logger.warning(f"获取隔离配置失败，使用默认配置: {e}")

        # 回退到原有逻辑
        from ..agent.manager import get_agent_manager
        from ..config.config import get_bot_config

        if self._agent_cache is None or self._config_cache_base_id != id(self):
            try:
                agent_manager = get_agent_manager()
                self._agent_cache = agent_manager.get_agent(self.agent_id)
                self._config_cache = get_bot_config(self._agent_cache.config_name if self._agent_cache else "default")
                self._config_cache_base_id = id(self)
            except Exception as e:
                logger.error(f"获取配置失败: {e}")
                from ..config.config import global_config

                self._config_cache = global_config
                self._agent_cache = None

        return self._config_cache

    def get_chat_info(self) -> Dict[str, any]:
        """获取聊天信息（支持隔离）"""
        info = {
            "stream_id": self.stream_id,
            "platform": self.platform,
            "create_time": self.create_time,
            "last_active_time": self.last_active_time,
            "agent_id": self.agent_id,
        }

        if self.isolation_context:
            info.update(
                {
                    "tenant_id": self.isolation_context.tenant_id,
                    "isolation_scope": str(self.isolation_context.scope),
                    "isolation_level": self.isolation_context.get_isolation_level().value,
                }
            )

        if self.group_info:
            info.update(
                {
                    "chat_info_group_platform": self.group_info.platform,
                    "chat_info_group_id": self.group_info.group_id,
                    "chat_info_group_name": self.group_info.group_name,
                }
            )

        if self.user_info:
            info.update(
                {
                    "chat_info_user_platform": self.user_info.platform,
                    "chat_info_user_id": self.user_info.user_id,
                    "chat_info_user_nickname": self.user_info.user_nickname,
                    "chat_info_user_cardname": self.user_info.user_cardname,
                }
            )

        return info

    async def save(self) -> bool:
        """保存聊天流到数据库"""
        try:
            from ..common.database.database_model import ChatStreams

            # 准备数据
            stream_data = {
                "stream_id": self.stream_id,
                "platform": self.platform,
                "agent_id": self.agent_id,
                "create_time": self.create_time,
                "last_active_time": self.last_active_time,
                # 新增隔离字段
                "tenant_id": self.tenant_id,
                "chat_stream_id": self.stream_id,  # 保持一致性
            }

            if self.group_info:
                stream_data.update(
                    {
                        "group_id": self.group_info.group_id,
                        "group_name": self.group_info.group_name,
                    }
                )

            # 使用带租户ID的模型查询
            filter_dict = {"stream_id": self.stream_id}
            if self.tenant_id:
                filter_dict["tenant_id"] = self.tenant_id

            # 查找现有记录
            existing = ChatStreams.get_or_none(**filter_dict)

            if existing:
                # 更新现有记录
                for key, value in stream_data.items():
                    if hasattr(existing, key):
                        setattr(existing, key, value)
                existing.save()
                logger.debug(f"更新聊天流 {self.stream_id} 到数据库")
            else:
                # 创建新记录
                ChatStreams.create(**stream_data)
                logger.debug(f"保存新聊天流 {self.stream_id} 到数据库")

            self.saved = True
            return True

        except Exception as e:
            logger.error(f"保存聊天流失败 {self.stream_id}: {e}")
            return False

    def __str__(self) -> str:
        """字符串表示"""
        scope_str = f" ({self.get_isolation_scope()})" if self.isolation_context else ""
        return f"IsolatedChatStream({self.stream_id}{scope_str})"

    def __repr__(self) -> str:
        """调试表示"""
        return self.__str__()


class IsolatedChatManager:
    """隔离化的聊天管理器，管理特定租户+智能体组合的所有聊天流"""

    def __init__(self, tenant_id: str, agent_id: str):
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.streams: Dict[str, IsolatedChatStream] = {}  # stream_id -> IsolatedChatStream
        self.last_messages: Dict[str, "MessageRecv"] = {}  # stream_id -> last_message
        self._initialized = False

    async def initialize(self):
        """异步初始化"""
        if not self._initialized:
            try:
                await self._load_all_streams()
                logger.info(
                    f"隔离化聊天管理器已启动 (租户: {self.tenant_id}, 智能体: {self.agent_id})，已加载 {len(self.streams)} 个聊天流"
                )
                self._initialized = True
            except Exception as e:
                logger.error(f"隔离化聊天管理器启动失败: {e}")

    async def _load_all_streams(self):
        """从数据库加载所有聊天流"""
        try:
            from ..common.database.database_model import ChatStreams

            # 只加载属于当前租户的聊天流
            streams = list(
                ChatStreams.select().where(
                    (ChatStreams.agent_id == self.agent_id) & (ChatStreams.tenant_id == self.tenant_id)
                )
            )

            for stream_data in streams:
                try:
                    # 转换为字典格式
                    stream_dict = {
                        "stream_id": stream_data.stream_id,
                        "platform": stream_data.platform,
                        "agent_id": stream_data.agent_id,
                        "create_time": stream_data.create_time,
                        "last_active_time": stream_data.last_active_time,
                        "tenant_id": stream_data.tenant_id,
                        "chat_stream_id": stream_data.stream_id,  # 保持一致性
                    }

                    # 创建隔离上下文
                    from .isolation_context import create_isolation_context

                    isolation_context = create_isolation_context(
                        tenant_id=stream_data.tenant_id,
                        agent_id=stream_data.agent_id,
                        platform=stream_data.platform,
                        chat_stream_id=stream_data.stream_id,
                    )

                    # 创建聊天流
                    chat_stream = IsolatedChatStream.from_dict(stream_dict)
                    chat_stream.isolation_context = isolation_context

                    self.streams[stream_data.stream_id] = chat_stream

                except Exception as e:
                    logger.error(f"加载聊天流失败 {stream_data.stream_id}: {e}")

        except Exception as e:
            logger.error(f"从数据库加载聊天流失败: {e}")

    async def get_or_create_stream(
        self,
        platform: str,
        user_info: UserInfo,
        group_info: Optional[GroupInfo] = None,
        chat_identifier: str = None,
    ) -> IsolatedChatStream:
        """获取或创建隔离化的聊天流"""

        # 生成隔离化的stream_id
        if not chat_identifier:
            chat_identifier = self._generate_isolated_stream_id(platform, user_info, group_info)

        if chat_identifier not in self.streams:
            # 创建新的隔离化聊天流
            chat_stream = IsolatedChatStream(
                stream_id=chat_identifier,
                platform=platform,
                user_info=user_info,
                group_info=group_info,
                agent_id=self.agent_id,
                isolation_context=None,  # 将在构造函数中创建
            )
            self.streams[chat_identifier] = chat_stream

            # 异步保存到数据库
            try:
                await chat_stream.save()
            except Exception as e:
                logger.error(f"保存新聊天流失败: {e}")

        return self.streams[chat_identifier]

    def _generate_isolated_stream_id(
        self,
        platform: str,
        user_info: UserInfo,
        group_info: Optional[GroupInfo] = None,
    ) -> str:
        """生成隔离化的stream_id"""
        components = [
            self.tenant_id,
            self.agent_id,
            platform,
            user_info.user_id or "unknown",
        ]

        if group_info and group_info.group_id:
            components.append(group_info.group_id)

        key = "|".join(components)
        return hashlib.sha256(key.encode()).hexdigest()

    def get_stream(self, stream_id: str) -> Optional[IsolatedChatStream]:
        """获取指定的聊天流"""
        return self.streams.get(stream_id)

    def get_all_streams(self) -> Dict[str, IsolatedChatStream]:
        """获取所有聊天流"""
        return self.streams.copy()

    def remove_stream(self, stream_id: str) -> bool:
        """移除指定的聊天流"""
        if stream_id in self.streams:
            del self.streams[stream_id]
            if stream_id in self.last_messages:
                del self.last_messages[stream_id]
            return True
        return False

    async def save_all_streams(self):
        """保存所有聊天流到数据库"""
        for chat_stream in self.streams.values():
            await chat_stream.save()

    def get_stream_count(self) -> int:
        """获取聊天流数量"""
        return len(self.streams)

    def __str__(self) -> str:
        return f"IsolatedChatManager(tenant={self.tenant_id}, agent={self.agent_id}, streams={len(self.streams)})"

    def __repr__(self) -> str:
        return self.__str__()


# 隔离化聊天管理器管理器
class IsolatedChatManagerManager:
    """隔离化聊天管理器管理器"""

    def __init__(self):
        self._managers: Dict[str, IsolatedChatManager] = {}

    def get_manager(self, tenant_id: str, agent_id: str) -> IsolatedChatManager:
        """获取或创建隔离化聊天管理器"""
        key = f"{tenant_id}:{agent_id}"

        if key not in self._managers:
            self._managers[key] = IsolatedChatManager(tenant_id, agent_id)

            # 异步初始化
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._managers[key].initialize())
            except RuntimeError:
                # 当前上下文没有事件循环，将在后续异步流程中初始化
                pass

        return self._managers[key]

    def clear_manager(self, tenant_id: str, agent_id: str = None):
        """清理指定租户或智能体的管理器"""
        if agent_id:
            # 清理特定智能体的管理器
            key = f"{tenant_id}:{agent_id}"
            if key in self._managers:
                del self._managers[key]
        else:
            # 清理租户的所有管理器
            keys_to_remove = [key for key in self._managers.keys() if key.startswith(f"{tenant_id}:")]
            for key in keys_to_remove:
                del self._managers[key]

    def clear_all(self):
        """清理所有管理器"""
        self._managers.clear()

    def get_active_manager_count(self) -> int:
        """获取活跃的管理器数量"""
        return len(self._managers)


# 全局隔离化聊天管理器管理器
_global_isolated_manager = IsolatedChatManagerManager()


def get_isolated_chat_manager(tenant_id: str, agent_id: str) -> IsolatedChatManager:
    """获取隔离化聊天管理器的便捷函数"""
    return _global_isolated_manager.get_manager(tenant_id, agent_id)


def clear_isolated_chat_manager(tenant_id: str, agent_id: str = None):
    """清理隔离化聊天管理器的便捷函数"""
    _global_isolated_manager.clear_manager(tenant_id, agent_id)


def clear_all_isolated_chat_managers():
    """清理所有隔离化聊天管理器的便捷函数"""
    _global_isolated_manager.clear_all()
