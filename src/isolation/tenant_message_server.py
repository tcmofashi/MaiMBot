"""
租户消息服务器
基于WebSocket的多租户消息服务器，支持T+A+C+P四维隔离
"""

import asyncio
import json
from typing import Dict, Any, Optional, List, Set, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import websockets
from websockets.server import WebSocketServerProtocol
import uuid

from .multi_tenant_adapter import MessagePriority, TenantMessageConfig
from ..common.logger import get_logger

logger = get_logger("tenant_message_server")


@dataclass
class TenantConnection:
    """租户连接信息"""

    tenant_id: str
    agent_id: str
    platform: str
    chat_stream_id: Optional[str]
    websocket: WebSocketServerProtocol
    connected_at: datetime
    last_heartbeat: datetime
    is_authenticated: bool = False
    subscriptions: Set[str] = field(default_factory=set)


@dataclass
class ServerMessage:
    """服务器消息格式"""

    message_id: str
    tenant_id: str
    agent_id: str
    platform: str
    chat_stream_id: Optional[str]
    message_type: str
    payload: Dict[str, Any]
    priority: MessagePriority
    timestamp: datetime
    expires_at: Optional[datetime] = None


class TenantMessageServer:
    """租户消息服务器"""

    def __init__(self, host: str = "localhost", port: int = 8091):
        self.host = host
        self.port = port
        self.server: Optional[websockets.WebSocketServer] = None

        # 连接管理
        self.connections: Dict[str, TenantConnection] = {}  # connection_id -> connection
        self.tenant_connections: Dict[str, Set[str]] = {}  # tenant_id -> connection_ids
        self.agent_connections: Dict[str, Set[str]] = {}  # agent_id -> connection_ids
        self.platform_connections: Dict[str, Set[str]] = {}  # platform -> connection_ids

        # 消息队列
        self.message_queues: Dict[str, asyncio.Queue] = {}  # tenant_id -> queue
        self.broadcast_queues: Dict[str, asyncio.Queue] = {}  # platform -> queue

        # 认证和配置
        self.tenant_configs: Dict[str, TenantMessageConfig] = {}
        self.api_keys: Dict[str, str] = {}  # api_key -> tenant_id

        # 事件回调
        self.on_client_connected: Optional[Callable] = None
        self.on_client_disconnected: Optional[Callable] = None
        self.on_message_received: Optional[Callable] = None

        # 统计信息
        self.stats = {
            "total_connections": 0,
            "active_connections": 0,
            "messages_sent": 0,
            "messages_received": 0,
            "server_start_time": None,
        }

        self._running = False
        self._cleanup_task: Optional[asyncio.Task] = None

    def register_tenant(self, config: TenantMessageConfig, api_key: str):
        """注册租户配置"""
        self.tenant_configs[config.tenant_id] = config
        if config.api_key:
            self.api_keys[config.api_key] = config.tenant_id
        if api_key:
            self.api_keys[api_key] = config.tenant_id

        # 初始化消息队列
        if config.tenant_id not in self.message_queues:
            self.message_queues[config.tenant_id] = asyncio.Queue(maxsize=10000)

        logger.info(f"注册租户服务器配置: {config.tenant_id}")

    def unregister_tenant(self, tenant_id: str):
        """注销租户配置"""
        if tenant_id in self.tenant_configs:
            del self.tenant_configs[tenant_id]

        # 清理API密钥
        keys_to_remove = [key for key, value in self.api_keys.items() if value == tenant_id]
        for key in keys_to_remove:
            del self.api_keys[key]

        logger.info(f"注销租户服务器配置: {tenant_id}")

    async def start(self):
        """启动服务器"""
        if self._running:
            logger.warning("服务器已经在运行")
            return

        try:
            self.server = await websockets.serve(
                self.handle_client, self.host, self.port, ping_interval=30, ping_timeout=10, close_timeout=10
            )

            self._running = True
            self.stats["server_start_time"] = datetime.now()

            # 启动清理任务
            self._cleanup_task = asyncio.create_task(self._cleanup_expired_connections())

            logger.info(f"租户消息服务器启动: ws://{self.host}:{self.port}")

        except Exception as e:
            logger.error(f"启动服务器失败: {e}")
            raise

    async def stop(self):
        """停止服务器"""
        if not self._running:
            return

        self._running = False

        # 关闭所有连接
        for connection in list(self.connections.values()):
            try:
                await connection.websocket.close()
            except Exception:
                pass

        # 关闭服务器
        if self.server:
            self.server.close()
            await self.server.wait_closed()

        # 取消清理任务
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        logger.info("租户消息服务器已停止")

    async def handle_client(self, websocket: WebSocketServerProtocol, path: str):
        """处理客户端连接"""
        connection_id = str(uuid.uuid4())
        connection = None

        try:
            # 等待认证消息
            auth_message = await websocket.recv()
            auth_data = json.loads(auth_message)

            if not await self._authenticate_client(auth_data):
                await websocket.send(json.dumps({"type": "auth_error", "message": "认证失败"}))
                await websocket.close()
                return

            # 创建连接对象
            tenant_id = auth_data["tenant_id"]
            agent_id = auth_data.get("agent_id", "default")
            platform = auth_data.get("platform", "unknown")
            chat_stream_id = auth_data.get("chat_stream_id")

            connection = TenantConnection(
                tenant_id=tenant_id,
                agent_id=agent_id,
                platform=platform,
                chat_stream_id=chat_stream_id,
                websocket=websocket,
                connected_at=datetime.now(),
                last_heartbeat=datetime.now(),
                is_authenticated=True,
            )

            # 注册连接
            self._register_connection(connection_id, connection)

            # 发送认证成功消息
            await websocket.send(
                json.dumps(
                    {"type": "auth_success", "connection_id": connection_id, "server_time": datetime.now().isoformat()}
                )
            )

            # 触发连接事件
            if self.on_client_connected:
                try:
                    await self.on_client_connected(connection)
                except Exception as e:
                    logger.warning(f"触发连接事件失败: {e}")

            # 处理客户端消息
            await self._handle_client_messages(connection)

        except websockets.exceptions.ConnectionClosed:
            logger.info(f"客户端连接关闭: {connection_id}")
        except Exception as e:
            logger.error(f"处理客户端连接异常 {connection_id}: {e}")
        finally:
            # 清理连接
            if connection:
                self._unregister_connection(connection_id, connection)
                if self.on_client_disconnected:
                    try:
                        await self.on_client_disconnected(connection)
                    except Exception as e:
                        logger.warning(f"触发断开连接事件失败: {e}")

    async def _authenticate_client(self, auth_data: Dict[str, Any]) -> bool:
        """认证客户端"""
        try:
            tenant_id = auth_data.get("tenant_id")
            api_key = auth_data.get("api_key")

            if not tenant_id:
                return False

            # 检查租户是否存在
            if tenant_id not in self.tenant_configs:
                return False

            # 检查API密钥
            if api_key and api_key in self.api_keys:
                return self.api_keys[api_key] == tenant_id

            # 如果租户配置中有API密钥，进行验证
            config = self.tenant_configs[tenant_id]
            if config.api_key and api_key == config.api_key:
                return True

            return False

        except Exception as e:
            logger.error(f"客户端认证异常: {e}")
            return False

    def _register_connection(self, connection_id: str, connection: TenantConnection):
        """注册连接"""
        self.connections[connection_id] = connection
        self.stats["active_connections"] += 1
        self.stats["total_connections"] += 1

        # 按租户分组
        if connection.tenant_id not in self.tenant_connections:
            self.tenant_connections[connection.tenant_id] = set()
        self.tenant_connections[connection.tenant_id].add(connection_id)

        # 按智能体分组
        if connection.agent_id not in self.agent_connections:
            self.agent_connections[connection.agent_id] = set()
        self.agent_connections[connection.agent_id].add(connection_id)

        # 按平台分组
        if connection.platform not in self.platform_connections:
            self.platform_connections[connection.platform] = set()
        self.platform_connections[connection.platform].add(connection_id)

        logger.info(f"注册连接: {connection_id} (租户: {connection.tenant_id}, 智能体: {connection.agent_id})")

    def _unregister_connection(self, connection_id: str, connection: TenantConnection):
        """注销连接"""
        if connection_id in self.connections:
            del self.connections[connection_id]
            self.stats["active_connections"] -= 1

        # 从各分组中移除
        if connection.tenant_id in self.tenant_connections:
            self.tenant_connections[connection.tenant_id].discard(connection_id)
            if not self.tenant_connections[connection.tenant_id]:
                del self.tenant_connections[connection.tenant_id]

        if connection.agent_id in self.agent_connections:
            self.agent_connections[connection.agent_id].discard(connection_id)
            if not self.agent_connections[connection.agent_id]:
                del self.agent_connections[connection.agent_id]

        if connection.platform in self.platform_connections:
            self.platform_connections[connection.platform].discard(connection_id)
            if not self.platform_connections[connection.platform]:
                del self.platform_connections[connection.platform]

        logger.info(f"注销连接: {connection_id}")

    async def _handle_client_messages(self, connection: TenantConnection):
        """处理客户端消息"""
        try:
            async for message in connection.websocket:
                try:
                    data = json.loads(message)
                    await self._process_client_message(connection, data)
                    connection.last_heartbeat = datetime.now()
                    self.stats["messages_received"] += 1

                except json.JSONDecodeError:
                    logger.warning(f"收到无效JSON消息: {message}")
                except Exception as e:
                    logger.error(f"处理客户端消息失败: {e}")

        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            logger.error(f"客户端消息处理异常: {e}")

    async def _process_client_message(self, connection: TenantConnection, data: Dict[str, Any]):
        """处理客户端消息"""
        message_type = data.get("type")

        if message_type == "heartbeat":
            await connection.websocket.send(
                json.dumps({"type": "heartbeat_response", "timestamp": datetime.now().isoformat()})
            )

        elif message_type == "message":
            # 转发消息到租户队列
            await self._route_message_to_tenant(connection, data)

        elif message_type == "subscribe":
            # 订阅主题
            topics = data.get("topics", [])
            for topic in topics:
                connection.subscriptions.add(topic)

        elif message_type == "unsubscribe":
            # 取消订阅
            topics = data.get("topics", [])
            for topic in topics:
                connection.subscriptions.discard(topic)

        # 触发消息接收事件
        if self.on_message_received:
            try:
                await self.on_message_received(connection, data)
            except Exception as e:
                logger.warning(f"触发消息接收事件失败: {e}")

    async def _route_message_to_tenant(self, connection: TenantConnection, data: Dict[str, Any]):
        """路由消息到租户"""
        tenant_id = connection.tenant_id
        if tenant_id in self.message_queues:
            try:
                server_message = ServerMessage(
                    message_id=str(uuid.uuid4()),
                    tenant_id=tenant_id,
                    agent_id=connection.agent_id,
                    platform=connection.platform,
                    chat_stream_id=connection.chat_stream_id,
                    message_type=data.get("message_type", "text"),
                    payload=data.get("payload", {}),
                    priority=MessagePriority(data.get("priority", MessagePriority.NORMAL.value)),
                    timestamp=datetime.now(),
                )

                self.message_queues[tenant_id].put_nowait(server_message)
                logger.debug(f"消息路由到租户队列: {tenant_id}")

            except asyncio.QueueFull:
                logger.warning(f"租户 {tenant_id} 消息队列已满")

    async def send_to_tenant(
        self, tenant_id: str, message_data: Dict[str, Any], exclude_connection: Optional[str] = None
    ) -> int:
        """向租户的所有连接发送消息"""
        sent_count = 0

        if tenant_id not in self.tenant_connections:
            logger.warning(f"租户 {tenant_id} 没有活跃连接")
            return 0

        message = json.dumps(
            {
                "type": "message",
                "tenant_id": tenant_id,
                "payload": message_data,
                "timestamp": datetime.now().isoformat(),
            }
        )

        # 向租户的所有连接发送消息
        connections_to_close = []
        for connection_id in self.tenant_connections[tenant_id]:
            if connection_id == exclude_connection:
                continue

            connection = self.connections.get(connection_id)
            if connection:
                try:
                    await connection.websocket.send(message)
                    sent_count += 1
                    self.stats["messages_sent"] += 1
                except Exception as e:
                    logger.warning(f"发送消息失败 {connection_id}: {e}")
                    connections_to_close.append(connection_id)

        # 清理失败的连接
        for connection_id in connections_to_close:
            connection = self.connections.get(connection_id)
            if connection:
                self._unregister_connection(connection_id, connection)
                try:
                    await connection.websocket.close()
                except Exception:
                    pass

        return sent_count

    async def send_to_agent(
        self, agent_id: str, message_data: Dict[str, Any], exclude_connection: Optional[str] = None
    ) -> int:
        """向特定智能体的所有连接发送消息"""
        sent_count = 0

        if agent_id not in self.agent_connections:
            logger.warning(f"智能体 {agent_id} 没有活跃连接")
            return 0

        message = json.dumps(
            {"type": "message", "agent_id": agent_id, "payload": message_data, "timestamp": datetime.now().isoformat()}
        )

        for connection_id in self.agent_connections[agent_id]:
            if connection_id == exclude_connection:
                continue

            connection = self.connections.get(connection_id)
            if connection:
                try:
                    await connection.websocket.send(message)
                    sent_count += 1
                    self.stats["messages_sent"] += 1
                except Exception as e:
                    logger.warning(f"发送消息失败 {connection_id}: {e}")

        return sent_count

    async def broadcast_to_platform(
        self, platform: str, message_data: Dict[str, Any], exclude_tenant: Optional[str] = None
    ) -> int:
        """向特定平台的所有连接广播消息"""
        sent_count = 0

        if platform not in self.platform_connections:
            logger.warning(f"平台 {platform} 没有活跃连接")
            return 0

        message = json.dumps(
            {
                "type": "broadcast",
                "platform": platform,
                "payload": message_data,
                "timestamp": datetime.now().isoformat(),
            }
        )

        for connection_id in self.platform_connections[platform]:
            connection = self.connections.get(connection_id)
            if connection and connection.tenant_id != exclude_tenant:
                try:
                    await connection.websocket.send(message)
                    sent_count += 1
                    self.stats["messages_sent"] += 1
                except Exception as e:
                    logger.warning(f"广播消息失败 {connection_id}: {e}")

        return sent_count

    async def _cleanup_expired_connections(self):
        """清理过期连接"""
        while self._running:
            try:
                now = datetime.now()
                timeout = timedelta(minutes=5)  # 5分钟超时

                connections_to_close = []
                for connection_id, connection in self.connections.items():
                    if now - connection.last_heartbeat > timeout:
                        connections_to_close.append((connection_id, connection))

                for connection_id, connection in connections_to_close:
                    logger.info(f"清理过期连接: {connection_id}")
                    self._unregister_connection(connection_id, connection)
                    try:
                        await connection.websocket.close()
                    except Exception:
                        pass

                await asyncio.sleep(60)  # 每分钟检查一次

            except Exception as e:
                logger.error(f"清理过期连接异常: {e}")
                await asyncio.sleep(60)

    def get_stats(self) -> Dict[str, Any]:
        """获取服务器统计信息"""
        stats = self.stats.copy()
        if stats["server_start_time"]:
            uptime = datetime.now() - stats["server_start_time"]
            stats["uptime_seconds"] = uptime.total_seconds()
        stats["tenant_count"] = len(self.tenant_connections)
        stats["agent_count"] = len(self.agent_connections)
        stats["platform_count"] = len(self.platform_connections)
        return stats

    def get_tenant_connections(self, tenant_id: str) -> List[TenantConnection]:
        """获取租户的所有连接"""
        if tenant_id not in self.tenant_connections:
            return []

        connections = []
        for connection_id in self.tenant_connections[tenant_id]:
            connection = self.connections.get(connection_id)
            if connection:
                connections.append(connection)

        return connections

    def get_connection_info(self, connection_id: str) -> Optional[TenantConnection]:
        """获取连接信息"""
        return self.connections.get(connection_id)


# 全局服务器实例
_global_tenant_server: Optional[TenantMessageServer] = None


def get_tenant_message_server() -> TenantMessageServer:
    """获取全局租户消息服务器"""
    global _global_tenant_server
    if _global_tenant_server is None:
        _global_tenant_server = TenantMessageServer()
    return _global_tenant_server


async def start_tenant_message_server(host: str = "localhost", port: int = 8091):
    """启动租户消息服务器"""
    server = get_tenant_message_server()
    await server.start()


async def stop_tenant_message_server():
    """停止租户消息服务器"""
    server = get_tenant_message_server()
    await server.stop()
