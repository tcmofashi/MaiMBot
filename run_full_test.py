#!/usr/bin/env python3
"""
MaiMBot 完整测试运行器
一键启动双后端并运行完整集成测试
"""

import asyncio
import sys
import os
import subprocess
import signal
import logging
from pathlib import Path
from typing import Optional
import json

# 设置项目根目录
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("full_test.log", encoding="utf-8")],
)
logger = logging.getLogger(__name__)


class FullTestRunner:
    """完整测试运行器"""

    def __init__(self):
        self.config_process: Optional[subprocess.Popen] = None
        self.reply_process: Optional[subprocess.Popen] = None
        self.project_root = project_root
        self.running = False

    def cleanup_processes(self):
        """清理所有进程"""
        logger.info("正在清理所有进程...")

        # 停止配置器后端
        if self.config_process:
            try:
                self.config_process.terminate()
                self.config_process.wait(timeout=5)
                logger.info("配置器后端已停止")
            except subprocess.TimeoutExpired:
                self.config_process.kill()
                logger.warning("强制杀死配置器后端进程")
            except Exception as e:
                logger.error(f"停止配置器后端失败: {e}")

        # 停止回复后端
        if self.reply_process:
            try:
                self.reply_process.terminate()
                self.reply_process.wait(timeout=5)
                logger.info("回复后端已停止")
            except subprocess.TimeoutExpired:
                self.reply_process.kill()
                logger.warning("强制杀死回复后端进程")
            except Exception as e:
                logger.error(f"停止回复后端失败: {e}")

        # 清理PID文件
        for pid_file in [".config_backend.pid", ".reply_backend.pid"]:
            pid_path = self.project_root / pid_file
            if pid_path.exists():
                try:
                    pid_path.unlink()
                except Exception as e:
                    logger.error(f"删除PID文件 {pid_file} 失败: {e}")

        self.config_process = None
        self.reply_process = None
        self.running = False

    def check_port_available(self, port: int) -> bool:
        """检查端口是否可用"""
        import socket

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                result = sock.connect_ex(("localhost", port))
                return result != 0  # 0表示连接成功，意味着端口被占用
        except Exception as e:
            logger.error(f"检查端口 {port} 失败: {e}")
            return False

    async def start_config_backend(self) -> bool:
        """启动配置器后端"""
        try:
            # 检查端口
            if not self.check_port_available(8000):
                logger.error("端口 8000 已被占用，请检查是否有其他服务运行")
                return False

            logger.info("启动配置器后端...")

            env = os.environ.copy()
            env["PYTHONPATH"] = str(self.project_root)

            # 切换到项目根目录
            os.chdir(self.project_root)

            self.config_process = subprocess.Popen(
                [sys.executable, "-m", "src.api.main"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
            )

            # 保存PID
            with open(self.project_root / ".config_backend.pid", "w") as f:
                f.write(str(self.config_process.pid))

            # 等待服务启动
            for i in range(60):  # 等待60秒
                if self.config_process.poll() is not None:
                    stdout, _ = self.config_process.communicate()
                    logger.error(f"配置器后端启动失败: {stdout}")
                    return False

                try:
                    import aiohttp

                    async with aiohttp.ClientSession() as session:
                        async with session.get("http://localhost:8000/health", timeout=2) as response:
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
            # 检查端口
            if not self.check_port_available(8095):
                logger.error("端口 8095 已被占用，请检查是否有其他服务运行")
                return False

            logger.info("启动回复后端...")

            env = os.environ.copy()
            env["PYTHONPATH"] = str(self.project_root)

            self.reply_process = subprocess.Popen(
                [sys.executable, "bot.py"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env
            )

            # 保存PID
            with open(self.project_root / ".reply_backend.pid", "w") as f:
                f.write(str(self.reply_process.pid))

            # 等待服务启动
            for i in range(60):  # 等待60秒
                if self.reply_process.poll() is not None:
                    stdout, stderr = self.reply_process.communicate()
                    logger.error(f"回复后端启动失败: {stdout}")
                    return False

                # 检查端口是否可访问
                if self.check_port_available(8095):
                    # 端口仍可用，说明服务还没启动
                    pass
                else:
                    # 端口被占用，说明服务已启动
                    logger.info("回复后端启动成功")
                    return True

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

    async def run_integration_test(self, user_count: int = 3, agents_per_user: int = 2) -> bool:
        """运行集成测试"""
        try:
            logger.info(f"开始运行集成测试: {user_count} 用户, 每用户 {agents_per_user} Agent")

            # 导入测试运行器
            from integration_tests.test_runner import IntegrationTestRunner

            test_runner = IntegrationTestRunner()
            result = await test_runner.run_full_test(
                user_count=user_count, agents_per_user=agents_per_user, cleanup_after=True
            )

            if result["success"]:
                logger.info("集成测试成功完成!")
                logger.info(f"测试结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
                return True
            else:
                logger.error("集成测试失败!")
                logger.error(f"错误信息: {result.get('error', '未知错误')}")
                return False

        except Exception as e:
            logger.error(f"运行集成测试失败: {e}")
            import traceback

            traceback.print_exc()
            return False

    async def run_full_test(self, user_count: int = 3, agents_per_user: int = 2, cleanup_after: bool = True) -> bool:
        """运行完整测试流程"""
        try:
            logger.info("=" * 60)
            logger.info("MaiMBot 完整测试开始")
            logger.info("=" * 60)

            # 1. 启动双后端
            if not await self.start_all_servers():
                logger.error("启动服务失败，测试终止")
                return False

            # 2. 运行集成测试
            test_success = await self.run_integration_test(user_count, agents_per_user)

            # 3. 清理（如果需要）
            if cleanup_after:
                logger.info("正在清理服务...")
                self.cleanup_processes()

            logger.info("=" * 60)
            if test_success:
                logger.info("完整测试成功完成!")
            else:
                logger.error("完整测试失败!")
            logger.info("=" * 60)

            return test_success

        except Exception as e:
            logger.error(f"运行完整测试失败: {e}")
            import traceback

            traceback.print_exc()
            self.cleanup_processes()
            return False

    def setup_signal_handlers(self):
        """设置信号处理器"""

        def signal_handler(signum, frame):
            logger.info(f"收到信号 {signum}，正在清理...")
            self.cleanup_processes()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)


async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="MaiMBot 完整测试运行器")
    parser.add_argument("--users", type=int, default=3, help="用户数量 (默认: 3)")
    parser.add_argument("--agents", type=int, default=2, help="每个用户的Agent数量 (默认: 2)")
    parser.add_argument("--no-cleanup", action="store_true", help="测试后不清理服务")
    parser.add_argument("--start-only", action="store_true", help="只启动服务，不运行测试")

    args = parser.parse_args()

    runner = FullTestRunner()
    runner.setup_signal_handlers()

    try:
        if args.start_only:
            # 只启动服务
            success = await runner.start_all_servers()
            if success:
                logger.info("服务已启动，按 Ctrl+C 停止...")
                # 保持运行
                while runner.running:
                    await asyncio.sleep(1)
        else:
            # 运行完整测试
            success = await runner.run_full_test(
                user_count=args.users, agents_per_user=args.agents, cleanup_after=not args.no_cleanup
            )

        return 0 if success else 1

    except KeyboardInterrupt:
        logger.info("用户中断，正在清理...")
        runner.cleanup_processes()
        return 1
    except Exception as e:
        logger.error(f"运行失败: {e}")
        runner.cleanup_processes()
        return 1


if __name__ == "__main__":
    # 激活conda环境（如果需要）
    if os.system("conda activate maibot > /dev/null 2>&1") != 0:
        logger.warning("无法激活conda环境 maibot，使用当前环境")

    # 运行主程序
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
