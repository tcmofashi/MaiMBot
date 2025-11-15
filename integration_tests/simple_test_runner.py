"""
简化的集成测试运行器
专注于核心功能测试
"""

import asyncio
import logging
from typing import Dict

from .api_client import create_test_scenario
from .simple_websocket_test import run_simple_websocket_tests
from .cleanup_test import TestDataCleaner

logger = logging.getLogger(__name__)


class SimpleIntegrationTestRunner:
    """简化的集成测试运行器"""

    def __init__(self):
        self.api_client = None
        self.cleaner = TestDataCleaner()

    async def run_simple_integration_test(
        self, user_count: int = 2, agents_per_user: int = 2, cleanup_after: bool = True
    ) -> Dict:
        """运行简化的集成测试"""
        logger.info("=" * 60)
        logger.info("开始简化集成测试")
        logger.info(f"测试参数: {user_count} 用户, 每用户 {agents_per_user} Agent")
        logger.info("=" * 60)

        result = {
            "success": False,
            "user_count": user_count,
            "agents_per_user": agents_per_user,
            "test_stages": {},
            "errors": [],
            "final_summary": {},
        }

        users = []
        all_agents = []

        try:
            # 阶段1: 创建测试用户和Agent
            logger.info("📝 阶段1: 创建测试用户和Agent")
            manager = await create_test_scenario(
                config_api_url="http://localhost:18000", user_count=user_count, agents_per_user=agents_per_user
            )
            users = manager.users
            all_agents = manager.agents

            result["test_stages"]["user_creation"] = {
                "success": True,
                "users_created": len(users),
                "agents_created": len(all_agents),
            }

            logger.info(f"✅ 创建了 {len(users)} 个用户和 {len(all_agents)} 个Agent")

            # 阶段2: WebSocket连接测试
            logger.info("🔌 阶段2: WebSocket连接和对话测试")
            websocket_results = await run_simple_websocket_tests(users, all_agents)

            result["test_stages"]["websocket_test"] = websocket_results

            if websocket_results["successful_connections"] > 0:
                logger.info(
                    f"✅ WebSocket测试完成: {websocket_results['successful_connections']}/{websocket_results['total_connections']} 连接成功"
                )
                logger.info(
                    f"📨 消息统计: {websocket_results['successful_messages']}/{websocket_results['total_messages']} 消息成功"
                )
                logger.info(f"📥 响应统计: {websocket_results['responses_received']} 个响应")
            else:
                logger.warning("⚠️ WebSocket连接测试失败")

            # 阶段3: 数据清理（如果启用）
            if cleanup_after:
                logger.info("🧹 阶段3: 清理测试数据")
                cleanup_result = await self.cleaner.cleanup_all_test_data(users, all_agents)
                result["test_stages"]["cleanup"] = cleanup_result

                if cleanup_result.get("cleanup_completed", False):
                    logger.info("✅ 测试数据清理完成")
                else:
                    logger.warning("⚠️ 数据清理可能不完整")

            # 生成最终总结
            result["final_summary"] = {
                "total_users": len(users),
                "total_agents": len(all_agents),
                "successful_connections": websocket_results["successful_connections"],
                "total_messages_sent": websocket_results["total_messages"],
                "successful_messages": websocket_results["successful_messages"],
                "responses_received": websocket_results["responses_received"],
                "error_count": len(websocket_results["errors"]),
            }

            # 判断测试是否成功
            success_criteria = [
                len(users) == user_count,
                len(all_agents) == user_count * agents_per_user,
                websocket_results["successful_connections"] > 0,
                websocket_results["successful_messages"] > 0,
            ]

            result["success"] = all(success_criteria)

            if result["success"]:
                logger.info("🎉 简化集成测试成功完成!")
            else:
                logger.error("❌ 简化集成测试未完全成功")

        except Exception as e:
            error_msg = f"集成测试过程中发生错误: {e}"
            logger.error(error_msg)
            result["errors"].append(error_msg)
            result["success"] = False

        logger.info("=" * 60)
        logger.info("简化集成测试结束")
        logger.info("=" * 60)

        return result


async def run_simple_integration_test(
    user_count: int = 2, agents_per_user: int = 2, cleanup_after: bool = True
) -> Dict:
    """运行简化集成测试的便捷函数"""
    runner = SimpleIntegrationTestRunner()
    return await runner.run_simple_integration_test(
        user_count=user_count, agents_per_user=agents_per_user, cleanup_after=cleanup_after
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    async def main():
        result = await run_simple_integration_test(user_count=2, agents_per_user=1)
        print("测试结果:", result)

    asyncio.run(main())
