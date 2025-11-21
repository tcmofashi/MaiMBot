import asyncio
import traceback
from typing import Optional

from rich.traceback import install
from maim_message import Seg

from src.common.logger import get_logger
from src.chat.message_receive.message import MessageSending
from src.chat.message_receive.storage import MessageStorage
from src.chat.utils.utils import truncate_message
from src.chat.utils.utils import calculate_typing_time

# 导入隔离支持
try:
    from src.isolation.isolation_context import IsolationContext, create_isolation_context
    from .isolated_uni_message_sender import get_isolated_message_sender

    ISOLATION_AVAILABLE = True
except ImportError:
    # 兼容性处理
    class IsolationContext:
        def __init__(self, *args, **kwargs):
            pass

    def create_isolation_context(*args, **kwargs):
        return None

    def get_isolated_message_sender(*args, **kwargs):
        return None

    ISOLATION_AVAILABLE = False

install(extra_lines=3)

logger = get_logger("sender")


async def _send_message(message: MessageSending, show_log=True) -> bool:
    """合并后的消息发送函数，使用WebSocketServer通过WebSocket发送消息"""
    message_preview = truncate_message(message.processed_plain_text, max_length=200)

    try:
        # 获取全局WebSocket服务器实例
        from src.common.message.api import get_global_api

        # 获取WebSocket服务器实例
        websocket_server = get_global_api()

        # 从消息中获取租户信息
        tenant_id = getattr(message, "tenant_id", None)
        agent_id = getattr(message, "agent_id", None)
        platform = message.message_info.platform

        # 如果没有租户信息，尝试从聊天流获取
        if not tenant_id and hasattr(message, "chat_stream") and message.chat_stream:
            tenant_id = getattr(message.chat_stream, "tenant_id", None)
            if not agent_id:
                agent_id = getattr(message.chat_stream, "agent_id", None)

        # 如果仍然没有租户信息，尝试从回复消息获取
        if (not tenant_id or not agent_id) and hasattr(message, "reply") and message.reply:
            if not tenant_id:
                tenant_id = getattr(message.reply, "tenant_id", None)
            if not agent_id:
                agent_id = getattr(message.reply, "agent_id", None)

        # 调试日志
        logger.debug(f"消息发送租户信息解析: tenant_id={tenant_id}, agent_id={agent_id}, platform={platform}")
        logger.debug(
            f"消息对象租户字段: tenant_id={getattr(message, 'tenant_id', None)}, agent_id={getattr(message, 'agent_id', None)}"
        )
        if hasattr(message, "chat_stream") and message.chat_stream:
            logger.debug(
                f"聊天流租户字段: tenant_id={getattr(message.chat_stream, 'tenant_id', None)}, agent_id={getattr(message.chat_stream, 'agent_id', None)}"
            )

        # 使用默认值（应该是最后的选择）
        if not tenant_id:
            logger.warning("无法获取租户ID，使用默认值 'default'")
            tenant_id = "default"
        if not agent_id:
            logger.warning("无法获取智能体ID，使用默认值 'default'")
            agent_id = "default"

        # 构建API密钥（格式：tenant_id:agent_id）
        api_key = f"{tenant_id}:{agent_id}"

        # 构建目标选择参数
        target = {"by_api_key": api_key}

        # 发送文本消息
        success = await websocket_server.send_message(
            message=message,
        )

        # send_message是同步方法，直接检查返回值
        if success:
            if show_log:
                logger.info(
                    f"已将消息  '{message_preview}'  发往平台'{platform}' (租户: {tenant_id}, 智能体: {agent_id})"
                )
            return True
        else:
            logger.error("发送消息失败: 无活跃连接或发送失败")
            return False

    except Exception as e:
        logger.error(f"发送消息   '{message_preview}'   发往平台'{message.message_info.platform}' 失败: {str(e)}")
        traceback.print_exc()
        raise e  # 重新抛出其他异常


class UniversalMessageSender:
    """管理消息的注册、即时处理、发送和存储，并跟踪思考状态。"""

    def __init__(self):
        self.storage = MessageStorage()
        self._isolation_context: Optional[IsolationContext] = None

    def set_isolation_context(self, isolation_context: IsolationContext) -> None:
        """
        设置隔离上下文

        Args:
            isolation_context: 隔离上下文
        """
        self._isolation_context = isolation_context
        logger.debug(f"设置UniversalMessageSender的隔离上下文: {isolation_context}")

    def get_isolation_context(self) -> Optional[IsolationContext]:
        """
        获取隔离上下文

        Returns:
            Optional[IsolationContext]: 隔离上下文
        """
        return self._isolation_context

    def _should_use_isolated_sender(self, message: MessageSending) -> bool:
        """
        判断是否应该使用隔离化发送器

        Args:
            message: 消息对象

        Returns:
            bool: 是否使用隔离化发送器
        """
        # 如果隔离功能不可用，使用原有逻辑
        if not ISOLATION_AVAILABLE:
            return False

        # 如果设置了隔离上下文，使用隔离化发送器
        if self._isolation_context:
            return True

        # 尝试从消息中获取隔离信息
        if hasattr(message, "tenant_id") and message.tenant_id and hasattr(message, "platform") and message.platform:
            return True

        # 尝试从聊天流中获取隔离信息
        if (
            hasattr(message, "chat_stream")
            and message.chat_stream
            and hasattr(message.chat_stream, "tenant_id")
            and message.chat_stream.tenant_id
        ):
            return True

        return False

    def _get_isolated_sender(self, message: MessageSending):
        """
        获取隔离化发送器

        Args:
            message: 消息对象

        Returns:
            隔离化发送器
        """
        if not ISOLATION_AVAILABLE:
            return None

        # 确定租户ID和平台
        tenant_id = None
        platform = None

        # 从隔离上下文获取
        if self._isolation_context:
            tenant_id = self._isolation_context.tenant_id
            platform = self._isolation_context.platform

        # 从消息获取
        if not tenant_id and hasattr(message, "tenant_id"):
            tenant_id = message.tenant_id
        if not platform and hasattr(message, "platform"):
            platform = message.platform

        # 从聊天流获取
        if not tenant_id and hasattr(message, "chat_stream") and message.chat_stream:
            if hasattr(message.chat_stream, "tenant_id"):
                tenant_id = message.chat_stream.tenant_id
            if hasattr(message.chat_stream, "platform"):
                platform = message.chat_stream.platform

        # 从消息信息获取
        if not platform and hasattr(message, "message_info") and message.message_info:
            if hasattr(message.message_info, "platform"):
                platform = message.message_info.platform

        # 如果仍有缺失，使用默认值
        if not tenant_id:
            tenant_id = "default"
        if not platform:
            platform = "default"

        try:
            return get_isolated_message_sender(tenant_id, platform)
        except Exception as e:
            logger.error(f"获取隔离化发送器失败: {e}")
            return None

    async def send_message(
        self, message: MessageSending, typing=False, set_reply=False, storage_message=True, show_log=True
    ):
        """
        处理、发送并存储一条消息。

        参数：
            message: MessageSending 对象，待发送的消息。
            typing: 是否模拟打字等待。

        用法：
            - typing=True 时，发送前会有打字等待。
        """
        if not message.chat_stream:
            logger.error("消息缺少 chat_stream，无法发送")
            raise ValueError("消息缺少 chat_stream，无法发送")
        if not message.message_info or not message.message_info.message_id:
            logger.error("消息缺少 message_info 或 message_id，无法发送")
            raise ValueError("消息缺少 message_info 或 message_id，无法发送")

        # 检查是否应该使用隔离化发送器
        if self._should_use_isolated_sender(message):
            return await self._send_with_isolation(message, typing, set_reply, storage_message, show_log)
        else:
            return await self._send_with_original_logic(message, typing, set_reply, storage_message, show_log)

    async def _send_with_isolation(
        self, message: MessageSending, typing: bool, set_reply: bool, storage_message: bool, show_log: bool
    ) -> bool:
        """
        使用隔离化发送器发送消息

        Args:
            message: 消息对象
            typing: 是否模拟打字等待
            set_reply: 是否设置回复
            storage_message: 是否存储消息
            show_log: 是否显示日志

        Returns:
            bool: 是否发送成功
        """
        try:
            isolated_sender = self._get_isolated_sender(message)
            if not isolated_sender:
                logger.warning("无法获取隔离化发送器，回退到原有逻辑")
                return await self._send_with_original_logic(message, typing, set_reply, storage_message, show_log)

            logger.debug(
                f"使用隔离化发送器发送消息: tenant={isolated_sender.tenant_id}, platform={isolated_sender.platform}"
            )

            # 使用隔离化发送器发送消息
            success = await isolated_sender.send_message(
                message=message, typing=typing, set_reply=set_reply, storage_message=storage_message, show_log=show_log
            )

            return success

        except Exception as e:
            logger.error(f"使用隔离化发送器发送消息失败: {e}")
            # 回退到原有逻辑
            return await self._send_with_original_logic(message, typing, set_reply, storage_message, show_log)

    async def _send_with_original_logic(
        self, message: MessageSending, typing: bool, set_reply: bool, storage_message: bool, show_log: bool
    ) -> bool:
        """
        使用原有逻辑发送消息

        Args:
            message: 消息对象
            typing: 是否模拟打字等待
            set_reply: 是否设置回复
            storage_message: 是否存储消息
            show_log: 是否显示日志

        Returns:
            bool: 是否发送成功
        """
        chat_id = message.chat_stream.stream_id
        message_id = message.message_info.message_id

        try:
            if set_reply:
                message.build_reply()
                logger.debug(f"[{chat_id}] 选择回复引用消息: {message.processed_plain_text[:20]}...")

            from src.plugin_system.core.events_manager import events_manager
            from src.plugin_system.base.component_types import EventType

            continue_flag, modified_message = await events_manager.handle_mai_events(
                EventType.POST_SEND_PRE_PROCESS, message=message, stream_id=chat_id
            )
            if not continue_flag:
                logger.info(f"[{chat_id}] 消息发送被插件取消: {str(message.message_segment)[:100]}...")
                return False
            if modified_message:
                if modified_message._modify_flags.modify_message_segments:
                    message.message_segment = Seg(type="seglist", data=modified_message.message_segments)
                if modified_message._modify_flags.modify_plain_text:
                    logger.warning(f"[{chat_id}] 插件修改了消息的纯文本内容，可能导致此内容被覆盖。")
                    message.processed_plain_text = modified_message.plain_text

            await message.process()

            continue_flag, modified_message = await events_manager.handle_mai_events(
                EventType.POST_SEND, message=message, stream_id=chat_id
            )
            if not continue_flag:
                logger.info(f"[{chat_id}] 消息发送被插件取消: {str(message.message_segment)[:100]}...")
                return False
            if modified_message:
                if modified_message._modify_flags.modify_message_segments:
                    message.message_segment = Seg(type="seglist", data=modified_message.message_segments)
                if modified_message._modify_flags.modify_plain_text:
                    message.processed_plain_text = modified_message.plain_text

            if typing:
                typing_time = calculate_typing_time(
                    input_string=message.processed_plain_text,
                    thinking_start_time=message.thinking_start_time,
                    is_emoji=message.is_emoji,
                )
                await asyncio.sleep(typing_time)

            sent_msg = await _send_message(message, show_log=show_log)
            if not sent_msg:
                return False

            continue_flag, modified_message = await events_manager.handle_mai_events(
                EventType.AFTER_SEND, message=message, stream_id=chat_id
            )
            if not continue_flag:
                logger.info(f"[{chat_id}] 消息发送后续处理被插件取消: {str(message.message_segment)[:100]}...")
                return True
            if modified_message:
                if modified_message._modify_flags.modify_message_segments:
                    message.message_segment = Seg(type="seglist", data=modified_message.message_segments)
                if modified_message._modify_flags.modify_plain_text:
                    message.processed_plain_text = modified_message.plain_text

            if storage_message:
                await self.storage.store_message(message, message.chat_stream)

            return sent_msg

        except Exception as e:
            logger.error(f"[{chat_id}] 处理或存储消息 {message_id} 时出错: {e}")
            raise e
