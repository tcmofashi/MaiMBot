"""
简化的WebSocket测试
使用maim_message库的租户模式进行WebSocket连接和消息交换
"""

import asyncio
import logging
import random
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from .api_client import TestUser
from src.isolation.websocket_connection_pool import get_connection_pool

logger = logging.getLogger(__name__)


@dataclass
class TenantWebSocketConfig:
    """租户WebSocket配置"""

    server_url: str = "ws://localhost:8095"
    api_key: Optional[str] = None
    max_retries: int = 3
    heartbeat_interval: int = 30
    message_timeout: float = 30.0


class SimpleWebSocketClient:
    """简化的WebSocket客户端 - 使用maim_message租户模式"""

    def __init__(self):
        self.user = None
        self.agent = None
        self.chat_stream_id = None
        self.tenant_client = None
        self.config = TenantWebSocketConfig()
        self.last_response = None
        self.message_received_event = asyncio.Event()
        self.connection_pool = get_connection_pool()
        self.connection_key = None  # 用于标识连接

    async def connect(self, user: TestUser, agent, platform: str = "test") -> bool:
        """连接到WebSocket"""
        try:
            self.user = user
            self.agent = agent

            # 获取agent_id，处理字典和对象两种情况
            agent_id = agent.agent_id if hasattr(agent, "agent_id") else agent.get("agent_id")
            agent_name = agent.name if hasattr(agent, "name") else agent.get("name", "Unknown")

            # 生成聊天流ID
            import uuid

            self.chat_stream_id = f"test_chat_{uuid.uuid4().hex[:8]}"

            # 为每个agent生成独立的api-key
            # 使用用户api-key + agent_id作为复合标识符
            agent_api_key = f"{user.api_key}:{agent_id}" if user.api_key else f"agent_key_{agent_id}"

            # 保存连接键，用于后续释放
            self.connection_key = {
                "tenant_id": user.tenant_id,
                "agent_id": agent_id,
                "platform": platform,
                "server_url": self.config.server_url
            }

            # 使用连接池获取客户端（每个客户端都是独立连接）
            self.tenant_client = await self.connection_pool.get_client(
                tenant_id=user.tenant_id,
                agent_id=agent_id,
                platform=platform,
                server_url=self.config.server_url,
                api_key=agent_api_key,
                max_retries=self.config.max_retries,
                heartbeat_interval=self.config.heartbeat_interval,
                message_timeout=self.config.message_timeout
            )

            # 设置消息回调
            self.tenant_client.register_callback(
                callback=self._handle_message,
                message_types=["chat_response", "message", "response"],
                tenant_filter=user.tenant_id,
                platform_filter=platform,
            )

            logger.info(f"租户模式WebSocket连接成功: {user.username} -> {agent_name}")
            return True

        except Exception as e:
            logger.error(f"WebSocket连接失败: {e}")
            return False

    
    def _handle_message(self, message: Dict[str, Any]) -> None:
        """处理接收到的消息"""
        self.last_response = message
        self.message_received_event.set()
        logger.info(f"收到消息: {str(message)[:100]}...")

    async def send_message(self, content: str) -> bool:
        """发送消息"""
        try:
            # 获取agent_id，处理字典和对象两种情况
            agent_id = self.agent.agent_id if hasattr(self.agent, "agent_id") else self.agent.get("agent_id")

            # 创建符合MaiMBot期望格式的消息
            message = {
                "type": "chat",
                "message_info": {
                    "message_id": f"msg_{int(time.time() * 1000)}_{random.randint(1000, 9999)}",
                    "time": time.time(),
                    "platform": "test",
                    "sender_info": {
                        "user_info": {
                            "platform": "test",
                            "user_id": self.user.user_id,
                            "user_nickname": self.user.username,
                        },
                        "group_info": {
                            "platform": "test",
                            "group_id": f"test_group_{self.user.tenant_id}",
                            "group_name": f"{self.user.username}的测试群",
                        },
                    },
                },
                "message_segment": {
                    "type": "text",
                    "data": content,
                },
                "raw_message": content,
                "processed_plain_text": content,
                "display_message": content,
                "chat_stream_id": self.chat_stream_id,
                "tenant_id": self.user.tenant_id,
                "agent_id": agent_id,
                "platform": "test",
            }

            # 使用租户客户端发送消息
            if self.tenant_client:
                success = await self.tenant_client.send_message(message)
                if success:
                    logger.info(f"消息已发送: {content[:50]}...")
                else:
                    logger.error("发送消息失败")
                return success
            else:
                logger.error("租户客户端未初始化")
                return False

        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            return False

    async def receive_response(self, timeout: int = 30) -> Optional[Dict]:
        """接收响应"""
        try:
            # 租户模式通过回调处理消息，等待响应
            self.message_received_event.clear()
            self.last_response = None

            # 等待消息接收事件，最多等待timeout秒
            try:
                await asyncio.wait_for(self.message_received_event.wait(), timeout=timeout)
                response = self.last_response
                self.last_response = None
                return response
            except asyncio.TimeoutError:
                logger.warning("接收响应超时")
                return None

        except Exception as e:
            logger.error(f"接收响应失败: {e}")
            return None

    async def close(self):
        """关闭连接"""
        if self.tenant_client:
            try:
                # 通过连接池释放连接
                await self.connection_pool.release_client(self.tenant_client)
                logger.info("租户模式WebSocket连接已释放回连接池")
            except Exception as e:
                logger.error(f"释放连接失败: {e}")
            finally:
                self.tenant_client = None
                self.connection_key = None

    async def chat(self, message: str) -> Optional[Dict]:
        """进行一次对话"""
        if not await self.send_message(message):
            return None

        return await self.receive_response()


async def run_simple_websocket_tests(users: List[TestUser], agents: List) -> Dict:
    """运行简化的WebSocket测试"""
    results = {
        "total_connections": 0,
        "successful_connections": 0,
        "total_messages": 0,
        "successful_messages": 0,
        "responses_received": 0,
        "errors": [],
        "test_details": [],
    }

    # 启动连接池
    connection_pool = get_connection_pool()
    await connection_pool.start()

    try:
        # 为每个用户和Agent创建连接
        for user in users:
            for agent in user.agents:
                results["total_connections"] += 1

                # 获取agent名称，处理字典和对象两种情况
                agent_name = agent.name if hasattr(agent, "name") else agent.get("name", "Unknown")

                # 创建客户端实例
                client = SimpleWebSocketClient()

                try:
                    # 连接WebSocket
                    if await client.connect(user, agent):
                        results["successful_connections"] += 1
                    else:
                        logger.error(f"连接失败: {user.username} -> {agent_name}")
                        results["errors"].append(f"连接失败: {user.username} -> {agent_name}")
                        continue

                    # 发送测试消息
                    test_messages = [
                        "你好！",
                        "我想了解一下你的功能",
                        "今天天气怎么样？",
                        "你能帮我做什么？",
                        "谢谢你的回答",
                    ]

                    for msg in test_messages:
                        results["total_messages"] += 1
                        response = await client.chat(msg)
                        if response:
                            results["successful_messages"] += 1
                            results["responses_received"] += 1
                            results["test_details"].append(
                                {
                                    "user": user.username,
                                    "agent": agent_name,
                                    "message": msg,
                                    "response": str(response)[:200] + "..."
                                    if len(str(response)) > 200
                                    else str(response),
                                    "success": True,
                                }
                            )
                        else:
                            results["test_details"].append(
                                {
                                    "user": user.username,
                                    "agent": agent_name,
                                    "message": msg,
                                    "response": None,
                                    "success": False,
                                }
                            )

                        # 等待一下再发送下一条消息
                        await asyncio.sleep(1)

                except Exception as e:
                    error_msg = f"测试 {user.username} -> {agent_name} 时发生错误: {e}"
                    logger.error(error_msg)
                    results["errors"].append(error_msg)

                finally:
                    # 关闭客户端
                    await client.close()

    except Exception as e:
        error_msg = f"测试过程中发生错误: {e}"
        results["errors"].append(error_msg)
        logger.error(f"WebSocket测试失败: {e}")

    finally:
        # 停止连接池
        await connection_pool.stop()

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("简化WebSocket测试模块已加载")
