"""
记忆服务的缓存管理器

提供记忆搜索结果、统计数据和会话的缓存管理。
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
from hashlib import md5

from .redis_client import RedisCache

logger = logging.getLogger(__name__)


class MemoryCacheManager:
    """记忆缓存管理器"""

    def __init__(self):
        self.cache = RedisCache(prefix="memory", default_ttl=3600)

    async def get_memories(
        self,
        tenant_id: str,
        agent_id: str,
        level: Optional[str] = None,
        platform: Optional[str] = None,
        scope_id: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        获取缓存的记忆列表

        Args:
            tenant_id: 租户ID
            agent_id: 智能体ID
            level: 记忆级别
            platform: 平台
            scope_id: 作用域ID
            limit: 限制数量
            offset: 偏移量

        Returns:
            记忆列表或None
        """
        try:
            cache_key = self._make_memories_key(tenant_id, agent_id, level, platform, scope_id, limit, offset)
            return await self.cache.get(cache_key)

        except Exception as e:
            logger.error(f"获取缓存记忆失败: {e}")
            return None

    async def set_memories(
        self,
        tenant_id: str,
        agent_id: str,
        memories: List[Dict[str, Any]],
        level: Optional[str] = None,
        platform: Optional[str] = None,
        scope_id: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
        ttl: int = 1800,  # 30分钟
    ) -> bool:
        """
        缓存记忆列表

        Args:
            tenant_id: 租户ID
            agent_id: 智能体ID
            memories: 记忆列表
            level: 记忆级别
            platform: 平台
            scope_id: 作用域ID
            limit: 限制数量
            offset: 偏移量
            ttl: 缓存时间

        Returns:
            是否成功
        """
        try:
            cache_key = self._make_memories_key(tenant_id, agent_id, level, platform, scope_id, limit, offset)
            return await self.cache.set(cache_key, memories, ttl=ttl)

        except Exception as e:
            logger.error(f"缓存记忆失败: {e}")
            return False

    async def get_memory(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """
        获取单个缓存的记忆

        Args:
            memory_id: 记忆ID

        Returns:
            记忆详情或None
        """
        try:
            cache_key = f"memory:{memory_id}"
            return await self.cache.get(cache_key)

        except Exception as e:
            logger.error(f"获取缓存记忆详情失败 {memory_id}: {e}")
            return None

    async def set_memory(
        self,
        memory_id: str,
        memory_data: Dict[str, Any],
        ttl: int = 3600,  # 1小时
    ) -> bool:
        """
        缓存单个记忆

        Args:
            memory_id: 记忆ID
            memory_data: 记忆数据
            ttl: 缓存时间

        Returns:
            是否成功
        """
        try:
            cache_key = f"memory:{memory_id}"
            return await self.cache.set(cache_key, memory_data, ttl=ttl)

        except Exception as e:
            logger.error(f"缓存记忆详情失败 {memory_id}: {e}")
            return False

    async def invalidate_memory(self, memory_id: str) -> bool:
        """
        使单个记忆缓存失效

        Args:
            memory_id: 记忆ID

        Returns:
            是否成功
        """
        try:
            cache_key = f"memory:{memory_id}"
            return await self.cache.delete(cache_key)

        except Exception as e:
            logger.error(f"使记忆缓存失效失败 {memory_id}: {e}")
            return False

    async def invalidate_tenant_memories(self, tenant_id: str, agent_id: str) -> int:
        """
        使租户的所有记忆缓存失效

        Args:
            tenant_id: 租户ID
            agent_id: 智能体ID

        Returns:
            删除的缓存数量
        """
        try:
            pattern = f"memories:{tenant_id}:{agent_id}:*"
            return await self.cache.delete_pattern(pattern)

        except Exception as e:
            logger.error(f"使租户记忆缓存失败 {tenant_id}:{agent_id}: {e}")
            return 0

    async def _make_memories_key(
        self,
        tenant_id: str,
        agent_id: str,
        level: Optional[str],
        platform: Optional[str],
        scope_id: Optional[str],
        limit: int,
        offset: int,
    ) -> str:
        """生成记忆列表缓存键"""
        key_parts = ["memories", tenant_id, agent_id]

        if level:
            key_parts.append(level)
        if platform:
            key_parts.append(platform)
        if scope_id:
            key_parts.append(scope_id)

        key_parts.extend([f"limit:{limit}", f"offset:{offset}"])

        return ":".join(key_parts)


class SearchCacheManager:
    """搜索缓存管理器"""

    def __init__(self):
        self.cache = RedisCache(prefix="search", default_ttl=900)  # 15分钟

    async def get_search_results(
        self, tenant_id: str, agent_id: str, query: str, filters: Dict[str, Any], limit: int = 10, offset: int = 0
    ) -> Optional[Dict[str, Any]]:
        """
        获取缓存的搜索结果

        Args:
            tenant_id: 租户ID
            agent_id: 智能体ID
            query: 搜索查询
            filters: 搜索过滤器
            limit: 限制数量
            offset: 偏移量

        Returns:
            搜索结果或None
        """
        try:
            cache_key = self._make_search_key(tenant_id, agent_id, query, filters, limit, offset)
            return await self.cache.get(cache_key)

        except Exception as e:
            logger.error(f"获取缓存搜索结果失败: {e}")
            return None

    async def set_search_results(
        self,
        tenant_id: str,
        agent_id: str,
        query: str,
        filters: Dict[str, Any],
        results: Dict[str, Any],
        limit: int = 10,
        offset: int = 0,
        ttl: int = 900,  # 15分钟
    ) -> bool:
        """
        缓存搜索结果

        Args:
            tenant_id: 租户ID
            agent_id: 智能体ID
            query: 搜索查询
            filters: 搜索过滤器
            results: 搜索结果
            limit: 限制数量
            offset: 偏移量
            ttl: 缓存时间

        Returns:
            是否成功
        """
        try:
            cache_key = self._make_search_key(tenant_id, agent_id, query, filters, limit, offset)
            return await self.cache.set(cache_key, results, ttl=ttl)

        except Exception as e:
            logger.error(f"缓存搜索结果失败: {e}")
            return False

    async def _make_search_key(
        self, tenant_id: str, agent_id: str, query: str, filters: Dict[str, Any], limit: int, offset: int
    ) -> str:
        """生成搜索缓存键"""
        # 创建查询指纹
        query_fingerprint = md5(f"{query}_{str(sorted(filters.items()))}".encode("utf-8")).hexdigest()[:16]

        return f"search:{tenant_id}:{agent_id}:{query_fingerprint}:{limit}:{offset}"


class StatsCacheManager:
    """统计缓存管理器"""

    def __init__(self):
        self.cache = RedisCache(prefix="stats", default_ttl=300)  # 5分钟

    async def get_memory_stats(self, tenant_id: str, agent_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        获取缓存的记忆统计

        Args:
            tenant_id: 租户ID
            agent_id: 智能体ID

        Returns:
            统计数据或None
        """
        try:
            cache_key = f"memory_stats:{tenant_id}"
            if agent_id:
                cache_key += f":{agent_id}"

            return await self.cache.get(cache_key)

        except Exception as e:
            logger.error(f"获取缓存记忆统计失败: {e}")
            return None

    async def set_memory_stats(
        self,
        tenant_id: str,
        stats: Dict[str, Any],
        agent_id: Optional[str] = None,
        ttl: int = 300,  # 5分钟
    ) -> bool:
        """
        缓存记忆统计

        Args:
            tenant_id: 租户ID
            stats: 统计数据
            agent_id: 智能体ID
            ttl: 缓存时间

        Returns:
            是否成功
        """
        try:
            cache_key = f"memory_stats:{tenant_id}"
            if agent_id:
                cache_key += f":{agent_id}"

            return await self.cache.set(cache_key, stats, ttl=ttl)

        except Exception as e:
            logger.error(f"缓存记忆统计失败: {e}")
            return False

    async def get_system_stats(self) -> Optional[Dict[str, Any]]:
        """获取缓存的系统统计"""
        try:
            return await self.cache.get("system_stats")

        except Exception as e:
            logger.error(f"获取缓存系统统计失败: {e}")
            return None

    async def set_system_stats(
        self,
        stats: Dict[str, Any],
        ttl: int = 300,  # 5分钟
    ) -> bool:
        """
        缓存系统统计

        Args:
            stats: 统计数据
            ttl: 缓存时间

        Returns:
            是否成功
        """
        try:
            return await self.cache.set("system_stats", stats, ttl=ttl)

        except Exception as e:
            logger.error(f"缓存系统统计失败: {e}")
            return False


class SessionCacheManager:
    """会话缓存管理器"""

    def __init__(self):
        self.cache = RedisCache(prefix="session", default_ttl=7200)  # 2小时

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        获取会话数据

        Args:
            session_id: 会话ID

        Returns:
            会话数据或None
        """
        try:
            return await self.cache.get(f"session:{session_id}")

        except Exception as e:
            logger.error(f"获取会话缓存失败 {session_id}: {e}")
            return None

    async def set_session(
        self,
        session_id: str,
        session_data: Dict[str, Any],
        ttl: int = 7200,  # 2小时
    ) -> bool:
        """
        设置会话数据

        Args:
            session_id: 会话ID
            session_data: 会话数据
            ttl: 缓存时间

        Returns:
            是否成功
        """
        try:
            return await self.cache.set(f"session:{session_id}", session_data, ttl=ttl)

        except Exception as e:
            logger.error(f"设置会话缓存失败 {session_id}: {e}")
            return False

    async def delete_session(self, session_id: str) -> bool:
        """
        删除会话数据

        Args:
            session_id: 会话ID

        Returns:
            是否成功
        """
        try:
            return await self.cache.delete(f"session:{session_id}")

        except Exception as e:
            logger.error(f"删除会话缓存失败 {session_id}: {e}")
            return False

    async def extend_session(self, session_id: str, ttl: int = 7200) -> bool:
        """
        延长会话过期时间

        Args:
            session_id: 会话ID
            ttl: 新的过期时间

        Returns:
            是否成功
        """
        try:
            return await self.cache.expire(f"session:{session_id}", ttl)

        except Exception as e:
            logger.error(f"延长会话时间失败 {session_id}: {e}")
            return False


class RateLimitCacheManager:
    """速率限制缓存管理器"""

    def __init__(self):
        self.cache = RedisCache(prefix="rate_limit", default_ttl=3600)

    async def check_rate_limit(self, key: str, limit: int, window: int = 60) -> Dict[str, Any]:
        """
        检查速率限制

        Args:
            key: 限制键（通常是用户ID或IP）
            limit: 限制次数
            window: 时间窗口（秒）

        Returns:
            限制状态信息
        """
        try:
            current_time = int(datetime.utcnow().timestamp())
            window_start = current_time - window

            # 使用滑动窗口算法
            pipe = self.cache.redis.pipeline()

            # 移除过期的请求记录
            pipe.zremrangebyscore(f"rate:{key}", 0, window_start)

            # 获取当前窗口内的请求数
            pipe.zcard(f"rate:{key}")

            # 添加当前请求
            pipe.zadd(f"rate:{key}", {str(current_time): current_time})

            # 设置过期时间
            pipe.expire(f"rate:{key}", window)

            results = await pipe.execute()
            current_requests = results[1]

            remaining = max(0, limit - current_requests)
            reset_time = window_start + window

            return {
                "allowed": current_requests < limit,
                "limit": limit,
                "remaining": remaining,
                "current": current_requests,
                "reset_time": reset_time,
                "window": window,
            }

        except Exception as e:
            logger.error(f"检查速率限制失败 {key}: {e}")
            return {
                "allowed": True,  # 出错时允许通过
                "error": str(e),
            }

    async def reset_rate_limit(self, key: str) -> bool:
        """
        重置速率限制

        Args:
            key: 限制键

        Returns:
            是否成功
        """
        try:
            return await self.cache.delete(f"rate:{key}")

        except Exception as e:
            logger.error(f"重置速率限制失败 {key}: {e}")
            return False


# 全局缓存管理器实例
memory_cache = MemoryCacheManager()
search_cache = SearchCacheManager()
stats_cache = StatsCacheManager()
session_cache = SessionCacheManager()
rate_limit_cache = RateLimitCacheManager()


# 便捷函数
async def invalidate_all_cache(tenant_id: str, agent_id: str) -> int:
    """
    使指定租户和智能体的所有缓存失效

    Args:
        tenant_id: 租户ID
        agent_id: 智能体ID

    Returns:
        删除的缓存数量
    """
    try:
        total_deleted = 0

        # 清理记忆缓存
        total_deleted += await memory_cache.invalidate_tenant_memories(tenant_id, agent_id)

        # 清理搜索缓存
        search_pattern = f"search:{tenant_id}:{agent_id}:*"
        total_deleted += await memory_cache.cache.delete_pattern(search_pattern)

        # 清理统计缓存
        stats_pattern = f"stats:memory_stats:{tenant_id}:*"
        total_deleted += await memory_cache.cache.delete_pattern(stats_pattern)

        logger.info(f"清理缓存完成: 租户={tenant_id}, 智能体={agent_id}, 删除数量={total_deleted}")

        return total_deleted

    except Exception as e:
        logger.error(f"清理所有缓存失败 {tenant_id}:{agent_id}: {e}")
        return 0
