"""
记忆服务客户端SDK

提供与记忆服务通信的异步客户端接口。
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
from uuid import UUID

import aiohttp

from .service.models.schemas import (
    MemoryResponse,
    MemoryListResponse,
    BatchOperationResponse,
    SuccessResponse,
    ConflictResponse,
)

logger = logging.getLogger(__name__)


class MemoryServiceClient:
    """记忆服务客户端"""

    def __init__(
        self,
        base_url: str,
        tenant_id: str,
        agent_id: str,
        api_key: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        """
        初始化记忆服务客户端

        Args:
            base_url: 服务基础URL
            tenant_id: 租户ID
            agent_id: 智能体ID
            api_key: API密钥（可选）
            timeout: 请求超时时间（秒）
            max_retries: 最大重试次数
        """
        self.base_url = base_url.rstrip("/")
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.api_key = api_key
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_retries = max_retries

        # 默认请求头
        self.default_headers = {
            "X-Tenant-ID": tenant_id,
            "X-Agent-ID": agent_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        if api_key:
            self.default_headers["Authorization"] = f"Bearer {api_key}"

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        发送HTTP请求

        Args:
            method: HTTP方法
            endpoint: API端点
            data: 请求数据
            params: 查询参数
            headers: 额外的请求头

        Returns:
            响应数据
        """
        url = f"{self.base_url}{endpoint}"
        request_headers = {**self.default_headers, **(headers or {})}

        for attempt in range(self.max_retries + 1):
            try:
                async with aiohttp.ClientSession(timeout=self.timeout) as session:
                    async with session.request(
                        method, url, json=data, params=params, headers=request_headers
                    ) as response:
                        response_text = await response.text()

                        if response.status >= 400:
                            try:
                                error_data = json.loads(response_text)
                                raise MemoryServiceError(
                                    status_code=response.status,
                                    message=error_data.get("error", {}).get("message", "未知错误"),
                                    details=error_data.get("error", {}),
                                )
                            except json.JSONDecodeError:
                                raise MemoryServiceError(
                                    status_code=response.status,
                                    message=response_text,
                                    details={"status": response.status},
                                )

                        if response_text:
                            return json.loads(response_text)
                        else:
                            return {}

            except MemoryServiceError:
                raise
            except Exception as e:
                if attempt == self.max_retries:
                    raise MemoryServiceError(message=f"请求失败: {str(e)}", details={"attempts": attempt + 1})
                logger.warning(f"请求失败，重试 {attempt + 1}/{self.max_retries}: {e}")

    # 记忆相关API
    async def add_memory(
        self,
        title: str,
        content: str,
        level: str,
        platform: Optional[str] = None,
        scope_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        expires_at: Optional[datetime] = None,
    ) -> MemoryResponse:
        """
        添加记忆

        Args:
            title: 记忆标题
            content: 记忆内容
            level: 记忆级别
            platform: 平台标识
            scope_id: 作用域ID
            tags: 标签列表
            metadata: 元数据
            expires_at: 过期时间

        Returns:
            创建的记忆
        """
        memory_data = {
            "title": title,
            "content": content,
            "level": level,
            "platform": platform,
            "scope_id": scope_id,
            "tags": tags or [],
            "metadata": metadata or {},
        }

        if expires_at:
            memory_data["expires_at"] = expires_at.isoformat()

        response = await self._make_request("POST", "/api/v1/memories", data=memory_data)
        return MemoryResponse(**response)

    async def get_memory(self, memory_id: Union[str, UUID]) -> MemoryResponse:
        """
        获取记忆

        Args:
            memory_id: 记忆ID

        Returns:
            记忆详情
        """
        memory_id_str = str(memory_id)
        response = await self._make_request("GET", f"/api/v1/memories/{memory_id_str}")
        return MemoryResponse(**response)

    async def update_memory(
        self,
        memory_id: Union[str, UUID],
        title: Optional[str] = None,
        content: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        expires_at: Optional[datetime] = None,
        status: Optional[str] = None,
    ) -> MemoryResponse:
        """
        更新记忆

        Args:
            memory_id: 记忆ID
            title: 新标题
            content: 新内容
            tags: 新标签
            metadata: 新元数据
            expires_at: 新过期时间
            status: 新状态

        Returns:
            更新后的记忆
        """
        memory_id_str = str(memory_id)
        update_data = {}

        if title is not None:
            update_data["title"] = title
        if content is not None:
            update_data["content"] = content
        if tags is not None:
            update_data["tags"] = tags
        if metadata is not None:
            update_data["metadata"] = metadata
        if expires_at is not None:
            update_data["expires_at"] = expires_at.isoformat()
        if status is not None:
            update_data["status"] = status

        response = await self._make_request("PUT", f"/api/v1/memories/{memory_id_str}", data=update_data)
        return MemoryResponse(**response)

    async def delete_memory(self, memory_id: Union[str, UUID]) -> SuccessResponse:
        """
        删除记忆

        Args:
            memory_id: 记忆ID

        Returns:
            删除结果
        """
        memory_id_str = str(memory_id)
        response = await self._make_request("DELETE", f"/api/v1/memories/{memory_id_str}")
        return SuccessResponse(**response)

    async def search_memories(
        self,
        query: str,
        level: Optional[str] = None,
        platform: Optional[str] = None,
        scope_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 10,
        offset: int = 0,
        similarity_threshold: float = 0.7,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> MemoryListResponse:
        """
        搜索记忆

        Args:
            query: 搜索查询
            level: 记忆级别过滤
            platform: 平台过滤
            scope_id: 作用域过滤
            tags: 标签过滤
            limit: 返回数量限制
            offset: 偏移量
            similarity_threshold: 相似度阈值
            date_from: 开始日期
            date_to: 结束日期

        Returns:
            搜索结果
        """
        search_data = {"query": query, "limit": limit, "offset": offset, "similarity_threshold": similarity_threshold}

        if level:
            search_data["level"] = level
        if platform:
            search_data["platform"] = platform
        if scope_id:
            search_data["scope_id"] = scope_id
        if tags:
            search_data["tags"] = tags
        if date_from:
            search_data["date_from"] = date_from.isoformat()
        if date_to:
            search_data["date_to"] = date_to.isoformat()

        response = await self._make_request("POST", "/api/v1/memories/search", data=search_data)
        return MemoryListResponse(**response)

    async def query_memories(
        self,
        filters: Dict[str, Any],
        sort_by: str = "created_at",
        sort_order: str = "desc",
        limit: int = 10,
        offset: int = 0,
    ) -> MemoryListResponse:
        """
        复杂查询记忆

        Args:
            filters: 查询过滤器
            sort_by: 排序字段
            sort_order: 排序顺序
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            查询结果
        """
        query_data = {
            "filters": filters,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "limit": limit,
            "offset": offset,
        }

        response = await self._make_request("POST", "/api/v1/memories/query", data=query_data)
        return MemoryListResponse(**response)

    async def aggregate_memories(
        self,
        source_scopes: List[str],
        target_level: str,
        target_platform: Optional[str] = None,
        target_scope_id: Optional[str] = None,
        merge_strategy: str = "append",
    ) -> SuccessResponse:
        """
        聚合记忆

        Args:
            source_scopes: 源作用域列表
            target_level: 目标级别
            target_platform: 目标平台
            target_scope_id: 目标作用域ID
            merge_strategy: 合并策略

        Returns:
            聚合结果
        """
        aggregate_data = {
            "source_scopes": source_scopes,
            "target_level": target_level,
            "merge_strategy": merge_strategy,
        }

        if target_platform:
            aggregate_data["target_platform"] = target_platform
        if target_scope_id:
            aggregate_data["target_scope_id"] = target_scope_id

        response = await self._make_request("POST", "/api/v1/memories/aggregate", data=aggregate_data)
        return SuccessResponse(**response)

    async def batch_create_memories(self, memories: List[Dict[str, Any]]) -> BatchOperationResponse:
        """
        批量创建记忆

        Args:
            memories: 记忆数据列表

        Returns:
            批量操作结果
        """
        batch_data = {"memories": memories}
        response = await self._make_request("POST", "/api/v1/memories/batch", data=batch_data)
        return BatchOperationResponse(**response)

    async def batch_delete_memories(self, memory_ids: List[Union[str, UUID]]) -> BatchOperationResponse:
        """
        批量删除记忆

        Args:
            memory_ids: 记忆ID列表

        Returns:
            批量操作结果
        """
        memory_id_strings = [str(mid) for mid in memory_ids]
        batch_data = {"memory_ids": memory_id_strings}
        response = await self._make_request("DELETE", "/api/v1/memories/batch", data=batch_data)
        return BatchOperationResponse(**response)

    async def get_tenant_agent_memories(
        self,
        tenant_id: str,
        agent_id: str,
        level: Optional[str] = None,
        platform: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> MemoryListResponse:
        """
        获取租户智能体的所有记忆

        Args:
            tenant_id: 租户ID
            agent_id: 智能体ID
            level: 记忆级别过滤
            platform: 平台过滤
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            记忆列表
        """
        params = {"limit": limit, "offset": offset}
        if level:
            params["level"] = level
        if platform:
            params["platform"] = platform

        response = await self._make_request(
            "GET", f"/api/v1/memories/tenant/{tenant_id}/agent/{agent_id}", params=params
        )
        return MemoryListResponse(**response)

    # 冲突跟踪相关API
    async def create_conflict(
        self,
        title: str,
        context: Optional[str] = None,
        platform: Optional[str] = None,
        scope_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        start_following: bool = False,
    ) -> ConflictResponse:
        """
        创建冲突记录

        Args:
            title: 冲突标题
            context: 冲突上下文
            platform: 平台标识
            scope_id: 作用域ID
            chat_id: 聊天ID
            start_following: 是否开始跟踪

        Returns:
            创建的冲突记录
        """
        conflict_data = {
            "title": title,
            "context": context,
            "platform": platform,
            "scope_id": scope_id,
            "chat_id": chat_id,
            "start_following": start_following,
        }

        response = await self._make_request("POST", "/api/v1/conflicts", data=conflict_data)
        return ConflictResponse(**response)

    async def get_conflict(self, conflict_id: Union[str, UUID]) -> ConflictResponse:
        """
        获取冲突记录

        Args:
            conflict_id: 冲突ID

        Returns:
            冲突记录详情
        """
        conflict_id_str = str(conflict_id)
        response = await self._make_request("GET", f"/api/v1/conflicts/{conflict_id_str}")
        return ConflictResponse(**response)

    async def update_conflict(
        self,
        conflict_id: Union[str, UUID],
        title: Optional[str] = None,
        context: Optional[str] = None,
        start_following: Optional[bool] = None,
        resolved: Optional[bool] = None,
    ) -> ConflictResponse:
        """
        更新冲突记录

        Args:
            conflict_id: 冲突ID
            title: 新标题
            context: 新上下文
            start_following: 是否开始跟踪
            resolved: 是否已解决

        Returns:
            更新后的冲突记录
        """
        conflict_id_str = str(conflict_id)
        update_data = {}

        if title is not None:
            update_data["title"] = title
        if context is not None:
            update_data["context"] = context
        if start_following is not None:
            update_data["start_following"] = start_following
        if resolved is not None:
            update_data["resolved"] = resolved

        response = await self._make_request("PUT", f"/api/v1/conflicts/{conflict_id_str}", data=update_data)
        return ConflictResponse(**response)

    async def delete_conflict(self, conflict_id: Union[str, UUID]) -> SuccessResponse:
        """
        删除冲突记录

        Args:
            conflict_id: 冲突ID

        Returns:
            删除结果
        """
        conflict_id_str = str(conflict_id)
        response = await self._make_request("DELETE", f"/api/v1/conflicts/{conflict_id_str}")
        return SuccessResponse(**response)

    # 系统管理API
    async def health_check(self) -> Dict[str, Any]:
        """
        健康检查

        Returns:
            健康状态
        """
        return await self._make_request("GET", "/api/v1/health")

    async def get_system_stats(self) -> Dict[str, Any]:
        """
        获取系统统计

        Returns:
            系统统计信息
        """
        return await self._make_request("GET", "/api/v1/stats")

    async def cleanup_expired_data(self, dry_run: bool = False, older_than_days: int = 30) -> Dict[str, Any]:
        """
        清理过期数据

        Args:
            dry_run: 是否试运行
            older_than_days: 清理多少天前的数据

        Returns:
            清理任务结果
        """
        params = {"dry_run": dry_run, "older_than_days": older_than_days}
        return await self._make_request("POST", "/api/v1/maintenance/cleanup", params=params)


class IsolatedMemoryChest:
    """
    向后兼容的MemoryChest包装器

    提供与原有MemoryChest兼容的接口，底层使用新的记忆服务客户端。
    """

    def __init__(
        self,
        tenant_id: str,
        agent_id: str,
        platform: Optional[str] = None,
        scope_id: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        """
        初始化隔离记忆库

        Args:
            tenant_id: 租户ID
            agent_id: 智能体ID
            platform: 平台标识
            scope_id: 作用域ID
            base_url: 记忆服务URL
        """
        self.base_url = base_url or os.getenv("MEMORY_SERVICE_URL", "http://localhost:8001")
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.platform = platform
        self.scope_id = scope_id

        # 创建客户端
        self.client = MemoryServiceClient(base_url=self.base_url, tenant_id=tenant_id, agent_id=agent_id)

    async def add_one_memory(self, title: str, content: str, **kwargs) -> Dict[str, Any]:
        """添加一个记忆（兼容接口）"""
        level = kwargs.get("level", "chat")
        if self.platform and not kwargs.get("platform"):
            kwargs["platform"] = self.platform
        if self.scope_id and not kwargs.get("scope_id"):
            kwargs["scope_id"] = self.scope_id

        memory = await self.client.add_memory(title, content, level, **kwargs)
        return memory.dict()

    async def remove_one_memory_by_age_weight(self, **kwargs) -> bool:
        """按年龄权重删除记忆（兼容接口）"""
        # 这里可以实现具体的删除逻辑
        # 暂时返回False表示未删除
        logger.warning("remove_one_memory_by_age_weight 尚未实现")
        return False

    async def search_for_answer(self, question: str, **kwargs) -> Optional[Dict[str, Any]]:
        """搜索答案（兼容接口）"""
        search_result = await self.client.search_memories(
            query=question, platform=self.platform, scope_id=self.scope_id, limit=kwargs.get("limit", 5), **kwargs
        )

        if search_result.items:
            # 返回最相似的记忆
            return search_result.items[0].dict()
        return None

    async def get_all_memories(self, **kwargs) -> List[Dict[str, Any]]:
        """获取所有记忆（兼容接口）"""
        memories_result = await self.client.query_memories(
            filters={"platform": self.platform, "scope_id": self.scope_id, **kwargs}, limit=kwargs.get("limit", 100)
        )

        return [memory.dict() for memory in memories_result.items]

    async def count_memories(self, **kwargs) -> int:
        """统计记忆数量（兼容接口）"""
        memories_result = await self.client.query_memories(
            filters={"platform": self.platform, "scope_id": self.scope_id, **kwargs}, limit=1
        )

        return memories_result.total

    # 新增的方法
    async def search_memories(
        self, query: str, level: Optional[str] = None, tags: Optional[List[str]] = None, limit: int = 10, **kwargs
    ) -> List[Dict[str, Any]]:
        """搜索记忆"""
        search_result = await self.client.search_memories(
            query=query, level=level, platform=self.platform, scope_id=self.scope_id, tags=tags, limit=limit, **kwargs
        )

        return [memory.dict() for memory in search_result.items]

    async def get_memory_by_id(self, memory_id: Union[str, UUID]) -> Optional[Dict[str, Any]]:
        """根据ID获取记忆"""
        try:
            memory = await self.client.get_memory(memory_id)
            return memory.dict()
        except Exception as e:
            logger.error(f"获取记忆失败 {memory_id}: {e}")
            return None

    async def update_memory(
        self, memory_id: Union[str, UUID], title: Optional[str] = None, content: Optional[str] = None, **kwargs
    ) -> Optional[Dict[str, Any]]:
        """更新记忆"""
        try:
            memory = await self.client.update_memory(memory_id=memory_id, title=title, content=content, **kwargs)
            return memory.dict()
        except Exception as e:
            logger.error(f"更新记忆失败 {memory_id}: {e}")
            return None

    async def delete_memory(self, memory_id: Union[str, UUID]) -> bool:
        """删除记忆"""
        try:
            await self.client.delete_memory(memory_id)
            return True
        except Exception as e:
            logger.error(f"删除记忆失败 {memory_id}: {e}")
            return False


class MemoryServiceError(Exception):
    """记忆服务错误"""

    def __init__(self, message: str, status_code: Optional[int] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}

    def __str__(self) -> str:
        if self.status_code:
            return f"[{self.status_code}] {self.message}"
        return self.message


# 便捷函数
async def create_memory_client(
    tenant_id: str, agent_id: str, base_url: Optional[str] = None, **kwargs
) -> MemoryServiceClient:
    """
    创建记忆服务客户端

    Args:
        tenant_id: 租户ID
        agent_id: 智能体ID
        base_url: 服务URL
        **kwargs: 其他参数

    Returns:
        记忆服务客户端
    """
    base_url = base_url or os.getenv("MEMORY_SERVICE_URL", "http://localhost:8001")
    return MemoryServiceClient(base_url=base_url, tenant_id=tenant_id, agent_id=agent_id, **kwargs)


async def create_isolated_memory_chest(
    tenant_id: str,
    agent_id: str,
    platform: Optional[str] = None,
    scope_id: Optional[str] = None,
    base_url: Optional[str] = None,
) -> IsolatedMemoryChest:
    """
    创建隔离记忆库

    Args:
        tenant_id: 租户ID
        agent_id: 智能体ID
        platform: 平台标识
        scope_id: 作用域ID
        base_url: 服务URL

    Returns:
        隔离记忆库
    """
    return IsolatedMemoryChest(
        tenant_id=tenant_id, agent_id=agent_id, platform=platform, scope_id=scope_id, base_url=base_url
    )


# 全局客户端缓存
_global_clients: Dict[str, MemoryServiceClient] = {}
_global_chests: Dict[str, IsolatedMemoryChest] = {}


def get_memory_client(tenant_id: str, agent_id: str, base_url: Optional[str] = None) -> MemoryServiceClient:
    """
    获取全局记忆服务客户端（单例模式）

    Args:
        tenant_id: 租户ID
        agent_id: 智能体ID
        base_url: 服务URL

    Returns:
        记忆服务客户端
    """
    base_url = base_url or os.getenv("MEMORY_SERVICE_URL", "http://localhost:8001")
    cache_key = f"{tenant_id}:{agent_id}:{base_url}"

    if cache_key not in _global_clients:
        _global_clients[cache_key] = MemoryServiceClient(base_url=base_url, tenant_id=tenant_id, agent_id=agent_id)

    return _global_clients[cache_key]


def get_isolated_memory_chest(
    tenant_id: str,
    agent_id: str,
    platform: Optional[str] = None,
    scope_id: Optional[str] = None,
    base_url: Optional[str] = None,
) -> IsolatedMemoryChest:
    """
    获取全局隔离记忆库（单例模式）

    Args:
        tenant_id: 租户ID
        agent_id: 智能体ID
        platform: 平台标识
        scope_id: 作用域ID
        base_url: 服务URL

    Returns:
        隔离记忆库
    """
    base_url = base_url or os.getenv("MEMORY_SERVICE_URL", "http://localhost:8001")
    cache_key = f"{tenant_id}:{agent_id}:{platform}:{scope_id}:{base_url}"

    if cache_key not in _global_chests:
        _global_chests[cache_key] = IsolatedMemoryChest(
            tenant_id=tenant_id, agent_id=agent_id, platform=platform, scope_id=scope_id, base_url=base_url
        )

    return _global_chests[cache_key]


def clear_global_clients():
    """清理全局客户端缓存"""
    _global_clients.clear()
    _global_chests.clear()


# 向后兼容的便捷函数
async def process_memory(
    title: str,
    content: str,
    tenant_id: str,
    agent_id: str,
    level: str = "chat",
    platform: Optional[str] = None,
    scope_id: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    处理记忆（便捷函数）

    Args:
        title: 记忆标题
        content: 记忆内容
        tenant_id: 租户ID
        agent_id: 智能体ID
        level: 记忆级别
        platform: 平台标识
        scope_id: 作用域ID
        **kwargs: 其他参数

    Returns:
        处理结果
    """
    client = await create_memory_client(tenant_id, agent_id)
    memory = await client.add_memory(
        title=title, content=content, level=level, platform=platform, scope_id=scope_id, **kwargs
    )
    return memory.dict()


async def search_memory(
    query: str,
    tenant_id: str,
    agent_id: str,
    level: Optional[str] = None,
    platform: Optional[str] = None,
    scope_id: Optional[str] = None,
    limit: int = 10,
    **kwargs,
) -> List[Dict[str, Any]]:
    """
    搜索记忆（便捷函数）

    Args:
        query: 搜索查询
        tenant_id: 租户ID
        agent_id: 智能体ID
        level: 记忆级别
        platform: 平台标识
        scope_id: 作用域ID
        limit: 返回数量限制
        **kwargs: 其他参数

    Returns:
        搜索结果
    """
    client = await create_memory_client(tenant_id, agent_id)
    search_result = await client.search_memories(
        query=query, level=level, platform=platform, scope_id=scope_id, limit=limit, **kwargs
    )
    return [memory.dict() for memory in search_result.items]
