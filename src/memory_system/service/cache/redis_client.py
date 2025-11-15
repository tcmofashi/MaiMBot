"""
记忆服务的Redis客户端

提供缓存管理、会话存储和分布式锁功能。
"""

import os
import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

import aioredis
from aioredis import Redis

logger = logging.getLogger(__name__)

# 全局Redis客户端
_redis_client: Optional[Redis] = None
_redis_url: Optional[str] = None


async def init_redis() -> None:
    """初始化Redis连接"""
    global _redis_client, _redis_url

    try:
        _redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

        logger.info(f"连接Redis: {_redis_url.split('@')[1] if '@' in _redis_url else _redis_url}")

        # 创建Redis连接池
        _redis_client = await aioredis.from_url(
            _redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=int(os.getenv("REDIS_POOL_SIZE", "10")),
            retry_on_timeout=True,
            socket_timeout=5,
            socket_connect_timeout=5,
        )

        # 测试连接
        await _redis_client.ping()
        logger.info("Redis连接初始化成功")

    except Exception as e:
        logger.error(f"Redis连接初始化失败: {e}")
        raise


async def close_redis() -> None:
    """关闭Redis连接"""
    global _redis_client

    try:
        if _redis_client:
            await _redis_client.close()
            _redis_client = None
            logger.info("Redis连接已关闭")

    except Exception as e:
        logger.error(f"关闭Redis连接失败: {e}")


def get_redis_client() -> Redis:
    """获取Redis客户端"""
    if not _redis_client:
        raise RuntimeError("Redis未初始化，请先调用 init_redis()")
    return _redis_client


class RedisCache:
    """Redis缓存管理器"""

    def __init__(self, prefix: str = "memory_service", default_ttl: int = 3600):
        """
        初始化缓存管理器

        Args:
            prefix: 缓存键前缀
            default_ttl: 默认过期时间（秒）
        """
        self.prefix = prefix
        self.default_ttl = default_ttl
        self.redis = get_redis_client()

    def _make_key(self, key: str) -> str:
        """生成完整的缓存键"""
        return f"{self.prefix}:{key}"

    async def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        try:
            full_key = self._make_key(key)
            value = await self.redis.get(full_key)

            if value is None:
                return None

            # 尝试JSON反序列化
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value

        except Exception as e:
            logger.error(f"获取缓存失败 {key}: {e}")
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None, serialize: bool = True) -> bool:
        """设置缓存值"""
        try:
            full_key = self._make_key(key)

            # 序列化值
            if serialize and not isinstance(value, (str, int, float)):
                value = json.dumps(value, default=str, ensure_ascii=False)

            # 设置过期时间
            expire_time = ttl if ttl is not None else self.default_ttl

            result = await self.redis.setex(full_key, expire_time, value)
            return bool(result)

        except Exception as e:
            logger.error(f"设置缓存失败 {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """删除缓存"""
        try:
            full_key = self._make_key(key)
            result = await self.redis.delete(full_key)
            return bool(result)

        except Exception as e:
            logger.error(f"删除缓存失败 {key}: {e}")
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """按模式删除缓存"""
        try:
            full_pattern = self._make_key(pattern)
            keys = await self.redis.keys(full_pattern)

            if not keys:
                return 0

            result = await self.redis.delete(*keys)
            return result

        except Exception as e:
            logger.error(f"按模式删除缓存失败 {pattern}: {e}")
            return 0

    async def exists(self, key: str) -> bool:
        """检查缓存是否存在"""
        try:
            full_key = self._make_key(key)
            result = await self.redis.exists(full_key)
            return bool(result)

        except Exception as e:
            logger.error(f"检查缓存存在性失败 {key}: {e}")
            return False

    async def expire(self, key: str, ttl: int) -> bool:
        """设置缓存过期时间"""
        try:
            full_key = self._make_key(key)
            result = await self.redis.expire(full_key, ttl)
            return bool(result)

        except Exception as e:
            logger.error(f"设置缓存过期时间失败 {key}: {e}")
            return False

    async def ttl(self, key: str) -> int:
        """获取缓存剩余时间"""
        try:
            full_key = self._make_key(key)
            return await self.redis.ttl(full_key)

        except Exception as e:
            logger.error(f"获取缓存TTL失败 {key}: {e}")
            return -1

    async def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """递增计数器"""
        try:
            full_key = self._make_key(key)
            result = await self.redis.incrby(full_key, amount)
            return result

        except Exception as e:
            logger.error(f"递增计数器失败 {key}: {e}")
            return None

    async def decrement(self, key: str, amount: int = 1) -> Optional[int]:
        """递减计数器"""
        try:
            full_key = self._make_key(key)
            result = await self.redis.decrby(full_key, amount)
            return result

        except Exception as e:
            logger.error(f"递减计数器失败 {key}: {e}")
            return None

    async def hget(self, key: str, field: str) -> Optional[Any]:
        """获取哈希字段值"""
        try:
            full_key = self._make_key(key)
            value = await self.redis.hget(full_key, field)

            if value is None:
                return None

            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value

        except Exception as e:
            logger.error(f"获取哈希字段失败 {key}.{field}: {e}")
            return None

    async def hset(self, key: str, field: str, value: Any, ttl: Optional[int] = None, serialize: bool = True) -> bool:
        """设置哈希字段值"""
        try:
            full_key = self._make_key(key)

            # 序列化值
            if serialize and not isinstance(value, (str, int, float)):
                value = json.dumps(value, default=str, ensure_ascii=False)

            await self.redis.hset(full_key, field, value)

            # 设置过期时间（仅在第一次设置时）
            if ttl is not None and await self.redis.hlen(full_key) == 1:
                await self.redis.expire(full_key, ttl)

            return True

        except Exception as e:
            logger.error(f"设置哈希字段失败 {key}.{field}: {e}")
            return False

    async def hgetall(self, key: str) -> Dict[str, Any]:
        """获取所有哈希字段"""
        try:
            full_key = self._make_key(key)
            result = await self.redis.hgetall(full_key)

            # 反序列化值
            deserialized_result = {}
            for field, value in result.items():
                try:
                    deserialized_result[field] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    deserialized_result[field] = value

            return deserialized_result

        except Exception as e:
            logger.error(f"获取所有哈希字段失败 {key}: {e}")
            return {}

    async def hdel(self, key: str, *fields: str) -> int:
        """删除哈希字段"""
        try:
            full_key = self._make_key(key)
            result = await self.redis.hdel(full_key, *fields)
            return result

        except Exception as e:
            logger.error(f"删除哈希字段失败 {key}: {e}")
            return 0

    async def lpush(self, key: str, *values: Any, ttl: Optional[int] = None) -> Optional[int]:
        """列表左推"""
        try:
            full_key = self._make_key(key)

            # 序列化值
            serialized_values = []
            for value in values:
                if isinstance(value, (dict, list)):
                    serialized_values.append(json.dumps(value, default=str, ensure_ascii=False))
                else:
                    serialized_values.append(str(value))

            result = await self.redis.lpush(full_key, *serialized_values)

            # 设置过期时间
            if ttl is not None:
                await self.redis.expire(full_key, ttl)

            return result

        except Exception as e:
            logger.error(f"列表左推失败 {key}: {e}")
            return None

    async def rpop(self, key: str) -> Optional[Any]:
        """列表右弹"""
        try:
            full_key = self._make_key(key)
            value = await self.redis.rpop(full_key)

            if value is None:
                return None

            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value

        except Exception as e:
            logger.error(f"列表右弹失败 {key}: {e}")
            return None

    async def lrange(self, key: str, start: int = 0, end: int = -1) -> List[Any]:
        """获取列表范围"""
        try:
            full_key = self._make_key(key)
            values = await self.redis.lrange(full_key, start, end)

            # 反序列化值
            result = []
            for value in values:
                try:
                    result.append(json.loads(value))
                except (json.JSONDecodeError, TypeError):
                    result.append(value)

            return result

        except Exception as e:
            logger.error(f"获取列表范围失败 {key}: {e}")
            return []


class RedisDistributedLock:
    """Redis分布式锁"""

    def __init__(self, redis_client: Redis, key: str, timeout: int = 30):
        """
        初始化分布式锁

        Args:
            redis_client: Redis客户端
            key: 锁键
            timeout: 超时时间（秒）
        """
        self.redis = redis_client
        self.key = f"lock:{key}"
        self.timeout = timeout
        self.identifier = None

    async def acquire(self) -> bool:
        """获取锁"""
        try:
            import time

            self.identifier = f"{int(time.time() * 1000)}-{os.getpid()}"
            result = await self.redis.set(self.key, self.identifier, ex=self.timeout, nx=True)
            return bool(result)

        except Exception as e:
            logger.error(f"获取分布式锁失败 {self.key}: {e}")
            return False

    async def release(self) -> bool:
        """释放锁"""
        try:
            if not self.identifier:
                return False

            # Lua脚本确保原子性释放锁
            lua_script = """
                if redis.call("get", KEYS[1]) == ARGV[1] then
                    return redis.call("del", KEYS[1])
                else
                    return 0
                end
            """

            result = await self.redis.eval(lua_script, 1, self.key, self.identifier)

            return bool(result)

        except Exception as e:
            logger.error(f"释放分布式锁失败 {self.key}: {e}")
            return False

    async def __aenter__(self):
        """异步上下文管理器入口"""
        if await self.acquire():
            return self
        else:
            raise RuntimeError(f"无法获取锁: {self.key}")

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.release()


# 便捷函数
async def check_redis_health() -> Dict[str, Any]:
    """检查Redis健康状态"""
    try:
        if not _redis_client:
            return {"status": "disconnected", "error": "Redis客户端未初始化"}

        # 执行ping测试
        start_time = datetime.utcnow()
        await _redis_client.ping()
        response_time = (datetime.utcnow() - start_time).total_seconds() * 1000

        # 获取Redis信息
        info = await _redis_client.info()

        return {
            "status": "connected",
            "response_time_ms": round(response_time, 2),
            "redis_version": info.get("redis_version"),
            "used_memory": info.get("used_memory_human"),
            "connected_clients": info.get("connected_clients"),
            "total_commands_processed": info.get("total_commands_processed"),
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}


async def get_redis_stats() -> Dict[str, Any]:
    """获取Redis统计信息"""
    try:
        if not _redis_client:
            return {"error": "Redis客户端未初始化"}

        info = await _redis_client.info()
        config = await _redis_client.config_get("*")

        return {
            "server": {
                "redis_version": info.get("redis_version"),
                "redis_mode": info.get("redis_mode"),
                "os": info.get("os"),
                "arch_bits": info.get("arch_bits"),
                "uptime_in_seconds": info.get("uptime_in_seconds"),
            },
            "memory": {
                "used_memory": info.get("used_memory"),
                "used_memory_human": info.get("used_memory_human"),
                "used_memory_peak": info.get("used_memory_peak"),
                "used_memory_peak_human": info.get("used_memory_peak_human"),
                "maxmemory": config.get("maxmemory"),
            },
            "clients": {
                "connected_clients": info.get("connected_clients"),
                "client_recent_max_input_buffer": info.get("client_recent_max_input_buffer"),
                "client_recent_max_output_buffer": info.get("client_recent_max_output_buffer"),
            },
            "stats": {
                "total_commands_processed": info.get("total_commands_processed"),
                "total_connections_received": info.get("total_connections_received"),
                "keyspace_hits": info.get("keyspace_hits"),
                "keyspace_misses": info.get("keyspace_misses"),
                "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec"),
            },
        }

    except Exception as e:
        return {"error": f"获取Redis统计失败: {str(e)}"}
