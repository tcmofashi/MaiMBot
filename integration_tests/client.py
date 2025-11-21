"""
多租户测试客户端

模拟多个租户、智能体和平台的并发消息发送
"""

import asyncio
import json
import logging
import random
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import uuid

from maim_message import BaseMessageInfo, UserInfo, GroupInfo, SenderInfo, ReceiverInfo, Seg
from maim_message.message import APIMessageBase, MessageDim
from maim_message.client import WebSocketClient, create_client_config

from .config import TestConfig, TestScenario
from .message_generator import LLMMessageGenerator, GeneratedMessage

logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """测试结果"""

    scenario_name: str
    tenant_id: str
    agent_id: str
    platform: str
    messages_sent: int
    messages_received: int
    errors: List[str]
    start_time: float
    end_time: float
    success_rate: float = 0.0

    def __post_init__(self):
        if self.messages_sent > 0:
            self.success_rate = (self.messages_received / self.messages_sent) * 100


class MultiTenantTestClient:
    """多租户测试客户端"""

    def __init__(self, config: TestConfig, server_url: str = "http://localhost:8000"):
        self.config = config

        # 确保server_url是字符串类型
        if isinstance(server_url, int):
            # 如果传入的是整数，假设是端口号
            self.server_url = f"http://localhost:{server_url}"
            logger.warning(f"MultiTenantTestClient接收到整数端口号 {server_url}，已转换为URL: {self.server_url}")
        elif isinstance(server_url, str):
            self.server_url = server_url
        else:
            # 其他类型转换为字符串
            self.server_url = str(server_url)
            logger.warning(
                f"MultiTenantTestClient接收到非字符串URL {server_url} (类型: {type(server_url)})，已转换为: {self.server_url}"
            )

        # 创建WebSocket客户端配置
        if "localhost" in self.server_url:
            try:
                # 将http://localhost:port转换为ws://localhost:port/ws
                port = int(self.server_url.split(":")[-1])
                ws_url = f"ws://localhost:{port}/ws"
            except (ValueError, IndexError) as e:
                logger.error(f"无法从URL {self.server_url} 解析端口号: {e}")
                # 默认配置
                ws_url = "ws://localhost:8000/ws"
        else:
            # 默认配置
            ws_url = "ws://localhost:8000/ws"

        # 创建客户端配置，使用默认API密钥
        client_config = create_client_config(url=ws_url, api_key="test_client_key")
        self.message_server = WebSocketClient(client_config)
        self.message_generator = LLMMessageGenerator(self.config.llm)
        self.results: List[TestResult] = []

    async def run_all_scenarios(self) -> List[TestResult]:
        """运行所有测试场景"""
        logger.info(f"开始运行 {len(self.config.scenarios)} 个测试场景")

        tasks = []
        for scenario in self.config.scenarios:
            task = asyncio.create_task(self.run_scenario(scenario))
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"场景运行异常: {result}")
            elif isinstance(result, TestResult):
                self.results.append(result)

        logger.info(f"测试完成，共处理 {len(self.results)} 个场景")
        return self.results

    async def run_scenario(self, scenario: TestScenario) -> TestResult:
        """运行单个测试场景"""
        logger.info(f"开始运行场景: {scenario.name}")

        # 获取相关配置
        tenant_config = self.config.get_tenant(scenario.tenant_id)
        agent_config = self.config.get_agent(scenario.agent_id)

        if not tenant_config:
            raise ValueError(f"未找到租户配置: {scenario.tenant_id}")
        if not agent_config:
            raise ValueError(f"未找到智能体配置: {scenario.agent_id}")

        start_time = time.time()
        result = TestResult(
            scenario_name=scenario.name,
            tenant_id=scenario.tenant_id,
            agent_id=scenario.agent_id,
            platform=scenario.platform,
            messages_sent=0,
            messages_received=0,
            errors=[],
            start_time=start_time,
            end_time=start_time,  # 临时设置，稍后更新
        )

        try:
            # 生成测试消息
            messages = await self.message_generator.generate_conversation_messages(
                scenario, agent_config, tenant_config
            )

            logger.info(f"为场景 {scenario.name} 生成了 {len(messages)} 条消息")

            # 发送消息
            for message in messages:
                try:
                    await self._send_message(message, scenario)
                    result.messages_sent += 1

                    # 添加随机延迟
                    delay = random.uniform(self.config.message_delay_min, self.config.message_delay_max)
                    await asyncio.sleep(delay)

                    # 模拟收到回复
                    if random.random() < 0.8:  # 80%的概率收到回复
                        result.messages_received += 1

                except Exception as e:
                    error_msg = f"发送消息失败: {e}"
                    logger.error(error_msg)
                    result.errors.append(error_msg)

        except Exception as e:
            error_msg = f"场景运行失败: {e}"
            logger.error(error_msg)
            result.errors.append(error_msg)

        result.end_time = time.time()
        logger.info(f"场景 {scenario.name} 完成，发送: {result.messages_sent}, 接收: {result.messages_received}")

        return result

    async def _send_message(self, message: GeneratedMessage, scenario: TestScenario):
        """发送单条消息"""

        try:
            # 确保客户端已连接
            if not self.message_server.is_connected():
                logger.info("建立WebSocket连接...")
                await self.message_server.start()
                await asyncio.sleep(1)  # 等待连接建立

            # 构建用户信息
            user_info = UserInfo(
                user_id=message.user_id, user_nickname=f"测试用户_{message.user_id}", platform=message.platform
            )

            # 构建发送者信息
            sender_info = SenderInfo(user_info=user_info)

            # 构建群组信息（如果是群聊）
            group_info = None
            if message.group_id:
                group_info = GroupInfo(
                    group_id=message.group_id, group_name=f"测试群组_{message.group_id}", platform=message.platform
                )
                # 在发送者信息中包含群组信息
                sender_info = SenderInfo(user_info=user_info, group_info=group_info)

            # 构建接收者信息
            bot_user_info = UserInfo(user_id="bot", user_nickname="MaiBot", platform=message.platform)
            receiver_info = ReceiverInfo(user_info=bot_user_info)

            # 构建消息基础信息 - 使用新的sender_info/receiver_info结构
            message_info = BaseMessageInfo(
                platform=message.platform,
                message_id=str(uuid.uuid4()),
                time=message.timestamp,
                sender_info=sender_info,
                receiver_info=receiver_info,
                additional_config={
                    # 添加多租户隔离信息
                    "tenant_id": message.tenant_id,
                    "agent_id": message.agent_id,
                    "isolation_context": {
                        "tenant_id": message.tenant_id,
                        "agent_id": message.agent_id,
                        "platform": message.platform,
                        "chat_stream_id": f"{message.tenant_id}_{message.agent_id}_{scenario.group_id or message.user_id}",
                    },
                },
            )

            # 构建消息对象（这里简化处理，使用文本内容）
            message_segment = Seg(type="text", data=message.content)

            # 构建MessageDim用于APIMessageBase
            message_dim = MessageDim(api_key=f"{message.tenant_id}:{message.agent_id}", platform=message.platform)

            # 创建APIMessageBase对象
            message_obj = APIMessageBase(
                message_info=message_info, message_segment=message_segment, message_dim=message_dim
            )

            # 直接发送消息
            response = await self.message_server.send_message(message_obj)
            logger.debug(f"消息发送成功: {message.content[:50]}...")
            return response

        except Exception as e:
            logger.error(f"消息发送失败: {e}")
            raise

    async def run_concurrent_test(self, concurrent_users: int = None) -> Dict[str, Any]:
        """运行并发测试"""
        if concurrent_users is None:
            concurrent_users = self.config.concurrent_users

        logger.info(f"开始并发测试，并发用户数: {concurrent_users}")

        start_time = time.time()

        # 复制场景以支持并发
        all_scenarios = []
        for i in range(concurrent_users):
            for scenario in self.config.scenarios:
                # 为每个用户创建独立的场景副本
                concurrent_scenario = TestScenario(
                    name=f"{scenario.name}_user_{i}",
                    description=scenario.description,
                    tenant_id=scenario.tenant_id,
                    agent_id=scenario.agent_id,
                    platform=scenario.platform,
                    user_id=f"{scenario.user_id}_{i}",
                    group_id=scenario.group_id,
                    message_count=max(1, scenario.message_count // concurrent_users),
                    conversation_topics=scenario.conversation_topics.copy(),
                    settings=scenario.settings.copy(),
                )
                all_scenarios.append(concurrent_scenario)

        # 限制总场景数
        max_scenarios = 50
        if len(all_scenarios) > max_scenarios:
            all_scenarios = all_scenarios[:max_scenarios]
            logger.info(f"场景数过多，限制为 {max_scenarios} 个")

        # 并发运行场景
        tasks = []
        for scenario in all_scenarios:
            task = asyncio.create_task(self.run_scenario(scenario))
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 统计结果
        total_messages_sent = 0
        total_messages_received = 0
        total_errors = 0
        successful_scenarios = 0

        for result in results:
            if isinstance(result, TestResult):
                total_messages_sent += result.messages_sent
                total_messages_received += result.messages_received
                total_errors += len(result.errors)
                if result.success_rate > 50:  # 成功率超过50%认为成功
                    successful_scenarios += 1

        end_time = time.time()
        duration = end_time - start_time

        summary = {
            "concurrent_users": concurrent_users,
            "total_scenarios": len(all_scenarios),
            "successful_scenarios": successful_scenarios,
            "total_messages_sent": total_messages_sent,
            "total_messages_received": total_messages_received,
            "total_errors": total_errors,
            "overall_success_rate": (total_messages_received / total_messages_sent * 100)
            if total_messages_sent > 0
            else 0,
            "duration_seconds": duration,
            "messages_per_second": total_messages_sent / duration if duration > 0 else 0,
            "start_time": start_time,
            "end_time": end_time,
        }

        logger.info(f"并发测试完成: {json.dumps(summary, indent=2, ensure_ascii=False)}")
        return summary

    def generate_report(self) -> str:
        """生成测试报告"""
        if not self.results:
            return "没有测试结果"

        report_lines = [
            "=== 多租户集成测试报告 ===",
            f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"测试场景数: {len(self.results)}",
            "",
        ]

        # 总体统计
        total_messages_sent = sum(r.messages_sent for r in self.results)
        total_messages_received = sum(r.messages_received for r in self.results)
        total_errors = sum(len(r.errors) for r in self.results)

        report_lines.extend(
            [
                "=== 总体统计 ===",
                f"总发送消息数: {total_messages_sent}",
                f"总接收消息数: {total_messages_received}",
                f"总错误数: {total_errors}",
                f"总体成功率: {(total_messages_received / total_messages_sent * 100):.2f}%"
                if total_messages_sent > 0
                else "总体成功率: 0%",
                "",
            ]
        )

        # 按场景统计
        report_lines.append("=== 场景详情 ===")
        for result in self.results:
            report_lines.extend(
                [
                    f"场景: {result.scenario_name}",
                    f"  租户: {result.tenant_id}",
                    f"  智能体: {result.agent_id}",
                    f"  平台: {result.platform}",
                    f"  发送消息: {result.messages_sent}",
                    f"  接收消息: {result.messages_received}",
                    f"  成功率: {result.success_rate:.2f}%",
                    f"  耗时: {result.end_time - result.start_time:.2f}秒",
                ]
            )

            if result.errors:
                report_lines.append("  错误:")
                for error in result.errors[:3]:  # 只显示前3个错误
                    report_lines.append(f"    - {error}")
                if len(result.errors) > 3:
                    report_lines.append(f"    ... 还有 {len(result.errors) - 3} 个错误")

            report_lines.append("")

        return "\n".join(report_lines)

    async def cleanup(self):
        """清理资源"""
        try:
            # 清理WebSocket连接
            if hasattr(self.message_server, "stop"):
                await self.message_server.stop()
            elif hasattr(self.message_server, "close"):
                await self.message_server.close()
        except Exception as e:
            logger.error(f"清理资源失败: {e}")


class TestRunner:
    """测试运行器"""

    def __init__(self, config_path: Optional[str] = None):
        if config_path:
            self.config = TestConfig.from_toml(config_path)
        else:
            self.config = self._create_default_config()

        self.client = MultiTenantTestClient(self.config)

    def _create_default_config(self) -> TestConfig:
        """创建默认配置"""
        from .config import create_default_config

        return create_default_config()

    async def run_test(self, mode: str = "all", concurrent_users: int = None) -> Dict[str, Any]:
        """运行测试"""

        # 设置日志级别
        logging.basicConfig(
            level=getattr(logging, self.config.log_level.upper()),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

        logger.info("开始多租户集成测试")

        try:
            if mode == "all":
                # 运行所有场景
                results = await self.client.run_all_scenarios()

                # 运行并发测试
                concurrent_result = await self.client.run_concurrent_test(concurrent_users)

                return {
                    "scenario_results": results,
                    "concurrent_test": concurrent_result,
                    "report": self.client.generate_report(),
                }

            elif mode == "concurrent":
                # 只运行并发测试
                return await self.client.run_concurrent_test(concurrent_users)

            elif mode == "scenarios":
                # 只运行场景测试
                results = await self.client.run_all_scenarios()
                return {"scenario_results": results, "report": self.client.generate_report()}

            else:
                raise ValueError(f"不支持的测试模式: {mode}")

        finally:
            await self.client.cleanup()
