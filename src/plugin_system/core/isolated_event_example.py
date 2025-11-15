"""
隔离化事件系统使用示例
展示如何使用新的多租户隔离事件系统
"""

import asyncio
from datetime import datetime

from src.common.logger import get_logger
from src.isolation.isolation_context import create_isolation_context
from src.plugin_system.core.event_types import EventPriority
from src.plugin_system.core.isolated_event import IsolatedEvent
from src.plugin_system.core.isolated_event_api import (
    publish_isolated_event,
    subscribe_to_events,
    get_event_history,
    get_event_statistics,
    event_handler,
    message_event_handler,
    cleanup_events,
    get_system_health,
)
from src.plugin_system.core.event_result import create_event_result, store_event_result, ResultStatus
from src.plugin_system.core.events_compatibility import (
    migrate_to_isolated_events,
    check_migration_status,
    MigrationHelper,
)

logger = get_logger("isolated_event_example")


class EventSystemExamples:
    """事件系统使用示例"""

    def __init__(self):
        self.tenant_id = "example_tenant"
        self.agent_id = "example_agent"
        self.platform = "qq"

    async def basic_event_publishing(self):
        """基础事件发布示例"""
        print("\n=== 基础事件发布示例 ===")

        try:
            # 发布简单事件
            success = await publish_isolated_event(
                event_type=IsolatedEventType.ON_ISOLATED_MESSAGE,
                data={"message": "Hello World", "user": "test_user"},
                tenant_id=self.tenant_id,
                agent_id=self.agent_id,
                platform=self.platform,
            )

            print(f"事件发布结果: {'成功' if success else '失败'}")

            # 发布带优先级的事件
            success = await publish_isolated_event(
                event_type=IsolatedEventType.ON_AGENT_CONFIG_CHANGE,
                data={"config_key": "personality", "old_value": "friendly", "new_value": "professional"},
                tenant_id=self.tenant_id,
                agent_id=self.agent_id,
                priority=EventPriority.HIGH,
            )

            print(f"高优先级事件发布结果: {'成功' if success else '失败'}")

        except Exception as e:
            print(f"基础事件发布失败: {e}")

    async def event_subscription_example(self):
        """事件订阅示例"""
        print("\n=== 事件订阅示例 ===")

        try:
            # 定义事件处理器
            async def message_handler(event: IsolatedEvent):
                print(f"收到消息事件: {event.data.get('message', '')}")
                print(f"事件来自租户: {event.isolation_context.tenant_id}")

            async def config_handler(event: IsolatedEvent):
                print(f"收到配置变更事件: {event.data}")
                print(f"变更时间: {datetime.fromtimestamp(event.timestamp)}")

            # 订阅消息事件
            subscription_id1 = subscribe_to_events(
                event_types=[IsolatedEventType.ON_ISOLATED_MESSAGE],
                handler=message_handler,
                tenant_id=self.tenant_id,
                agent_id=self.agent_id,
                platform=self.platform,
            )

            print(f"消息事件订阅ID: {subscription_id1}")

            # 订阅配置变更事件
            subscription_id2 = subscribe_to_events(
                event_types=[IsolatedEventType.ON_AGENT_CONFIG_CHANGE],
                handler=config_handler,
                tenant_id=self.tenant_id,
                agent_id=self.agent_id,
                filters={"priority": "high"},
            )

            print(f"配置事件订阅ID: {subscription_id2}")

            # 发布测试事件
            await publish_isolated_event(
                event_type=IsolatedEventType.ON_ISOLATED_MESSAGE,
                data={"message": "测试消息"},
                tenant_id=self.tenant_id,
                agent_id=self.agent_id,
                platform=self.platform,
            )

            await asyncio.sleep(0.1)  # 等待事件处理

        except Exception as e:
            print(f"事件订阅示例失败: {e}")

    def decorator_example(self):
        """装饰器示例"""
        print("\n=== 装饰器示例 ===")

        try:
            # 使用装饰器定义事件处理器
            @event_handler(
                event_types=[IsolatedEventType.ON_PLATFORM_CONNECTED], tenant_id=self.tenant_id, agent_id=self.agent_id
            )
            async def platform_connected_handler(event: IsolatedEvent):
                print(f"平台连接事件: {event.data.get('platform', 'unknown')}")
                return "平台连接处理完成"

            @message_event_handler(tenant_id=self.tenant_id, agent_id=self.agent_id, platform=self.platform)
            async def message_handler(event: IsolatedEvent):
                message = event.data.get("message", "")
                print(f"收到消息: {message}")
                return f"消息已处理: {message}"

            print("装饰器事件处理器已定义")
            print(f"消息处理器订阅ID: {message_handler._subscription_id}")
            print(f"平台连接处理器订阅ID: {platform_connected_handler._subscription_id}")

        except Exception as e:
            print(f"装饰器示例失败: {e}")

    async def event_history_query(self):
        """事件历史查询示例"""
        print("\n=== 事件历史查询示例 ===")

        try:
            # 发布一些测试事件
            for i in range(5):
                await publish_isolated_event(
                    event_type=IsolatedEventType.ON_ISOLATED_MESSAGE,
                    data={"message": f"测试消息 {i + 1}", "sequence": i + 1},
                    tenant_id=self.tenant_id,
                    agent_id=self.agent_id,
                    platform=self.platform,
                )

            # 查询事件历史
            history = get_event_history(
                tenant_id=self.tenant_id, agent_id=self.agent_id, platform=self.platform, limit=10, hours=1
            )

            print(f"查询到 {len(history)} 个历史事件:")
            for i, event in enumerate(history[:3]):  # 只显示前3个
                print(f"  {i + 1}. 事件类型: {event['event_type']}")
                print(f"     时间: {event['timestamp']}")
                print(f"     数据: {event['data']}")

        except Exception as e:
            print(f"事件历史查询失败: {e}")

    async def event_statistics(self):
        """事件统计示例"""
        print("\n=== 事件统计示例 ===")

        try:
            # 获取事件统计
            stats = get_event_statistics(tenant_id=self.tenant_id, agent_id=self.agent_id, platform=self.platform)

            print("事件统计信息:")
            print(f"  总结果数: {stats.get('total_results', 0)}")
            print(f"  按状态分布: {stats.get('by_status', {})}")
            print(f"  按事件类型分布: {stats.get('by_event_type', {})}")

        except Exception as e:
            print(f"事件统计失败: {e}")

    async def event_result_storage(self):
        """事件结果存储示例"""
        print("\n=== 事件结果存储示例 ===")

        try:
            # 创建事件结果
            result1 = create_event_result(
                event_type=IsolatedEventType.ON_ISOLATED_MESSAGE.value,
                event_id="test_event_1",
                isolation_context=create_isolation_context(
                    tenant_id=self.tenant_id, agent_id=self.agent_id, platform=self.platform
                ),
                status=ResultStatus.SUCCESS,
                result_data={"processed": True, "response": "消息已处理"},
                processor_name="test_processor",
                execution_time=0.05,
            )

            result1.add_tag("test")
            result1.add_tag("example")

            # 存储事件结果
            success = store_event_result(result1)
            print(f"事件结果存储: {'成功' if success else '失败'}")

            # 创建失败结果
            result2 = create_event_result(
                event_type=IsolatedEventType.ON_AGENT_CONFIG_CHANGE.value,
                event_id="test_event_2",
                isolation_context=create_isolation_context(tenant_id=self.tenant_id, agent_id=self.agent_id),
                status=ResultStatus.FAILURE,
                error_message="配置验证失败",
                processor_name="config_processor",
            )

            store_event_result(result2)
            print("已存储失败的事件结果")

            # 查询结果
            from src.plugin_system.core.event_result import get_event_results

            results = get_event_results(
                isolation_context=create_isolation_context(tenant_id=self.tenant_id, agent_id=self.agent_id), limit=10
            )

            print(f"查询到 {len(results)} 个事件结果:")
            for result in results:
                print(f"  - 事件: {result.event_type}, 状态: {result.status.value}")

        except Exception as e:
            print(f"事件结果存储示例失败: {e}")

    async def system_health_check(self):
        """系统健康检查示例"""
        print("\n=== 系统健康检查示例 ===")

        try:
            # 获取系统健康状态
            health = get_system_health()

            print("系统健康状态:")
            print(f"  状态: {health['status']}")
            print(f"  检查时间: {health['timestamp']}")
            print(f"  管理器数量: {len(health.get('managers', {}))}")
            print(f"  总事件数: {health.get('total_events', 0)}")

            # 执行健康检查
            from src.plugin_system.core.isolated_event_api import health_check

            is_healthy = await health_check()
            print(f"系统健康: {'是' if is_healthy else '否'}")

        except Exception as e:
            print(f"系统健康检查失败: {e}")

    async def migration_example(self):
        """迁移示例"""
        print("\n=== 迁移示例 ===")

        try:
            # 检查当前迁移状态
            status = check_migration_status()
            print("当前迁移状态:")
            for key, value in status.items():
                print(f"  {key}: {value}")

            # 执行迁移
            success = migrate_to_isolated_events(tenant_id=self.tenant_id, agent_id=self.agent_id)
            print(f"迁移执行: {'成功' if success else '失败'}")

            # 测试隔离化系统
            helper = MigrationHelper()
            test_result = await helper.test_isolated_events(self.tenant_id, self.agent_id)
            print(f"隔离化系统测试: {'通过' if test_result else '失败'}")

            # 获取迁移建议
            recommendations = helper.get_migration_recommendations()
            print("迁移建议:")
            for rec in recommendations:
                print(f"  - {rec}")

        except Exception as e:
            print(f"迁移示例失败: {e}")

    async def cleanup_example(self):
        """清理示例"""
        print("\n=== 清理示例 ===")

        try:
            # 清理旧事件
            cleaned_count = await cleanup_events(tenant_id=self.tenant_id, agent_id=self.agent_id, older_than_hours=1)
            print(f"清理了 {cleaned_count} 个旧事件")

        except Exception as e:
            print(f"清理示例失败: {e}")

    async def run_all_examples(self):
        """运行所有示例"""
        print("开始运行隔离化事件系统示例...")

        await self.basic_event_publishing()
        await self.event_subscription_example()
        self.decorator_example()
        await self.event_history_query()
        await self.event_statistics()
        await self.event_result_storage()
        await self.system_health_check()
        await self.migration_example()
        await self.cleanup_example()

        print("\n所有示例运行完成!")


async def main():
    """主函数"""
    examples = EventSystemExamples()
    await examples.run_all_examples()


if __name__ == "__main__":
    # 运行示例
    asyncio.run(main())
