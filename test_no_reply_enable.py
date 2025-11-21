#!/usr/bin/env python3
"""
测试no_reply功能是否已重新启用

这个脚本将测试AI是否能够选择no_reply和no_reply_until_call选项，
而不是被强制每次都回复。
"""

import asyncio
import time
from typing import Dict, Any
import aiohttp
from integration_tests.simple_websocket_test import SimpleWebSocketClient


class NoReplyEnableTester:
    """测试no_reply功能重新启用的测试器"""

    def __init__(self):
        self.api_base_url = "http://localhost:8080"
        self.reply_backend_url = "ws://localhost:8095/ws"
        self.test_results = []

    async def create_test_user_and_agent(self) -> Dict[str, Any]:
        """创建测试用户和Agent"""
        async with aiohttp.ClientSession() as session:
            # 创建用户
            user_data = {"username": f"testuser_noreply_{int(time.time())}", "platform": "test"}

            async with session.post(f"{self.api_base_url}/api/users", json=user_data) as resp:
                if resp.status != 200:
                    raise Exception(f"创建用户失败: {resp.status}")
                user_result = await resp.json()

            # 创建Agent
            agent_data = {
                "name": f"test_agent_noreply_{int(time.time())}",
                "description": "测试no_reply功能的Agent",
                "personality": {
                    "interest": "对技术相关话题，游戏和动漫相关话题感兴趣，也对日常话题感兴趣，不喜欢太过沉重严肃的话题",
                    "plan_style": "请控制你的发言频率，不要太过频繁的发言。如果话题不感兴趣，可以选择保持沉默。",
                },
            }

            headers = {"Authorization": f"Bearer {user_result['token']}"}
            async with session.post(f"{self.api_base_url}/api/agents", json=agent_data, headers=headers) as resp:
                if resp.status != 200:
                    raise Exception(f"创建Agent失败: {resp.status}")
                agent_result = await resp.json()

            return {"user": user_result, "agent": agent_result, "token": user_result["token"]}

    async def test_no_reply_options_available(self) -> bool:
        """测试no_reply选项是否可用"""
        print("🧪 测试no_reply选项是否可用...")

        try:
            # 创建测试用户和Agent
            test_data = await self.create_test_user_and_agent()
            user = test_data["user"]
            agent = test_data["agent"]
            token = test_data["token"]

            print(f"✅ 创建测试用户: {user['username']}")
            print(f"✅ 创建测试Agent: {agent['name']}")

            # 创建WebSocket客户端
            ws_client = SimpleWebSocketClient()

            # 连接WebSocket
            connected = await ws_client.connect(tenant_id=user["tenant_id"], agent_id=agent["id"], platform="test")

            if not connected:
                print("❌ WebSocket连接失败")
                return False

            print("✅ WebSocket连接成功")

            # 发送多条消息来测试AI是否会选择no_reply
            messages = [
                "你好",
                "今天天气怎么样",
                "你在做什么",
                "给我讲个故事吧",
                "你喜欢什么颜色",
                "你刚才为什么沉默",
                "继续聊聊天吧",
                "你觉得这个怎么样",
                "有什么建议吗",
                "再见",
            ]

            reply_count = 0
            no_reply_count = 0
            total_messages = len(messages)

            for i, message in enumerate(messages, 1):
                print(f"\n📤 发送第{i}条消息: {message}")

                # 发送消息
                response = await ws_client.send_message(message)

                if response:
                    reply_count += 1
                    print(f"💬 AI回复: {response[:50]}...")

                    # 检查回复内容是否提到沉默或不想回复
                    if any(keyword in response.lower() for keyword in ["沉默", "不想", "没兴趣", "安静", "保持安静"]):
                        print("🤔 AI表达了想要沉默的意愿")

                else:
                    no_reply_count += 1
                    print("🔇 AI选择沉默(no_reply)")

                # 等待一段时间再发送下一条消息
                await asyncio.sleep(2)

            # 断开连接
            await ws_client.disconnect()

            # 计算统计结果
            reply_rate = reply_count / total_messages
            no_reply_rate = no_reply_count / total_messages

            print("\n📊 测试结果统计:")
            print(f"   总消息数: {total_messages}")
            print(f"   回复次数: {reply_count} ({reply_rate:.1%})")
            print(f"   沉默次数: {no_reply_count} ({no_reply_rate:.1%})")

            # 判断测试结果
            if no_reply_count > 0:
                print("✅ no_reply功能已重新启用，AI可以选择沉默")
                return True
            elif reply_rate < 0.9:  # 如果回复率低于90%，说明AI在控制频率
                print("✅ AI在控制回复频率，no_reply功能部分正常")
                return True
            else:
                print("⚠️ AI仍然每次都回复，no_reply功能可能未完全启用")
                return False

        except Exception as e:
            print(f"❌ 测试过程中出错: {e}")
            return False

    async def run_test(self):
        """运行完整的测试"""
        print("🚀 开始测试no_reply功能重新启用")
        print("=" * 50)

        try:
            # 测试no_reply选项是否可用
            success = await self.test_no_reply_options_available()

            print("\n" + "=" * 50)
            if success:
                print("🎉 no_reply功能重新启用测试通过！")
                print("   AI现在可以根据情况选择是否回复")
            else:
                print("❌ no_reply功能重新启用测试失败")
                print("   AI仍然被强制每次都回复")

            return success

        except Exception as e:
            print(f"❌ 测试运行失败: {e}")
            return False


async def main():
    """主函数"""
    tester = NoReplyEnableTester()
    success = await tester.run_test()

    if success:
        print("\n✅ 所有测试通过")
        exit(0)
    else:
        print("\n❌ 测试失败")
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())
