#!/usr/bin/env python3
"""
使用maim_message客户端测试no_reply选项禁用效果
基于现有的集成测试框架
"""

import asyncio
import logging
import time
from typing import Dict, Any

from integration_tests.api_client import TestUser
from integration_tests.simple_websocket_test import SimpleWebSocketClient

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NoReplyTester:
    """测试no_reply选项禁用的测试器"""

    def __init__(self):
        self.api_base_url = "http://localhost:8080"
        self.users = []
        self.agents = []

    async def create_test_user_and_agent(self) -> Dict[str, Any]:
        """创建测试用户和Agent"""
        try:
            # 创建测试用户
            user_data = {
                "username": f"testuser_{int(time.time() * 1000)}",
                "password": "test123456",
                "email": f"test_{int(time.time() * 1000)}@example.com",
                "tenant_name": "测试租户",
            }

            import aiohttp

            async with aiohttp.ClientSession() as session:
                # 注册用户
                async with session.post(f"{self.api_base_url}/api/v1/auth/register", json=user_data) as resp:
                    if resp.status == 201:
                        user_result = await resp.json()
                        user_info = user_result["user_info"]
                        logger.info(f"用户创建成功: tenant_id={user_info['tenant_id']}")
                    else:
                        error_text = await resp.text()
                        logger.error(f"创建用户失败: {resp.status} - {error_text}")
                        raise Exception(f"创建用户失败: {resp.status}")

                # 创建测试Agent
                agent_data = {
                    "name": f"testagent_{int(time.time() * 1000)}",
                    "description": "测试Agent",
                    "persona": "一个友好的测试AI助手",
                }

                headers = {"Authorization": f"Bearer {user_result['access_token']}"}
                async with session.post(
                    f"{self.api_base_url}/api/v1/agents/", json=agent_data, headers=headers
                ) as resp:
                    if resp.status in [200, 201]:
                        agent_result = await resp.json()
                        logger.info(f"Agent创建成功: agent_id={agent_result['agent_id']}")

                        # 创建TestUser对象
                        test_user = TestUser(
                            username=user_info["username"],
                            password=user_data["password"],
                            email=user_info["email"],
                            tenant_name=user_info["tenant_name"],
                            tenant_id=user_info["tenant_id"],
                            user_id=user_info["user_id"],
                            access_token=user_result["access_token"],
                            api_key=user_info["api_key"],
                        )

                        # 创建Agent对象
                        agent = {
                            "agent_id": agent_result["agent_id"],
                            "name": agent_result["name"],
                            "description": agent_result["description"],
                            "persona": agent_result["persona"],
                        }

                        return {"user": test_user, "agent": agent, "access_token": user_result["access_token"]}
                    else:
                        error_text = await resp.text()
                        logger.error(f"创建Agent失败: {resp.status} - {error_text}")
                        raise Exception(f"创建Agent失败: {resp.status}")

        except Exception as e:
            logger.error(f"创建测试用户和Agent失败: {e}")
            raise

    async def test_no_reply_disabled(self) -> bool:
        """测试no_reply选项是否被禁用"""
        try:
            # 创建测试用户和Agent
            test_data = await self.create_test_user_and_agent()
            user = test_data["user"]
            agent = test_data["agent"]

            logger.info(f"创建测试数据成功: user={user.username}, agent={agent['name']}")

            # 创建WebSocket客户端
            client = SimpleWebSocketClient()

            try:
                # 连接WebSocket
                if not await client.connect(user, agent):
                    return False

                # 测试消息列表
                test_messages = ["你好！", "今天天气怎么样？", "你能帮我做什么？", "谢谢你的回答", "再见！"]

                reply_count = 0
                no_reply_count = 0

                for i, message in enumerate(test_messages):
                    logger.info(f"\n测试消息 {i + 1}: {message}")

                    # 发送消息并等待回复
                    response = await client.chat(message)

                    if response:
                        # 检查是否是有效回复
                        content = str(response)
                        if content and len(content.strip()) > 0:
                            logger.info(f"✅ 收到回复: {content[:100]}...")
                            reply_count += 1
                        else:
                            logger.warning("⚠️ 收到空回复")
                            no_reply_count += 1
                    else:
                        logger.warning("⚠️ 未收到任何响应")
                        no_reply_count += 1

                    # 等待一下再发送下一条消息
                    await asyncio.sleep(3)

                # 统计结果
                total_messages = len(test_messages)
                reply_rate = (reply_count / total_messages) * 100 if total_messages > 0 else 0

                logger.info("\n📊 测试结果统计:")
                logger.info(f"   总消息数: {total_messages}")
                logger.info(f"   回复数: {reply_count}")
                logger.info(f"   未回复数: {no_reply_count}")
                logger.info(f"   回复率: {reply_rate:.1f}%")

                # 判断测试是否通过
                if reply_rate >= 80:  # 至少80%的回复率算通过
                    logger.info("✅ 测试通过：AI大部分时间都在回复")
                    return True
                else:
                    logger.error("❌ 测试失败：AI回复率过低，no_reply选项可能未被正确禁用")
                    return False

            finally:
                # 关闭客户端
                await client.close()

        except Exception as e:
            logger.error(f"测试过程中出现错误: {e}")
            import traceback

            traceback.print_exc()
            return False


async def main():
    """主函数"""
    logger.info("🎯 开始测试no_reply选项禁用效果（使用maim_message客户端）")
    logger.info("=" * 60)

    tester = NoReplyTester()
    success = await tester.test_no_reply_disabled()

    logger.info("\n" + "=" * 60)
    if success:
        logger.info("🎉 测试完成：no_reply选项已成功禁用")
    else:
        logger.error("😞 测试完成：no_reply选项禁用可能存在问题")

    return success


if __name__ == "__main__":
    asyncio.run(main())
