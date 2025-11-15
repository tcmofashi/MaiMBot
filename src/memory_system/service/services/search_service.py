"""
记忆服务的搜索服务

提供记忆的向量相似度搜索和文本搜索功能。
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from ..database.connection import get_session
from ..database.models import Memory
from ..cache.cache_manager import search_cache
from ..utils.embeddings import encode_text, find_similar_embeddings, text_similarity

logger = logging.getLogger(__name__)


class SearchService:
    """搜索服务类"""

    def __init__(self):
        self.cache = search_cache

    async def search_memories(
        self,
        query: str,
        tenant_id: str,
        agent_id: str,
        level: Optional[str] = None,
        platform: Optional[str] = None,
        scope_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 10,
        offset: int = 0,
        similarity_threshold: float = 0.7,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        基于查询文本搜索记忆（支持向量相似度搜索）

        Args:
            query: 搜索查询
            tenant_id: 租户ID
            agent_id: 智能体ID
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
        try:
            # 检查缓存
            self._make_search_cache_key(
                query,
                tenant_id,
                agent_id,
                level,
                platform,
                scope_id,
                tags,
                limit,
                offset,
                similarity_threshold,
                date_from,
                date_to,
            )
            cached_result = await self.cache.get_search_results(
                tenant_id,
                agent_id,
                query,
                {
                    "level": level,
                    "platform": platform,
                    "scope_id": scope_id,
                    "tags": tags,
                    "limit": limit,
                    "offset": offset,
                    "similarity_threshold": similarity_threshold,
                    "date_from": date_from,
                    "date_to": date_to,
                },
                limit,
                offset,
            )
            if cached_result:
                return cached_result

            # 编码查询文本
            query_embedding = await encode_text(query)
            if not query_embedding:
                # 如果无法编码查询文本，使用文本匹配搜索
                return await self._text_search(
                    query, tenant_id, agent_id, level, platform, scope_id, tags, limit, offset, date_from, date_to
                )

            # 搜索相似记忆
            search_results = await self._vector_search(
                query_embedding,
                tenant_id,
                agent_id,
                level,
                platform,
                scope_id,
                tags,
                limit,
                offset,
                similarity_threshold,
                date_from,
                date_to,
            )

            # 缓存结果
            await self.cache.set_search_results(
                tenant_id,
                agent_id,
                query,
                {
                    "level": level,
                    "platform": platform,
                    "scope_id": scope_id,
                    "tags": tags,
                    "limit": limit,
                    "offset": offset,
                    "similarity_threshold": similarity_threshold,
                    "date_from": date_from,
                    "date_to": date_to,
                },
                search_results,
                limit,
                offset,
            )

            return search_results

        except Exception as e:
            logger.error(f"搜索记忆失败: {e}")
            raise

    async def _vector_search(
        self,
        query_embedding: List[float],
        tenant_id: str,
        agent_id: str,
        level: Optional[str],
        platform: Optional[str],
        scope_id: Optional[str],
        tags: Optional[List[str]],
        limit: int,
        offset: int,
        similarity_threshold: float,
        date_from: Optional[datetime],
        date_to: Optional[datetime],
    ) -> Dict[str, Any]:
        """执行向量相似度搜索"""
        try:
            async for session in get_session():
                # 构建基础查询
                query = session.query(Memory).filter(
                    Memory.tenant_id == tenant_id,
                    Memory.agent_id == agent_id,
                    Memory.status == "active",
                    Memory.embedding.isnot(None),  # 必须有嵌入向量
                )

                # 应用过滤器
                if level:
                    query = query.filter(Memory.level == level)
                if platform:
                    query = query.filter(Memory.platform == platform)
                if scope_id:
                    query = query.filter(Memory.scope_id == scope_id)
                if tags:
                    for tag in tags:
                        query = query.filter(Memory.tags.contains([tag]))
                if date_from:
                    query = query.filter(Memory.created_at >= date_from)
                if date_to:
                    query = query.filter(Memory.created_at <= date_to)

                # 获取候选记忆（获取更多候选以便计算相似度）
                candidates = await query.limit(limit * 3).all()
                if not candidates:
                    return {
                        "memories": [],
                        "total": 0,
                        "limit": limit,
                        "offset": offset,
                        "has_more": False,
                        "search_type": "vector",
                    }

                # 计算相似度
                candidate_embeddings = [memory.embedding for memory in candidates if memory.embedding]

                # 使用嵌入工具计算相似度
                similarity_results = await find_similar_embeddings(
                    query_embedding,
                    candidate_embeddings,
                    top_k=len(candidates),
                    similarity_threshold=similarity_threshold,
                    distance_metric="cosine",
                )

                # 根据相似度结果筛选记忆
                scored_memories = []
                for result in similarity_results:
                    index = result["index"]
                    similarity = result["similarity"]
                    if similarity >= similarity_threshold:
                        memory = candidates[index]
                        memory_dict = memory.to_dict()
                        memory_dict["similarity_score"] = similarity
                        scored_memories.append((memory_dict, similarity))

                # 按相似度排序
                scored_memories.sort(key=lambda x: x[1], reverse=True)

                # 应用分页
                total = len(scored_memories)
                memories = [item[0] for item in scored_memories[offset : offset + limit]]

                return {
                    "memories": memories,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "has_more": offset + limit < total,
                    "search_type": "vector",
                    "candidates_count": len(candidates),
                }

        except Exception as e:
            logger.error(f"向量搜索失败: {e}")
            raise

    async def _text_search(
        self,
        query: str,
        tenant_id: str,
        agent_id: str,
        level: Optional[str],
        platform: Optional[str],
        scope_id: Optional[str],
        tags: Optional[List[str]],
        limit: int,
        offset: int,
        date_from: Optional[datetime],
        date_to: Optional[datetime],
    ) -> Dict[str, Any]:
        """执行文本匹配搜索"""
        try:
            async for session in get_session():
                # 构建基础查询
                query_builder = session.query(Memory).filter(
                    Memory.tenant_id == tenant_id, Memory.agent_id == agent_id, Memory.status == "active"
                )

                # 应用过滤器
                if level:
                    query_builder = query_builder.filter(Memory.level == level)
                if platform:
                    query_builder = query_builder.filter(Memory.platform == platform)
                if scope_id:
                    query_builder = query_builder.filter(Memory.scope_id == scope_id)
                if tags:
                    for tag in tags:
                        query_builder = query_builder.filter(Memory.tags.contains([tag]))
                if date_from:
                    query_builder = query_builder.filter(Memory.created_at >= date_from)
                if date_to:
                    query_builder = query_builder.filter(Memory.created_at <= date_to)

                # 文本搜索（使用PostgreSQL的全文搜索或简单的LIKE匹配）
                if query:
                    # 简单的文本匹配
                    query_builder = query_builder.filter(
                        (Memory.title.ilike(f"%{query}%")) | (Memory.content.ilike(f"%{query}%"))
                    )

                # 获取总数
                total = await query_builder.count()

                # 应用分页和排序
                memories = await query_builder.order_by(Memory.created_at.desc()).offset(offset).limit(limit).all()

                # 计算文本相似度分数
                memory_dicts = []
                for memory in memories:
                    memory_dict = memory.to_dict()
                    # 计算文本相似度
                    title_similarity = await text_similarity(query, memory.title or "")
                    content_similarity = await text_similarity(query, memory.content or "")
                    max_similarity = max(title_similarity or 0.0, content_similarity or 0.0)
                    memory_dict["similarity_score"] = max_similarity
                    memory_dicts.append(memory_dict)

                return {
                    "memories": memory_dicts,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "has_more": offset + limit < total,
                    "search_type": "text",
                }

        except Exception as e:
            logger.error(f"文本搜索失败: {e}")
            raise

    async def find_similar_memories(
        self,
        memory_id: str,
        tenant_id: str,
        agent_id: str,
        limit: int = 10,
        similarity_threshold: float = 0.7,
        exclude_self: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        找到与指定记忆相似的其他记忆

        Args:
            memory_id: 参考记忆ID
            tenant_id: 租户ID
            agent_id: 智能体ID
            limit: 返回数量限制
            similarity_threshold: 相似度阈值
            exclude_self: 是否排除自身

        Returns:
            相似记忆列表
        """
        try:
            async for session in get_session():
                # 获取参考记忆
                reference_memory = await session.get(Memory, memory_id)
                if not reference_memory or not reference_memory.embedding:
                    return []

                # 查询同租户同智能体的其他记忆
                query = session.query(Memory).filter(
                    Memory.tenant_id == tenant_id,
                    Memory.agent_id == agent_id,
                    Memory.status == "active",
                    Memory.embedding.isnot(None),
                )

                if exclude_self:
                    query = query.filter(Memory.id != memory_id)

                candidates = await query.limit(limit * 2).all()
                if not candidates:
                    return []

                # 计算相似度
                candidate_embeddings = [memory.embedding for memory in candidates if memory.embedding]

                similarity_results = await find_similar_embeddings(
                    reference_memory.embedding,
                    candidate_embeddings,
                    top_k=limit,
                    similarity_threshold=similarity_threshold,
                )

                # 构建结果
                similar_memories = []
                for result in similarity_results:
                    index = result["index"]
                    similarity = result["similarity"]
                    memory = candidates[index]
                    memory_dict = memory.to_dict()
                    memory_dict["similarity_score"] = similarity
                    similar_memories.append(memory_dict)

                return similar_memories

        except Exception as e:
            logger.error(f"查找相似记忆失败: {e}")
            return []

    async def search_by_tags(
        self,
        tenant_id: str,
        agent_id: str,
        tags: List[str],
        level: Optional[str] = None,
        platform: Optional[str] = None,
        scope_id: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
        match_all: bool = True,  # 是否需要匹配所有标签
    ) -> Dict[str, Any]:
        """
        基于标签搜索记忆

        Args:
            tenant_id: 租户ID
            agent_id: 智能体ID
            tags: 标签列表
            level: 记忆级别过滤
            platform: 平台过滤
            scope_id: 作用域过滤
            limit: 返回数量限制
            offset: 偏移量
            match_all: 是否需要匹配所有标签

        Returns:
            搜索结果
        """
        try:
            async for session in get_session():
                # 构建基础查询
                query = session.query(Memory).filter(
                    Memory.tenant_id == tenant_id, Memory.agent_id == agent_id, Memory.status == "active"
                )

                # 应用过滤器
                if level:
                    query = query.filter(Memory.level == level)
                if platform:
                    query = query.filter(Memory.platform == platform)
                if scope_id:
                    query = query.filter(Memory.scope_id == scope_id)

                # 应用标签过滤
                if match_all:
                    # 需要包含所有标签
                    for tag in tags:
                        query = query.filter(Memory.tags.contains([tag]))
                else:
                    # 只需要包含任一标签
                    tag_conditions = []
                    for tag in tags:
                        tag_conditions.append(Memory.tags.contains([tag]))
                    from sqlalchemy import or_

                    query = query.filter(or_(*tag_conditions))

                # 获取总数
                total = await query.count()

                # 应用分页和排序
                memories = await query.order_by(Memory.created_at.desc()).offset(offset).limit(limit).all()

                memory_dicts = [memory.to_dict() for memory in memories]

                return {
                    "memories": memory_dicts,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "has_more": offset + limit < total,
                    "search_type": "tags",
                    "tags": tags,
                    "match_all": match_all,
                }

        except Exception as e:
            logger.error(f"标签搜索失败: {e}")
            raise

    async def advanced_search(self, tenant_id: str, agent_id: str, search_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        高级搜索功能

        Args:
            tenant_id: 租户ID
            agent_id: 智能体ID
            search_params: 搜索参数字典

        Returns:
            搜索结果
        """
        try:
            # 提取搜索参数
            query = search_params.get("query", "")
            tags = search_params.get("tags", [])
            level = search_params.get("level")
            platform = search_params.get("platform")
            scope_id = search_params.get("scope_id")
            limit = search_params.get("limit", 10)
            offset = search_params.get("offset", 0)
            similarity_threshold = search_params.get("similarity_threshold", 0.7)
            date_from = search_params.get("date_from")
            date_to = search_params.get("date_to")
            sort_by = search_params.get("sort_by", "created_at")
            sort_order = search_params.get("sort_order", "desc")

            # 根据是否有查询文本选择搜索方法
            if query:
                return await self.search_memories(
                    query,
                    tenant_id,
                    agent_id,
                    level,
                    platform,
                    scope_id,
                    tags,
                    limit,
                    offset,
                    similarity_threshold,
                    date_from,
                    date_to,
                )
            elif tags:
                return await self.search_by_tags(
                    tenant_id,
                    agent_id,
                    tags,
                    level,
                    platform,
                    scope_id,
                    limit,
                    offset,
                    match_all=search_params.get("match_all_tags", True),
                )
            else:
                # 仅按条件过滤
                return await self._filter_memories(
                    tenant_id,
                    agent_id,
                    level,
                    platform,
                    scope_id,
                    date_from,
                    date_to,
                    sort_by,
                    sort_order,
                    limit,
                    offset,
                )

        except Exception as e:
            logger.error(f"高级搜索失败: {e}")
            raise

    async def _filter_memories(
        self,
        tenant_id: str,
        agent_id: str,
        level: Optional[str],
        platform: Optional[str],
        scope_id: Optional[str],
        date_from: Optional[datetime],
        date_to: Optional[datetime],
        sort_by: str,
        sort_order: str,
        limit: int,
        offset: int,
    ) -> Dict[str, Any]:
        """仅按条件过滤记忆"""
        try:
            async for session in get_session():
                query = session.query(Memory).filter(
                    Memory.tenant_id == tenant_id, Memory.agent_id == agent_id, Memory.status == "active"
                )

                # 应用过滤器
                if level:
                    query = query.filter(Memory.level == level)
                if platform:
                    query = query.filter(Memory.platform == platform)
                if scope_id:
                    query = query.filter(Memory.scope_id == scope_id)
                if date_from:
                    query = query.filter(Memory.created_at >= date_from)
                if date_to:
                    query = query.filter(Memory.created_at <= date_to)

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
                memory_dicts = [memory.to_dict() for memory in memories]

                return {
                    "memories": memory_dicts,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "has_more": offset + limit < total,
                    "search_type": "filter",
                }

        except Exception as e:
            logger.error(f"过滤记忆失败: {e}")
            raise

    async def get_search_suggestions(
        self, partial_query: str, tenant_id: str, agent_id: str, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        获取搜索建议

        Args:
            partial_query: 部分查询文本
            tenant_id: 租户ID
            agent_id: 智能体ID
            limit: 建议数量限制

        Returns:
            搜索建议列表
        """
        try:
            if not partial_query or len(partial_query) < 2:
                return []

            async for session in get_session():
                # 从记忆标题中提取相似的建议
                query = (
                    session.query(Memory.title)
                    .filter(
                        Memory.tenant_id == tenant_id,
                        Memory.agent_id == agent_id,
                        Memory.status == "active",
                        Memory.title.ilike(f"%{partial_query}%"),
                    )
                    .distinct()
                    .limit(limit * 2)
                )

                titles = await query.all()
                suggestions = []

                for title_tuple in titles:
                    title = title_tuple[0]
                    # 简单的相似度检查
                    if partial_query.lower() in title.lower():
                        suggestions.append(
                            {
                                "text": title,
                                "type": "title",
                                "relevance": self._calculate_relevance(partial_query, title),
                            }
                        )

                # 按相关性排序并限制数量
                suggestions.sort(key=lambda x: x["relevance"], reverse=True)
                return suggestions[:limit]

        except Exception as e:
            logger.error(f"获取搜索建议失败: {e}")
            return []

    def _calculate_relevance(self, query: str, text: str) -> float:
        """计算查询与文本的相关性"""
        query_lower = query.lower()
        text_lower = text.lower()

        # 完全匹配的权重最高
        if query_lower == text_lower:
            return 1.0

        # 开头匹配
        if text_lower.startswith(query_lower):
            return 0.8

        # 包含匹配
        if query_lower in text_lower:
            return 0.6

        # 部分匹配
        for word in query_lower.split():
            if word in text_lower:
                return 0.4

        return 0.0

    def _make_search_cache_key(
        self,
        query: str,
        tenant_id: str,
        agent_id: str,
        level: Optional[str],
        platform: Optional[str],
        scope_id: Optional[str],
        tags: Optional[List[str]],
        limit: int,
        offset: int,
        similarity_threshold: float,
        date_from: Optional[datetime],
        date_to: Optional[datetime],
    ) -> str:
        """生成搜索缓存键"""
        import hashlib

        # 创建参数字符串
        params = {
            "query": query,
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "level": level,
            "platform": platform,
            "scope_id": scope_id,
            "tags": sorted(tags) if tags else None,
            "limit": limit,
            "offset": offset,
            "similarity_threshold": similarity_threshold,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
        }

        param_str = str(sorted(params.items()))
        return f"search:{hashlib.md5(param_str.encode()).hexdigest()}"
