"""
WebSocket多路连接对话测试
使用maim_message库的租户模式创建多个WebSocket连接与回复器对话
"""

import asyncio
import logging
import random
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime


from .api_client import TestUser, TestAgent

logger = logging.getLogger(__name__)


@dataclass
class ConversationScenario:
    """对话场景"""

    name: str
    topics: List[str]
    message_count: int
    user_id: str
    user_nickname: str
    tenant_id: str


class WebSocketChatClient:
    """WebSocket聊天客户端 - 使用maim_message租户模式"""

    def __init__(self, reply_server_url: str = "ws://localhost:8095"):
        self.reply_server_url = reply_server_url
        self.tenant_client: Optional[TenantMessageClient] = None
        self.user: Optional[TestUser] = None
        self.agent: Optional[TestAgent] = None
        self.chat_stream_id: Optional[str] = None
        self.messages_sent: List[Dict] = []
        self.messages_received: List[Dict] = []
        self.message_received_event = asyncio.Event()

    async def connect(self, user: TestUser, agent: TestAgent, platform: str = "test") -> bool:
        """连接到回复后端"""
        try:
            # 创建客户端配置
            client_config = ClientConfig(
                tenant_id=user.tenant_id,
                agent_id=agent.agent_id,
                platform=platform,
                server_url=self.reply_server_url,
                max_retries=3,
                heartbeat_interval=30,
                message_timeout=30.0,
            )

            self.tenant_client = TenantMessageClient(client_config)

            # 设置消息回调
            self.tenant_client.register_callback(
                callback=self._handle_message,
                message_types=["chat_response", "message", "response"],
                tenant_filter=user.tenant_id,
                platform_filter=platform,
            )

            # 连接到服务器
            if await self.tenant_client.connect():
                self.user = user
                self.agent = agent

                # 生成聊天流ID
                import uuid

                self.chat_stream_id = f"test_chat_{uuid.uuid4().hex[:8]}"

                logger.info(f"租户模式WebSocket连接成功: {user.username} -> {agent.name}")
                return True
            else:
                logger.error(f"租户模式连接失败: {user.username} -> {agent.name}")
                return False

        except Exception as e:
            logger.error(f"WebSocket连接失败: {e}")
            return False

    def _handle_message(self, message: Dict[str, Any]) -> None:
        """处理接收到的消息"""
        self.messages_received.append(
            {
                "content": message.get("data", {}).get("response", ""),
                "timestamp": datetime.now().isoformat(),
                "agent_id": message.get("data", {}).get("agent_id"),
                "chat_stream_id": message.get("data", {}).get("chat_stream_id"),
                "raw_message": message,
            }
        )
        self.message_received_event.set()
        logger.debug(f"收到回复: {message.get('data', {}).get('response', '')[:50]}...")

    async def send_message(self, content: str, message_id: str = None) -> bool:
        """发送消息"""
        if not self.tenant_client:
            logger.error("租户客户端未连接")
            return False

        if not message_id:
            message_id = f"msg_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"

        try:
            # 创建符合MaiMBot期望格式的消息
            message = {
                "type": "chat",
                "message_info": {
                    "message_id": message_id,
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
                "agent_id": self.agent.agent_id,
                "platform": "test",
            }

            # 发送消息
            success = await self.tenant_client.send_message(message)

            if success:
                # 记录发送的消息
                self.messages_sent.append(
                    {
                        "message_id": message_id,
                        "content": content,
                        "timestamp": datetime.now().isoformat(),
                        "chat_stream_id": self.chat_stream_id,
                    }
                )
                logger.debug(f"发送消息: {content}")
                return True
            else:
                logger.error("发送消息失败")
                return False

        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            return False

    async def listen_for_responses(self, timeout: float = 30.0) -> List[Dict]:
        """监听回复消息"""
        if not self.tenant_client:
            logger.error("租户客户端未连接")
            return []

        # 清空之前的接收消息列表
        self.messages_received.clear()

        # 清空事件并等待消息
        self.message_received_event.clear()

        try:
            # 等待消息接收事件，最多等待timeout秒
            await asyncio.wait_for(self.message_received_event.wait(), timeout=timeout)
            logger.debug("收到回复消息")
        except asyncio.TimeoutError:
            logger.debug("等待回复超时")

        return self.messages_received

    async def close(self):
        """关闭连接"""
        if self.tenant_client:
            try:
                await self.tenant_client.disconnect()
                logger.info(f"租户模式WebSocket连接已关闭: {self.user.username}")
            except Exception as e:
                logger.error(f"关闭连接失败: {e}")
            finally:
                self.tenant_client = None


class MultiWebSocketTestRunner:
    """多WebSocket测试运行器"""

    def __init__(self, reply_server_url: str = "ws://localhost:8095"):
        self.reply_server_url = reply_server_url
        self.clients: List[WebSocketChatClient] = []
        self.test_results: List[Dict] = []

    async def create_conversation_scenarios(
        self, users: List[TestUser], agents: List[TestAgent]
    ) -> List[ConversationScenario]:
        """创建对话场景"""
        scenarios = []

        # 定义对话主题
        topics_by_agent = {
            "friendly_assistant": ["你好，请介绍一下自己", "你喜欢做什么", "有什么兴趣爱好", "能给些建议吗"],
            "professional_expert": [
                "请解释一下人工智能",
                "机器学习的原理是什么",
                "深度学习和机器学习的区别",
                "AI的未来发展",
            ],
            "creative_companion": ["我们一起创作个故事吧", "给我一些创意灵感", "如何提高创造力", "分享一个有趣的想法"],
            "caring_friend": ["最近心情怎么样", "有什么烦恼吗", "如何保持积极心态", "分享一些快乐的事情"],
            "efficient_helper": ["如何提高工作效率", "有什么好的时间管理方法", "如何避免拖延", "推荐一些生产力工具"],
        }

        # 为每个用户和Agent创建场景
        for user in users:
            for j, agent in enumerate(user.agents):
                if j < len(agents):
                    matched_agent = next((a for a in agents if a.agent_id == agent["agent_id"]), None)
                    if matched_agent:
                        topics = topics_by_agent.get(
                            matched_agent.template_id, ["你好", "今天天气怎么样", "聊聊天吧", "有什么有趣的事情吗"]
                        )

                        scenario = ConversationScenario(
                            name=f"{user.username}_与_{agent['name']}_对话",
                            topics=topics,
                            message_count=min(len(topics), 5),  # 限制消息数量
                            user_id=user.user_id,
                            user_nickname=user.username,
                            tenant_id=user.tenant_id,
                        )
                        scenarios.append(scenario)

        return scenarios

    async def run_conversation_tests(self, users: List[TestUser], agents: List[TestAgent]) -> Dict:
        """运行对话测试"""
        logger.info(f"开始WebSocket对话测试: {len(users)} 用户, {len(agents)} Agent")

        # 创建对话场景
        scenarios = await self.create_conversation_scenarios(users, agents)
        logger.info(f"创建了 {len(scenarios)} 个对话场景")

        results = {
            "total_scenarios": len(scenarios),
            "successful_connections": 0,
            "successful_conversations": 0,
            "total_messages_sent": 0,
            "total_messages_received": 0,
            "average_response_time": 0,
            "scenarios": [],
        }

        # 并发运行场景测试
        tasks = []
        for scenario in scenarios:
            # 找到对应的用户和Agent
            user = next((u for u in users if u.username in scenario.name), None)
            agent_info = next((a for a in user.agents if a["name"] in scenario.name), None) if user else None

            if user and agent_info:
                agent = next((a for a in agents if a.agent_id == agent_info["agent_id"]), None)
                if agent:
                    tasks.append(self._run_single_scenario(scenario, user, agent))

        if tasks:
            scenario_results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in scenario_results:
                if isinstance(result, Exception):
                    logger.error(f"场景测试异常: {result}")
                else:
                    results["scenarios"].append(result)
                    results["successful_connections"] += result.get("connected", 0)
                    results["successful_conversations"] += result.get("conversation_completed", 0)
                    results["total_messages_sent"] += result.get("messages_sent", 0)
                    results["total_messages_received"] += result.get("messages_received", 0)

        # 计算平均响应时间
        if results["total_messages_received"] > 0:
            total_response_time = sum(
                s.get("average_response_time", 0) for s in results["scenarios"] if s.get("average_response_time")
            )
            results["average_response_time"] = total_response_time / len(results["scenarios"])

        logger.info("WebSocket对话测试完成:")
        logger.info(f"  成功连接: {results['successful_connections']}/{results['total_scenarios']}")
        logger.info(f"  成功对话: {results['successful_conversations']}/{results['total_scenarios']}")
        logger.info(f"  发送消息: {results['total_messages_sent']}")
        logger.info(f"  收到回复: {results['total_messages_received']}")
        logger.info(f"  平均响应时间: {results['average_response_time']:.2f}s")

        return results

    async def _run_single_scenario(self, scenario: ConversationScenario, user: TestUser, agent: TestAgent) -> Dict:
        """运行单个对话场景"""
        result = {
            "scenario_name": scenario.name,
            "user": user.username,
            "agent": agent.name,
            "connected": False,
            "conversation_completed": False,
            "messages_sent": 0,
            "messages_received": 0,
            "average_response_time": 0,
            "start_time": datetime.now().isoformat(),
            "end_time": None,
            "error": None,
        }

        client = WebSocketChatClient(self.reply_server_url)

        try:
            # 连接WebSocket
            if not await client.connect(user, agent):
                result["error"] = "WebSocket连接失败"
                return result

            result["connected"] = True

            # 发送消息并等待回复
            response_times = []

            for i, topic in enumerate(scenario.topics[: scenario.message_count]):
                start_time = time.time()

                # 发送消息
                message_id = f"{scenario.name}_{i}_{int(start_time * 1000)}"
                if await client.send_message(topic, message_id):
                    result["messages_sent"] += 1

                    # 等待回复
                    responses = await client.listen_for_responses(timeout=10.0)

                    if responses:
                        result["messages_received"] += 1
                        response_time = time.time() - start_time
                        response_times.append(response_time)

                        # 消息间隔
                        await asyncio.sleep(random.uniform(1.0, 3.0))
                    else:
                        logger.warning(f"未收到回复: {topic}")

            result["conversation_completed"] = True

            # 计算平均响应时间
            if response_times:
                result["average_response_time"] = sum(response_times) / len(response_times)

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"场景测试失败 {scenario.name}: {e}")

        finally:
            result["end_time"] = datetime.now().isoformat()
            await client.close()

        return result


# 便捷函数
async def run_websocket_tests(
    users: List[TestUser], agents: List[TestAgent], reply_server_url: str = "ws://localhost:8095"
) -> Dict:
    """运行WebSocket测试"""
    runner = MultiWebSocketTestRunner(reply_server_url)
    return await runner.run_conversation_tests(users, agents)
