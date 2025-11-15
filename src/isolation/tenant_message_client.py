"""
租户消息客户端
与租户消息服务器通信的客户端，支持自动重连和错误处理
"""

import asyncio
import json
from typing import Dict, Any, Optional, List, Set, Callable
from dataclasses import dataclass, field
from datetime import datetime
import websockets
from websockets.client import WebSocketClientProtocol
import uuid

from .multi_tenant_adapter import MessagePriority
from ..common.logger import get_logger

logger = get_logger("tenant_message_client")


@dataclass
class ClientConfig:
    """客户端配置"""

    tenant_id: str
    agent_id: str = "default"
    platform: str = "unknown"
    chat_stream_id: Optional[str] = None
    server_url: str = "ws://localhost:8091"
    api_key: Optional[str] = None
    reconnect_attempts: int = 3
    reconnect_delay: float = 5.0
    heartbeat_interval: float = 30.0
    message_timeout: float = 30.0


@dataclass
class ClientMessage:
    """客户端消息"""

    message_id: str
    message_type: str
    payload: Dict[str, Any]
    priority: MessagePriority = MessagePriority.NORMAL
    timestamp: datetime = field(default_factory=datetime.now)
    retry_count: int = 0
    max_retries: int = 3


class TenantMessageClient:
    """租户消息客户端"""

    def __init__(self, config: ClientConfig):
        self.config = config
        self.websocket: Optional[WebSocketClientProtocol] = None
        self.connection_id: Optional[str] = None
        self.is_connected = False
        self.is_authenticated = False

        # 消息队列
        self.message_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self.pending_messages: Dict[str, ClientMessage] = {}  # message_id -> message
        self.message_futures: Dict[str, asyncio.Future] = {}  # message_id -> future

        # 订阅管理
        self.subscriptions: Set[str] = set()

        # recv调用保护
        self._recv_lock = asyncio.Lock()
        self._message_loop_active = False

        # 任务管理
        self._connect_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._message_processor_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None

        # 事件回调
        self.on_connected: Optional[Callable] = None
        self.on_disconnected: Optional[Callable] = None
        self.on_message_received: Optional[Callable] = None
        self.on_error: Optional[Callable] = None

        # 统计信息
        self.stats = {
            "messages_sent": 0,
            "messages_received": 0,
            "connection_attempts": 0,
            "reconnections": 0,
            "last_connected": None,
            "last_disconnected": None,
        }

        self._running = False
        self._should_reconnect = True

    async def connect(self) -> bool:
        """连接到服务器"""
        if self.is_connected:
            logger.warning("客户端已经连接")
            return True

        self._running = True
        self._should_reconnect = True

        self._connect_task = asyncio.create_task(self._connection_loop())
        return await self._wait_for_connection()

    async def disconnect(self):
        """断开连接"""
        self._should_reconnect = False
        self._running = False

        if self.websocket:
            await self.websocket.close()

        # 取消所有任务
        tasks = [self._connect_task, self._heartbeat_task, self._message_processor_task, self._reconnect_task]

        for task in tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        logger.info(f"客户端断开连接: {self.config.tenant_id}")

    async def _wait_for_connection(self, timeout: float = 30.0) -> bool:
        """等待连接成功"""
        start_time = datetime.now()
        while not self.is_connected and (datetime.now() - start_time).total_seconds() < timeout:
            await asyncio.sleep(0.1)
        return self.is_connected

    async def _connection_loop(self):
        """连接循环"""
        retry_count = 0

        while self._should_reconnect and retry_count < self.config.reconnect_attempts:
            try:
                self.stats["connection_attempts"] += 1
                logger.info(f"尝试连接到服务器: {self.config.server_url}")

                # 建立WebSocket连接
                self.websocket = await websockets.connect(
                    self.config.server_url,
                    ping_interval=self.config.heartbeat_interval,
                    ping_timeout=self.config.message_timeout,
                )

                # 认证
                await self._authenticate()

                if self.is_authenticated:
                    # 启动心跳和消息处理
                    self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                    self._message_processor_task = asyncio.create_task(self._message_loop())

                    # 更新统计信息
                    self.stats["last_connected"] = datetime.now()
                    if retry_count > 0:
                        self.stats["reconnections"] += 1

                    # 触发连接事件
                    if self.on_connected:
                        try:
                            await self.on_connected()
                        except Exception as e:
                            logger.warning(f"触发连接事件失败: {e}")

                    logger.info(f"客户端连接成功: {self.config.tenant_id}")

                    # 等待连接断开
                    await self.websocket.wait_closed()

                retry_count = 0  # 连接成功，重置重试计数

            except Exception as e:
                logger.error(f"连接失败: {e}")
                retry_count += 1

                # 触发错误事件
                if self.on_error:
                    try:
                        await self.on_error(e)
                    except Exception as callback_error:
                        logger.warning(f"触发错误事件失败: {callback_error}")

            finally:
                await self._cleanup_connection()

            # 如果需要重连，等待一段时间
            if self._should_reconnect and retry_count < self.config.reconnect_attempts:
                logger.info(f"等待 {self.config.reconnect_delay} 秒后重连...")
                await asyncio.sleep(self.config.reconnect_delay)

        logger.error(f"客户端连接失败，已达到最大重试次数: {self.config.tenant_id}")

    async def _authenticate(self):
        """认证"""
        try:
            auth_message = {
                "tenant_id": self.config.tenant_id,
                "agent_id": self.config.agent_id,
                "platform": self.config.platform,
                "chat_stream_id": self.config.chat_stream_id,
                "api_key": self.config.api_key,
            }

            await self.websocket.send(json.dumps(auth_message))

            # 等待认证响应
            response = await asyncio.wait_for(self.websocket.recv(), timeout=self.config.message_timeout)

            response_data = json.loads(response)
            if response_data.get("type") == "auth_success":
                self.connection_id = response_data.get("connection_id")
                self.is_connected = True
                self.is_authenticated = True
                logger.info(f"客户端认证成功: {self.config.tenant_id}")
            else:
                logger.error(f"客户端认证失败: {response_data.get('message', '未知错误')}")
                self.is_authenticated = False

        except Exception as e:
            logger.error(f"认证过程异常: {e}")
            self.is_authenticated = False

    async def _cleanup_connection(self):
        """清理连接"""
        self.is_connected = False
        self.is_authenticated = False
        self.connection_id = None

        self.stats["last_disconnected"] = datetime.now()

        # 触发断开连接事件
        if self.on_disconnected:
            try:
                await self.on_disconnected()
            except Exception as e:
                logger.warning(f"触发断开连接事件失败: {e}")

        # 清理待处理消息的Future
        for future in self.message_futures.values():
            if not future.done():
                future.set_exception(ConnectionError("连接已断开"))
        self.message_futures.clear()

        logger.info(f"客户端连接已清理: {self.config.tenant_id}")

    async def _heartbeat_loop(self):
        """心跳循环"""
        while self.is_connected and self._running:
            try:
                heartbeat_message = {"type": "heartbeat", "timestamp": datetime.now().isoformat()}

                await self.websocket.send(json.dumps(heartbeat_message))
                await asyncio.sleep(self.config.heartbeat_interval)

            except Exception as e:
                logger.error(f"心跳发送失败: {e}")
                break

    async def _message_loop(self):
        """消息循环"""
        # 防止重复启动消息循环
        if self._message_loop_active:
            logger.warning("消息循环已在运行，跳过重复启动")
            return

        self._message_loop_active = True
        try:
            async for message in self.websocket:
                if not self._running:
                    break

                # 使用recv锁防止并发调用
                async with self._recv_lock:
                    if not self._running:
                        break
                    try:
                        data = json.loads(message)
                        await self._handle_server_message(data)
                        self.stats["messages_received"] += 1

                    except json.JSONDecodeError:
                        logger.warning(f"收到无效JSON消息: {message}")
                    except Exception as e:
                        logger.error(f"处理服务器消息失败: {e}")

        except websockets.exceptions.ConnectionClosed:
            logger.info("服务器连接已关闭")
        except Exception as e:
            logger.error(f"消息循环异常: {e}")
        finally:
            self._message_loop_active = False

    async def _handle_server_message(self, data: Dict[str, Any]):
        """处理服务器消息"""
        message_type = data.get("type")

        if message_type == "heartbeat_response":
            # 心跳响应，无需特殊处理
            pass

        elif message_type == "message":
            # 收到消息
            await self._process_received_message(data)

        elif message_type == "broadcast":
            # 收到广播消息
            await self._process_broadcast_message(data)

        # 触发消息接收事件
        if self.on_message_received:
            try:
                await self.on_message_received(data)
            except Exception as e:
                logger.warning(f"触发消息接收事件失败: {e}")

    async def _process_received_message(self, data: Dict[str, Any]):
        """处理收到的消息"""
        # 如果有对应的Future，完成它
        message_id = data.get("message_id")
        if message_id and message_id in self.message_futures:
            future = self.message_futures.pop(message_id)
            if not future.done():
                future.set_result(data)

        # 处理消息内容
        payload = data.get("payload", {})
        logger.debug(f"收到消息: {payload}")

    async def _process_broadcast_message(self, data: Dict[str, Any]):
        """处理广播消息"""
        payload = data.get("payload", {})
        logger.debug(f"收到广播消息: {payload}")

    async def send_message(
        self,
        message_data: Dict[str, Any],
        message_type: str = "text",
        priority: MessagePriority = MessagePriority.NORMAL,
        wait_for_response: bool = False,
        timeout: float = 30.0,
    ) -> Optional[Dict[str, Any]]:
        """发送消息"""
        if not self.is_connected or not self.websocket:
            logger.error("客户端未连接")
            return None

        message_id = str(uuid.uuid4())
        message = ClientMessage(
            message_id=message_id, message_type=message_type, payload=message_data, priority=priority
        )

        # 构建发送数据
        send_data = {
            "type": "message",
            "message_id": message_id,
            "message_type": message_type,
            "priority": priority.value,
            "payload": message_data,
            "timestamp": message.timestamp.isoformat(),
        }

        try:
            # 如果需要等待响应
            if wait_for_response:
                future = asyncio.Future()
                self.message_futures[message_id] = future

            await self.websocket.send(json.dumps(send_data))
            self.stats["messages_sent"] += 1

            logger.debug(f"发送消息: {message_id}")

            # 等待响应
            if wait_for_response:
                try:
                    response = await asyncio.wait_for(future, timeout=timeout)
                    return response
                except asyncio.TimeoutError:
                    logger.warning(f"消息响应超时: {message_id}")
                    if message_id in self.message_futures:
                        del self.message_futures[message_id]
                    return None

            return {"message_id": message_id, "status": "sent"}

        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            if message_id in self.message_futures:
                future = self.message_futures.pop(message_id)
                if not future.done():
                    future.set_exception(e)
            return None

    async def send_message_async(
        self,
        message_data: Dict[str, Any],
        message_type: str = "text",
        priority: MessagePriority = MessagePriority.NORMAL,
    ) -> bool:
        """异步发送消息（不等待响应）"""
        try:
            await self.message_queue.put((message_data, message_type, priority))
            return True
        except asyncio.QueueFull:
            logger.warning("消息队列已满")
            return False

    async def subscribe(self, topics: List[str]) -> bool:
        """订阅主题"""
        if not self.is_connected or not self.websocket:
            logger.error("客户端未连接")
            return False

        try:
            subscribe_data = {"type": "subscribe", "topics": topics}

            await self.websocket.send(json.dumps(subscribe_data))
            self.subscriptions.update(topics)

            logger.info(f"订阅主题: {topics}")
            return True

        except Exception as e:
            logger.error(f"订阅主题失败: {e}")
            return False

    async def unsubscribe(self, topics: List[str]) -> bool:
        """取消订阅主题"""
        if not self.is_connected or not self.websocket:
            logger.error("客户端未连接")
            return False

        try:
            unsubscribe_data = {"type": "unsubscribe", "topics": topics}

            await self.websocket.send(json.dumps(unsubscribe_data))
            self.subscriptions.difference_update(topics)

            logger.info(f"取消订阅主题: {topics}")
            return True

        except Exception as e:
            logger.error(f"取消订阅主题失败: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """获取客户端统计信息"""
        return self.stats.copy()

    def is_ready(self) -> bool:
        """检查客户端是否就绪"""
        return self.is_connected and self.is_authenticated

    async def wait_until_ready(self, timeout: float = 30.0) -> bool:
        """等待客户端就绪"""
        start_time = datetime.now()
        while not self.is_ready() and (datetime.now() - start_time).total_seconds() < timeout:
            await asyncio.sleep(0.1)
        return self.is_ready()


# 便捷函数
async def create_tenant_client(
    tenant_id: str,
    agent_id: str = "default",
    platform: str = "unknown",
    server_url: str = "ws://localhost:8091",
    api_key: Optional[str] = None,
    **kwargs,
) -> TenantMessageClient:
    """创建租户客户端"""
    config = ClientConfig(
        tenant_id=tenant_id, agent_id=agent_id, platform=platform, server_url=server_url, api_key=api_key, **kwargs
    )

    client = TenantMessageClient(config)
    await client.connect()
    return client


async def send_tenant_message(
    client: TenantMessageClient,
    message_data: Dict[str, Any],
    message_type: str = "text",
    priority: MessagePriority = MessagePriority.NORMAL,
    wait_for_response: bool = False,
) -> Optional[Dict[str, Any]]:
    """发送租户消息的便捷函数"""
    return await client.send_message(
        message_data=message_data, message_type=message_type, priority=priority, wait_for_response=wait_for_response
    )
