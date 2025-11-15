"""
隔离化心流处理系统使用示例
演示如何使用多租户隔离的心流处理功能
"""

import asyncio
import logging

from src.chat.heart_flow.heartflow_message_processor import (
    IsolatedHeartFCMessageReceiver,
    get_isolated_heartfc_receiver,
)
from src.chat.heart_flow.isolated_heartflow import get_isolated_heartflow, get_isolated_heartflow_stats
from src.chat.heart_flow.isolated_heartFC_chat import IsolatedHeartFChatting
from src.isolation.isolation_context import create_isolation_context, get_isolation_context_manager

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class IsolatedHeartFlowExample:
    """隔离化心流处理系统示例"""

    def __init__(self):
        self.tenant_id = "example_tenant"
        self.agent_id = "example_agent"
        self.platform = "example_platform"

    async def example_basic_usage(self):
        """基础使用示例"""
        logger.info("=== 基础使用示例 ===")

        # 1. 创建隔离上下文
        isolation_context = create_isolation_context(
            tenant_id=self.tenant_id, agent_id=self.agent_id, platform=self.platform
        )
        logger.info(f"创建隔离上下文: {isolation_context.scope}")

        # 2. 获取隔离化的心流处理器
        receiver = get_isolated_heartfc_receiver(self.tenant_id, self.agent_id)
        logger.info(f"获取隔离心流处理器: {receiver.get_isolation_info()}")

        # 3. 获取隔离化的心流管理器
        heartflow = get_isolated_heartflow(self.tenant_id, self.agent_id)
        logger.info(f"获取隔离心流管理器: {heartflow.get_isolation_info()}")

        # 4. 处理消息（模拟）
        await self._simulate_message_processing(receiver)

        # 5. 健康检查
        health_info = await heartflow.health_check()
        logger.info(f"心流健康检查: {health_info}")

    async def example_multi_tenant_isolation(self):
        """多租户隔离示例"""
        logger.info("=== 多租户隔离示例 ===")

        # 创建多个租户的心流处理器
        tenants = ["tenant1", "tenant2"]
        agents = ["agent1", "agent2"]

        for tenant_id in tenants:
            for agent_id in agents:
                receiver = get_isolated_heartfc_receiver(tenant_id, agent_id)
                get_isolated_heartflow(tenant_id, agent_id)

                isolation_info = receiver.get_isolation_info()
                logger.info(f"租户 {tenant_id} 智能体 {agent_id}: {isolation_info}")

        # 获取全局统计
        stats = get_isolated_heartflow_stats()
        logger.info(f"全局统计: {stats}")

    async def example_isolation_context_management(self):
        """隔离上下文管理示例"""
        logger.info("=== 隔离上下文管理示例 ===")

        context_manager = get_isolation_context_manager()

        # 创建多个上下文
        contexts = []
        for i in range(3):
            context = context_manager.create_context(
                tenant_id=f"tenant{i}", agent_id=f"agent{i}", platform=f"platform{i}"
            )
            contexts.append(context)
            logger.info(f"创建上下文 {i}: {context.scope}")

        # 检查活跃上下文数量
        active_count = context_manager.get_active_context_count()
        logger.info(f"活跃上下文数量: {active_count}")

        # 清理特定租户的上下文
        context_manager.clear_tenant_contexts("tenant1")
        logger.info("清理租户 tenant1 的上下文")

        # 再次检查活跃上下文数量
        active_count = context_manager.get_active_context_count()
        logger.info(f"清理后活跃上下文数量: {active_count}")

    async def example_chat_stream_isolation(self):
        """聊天流隔离示例"""
        logger.info("=== 聊天流隔离示例 ===")

        # 创建隔离化的心流聊天
        isolation_context = create_isolation_context(
            tenant_id=self.tenant_id, agent_id=self.agent_id, platform=self.platform, chat_stream_id="chat123"
        )

        # 注意：这需要真实的聊天流数据，这里只是演示接口
        try:
            # 这里会因为找不到聊天流而失败，这是正常的
            chat = IsolatedHeartFChatting(chat_id="chat123", isolation_context=isolation_context)
            logger.info(f"创建隔离心流聊天: {chat.get_isolation_info()}")
        except Exception as e:
            logger.info(f"预期错误（需要真实聊天流数据）: {e}")

    async def example_configuration_isolation(self):
        """配置隔离示例"""
        logger.info("=== 配置隔离示例 ===")

        isolation_context = create_isolation_context(
            tenant_id=self.tenant_id, agent_id=self.agent_id, platform=self.platform
        )

        # 获取隔离配置（如果实现了的话）
        try:
            isolation_context.get_config_manager()
            logger.info("获取隔离配置管理器成功")
        except NotImplementedError:
            logger.info("隔离配置管理器尚未实现（这是正常的）")

        # 获取隔离记忆系统（如果实现了的话）
        try:
            isolation_context.get_memory_chest()
            logger.info("获取隔离记忆系统成功")
        except NotImplementedError:
            logger.info("隔离记忆系统尚未实现（这是正常的）")

    async def _simulate_message_processing(self, receiver: IsolatedHeartFCMessageReceiver):
        """模拟消息处理"""
        logger.info("模拟消息处理...")

        # 这里应该创建真实的MessageRecv对象
        # 为了演示，我们只记录日志
        logger.info("注意：真实消息处理需要有效的MessageRecv对象")
        logger.info(f"处理器隔离信息: {receiver.get_isolation_info()}")

    async def example_cleanup_and_resource_management(self):
        """清理和资源管理示例"""
        logger.info("=== 清理和资源管理示例 ===")

        # 创建一些心流实例
        for i in range(3):
            get_isolated_heartfc_receiver(f"tenant{i}", f"agent{i}")
            get_isolated_heartflow(f"tenant{i}", f"agent{i}")
            logger.info(f"创建心流实例 {i}")

        # 获取创建前的统计
        stats_before = get_isolated_heartflow_stats()
        logger.info(f"清理前统计: {stats_before}")

        # 清理特定租户
        from src.chat.heart_flow.heartflow_message_processor import clear_isolated_heartfc_receivers
        from src.chat.heart_flow.isolated_heartflow import clear_isolated_heartflows

        clear_isolated_heartfc_receivers("tenant1")
        clear_isolated_heartflows("tenant1")
        logger.info("清理租户 tenant1 的资源")

        # 清理所有资源
        clear_isolated_heartfc_receivers()
        clear_isolated_heartflows()
        logger.info("清理所有资源")

        # 获取清理后的统计
        stats_after = get_isolated_heartflow_stats()
        logger.info(f"清理后统计: {stats_after}")

    async def run_all_examples(self):
        """运行所有示例"""
        logger.info("开始运行隔离化心流处理系统示例")

        try:
            await self.example_basic_usage()
            await asyncio.sleep(0.5)

            await self.example_multi_tenant_isolation()
            await asyncio.sleep(0.5)

            await self.example_isolation_context_management()
            await asyncio.sleep(0.5)

            await self.example_chat_stream_isolation()
            await asyncio.sleep(0.5)

            await self.example_configuration_isolation()
            await asyncio.sleep(0.5)

            await self.example_cleanup_and_resource_management()

            logger.info("所有示例运行完成")

        except Exception as e:
            logger.error(f"运行示例时出错: {e}")
            import traceback

            traceback.print_exc()


async def main():
    """主函数"""
    example = IsolatedHeartFlowExample()
    await example.run_all_examples()


if __name__ == "__main__":
    asyncio.run(main())
