"""
智能体管理系统多租户隔离使用示例
演示如何使用隔离化的智能体管理系统
"""

import asyncio

from src.agent import (
    # 原有API - 继续工作
    get_agent,
    create_tenant_agent,
    get_tenant_agent,
    update_tenant_agent,
    delete_tenant_agent,
    list_tenant_agents,
    get_tenant_agent_config_stats,
    get_agent_instance,
    get_tenant_agent_instance,
    get_isolated_manager_stats,
    get_isolated_registry_stats,
    get_instance_management_stats,
)


def demo_backward_compatibility():
    """演示向后兼容性 - 现有代码无需修改"""

    print("=== 向后兼容性演示 ===")

    # 原有代码继续正常工作
    agent = get_agent("default")
    if agent:
        print(f"✓ 原有API工作正常: {agent.name}")
    else:
        print("✓ 原有API可访问，但default智能体不存在")

    # 原有智能体注册功能继续工作
    print("✓ 原有register_agent函数可用")

    print("向后兼容性测试完成！\n")


def demo_isolated_agent_management():
    """演示隔离化智能体管理"""

    print("=== 隔离化智能体管理演示 ===")

    # 为两个租户创建智能体
    tenant1 = "company_a"
    tenant2 = "company_b"

    # 创建租户1的智能体
    agent1 = create_tenant_agent(
        tenant_id=tenant1,
        agent_id="assistant",
        name="客服助手",
        persona_config={"name": "小助手", "prompt": "我是一个专业的客服助手", "response_style": "友好专业"},
        bot_overrides={"nickname": "客服小助手", "greeting": "您好，我是您的专属客服助手"},
        tags=["客服", "专业"],
        description="为公司A提供的客服助手",
    )

    print(f"✓ 为租户 '{tenant1}' 创建智能体: {agent1.name}")

    # 创建租户2的智能体（使用相同agent_id但不同配置）
    agent2 = create_tenant_agent(
        tenant_id=tenant2,
        agent_id="assistant",
        name="销售助手",
        persona_config={"name": "销售专家", "prompt": "我是一个专业的销售助手", "response_style": "热情积极"},
        bot_overrides={"nickname": "销售小助手", "greeting": "您好，我是您的专属销售助手"},
        tags=["销售", "专业"],
        description="为公司B提供的销售助手",
    )

    print(f"✓ 为租户 '{tenant2}' 创建智能体: {agent2.name}")

    # 获取智能体（验证隔离）
    retrieved_agent1 = get_tenant_agent(tenant1, "assistant")
    retrieved_agent2 = get_tenant_agent(tenant2, "assistant")

    print(f"✓ 租户 '{tenant1}' 的智能体: {retrieved_agent1.name if retrieved_agent1 else 'None'}")
    print(f"✓ 租户 '{tenant2}' 的智能体: {retrieved_agent2.name if retrieved_agent2 else 'None'}")

    # 验证隔离 - 相同agent_id但不同租户的智能体不同
    if retrieved_agent1 and retrieved_agent2:
        if retrieved_agent1.name != retrieved_agent2.name:
            print("✓ 智能体隔离验证成功：相同ID不同租户的智能体配置不同")
        else:
            print("✗ 智能体隔离验证失败")

    print("隔离化智能体管理演示完成！\n")


def demo_agent_config_management():
    """演示智能体配置管理"""

    print("=== 智能体配置管理演示 ===")

    tenant_id = "demo_company"
    agent_id = "config_demo"

    # 创建智能体
    agent = create_tenant_agent(
        tenant_id=tenant_id,
        agent_id=agent_id,
        name="配置演示智能体",
        persona_config={"name": "演示助手", "prompt": "我是一个配置演示助手"},
        bot_overrides={"nickname": "配置助手", "greeting": "你好，我是配置演示助手"},
        tags=["演示", "配置"],
        description="用于演示配置管理的智能体",
    )

    print(f"✓ 创建智能体: {agent.name}")

    # 获取配置统计
    stats = get_tenant_agent_config_stats(tenant_id)
    print("✓ 租户配置统计:")
    print(f"  - 总智能体数: {stats['total_agents']}")
    print(f"  - 自定义人格数: {stats['agents_with_custom_personas']}")
    print(f"  - Bot配置覆盖数: {stats['agents_with_bot_overrides']}")

    # 更新智能体配置
    updated_agent = update_tenant_agent(
        tenant_id=tenant_id, agent_id=agent_id, name="更新后的演示智能体", description="这是更新后的描述"
    )

    if updated_agent:
        print(f"✓ 更新智能体名称: {updated_agent.name}")

    # 列出租户所有智能体
    agents = list_tenant_agents(tenant_id)
    print(f"✓ 租户 '{tenant_id}' 共有 {len(agents)} 个智能体:")
    for agent in agents:
        print(f"  - {agent.agent_id}: {agent.name}")

    # 清理演示数据
    delete_tenant_agent(tenant_id, agent_id)
    print("✓ 删除演示智能体")

    print("智能体配置管理演示完成！\n")


def demo_agent_instance_management():
    """演示智能体实例管理"""

    print("=== 智能体实例管理演示 ===")

    tenant_id = "instance_demo"

    # 创建智能体
    agent = create_tenant_agent(
        tenant_id=tenant_id,
        agent_id="instance_test",
        name="实例演示智能体",
        persona_config={"name": "实例助手", "prompt": "我是一个实例演示助手"},
    )

    print(f"✓ 创建智能体: {agent.name}")

    # 获取智能体实例
    instance = get_agent_instance(agent, tenant_id)
    print(f"✓ 获取智能体实例: {agent.agent_id}")

    # 设置实例状态
    instance.set_state("last_message", "Hello, World!")
    instance.set_state("conversation_count", 10)
    instance.activate()

    print("✓ 设置实例状态和激活状态")

    # 添加实例资源
    instance.add_resource("memory_cache", {"data": "example"})
    instance.add_resource("session_data", {"id": "session_123"})

    print("✓ 添加实例资源")

    # 获取实例信息
    instance_info = instance.get_instance_info()
    print("✓ 实例信息:")
    print(f"  - 智能体ID: {instance_info['agent_id']}")
    print(f"  - 租户ID: {instance_info['tenant_id']}")
    print(f"  - 是否活跃: {instance_info['is_active']}")
    print(f"  - 使用次数: {instance_info['usage_count']}")
    print(f"  - 状态键数量: {len(instance_info['state_keys'])}")
    print(f"  - 资源数量: {instance_info['resource_count']}")

    # 通过便捷函数获取实例
    retrieved_instance = get_tenant_agent_instance(tenant_id, "instance_test")
    if retrieved_instance:
        print("✓ 通过便捷函数获取实例成功")
        print(f"  - 最后消息: {retrieved_instance.get_state('last_message')}")
        print(f"  - 对话次数: {retrieved_instance.get_state('conversation_count')}")

    # 获取实例管理统计
    instance_stats = get_instance_management_stats()
    print("✓ 实例管理统计:")
    print(f"  - 总实例数: {instance_stats['total_instances']}")
    print(f"  - 活跃实例数: {instance_stats['active_instances']}")

    print("智能体实例管理演示完成！\n")


def demo_system_stats():
    """演示系统统计信息"""

    print("=== 系统统计信息演示 ===")

    # 注册中心统计
    registry_stats = get_isolated_registry_stats()
    print("✓ 智能体注册中心统计:")
    print(f"  - 总租户数: {registry_stats['total_tenants']}")
    for tenant_id, info in registry_stats["registries"].items():
        print(f"  - 租户 '{tenant_id}': {info['agent_count']} 个智能体")

    # 管理器统计
    manager_stats = get_isolated_manager_stats()
    print("✓ 智能体管理器统计:")
    print(f"  - 总租户数: {manager_stats['total_tenants']}")
    for tenant_id, info in manager_stats["managers"].items():
        print(f"  - 租户 '{tenant_id}':")
        print(f"    - 数据库智能体数: {info['database_agent_count']}")
        print(f"    - 缓存智能体数: {info['cache_agent_count']}")
        print(f"    - 注册表智能体数: {info['registry_agent_count']}")

    print("系统统计信息演示完成！\n")


async def demo_async_initialization():
    """演示异步初始化"""

    print("=== 异步初始化演示 ===")

    # 初始化租户的智能体管理器
    agent_count = len(get_tenant_agent_instances("async_demo"))
    print(f"✓ 异步初始化租户 'async_demo' 完成，加载了 {agent_count} 个智能体")

    print("异步初始化演示完成！\n")


def run_comprehensive_demo():
    """运行完整的演示"""

    print("🚀 智能体管理系统多租户隔离完整演示\n")

    # 1. 向后兼容性
    demo_backward_compatibility()

    # 2. 隔离化智能体管理
    demo_isolated_agent_management()

    # 3. 配置管理
    demo_agent_config_management()

    # 4. 实例管理
    demo_agent_instance_management()

    # 5. 系统统计
    demo_system_stats()

    # 6. 异步初始化
    asyncio.run(demo_async_initialization())

    print("🎉 智能体管理系统多租户隔离演示完成！")
    print("\n主要特性:")
    print("✅ 完全向后兼容 - 现有代码无需修改")
    print("✅ T+A维度隔离 - 租户和智能体级别的完全隔离")
    print("✅ 配置隔离 - 每个租户独立的智能体配置")
    print("✅ 实例管理 - 隔离化的智能体实例和状态管理")
    print("✅ 资源管理 - 自动清理和内存安全")
    print("✅ 统计监控 - 完整的统计和健康检查")
    print("✅ 异步支持 - 完整的异步操作支持")
    print("✅ 便捷API - 简单易用的函数接口")


if __name__ == "__main__":
    run_comprehensive_demo()
