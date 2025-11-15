"""
搜索服务的单元测试

测试搜索服务的核心业务逻辑。
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.memory_system.service.services.search_service import SearchService
from src.memory_system.service.utils.isolation import IsolationContext


@pytest.fixture
async def search_service():
    """创建搜索服务实例"""
    service = SearchService()
    yield service


@pytest.fixture
def sample_isolation_context():
    """创建示例隔离上下文"""
    return IsolationContext(
        tenant_id="test_tenant", agent_id="test_agent", platform="test_platform", scope_id="test_scope"
    )


class TestSearchService:
    """搜索服务测试类"""

    @pytest.mark.asyncio
    async def test_search_memories_with_vector_search(self, search_service):
        """测试向量相似度搜索"""
        query = "测试搜索查询"
        query_embedding = [0.1] * 1536

        with patch.object(search_service, "_make_search_cache_key") as mock_cache_key:
            mock_cache_key.return_value = "test_cache_key"

            with patch.object(search_service.cache, "get_search_results") as mock_cache_get:
                mock_cache_get.return_value = None  # 缓存未命中

                with patch("src.memory_system.service.services.search_service.encode_text") as mock_encode:
                    mock_encode.return_value = query_embedding

                    # 模拟候选记忆
                    candidate_memories = []
                    for i in range(3):
                        memory = MagicMock()
                        memory.id = uuid4()
                        memory.title = f"记忆标题 {i}"
                        memory.content = f"记忆内容 {i}"
                        memory.embedding = [0.1 * (i + 1)] * 1536
                        memory.to_dict.return_value = {
                            "id": str(memory.id),
                            "title": memory.title,
                            "content": memory.content,
                        }
                        candidate_memories.append(memory)

                    with patch.object(search_service, "_vector_search") as mock_vector_search:
                        search_result = {
                            "memories": [memory.to_dict() for memory in candidate_memories[:2]],
                            "total": 2,
                            "limit": 10,
                            "offset": 0,
                            "has_more": False,
                            "search_type": "vector",
                        }
                        mock_vector_search.return_value = search_result

                        with patch.object(search_service.cache, "set_search_results") as mock_cache_set:
                            result = await search_service.search_memories(
                                query=query, tenant_id="test_tenant", agent_id="test_agent", limit=10, offset=0
                            )

                            assert result is not None
                            assert result["search_type"] == "vector"
                            assert len(result["memories"]) == 2
                            assert result["total"] == 2

                            mock_encode.assert_called_once_with(query)
                            mock_cache_key.assert_called_once()
                            mock_cache_get.assert_called_once()
                            mock_vector_search.assert_called_once()
                            mock_cache_set.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_memories_fallback_to_text_search(self, search_service):
        """测试向量搜索失败时回退到文本搜索"""
        query = "测试搜索查询"

        with patch.object(search_service, "_make_search_cache_key") as mock_cache_key:
            mock_cache_key.return_value = "test_cache_key"

            with patch.object(search_service.cache, "get_search_results") as mock_cache_get:
                mock_cache_get.return_value = None  # 缓存未命中

                with patch("src.memory_system.service.services.search_service.encode_text") as mock_encode:
                    mock_encode.return_value = None  # 向量编码失败

                    with patch.object(search_service, "_text_search") as mock_text_search:
                        text_search_result = {
                            "memories": [{"title": "文本搜索结果"}],
                            "total": 1,
                            "limit": 10,
                            "offset": 0,
                            "has_more": False,
                            "search_type": "text",
                        }
                        mock_text_search.return_value = text_search_result

                        with patch.object(search_service.cache, "set_search_results"):
                            result = await search_service.search_memories(
                                query=query, tenant_id="test_tenant", agent_id="test_agent"
                            )

                            assert result is not None
                            assert result["search_type"] == "text"
                            assert len(result["memories"]) == 1

                            mock_encode.assert_called_once_with(query)
                            mock_text_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_vector_search(self, search_service):
        """测试向量搜索实现"""
        query_embedding = [0.1] * 1536

        # 模拟候选记忆
        candidate_memories = []
        for i in range(5):
            memory = MagicMock()
            memory.id = uuid4()
            memory.title = f"候选记忆 {i}"
            memory.content = f"候选内容 {i}"
            memory.embedding = [0.1 * (i + 1)] * 1536
            memory.to_dict.return_value = {"id": str(memory.id), "title": memory.title, "content": memory.content}
            candidate_memories.append(memory)

        with patch("src.memory_system.service.services.search_service.get_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = MagicMock()
            mock_session.return_value.__aexit__.return_value = MagicMock()

            session_instance = mock_session.return_value.__aenter__.return_value
            query_mock = MagicMock()
            session_instance.query = MagicMock(return_value=query_mock)

            # 模拟链式查询调用
            query_mock.filter.return_value = query_mock
            query_mock.limit.return_value = AsyncMock(return_value=candidate_memories)

            with patch(
                "src.memory_system.service.services.search_service.find_similar_embeddings"
            ) as mock_find_similar:
                mock_find_similar.return_value = [
                    {"index": 0, "similarity": 0.9},
                    {"index": 2, "similarity": 0.8},
                    {"index": 1, "similarity": 0.7},
                ]

                result = await search_service._vector_search(
                    query_embedding=query_embedding,
                    tenant_id="test_tenant",
                    agent_id="test_agent",
                    level=None,
                    platform=None,
                    scope_id=None,
                    tags=None,
                    limit=10,
                    offset=0,
                    similarity_threshold=0.7,
                    date_from=None,
                    date_to=None,
                )

                assert result is not None
                assert result["search_type"] == "vector"
                assert len(result["memories"]) == 3  # 相似度 >= 0.7的记忆
                assert result["candidates_count"] == 5

                # 验证相似度分数已添加
                for memory_dict in result["memories"]:
                    assert "similarity_score" in memory_dict

    @pytest.mark.asyncio
    async def test_text_search(self, search_service):
        """测试文本搜索实现"""
        query = "搜索关键词"

        # 模拟搜索结果记忆
        search_memories = []
        for i in range(3):
            memory = MagicMock()
            memory.id = uuid4()
            memory.title = f"包含{query}的记忆{i}"
            memory.content = f"这是包含{query}的内容{i}"
            memory.created_at = datetime.utcnow()
            memory.to_dict.return_value = {"id": str(memory.id), "title": memory.title, "content": memory.content}
            search_memories.append(memory)

        with patch("src.memory_system.service.services.search_service.get_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = MagicMock()
            mock_session.return_value.__aexit__.return_value = MagicMock()

            session_instance = mock_session.return_value.__aenter__.return_value
            query_mock = MagicMock()
            session_instance.query = MagicMock(return_value=query_mock)

            # 模拟链式查询调用
            query_mock.filter.return_value = query_mock
            query_mock.count.return_value = AsyncMock(return_value=3)
            query_mock.order_by.return_value = query_mock
            query_mock.offset.return_value = query_mock
            query_mock.limit.return_value = AsyncMock(return_value=search_memories)

            with patch("src.memory_system.service.services.search_service.text_similarity") as mock_text_similarity:
                # 模拟文本相似度计算
                mock_text_similarity.side_effect = [0.9, 0.8, 0.7]

                result = await search_service._text_search(
                    query=query,
                    tenant_id="test_tenant",
                    agent_id="test_agent",
                    level=None,
                    platform=None,
                    scope_id=None,
                    tags=None,
                    limit=10,
                    offset=0,
                    date_from=None,
                    date_to=None,
                )

                assert result is not None
                assert result["search_type"] == "text"
                assert len(result["memories"]) == 3
                assert result["total"] == 3

                # 验证文本相似度分数已添加
                for i, memory_dict in enumerate(result["memories"]):
                    assert "similarity_score" in memory_dict
                    assert memory_dict["similarity_score"] == [0.9, 0.8, 0.7][i]

    @pytest.mark.asyncio
    async def test_find_similar_memories(self, search_service):
        """测试查找相似记忆"""
        memory_id = str(uuid4())
        reference_embedding = [0.5] * 1536

        # 模拟参考记忆
        reference_memory = MagicMock()
        reference_memory.id = memory_id
        reference_memory.embedding = reference_embedding

        # 模拟候选记忆
        candidate_memories = []
        for i in range(5):
            memory = MagicMock()
            memory.id = str(uuid4())
            memory.title = f"候选记忆 {i}"
            memory.embedding = [0.4 + i * 0.1] * 1536
            memory.to_dict.return_value = {"id": memory.id, "title": memory.title}
            candidate_memories.append(memory)

        with patch("src.memory_system.service.services.search_service.get_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = MagicMock()
            mock_session.return_value.__aexit__.return_value = MagicMock()

            session_instance = mock_session.return_value.__aenter__.return_value
            session_instance.get = AsyncMock(return_value=reference_memory)

            query_mock = MagicMock()
            session_instance.query = MagicMock(return_value=query_mock)
            query_mock.filter.return_value = query_mock
            query_mock.limit.return_value = AsyncMock(return_value=candidate_memories)

            with patch(
                "src.memory_system.service.services.search_service.find_similar_embeddings"
            ) as mock_find_similar:
                mock_find_similar.return_value = [
                    {"index": 0, "similarity": 0.95},
                    {"index": 2, "similarity": 0.85},
                    {"index": 4, "similarity": 0.75},
                ]

                result = await search_service.find_similar_memories(
                    memory_id=memory_id,
                    tenant_id="test_tenant",
                    agent_id="test_agent",
                    limit=3,
                    similarity_threshold=0.7,
                    exclude_self=True,
                )

                assert result is not None
                assert len(result) == 3
                assert all("similarity_score" in memory for memory in result)

                # 验证相似度排序
                similarities = [memory["similarity_score"] for memory in result]
                assert similarities == sorted(similarities, reverse=True)

    @pytest.mark.asyncio
    async def test_search_by_tags(self, search_service):
        """测试基于标签搜索"""
        tags = ["测试", "标签"]

        # 模拟搜索结果记忆
        tagged_memories = []
        for i in range(3):
            memory = MagicMock()
            memory.id = uuid4()
            memory.title = f"标签记忆 {i}"
            memory.content = f"标签内容 {i}"
            memory.tags = tags + [f"额外标签{i}"]
            memory.created_at = datetime.utcnow()
            memory.to_dict.return_value = {
                "id": str(memory.id),
                "title": memory.title,
                "content": memory.content,
                "tags": memory.tags,
            }
            tagged_memories.append(memory)

        with patch("src.memory_system.service.services.search_service.get_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = MagicMock()
            mock_session.return_value.__aexit__.return_value = MagicMock()

            session_instance = mock_session.return_value.__aenter__.return_value
            query_mock = MagicMock()
            session_instance.query = MagicMock(return_value=query_mock)

            # 模拟链式查询调用
            query_mock.filter.return_value = query_mock
            query_mock.count.return_value = AsyncMock(return_value=3)
            query_mock.order_by.return_value = query_mock
            query_mock.offset.return_value = query_mock
            query_mock.limit.return_value = AsyncMock(return_value=tagged_memories)

            result = await search_service.search_by_tags(
                tenant_id="test_tenant", agent_id="test_agent", tags=tags, limit=10, offset=0, match_all=True
            )

            assert result is not None
            assert result["search_type"] == "tags"
            assert len(result["memories"]) == 3
            assert result["total"] == 3
            assert result["tags"] == tags
            assert result["match_all"] is True

            # 验证标签过滤调用次数
            assert query_mock.filter.call_count >= 2  # status + tags

    @pytest.mark.asyncio
    async def test_advanced_search_with_query(self, search_service):
        """测试带查询的高级搜索"""
        search_params = {
            "query": "高级搜索",
            "tags": ["高级"],
            "level": "agent",
            "limit": 5,
            "similarity_threshold": 0.8,
        }

        with patch.object(search_service, "search_memories") as mock_search:
            mock_search.return_value = {
                "memories": [{"title": "高级搜索结果"}],
                "total": 1,
                "limit": 5,
                "offset": 0,
                "has_more": False,
            }

            result = await search_service.advanced_search(
                tenant_id="test_tenant", agent_id="test_agent", search_params=search_params
            )

            assert result is not None
            assert len(result["memories"]) == 1
            mock_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_advanced_search_with_tags_only(self, search_service):
        """测试仅基于标签的高级搜索"""
        search_params = {"tags": ["标签1", "标签2"], "match_all_tags": False, "limit": 10}

        with patch.object(search_service, "search_by_tags") as mock_search_tags:
            mock_search_tags.return_value = {
                "memories": [{"title": "标签搜索结果"}],
                "total": 1,
                "limit": 10,
                "offset": 0,
                "has_more": False,
                "search_type": "tags",
            }

            result = await search_service.advanced_search(
                tenant_id="test_tenant", agent_id="test_agent", search_params=search_params
            )

            assert result is not None
            assert result["search_type"] == "tags"
            mock_search_tags.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_search_suggestions(self, search_service):
        """测试获取搜索建议"""
        partial_query = "测试"

        # 模拟数据库查询结果
        title_suggestions = [("测试记忆1",), ("测试记忆2",), ("单元测试示例",), ("集成测试指南",), ("性能测试报告",)]

        with patch("src.memory_system.service.services.search_service.get_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = MagicMock()
            mock_session.return_value.__aexit__.return_value = MagicMock()

            session_instance = mock_session.return_value.__aenter__.return_value
            query_mock = MagicMock()
            session_instance.query = MagicMock(return_value=query_mock)

            query_mock.filter.return_value = query_mock
            query_mock.distinct.return_value = query_mock
            query_mock.limit.return_value = AsyncMock(return_value=title_suggestions)

            result = await search_service.get_search_suggestions(
                partial_query=partial_query, tenant_id="test_tenant", agent_id="test_agent", limit=5
            )

            assert result is not None
            assert len(result) <= 5
            assert all("text" in suggestion for suggestion in result)
            assert all("type" in suggestion for suggestion in result)
            assert all("relevance" in suggestion for suggestion in result)

            # 验证相关性排序
            if len(result) > 1:
                relevances = [suggestion["relevance"] for suggestion in result]
                assert relevances == sorted(relevances, reverse=True)

    @pytest.mark.asyncio
    async def test_get_search_suggestions_empty_query(self, search_service):
        """测试空查询的搜索建议"""
        result = await search_service.get_search_suggestions(
            partial_query="", tenant_id="test_tenant", agent_id="test_agent"
        )

        assert result == []

        result = await search_service.get_search_suggestions(
            partial_query="测",  # 少于2个字符
            tenant_id="test_tenant",
            agent_id="test_agent",
        )

        assert result == []

    def test_calculate_relevance(self, search_service):
        """测试相关性计算"""
        # 完全匹配
        relevance = search_service._calculate_relevance("测试", "测试")
        assert relevance == 1.0

        # 开头匹配
        relevance = search_service._calculate_relevance("测试", "测试记忆标题")
        assert relevance == 0.8

        # 包含匹配
        relevance = search_service._calculate_relevance("测试", "这是一个测试记忆")
        assert relevance == 0.6

        # 部分匹配
        relevance = search_service._calculate_relevance("测试记忆", "这是一个测试")
        assert relevance == 0.4

        # 不匹配
        relevance = search_service._calculate_relevance("测试", "完全不相关的内容")
        assert relevance == 0.0

    @pytest.mark.asyncio
    async def test_filter_memories(self, search_service):
        """测试仅过滤记忆（无搜索查询）"""
        filters = {"level": "agent", "platform": "test_platform"}

        # 模拟过滤结果记忆
        filtered_memories = []
        for i in range(3):
            memory = MagicMock()
            memory.id = uuid4()
            memory.title = f"过滤记忆 {i}"
            memory.content = f"过滤内容 {i}"
            memory.created_at = datetime.utcnow()
            memory.to_dict.return_value = {"id": str(memory.id), "title": memory.title, "content": memory.content}
            filtered_memories.append(memory)

        with patch("src.memory_system.service.services.search_service.get_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = MagicMock()
            mock_session.return_value.__aexit__.return_value = MagicMock()

            session_instance = mock_session.return_value.__aenter__.return_value
            query_mock = MagicMock()
            session_instance.query = MagicMock(return_value=query_mock)

            # 模拟链式查询调用
            query_mock.filter.return_value = query_mock
            query_mock.count.return_value = AsyncMock(return_value=3)
            query_mock.order_by.return_value = query_mock
            query_mock.offset.return_value = query_mock
            query_mock.limit.return_value = AsyncMock(return_value=filtered_memories)

            result = await search_service._filter_memories(
                tenant_id="test_tenant",
                agent_id="test_agent",
                level=filters["level"],
                platform=filters["platform"],
                scope_id=None,
                date_from=None,
                date_to=None,
                sort_by="created_at",
                sort_order="desc",
                limit=10,
                offset=0,
            )

            assert result is not None
            assert result["search_type"] == "filter"
            assert len(result["memories"]) == 3
            assert result["total"] == 3

    def test_make_search_cache_key(self, search_service):
        """测试搜索缓存键生成"""
        query = "测试查询"
        tenant_id = "test_tenant"
        agent_id = "test_agent"
        level = "chat"
        platform = "test_platform"
        tags = ["标签1", "标签2"]

        cache_key = search_service._make_search_cache_key(
            query, tenant_id, agent_id, level, platform, None, tags, 10, 0, 0.7, None, None
        )

        assert cache_key is not None
        assert cache_key.startswith("search:")
        # 验证包含查询参数
        assert "test_tenant" in cache_key
        assert "test_agent" in cache_key
        assert "测试查询" in cache_key

        # 相同参数应该生成相同的缓存键
        cache_key2 = search_service._make_search_cache_key(
            query, tenant_id, agent_id, level, platform, None, tags, 10, 0, 0.7, None, None
        )
        assert cache_key == cache_key2

        # 不同参数应该生成不同的缓存键
        cache_key3 = search_service._make_search_cache_key(
            "不同查询", tenant_id, agent_id, level, platform, None, tags, 10, 0, 0.7, None, None
        )
        assert cache_key != cache_key3
