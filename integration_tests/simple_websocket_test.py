"""
简化的WebSocket测试
使用maim_message库的租户模式进行WebSocket连接和消息交换
"""

import asyncio
import logging
import random
import time
from typing import Dict, List, Optional
from dataclasses import dataclass

from .api_client import TestUser
from maim_message.client import WebSocketClient, create_client_config
from maim_message.message import APIMessageBase, BaseMessageInfo, Seg, MessageDim, SenderInfo, UserInfo, GroupInfo

logger = logging.getLogger(__name__)


@dataclass
class WebSocketTestConfig:
    """WebSocket测试配置"""

    server_url: str = "ws://localhost:8095/ws"
    api_key: Optional[str] = None
    max_retries: int = 3
    heartbeat_interval: int = 30
    message_timeout: float = 100.0


class SimpleWebSocketClient:
    """简化的WebSocket客户端 - 使用最新maim_message API"""

    def __init__(self):
        self.user = None
        self.agent = None
        self.chat_stream_id = None
        self.ws_client = None
        self.config = WebSocketTestConfig()
        self.last_response = None
        self.message_received_event = asyncio.Event()

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
            # 使用 tenant_id + agent_id 作为复合标识符，确保服务器能正确解析
            agent_api_key = f"{user.tenant_id}:{agent_id}" if user.tenant_id else f"default:{agent_id}"
            logger.info(f"🔑 构造API Key: {agent_api_key} (tenant_id={user.tenant_id}, agent_id={agent_id})")

            # 定义异步回调函数
            async def on_connect_callback(conn_uuid, config):
                logger.info(f"WebSocket连接已建立: {conn_uuid}")

            async def on_disconnect_callback(conn_uuid, error):
                logger.info(f"WebSocket连接已断开: {conn_uuid}")

            # 创建最新的WebSocket客户端配置
            client_config = create_client_config(
                url=self.config.server_url,
                api_key=agent_api_key,
                platform=platform,
                auto_reconnect=True,
                max_reconnect_attempts=self.config.max_retries,
                ping_interval=self.config.heartbeat_interval,
                close_timeout=int(self.config.message_timeout),
                on_connect=on_connect_callback,
                on_disconnect=on_disconnect_callback,
                on_message=self._handle_message,
            )

            # 创建最新的WebSocket客户端
            self.ws_client = WebSocketClient(client_config)

            # 启动客户端
            await self.ws_client.start()

            # 连接到服务器
            connected = await self.ws_client.connect()
            if connected:
                logger.info(f"WebSocket连接成功: {user.username} -> {agent_name}")
                return True
            else:
                logger.error(f"WebSocket连接失败: {user.username} -> {agent_name}")
                return False

        except Exception as e:
            logger.error(f"WebSocket连接失败: {e}")
            return False

    async def _handle_message(self, server_message, metadata) -> None:
        """处理接收到的消息"""
        # 处理最新的APIMessageBase格式
        if hasattr(server_message, "message_segment") and hasattr(server_message, "message_info"):
            # 如果是APIMessageBase对象，转换为字典
            message_dict = {
                "message_info": {
                    "platform": server_message.message_info.platform if server_message.message_info else "unknown",
                    "message_id": server_message.message_info.message_id if server_message.message_info else "unknown",
                    "time": server_message.message_info.time if server_message.message_info else 0,
                },
                "message_segment": {
                    "type": server_message.message_segment.type if server_message.message_segment else "unknown",
                    "data": server_message.message_segment.data if server_message.message_segment else "",
                },
                "raw_message": server_message.message_segment.data if server_message.message_segment else "",
            }
            self.last_response = message_dict
        else:
            # 如果已经是字典格式，直接使用
            self.last_response = server_message

        self.message_received_event.set()
        logger.info(f"收到消息: {str(self.last_response)[:100]}...")

    async def send_message(self, content: str) -> bool:
        """发送消息"""
        try:
            # 获取agent_id，处理字典和对象两种情况
            agent_id = self.agent.agent_id if hasattr(self.agent, "agent_id") else self.agent.get("agent_id")

            # 首先构建API key和message_dim
            message_api_key = f"{self.user.tenant_id}:{agent_id}" if self.user.tenant_id else f"default:{agent_id}"
            message_dim = MessageDim(
                api_key=message_api_key,
                platform="test",
            )

            # 创建最新的APIMessageBase格式消息
            message = APIMessageBase(
                message_info=BaseMessageInfo(
                    platform="test",
                    message_id=f"msg_{int(time.time() * 1000)}_{random.randint(1000, 9999)}",
                    time=time.time(),
                    sender_info=SenderInfo(
                        user_info=UserInfo(
                            platform="test",
                            user_id=self.user.user_id,
                            user_nickname=self.user.username,
                        ),
                        group_info=GroupInfo(
                            platform="test",
                            group_id=f"test_group_{self.user.tenant_id}",
                            group_name=f"{self.user.username}的测试群",
                        ),
                    ),
                ),
                message_segment=Seg(type="text", data=content),
                message_dim=message_dim,
            )
            logger.info(f"📤 准备发送消息，API Key: {message_api_key}, 内容: {content[:30]}...")

            # 使用最新的WebSocket客户端发送消息
            if self.ws_client:
                success = await self.ws_client.send_message(message)
                if success:
                    logger.info(f"消息已发送: {content[:50]}...")
                else:
                    logger.error("发送消息失败")
                return success
            else:
                logger.error("WebSocket客户端未初始化")
                return False

        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            return False

    async def receive_response(self, timeout: int = 100) -> Optional[Dict]:
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
        if self.ws_client:
            try:
                # 断开连接
                await self.ws_client.disconnect()
                # 停止客户端
                await self.ws_client.stop()
                logger.info("WebSocket连接已关闭")
            except Exception as e:
                logger.error(f"关闭连接失败: {e}")
            finally:
                self.ws_client = None

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

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("简化WebSocket测试模块已加载")
