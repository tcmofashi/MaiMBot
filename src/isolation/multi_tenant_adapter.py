"""
多租户消息发送接收适配器
对接maim_message的多租户系统，支持T+A+C+P四维隔离
"""

from typing import Dict, Any, Optional, List, Set, Callable
from dataclasses import dataclass, field
from enum import Enum
import asyncio
from datetime import datetime

from maim_message.message import Seg

from ..isolation import IsolationContext, create_isolation_context, get_isolated_chat_manager
from ..chat.message_receive.message import MessageRecv, MessageSending
from ..chat.message_receive.uni_message_sender import UniversalMessageSender
from ..common.logger import get_logger

logger = get_logger("multi_tenant_adapter")


class MessagePriority(Enum):
    """消息优先级"""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


@dataclass
class TenantMessageConfig:
    """租户消息配置"""

    tenant_id: str
    server_url: str
    api_key: Optional[str] = None
    platforms: List[str] = field(default_factory=list)
    max_connections: int = 10
    heartbeat_interval: int = 30
    reconnect_attempts: int = 3
    message_timeout: int = 30
    enable_broadcast: bool = True
    allowed_agents: Set[str] = field(default_factory=lambda: {"default"})


@dataclass
class TenantMessageStats:
    """租户消息统计"""

    tenant_id: str
    messages_processed: int = 0
    messages_sent: int = 0
    messages_failed: int = 0
    last_activity: Optional[datetime] = None
    active_connections: int = 0


class MultiTenantMessageAdapter:
    """多租户消息发送接收适配器"""

    def __init__(self):
        self.tenant_configs: Dict[str, TenantMessageConfig] = {}
        self.clients: Dict[str, Any] = {}  # tenant_id -> client
        self.universal_sender = UniversalMessageSender()
        self._initialized = False

        # 消息队列和路由
        self.message_queues: Dict[str, asyncio.Queue] = {}  # tenant_id -> queue
        self.message_handlers: Dict[str, Callable] = {}  # tenant_id -> handler
        self.broadcast_listeners: Dict[str, List[Callable]] = {}  # tenant_id -> listeners

        # 统计信息
        self.tenant_stats: Dict[str, TenantMessageStats] = {}

        # 事件回调
        self.on_message_received: Optional[Callable] = None
        self.on_message_sent: Optional[Callable] = None
        self.on_error: Optional[Callable] = None

    async def initialize(self):
        """异步初始化"""
        if not self._initialized:
            logger.info("多租户消息适配器初始化完成")
            self._initialized = True

    def register_tenant(self, config: TenantMessageConfig):
        """注册租户配置"""
        self.tenant_configs[config.tenant_id] = config

        # 初始化租户相关资源
        if config.tenant_id not in self.message_queues:
            self.message_queues[config.tenant_id] = asyncio.Queue(maxsize=1000)
        if config.tenant_id not in self.broadcast_listeners:
            self.broadcast_listeners[config.tenant_id] = []
        if config.tenant_id not in self.tenant_stats:
            self.tenant_stats[config.tenant_id] = TenantMessageStats(tenant_id=config.tenant_id)

        logger.info(f"注册租户配置: {config.tenant_id}")

    def unregister_tenant(self, tenant_id: str):
        """注销租户配置"""
        if tenant_id in self.tenant_configs:
            del self.tenant_configs[tenant_id]
        if tenant_id in self.message_handlers:
            del self.message_handlers[tenant_id]
        if tenant_id in self.broadcast_listeners:
            del self.broadcast_listeners[tenant_id]
        logger.info(f"注销租户配置: {tenant_id}")

    def add_message_handler(self, tenant_id: str, handler: Callable):
        """添加租户消息处理器"""
        self.message_handlers[tenant_id] = handler
        logger.info(f"添加租户消息处理器: {tenant_id}")

    def add_broadcast_listener(self, tenant_id: str, listener: Callable):
        """添加租户广播监听器"""
        if tenant_id not in self.broadcast_listeners:
            self.broadcast_listeners[tenant_id] = []
        self.broadcast_listeners[tenant_id].append(listener)
        logger.info(f"添加租户广播监听器: {tenant_id}")

    def get_tenant_stats(self, tenant_id: str) -> Optional[TenantMessageStats]:
        """获取租户统计信息"""
        return self.tenant_stats.get(tenant_id)

    def get_all_stats(self) -> Dict[str, TenantMessageStats]:
        """获取所有租户统计信息"""
        return self.tenant_stats.copy()

    async def process_isolated_message(
        self,
        message_data: Dict[str, Any],
        tenant_id: str,
        agent_id: str = "default",
        priority: MessagePriority = MessagePriority.NORMAL,
    ) -> bool:
        """处理带隔离上下文的消息"""
        try:
            # 验证租户配置
            if tenant_id not in self.tenant_configs:
                logger.error(f"未找到租户配置: {tenant_id}")
                return False

            config = self.tenant_configs[tenant_id]
            if agent_id not in config.allowed_agents:
                logger.error(f"智能体 {agent_id} 不在租户 {tenant_id} 的允许列表中")
                return False

            # 更新统计信息
            if tenant_id in self.tenant_stats:
                self.tenant_stats[tenant_id].messages_processed += 1
                self.tenant_stats[tenant_id].last_activity = datetime.now()

            # 创建隔离上下文
            isolation_context = create_isolation_context(
                tenant_id=tenant_id,
                agent_id=agent_id,
                platform=message_data.get("platform", "unknown"),
                chat_stream_id=message_data.get("chat_stream_id"),
            )

            # 为消息数据添加隔离信息
            message_data["tenant_id"] = tenant_id
            message_data["agent_id"] = agent_id
            message_data["isolation_context"] = isolation_context
            message_data["priority"] = priority.value

            # 触发消息接收事件
            if self.on_message_received:
                try:
                    await self.on_message_received(message_data, isolation_context)
                except Exception as e:
                    logger.warning(f"触发消息接收事件失败: {e}")

            # 如果有自定义处理器，使用自定义处理器
            if tenant_id in self.message_handlers:
                handler = self.message_handlers[tenant_id]
                return await handler(message_data, isolation_context)

            # 使用默认处理流程
            return await self._process_default_message(message_data, isolation_context)

        except Exception as e:
            logger.error(f"处理隔离消息失败 {tenant_id}:{agent_id} - {e}")
            if tenant_id in self.tenant_stats:
                self.tenant_stats[tenant_id].messages_failed += 1
            if self.on_error:
                try:
                    await self.on_error(e, tenant_id, agent_id)
                except Exception as callback_error:
                    logger.warning(f"触发错误事件失败: {callback_error}")
            return False

    async def _process_default_message(self, message_data: Dict[str, Any], isolation_context: IsolationContext) -> bool:
        """默认消息处理流程"""
        try:
            # 获取隔离化的聊天管理器
            chat_manager = get_isolated_chat_manager(isolation_context.tenant_id, isolation_context.agent_id)

            # 创建MessageRecv对象（支持隔离上下文）
            message_recv = await self._create_isolated_message_recv(message_data, isolation_context)

            # 获取或创建隔离化的聊天流
            user_info = message_recv.message_info.sender_info.user_info
            group_info = message_recv.message_info.sender_info.group_info

            chat_stream = await chat_manager.get_or_create_stream(
                platform=message_recv.message_info.platform, user_info=user_info, group_info=group_info
            )

            # 设置聊天流的消息上下文
            chat_stream.set_context(message_recv)

            # 处理消息（这里需要集成到现有的消息处理流程）
            return await self._process_message_with_isolation(message_recv, chat_stream, isolation_context)

        except Exception as e:
            logger.error(f"默认消息处理失败: {e}")
            return False

    async def _create_isolated_message_recv(
        self, message_data: Dict[str, Any], isolation_context: IsolationContext
    ) -> MessageRecv:
        """创建带隔离上下文的MessageRecv对象"""
        # 这里需要根据实际的MessageRecv构造函数来创建
        # 由于MessageRecv的构造比较复杂，这里提供一个简化的实现思路
        from maim_message import MessageInfo

        # 从message_data中提取必要信息
        message_info_payload = message_data.get("message_info", {})

        # 创建MessageInfo对象（简化版）
        message_info = MessageInfo.from_dict(message_info_payload)

        # 创建消息段
        message_segments = []
        if "message_segments" in message_data:
            for seg_data in message_data["message_segments"]:
                message_segments.append(Seg.from_dict(seg_data))

        # 创建聊天流（需要从chat_manager获取）
        get_isolated_chat_manager(isolation_context.tenant_id, isolation_context.agent_id)

        # 这里需要获取或创建聊天流，暂时使用占位符
        chat_stream = None  # 实际实现中需要从chat_manager获取

        # 创建MessageRecv对象
        message_recv = MessageRecv(
            message_info=message_info,
            message_segment=message_segments[0] if message_segments else Seg.text(""),
            chat_stream=chat_stream,
            tenant_id=isolation_context.tenant_id,
            agent_id=isolation_context.agent_id,
            isolation_context=isolation_context,
        )

        return message_recv

    async def _process_message_with_isolation(
        self, message_recv: MessageRecv, chat_stream, isolation_context: IsolationContext
    ) -> bool:
        """使用隔离上下文处理消息"""
        try:
            # 这里集成到现有的HeartFC消息处理流程
            # 调用heartFC的处理器，但传入隔离上下文
            from ..chat.heart_flow.heartflow_message_processor import heart_fc_receiver

            # 处理消息
            await heart_fc_receiver.process_message(message_recv)

            return True

        except Exception as e:
            logger.error(f"隔离消息处理失败: {e}")
            return False

    async def send_isolated_message(
        self,
        message: MessageSending,
        isolation_context: IsolationContext,
        priority: MessagePriority = MessagePriority.NORMAL,
    ) -> bool:
        """发送带隔离上下文的消息"""
        try:
            # 验证租户配置
            if isolation_context.tenant_id not in self.tenant_configs:
                logger.error(f"未找到租户配置: {isolation_context.tenant_id}")
                return False

            config = self.tenant_configs[isolation_context.tenant_id]
            if isolation_context.agent_id not in config.allowed_agents:
                logger.error(f"智能体 {isolation_context.agent_id} 不在租户 {isolation_context.tenant_id} 的允许列表中")
                return False

            # 确保消息中包含隔离信息
            if not hasattr(message, "tenant_id"):
                message.tenant_id = isolation_context.tenant_id
            if not hasattr(message, "agent_id"):
                message.agent_id = isolation_context.agent_id
            if not hasattr(message, "priority"):
                message.priority = priority.value

            # 添加到租户消息队列
            if isolation_context.tenant_id in self.message_queues:
                queue_item = {
                    "message": message,
                    "isolation_context": isolation_context,
                    "priority": priority,
                    "timestamp": datetime.now(),
                }
                try:
                    self.message_queues[isolation_context.tenant_id].put_nowait(queue_item)
                except asyncio.QueueFull:
                    logger.warning(f"租户 {isolation_context.tenant_id} 消息队列已满，丢弃消息")
                    return False

            # 更新统计信息
            if isolation_context.tenant_id in self.tenant_stats:
                self.tenant_stats[isolation_context.tenant_id].messages_sent += 1

            # 使用现有的消息发送器发送
            success = await self.universal_sender.send_message(message)

            # 触发消息发送事件
            if self.on_message_sent:
                try:
                    await self.on_message_sent(message, isolation_context, success)
                except Exception as e:
                    logger.warning(f"触发消息发送事件失败: {e}")

            return success

        except Exception as e:
            logger.error(f"发送隔离消息失败: {e}")
            if isolation_context.tenant_id in self.tenant_stats:
                self.tenant_stats[isolation_context.tenant_id].messages_failed += 1
            return False

    async def broadcast_to_tenant(
        self, tenant_id: str, platform: str, message_data: Dict[str, Any], exclude_agent: Optional[str] = None
    ) -> bool:
        """向租户的特定平台广播消息"""
        try:
            if tenant_id not in self.tenant_configs:
                logger.error(f"未找到租户配置: {tenant_id}")
                return False

            config = self.tenant_configs[tenant_id]
            if not config.enable_broadcast:
                logger.warning(f"租户 {tenant_id} 未启用广播功能")
                return False

            # 通知广播监听器
            if tenant_id in self.broadcast_listeners:
                for listener in self.broadcast_listeners[tenant_id]:
                    try:
                        await listener(tenant_id, platform, message_data, exclude_agent)
                    except Exception as e:
                        logger.warning(f"广播监听器处理失败: {e}")

            # 如果有租户客户端，使用租户客户端发送
            if tenant_id in self.clients:
                client = self.clients[tenant_id]
                if hasattr(client, "broadcast"):
                    await client.broadcast(platform, message_data, exclude_agent)

            logger.info(f"向租户 {tenant_id} 的平台 {platform} 广播消息完成")
            return True

        except Exception as e:
            logger.error(f"租户消息广播失败: {e}")
            return False

    async def process_message_queue(self, tenant_id: str):
        """处理租户消息队列"""
        if tenant_id not in self.message_queues:
            return

        queue = self.message_queues[tenant_id]
        while not queue.empty():
            try:
                queue_item = queue.get_nowait()
                message = queue_item["message"]
                priority = queue_item.get("priority", MessagePriority.NORMAL)

                # 根据优先级处理消息
                if priority == MessagePriority.URGENT:
                    await self.universal_sender.send_message(message)
                else:
                    await self.universal_sender.send_message(message)

                queue.task_done()

            except asyncio.QueueEmpty:
                break
            except Exception as e:
                logger.error(f"处理队列消息失败 {tenant_id}: {e}")

    async def start_queue_processor(self, tenant_id: str, interval: float = 1.0):
        """启动租户消息队列处理器"""

        async def processor():
            while True:
                try:
                    await self.process_message_queue(tenant_id)
                    await asyncio.sleep(interval)
                except Exception as e:
                    logger.error(f"队列处理器异常 {tenant_id}: {e}")
                    await asyncio.sleep(interval)

        # 启动后台任务
        asyncio.create_task(processor())
        logger.info(f"启动租户 {tenant_id} 消息队列处理器")

    async def cleanup_tenant(self, tenant_id: str):
        """清理租户资源"""
        try:
            # 清理租户客户端
            if tenant_id in self.clients:
                client = self.clients[tenant_id]
                if hasattr(client, "close"):
                    await client.close()
                del self.clients[tenant_id]

            # 清理隔离化聊天管理器
            from ..isolation import clear_isolated_chat_manager

            clear_isolated_chat_manager(tenant_id)

            logger.info(f"清理租户资源完成: {tenant_id}")

        except Exception as e:
            logger.error(f"清理租户资源失败 {tenant_id}: {e}")


# 全局多租户适配器实例
_global_multi_tenant_adapter = MultiTenantMessageAdapter()


def get_multi_tenant_adapter() -> MultiTenantMessageAdapter:
    """获取全局多租户消息适配器"""
    return _global_multi_tenant_adapter


async def initialize_multi_tenant_system():
    """初始化多租户系统"""
    adapter = get_multi_tenant_adapter()
    await adapter.initialize()


# 便捷函数
async def process_tenant_message(message_data: Dict[str, Any], tenant_id: str, agent_id: str = "default") -> bool:
    """处理租户消息的便捷函数"""
    adapter = get_multi_tenant_adapter()
    return await adapter.process_isolated_message(message_data, tenant_id, agent_id)


async def send_tenant_message(message: MessageSending, tenant_id: str, agent_id: str = "default") -> bool:
    """发送租户消息的便捷函数"""
    from ..isolation import create_isolation_context

    isolation_context = create_isolation_context(tenant_id=tenant_id, agent_id=agent_id)

    adapter = get_multi_tenant_adapter()
    return await adapter.send_isolated_message(message, isolation_context)
