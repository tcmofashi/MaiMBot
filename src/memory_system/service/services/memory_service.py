"""
记忆服务的业务逻辑层

提供记忆的CRUD操作、搜索、聚合和统计功能。
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from uuid import UUID

from ..database.connection import get_session
from ..database.models import Memory, Conflict, OperationLog
from ..cache.cache_manager import memory_cache, stats_cache
from ..utils.embeddings import encode_text

logger = logging.getLogger(__name__)


class MemoryService:
    """记忆服务类"""

    def __init__(self):
        self.cache = memory_cache
        self.stats_cache = stats_cache

    async def create_memory(
        self,
        title: str,
        content: str,
        level: str,
        tenant_id: str,
        agent_id: str,
        platform: Optional[str] = None,
        scope_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        expires_at: Optional[datetime] = None,
    ) -> Memory:
        """
        创建新记忆

        Args:
            title: 记忆标题
            content: 记忆内容
            level: 记忆级别 (agent/platform/chat)
            tenant_id: 租户ID
            agent_id: 智能体ID
            platform: 平台标识
            scope_id: 作用域ID
            tags: 标签列表
            metadata: 元数据
            expires_at: 过期时间

        Returns:
            创建的记忆对象
        """
        try:
            async for session in get_session():
                # 生成嵌入向量
                embedding = None
                if content:
                    embedding = await encode_text(content)

                # 创建记忆对象
                memory = Memory(
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    platform=platform,
                    scope_id=scope_id,
                    level=level,
                    title=title,
                    content=content,
                    embedding=embedding,
                    tags=tags or [],
                    metadata=metadata or {},
                    expires_at=expires_at,
                    status="active",
                )

                session.add(memory)
                await session.commit()
                await session.refresh(memory)

                # 清理相关缓存
                await self._invalidate_memory_caches(tenant_id, agent_id)

                # 记录操作日志
                await self._log_operation(
                    session=session,
                    operation_type="create",
                    resource_type="memory",
                    resource_id=memory.id,
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    platform=platform,
                    scope_id=scope_id,
                    new_values=memory.to_dict(),
                )

                logger.info(f"创建记忆成功: {memory.id}, 租户: {tenant_id}, 智能体: {agent_id}")
                return memory

        except Exception as e:
            logger.error(f"创建记忆失败: {e}")
            raise

    async def get_memory(self, memory_id: UUID) -> Optional[Memory]:
        """
        获取记忆

        Args:
            memory_id: 记忆ID

        Returns:
            记忆对象或None
        """
        try:
            # 先检查缓存
            cached_memory = await self.cache.get_memory(str(memory_id))
            if cached_memory:
                return Memory(**cached_memory)

            async for session in get_session():
                result = await session.get(Memory, memory_id)
                if result:
                    # 缓存结果
                    await self.cache.set_memory(str(memory_id), result.to_dict())
                return result

        except Exception as e:
            logger.error(f"获取记忆失败 {memory_id}: {e}")
            return None

    async def update_memory(
        self,
        memory_id: UUID,
        title: Optional[str] = None,
        content: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        expires_at: Optional[datetime] = None,
        status: Optional[str] = None,
    ) -> Memory:
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
            更新后的记忆对象
        """
        try:
            async for session in get_session():
                # 获取现有记忆
                memory = await session.get(Memory, memory_id)
                if not memory:
                    raise ValueError(f"记忆不存在: {memory_id}")

                # 保存旧值
                old_values = memory.to_dict()

                # 更新字段
                if title is not None:
                    memory.title = title
                if content is not None:
                    memory.content = content
                    # 重新生成嵌入向量
                    memory.embedding = await encode_text(content)
                if tags is not None:
                    memory.tags = tags
                if metadata is not None:
                    memory.metadata = metadata
                if expires_at is not None:
                    memory.expires_at = expires_at
                if status is not None:
                    memory.status = status

                memory.updated_at = datetime.utcnow()

                await session.commit()
                await session.refresh(memory)

                # 清理缓存
                await self.cache.invalidate_memory(str(memory_id))
                await self._invalidate_memory_caches(memory.tenant_id, memory.agent_id)

                # 记录操作日志
                await self._log_operation(
                    session=session,
                    operation_type="update",
                    resource_type="memory",
                    resource_id=memory.id,
                    tenant_id=memory.tenant_id,
                    agent_id=memory.agent_id,
                    platform=memory.platform,
                    scope_id=memory.scope_id,
                    old_values=old_values,
                    new_values=memory.to_dict(),
                )

                logger.info(f"更新记忆成功: {memory_id}")
                return memory

        except Exception as e:
            logger.error(f"更新记忆失败 {memory_id}: {e}")
            raise

    async def delete_memory(self, memory_id: UUID) -> bool:
        """
        删除记忆

        Args:
            memory_id: 记忆ID

        Returns:
            是否成功删除
        """
        try:
            async for session in get_session():
                memory = await session.get(Memory, memory_id)
                if not memory:
                    return False

                # 记录信息用于日志
                tenant_id = memory.tenant_id
                agent_id = memory.agent_id
                platform = memory.platform
                scope_id = memory.scope_id
                old_values = memory.to_dict()

                # 删除记忆
                await session.delete(memory)
                await session.commit()

                # 清理缓存
                await self.cache.invalidate_memory(str(memory_id))
                await self._invalidate_memory_caches(tenant_id, agent_id)

                # 记录操作日志
                await self._log_operation(
                    session=session,
                    operation_type="delete",
                    resource_type="memory",
                    resource_id=memory_id,
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    platform=platform,
                    scope_id=scope_id,
                    old_values=old_values,
                )

                logger.info(f"删除记忆成功: {memory_id}")
                return True

        except Exception as e:
            logger.error(f"删除记忆失败 {memory_id}: {e}")
            return False

    async def query_memories(
        self,
        filters: Dict[str, Any],
        sort_by: str = "created_at",
        sort_order: str = "desc",
        limit: int = 10,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        查询记忆列表

        Args:
            filters: 查询过滤器
            sort_by: 排序字段
            sort_order: 排序顺序
            limit: 限制数量
            offset: 偏移量

        Returns:
            查询结果
        """
        try:
            # 检查缓存
            cache_key = self._make_query_cache_key(filters, sort_by, sort_order, limit, offset)
            cached_result = await self.cache.get(cache_key)
            if cached_result:
                return cached_result

            async for session in get_session():
                # 构建查询
                query = session.query(Memory)

                # 应用过滤器
                for field, value in filters.items():
                    if hasattr(Memory, field) and value is not None:
                        if isinstance(value, list):
                            query = query.filter(getattr(Memory, field).in_(value))
                        else:
                            query = query.filter(getattr(Memory, field) == value)

                # 应用排序
                if hasattr(Memory, sort_by):
                    sort_column = getattr(Memory, sort_by)
                    if sort_order.lower() == "desc":
                        query = query.order_by(sort_column.desc())
                    else:
                        query = query.order_by(sort_column.asc())

                # 获取总数
                total = await query.count()

                # 应用分页
                memories = await query.offset(offset).limit(limit).all()

                # 转换结果
                memory_list = [memory.to_dict() for memory in memories]

                result = {
                    "memories": memory_list,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "has_more": offset + limit < total,
                }

                # 缓存结果
                await self.cache.set(cache_key, result, ttl=300)  # 5分钟缓存

                return result

        except Exception as e:
            logger.error(f"查询记忆失败: {e}")
            raise

    async def batch_create_memories(
        self,
        memories: List[Dict[str, Any]],
        tenant_id: str,
        agent_id: str,
        default_platform: Optional[str] = None,
        default_scope_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        批量创建记忆

        Args:
            memories: 记忆数据列表
            tenant_id: 租户ID
            agent_id: 智能体ID
            default_platform: 默认平台
            default_scope_id: 默认作用域ID

        Returns:
            批量操作结果
        """
        successful = 0
        failed = 0
        errors = []
        created_memories = []

        try:
            async for session in get_session():
                for i, memory_data in enumerate(memories):
                    try:
                        # 批量编码内容以提高性能
                        if memory_data.get("content"):
                            embedding = await encode_text(memory_data["content"])
                        else:
                            embedding = None

                        memory = Memory(
                            tenant_id=tenant_id,
                            agent_id=agent_id,
                            platform=memory_data.get("platform") or default_platform,
                            scope_id=memory_data.get("scope_id") or default_scope_id,
                            level=memory_data["level"],
                            title=memory_data["title"],
                            content=memory_data["content"],
                            embedding=embedding,
                            tags=memory_data.get("tags", []),
                            metadata=memory_data.get("metadata", {}),
                            expires_at=memory_data.get("expires_at"),
                            status="active",
                        )

                        session.add(memory)
                        created_memories.append(memory)
                        successful += 1

                    except Exception as e:
                        failed += 1
                        errors.append({"index": i, "error": str(e), "data": memory_data})

                # 提交所有成功的创建
                await session.commit()

                # 清理缓存
                await self._invalidate_memory_caches(tenant_id, agent_id)

                logger.info(f"批量创建记忆完成: 成功={successful}, 失败={failed}")

                return {
                    "successful": successful,
                    "failed": failed,
                    "errors": errors,
                    "created_memories": [m.to_dict() for m in created_memories],
                }

        except Exception as e:
            logger.error(f"批量创建记忆失败: {e}")
            raise

    async def batch_delete_memories(self, memory_ids: List[UUID], tenant_id: str, agent_id: str) -> Dict[str, Any]:
        """
        批量删除记忆

        Args:
            memory_ids: 记忆ID列表
            tenant_id: 租户ID
            agent_id: 智能体ID

        Returns:
            批量操作结果
        """
        successful = 0
        failed = 0
        errors = []

        try:
            async for session in get_session():
                for memory_id in memory_ids:
                    try:
                        memory = await session.get(Memory, memory_id)
                        if memory and memory.tenant_id == tenant_id and memory.agent_id == agent_id:
                            await session.delete(memory)
                            # 清理单个缓存
                            await self.cache.invalidate_memory(str(memory_id))
                            successful += 1
                        else:
                            failed += 1
                            errors.append({"memory_id": str(memory_id), "error": "记忆不存在或权限不足"})

                    except Exception as e:
                        failed += 1
                        errors.append({"memory_id": str(memory_id), "error": str(e)})

                await session.commit()

                # 清理相关缓存
                await self._invalidate_memory_caches(tenant_id, agent_id)

                logger.info(f"批量删除记忆完成: 成功={successful}, 失败={failed}")

                return {"successful": successful, "failed": failed, "errors": errors}

        except Exception as e:
            logger.error(f"批量删除记忆失败: {e}")
            raise

    async def aggregate_memories(
        self,
        source_scopes: List[str],
        target_level: str,
        tenant_id: str,
        agent_id: str,
        target_platform: Optional[str] = None,
        target_scope_id: Optional[str] = None,
        merge_strategy: str = "append",
    ) -> Dict[str, Any]:
        """
        聚合记忆到目标级别

        Args:
            source_scopes: 源作用域列表
            target_level: 目标级别
            tenant_id: 租户ID
            agent_id: 智能体ID
            target_platform: 目标平台
            target_scope_id: 目标作用域ID
            merge_strategy: 合并策略

        Returns:
            聚合结果
        """
        try:
            async for session in get_session():
                # 查询源记忆
                source_memories = (
                    await session.query(Memory)
                    .filter(
                        Memory.tenant_id == tenant_id, Memory.agent_id == agent_id, Memory.scope_id.in_(source_scopes)
                    )
                    .all()
                )

                if not source_memories:
                    return {
                        "aggregated_count": 0,
                        "target_level": target_level,
                        "source_scopes": source_scopes,
                        "message": "没有找到源记忆",
                    }

                # 根据合并策略处理记忆
                aggregated_memories = []
                for memory in source_memories:
                    if merge_strategy == "append":
                        # 追加策略：创建新的聚合记忆
                        aggregate_memory = Memory(
                            tenant_id=tenant_id,
                            agent_id=agent_id,
                            platform=target_platform,
                            scope_id=target_scope_id,
                            level=target_level,
                            title=f"[聚合] {memory.title}",
                            content=memory.content,
                            embedding=memory.embedding,
                            tags=memory.tags + ["aggregated"],
                            metadata={
                                **memory.metadata,
                                "source_memory_id": str(memory.id),
                                "source_scope_id": memory.scope_id,
                                "aggregated_at": datetime.utcnow().isoformat(),
                            },
                            status="active",
                        )
                        aggregated_memories.append(aggregate_memory)

                    elif merge_strategy == "merge":
                        # 合并策略：合并内容
                        # 这里可以实现更复杂的合并逻辑
                        pass

                # 保存聚合记忆
                for memory in aggregated_memories:
                    session.add(memory)

                await session.commit()

                # 清理缓存
                await self._invalidate_memory_caches(tenant_id, agent_id)

                logger.info(f"记忆聚合完成: 源={len(source_memories)}, 聚合={len(aggregated_memories)}")

                return {
                    "aggregated_count": len(aggregated_memories),
                    "source_count": len(source_memories),
                    "target_level": target_level,
                    "source_scopes": source_scopes,
                    "merge_strategy": merge_strategy,
                }

        except Exception as e:
            logger.error(f"聚合记忆失败: {e}")
            raise

    async def increment_access_count(self, memory_id: UUID) -> bool:
        """
        增加记忆访问次数

        Args:
            memory_id: 记忆ID

        Returns:
            是否成功
        """
        try:
            async for session in get_session():
                memory = await session.get(Memory, memory_id)
                if memory:
                    memory.access_count += 1
                    memory.last_accessed = datetime.utcnow()
                    await session.commit()
                    return True
                return False

        except Exception as e:
            logger.error(f"增加访问次数失败 {memory_id}: {e}")
            return False

    async def regenerate_embedding(self, memory_id: UUID) -> bool:
        """
        重新生成记忆的嵌入向量

        Args:
            memory_id: 记忆ID

        Returns:
            是否成功
        """
        try:
            async for session in get_session():
                memory = await session.get(Memory, memory_id)
                if memory and memory.content:
                    # 重新生成嵌入
                    new_embedding = await encode_text(memory.content)
                    if new_embedding:
                        memory.embedding = new_embedding
                        memory.updated_at = datetime.utcnow()
                        await session.commit()

                        # 清理缓存
                        await self.cache.invalidate_memory(str(memory_id))

                        logger.info(f"重新生成嵌入成功: {memory_id}")
                        return True
                return False

        except Exception as e:
            logger.error(f"重新生成嵌入失败 {memory_id}: {e}")
            return False

    async def get_system_stats(self) -> Dict[str, Any]:
        """
        获取系统统计信息

        Returns:
            统计信息
        """
        try:
            # 检查缓存
            cached_stats = await self.stats_cache.get_system_stats()
            if cached_stats:
                return cached_stats

            async for session in get_session():
                # 总记忆数量
                total_memories = await session.query(Memory).count()

                # 总冲突数量
                total_conflicts = await session.query(Conflict).count()

                # 活跃租户数量
                active_tenants = await session.query(Memory.tenant_id).distinct().count()

                stats = {
                    "total_memories": total_memories,
                    "total_conflicts": total_conflicts,
                    "active_tenants": active_tenants,
                    "timestamp": datetime.utcnow().isoformat(),
                }

                # 缓存结果
                await self.stats_cache.set_system_stats(stats, ttl=300)  # 5分钟

                return stats

        except Exception as e:
            logger.error(f"获取系统统计失败: {e}")
            return {}

    async def get_memory_stats_by_level(self, tenant_id: str, agent_id: str) -> Dict[str, int]:
        """
        按级别获取记忆统计

        Args:
            tenant_id: 租户ID
            agent_id: 智能体ID

        Returns:
            各级别的记忆数量
        """
        try:
            # 检查缓存
            cached_stats = await self.stats_cache.get_memory_stats(tenant_id, agent_id)
            if cached_stats and "by_level" in cached_stats:
                return cached_stats["by_level"]

            async for session in get_session():
                # 按级别统计
                agent_count = (
                    await session.query(Memory)
                    .filter(Memory.tenant_id == tenant_id, Memory.agent_id == agent_id, Memory.level == "agent")
                    .count()
                )

                platform_count = (
                    await session.query(Memory)
                    .filter(Memory.tenant_id == tenant_id, Memory.agent_id == agent_id, Memory.level == "platform")
                    .count()
                )

                chat_count = (
                    await session.query(Memory)
                    .filter(Memory.tenant_id == tenant_id, Memory.agent_id == agent_id, Memory.level == "chat")
                    .count()
                )

                stats = {"agent": agent_count, "platform": platform_count, "chat": chat_count}

                # 缓存结果
                await self.stats_cache.set_memory_stats(tenant_id, {"by_level": stats}, agent_id)

                return stats

        except Exception as e:
            logger.error(f"获取记忆级别统计失败: {e}")
            return {}

    async def get_recent_activity(self, hours: int = 24, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取最近的活动记录

        Args:
            hours: 时间范围（小时）
            tenant_id: 租户ID过滤

        Returns:
            活动记录列表
        """
        try:
            async for session in get_session():
                cutoff_time = datetime.utcnow() - timedelta(hours=hours)

                query = (
                    session.query(OperationLog)
                    .filter(OperationLog.created_at >= cutoff_time)
                    .order_by(OperationLog.created_at.desc())
                    .limit(50)
                )

                if tenant_id:
                    query = query.filter(OperationLog.tenant_id == tenant_id)

                logs = await query.all()

                return [log.to_dict() for log in logs]

        except Exception as e:
            logger.error(f"获取最近活动失败: {e}")
            return []

    async def get_storage_usage(self, tenant_id: str, agent_id: str) -> Dict[str, Any]:
        """
        获取存储使用情况

        Args:
            tenant_id: 租户ID
            agent_id: 智能体ID

        Returns:
            存储使用信息
        """
        try:
            async for session in get_session():
                # 记忆数量和大小估算
                memories = (
                    await session.query(Memory).filter(Memory.tenant_id == tenant_id, Memory.agent_id == agent_id).all()
                )

                total_count = len(memories)
                total_size = 0
                embedding_count = 0

                for memory in memories:
                    # 估算内容大小
                    content_size = len(memory.content.encode("utf-8")) if memory.content else 0
                    title_size = len(memory.title.encode("utf-8")) if memory.title else 0
                    metadata_size = len(str(memory.metadata).encode("utf-8"))

                    # 嵌入向量大小估算（1536维 * 4字节）
                    embedding_size = 1536 * 4 if memory.embedding else 0
                    if embedding_size > 0:
                        embedding_count += 1

                    memory_size = content_size + title_size + metadata_size + embedding_size
                    total_size += memory_size

                return {
                    "memory_count": total_count,
                    "embedding_count": embedding_count,
                    "total_size_bytes": total_size,
                    "total_size_mb": round(total_size / (1024 * 1024), 2),
                    "avg_size_per_memory": round(total_size / total_count, 2) if total_count > 0 else 0,
                }

        except Exception as e:
            logger.error(f"获取存储使用情况失败: {e}")
            return {}

    async def health_check(self) -> Dict[str, Any]:
        """
        健康检查

        Returns:
            健康状态
        """
        try:
            # 检查数据库连接
            async for session in get_session():
                await session.execute("SELECT 1")
                database_status = "healthy"
                break
        except Exception as e:
            database_status = f"unhealthy: {str(e)}"

        return {
            "status": "healthy" if database_status == "healthy" else "unhealthy",
            "database": database_status,
            "cache": "healthy",  # 这里可以添加缓存健康检查
            "timestamp": datetime.utcnow().isoformat(),
        }

    # 私有辅助方法
    async def _invalidate_memory_caches(self, tenant_id: str, agent_id: str):
        """清理记忆相关缓存"""
        try:
            # 清理记忆列表缓存
            await self.cache.invalidate_tenant_memories(tenant_id, agent_id)

            # 清理统计缓存
            await self.stats_cache.get_memory_stats(tenant_id, agent_id)  # 这会触发缓存清理

        except Exception as e:
            logger.error(f"清理记忆缓存失败: {e}")

    async def _log_operation(
        self,
        session,
        operation_type: str,
        resource_type: str,
        resource_id: UUID,
        tenant_id: str,
        agent_id: str,
        platform: Optional[str] = None,
        scope_id: Optional[str] = None,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
    ):
        """记录操作日志"""
        try:
            log = OperationLog(
                operation_type=operation_type,
                resource_type=resource_type,
                resource_id=resource_id,
                tenant_id=tenant_id,
                agent_id=agent_id,
                platform=platform,
                scope_id=scope_id,
                old_values=old_values,
                new_values=new_values,
                success=True,
            )
            session.add(log)

        except Exception as e:
            logger.error(f"记录操作日志失败: {e}")

    def _make_query_cache_key(
        self, filters: Dict[str, Any], sort_by: str, sort_order: str, limit: int, offset: int
    ) -> str:
        """生成查询缓存键"""
        import hashlib

        # 创建过滤器哈希
        filter_str = str(sorted(filters.items()))
        filter_hash = hashlib.md5(filter_str.encode()).hexdigest()[:16]

        return f"query:{filter_hash}:{sort_by}:{sort_order}:{limit}:{offset}"

    # 冲突跟踪相关方法
    async def create_conflict(
        self,
        title: str,
        context: Optional[str],
        tenant_id: str,
        agent_id: str,
        platform: Optional[str] = None,
        scope_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        start_following: bool = False,
    ) -> Conflict:
        """创建冲突记录"""
        try:
            async for session in get_session():
                conflict = Conflict(
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    platform=platform,
                    scope_id=scope_id,
                    title=title,
                    context=context,
                    chat_id=chat_id,
                    start_following=start_following,
                    resolved=False,
                )

                session.add(conflict)
                await session.commit()
                await session.refresh(conflict)

                logger.info(f"创建冲突记录成功: {conflict.id}")
                return conflict

        except Exception as e:
            logger.error(f"创建冲突记录失败: {e}")
            raise

    async def get_conflict(self, conflict_id: UUID) -> Optional[Conflict]:
        """获取冲突记录"""
        try:
            async for session in get_session():
                return await session.get(Conflict, conflict_id)

        except Exception as e:
            logger.error(f"获取冲突记录失败 {conflict_id}: {e}")
            return None

    async def update_conflict(
        self,
        conflict_id: UUID,
        title: Optional[str] = None,
        context: Optional[str] = None,
        start_following: Optional[bool] = None,
        resolved: Optional[bool] = None,
    ) -> Conflict:
        """更新冲突记录"""
        try:
            async for session in get_session():
                conflict = await session.get(Conflict, conflict_id)
                if not conflict:
                    raise ValueError(f"冲突记录不存在: {conflict_id}")

                if title is not None:
                    conflict.title = title
                if context is not None:
                    conflict.context = context
                if start_following is not None:
                    conflict.start_following = start_following
                if resolved is not None:
                    conflict.resolved = resolved
                    if resolved:
                        conflict.resolved_at = datetime.utcnow()

                conflict.updated_at = datetime.utcnow()
                await session.commit()
                await session.refresh(conflict)

                logger.info(f"更新冲突记录成功: {conflict_id}")
                return conflict

        except Exception as e:
            logger.error(f"更新冲突记录失败 {conflict_id}: {e}")
            raise

    async def delete_conflict(self, conflict_id: UUID) -> bool:
        """删除冲突记录"""
        try:
            async for session in get_session():
                conflict = await session.get(Conflict, conflict_id)
                if not conflict:
                    return False

                await session.delete(conflict)
                await session.commit()

                logger.info(f"删除冲突记录成功: {conflict_id}")
                return True

        except Exception as e:
            logger.error(f"删除冲突记录失败 {conflict_id}: {e}")
            return False

    async def list_conflicts(self, filters: Dict[str, Any], limit: int = 10, offset: int = 0) -> List[Conflict]:
        """列出冲突记录"""
        try:
            async for session in get_session():
                query = session.query(Conflict)

                for field, value in filters.items():
                    if hasattr(Conflict, field) and value is not None:
                        if isinstance(value, bool):
                            query = query.filter(getattr(Conflict, field) == value)
                        elif isinstance(value, list):
                            query = query.filter(getattr(Conflict, field).in_(value))
                        else:
                            query = query.filter(getattr(Conflict, field) == value)

                return await query.offset(offset).limit(limit).all()

        except Exception as e:
            logger.error(f"列出冲突记录失败: {e}")
            return []

    async def resolve_conflict(self, conflict_id: UUID) -> Conflict:
        """解决冲突"""
        return await self.update_conflict(conflict_id, resolved=True)

    async def start_conflict_tracking(self, conflict_id: UUID) -> Conflict:
        """开始跟踪冲突"""
        return await self.update_conflict(conflict_id, start_following=True)

    async def stop_conflict_tracking(self, conflict_id: UUID) -> Conflict:
        """停止跟踪冲突"""
        return await self.update_conflict(conflict_id, start_following=False)

    # 维护任务相关方法
    async def count_expired_memories(self, tenant_id: str, agent_id: str, cutoff_date: datetime) -> int:
        """统计过期记忆数量"""
        try:
            async for session in get_session():
                return (
                    await session.query(Memory)
                    .filter(Memory.tenant_id == tenant_id, Memory.agent_id == agent_id, Memory.expires_at < cutoff_date)
                    .count()
                )

        except Exception as e:
            logger.error(f"统计过期记忆失败: {e}")
            return 0

    async def count_expired_conflicts(self, tenant_id: str, agent_id: str, cutoff_date: datetime) -> int:
        """统计过期冲突数量"""
        try:
            async for session in get_session():
                return (
                    await session.query(Conflict)
                    .filter(
                        Conflict.tenant_id == tenant_id,
                        Conflict.agent_id == agent_id,
                        Conflict.created_at < cutoff_date,
                    )
                    .count()
                )

        except Exception as e:
            logger.error(f"统计过期冲突失败: {e}")
            return 0

    async def delete_expired_memories(self, tenant_id: str, agent_id: str, cutoff_date: datetime) -> int:
        """删除过期记忆"""
        try:
            async for session in get_session():
                query = session.query(Memory).filter(
                    Memory.tenant_id == tenant_id, Memory.agent_id == agent_id, Memory.expires_at < cutoff_date
                )

                memories_to_delete = await query.all()
                count = len(memories_to_delete)

                for memory in memories_to_delete:
                    await session.delete(memory)

                await session.commit()

                # 清理缓存
                await self._invalidate_memory_caches(tenant_id, agent_id)

                logger.info(f"删除过期记忆: {count}条")
                return count

        except Exception as e:
            logger.error(f"删除过期记忆失败: {e}")
            return 0

    async def delete_expired_conflicts(self, tenant_id: str, agent_id: str, cutoff_date: datetime) -> int:
        """删除过期冲突"""
        try:
            async for session in get_session():
                query = session.query(Conflict).filter(
                    Conflict.tenant_id == tenant_id,
                    Conflict.agent_id == agent_id,
                    Conflict.created_at < cutoff_date,
                    Conflict.resolved,  # 只删除已解决的冲突
                )

                conflicts_to_delete = await query.all()
                count = len(conflicts_to_delete)

                for conflict in conflicts_to_delete:
                    await session.delete(conflict)

                await session.commit()

                logger.info(f"删除过期冲突: {count}条")
                return count

        except Exception as e:
            logger.error(f"删除过期冲突失败: {e}")
            return 0

    async def backup_data(self, tenant_id: str, agent_id: str, include_embeddings: bool = True) -> Dict[str, Any]:
        """备份数据"""
        try:
            async for session in get_session():
                # 备份记忆
                memories_query = session.query(Memory).filter(
                    Memory.tenant_id == tenant_id, Memory.agent_id == agent_id
                )
                memories = await memories_query.all()

                memory_data = []
                for memory in memories:
                    data = memory.to_dict()
                    if not include_embeddings:
                        data.pop("embedding", None)
                    memory_data.append(data)

                # 备份冲突
                conflicts_query = session.query(Conflict).filter(
                    Conflict.tenant_id == tenant_id, Conflict.agent_id == agent_id
                )
                conflicts = await conflicts_query.all()
                conflict_data = [conflict.to_dict() for conflict in conflicts]

                backup_result = {
                    "tenant_id": tenant_id,
                    "agent_id": agent_id,
                    "backup_time": datetime.utcnow().isoformat(),
                    "include_embeddings": include_embeddings,
                    "memory_count": len(memory_data),
                    "conflict_count": len(conflict_data),
                    "memories": memory_data,
                    "conflicts": conflict_data,
                }

                logger.info(f"数据备份完成: 记忆{len(memory_data)}条, 冲突{len(conflict_data)}条")
                return backup_result

        except Exception as e:
            logger.error(f"数据备份失败: {e}")
            raise

    async def optimize_database(self, analyze_only: bool = False) -> Dict[str, Any]:
        """优化数据库"""
        try:
            async for session in get_session():
                if analyze_only:
                    # 分析表统计信息
                    await session.execute("ANALYZE memories")
                    await session.execute("ANALYZE conflicts")
                    await session.execute("ANALYZE operation_logs")

                    return {
                        "operation": "analyze_only",
                        "message": "数据库分析完成",
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                else:
                    # 执行优化
                    await session.execute("VACUUM ANALYZE memories")
                    await session.execute("VACUUM ANALYZE conflicts")
                    await session.execute("VACUUM ANALYZE operation_logs")

                    return {
                        "operation": "optimize",
                        "message": "数据库优化完成",
                        "timestamp": datetime.utcnow().isoformat(),
                    }

        except Exception as e:
            logger.error(f"数据库优化失败: {e}")
            raise

    async def get_conflict_related_memories(self, conflict_id: UUID) -> List[Dict[str, Any]]:
        """获取冲突相关记忆"""
        try:
            async for session in get_session():
                conflict = await session.get(Conflict, conflict_id)
                if not conflict:
                    return []

                # 根据冲突的上下文信息搜索相关记忆
                memories_query = session.query(Memory).filter(
                    Memory.tenant_id == conflict.tenant_id, Memory.agent_id == conflict.agent_id
                )

                # 如果有聊天ID，优先按聊天ID搜索
                if conflict.chat_id:
                    memories_query = memories_query.filter(Memory.scope_id == conflict.chat_id)
                # 否则按平台和作用域搜索
                elif conflict.platform and conflict.scope_id:
                    memories_query = memories_query.filter(
                        Memory.platform == conflict.platform, Memory.scope_id == conflict.scope_id
                    )

                memories = await memories_query.limit(20).all()
                return [memory.to_dict() for memory in memories]

        except Exception as e:
            logger.error(f"获取冲突相关记忆失败: {e}")
            return []

    async def update_memory_stats(self, tenant_id: str, agent_id: str):
        """更新记忆统计信息"""
        try:
            # 这里可以更新 MemoryStats 表
            # 暂时通过清理缓存来触发重新计算
            await self.stats_cache.get_memory_stats(tenant_id, agent_id)
            logger.info(f"更新记忆统计: {tenant_id}:{agent_id}")

        except Exception as e:
            logger.error(f"更新记忆统计失败: {e}")

    async def cleanup_conflict_resources(self, conflict_id: UUID):
        """清理冲突相关资源"""
        try:
            # 清理冲突跟踪相关的资源
            # 这里可以添加具体的清理逻辑
            logger.info(f"清理冲突资源: {conflict_id}")

        except Exception as e:
            logger.error(f"清理冲突资源失败: {e}")

    async def setup_conflict_monitoring(self, conflict_id: UUID):
        """设置冲突监控"""
        try:
            # 设置冲突监控逻辑
            # 这里可以添加具体的监控设置
            logger.info(f"设置冲突监控: {conflict_id}")

        except Exception as e:
            logger.error(f"设置冲突监控失败: {e}")

    async def cleanup_conflict_monitoring(self, conflict_id: UUID):
        """清理冲突监控"""
        try:
            # 清理冲突监控
            # 这里可以添加具体的清理逻辑
            logger.info(f"清理冲突监控: {conflict_id}")

        except Exception as e:
            logger.error(f"清理冲突监控失败: {e}")
