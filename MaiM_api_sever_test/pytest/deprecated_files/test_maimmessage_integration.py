#!/usr/bin/env python3
"""
测试maim_message库集成
验证3用户2Agent的多连接场景
"""

import asyncio
import logging
import sys

# 添加项目路径
sys.path.insert(0, '/home/tcmofashi/proj/MaiMBot')

from integration_tests.api_client import create_test_scenario
from integration_tests.simple_websocket_test import run_simple_websocket_tests

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_maimmessage_integration():
    """测试maim_message库集成"""
    logger.info("=" * 60)
    logger.info("开始maim_message库集成测试")
    logger.info("=" * 60)

    # 测试参数：3用户2Agent
    user_count = 3
    agents_per_user = 2

    try:
        # 阶段1: 创建测试场景
        logger.info("📝 阶段1: 创建测试用户和Agent")
        manager = await create_test_scenario(
            config_api_url="http://localhost:18000",
            user_count=user_count,
            agents_per_user=agents_per_user
        )

        users = manager['users']
        all_agents = manager['all_agents']

        logger.info(f"✅ 创建了 {len(users)} 个用户，{len(all_agents)} 个Agent")

        # 打印用户和Agent信息
        for user in users:
            logger.info(f"用户: {user.username} (tenant_id: {user.tenant_id})")
            for agent in user.agents:
                agent_obj = next((a for a in all_agents if a.agent_id == agent["agent_id"]), None)
                if agent_obj:
                    logger.info(f"  - Agent: {agent_obj.name} (agent_id: {agent_obj.agent_id})")
                else:
                    logger.warning(f"  - Agent未找到: {agent}")

        # 阶段2: WebSocket连接测试
        logger.info("\n🔗 阶段2: WebSocket连接测试")
        websocket_results = await run_simple_websocket_tests(users, all_agents)

        # 打印测试结果
        logger.info("\n📊 WebSocket测试结果:")
        logger.info(f"  总连接数: {websocket_results['total_connections']}")
        logger.info(f"  成功连接: {websocket_results['successful_connections']}")
        logger.info(f"  总消息数: {websocket_results['total_messages']}")
        logger.info(f"  成功发送: {websocket_results['successful_messages']}")
        logger.info(f"  收到回复: {websocket_results['responses_received']}")

        if websocket_results['errors']:
            logger.warning("❌ 发现错误:")
            for error in websocket_results['errors']:
                logger.warning(f"  - {error}")

        # 打印详细测试信息
        logger.info("\n📋 详细测试结果:")
        for detail in websocket_results['test_details'][:10]:  # 只显示前10个
            status = "✅" if detail['success'] else "❌"
            logger.info(f"  {status} {detail['user']} -> {detail['agent']}: {detail['message']}")
            if detail['response']:
                response_preview = detail['response'][:100] + "..." if len(detail['response']) > 100 else detail['response']
                logger.info(f"      回复: {response_preview}")

        # 测试评估
        success_rate = websocket_results['successful_connections'] / websocket_results['total_connections'] if websocket_results['total_connections'] > 0 else 0
        message_success_rate = websocket_results['successful_messages'] / websocket_results['total_messages'] if websocket_results['total_messages'] > 0 else 0

        logger.info("\n📈 测试评估:")
        logger.info(f"  连接成功率: {success_rate:.1%}")
        logger.info(f"  消息成功率: {message_success_rate:.1%}")

        # 判断测试是否成功
        if success_rate >= 0.8 and message_success_rate >= 0.8:
            logger.info("🎉 maim_message库集成测试成功！")
            return True
        else:
            logger.error("❌ maim_message库集成测试失败")
            return False

    except Exception as e:
        logger.error(f"❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主函数"""
    logger.info("开始测试maim_message库集成...")

    success = await test_maimmessage_integration()

    if success:
        logger.info("✅ 所有测试通过")
        sys.exit(0)
    else:
        logger.error("❌ 测试失败")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())