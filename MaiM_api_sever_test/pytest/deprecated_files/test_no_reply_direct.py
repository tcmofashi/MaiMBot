#!/usr/bin/env python3
"""
直接测试no_reply选项禁用效果
不使用maim_message，直接连接回复后端进行测试
"""

import asyncio
import json
import time
import logging
import aiohttp
from typing import Dict, Any, Optional

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DirectBackendTester:
    """直接连接回复后端的测试器"""

    def __init__(self):
        self.api_base_url = "http://localhost:8080"  # 配置器后端API
        self.reply_backend_url = "http://localhost:8095"  # 回复后端WebSocket
        self.session = None
        self.websocket = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.websocket:
            await self.websocket.close()
        if self.session:
            await self.session.close()

    async def create_test_user_and_agent(self) -> Dict[str, Any]:
        """创建测试用户和Agent"""
        try:
            # 创建用户
            user_data = {"username": f"test_direct_user_{int(time.time())}", "platform": "test"}

            async with self.session.post(f"{self.api_base_url}/api/users", json=user_data) as resp:
                if resp.status != 200:
                    raise Exception(f"创建用户失败: {resp.status}")
                user_result = await resp.json()

            # 创建Agent
            agent_data = {
                "name": f"test_direct_agent_{int(time.time())}",
                "description": "测试Agent",
                "config": {
                    "personality": {
                        "name": "小千",
                        "interest": "对技术相关话题，游戏和动漫相关话题感兴趣，也对日常话题感兴趣，不喜欢太过沉重严肃的话题",
                    }
                },
            }

            async with self.session.post(
                f"{self.api_base_url}/api/agents", json=agent_data, headers={"X-Tenant-ID": user_result["tenant_id"]}
            ) as resp:
                if resp.status != 200:
                    raise Exception(f"创建Agent失败: {resp.status}")
                agent_result = await resp.json()

            return {
                "user": user_result,
                "agent": agent_result,
                "tenant_id": user_result["tenant_id"],
                "agent_id": agent_result["agent_id"],
            }

        except Exception as e:
            logger.error(f"创建测试用户和Agent失败: {e}")
            raise

    async def connect_websocket(self, tenant_id: str, agent_id: str) -> bool:
        """连接WebSocket"""
        try:
            import websockets

            # 构建WebSocket URL
            ws_url = "ws://localhost:8095/ws"

            # 构建连接参数
            params = {"tenant_id": tenant_id, "agent_id": agent_id, "platform": "test"}

            # 连接WebSocket
            self.websocket = await websockets.connect(f"{ws_url}?{'&'.join([f'{k}={v}' for k, v in params.items()])}")

            logger.info(f"WebSocket连接成功: tenant={tenant_id}, agent={agent_id}")
            return True

        except Exception as e:
            logger.error(f"WebSocket连接失败: {e}")
            return False

    async def send_message(self, content: str) -> bool:
        """发送消息"""
        try:
            message = {
                "type": "chat",
                "message_id": f"msg_{int(time.time() * 1000)}",
                "timestamp": time.time(),
                "content": content,
                "sender": {"user_id": "test_user", "username": "test_user"},
                "platform": "test",
            }

            await self.websocket.send(json.dumps(message))
            logger.info(f"发送消息: {content}")
            return True

        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            return False

    async def receive_response(self, timeout: int = 30) -> Optional[Dict[str, Any]]:
        """接收响应"""
        try:
            # 等待响应
            response = await asyncio.wait_for(self.websocket.recv(), timeout=timeout)

            response_data = json.loads(response)
            logger.info(f"收到响应: {response_data}")
            return response_data

        except asyncio.TimeoutError:
            logger.warning("接收响应超时")
            return None
        except Exception as e:
            logger.error(f"接收响应失败: {e}")
            return None

    async def test_no_reply_disabled(self) -> bool:
        """测试no_reply选项是否被禁用"""
        try:
            # 创建测试用户和Agent
            test_data = await self.create_test_user_and_agent()
            logger.info(f"创建测试数据成功: {test_data}")

            # 连接WebSocket
            if not await self.connect_websocket(test_data["tenant_id"], test_data["agent_id"]):
                return False

            # 测试消息列表
            test_messages = ["你好！", "今天天气怎么样？", "你能帮我做什么？", "谢谢你的回答", "再见！"]

            reply_count = 0
            no_reply_count = 0

            for i, message in enumerate(test_messages):
                logger.info(f"\n测试消息 {i + 1}: {message}")

                # 发送消息
                if not await self.send_message(message):
                    continue

                # 等待响应
                response = await self.receive_response(timeout=30)

                if response:
                    # 检查是否是有效回复
                    if response.get("type") == "chat_response":
                        content = response.get("content", "").strip()
                        if content:
                            logger.info(f"✅ 收到回复: {content}")
                            reply_count += 1
                        else:
                            logger.warning("⚠️ 收到空回复")
                            no_reply_count += 1
                    else:
                        logger.warning(f"⚠️ 收到非回复类型消息: {response.get('type')}")
                        no_reply_count += 1
                else:
                    logger.warning("⚠️ 未收到任何响应")
                    no_reply_count += 1

                # 等待一下再发送下一条消息
                await asyncio.sleep(2)

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

        except Exception as e:
            logger.error(f"测试过程中出现错误: {e}")
            import traceback

            traceback.print_exc()
            return False


async def main():
    """主函数"""
    logger.info("🎯 开始直接测试no_reply选项禁用效果")
    logger.info("=" * 50)

    async with DirectBackendTester() as tester:
        success = await tester.test_no_reply_disabled()

    logger.info("\n" + "=" * 50)
    if success:
        logger.info("🎉 测试完成：no_reply选项已成功禁用")
    else:
        logger.error("😞 测试完成：no_reply选项禁用可能存在问题")

    return success


if __name__ == "__main__":
    asyncio.run(main())
