"""
隔离化的ChatBot实现
支持T+P维度的多租户隔离
"""

import traceback
from typing import Dict


from ..chat.message_receive.message import MessageRecv
from ..chat.message_receive.bot import ChatBot
from ..common.logger import get_logger

logger = get_logger("isolated_chat_bot")


class IsolatedChatBot:
    """隔离化的ChatBot，支持T+P维度隔离"""

    def __init__(self, tenant_id: str, platform: str):
        self.tenant_id = tenant_id  # T: 租户隔离
        self.platform = platform  # P: 平台隔离
        self.isolation_context = None

        # 创建隔离上下文
        from .isolation_context import create_isolation_context

        self.isolation_context = create_isolation_context(
            tenant_id=tenant_id,
            agent_id="system",  # 系统级别的agent
            platform=platform,
        )

        # 内部ChatBot实例（复用现有逻辑）
        self._inner_bot = ChatBot()
        self._started = False

    async def _ensure_started(self):
        """确保所有任务已启动"""
        if not self._started:
            logger.debug(f"启动隔离化ChatBot: {self.tenant_id}:{self.platform}")
            await self._inner_bot._ensure_started()
            self._started = True

    async def message_process(self, message: MessageRecv) -> None:
        """处理转化后的统一格式消息（支持隔离）"""
        try:
            # 确保消息包含正确的隔离信息
            if not hasattr(message, "tenant_id") or not message.tenant_id:
                message.tenant_id = self.tenant_id
            if not hasattr(message, "agent_id") or not message.agent_id:
                message.agent_id = "default"
            if not hasattr(message, "isolation_context") or not message.isolation_context:
                message.isolation_context = self.isolation_context

            # 确保ChatBot已启动
            await self._ensure_started()

            # 使用原有的ChatBot处理逻辑，但添加隔离支持
            await self._process_message_with_isolation(message)

        except Exception as e:
            logger.error(f"隔离化ChatBot消息处理失败 {self.tenant_id}:{self.platform}: {e}")
            traceback.print_exc()

    async def _process_message_with_isolation(self, message: MessageRecv) -> None:
        """使用隔离上下文处理消息"""
        try:
            # 检查租户权限
            if message.tenant_id != self.tenant_id:
                logger.warning(f"消息租户ID不匹配: {message.tenant_id} != {self.tenant_id}")
                return

            # 检查平台权限
            if message.message_info.platform != self.platform:
                logger.warning(f"消息平台不匹配: {message.message_info.platform} != {self.platform}")
                return

            # 使用内部ChatBot的处理逻辑
            # 这里需要适配原有的ChatBot.message_process方法
            # 由于原方法比较复杂，我们采用逐步迁移的方式

            # 1. 过滤词检查
            if await self._check_ban_words_with_isolation(message):
                return

            # 2. 心流处理
            await self._heart_flow_process_with_isolation(message)

            # 3. 命令处理
            await self._command_process_with_isolation(message)

        except Exception as e:
            logger.error(f"隔离消息处理失败: {e}")

    async def _check_ban_words_with_isolation(self, message: MessageRecv) -> bool:
        """检查过滤词（支持隔离）"""
        try:
            # 获取隔离化的配置
            if message.isolation_context and hasattr(message.isolation_context, "get_config_manager"):
                config_manager = message.isolation_context.get_config_manager()
                config = config_manager.get_isolated_config()
            else:
                # 回退到默认配置
                from ..config.config import global_config

                config = global_config

            # 使用原有的过滤词检查逻辑
            text = message.processed_plain_text
            user_info = message.message_info.sender_info.user_info
            group_info = message.message_info.sender_info.group_info

            for word in getattr(config.message_receive, "ban_words", []):
                if word in text:
                    chat_name = group_info.group_name if group_info else "私聊"
                    logger.info(f"[{chat_name}][{message.tenant_id}]{user_info.user_nickname}:{text}")
                    logger.info(f"[过滤词识别]消息中含有{word}，filtered")
                    return True
            return False

        except Exception as e:
            logger.error(f"过滤词检查失败: {e}")
            return False

    async def _heart_flow_process_with_isolation(self, message: MessageRecv):
        """心流处理（支持隔离）"""
        try:
            # 使用隔离化心流处理器
            from ..chat.heart_flow.heartflow_message_processor import heart_fc_receiver

            # 确保心流处理器有隔离上下文
            if hasattr(heart_fc_receiver, "set_isolation_context"):
                heart_fc_receiver.set_isolation_context(message.isolation_context)

            # 处理消息
            await heart_fc_receiver.process_message(message)

        except Exception as e:
            logger.error(f"心流处理失败: {e}")

    async def _command_process_with_isolation(self, message: MessageRecv):
        """命令处理（支持隔离）"""
        try:
            # 使用内部ChatBot的命令处理逻辑
            await self._inner_bot._process_commands_with_new_system(message)

        except Exception as e:
            logger.error(f"命令处理失败: {e}")

    async def cleanup(self):
        """清理资源"""
        try:
            if self._started:
                logger.info(f"清理隔离化ChatBot资源: {self.tenant_id}:{self.platform}")
                # 清理内部资源
                if hasattr(self._inner_bot, "cleanup"):
                    await self._inner_bot.cleanup()
                self._started = False

        except Exception as e:
            logger.error(f"清理隔离化ChatBot失败: {e}")

    def __str__(self) -> str:
        return f"IsolatedChatBot(tenant={self.tenant_id}, platform={self.platform})"

    def __repr__(self) -> str:
        return self.__str__()


class IsolatedChatBotManager:
    """隔离化ChatBot管理器"""

    def __init__(self):
        self._bots: Dict[str, IsolatedChatBot] = {}  # tenant_id:platform -> IsolatedChatBot

    def get_bot(self, tenant_id: str, platform: str) -> IsolatedChatBot:
        """获取或创建隔离化ChatBot"""
        key = f"{tenant_id}:{platform}"

        if key not in self._bots:
            self._bots[key] = IsolatedChatBot(tenant_id, platform)
            logger.info(f"创建隔离化ChatBot: {key}")

        return self._bots[key]

    async def cleanup_bot(self, tenant_id: str, platform: str = None):
        """清理指定租户或平台的ChatBot"""
        if platform:
            # 清理特定平台的ChatBot
            key = f"{tenant_id}:{platform}"
            if key in self._bots:
                await self._bots[key].cleanup()
                del self._bots[key]
                logger.info(f"清理隔离化ChatBot: {key}")
        else:
            # 清理租户的所有ChatBot
            keys_to_remove = [key for key in self._bots.keys() if key.startswith(f"{tenant_id}:")]
            for key in keys_to_remove:
                await self._bots[key].cleanup()
                del self._bots[key]
                logger.info(f"清理租户的隔离化ChatBot: {key}")

    async def cleanup_all(self):
        """清理所有ChatBot"""
        for bot in self._bots.values():
            await bot.cleanup()
        self._bots.clear()
        logger.info("清理所有隔离化ChatBot")

    def get_active_bot_count(self) -> int:
        """获取活跃的ChatBot数量"""
        return len(self._bots)

    def get_tenant_bots(self, tenant_id: str) -> Dict[str, IsolatedChatBot]:
        """获取租户的所有ChatBot"""
        result = {}
        for key, bot in self._bots.items():
            if key.startswith(f"{tenant_id}:"):
                result[key] = bot
        return result


# 全局隔离化ChatBot管理器
_global_isolated_bot_manager = IsolatedChatBotManager()


def get_isolated_chat_bot(tenant_id: str, platform: str) -> IsolatedChatBot:
    """获取隔离化ChatBot的便捷函数"""
    return _global_isolated_bot_manager.get_bot(tenant_id, platform)


async def cleanup_isolated_chat_bot(tenant_id: str, platform: str = None):
    """清理隔离化ChatBot的便捷函数"""
    await _global_isolated_bot_manager.cleanup_bot(tenant_id, platform)


async def cleanup_all_isolated_chat_bots():
    """清理所有隔离化ChatBot的便捷函数"""
    await _global_isolated_bot_manager.cleanup_all()


def get_isolated_chat_bot_manager() -> IsolatedChatBotManager:
    """获取隔离化ChatBot管理器的便捷函数"""
    return _global_isolated_bot_manager
