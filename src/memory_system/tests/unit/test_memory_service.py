"""
记忆服务的单元测试

测试记忆服务的核心业务逻辑。
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.memory_system.service.services.memory_service import MemoryService
from src.memory_system.service.database.models import Memory, Conflict
from src.memory_system.service.utils.isolation import IsolationContext


@pytest.fixture
async def memory_service():
    """创建记忆服务实例"""
    service = MemoryService()
    yield service


@pytest.fixture
def sample_isolation_context():
    """创建示例隔离上下文"""
    return IsolationContext(
        tenant_id="test_tenant", agent_id="test_agent", platform="test_platform", scope_id="test_scope"
    )


class TestMemoryService:
    """记忆服务测试类"""

    @pytest.mark.asyncio
    async def test_create_memory_success(self, memory_service, sample_isolation_context):
        """测试成功创建记忆"""
        memory_data = {
            "title": "测试记忆",
            "content": "这是一个测试记忆的内容",
            "level": "chat",
            "tags": ["测试", "示例"],
            "metadata": {"type": "test"},
        }

        # 模拟数据库会话
        with patch("src.memory_system.service.services.memory_service.get_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = MagicMock()
            mock_session.return_value.__aexit__.return_value = MagicMock()

            # 模拟编码文本
            with patch("src.memory_system.service.services.memory_service.encode_text") as mock_encode:
                mock_encode.return_value = [0.1] * 1536  # 模拟嵌入向量

                # 模拟数据库操作
                mock_memory = MagicMock()
                mock_memory.id = uuid4()
                mock_memory.tenant_id = sample_isolation_context.tenant_id
                mock_memory.agent_id = sample_isolation_context.agent_id
                mock_memory.title = memory_data["title"]
                mock_memory.content = memory_data["content"]
                mock_memory.level = memory_data["level"]
                mock_memory.tags = memory_data["tags"]
                mock_memory.metadata = memory_data["metadata"]
                mock_memory.status = "active"
                mock_memory.embedding = [0.1] * 1536
                mock_memory.created_at = datetime.utcnow()
                mock_memory.updated_at = datetime.utcnow()

                session_instance = mock_session.return_value.__aenter__.return_value
                session_instance.add = MagicMock()
                session_instance.commit = AsyncMock()
                session_instance.refresh = AsyncMock()

                # 模拟cache失效
                with patch.object(memory_service, "_invalidate_memory_caches") as mock_invalidate:
                    with patch.object(memory_service, "_log_operation") as mock_log:
                        result = await memory_service.create_memory(
                            title=memory_data["title"],
                            content=memory_data["content"],
                            level=memory_data["level"],
                            tenant_id=sample_isolation_context.tenant_id,
                            agent_id=sample_isolation_context.agent_id,
                            platform=sample_isolation_context.platform,
                            scope_id=sample_isolation_context.scope_id,
                            tags=memory_data["tags"],
                            metadata=memory_data["metadata"],
                        )

                        # 验证结果
                        assert result is not None
                        assert result.title == memory_data["title"]
                        assert result.content == memory_data["content"]
                        assert result.level == memory_data["level"]
                        assert result.tenant_id == sample_isolation_context.tenant_id
                        assert result.agent_id == sample_isolation_context.agent_id

                        # 验证调用
                        mock_encode.assert_called_once_with(memory_data["content"])
                        session_instance.add.assert_called_once()
                        session_instance.commit.assert_called_once()
                        session_instance.refresh.assert_called_once()
                        mock_invalidate.assert_called_once()
                        mock_log.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_memory_without_content(self, memory_service, sample_isolation_context):
        """测试创建没有内容的记忆"""
        with patch("src.memory_system.service.services.memory_service.get_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = MagicMock()
            mock_session.return_value.__aexit__.return_value = MagicMock()

            with patch("src.memory_system.service.services.memory_service.encode_text") as mock_encode:
                mock_encode.return_value = None  # 没有内容时返回None

                mock_memory = MagicMock()
                mock_memory.id = uuid4()
                mock_memory.title = "空内容记忆"
                mock_memory.content = ""
                mock_memory.level = "chat"
                mock_memory.embedding = None

                session_instance = mock_session.return_value.__aenter__.return_value
                session_instance.add = MagicMock()
                session_instance.commit = AsyncMock()
                session_instance.refresh = AsyncMock()

                result = await memory_service.create_memory(
                    title="空内容记忆",
                    content="",
                    level="chat",
                    tenant_id=sample_isolation_context.tenant_id,
                    agent_id=sample_isolation_context.agent_id,
                )

                assert result is not None
                assert result.content == ""
                assert result.embedding is None

    @pytest.mark.asyncio
    async def test_get_memory_cached(self, memory_service):
        """测试从缓存获取记忆"""
        memory_id = uuid4()
        cached_memory_data = {
            "id": str(memory_id),
            "title": "缓存的记忆",
            "content": "这是从缓存获取的记忆",
            "level": "chat",
            "tenant_id": "test_tenant",
            "agent_id": "test_agent",
            "created_at": datetime.utcnow().isoformat(),
        }

        # 模拟缓存命中
        with patch.object(memory_service.cache, "get_memory") as mock_cache_get:
            mock_cache_get.return_value = cached_memory_data

            result = await memory_service.get_memory(memory_id)

            assert result is not None
            assert result.title == "缓存的记忆"
            mock_cache_get.assert_called_once_with(str(memory_id))

    @pytest.mark.asyncio
    async def test_get_memory_from_database(self, memory_service):
        """测试从数据库获取记忆"""
        memory_id = uuid4()
        mock_memory = MagicMock()
        mock_memory.to_dict.return_value = {
            "id": str(memory_id),
            "title": "数据库记忆",
            "content": "这是从数据库获取的记忆",
            "level": "chat",
        }

        # 模拟缓存未命中
        with patch.object(memory_service.cache, "get_memory") as mock_cache_get:
            mock_cache_get.return_value = None

            with patch("src.memory_system.service.services.memory_service.get_session") as mock_session:
                mock_session.return_value.__aenter__.return_value = MagicMock()
                mock_session.return_value.__aexit__.return_value = MagicMock()

                session_instance = mock_session.return_value.__aenter__.return_value
                session_instance.get = AsyncMock(return_value=mock_memory)

                with patch.object(memory_service.cache, "set_memory") as mock_cache_set:
                    result = await memory_service.get_memory(memory_id)

                    assert result is not None
                    assert result == mock_memory
                    mock_cache_get.assert_called_once_with(str(memory_id))
                    session_instance.get.assert_called_once_with(Memory, memory_id)
                    mock_cache_set.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_memory(self, memory_service, sample_isolation_context):
        """测试更新记忆"""
        memory_id = uuid4()
        update_data = {"title": "更新后的标题", "content": "更新后的内容", "tags": ["更新", "测试"]}

        existing_memory = MagicMock()
        existing_memory.id = memory_id
        existing_memory.tenant_id = sample_isolation_context.tenant_id
        existing_memory.agent_id = sample_isolation_context.agent_id
        existing_memory.title = "原标题"
        existing_memory.content = "原内容"
        existing_memory.tags = ["原标签"]

        with patch("src.memory_system.service.services.memory_service.get_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = MagicMock()
            mock_session.return_value.__aexit__.return_value = MagicMock()

            session_instance = mock_session.return_value.__aenter__.return_value
            session_instance.get = AsyncMock(return_value=existing_memory)
            session_instance.commit = AsyncMock()
            session_instance.refresh = AsyncMock()

            with patch("src.memory_system.service.services.memory_service.encode_text") as mock_encode:
                mock_encode.return_value = [0.2] * 1536  # 新的嵌入向量

                with patch.object(memory_service.cache, "invalidate_memory") as mock_invalidate:
                    with patch.object(memory_service, "_invalidate_memory_caches") as mock_invalidate_caches:
                        with patch.object(memory_service, "_log_operation") as mock_log:
                            result = await memory_service.update_memory(
                                memory_id=memory_id,
                                title=update_data["title"],
                                content=update_data["content"],
                                tags=update_data["tags"],
                            )

                            assert result is not None
                            assert result.title == update_data["title"]
                            assert result.content == update_data["content"]
                            assert result.tags == update_data["tags"]

                            # 验证调用
                            session_instance.get.assert_called_once_with(Memory, memory_id)
                            mock_encode.assert_called_once_with(update_data["content"])
                            session_instance.commit.assert_called_once()
                            session_instance.refresh.assert_called_once()
                            mock_invalidate.assert_called_once_with(str(memory_id))
                            mock_invalidate_caches.assert_called_once()
                            mock_log.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_memory(self, memory_service):
        """测试删除记忆"""
        memory_id = uuid4()
        mock_memory = MagicMock()
        mock_memory.id = memory_id
        mock_memory.tenant_id = "test_tenant"
        mock_memory.agent_id = "test_agent"
        mock_memory.to_dict.return_value = {"id": str(memory_id)}

        with patch("src.memory_system.service.services.memory_service.get_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = MagicMock()
            mock_session.return_value.__aexit__.return_value = MagicMock()

            session_instance = mock_session.return_value.__aenter__.return_value
            session_instance.get = AsyncMock(return_value=mock_memory)
            session_instance.delete = AsyncMock()
            session_instance.commit = AsyncMock()

            with patch.object(memory_service.cache, "invalidate_memory") as mock_invalidate:
                with patch.object(memory_service, "_invalidate_memory_caches") as mock_invalidate_caches:
                    with patch.object(memory_service, "_log_operation") as mock_log:
                        result = await memory_service.delete_memory(memory_id)

                        assert result is True
                        session_instance.get.assert_called_once_with(Memory, memory_id)
                        session_instance.delete.assert_called_once_with(mock_memory)
                        session_instance.commit.assert_called_once()
                        mock_invalidate.assert_called_once_with(str(memory_id))
                        mock_invalidate_caches.assert_called_once()
                        mock_log.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_memory_not_found(self, memory_service):
        """测试删除不存在的记忆"""
        memory_id = uuid4()

        with patch("src.memory_system.service.services.memory_service.get_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = MagicMock()
            mock_session.return_value.__aexit__.return_value = MagicMock()

            session_instance = mock_session.return_value.__aenter__.return_value
            session_instance.get = AsyncMock(return_value=None)

            result = await memory_service.delete_memory(memory_id)

            assert result is False
            session_instance.get.assert_called_once_with(Memory, memory_id)

    @pytest.mark.asyncio
    async def test_query_memories(self, memory_service):
        """测试查询记忆"""
        filters = {"tenant_id": "test_tenant", "agent_id": "test_agent", "level": "chat"}

        mock_memories = [MagicMock(), MagicMock()]
        for i, memory in enumerate(mock_memories):
            memory.to_dict.return_value = {"id": f"memory_{i}", "title": f"记忆 {i}", "content": f"内容 {i}"}

        with patch("src.memory_system.service.services.memory_service.get_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = MagicMock()
            mock_session.return_value.__aexit__.return_value = MagicMock()

            session_instance = mock_session.return_value.__aenter__.return_value
            query_mock = MagicMock()
            session_instance.query = MagicMock(return_value=query_mock)

            # 模拟链式调用
            query_mock.filter.return_value = query_mock
            query_mock.order_by.return_value = query_mock
            query_mock.count.return_value = AsyncMock(return_value=2)
            query_mock.offset.return_value = query_mock
            query_mock.limit.return_value = AsyncMock(return_value=mock_memories)

            result = await memory_service.query_memories(
                filters=filters, sort_by="created_at", sort_order="desc", limit=10, offset=0
            )

            assert result["memories"] is not None
            assert len(result["memories"]) == 2
            assert result["total"] == 2
            assert result["limit"] == 10
            assert result["offset"] == 0
            assert result["has_more"] is False

    @pytest.mark.asyncio
    async def test_batch_create_memories(self, memory_service, sample_isolation_context):
        """测试批量创建记忆"""
        memories_data = [
            {"title": "批量记忆1", "content": "批量内容1", "level": "chat"},
            {"title": "批量记忆2", "content": "批量内容2", "level": "chat"},
        ]

        with patch("src.memory_system.service.services.memory_service.get_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = MagicMock()
            mock_session.return_value.__aexit__.return_value = MagicMock()

            session_instance = mock_session.return_value.__aenter__.return_value
            session_instance.add = MagicMock()
            session_instance.commit = AsyncMock()

            mock_created_memories = []
            for _i, memory_data in enumerate(memories_data):
                mock_memory = MagicMock()
                mock_memory.id = uuid4()
                mock_memory.title = memory_data["title"]
                mock_memory.to_dict.return_value = {"id": str(mock_memory.id), "title": memory_data["title"]}
                mock_created_memories.append(mock_memory)

            with patch("src.memory_system.service.services.memory_service.encode_text") as mock_encode:
                mock_encode.return_value = [0.3] * 1536

                with patch.object(memory_service, "_invalidate_memory_caches") as mock_invalidate:
                    result = await memory_service.batch_create_memories(
                        memories=memories_data,
                        tenant_id=sample_isolation_context.tenant_id,
                        agent_id=sample_isolation_context.agent_id,
                    )

                    assert result["successful"] == 2
                    assert result["failed"] == 0
                    assert len(result["errors"]) == 0
                    assert len(result["created_memories"]) == 2

                    # 验证调用次数
                    assert session_instance.add.call_count == 2
                    assert session_instance.commit.call_count == 1
                    mock_invalidate.assert_called_once()

    @pytest.mark.asyncio
    async def test_increment_access_count(self, memory_service):
        """测试增加访问次数"""
        memory_id = uuid4()
        mock_memory = MagicMock()
        mock_memory.access_count = 5

        with patch("src.memory_system.service.services.memory_service.get_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = MagicMock()
            mock_session.return_value.__aexit__.return_value = MagicMock()

            session_instance = mock_session.return_value.__aenter__.return_value
            session_instance.get = AsyncMock(return_value=mock_memory)
            session_instance.commit = AsyncMock()

            result = await memory_service.increment_access_count(memory_id)

            assert result is True
            assert mock_memory.access_count == 6  # 验证访问次数增加了1
            session_instance.get.assert_called_once_with(Memory, memory_id)
            session_instance.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_regenerate_embedding(self, memory_service):
        """测试重新生成嵌入向量"""
        memory_id = uuid4()
        new_content = "更新后的内容"
        new_embedding = [0.4] * 1536

        mock_memory = MagicMock()
        mock_memory.content = new_content

        with patch("src.memory_system.service.services.memory_service.get_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = MagicMock()
            mock_session.return_value.__aexit__.return_value = MagicMock()

            session_instance = mock_session.return_value.__aenter__.return_value
            session_instance.get = AsyncMock(return_value=mock_memory)
            session_instance.commit = AsyncMock()

            with patch("src.memory_system.service.services.memory_service.encode_text") as mock_encode:
                mock_encode.return_value = new_embedding

                with patch.object(memory_service.cache, "invalidate_memory") as mock_invalidate:
                    result = await memory_service.regenerate_embedding(memory_id)

                    assert result is True
                    assert mock_memory.embedding == new_embedding
                    mock_encode.assert_called_once_with(new_content)
                    session_instance.commit.assert_called_once()
                    mock_invalidate.assert_called_once_with(str(memory_id))

    @pytest.mark.asyncio
    async def test_health_check(self, memory_service):
        """测试健康检查"""
        with patch("src.memory_system.service.services.memory_service.get_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = MagicMock()
            mock_session.return_value.__aexit__.return_value = MagicMock()

            session_instance = mock_session.return_value.__aenter__.return_value
            session_instance.execute = AsyncMock()

            result = await memory_service.health_check()

            assert result is not None
            assert result["status"] == "healthy"
            assert "database" in result
            assert "timestamp" in result

    # 冲突跟踪相关测试
    @pytest.mark.asyncio
    async def test_create_conflict(self, memory_service, sample_isolation_context):
        """测试创建冲突记录"""
        conflict_data = {"title": "测试冲突", "context": "这是一个测试冲突", "chat_id": "test_chat"}

        with patch("src.memory_system.service.services.memory_service.get_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = MagicMock()
            mock_session.return_value.__aexit__.return_value = MagicMock()

            session_instance = mock_session.return_value.__aenter__.return_value
            session_instance.add = MagicMock()
            session_instance.commit = AsyncMock()
            session_instance.refresh = AsyncMock()

            result = await memory_service.create_conflict(
                title=conflict_data["title"],
                context=conflict_data["context"],
                tenant_id=sample_isolation_context.tenant_id,
                agent_id=sample_isolation_context.agent_id,
                platform=sample_isolation_context.platform,
                scope_id=sample_isolation_context.scope_id,
                chat_id=conflict_data["chat_id"],
            )

            assert result is not None
            assert result.title == conflict_data["title"]
            assert result.context == conflict_data["context"]
            assert result.tenant_id == sample_isolation_context.tenant_id
            assert result.agent_id == sample_isolation_context.agent_id
            assert result.chat_id == conflict_data["chat_id"]

            session_instance.add.assert_called_once()
            session_instance.commit.assert_called_once()
            session_instance.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_conflict(self, memory_service):
        """测试解决冲突"""
        conflict_id = uuid4()
        mock_conflict = MagicMock()
        mock_conflict.id = conflict_id
        mock_conflict.resolved = False
        mock_conflict.resolved_at = None

        with patch("src.memory_system.service.services.memory_service.get_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = MagicMock()
            mock_session.return_value.__aexit__.return_value = MagicMock()

            session_instance = mock_session.return_value.__aenter__.return_value
            session_instance.get = AsyncMock(return_value=mock_conflict)
            session_instance.commit = AsyncMock()
            session_instance.refresh = AsyncMock()

            result = await memory_service.resolve_conflict(conflict_id)

            assert result is not None
            assert result.resolved is True
            assert result.resolved_at is not None

            session_instance.get.assert_called_once_with(Conflict, conflict_id)
            session_instance.commit.assert_called_once()
            session_instance.refresh.assert_called_once()

    # 私有方法测试
    def test_make_query_cache_key(self, memory_service):
        """测试查询缓存键生成"""
        filters = {"tenant_id": "test", "agent_id": "agent"}
        sort_by = "created_at"
        sort_order = "desc"
        limit = 10
        offset = 0

        cache_key = memory_service._make_query_cache_key(filters, sort_by, sort_order, limit, offset)

        assert cache_key is not None
        assert cache_key.startswith("query:")
        assert len(cache_key) > 20  # 确保有足够的长度

    @pytest.mark.asyncio
    async def test_invalidate_memory_caches(self, memory_service):
        """测试清理记忆缓存"""
        tenant_id = "test_tenant"
        agent_id = "test_agent"

        with patch.object(memory_service.cache, "invalidate_tenant_memories") as mock_invalidate:
            with patch.object(memory_service.stats_cache, "get_memory_stats") as mock_stats:
                mock_invalidate.return_value = 5
                mock_stats.return_value = None

                await memory_service._invalidate_memory_caches(tenant_id, agent_id)

                mock_invalidate.assert_called_once_with(tenant_id, agent_id)
                mock_stats.assert_called_once_with(tenant_id, agent_id)
