#!/usr/bin/env python3
"""
消息发送和回复测试演示
展示WebSocket测试系统的功能
"""

import asyncio
import logging
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from integration_tests.api_client import create_test_scenario
from integration_tests.simple_websocket_test import SimpleWebSocketClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


async def demo_message_test():
    """演示消息发送和回复测试"""
    logger.info("🎯 开始演示消息发送和回复测试")

    # 1. 检查服务是否可用
    logger.info("🔍 检查服务状态...")

    try:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:18000/health") as response:
                health = await response.json()
                if not health.get("status") == "healthy":
                    logger.error("❌ 配置器服务不可用")
                    return
                logger.info("✅ 配置器服务正常")
    except Exception as e:
        logger.error(f"❌ 无法连接到配置器服务: {e}")
        logger.info("💡 请确保配置器后端在端口18000运行")
        return

    # 2. 创建测试用户和Agent
    logger.info("👥 创建测试用户和Agent...")
    try:
        manager = await create_test_scenario(config_api_url="http://localhost:18000", user_count=1, agents_per_user=1)
        user = manager.users[0]
        agent = user.agents[0]

        logger.info(f"✅ 创建用户: {user.username} (租户: {user.tenant_id})")
        logger.info(f"✅ 创建Agent: {agent.name} (ID: {agent.agent_id})")

    except Exception as e:
        logger.error(f"❌ 创建用户和Agent失败: {e}")
        return

    # 3. 建立WebSocket连接
    logger.info("🔌 建立WebSocket连接...")
    ws_client = SimpleWebSocketClient()

    try:
        # 启动连接池
        from integration_tests.simple_websocket_test import get_connection_pool

        connection_pool = get_connection_pool()
        await connection_pool.start()

        connected = await ws_client.connect(user, agent)
        if not connected:
            logger.error("❌ WebSocket连接失败")
            return
        logger.info("✅ WebSocket连接成功")

    except Exception as e:
        logger.error(f"❌ WebSocket连接异常: {e}")
        logger.info("💡 请确保回复后端在端口8095运行")
        return

    # 4. 发送测试消息并接收回复
    logger.info("💬 开始消息发送和回复测试...")

    test_messages = ["你好！我是测试用户", "你能介绍一下自己吗？", "你有什么功能？", "今天天气如何？", "谢谢你的回答"]

    success_count = 0
    total_count = len(test_messages)

    for i, message in enumerate(test_messages, 1):
        logger.info(f"📨 测试 {i}/{total_count}: 发送消息 '{message}'")

        try:
            response = await ws_client.chat(message)

            if response:
                success_count += 1
                # 提取响应文本
                if isinstance(response, dict):
                    if "processed_plain_text" in response:
                        response_text = response["processed_plain_text"]
                    elif "display_message" in response:
                        response_text = response["display_message"]
                    else:
                        response_text = str(response)[:100] + "..."
                else:
                    response_text = str(response)[:100] + "..."

                logger.info(f"✅ 收到回复: {response_text}")
            else:
                logger.warning("⚠️ 未收到回复")

        except Exception as e:
            logger.error(f"❌ 消息测试失败: {e}")

        # 等待一下再发送下一条消息
        await asyncio.sleep(2)

    # 5. 测试总结
    logger.info("📊 测试总结:")
    logger.info(f"   总消息数: {total_count}")
    logger.info(f"   成功回复: {success_count}")
    logger.info(f"   成功率: {success_count / total_count * 100:.1f}%")

    # 6. 清理连接
    logger.info("🧹 清理连接...")
    await ws_client.close()

    # 停止连接池
    try:
        await connection_pool.stop()
    except Exception as e:
        logger.error(f"停止连接池失败: {e}")

    logger.info("🎉 消息发送和回复测试演示完成!")


async def main():
    """主函数"""
    print("🤖 MaiMBot 消息发送和回复测试演示")
    print("=" * 50)
    print("本演示将展示:")
    print("1. 通过API创建测试用户和Agent")
    print("2. 建立WebSocket连接")
    print("3. 发送多种类型的测试消息")
    print("4. 接收并验证Bot回复")
    print("5. 统计测试结果")
    print("=" * 50)
    print()

    await demo_message_test()


if __name__ == "__main__":
    asyncio.run(main())
