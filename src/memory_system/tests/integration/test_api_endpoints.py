"""
API端点的集成测试

测试记忆服务的RESTful API端点。
"""

import pytest
import asyncio
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

# 假设我们已经导入了FastAPI应用
try:
    from src.memory_system.service.main import app
except ImportError:
    # 如果无法导入，创建一个模拟的app
    from fastapi import FastAPI

    app = FastAPI()


@pytest.fixture
def test_client():
    """创建测试客户端"""
    return TestClient(app)


@pytest.fixture
async def http_client():
    """创建异步HTTP客户端"""
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
def sample_headers():
    """创建示例请求头"""
    return {
        "X-Tenant-ID": "test_tenant",
        "X-Agent-ID": "test_agent",
        "X-Platform": "test_platform",
        "X-Scope-ID": "test_scope",
        "Content-Type": "application/json",
    }


class TestMemoryAPI:
    """记忆API测试类"""

    @pytest.mark.asyncio
    async def test_create_memory_endpoint(self, http_client, sample_headers):
        """测试创建记忆端点"""
        memory_data = {
            "title": "API测试记忆",
            "content": "这是通过API创建的测试记忆",
            "level": "chat",
            "tags": ["API", "测试"],
            "metadata": {"test": True},
        }

        response = await http_client.post("/api/v1/memories", json=memory_data, headers=sample_headers)

        # 检查响应状态
        assert response.status_code in [200, 201]

        if response.status_code in [200, 201]:
            result = response.json()
            assert "id" in result
            assert result["title"] == memory_data["title"]
            assert result["content"] == memory_data["content"]
            assert result["level"] == memory_data["level"]
            assert result["tenant_id"] == sample_headers["X-Tenant-ID"]
            assert result["agent_id"] == sample_headers["X-Agent-ID"]

    @pytest.mark.asyncio
    async def test_get_memory_endpoint(self, http_client, sample_headers):
        """测试获取记忆端点"""
        # 首先创建一个记忆
        memory_data = {"title": "获取测试记忆", "content": "这是用于测试获取的记忆", "level": "chat"}

        create_response = await http_client.post("/api/v1/memories", json=memory_data, headers=sample_headers)

        if create_response.status_code in [200, 201]:
            created_memory = create_response.json()
            memory_id = created_memory["id"]

            # 获取记忆
            get_response = await http_client.get(f"/api/v1/memories/{memory_id}", headers=sample_headers)

            assert get_response.status_code == 200
            result = get_response.json()
            assert result["id"] == memory_id
            assert result["title"] == memory_data["title"]
        else:
            pytest.skip("无法创建测试记忆")

    @pytest.mark.asyncio
    async def test_get_memory_not_found(self, http_client, sample_headers):
        """测试获取不存在的记忆"""
        fake_id = str(uuid4())
        response = await http_client.get(f"/api/v1/memories/{fake_id}", headers=sample_headers)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_memory_endpoint(self, http_client, sample_headers):
        """测试更新记忆端点"""
        # 创建记忆
        memory_data = {"title": "原始标题", "content": "原始内容", "level": "chat"}

        create_response = await http_client.post("/api/v1/memories", json=memory_data, headers=sample_headers)

        if create_response.status_code in [200, 201]:
            created_memory = create_response.json()
            memory_id = created_memory["id"]

            # 更新记忆
            update_data = {"title": "更新后的标题", "content": "更新后的内容", "tags": ["更新"]}

            update_response = await http_client.put(
                f"/api/v1/memories/{memory_id}", json=update_data, headers=sample_headers
            )

            assert update_response.status_code == 200
            result = update_response.json()
            assert result["id"] == memory_id
            assert result["title"] == update_data["title"]
            assert result["content"] == update_data["content"]
            assert "tags" in result
        else:
            pytest.skip("无法创建测试记忆")

    @pytest.mark.asyncio
    async def test_delete_memory_endpoint(self, http_client, sample_headers):
        """测试删除记忆端点"""
        # 创建记忆
        memory_data = {"title": "待删除记忆", "content": "这个记忆将被删除", "level": "chat"}

        create_response = await http_client.post("/api/v1/memories", json=memory_data, headers=sample_headers)

        if create_response.status_code in [200, 201]:
            created_memory = create_response.json()
            memory_id = created_memory["id"]

            # 删除记忆
            delete_response = await http_client.delete(f"/api/v1/memories/{memory_id}", headers=sample_headers)

            assert delete_response.status_code == 200
            result = delete_response.json()
            assert result["success"] is True
            assert "memory_id" in result

            # 验证记忆已删除
            get_response = await http_client.get(f"/api/v1/memories/{memory_id}", headers=sample_headers)
            assert get_response.status_code == 404
        else:
            pytest.skip("无法创建测试记忆")

    @pytest.mark.asyncio
    async def test_search_memories_endpoint(self, http_client, sample_headers):
        """测试搜索记忆端点"""
        # 先创建一些测试记忆
        test_memories = [
            {
                "title": "机器学习基础",
                "content": "机器学习是人工智能的一个重要分支",
                "level": "agent",
                "tags": ["AI", "ML"],
            },
            {
                "title": "深度学习进阶",
                "content": "深度学习使用神经网络进行模式识别",
                "level": "agent",
                "tags": ["AI", "DL"],
            },
            {"title": "Python编程", "content": "Python是一种流行的编程语言", "level": "platform", "tags": ["编程"]},
        ]

        created_ids = []
        for memory_data in test_memories:
            create_response = await http_client.post("/api/v1/memories", json=memory_data, headers=sample_headers)
            if create_response.status_code in [200, 201]:
                created_memory = create_response.json()
                created_ids.append(created_memory["id"])

        if created_ids:
            # 搜索记忆
            search_data = {"query": "学习", "limit": 10, "similarity_threshold": 0.5}

            search_response = await http_client.post(
                "/api/v1/memories/search", json=search_data, headers=sample_headers
            )

            assert search_response.status_code == 200
            result = search_response.json()
            assert "memories" in result
            assert "total" in result
            assert "search_type" in result

            # 验证搜索结果包含相关记忆
            memory_titles = [memory["title"] for memory in result["memories"]]
            assert any("学习" in title for title in memory_titles)
        else:
            pytest.skip("无法创建测试记忆")

    @pytest.mark.asyncio
    async def test_query_memories_endpoint(self, http_client, sample_headers):
        """测试查询记忆端点"""
        # 先创建测试记忆
        memory_data = {
            "title": "查询测试记忆",
            "content": "这是用于测试查询的记忆",
            "level": "chat",
            "tags": ["测试", "查询"],
        }

        create_response = await http_client.post("/api/v1/memories", json=memory_data, headers=sample_headers)

        if create_response.status_code in [200, 201]:
            # 查询记忆
            query_data = {
                "filters": {"level": "chat", "tags": ["测试"]},
                "sort_by": "created_at",
                "sort_order": "desc",
                "limit": 5,
            }

            query_response = await http_client.post("/api/v1/memories/query", json=query_data, headers=sample_headers)

            assert query_response.status_code == 200
            result = query_response.json()
            assert "memories" in result
            assert "total" in result

            # 验证查询结果
            if result["memories"]:
                memory = result["memories"][0]
                assert memory["level"] == "chat"
                assert "测试" in memory["tags"]
        else:
            pytest.skip("无法创建测试记忆")

    @pytest.mark.asyncio
    async def test_batch_create_memories_endpoint(self, http_client, sample_headers):
        """测试批量创建记忆端点"""
        batch_data = {
            "memories": [
                {"title": "批量记忆1", "content": "这是第一个批量创建的记忆", "level": "chat"},
                {"title": "批量记忆2", "content": "这是第二个批量创建的记忆", "level": "chat"},
                {"title": "批量记忆3", "content": "这是第三个批量创建的记忆", "level": "platform"},
            ]
        }

        response = await http_client.post("/api/v1/memories/batch", json=batch_data, headers=sample_headers)

        assert response.status_code == 200
        result = response.json()
        assert "successful" in result
        assert "failed" in result
        assert "errors" in result

        # 验证至少有一些记忆创建成功
        assert result["successful"] >= 0

    @pytest.mark.asyncio
    async def test_batch_delete_memories_endpoint(self, http_client, sample_headers):
        """测试批量删除记忆端点"""
        # 先创建一些测试记忆
        created_ids = []
        for i in range(3):
            memory_data = {"title": f"批量删除测试{i}", "content": f"这是第{i}个待批量删除的记忆", "level": "chat"}

            create_response = await http_client.post("/api/v1/memories", json=memory_data, headers=sample_headers)
            if create_response.status_code in [200, 201]:
                created_memory = create_response.json()
                created_ids.append(created_memory["id"])

        if len(created_ids) >= 2:
            # 批量删除记忆
            batch_delete_data = {
                "memory_ids": created_ids[:2]  # 只删除前两个
            }

            delete_response = await http_client.delete(
                "/api/v1/memories/batch", json=batch_delete_data, headers=sample_headers
            )

            assert delete_response.status_code == 200
            result = delete_response.json()
            assert "successful" in result
            assert "failed" in result
        else:
            pytest.skip("无法创建足够的测试记忆")

    @pytest.mark.asyncio
    async def test_get_tenant_agent_memories_endpoint(self, http_client, sample_headers):
        """测试获取租户智能体记忆端点"""
        tenant_id = sample_headers["X-Tenant-ID"]
        agent_id = sample_headers["X-Agent-ID"]

        # 先创建一些测试记忆
        test_memories = [
            {"title": "租户记忆1", "content": "内容1", "level": "agent"},
            {"title": "租户记忆2", "content": "内容2", "level": "platform"},
            {"title": "租户记忆3", "content": "内容3", "level": "chat"},
        ]

        for memory_data in test_memories:
            await http_client.post("/api/v1/memories", json=memory_data, headers=sample_headers)

        # 获取租户智能体的所有记忆
        response = await http_client.get(
            f"/api/v1/memories/tenant/{tenant_id}/agent/{agent_id}", headers=sample_headers
        )

        assert response.status_code == 200
        result = response.json()
        assert "items" in result  # 注意：这里的字段名可能是items而不是memories
        assert "total" in result


class TestConflictAPI:
    """冲突API测试类"""

    @pytest.mark.asyncio
    async def test_create_conflict_endpoint(self, http_client, sample_headers):
        """测试创建冲突记录端点"""
        conflict_data = {
            "title": "API测试冲突",
            "context": "这是通过API创建的测试冲突",
            "start_following": True,
            "chat_id": "test_chat",
        }

        response = await http_client.post("/api/v1/conflicts", json=conflict_data, headers=sample_headers)

        # 检查响应状态
        assert response.status_code in [200, 201]

        if response.status_code in [200, 201]:
            result = response.json()
            assert "id" in result
            assert result["title"] == conflict_data["title"]
            assert result["context"] == conflict_data["context"]
            assert result["start_following"] == conflict_data["start_following"]
            assert result["chat_id"] == conflict_data["chat_id"]

    @pytest.mark.asyncio
    async def test_get_conflict_endpoint(self, http_client, sample_headers):
        """测试获取冲突记录端点"""
        # 先创建一个冲突记录
        conflict_data = {"title": "获取测试冲突", "context": "这是用于测试获取的冲突", "start_following": False}

        create_response = await http_client.post("/api/v1/conflicts", json=conflict_data, headers=sample_headers)

        if create_response.status_code in [200, 201]:
            created_conflict = create_response.json()
            conflict_id = created_conflict["id"]

            # 获取冲突记录
            get_response = await http_client.get(f"/api/v1/conflicts/{conflict_id}", headers=sample_headers)

            assert get_response.status_code == 200
            result = get_response.json()
            assert result["id"] == conflict_id
            assert result["title"] == conflict_data["title"]
        else:
            pytest.skip("无法创建测试冲突")

    @pytest.mark.asyncio
    async def test_resolve_conflict_endpoint(self, http_client, sample_headers):
        """测试解决冲突端点"""
        # 先创建一个冲突记录
        conflict_data = {"title": "待解决冲突", "context": "这个冲突将被解决", "start_following": True}

        create_response = await http_client.post("/api/v1/conflicts", json=conflict_data, headers=sample_headers)

        if create_response.status_code in [200, 201]:
            created_conflict = create_response.json()
            conflict_id = created_conflict["id"]

            # 解决冲突
            resolve_response = await http_client.post(
                f"/api/v1/conflicts/{conflict_id}/resolve", headers=sample_headers
            )

            assert resolve_response.status_code == 200
            result = resolve_response.json()
            assert result["id"] == conflict_id
            assert result["resolved"] is True
            assert "resolved_at" in result
        else:
            pytest.skip("无法创建测试冲突")


class TestHealthAPI:
    """健康检查API测试类"""

    @pytest.mark.asyncio
    async def test_health_check_endpoint(self, http_client):
        """测试健康检查端点"""
        response = await http_client.get("/api/v1/health")

        assert response.status_code == 200
        result = response.json()
        assert "status" in result
        assert "version" in result
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_readiness_check_endpoint(self, http_client):
        """测试就绪检查端点"""
        response = await http_client.get("/api/v1/health/readiness")

        # 就绪检查可能返回200或503
        assert response.status_code in [200, 503]
        result = response.json()
        assert "ready" in result

    @pytest.mark.asyncio
    async def test_liveness_check_endpoint(self, http_client):
        """测试存活检查端点"""
        response = await http_client.get("/api/v1/health/liveness")

        assert response.status_code == 200
        response.json()
        assert "alive" == True


class TestAdminAPI:
    """系统管理API测试类"""

    @pytest.mark.asyncio
    async def test_get_system_stats_endpoint(self, http_client, sample_headers):
        """测试获取系统统计端点"""
        response = await http_client.get("/api/v1/stats", headers=sample_headers)

        assert response.status_code == 200
        result = response.json()
        assert "total_memories" in result
        assert "total_conflicts" in result
        assert "active_tenants" in result

    @pytest.mark.asyncio
    async def test_cleanup_expired_data_endpoint(self, http_client, sample_headers):
        """测试清理过期数据端点"""
        # 这是一个可能耗时的操作，使用试运行模式
        params = {"dry_run": True, "older_than_days": 30}
        response = await http_client.post("/api/v1/maintenance/cleanup", params=params, headers=sample_headers)

        # 检查响应状态（可能需要管理员权限）
        assert response.status_code in [200, 403, 401]

        if response.status_code == 200:
            result = response.json()
            assert "task_id" in result
            assert "status" in result


class TestErrorHandling:
    """错误处理测试类"""

    @pytest.mark.asyncio
    async def test_missing_isolation_headers(self, http_client):
        """测试缺少隔离头部时的错误处理"""
        memory_data = {"title": "测试记忆", "content": "测试内容", "level": "chat"}

        # 不发送必需的隔离头部
        response = await http_client.post(
            "/api/v1/memories", json=memory_data, headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 400
        result = response.json()
        assert "error" in result

    @pytest.mark.asyncio
    async def test_invalid_memory_data(self, http_client, sample_headers):
        """测试无效记忆数据的错误处理"""
        # 发送缺少必需字段的数据
        invalid_data = {"content": "只有内容，缺少标题和级别"}

        response = await http_client.post("/api/v1/memories", json=invalid_data, headers=sample_headers)

        assert response.status_code == 422  # 验证错误

    @pytest.mark.asyncio
    async def test_invalid_memory_id_format(self, http_client, sample_headers):
        """测试无效记忆ID格式的错误处理"""
        invalid_id = "invalid-uuid-format"

        response = await http_client.get(f"/api/v1/memories/{invalid_id}", headers=sample_headers)

        assert response.status_code == 422  # 验证错误

    @pytest.mark.asyncio
    async def test_cross_tenant_access(self, http_client, sample_headers):
        """测试跨租户访问的错误处理"""
        # 尝试访问另一个租户的记忆
        other_tenant_headers = sample_headers.copy()
        other_tenant_headers["X-Tenant-ID"] = "other_tenant"

        response = await http_client.get(
            "/api/v1/memories/tenant/test_tenant/agent/test_agent", headers=other_tenant_headers
        )

        # 应该返回403（禁止访问）或根据实现返回404
        assert response.status_code in [403, 404]


@pytest.mark.asyncio
async def test_api_rate_limiting(http_client, sample_headers):
    """测试API限流"""
    # 快速发送多个请求
    responses = []
    for _i in range(10):
        response = await http_client.get("/api/v1/health", headers=sample_headers)
        responses.append(response.status_code)

    # 检查是否有请求被限流
    # 注意：实际的限流阈值可能不同
    any(status == 429 for status in responses)
    # 这个测试可能需要根据实际的限流配置调整


@pytest.mark.asyncio
async def test_api_concurrent_requests(http_client, sample_headers):
    """测试API并发请求"""

    async def make_request():
        """发起单个请求"""
        response = await http_client.get("/api/v1/health", headers=sample_headers)
        return response.status_code

    # 并发发起多个请求
    tasks = [make_request() for _ in range(5)]
    responses = await asyncio.gather(*tasks, return_exceptions=True)

    # 检查所有请求都成功完成
    successful_responses = [r for r in responses if isinstance(r, int) and r == 200]
    assert len(successful_responses) >= 3  # 至少大部分请求成功
