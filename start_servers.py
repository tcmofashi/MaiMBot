#!/usr/bin/env python3
"""
MaiMBot 双后端一键启动脚本 (Python版本)
启动配置器后端和回复后端，并支持集成测试
"""

import argparse
import asyncio
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# 添加项目根目录到Python路径
current_path = Path(__file__).resolve()
project_root = current_path.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from integration_tests.test_runner import run_integration_test

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(project_root / "logs" / "startup.log", encoding="utf-8")],
)

logger = logging.getLogger(__name__)


class ServerManager:
    """服务器管理器"""

    def __init__(self):
        self.config_process: Optional[subprocess.Popen] = None
        self.reply_process: Optional[subprocess.Popen] = None
        self.config_url = "http://localhost:8000"
        self.reply_url = "ws://localhost:8095/ws"
        self.running = False

    async def start_config_backend(self) -> bool:
        """启动配置器后端"""
        try:
            logger.info("启动配置器后端...")

            # 确保日志目录存在
            (project_root / "logs").mkdir(exist_ok=True)

            # 启动配置器后端
            env = os.environ.copy()
            env["PYTHONPATH"] = str(project_root)

            self.config_process = subprocess.Popen(
                [sys.executable, "src/api/main.py"],
                cwd=str(project_root),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )

            # 保存PID
            with open(project_root / ".config_backend.pid", "w") as f:
                f.write(str(self.config_process.pid))

            # 等待服务启动
            for _i in range(30):  # 等待30秒
                if self.config_process.poll() is not None:
                    logger.error("配置器后端启动失败")
                    return False

                try:
                    import aiohttp

                    async with aiohttp.ClientSession() as session:
                        async with session.get(f"{self.config_url}/health", timeout=2) as response:
                            if response.status == 200:
                                logger.info("配置器后端启动成功")
                                return True
                except Exception:
                    pass

                await asyncio.sleep(1)
                print(".", end="", flush=True)

            print()
            logger.error("配置器后端启动超时")
            return False

        except Exception as e:
            logger.error(f"启动配置器后端失败: {e}")
            return False

    async def start_reply_backend(self) -> bool:
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
                stderr=subprocess.STDOUT,
                text=True,
            )

            # 保存PID
            with open(project_root / ".reply_backend.pid", "w") as f:
                f.write(str(self.reply_process.pid))

            # 等待服务启动
            for _i in range(60):  # 等待60秒
                if self.reply_process.poll() is not None:
                    logger.error("回复后端启动失败")
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
                print(".", end="", flush=True)

            print()
            logger.error("回复后端启动超时")
            return False

        except Exception as e:
            logger.error(f"启动回复后端失败: {e}")
            return False

    async def start_all_servers(self) -> bool:
        """启动所有服务器"""
        logger.info("启动 MaiMBot 双后端服务...")

        # 启动配置器后端
        if not await self.start_config_backend():
            return False

        # 启动回复后端
        if not await self.start_reply_backend():
            return False

        # 等待服务完全就绪
        await asyncio.sleep(3)

        self.running = True
        logger.info("所有服务启动成功!")
        return True

    async def stop_servers(self):
        """停止所有服务器"""
        logger.info("停止所有服务...")

        stopped = []

        # 停止配置器后端
        config_pid_file = project_root / ".config_backend.pid"
        if config_pid_file.exists():
            try:
                with open(config_pid_file, "r") as f:
                    config_pid = int(f.read().strip())

                if self.config_process and self.config_process.poll() is None:
                    self.config_process.terminate()
                    try:
                        self.config_process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        self.config_process.kill()

                # 确保进程被停止
                try:
                    os.kill(config_pid, 0)  # 检查进程是否存在
                    os.kill(config_pid, 15)  # SIGTERM
                    time.sleep(2)
                    os.kill(config_pid, 0)  # 再次检查
                    os.kill(config_pid, 9)  # SIGTERM
                except OSError:
                    pass

                stopped.append("配置器后端")
                config_pid_file.unlink(missing_ok=True)

            except Exception as e:
                logger.error(f"停止配置器后端失败: {e}")

        # 停止回复后端
        reply_pid_file = project_root / ".reply_backend.pid"
        if reply_pid_file.exists():
            try:
                with open(reply_pid_file, "r") as f:
                    reply_pid = int(f.read().strip())

                if self.reply_process and self.reply_process.poll() is None:
                    self.reply_process.terminate()
                    try:
                        self.reply_process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        self.reply_process.kill()

                # 确保进程被停止
                try:
                    os.kill(reply_pid, 0)
                    os.kill(reply_pid, 15)
                    time.sleep(2)
                    os.kill(reply_pid, 0)
                    os.kill(reply_pid, 9)
                except OSError:
                    pass

                stopped.append("回复后端")
                reply_pid_file.unlink(missing_ok=True)

            except Exception as e:
                logger.error(f"停止回复后端失败: {e}")

        self.running = False
        self.config_process = None
        self.reply_process = None

        if stopped:
            logger.info(f"已停止: {', '.join(stopped)}")
        else:
            logger.info("没有运行中的服务需要停止")

    def is_running(self) -> bool:
        """检查服务是否运行中"""
        return self.running and (
            (self.config_process and self.config_process.poll() is None)
            or (self.reply_process and self.reply_process.poll() is None)
        )

    def show_status(self):
        """显示服务状态"""
        print("\n" + "=" * 50)
        print("MaiMBot 服务状态")
        print("=" * 50)

        # 配置器后端状态
        config_running = self.config_process and self.config_process.poll() is None
        if config_running:
            print(f"配置器后端: ✅ 运行中 (PID: {self.config_process.pid})")
            print(f"  API地址: {self.config_url}")
            print(f"  API文档: {self.config_url}/docs")
        else:
            print("配置器后端: ❌ 未运行")

        # 回复后端状态
        reply_running = self.reply_process and self.reply_process.poll() is None
        if reply_running:
            print(f"回复后端: ✅ 运行中 (PID: {self.reply_process.pid})")
            print(f"  WebSocket: {self.reply_url}")
        else:
            print("回复后端: ❌ 未运行")

        print("=" * 50)
        print("日志文件位置:")
        print("  启动日志: logs/startup.log")
        print("  配置器: logs/config_backend.log")
        print("  回复器: logs/reply_backend.log")
        print("=" * 50)


# 全局服务器管理器
server_manager = ServerManager()


def signal_handler(signum, frame):
    """信号处理器"""
    print(f"\n收到信号 {signum}，正在停止服务...")
    asyncio.create_task(server_manager.stop_servers())
    sys.exit(0)


# 注册信号处理器
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="MaiMBot 双后端管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python start_servers.py              # 启动服务
  python start_servers.py start        # 启动服务
  python start_servers.py stop         # 停止服务
  python start_servers.py restart      # 重启服务
  python start_servers.py status       # 查看状态
  python start_servers.py test         # 运行测试
        """,
    )

    parser.add_argument(
        "command",
        nargs="?",
        choices=["start", "stop", "restart", "status", "test"],
        default="start",
        help="要执行的命令",
    )

    parser.add_argument("--users", type=int, default=3, help="集成测试用户数量 (默认: 3)")

    parser.add_argument("--agents", type=int, default=2, help="集成测试每用户Agent数量 (默认: 2)")

    parser.add_argument("--no-cleanup", action="store_true", help="集成测试后不清理数据")

    args = parser.parse_args()

    try:
        if args.command == "start":
            if await server_manager.start_all_servers():
                server_manager.show_status()
                print("\n服务已启动，按 Ctrl+C 停止")
                # 保持服务运行
                try:
                    while server_manager.is_running():
                        await asyncio.sleep(1)
                except KeyboardInterrupt:
                    pass
            else:
                logger.error("服务启动失败")
                sys.exit(1)

        elif args.command == "stop":
            await server_manager.stop_servers()

        elif args.command == "restart":
            await server_manager.stop_servers()
            await asyncio.sleep(2)
            if await server_manager.start_all_servers():
                server_manager.show_status()
            else:
                logger.error("服务重启失败")
                sys.exit(1)

        elif args.command == "status":
            server_manager.show_status()

        elif args.command == "test":
            # 运行集成测试
            logger.info("运行集成测试...")
            results = await run_integration_test(
                user_count=args.users, agents_per_user=args.agents, cleanup_after=not args.no_cleanup
            )

            if results["success"]:
                logger.info("集成测试成功完成")
            else:
                logger.error("集成测试失败")
                sys.exit(1)

    except KeyboardInterrupt:
        print("\n操作被用户中断")
    except Exception as e:
        logger.error(f"执行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
