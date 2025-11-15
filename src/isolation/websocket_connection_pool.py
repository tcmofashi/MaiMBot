"""
WebSocket连接池管理器
避免重复连接和并发recv调用冲突
"""

import asyncio
import logging
from typing import Dict, Optional, Any
from dataclasses import dataclass
from threading import Lock

from maim_message.tenant_client import TenantMessageClient, ClientConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConnectionKey:
    """连接键 - 每个客户端都有唯一标识"""
    client_id: str
    tenant_id: str
    agent_id: str
    platform: str
    server_url: str
    api_key: Optional[str] = None


@dataclass
class ConnectionEntry:
    """连接条目 - 每个条目管理一个独立连接"""
    client: TenantMessageClient
    client_id: str
    created_at: float
    last_used: float
    is_active: bool = True


class WebSocketConnectionPool:
    """WebSocket连接池管理器"""

    def __init__(self, max_connections: int = 10, connection_timeout: float = 300.0):
        self.max_connections = max_connections
        self.connection_timeout = connection_timeout

        # 连接池
        self._connections: Dict[ConnectionKey, ConnectionEntry] = {}

        # 线程安全锁
        self._pool_lock = Lock()

        # 清理任务
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """启动连接池"""
        if self._running:
            return

        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("WebSocket连接池已启动")

    async def stop(self):
        """停止连接池"""
        if not self._running:
            return

        self._running = False

        # 取消清理任务
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # 关闭所有连接
        with self._pool_lock:
            for entry in self._connections.values():
                try:
                    await entry.client.disconnect()
                except Exception as e:
                    logger.error(f"关闭连接失败: {e}")
            self._connections.clear()

        logger.info("WebSocket连接池已停止")

    async def get_client(
        self,
        tenant_id: str,
        agent_id: str,
        platform: str,
        server_url: str,
        api_key: Optional[str] = None,
        **config_kwargs
    ) -> TenantMessageClient:
        """获取客户端连接 - 为每个客户端创建独立连接"""
        import uuid

        # 为每个客户端生成唯一ID
        client_id = str(uuid.uuid4())
        key = ConnectionKey(
            client_id=client_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            platform=platform,
            server_url=server_url,
            api_key=api_key
        )

        # 检查连接池是否已满
        with self._pool_lock:
            if len(self._connections) >= self.max_connections:
                # 清理最久未使用的连接
                await self._evict_lru_connection()

        # 创建新连接（不复用现有连接）
        logger.info(f"创建新的独立WebSocket连接: {client_id} ({tenant_id}/{agent_id})")
        client_config = ClientConfig(
            tenant_id=tenant_id,
            agent_id=agent_id,
            platform=platform,
            server_url=server_url,
            api_key=api_key,
            **config_kwargs
        )

        client = TenantMessageClient(client_config)

        # 连接到服务器
        if not await client.connect():
            raise ConnectionError(f"无法连接到服务器: {server_url}")

        # 添加到连接池
        current_time = asyncio.get_event_loop().time()
        entry = ConnectionEntry(
            client=client,
            client_id=client_id,
            created_at=current_time,
            last_used=current_time,
            is_active=True
        )

        with self._pool_lock:
            self._connections[key] = entry

        return client

    async def release_client(self, client: TenantMessageClient):
        """释放客户端连接"""
        with self._pool_lock:
            # 查找对应的连接条目
            found_key = None
            found_entry = None

            for key, entry in self._connections.items():
                if entry.client is client:
                    found_key = key
                    found_entry = entry
                    break

            if found_entry:
                found_entry.is_active = False
                found_entry.last_used = asyncio.get_event_loop().time()
                logger.info(f"标记连接为非活跃: {found_entry.client_id}")
            else:
                logger.warning(f"尝试释放不存在的连接")

    async def _evict_lru_connection(self):
        """清理最久未使用的非活跃连接"""
        if not self._connections:
            return

        # 找到最久未使用的非活跃连接
        lru_key = None
        lru_time = float('inf')

        for key, entry in self._connections.items():
            if not entry.is_active and entry.last_used < lru_time:
                lru_key = key
                lru_time = entry.last_used

        if lru_key:
            entry = self._connections[lru_key]
            logger.info(f"清理最久未使用的连接: {entry.client_id}")
            try:
                await entry.client.disconnect()
            except Exception as e:
                logger.error(f"清理连接失败: {e}")
            finally:
                del self._connections[lru_key]
        else:
            # 如果没有非活跃连接，强制清理最久未使用的连接
            for key, entry in self._connections.items():
                if entry.last_used < lru_time:
                    lru_key = key
                    lru_time = entry.last_used

            if lru_key:
                entry = self._connections[lru_key]
                logger.warning(f"强制清理活跃连接: {entry.client_id}")
                try:
                    await entry.client.disconnect()
                except Exception as e:
                    logger.error(f"清理连接失败: {e}")
                finally:
                    del self._connections[lru_key]

    async def _cleanup_loop(self):
        """清理循环"""
        while self._running:
            try:
                await asyncio.sleep(60)  # 每分钟清理一次
                await self._cleanup_expired_connections()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"清理循环异常: {e}")

    async def _cleanup_expired_connections(self):
        """清理过期连接"""
        current_time = asyncio.get_event_loop().time()
        expired_keys = []

        with self._pool_lock:
            for key, entry in self._connections.items():
                if (not entry.is_active and
                    current_time - entry.last_used > self.connection_timeout):
                    expired_keys.append(key)

        for key in expired_keys:
            with self._pool_lock:
                if key in self._connections:
                    entry = self._connections[key]
                    logger.info(f"清理过期连接: {entry.client_id}")
                    try:
                        await entry.client.disconnect()
                    except Exception as e:
                        logger.error(f"清理过期连接失败: {e}")
                    finally:
                        del self._connections[key]

    def get_stats(self) -> Dict[str, Any]:
        """获取连接池统计信息"""
        with self._pool_lock:
            total_connections = len(self._connections)
            active_connections = sum(1 for entry in self._connections.values() if entry.is_active)
            idle_connections = total_connections - active_connections

            return {
                "total_connections": total_connections,
                "active_connections": active_connections,
                "idle_connections": idle_connections,
                "max_connections": self.max_connections,
                "connection_timeout": self.connection_timeout,
                "running": self._running
            }


# 全局连接池实例
_global_pool: Optional[WebSocketConnectionPool] = None


def get_connection_pool() -> WebSocketConnectionPool:
    """获取全局连接池实例"""
    global _global_pool
    if _global_pool is None:
        _global_pool = WebSocketConnectionPool()
    return _global_pool


async def start_global_pool():
    """启动全局连接池"""
    pool = get_connection_pool()
    await pool.start()


async def stop_global_pool():
    """停止全局连接池"""
    global _global_pool
    if _global_pool:
        await _global_pool.stop()
        _global_pool = None