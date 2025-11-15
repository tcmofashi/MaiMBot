"""
智能体管理系统多租户隔离集成测试
验证隔离化智能体管理系统的核心功能
"""

import pytest
import asyncio

from src.agent import (
    # 原有API - 测试向后兼容
    Agent,
    get_agent,
    register_agent,
    # 隔离化API
    get_isolated_registry,
    create_tenant_agent,
    get_tenant_agent,
    update_tenant_agent,
    delete_tenant_agent,
    get_agent_instance,
    get_tenant_agent_instance,
)


def test_backward_compatibility():
    """测试向后兼容性"""
    print("🧪 测试向后兼容性...")

    # 测试原有API是否可用
    try:
        # 这些函数应该可以正常导入和调用
        assert callable(get_agent)
        assert callable(register_agent)
        print("✅ 原有API函数导入成功")

        # 测试Agent类是否可用
        assert callable(Agent)
        print("✅ Agent类导入成功")

    except Exception as e:
        pytest.fail(f"向后兼容性测试失败: {e}")

    print("✅ 向后兼容性测试通过")


def test_isolated_registry():
    """测试隔离化智能体注册中心"""
    print("🧪 测试隔离化智能体注册中心...")

    tenant1 = "test_tenant_1"
    tenant2 = "test_tenant_2"

    try:
        # 获取两个租户的注册中心
        registry1 = get_isolated_registry(tenant1)
        registry2 = get_isolated_registry(tenant2)

        assert registry1.tenant_id == tenant1
        assert registry2.tenant_id == tenant2
        assert registry1 != registry2
        print("✅ 租户隔离的注册中心创建成功")

        # 测试注册中心管理器
        from src.agent import get_isolated_registry_manager

        manager = get_isolated_registry_manager()
        assert tenant1 in manager.list_tenant_registries()
        assert tenant2 in manager.list_tenant_registries()
        print("✅ 注册中心管理器功能正常")

    except Exception as e:
        pytest.fail(f"隔离化注册中心测试失败: {e}")

    print("✅ 隔离化智能体注册中心测试通过")


def test_isolated_agent_creation():
    """测试隔离化智能体创建"""
    print("🧪 测试隔离化智能体创建...")

    tenant1 = "test_tenant_agent_1"
    tenant2 = "test_tenant_agent_2"
    agent_id = "test_assistant"

    try:
        # 为两个租户创建相同ID的智能体
        agent1 = create_tenant_agent(
            tenant_id=tenant1,
            agent_id=agent_id,
            name="租户1助手",
            persona_config={"name": "助手1", "prompt": "我是租户1的助手"},
            bot_overrides={"nickname": "助手1", "greeting": "你好，我是租户1的助手"},
            tags=["租户1"],
            description="租户1的测试助手",
        )

        agent2 = create_tenant_agent(
            tenant_id=tenant2,
            agent_id=agent_id,
            name="租户2助手",
            persona_config={"name": "助手2", "prompt": "我是租户2的助手"},
            bot_overrides={"nickname": "助手2", "greeting": "你好，我是租户2的助手"},
            tags=["租户2"],
            description="租户2的测试助手",
        )

        # 验证智能体创建成功
        assert agent1.name == "租户1助手"
        assert agent2.name == "租户2助手"
        assert agent1.agent_id != agent2.agent_id  # 应该包含租户前缀
        print("✅ 智能体创建成功")

        # 验证隔离
        retrieved_agent1 = get_tenant_agent(tenant1, agent_id)
        retrieved_agent2 = get_tenant_agent(tenant2, agent_id)

        assert retrieved_agent1 is not None
        assert retrieved_agent2 is not None
        assert retrieved_agent1.name != retrieved_agent2.name
        print("✅ 智能体隔离验证成功")

    except Exception as e:
        pytest.fail(f"智能体创建测试失败: {e}")

    # 清理测试数据
    finally:
        try:
            delete_tenant_agent(tenant1, agent_id)
            delete_tenant_agent(tenant2, agent_id)
        except:
            pass

    print("✅ 隔离化智能体创建测试通过")


def test_agent_config_update():
    """测试智能体配置更新"""
    print("🧪 测试智能体配置更新...")

    tenant_id = "test_tenant_update"
    agent_id = "test_update_agent"

    try:
        # 创建智能体
        create_tenant_agent(
            tenant_id=tenant_id,
            agent_id=agent_id,
            name="原始名称",
            persona_config={"name": "原始人格", "prompt": "原始提示"},
            description="原始描述",
        )

        # 更新配置
        updated_agent = update_tenant_agent(
            tenant_id=tenant_id, agent_id=agent_id, name="更新后名称", description="更新后描述"
        )

        assert updated_agent is not None
        assert updated_agent.name == "更新后名称"
        assert updated_agent.description == "更新后描述"
        # 人格应该保持不变
        assert updated_agent.persona.name == "原始人格"
        print("✅ 智能体配置更新成功")

    except Exception as e:
        pytest.fail(f"智能体配置更新测试失败: {e}")

    # 清理测试数据
    finally:
        try:
            delete_tenant_agent(tenant_id, agent_id)
        except:
            pass

    print("✅ 智能体配置更新测试通过")


def test_agent_instance_management():
    """测试智能体实例管理"""
    print("🧪 测试智能体实例管理...")

    tenant_id = "test_tenant_instance"
    agent_id = "test_instance_agent"

    try:
        # 创建智能体
        agent = create_tenant_agent(
            tenant_id=tenant_id,
            agent_id=agent_id,
            name="实例测试智能体",
            persona_config={"name": "实例助手", "prompt": "我是实例测试助手"},
        )

        # 获取智能体实例
        instance = get_agent_instance(agent, tenant_id)
        assert instance is not None
        assert instance.agent.agent_id == agent.agent_id
        assert instance.tenant_id == tenant_id
        print("✅ 智能体实例创建成功")

        # 测试实例状态管理
        instance.set_state("test_key", "test_value")
        assert instance.get_state("test_key") == "test_value"
        assert instance.get_state("non_existent_key", "default") == "default"
        print("✅ 实例状态管理正常")

        # 测试资源管理
        instance.add_resource("test_resource", {"data": "test"})
        assert instance.get_resource("test_resource") == {"data": "test"}
        assert instance.get_resource("non_existent_resource") is None
        print("✅ 实例资源管理正常")

        # 测试实例激活
        instance.activate()
        assert instance.is_active
        assert instance.usage_count > 0
        print("✅ 实例激活功能正常")

        # 通过便捷函数获取实例
        retrieved_instance = get_tenant_agent_instance(tenant_id, agent_id)
        assert retrieved_instance is not None
        assert retrieved_instance.get_state("test_key") == "test_value"
        print("✅ 便捷函数获取实例成功")

        # 获取实例信息
        instance_info = instance.get_instance_info()
        assert "agent_id" in instance_info
        assert "tenant_id" in instance_info
        assert "is_active" in instance_info
        print("✅ 实例信息获取成功")

    except Exception as e:
        pytest.fail(f"智能体实例管理测试失败: {e}")

    # 清理测试数据
    finally:
        try:
            delete_tenant_agent(tenant_id, agent_id)
            from src.agent import remove_agent_instance, clear_tenant_agent_instances

            remove_agent_instance(tenant_id, agent_id)
            clear_tenant_agent_instances(tenant_id)
        except:
            pass

    print("✅ 智能体实例管理测试通过")


async def test_async_initialization():
    """测试异步初始化"""
    print("🧪 测试异步初始化...")

    tenant_id = "test_tenant_async"

    try:
        # 测试异步初始化
        from src.agent import initialize_isolated_agent_manager

        agent_count = await initialize_isolated_agent_manager(tenant_id)
        print(f"✅ 异步初始化完成，加载了 {agent_count} 个智能体")

    except Exception as e:
        pytest.fail(f"异步初始化测试失败: {e}")

    print("✅ 异步初始化测试通过")


def test_system_statistics():
    """测试系统统计功能"""
    print("🧪 测试系统统计功能...")

    try:
        # 测试注册中心统计
        from src.agent import get_isolated_registry_stats

        registry_stats = get_isolated_registry_stats()
        assert "total_tenants" in registry_stats
        assert "registries" in registry_stats
        print("✅ 注册中心统计功能正常")

        # 测试管理器统计
        from src.agent import get_isolated_manager_stats

        manager_stats = get_isolated_manager_stats()
        assert "total_tenants" in manager_stats
        assert "managers" in manager_stats
        print("✅ 管理器统计功能正常")

        # 测试实例管理统计
        from src.agent import get_instance_management_stats

        instance_stats = get_instance_management_stats()
        assert "total_instances" in instance_stats
        assert "active_instances" in instance_stats
        print("✅ 实例管理统计功能正常")

    except Exception as e:
        pytest.fail(f"系统统计测试失败: {e}")

    print("✅ 系统统计功能测试通过")


def test_isolation_validation():
    """测试隔离验证"""
    print("🧪 测试隔离验证...")

    tenant1 = "test_tenant_isolation_1"
    tenant2 = "test_tenant_isolation_2"
    agent_id = "isolation_test"

    try:
        # 为两个租户创建智能体
        create_tenant_agent(
            tenant_id=tenant1,
            agent_id=agent_id,
            name="隔离测试1",
            persona_config={"name": "测试助手1", "prompt": "我是租户1的测试助手"},
        )

        create_tenant_agent(
            tenant_id=tenant2,
            agent_id=agent_id,
            name="隔离测试2",
            persona_config={"name": "测试助手2", "prompt": "我是租户2的测试助手"},
        )

        # 验证租户间的数据隔离
        agent1_from_tenant1 = get_tenant_agent(tenant1, agent_id)
        agent1_from_tenant2 = get_tenant_agent(tenant2, agent_id)

        # 租户1应该能访问到自己的智能体
        assert agent1_from_tenant1 is not None
        assert agent1_from_tenant1.name == "隔离测试1"

        # 租户2访问相同agent_id应该得到租户2的智能体
        assert agent1_from_tenant2 is not None
        assert agent1_from_tenant2.name == "隔离测试2"

        # 两个智能体应该不同
        assert agent1_from_tenant1.name != agent1_from_tenant2.name
        assert agent1_from_tenant1.agent_id != agent1_from_tenant2.agent_id

        print("✅ 租户隔离验证成功")

    except Exception as e:
        pytest.fail(f"隔离验证测试失败: {e}")

    # 清理测试数据
    finally:
        try:
            delete_tenant_agent(tenant1, agent_id)
            delete_tenant_agent(tenant2, agent_id)
        except:
            pass

    print("✅ 隔离验证测试通过")


def run_all_tests():
    """运行所有测试"""
    print("🚀 智能体管理系统多租户隔离集成测试\n")

    tests = [
        test_backward_compatibility,
        test_isolated_registry,
        test_isolated_agent_creation,
        test_agent_config_update,
        test_agent_instance_management,
        test_system_statistics,
        test_isolation_validation,
    ]

    passed_tests = 0
    total_tests = len(tests)

    for test in tests:
        try:
            test()
            passed_tests += 1
        except Exception as e:
            print(f"❌ 测试 {test.__name__} 失败: {e}")

    # 运行异步测试
    try:
        asyncio.run(test_async_initialization())
        passed_tests += 1
    except Exception as e:
        print(f"❌ 异步测试失败: {e}")

    total_tests += 1

    print(f"\n📊 测试结果: {passed_tests}/{total_tests} 通过")

    if passed_tests == total_tests:
        print("🎉 所有测试通过！智能体管理系统多租户隔离改造成功！")
        return True
    else:
        print("⚠️  部分测试失败，需要检查实现")
        return False


if __name__ == "__main__":
    run_all_tests()
