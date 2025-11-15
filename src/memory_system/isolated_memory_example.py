# -*- coding: utf-8 -*-
"""
隔离化记忆系统使用示例
演示T+A+P+C四维隔离的记忆管理功能
"""

import asyncio

from src.memory_system.isolated_memory_api import (
    MemorySystemConfig,
    create_isolated_memory_system,
    process_isolated_memory,
    search_isolated_memory,
    query_isolated_memories,
    track_isolated_conflict,
    get_isolation_stats,
    cleanup_tenant_resources,
    get_tenant_memory_info,
    system_health_check,
    cleanup_all_expired_memories,
)
from src.common.logger import get_logger

logger = get_logger("isolated_memory_example")


async def example_basic_usage():
    """基础使用示例"""
    print("\n=== 基础使用示例 ===")

    # 1. 创建隔离化记忆系统
    memory_system = await create_isolated_memory_system(tenant_id="tenant1", agent_id="agent1", platform="qq")

    # 2. 添加不同级别的记忆
    await memory_system.add_memory(
        title="Python基础语法", content="Python是一种解释型、面向对象的高级编程语言", level="agent"
    )

    await memory_system.add_memory(
        title="QQ群聊天规则", content="在QQ群中请遵守群规，不要发送广告信息", level="platform", scope_id="qq"
    )

    await memory_system.add_memory(
        title="群成员张三的喜好",
        content="张三喜欢编程和音乐，特别是Python和古典音乐",
        level="chat",
        scope_id="chat_12345",
    )

    # 3. 查询不同级别的记忆
    print("智能体级别记忆:")
    agent_memories = memory_system.query_memories(level="agent")
    for memory in agent_memories:
        print(f"  - {memory['title']}: {memory['content'][:50]}...")

    print("\n平台级别记忆:")
    platform_memories = memory_system.query_memories(level="platform", scope_id="qq")
    for memory in platform_memories:
        print(f"  - {memory['title']}: {memory['content'][:50]}...")

    print("\n聊天流级别记忆:")
    chat_memories = memory_system.query_memories(level="chat", scope_id="chat_12345")
    for memory in chat_memories:
        print(f"  - {memory['title']}: {memory['content'][:50]}...")

    # 4. 搜索记忆
    answer = await memory_system.search_memories("Python是什么？")
    print(f"\n搜索答案: {answer}")


async def example_multi_tenant():
    """多租户隔离示例"""
    print("\n=== 多租户隔离示例 ===")

    # 创建不同租户的记忆系统
    tenant1_system = await create_isolated_memory_system("tenant1", "agent1", "qq")
    tenant2_system = await create_isolated_memory_system("tenant2", "agent1", "qq")

    # 添加相同标题的记忆
    await tenant1_system.add_memory("公司机密", "tenant1的机密信息", level="agent")
    await tenant2_system.add_memory("公司机密", "tenant2的机密信息", level="agent")

    # 验证隔离效果
    t1_memories = tenant1_system.query_memories(level="agent")
    t2_memories = tenant2_system.query_memories(level="agent")

    print(f"Tenant1记忆数量: {len(t1_memories)}")
    print(f"Tenant2记忆数量: {len(t2_memories)}")

    # 验证内容隔离
    t1_content = [m["content"] for m in t1_memories if m["title"] == "公司机密"]
    t2_content = [m["content"] for m in t2_memories if m["title"] == "公司机密"]

    print(f"Tenant1机密内容: {t1_content}")
    print(f"Tenant2机密内容: {t2_content}")
    print(f"内容隔离成功: {len(set(t1_content) & set(t2_content)) == 0}")


async def example_memory_aggregation():
    """记忆聚合示例"""
    print("\n=== 记忆聚合示例 ===")

    memory_system = await create_isolated_memory_system("tenant1", "agent1", "qq")

    # 添加多个聊天流级别的记忆
    await memory_system.add_memory("群聊A的用户爱好", "群聊A的用户喜欢游戏和动漫", level="chat", scope_id="chat_a")
    await memory_system.add_memory("群聊B的用户爱好", "群聊B的用户喜欢阅读和旅游", level="chat", scope_id="chat_b")
    await memory_system.add_memory("群聊C的用户爱好", "群聊C的用户喜欢音乐和电影", level="chat", scope_id="chat_c")

    print("聚合前的聊天流记忆:")
    chat_memories = memory_system.query_memories(level="chat", limit=10)
    for memory in chat_memories:
        print(f"  - {memory['chat_stream_id']}: {memory['title']}")

    # 聚合到平台级别
    success = await memory_system.aggregate_memories(
        from_levels=["chat"], to_level="platform", scope_ids=["chat_a", "chat_b", "chat_c"]
    )

    if success:
        print("\n聚合后的平台记忆:")
        platform_memories = memory_system.query_memories(level="platform", scope_id="qq")
        for memory in platform_memories:
            print(f"  - {memory['title']}: {memory['content'][:100]}...")


async def example_conflict_tracking():
    """冲突跟踪示例"""
    print("\n=== 冲突跟踪示例 ===")

    memory_system = await create_isolated_memory_system("tenant1", "agent1", "qq")

    # 跟踪一些可能有冲突的问题
    await memory_system.track_conflict(
        question="Python的最佳IDE是什么？",
        chat_id="chat_development",
        context="关于开发工具选择的讨论",
        start_following=False,  # 示例中不启动实际跟踪
    )

    await memory_system.track_conflict(
        question="前端开发应该学React还是Vue？",
        chat_id="chat_frontend",
        context="前端框架选择的争议",
        start_following=False,
    )

    # 获取统计信息
    stats = memory_system.get_statistics()
    print("冲突统计信息:")
    print(f"  - 总冲突数: {stats['conflict_stats']['total_conflicts']}")
    print(f"  - 未解答冲突: {stats['conflict_stats']['unanswered_conflicts']}")
    print(f"  - 活跃跟踪器: {stats['conflict_stats']['active_trackers']}")


async def example_convenient_apis():
    """便捷API使用示例"""
    print("\n=== 便捷API使用示例 ===")

    # 1. 便捷的记忆处理
    memory_id = await process_isolated_memory(
        title="机器学习基础",
        content="机器学习是人工智能的一个分支，通过算法让计算机从数据中学习",
        tenant_id="tenant1",
        agent_id="agent1",
        level="agent",
    )
    print(f"添加记忆ID: {memory_id}")

    # 2. 便捷的记忆搜索
    answer = await search_isolated_memory(question="什么是机器学习？", tenant_id="tenant1", agent_id="agent1")
    print(f"搜索答案: {answer}")

    # 3. 便捷的记忆查询
    memories = query_isolated_memories(tenant_id="tenant1", agent_id="agent1", level="agent", limit=5)
    print(f"查询到 {len(memories)} 条记忆")

    # 4. 便捷的冲突跟踪
    track_success = await track_isolated_conflict(
        question="深度学习和机器学习的区别是什么？", tenant_id="tenant1", agent_id="agent1", context="AI概念辨析讨论"
    )
    print(f"冲突跟踪状态: {'成功' if track_success else '失败'}")


async def example_system_management():
    """系统管理示例"""
    print("\n=== 系统管理示例 ===")

    # 1. 获取租户记忆信息
    tenant_info = get_tenant_memory_info("tenant1", "agent1")
    print("租户记忆信息:")
    print(f"  - 隔离范围: {tenant_info.get('isolation_info', {}).get('memory_scope', 'Unknown')}")
    print(f"  - 总记忆数: {tenant_info.get('memory_statistics', {}).get('total_count', 0)}")
    print(f"  - 冲突数: {tenant_info.get('conflict_statistics', {}).get('total_conflicts', 0)}")

    # 2. 系统健康检查
    health_status = await system_health_check()
    print(f"\n系统健康状态: {health_status['overall_health']}")
    print(f"  - 记忆系统: {health_status['memory_system']['status']}")
    print(f"  - 冲突系统: {health_status['conflict_system']['status']}")

    if health_status["recommendations"]:
        print("  - 建议:")
        for rec in health_status["recommendations"]:
            print(f"    * {rec}")

    # 3. 获取全局统计信息
    global_stats = get_isolation_stats("tenant1", "agent1")
    print("\n全局统计:")
    print(f"  - 活跃记忆实例: {global_stats['memory_system']['active_instances']}")
    print(f"  - 活跃冲突跟踪器: {global_stats['conflict_system']['active_instances']}")


async def example_advanced_configuration():
    """高级配置示例"""
    print("\n=== 高级配置示例 ===")

    # 自定义配置
    config = MemorySystemConfig(
        enable_aggregation=True,
        enable_conflict_tracking=True,
        cache_ttl=600,  # 10分钟缓存
        max_memories_per_level=500,
        auto_cleanup_days=7,  # 7天后自动清理
    )

    memory_system = await create_isolated_memory_system(
        tenant_id="tenant_advanced", agent_id="agent_advanced", platform="discord", config=config
    )

    # 添加一些测试记忆
    await memory_system.add_memory("测试记忆1", "这是测试记忆1", level="agent")
    await memory_system.add_memory("测试记忆2", "这是测试记忆2", level="agent")

    # 获取配置信息
    stats = memory_system.get_statistics()
    print("高级配置信息:")
    config_info = stats["config"]
    for key, value in config_info.items():
        print(f"  - {key}: {value}")


async def example_cleanup_maintenance():
    """清理和维护示例"""
    print("\n=== 清理和维护示例 ===")

    # 创建一些测试数据
    memory_system = await create_isolated_memory_system("tenant_cleanup", "agent_cleanup")
    await memory_system.add_memory("临时记忆", "这是一个临时记忆", level="agent")

    # 清理过期记忆（如果有）
    cleaned_count = await memory_system.cleanup_expired_memories(max_age_days=0)  # 清理所有记忆
    print(f"清理了 {cleaned_count} 条过期记忆")

    # 全局清理
    cleanup_result = await cleanup_all_expired_memories(max_age_days=0)
    print(f"全局清理结果: 总共清理 {cleanup_result['total_cleaned']} 条记忆")

    # 清理租户资源
    cleanup_success = cleanup_tenant_resources("tenant_cleanup")
    print(f"租户资源清理: {'成功' if cleanup_success else '失败'}")


async def run_all_examples():
    """运行所有示例"""
    print("开始运行隔离化记忆系统示例...")

    try:
        await example_basic_usage()
        await example_multi_tenant()
        await example_memory_aggregation()
        await example_conflict_tracking()
        await example_convenient_apis()
        await example_system_management()
        await example_advanced_configuration()
        await example_cleanup_maintenance()

        print("\n✅ 所有示例运行完成！")

    except Exception as e:
        logger.error(f"运行示例时出错: {e}")
        print(f"\n❌ 示例运行出错: {e}")


if __name__ == "__main__":
    # 运行示例
    asyncio.run(run_all_examples())
