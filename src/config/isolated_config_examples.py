"""
多租户隔离配置系统使用示例
展示如何使用新的多租户配置系统
"""

import asyncio

from src.isolation.isolation_context import create_isolation_context
from src.config.isolated_config_system import get_isolated_config_system, isolated_config_context, with_isolated_config
from src.config.isolated_config_manager import get_isolated_config_manager
from src.config.isolated_config_tools import migrate_global_to_tenant, validate_tenant_configs

# 配置系统使用示例


def example_basic_usage():
    """基础使用示例"""
    print("=== 基础配置使用示例 ===")

    # 获取配置系统
    config_system = get_isolated_config_system()

    # 获取配置管理器
    config_manager = config_system.get_config_manager("tenant1", "agent1")

    # 设置配置
    config_manager.set_config("bot", "nickname", "智能助手", level="agent")
    config_manager.set_config("personality", "personality", "是一个友好的人工智能助手", level="agent")
    config_manager.set_config("chat", "max_response_length", 500, level="agent")

    # 获取配置
    nickname = config_manager.get_config("bot", "nickname", "默认昵称")
    personality = config_manager.get_config("personality", "personality")
    max_length = config_manager.get_config("chat", "max_response_length", 200)

    print(f"昵称: {nickname}")
    print(f"人格设定: {personality}")
    print(f"最大回复长度: {max_length}")

    # 获取完整配置
    full_config = config_manager.get_effective_config()
    print(f"完整配置分类: {list(full_config.keys())}")


def example_isolation_context():
    """隔离上下文使用示例"""
    print("\n=== 隔离上下文使用示例 ===")

    # 创建隔离上下文
    isolation_context = create_isolation_context(tenant_id="tenant1", agent_id="agent1", platform="qq")

    # 扩展的隔离上下文自动支持配置管理
    if hasattr(isolation_context, "get_config"):
        # 直接从隔离上下文获取配置
        nickname = isolation_context.get_config("bot", "nickname", "默认昵称")
        print(f"从隔离上下文获取昵称: {nickname}")

        # 设置配置
        isolation_context.set_config("bot", "nickname", "QQ智能助手", level="platform")

        # 获取配置上下文
        config_context = isolation_context.get_config_context()
        full_config = config_context.get_effective_config()
        print(f"从配置上下文获取的配置项数量: {len(full_config)}")


def example_config_inheritance():
    """配置继承示例"""
    print("\n=== 配置继承示例 ===")

    # 设置不同级别的配置
    config_system = get_isolated_config_system()

    # 1. 租户级别配置
    config_system.set_config("bot", "nickname", "通用助手", tenant_id="tenant1", level="tenant")
    config_system.set_config("chat", "max_response_length", 300, tenant_id="tenant1", level="tenant")

    # 2. 智能体级别配置（覆盖租户配置）
    config_system.set_config("bot", "nickname", "客服助手", tenant_id="tenant1", agent_id="agent1", level="agent")

    # 3. 平台级别配置（覆盖智能体配置）
    config_system.set_config(
        "bot", "nickname", "QQ客服助手", tenant_id="tenant1", agent_id="agent1", level="platform", platform="qq"
    )

    # 查看继承效果
    config_manager = config_system.get_config_manager("tenant1", "agent1")

    # 获取不同平台下的配置
    qq_nickname = config_manager.get_config("bot", "nickname", platform="qq")
    wx_nickname = config_manager.get_config("bot", "nickname", platform="wx")
    max_length = config_manager.get_config("chat", "max_response_length")  # 继承自租户配置

    print(f"QQ平台昵称: {qq_nickname}")
    print(f"微信平台昵称: {wx_nickname or '使用默认'}")
    print(f"最大回复长度: {max_length}")

    # 查看配置来源
    effective_config = config_manager.get_effective_config("qq")
    print(f"QQ平台有效配置: {effective_config.get('bot', {})}")


def example_context_manager():
    """上下文管理器使用示例"""
    print("\n=== 上下文管理器使用示例 ===")

    # 使用上下文管理器
    with isolated_config_context("tenant1", "agent1", "qq") as config_manager:
        # 在这个上下文中使用配置管理器
        config_manager.set_config("bot", "status", "在线", level="platform", platform="qq")
        status = config_manager.get_config("bot", "status")
        print(f"状态: {status}")

    # 上下文结束后，配置管理器仍然缓存着


def example_decorators():
    """装饰器使用示例"""
    print("\n=== 装饰器使用示例 ===")

    @with_isolated_config(tenant_id="tenant1", agent_id="agent1")
    def process_with_config(config_manager, message: str):
        """使用配置管理器的函数"""
        max_length = config_manager.get_config("chat", "max_response_length", 100)
        nickname = config_manager.get_config("bot", "nickname", "助手")

        # 处理消息逻辑
        response = f"{nickname}说：{message[:max_length]}"
        return response

    # 调用函数
    result = process_with_config("这是一个很长的消息，应该被截断")
    print(f"处理结果: {result}")


def example_config_migration():
    """配置迁移示例"""
    print("\n=== 配置迁移示例 ===")

    # 从全局配置迁移到租户配置
    migration_result = migrate_global_to_tenant("tenant2", "agent2", overwrite=False)
    print(f"迁移结果: {migration_result}")

    # 验证迁移后的配置
    validation_result = validate_tenant_configs("tenant2", "agent2")
    print(f"配置验证结果: {'有效' if validation_result['valid'] else '无效'}")
    if not validation_result["valid"]:
        print(f"缺失配置: {validation_result['missing_configs']}")


def example_config_export_import():
    """配置导出导入示例"""
    print("\n=== 配置导出导入示例 ===")

    config_system = get_isolated_config_system()

    # 设置一些测试配置
    config_system.set_config("bot", "nickname", "测试助手", tenant_id="tenant3", agent_id="agent1")
    config_system.set_config(
        "personality", "personality", "是一个测试用的智能体", tenant_id="tenant3", agent_id="agent1"
    )

    # 导出配置
    export_data = config_system.export_configs("tenant3", "agent1")
    print(f"导出的配置项: {list(export_data['configs']['agent1'].keys())}")

    # 导入到另一个租户
    import_result = config_system.import_configs(export_data, "tenant4", overwrite=False)
    print(f"导入结果: {import_result}")


def example_config_validation():
    """配置验证示例"""
    print("\n=== 配置验证示例 ===")

    config_system = get_isolated_config_system()

    # 设置完整配置
    config_system.set_config("bot", "platform", "qq", tenant_id="tenant5", agent_id="agent1")
    config_system.set_config("bot", "nickname", "完整配置助手", tenant_id="tenant5", agent_id="agent1")
    config_system.set_config(
        "personality", "personality", "这是一个配置完整的智能体", tenant_id="tenant5", agent_id="agent1"
    )

    # 验证配置
    validation_result = config_system.validate_configs("tenant5", "agent1")
    print(f"配置验证: {'通过' if validation_result['valid'] else '失败'}")

    if validation_result["errors"]:
        print(f"错误: {validation_result['errors']}")

    if validation_result["warnings"]:
        print(f"警告: {validation_result['warnings']}")


def example_config_history():
    """配置历史记录示例"""
    print("\n=== 配置历史记录示例 ===")

    config_manager = get_isolated_config_manager("tenant1", "agent1")

    # 修改配置（这会记录到历史）
    config_manager.set_config("bot", "nickname", "历史测试助手1", level="agent")
    config_manager.set_config("bot", "nickname", "历史测试助手2", level="agent")
    config_manager.set_config("bot", "nickname", "历史测试助手3", level="agent")

    # 查看配置历史
    history = config_manager.get_config_history("bot", "nickname", limit=5)
    print(f"配置变更历史记录数: {len(history)}")

    for i, record in enumerate(history):
        print(
            f"{i + 1}. {record['operated_at']}: {record['old_value']} -> {record['new_value']} ({record['change_type']})"
        )


def example_performance_monitoring():
    """性能监控示例"""
    print("\n=== 性能监控示例 ===")

    config_system = get_isolated_config_system()

    # 获取配置统计信息
    stats = config_system.get_statistics()
    print(f"配置统计: {stats}")

    # 查看缓存使用情况
    config_system.get_config_manager("tenant1", "agent1")
    print("缓存管理器已创建")


def example_platform_specific_configs():
    """平台特定配置示例"""
    print("\n=== 平台特定配置示例 ===")

    config_system = get_isolated_config_system()

    # 为不同平台设置不同配置
    platforms = ["qq", "wx", "discord"]

    for platform in platforms:
        config_system.set_config(
            "bot",
            "greeting",
            f"你好，我是{platform}平台的助手！",
            tenant_id="tenant1",
            agent_id="agent1",
            level="platform",
            platform=platform,
        )
        config_system.set_config(
            "chat",
            "response_style",
            f"{platform}风格回复",
            tenant_id="tenant1",
            agent_id="agent1",
            level="platform",
            platform=platform,
        )

    # 测试不同平台的配置获取
    config_manager = config_system.get_config_manager("tenant1", "agent1")

    for platform in platforms:
        greeting = config_manager.get_config("bot", "greeting", platform=platform)
        style = config_manager.get_config("chat", "response_style", platform=platform)
        print(f"{platform}平台 - 问候语: {greeting}, 回复风格: {style}")


async def example_async_usage():
    """异步使用示例"""
    print("\n=== 异步使用示例 ===")

    config_system = get_isolated_config_system()

    @config_system.async_with_isolated_config(tenant_id="tenant1", agent_id="agent1")
    async def async_process_with_config(config_manager):
        """异步处理配置"""
        # 模拟异步操作
        await asyncio.sleep(0.1)

        # 获取配置
        nickname = config_manager.get_config("bot", "nickname", "异步助手")
        return f"异步处理的{nickname}"

    # 调用异步函数
    result = await async_process_with_config()
    print(f"异步处理结果: {result}")


def run_all_examples():
    """运行所有示例"""
    print("多租户隔离配置系统使用示例\n")

    try:
        example_basic_usage()
        example_isolation_context()
        example_config_inheritance()
        example_context_manager()
        example_decorators()
        example_config_migration()
        example_config_export_import()
        example_config_validation()
        example_config_history()
        example_performance_monitoring()
        example_platform_specific_configs()

        # 异步示例
        asyncio.run(example_async_usage())

        print("\n=== 所有示例运行完成 ===")

    except Exception as e:
        print(f"示例运行出错: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    run_all_examples()
