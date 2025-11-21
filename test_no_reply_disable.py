#!/usr/bin/env python3
"""
测试禁用no_reply选项的效果
验证AI是否每次都回复用户消息
"""

import asyncio
import logging
from integration_tests.simple_websocket_test import run_simple_websocket_tests
from integration_tests.api_client import MaiMBotAPIClient

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_no_reply_disabled():
    """测试no_reply选项是否被禁用"""
    print("🧪 测试no_reply选项禁用效果...")

    # 创建测试客户端
    api_client = MaiMBotAPIClient()

    try:
        # 创建用户和Agent
        print("📝 创建测试用户和Agent...")
        user_result = await api_client.create_user("test_no_reply_user")
        agent_result = await api_client.create_agent(user_result["user_id"], "test_no_reply_agent")

        # 创建TestUser对象
        from integration_tests.api_client import TestUser

        test_user = TestUser(
            user_id=user_result["user_id"],
            username=user_result["username"],
            tenant_id=user_result["tenant_id"],
            api_key=user_result["api_key"],
        )
        test_user.agents = [agent_result]

        print(f"✅ 创建成功: user={user_result['user_id']}, agent={agent_result['agent_id']}")

        # 使用简化的WebSocket测试函数
        print("🔌 开始WebSocket测试...")
        results = await run_simple_websocket_tests([test_user], [agent_result])

        # 分析结果
        total_messages = results.get("total_messages", 0)
        successful_messages = results.get("successful_messages", 0)
        responses_received = results.get("responses_received", 0)

        print("\n📊 测试结果统计:")
        print(f"   总消息数: {total_messages}")
        print(f"   成功发送数: {successful_messages}")
        print(f"   收到回复数: {responses_received}")

        reply_rate = (responses_received / total_messages) * 100 if total_messages > 0 else 0
        print(f"   回复率: {reply_rate:.1f}%")

        # 显示详细测试结果
        test_details = results.get("test_details", [])
        for detail in test_details:
            status = "✅" if detail["success"] else "❌"
            print(f"   {status} {detail['message']} -> {detail.get('response', 'No response')}")

        # 判断测试是否通过
        if reply_rate >= 80:  # 至少80%的回复率算通过
            print("✅ 测试通过：AI大部分时间都在回复")
            return True
        else:
            print("❌ 测试失败：AI回复率过低，no_reply选项可能未被正确禁用")
            return False

    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """主函数"""
    print("🎯 开始测试no_reply选项禁用效果")
    print("=" * 50)

    success = await test_no_reply_disabled()

    print("\n" + "=" * 50)
    if success:
        print("🎉 测试完成：no_reply选项已成功禁用")
    else:
        print("😞 测试完成：no_reply选项禁用可能存在问题")

    return success


if __name__ == "__main__":
    asyncio.run(main())
