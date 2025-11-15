"""
集成测试主运行器
协调整个测试流程：用户注册 -> Agent创建 -> WebSocket对话 -> 数据清理
"""

import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# 添加项目根目录到Python路径
current_path = Path(__file__).resolve()
project_root = current_path.parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from .api_client import create_test_scenario, TestUser, TestAgent  # noqa: E402
from .websocket_test import run_websocket_tests  # noqa: E402
from .cleanup_test import cleanup_test_scenario  # noqa: E402

logger = logging.getLogger(__name__)


class ServerManager:
    """服务器管理器"""

    def __init__(self):
        self.config_process: Optional[subprocess.Popen] = None
        self.reply_process: Optional[subprocess.Popen] = None
        self.config_url = "http://localhost:18000"
        self.reply_url = "ws://localhost:8095/ws"

    async def start_config_server(self) -> bool:
        """启动配置器后端"""
        try:
            logger.info("启动配置器后端...")
            env = os.environ.copy()
            env["PYTHONPATH"] = str(project_root)
            # 设置配置器后端端口为18000
            env["PORT"] = "18000"

            self.config_process = subprocess.Popen(
                [sys.executable, "-m", "src.api.main"],
                cwd=str(project_root),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # 等待服务启动
            for _i in range(30):  # 等待30秒
                if self.config_process.poll() is not None:
                    stdout, stderr = self.config_process.communicate()
                    logger.error(f"配置器后端启动失败: {stderr}")
                    return False

                try:
                    import aiohttp

                    async with aiohttp.ClientSession() as session:
                        async with session.get(f"{self.config_url}/health", timeout=5) as response:
                            if response.status == 200:
                                logger.info("配置器后端启动成功")
                                return True
                except Exception:
                    pass

                await asyncio.sleep(1)

            logger.error("配置器后端启动超时")
            return False

        except Exception as e:
            logger.error(f"启动配置器后端失败: {e}")
            return False

    async def start_reply_server(self) -> bool:
        """启动回复后端"""
        try:
            logger.info("启动回复后端...")
            env = os.environ.copy()
            env["PYTHONPATH"] = str(project_root)

            self.reply_process = subprocess.Popen(
                [sys.executable, "bot.py"],
                cwd=str(project_root),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # 等待服务启动
            for _i in range(60):  # 等待60秒
                if self.reply_process.poll() is not None:
                    stdout, stderr = self.reply_process.communicate()
                    logger.error(f"回复后端启动失败: {stderr}")
                    return False

                # 检查端口是否可访问
                try:
                    import socket

                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    result = sock.connect_ex(("localhost", 8095))
                    sock.close()
                    if result == 0:
                        logger.info("回复后端启动成功")
                        return True
                except Exception:
                    pass

                await asyncio.sleep(1)

            logger.error("回复后端启动超时")
            return False

        except Exception as e:
            logger.error(f"启动回复后端失败: {e}")
            return False

    async def stop_servers(self):
        """停止所有服务器"""
        logger.info("停止服务器...")

        if self.config_process:
            self.config_process.terminate()
            try:
                self.config_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.config_process.kill()
            logger.info("配置器后端已停止")

        if self.reply_process:
            self.reply_process.terminate()
            try:
                self.reply_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.reply_process.kill()
            logger.info("回复后端已停止")

    def is_running(self) -> bool:
        """检查服务器是否运行中"""
        return (
            self.config_process
            and self.config_process.poll() is None
            and self.reply_process
            and self.reply_process.poll() is None
        )


class IntegrationTestRunner:
    """集成测试运行器"""

    def __init__(self, config_url: str = "http://localhost:8000", reply_url: str = "ws://localhost:8095/ws"):
        # 确保config_url是字符串类型
        if isinstance(config_url, int):
            # 如果传入的是整数，假设是端口号
            self.config_url = f"http://localhost:{config_url}"
            logger.warning(f"IntegrationTestRunner接收到整数端口号 {config_url}，已转换为URL: {self.config_url}")
        elif isinstance(config_url, str):
            self.config_url = config_url
        else:
            # 其他类型转换为字符串
            self.config_url = str(config_url)
            logger.warning(
                f"IntegrationTestRunner接收到非字符串URL {config_url} (类型: {type(config_url)})，已转换为: {self.config_url}"
            )

        # 确保reply_url是字符串类型
        if isinstance(reply_url, int):
            # 如果传入的是整数，假设是端口号
            self.reply_url = f"ws://localhost:{reply_url}"
            logger.warning(
                f"IntegrationTestRunner接收到整数端口号 {reply_url}，已转换为WebSocket URL: {self.reply_url}"
            )
        elif isinstance(reply_url, str):
            self.reply_url = reply_url
        else:
            # 其他类型转换为字符串
            self.reply_url = str(reply_url)
            logger.warning(
                f"IntegrationTestRunner接收到非字符串WebSocket URL {reply_url} (类型: {type(reply_url)})，已转换为: {self.reply_url}"
            )

        self.server_manager = ServerManager()
        self.test_results: Dict = {}

    async def run_full_test(self, user_count: int = 3, agents_per_user: int = 2, cleanup_after: bool = True) -> Dict:
        """运行完整测试流程"""
        start_time = time.time()
        test_id = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        logger.info(f"开始集成测试: {test_id}")
        logger.info(f"参数: {user_count} 用户, 每用户 {agents_per_user} Agent")

        results = {
            "test_id": test_id,
            "start_time": datetime.now().isoformat(),
            "parameters": {
                "user_count": user_count,
                "agents_per_user": agents_per_user,
                "cleanup_after": cleanup_after,
            },
            "servers_started": False,
            "user_creation": None,
            "websocket_tests": None,
            "cleanup": None,
            "end_time": None,
            "duration_seconds": 0,
            "success": False,
            "errors": [],
        }

        try:
            # 1. 启动服务器
            if not await self._start_servers():
                results["errors"].append("服务器启动失败")
                return results

            results["servers_started"] = True

            # 2. 创建测试用户和Agent
            logger.info("步骤1: 创建测试用户和Agent")
            users, agents = await create_test_scenario(self.config_url, user_count, agents_per_user)

            results["user_creation"] = {
                "success": True,
                "users_created": len(users),
                "agents_created": len(agents),
                "test_data": self._format_test_data(users, agents),
            }

            if not users:
                results["errors"].append("用户创建失败")
                return results

            # 3. 运行WebSocket对话测试
            logger.info("步骤2: 运行WebSocket对话测试")
            await asyncio.sleep(2)  # 等待服务器完全就绪

            websocket_results = await run_websocket_tests(users, agents, self.reply_url)

            results["websocket_tests"] = websocket_results

            if websocket_results["successful_conversations"] == 0:
                results["errors"].append("WebSocket对话测试失败")

            # 4. 清理测试数据
            if cleanup_after:
                logger.info("步骤3: 清理测试数据")
                cleanup_results = await cleanup_test_scenario(users, agents, save_report=True)
                results["cleanup"] = cleanup_results

                if cleanup_results["total_errors"] > 0:
                    results["errors"].extend(cleanup_results["errors"])

            # 5. 计算最终结果
            results["success"] = (
                results["servers_started"]
                and results["user_creation"]["success"]
                and websocket_results["successful_conversations"] > 0
            )

            logger.info(f"集成测试完成: {'成功' if results['success'] else '失败'}")

        except Exception as e:
            error_msg = f"测试执行失败: {e}"
            logger.error(error_msg)
            results["errors"].append(error_msg)

        finally:
            # 停止服务器
            await self.server_manager.stop_servers()

        results["end_time"] = datetime.now().isoformat()
        results["duration_seconds"] = time.time() - start_time

        # 保存测试结果
        self._save_test_results(results)

        self.test_results = results
        return results

    async def _start_servers(self) -> bool:
        """启动服务器"""
        # 启动配置器后端
        if not await self.server_manager.start_config_server():
            return False

        # 启动回复后端
        if not await self.server_manager.start_reply_server():
            return False

        # 等待服务完全就绪
        await asyncio.sleep(3)
        return True

    def _format_test_data(self, users: List[TestUser], agents: List[TestAgent]) -> Dict:
        """格式化测试数据"""
        return {
            "users": [
                {"username": user.username, "tenant_id": user.tenant_id, "user_id": user.user_id, "agents": user.agents}
                for user in users
            ],
            "agents": [
                {
                    "agent_id": agent.agent_id,
                    "name": agent.name,
                    "tenant_id": agent.tenant_id,
                    "template_id": agent.template_id,
                }
                for agent in agents
            ],
        }

    def _save_test_results(self, results: Dict):
        """保存测试结果"""
        filename = f"integration_test_results_{results['test_id']}.json"
        filepath = project_root / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)

        logger.info(f"测试结果已保存到: {filepath}")

    def print_summary(self):
        """打印测试摘要"""
        if not self.test_results:
            print("没有测试结果可显示")
            return

        results = self.test_results
        print("\n" + "=" * 60)
        print("集成测试摘要")
        print("=" * 60)
        print(f"测试ID: {results['test_id']}")
        print(f"开始时间: {results['start_time']}")
        print(f"结束时间: {results['end_time']}")
        print(f"总耗时: {results['duration_seconds']:.2f} 秒")
        print(f"测试状态: {'✅ 成功' if results['success'] else '❌ 失败'}")

        print("\n参数:")
        params = results["parameters"]
        print(f"  用户数量: {params['user_count']}")
        print(f"  每用户Agent数: {params['agents_per_user']}")
        print(f"  事后清理: {'是' if params['cleanup_after'] else '否'}")

        if results["user_creation"]:
            user_creation = results["user_creation"]
            print("\n用户创建:")
            print(f"  成功用户: {user_creation['users_created']}")
            print(f"  创建Agent: {user_creation['agents_created']}")

        if results["websocket_tests"]:
            ws_tests = results["websocket_tests"]
            print("\nWebSocket测试:")
            print(f"  总场景数: {ws_tests['total_scenarios']}")
            print(f"  成功连接: {ws_tests['successful_connections']}")
            print(f"  成功对话: {ws_tests['successful_conversations']}")
            print(f"  发送消息: {ws_tests['total_messages_sent']}")
            print(f"  收到回复: {ws_tests['total_messages_received']}")
            print(f"  平均响应时间: {ws_tests['average_response_time']:.2f} 秒")

        if results["errors"]:
            print("\n错误信息:")
            for error in results["errors"]:
                print(f"  ❌ {error}")

        print("=" * 60)


# 全局测试运行器实例
test_runner = IntegrationTestRunner()


def signal_handler(signum, frame):
    """信号处理器"""
    logger.info("收到中断信号，正在清理...")
    asyncio.create_task(test_runner.server_manager.stop_servers())
    sys.exit(0)


# 注册信号处理器
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# 便捷函数
async def run_integration_test(user_count: int = 3, agents_per_user: int = 2, cleanup_after: bool = True) -> Dict:
    """运行集成测试"""
    runner = IntegrationTestRunner()
    results = await runner.run_full_test(user_count, agents_per_user, cleanup_after)
    runner.print_summary()
    return results


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="MaiBot 集成测试运行器")
    parser.add_argument("--users", type=int, default=3, help="测试用户数量")
    parser.add_argument("--agents", type=int, default=2, help="每用户Agent数量")
    parser.add_argument("--no-cleanup", action="store_true", help="不清理测试数据")
    parser.add_argument("--config-url", default="http://localhost:8000", help="配置器API地址")
    parser.add_argument("--reply-url", default="ws://localhost:8095/ws", help="WebSocket回复地址")

    args = parser.parse_args()

    # 设置日志
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    try:
        # 运行测试
        results = asyncio.run(
            run_integration_test(user_count=args.users, agents_per_user=args.agents, cleanup_after=not args.no_cleanup)
        )

        # 根据结果设置退出码
        sys.exit(0 if results["success"] else 1)

    except KeyboardInterrupt:
        print("\n测试被用户中断")
        sys.exit(1)
    except Exception as e:
        logger.error(f"测试执行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
