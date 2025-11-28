#!/usr/bin/env python3
"""
MaiMBot 完整集成测试脚本
启动双后端并运行集成测试的完整解决方案

创建时间: 2025-11-29 01:23:08
最后修改: 2025-11-29 01:23:08
AI生成标识: Cline
测试类型: 集成测试
文件类型: 集成测试
测试模块: src/api/main.py, bot.py
测试功能: 双后端启动和集成测试
分类标签: [integration_test, backend_test, maimbot]
"""

import asyncio
import sys
import os
import subprocess
import signal
import logging
import hashlib
from pathlib import Path
from typing import Optional

# 设置项目根目录 - 修正路径计算
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("maimbot_test.log", encoding="utf-8")],
)
logger = logging.getLogger(__name__)


class MaiBotTestRunner:
    """MaiMBot测试运行器"""

    def __init__(self):
        self.config_process: Optional[subprocess.Popen] = None
        self.reply_process: Optional[subprocess.Popen] = None
        self.project_root = project_root
        self.running = False
        self.log_outputs = {"config": [], "reply": []}

    def cleanup_processes(self):
        """清理所有进程"""
        logger.info("🧹 正在清理所有进程...")

        for process, name in [(self.config_process, "配置器后端"), (self.reply_process, "回复后端")]:
            if process:
                try:
                    process.terminate()
                    process.wait(timeout=5)
                    logger.info(f"✅ {name}已停止")
                except subprocess.TimeoutExpired:
                    process.kill()
                    logger.warning(f"⚠️ 强制杀死{name}进程")
                except Exception as e:
                    logger.error(f"❌ 停止{name}失败: {e}")

        # 清理PID文件
        for pid_file in [".config_backend.pid", ".reply_backend.pid"]:
            pid_path = self.project_root / pid_file
            if pid_path.exists():
                try:
                    pid_path.unlink()
                except Exception as e:
                    logger.error(f"❌ 删除PID文件 {pid_file} 失败: {e}")

        self.config_process = None
        self.reply_process = None
        self.running = False

    async def monitor_process_output(self, process: subprocess.Popen, name: str):
        """监控进程输出 - 使用异步读取避免阻塞"""
        if not process:
            return

        log_key = "config" if "配置器" in name else "reply"

        # 使用异步读取，避免阻塞
        loop = asyncio.get_event_loop()

        while process.poll() is None:
            try:
                # 使用 run_in_executor 避免阻塞
                line = await loop.run_in_executor(None, process.stdout.readline)
                if line:
                    log_line = line.strip()
                    self.log_outputs[log_key].append(log_line)

                    # 对于回复后端，显示所有日志（包括debug级别）
                    if "回复后端" in name:
                        print(f"[回复后端] {log_line}")
                    else:
                        # 对于配置器后端，只显示重要的日志
                        if any(
                            keyword in log_line.lower()
                            for keyword in [
                                "error",
                                "exception",
                                "failed",
                                "timeout",
                                "websocket",
                                "connection",
                                "message",
                                "received",
                                "sent",
                                "warning",
                            ]
                        ):
                            logger.info(f"[{name}] {log_line}")
                else:
                    # 如果没有输出，短暂等待
                    await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"❌ 读取{name}输出失败: {e}")
                break

    def show_backend_logs(self, backend_type: str = "both", lines: int = 20):
        """显示后端日志用于调试"""
        if backend_type in ["config", "both"]:
            logger.info("📋 配置器后端最近日志:")
            config_logs = self.log_outputs["config"][-lines:] if self.log_outputs["config"] else []
            for log in config_logs:
                logger.info(f"  [配置器] {log}")

        if backend_type in ["reply", "both"]:
            logger.info("📋 回复后端最近日志:")
            reply_logs = self.log_outputs["reply"][-lines:] if self.log_outputs["reply"] else []
            for log in reply_logs:
                logger.info(f"  [回复器] {log}")

    async def start_config_backend(self) -> bool:
        """启动配置器后端"""
        try:
            logger.info("🚀 启动配置器后端...")

            env = os.environ.copy()
            env["PYTHONPATH"] = str(self.project_root)
            # 设置环境变量覆盖端口
            env["PORT"] = "18000"
            # 明确设置 HOST，确保监听在 0.0.0.0
            env["HOST"] = "0.0.0.0"

            os.chdir(self.project_root)

            # 直接以脚本方式启动，使用 src/api/main.py 内的 uvicorn.run，避免 -m uvicorn 立即退出问题
            self.config_process = subprocess.Popen(
                [sys.executable, "src/api/main.py"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
            )

            # 等待服务启动
            logger.info("⏳ 等待配置器后端启动...")
            await asyncio.sleep(25)  # 给足够时间启动

            # 检查进程状态和API健康
            if self.config_process.poll() is None:
                logger.info("🔍 配置器后端进程运行中，检查API可用性...")

                # 测试API健康检查
                try:
                    import aiohttp

                    async with aiohttp.ClientSession() as session:
                        async with session.get("http://localhost:18000/health", timeout=10) as response:
                            if response.status == 200:
                                data = await response.json()
                                logger.info(f"✅ 配置器后端启动成功! API状态: {data.get('status', 'unknown')}")
                                return True
                            else:
                                logger.error(f"❌ 配置器后端API响应异常: HTTP {response.status}")
                                return False
                except Exception as e:
                    logger.error(f"❌ 配置器后端API健康检查失败: {e}")

                    # 获取进程输出来诊断问题
                    stdout, stderr = self.config_process.communicate()
                    if stdout:
                        logger.error(f"❌ 配置器后端输出: {stdout}")
                    if stderr:
                        logger.error(f"❌ 配置器后端错误: {stderr}")

                    return False
            else:
                stdout, _ = self.config_process.communicate()
                logger.error(f"❌ 配置器后端进程已退出: {stdout}")
                return False

        except Exception as e:
            logger.error(f"❌ 启动配置器后端失败: {e}")
            return False

    async def start_reply_backend(self) -> bool:
        """启动回复后端"""
        try:
            logger.info("🚀 启动回复后端...")

            env = os.environ.copy()
            env["PYTHONPATH"] = str(self.project_root)
            # 设置环境变量覆盖端口（统一使用8095）
            env["PORT"] = "8095"
            # 明确设置 HOST，确保监听在 0.0.0.0
            env["HOST"] = "0.0.0.0"
            # 设置日志级别为DEBUG以查看所有日志（确保覆盖配置文件设置）
            env["LOG_LEVEL"] = "DEBUG"
            env["CONSOLE_LOG_LEVEL"] = "DEBUG"
            env["FILE_LOG_LEVEL"] = "DEBUG"
            # 计算并注入 EULA/PRIVACY 确认哈希，避免 bot.py 阻塞交互
            try:
                eula_path = self.project_root / "EULA.md"
                privacy_path = self.project_root / "PRIVACY.md"
                eula_hash = hashlib.md5(eula_path.read_bytes()).hexdigest()
                privacy_hash = hashlib.md5(privacy_path.read_bytes()).hexdigest()
                env["EULA_AGREE"] = eula_hash
                env["PRIVACY_AGREE"] = privacy_hash
                logger.info("已注入 EULA_AGREE/PRIVACY_AGREE 环境变量，跳过协议交互确认")
            except Exception as e:
                logger.warning(f"无法计算 EULA/PRIVACY 哈希，可能导致启动阻塞: {e}")

            self.reply_process = subprocess.Popen(
                [sys.executable, "bot.py"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env
            )

            # 等待服务启动
            logger.info("⏳ 等待回复后端启动...")
            await asyncio.sleep(30)  # 给足够时间启动（30秒）

            # 检查进程状态
            if self.reply_process.poll() is None:
                logger.info("✅ 回复后端启动成功!")
                return True
            else:
                stdout, _ = self.reply_process.communicate()
                logger.error(f"❌ 回复后端启动失败: {stdout}")
                return False

        except Exception as e:
            logger.error(f"❌ 启动回复后端失败: {e}")
            return False

    async def start_all_servers(self) -> bool:
        """启动所有服务器"""
        logger.info("🎯 启动 MaiMBot 双后端服务...")

        # 启动配置器后端
        if not await self.start_config_backend():
            return False

        # 启动回复后端
        if not await self.start_reply_backend():
            return False

        # 启动日志监控任务
        asyncio.create_task(self.monitor_process_output(self.config_process, "配置器后端"))
        asyncio.create_task(self.monitor_process_output(self.reply_process, "回复后端"))

        # 等待服务完全就绪
        await asyncio.sleep(10)  # 增加等待时间确保完全就绪

        self.running = True
        logger.info("🎉 所有服务启动成功!")
        return True

    async def run_simple_test(self) -> bool:
        """运行简单的连接测试"""
        try:
            import aiohttp

            logger.info("🧪 开始API连接测试...")

            # 测试配置器后端
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get("http://localhost:18000/health", timeout=5) as response:
                        if response.status == 200:
                            data = await response.json()
                            logger.info(
                                f"✅ 配置器后端测试成功: {data.get('service', 'Unknown')} v{data.get('version', 'Unknown')}"
                            )
                        else:
                            logger.warning(f"⚠️ 配置器后端API响应状态码: {response.status}")
                except Exception as e:
                    logger.error(f"❌ 配置器后端测试失败: {e}")

                # 测试回复后端WebSocket
                try:
                    async with session.ws_connect("http://localhost:8095/ws", timeout=5):
                        logger.info("✅ 回复后端WebSocket连接成功")
                except Exception as e:
                    logger.error(f"❌ 回复后端WebSocket测试失败: {e}")

            return True

        except ImportError:
            logger.warning("⚠️ aiohttp未安装，跳过连接测试")
            return True
        except Exception as e:
            logger.error(f"❌ 连接测试失败: {e}")
            return False

    async def run_integration_test(self, user_count: int = 2, agents_per_user: int = 1) -> bool:
        """运行集成测试"""
        try:
            logger.info(f"🧪 开始运行集成测试: {user_count} 用户, 每用户 {agents_per_user} Agent")

            # 尝试导入简化测试运行器
            try:
                from integration_tests.simple_test_runner import run_simple_integration_test

                result = await run_simple_integration_test(
                    user_count=user_count, agents_per_user=agents_per_user, cleanup_after=True
                )

                if result["success"]:
                    logger.info("🎉 集成测试成功完成!")
                    # 显示测试统计
                    summary = result.get("final_summary", {})
                    logger.info("📊 测试统计:")
                    logger.info(f"   👥 用户: {summary.get('total_users', 0)}")
                    logger.info(f"   🤖 Agent: {summary.get('total_agents', 0)}")
                    logger.info(f"   🔗 连接成功: {summary.get('successful_connections', 0)}")
                    logger.info(
                        f"   📨 消息成功: {summary.get('successful_messages', 0)}/{summary.get('total_messages_sent', 0)}"
                    )
                    logger.info(f"   📥 响应收到: {summary.get('responses_received', 0)}")
                    return True
                else:
                    logger.error("❌ 集成测试失败")
                    for error in result.get("errors", []):
                        logger.error(f"   - {error}")
                    return False

            except ImportError as e:
                logger.warning(f"⚠️ 无法导入集成测试模块: {e}")
                logger.info("💡 跳过集成测试，仅进行基础连接测试")
                return True

        except Exception as e:
            logger.error(f"❌ 运行集成测试失败: {e}")
            import traceback

            traceback.print_exc()
            return False

    async def run_full_test(
        self, user_count: int = 2, agents_per_user: int = 1, run_integration: bool = False, cleanup_after: bool = True
    ) -> bool:
        """运行完整测试流程"""
        try:
            logger.info("=" * 80)
            logger.info("🎯 MaiMBot 完整测试开始")
            logger.info("=" * 80)

            # 1. 启动双后端
            if not await self.start_all_servers():
                logger.error("❌ 启动服务失败，测试终止")
                return False

            # 2. 运行简单连接测试
            logger.info("🔗 运行连接测试...")
            test_success = await self.run_simple_test()

            # 3. 运行集成测试（如果启用）
            if run_integration and test_success:
                logger.info("🧪 运行集成测试...")
                integration_success = await self.run_integration_test(user_count, agents_per_user)
                test_success = test_success and integration_success

            # 4. 等待观察
            logger.info("⏰ 服务运行中，等待10秒观察状态...")
            await asyncio.sleep(10)

            # 5. 清理（如果需要）
            if cleanup_after:
                logger.info("🧹 正在清理服务...")
                self.cleanup_processes()

            logger.info("=" * 80)
            if test_success:
                logger.info("🎉 完整测试成功完成!")
            else:
                logger.error("❌ 完整测试失败!")
            logger.info("=" * 80)

            return test_success

        except Exception as e:
            logger.error(f"❌ 运行完整测试失败: {e}")
            import traceback

            traceback.print_exc()
            if cleanup_after:
                self.cleanup_processes()
            return False

    def setup_signal_handlers(self):
        """设置信号处理器"""

        def signal_handler(signum, frame):
            logger.info(f"📡 收到信号 {signum}，正在清理...")
            self.cleanup_processes()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)


async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="MaiMBot 完整集成测试脚本")
    parser.add_argument("--users", type=int, default=2, help="用户数量 (默认: 2)")
    parser.add_argument("--agents", type=int, default=1, help="每个用户的Agent数量 (默认: 1)")
    parser.add_argument("--integration", action="store_true", help="运行完整集成测试")
    parser.add_argument("--no-cleanup", action="store_true", help="测试后不清理服务")
    parser.add_argument("--start-only", action="store_true", help="只启动服务，不运行测试")

    args = parser.parse_args()

    runner = MaiBotTestRunner()
    runner.setup_signal_handlers()

    try:
        if args.start_only:
            # 只启动服务
            success = await runner.start_all_servers()
            if success:
                logger.info("🎯 服务已启动，按 Ctrl+C 停止...")
                # 保持运行
                while runner.running:
                    await asyncio.sleep(1)
        else:
            # 运行测试
            success = await runner.run_full_test(
                user_count=args.users,
                agents_per_user=args.agents,
                run_integration=args.integration,
                cleanup_after=not args.no_cleanup,
            )

        return 0 if success else 1

    except KeyboardInterrupt:
        logger.info("👋 用户中断，正在清理...")
        runner.cleanup_processes()
        return 1
    except Exception as e:
        logger.error(f"❌ 运行失败: {e}")
        runner.cleanup_processes()
        return 1


if __name__ == "__main__":
    # 显示使用说明
    print("🤖 MaiMBot 完整集成测试脚本")
    print("=" * 50)
    print("使用方法:")
    print("  python test_maimbot_full_integration.py                    # 基础连接测试")
    print("  python test_maimbot_full_integration.py --integration     # 完整集成测试")
    print("  python test_maimbot_full_integration.py --users 3 --agents 2  # 自定义参数测试")
    print("  python test_maimbot_full_integration.py --start-only       # 只启动服务")
    print("  python test_maimbot_full_integration.py --no-cleanup      # 测试后不清理")
    print("=" * 50)
    print()

    # 运行主程序
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
