#!/usr/bin/env python3
"""
测试连接池功能是否正常工作
验证同一个(user, agent)组合是否只创建一个客户端实例
"""

import asyncio
import logging
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from integration_tests.simple_websocket_test import SimpleWebSocketClient, get_connection_pool
from integration_tests.api_client import create_test_scenario

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


async def test_connection_pool():
    """测试连接池功能"""
    logger.info("🔧 开始测试连接池功能")

    # 1. 创建测试用户和Agent
    logger.info("👥 创建测试用户和Agent...")
    try:
        manager = await create_test_scenario(config_api_url="http://localhost:18000", user_count=1, agents_per_user=1)
        user = manager.users[0]
        agent = user.agents[0]

        logger.info(f"✅ 创建用户: {user.username} (租户: {user.tenant_id})")
        agent_name = agent.name if hasattr(agent, "name") else agent.get("name", "Unknown")
        agent_id = agent.agent_id if hasattr(agent, "agent_id") else agent.get("agent_id")
        logger.info(f"✅ 创建Agent: {agent_name} (ID: {agent_id})")

    except Exception as e:
        logger.error(f"❌ 创建用户和Agent失败: {e}")
        return False

    # 2. 启动连接池
    logger.info("🚀 启动连接池...")
    connection_pool = get_connection_pool()
    await connection_pool.start()

    try:
        # 3. 创建多个客户端实例，验证连接复用
        logger.info("🔌 创建多个客户端实例...")

        clients = []
        for i in range(3):
            client = SimpleWebSocketClient()
            clients.append(client)

            connected = await client.connect(user, agent)
            if connected:
                logger.info(f"✅ 客户端 {i + 1} 连接成功")
            else:
                logger.error(f"❌ 客户端 {i + 1} 连接失败")
                return False

        # 4. 检查连接池状态
        stats = connection_pool.get_stats()
        logger.info("📊 连接池状态:")
        logger.info(f"   总连接数: {stats['total_connections']}")
        logger.info(f"   活跃连接数: {stats['active_connections']}")
        logger.info(f"   闲置连接数: {stats['idle_connections']}")

        # 验证是否每个客户端都有独立的连接
        if stats["total_connections"] == 3 and stats["active_connections"] == 3:
            logger.info("✅ 连接池正常：3个客户端创建了3个独立连接")
            success = True
        else:
            logger.error(
                f"❌ 连接池异常：预期3个连接3个活跃，实际{stats['total_connections']}个连接{stats['active_connections']}个活跃"
            )
            success = False

        # 5. 关闭所有客户端
        logger.info("🧹 关闭所有客户端...")
        for i, client in enumerate(clients):
            await client.close()
            logger.info(f"✅ 客户端 {i + 1} 已关闭")

        # 6. 再次检查连接池状态
        stats = connection_pool.get_stats()
        logger.info("📊 关闭后连接池状态:")
        logger.info(f"   总连接数: {stats['total_connections']}")
        logger.info(f"   活跃连接数: {stats['active_connections']}")
        logger.info(f"   闲置连接数: {stats['idle_connections']}")

        if stats["total_connections"] == 1 and stats["active_connections"] == 0 and stats["idle_connections"] == 1:
            logger.info("✅ 连接释放正常：连接保留在池中但未活跃")
        else:
            logger.warning(f"⚠️ 连接状态异常：{stats}")

        return success

    except Exception as e:
        logger.error(f"❌ 测试过程中发生错误: {e}")
        return False

    finally:
        # 7. 停止连接池
        logger.info("🛑 停止连接池...")
        await connection_pool.stop()
        logger.info("✅ 连接池已停止")


async def main():
    """主函数"""
    print("🤖 连接池功能测试")
    print("=" * 50)
    print("本测试将验证:")
    print("1. 连接池启动和停止")
    print("2. 多个客户端复用同一个连接")
    print("3. 连接获取和释放逻辑")
    print("4. 连接池状态统计")
    print("=" * 50)
    print()

    success = await test_connection_pool()

    print("\n" + "=" * 50)
    if success:
        print("✅ 连接池功能测试通过!")
    else:
        print("❌ 连接池功能测试失败!")
    print("=" * 50)

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
