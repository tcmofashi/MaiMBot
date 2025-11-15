#!/usr/bin/env python3
"""
简化的MaiMBot测试脚本
专门用于快速测试和调试
"""

import asyncio
import sys
import os
import subprocess
import signal
import logging
from pathlib import Path

# 设置项目根目录
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class SimpleTestRunner:
    """简单测试运行器"""

    def __init__(self):
        self.config_process = None
        self.reply_process = None
        self.project_root = project_root

    def cleanup_processes(self):
        """清理所有进程"""
        logger.info("正在清理所有进程...")

        for process, name in [(self.config_process, "配置器后端"), (self.reply_process, "回复后端")]:
            if process:
                try:
                    process.terminate()
                    process.wait(timeout=5)
                    logger.info(f"{name}已停止")
                except subprocess.TimeoutExpired:
                    process.kill()
                    logger.warning(f"强制杀死{name}进程")
                except Exception as e:
                    logger.error(f"停止{name}失败: {e}")

    async def test_config_backend(self):
        """测试配置器后端"""
        try:
            logger.info("启动配置器后端...")

            env = os.environ.copy()
            env["PYTHONPATH"] = str(self.project_root)

            # 切换到项目根目录
            os.chdir(self.project_root)

            # 启动配置器后端
            self.config_process = subprocess.Popen(
                [sys.executable, "-m", "src.api.main"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
            )

            # 等待一段时间让服务启动
            logger.info("等待配置器后端启动...")
            await asyncio.sleep(20)

            # 检查进程是否还在运行
            if self.config_process.poll() is None:
                logger.info("✅ 配置器后端启动成功!")
                return True
            else:
                stdout, _ = self.config_process.communicate()
                logger.error(f"❌ 配置器后端启动失败: {stdout}")
                return False

        except Exception as e:
            logger.error(f"启动配置器后端失败: {e}")
            return False

    async def test_reply_backend(self):
        """测试回复后端"""
        try:
            logger.info("启动回复后端...")

            env = os.environ.copy()
            env["PYTHONPATH"] = str(self.project_root)

            # 启动回复后端
            self.reply_process = subprocess.Popen(
                [sys.executable, "bot.py"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env
            )

            # 等待一段时间让服务启动
            logger.info("等待回复后端启动...")
            await asyncio.sleep(30)

            # 检查进程是否还在运行
            if self.reply_process.poll() is None:
                logger.info("✅ 回复后端启动成功!")
                return True
            else:
                stdout, _ = self.reply_process.communicate()
                logger.error(f"❌ 回复后端启动失败: {stdout}")
                return False

        except Exception as e:
            logger.error(f"启动回复后端失败: {e}")
            return False

    async def test_apis(self):
        """测试API接口"""
        try:
            import aiohttp

            # 测试配置器后端API
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get("http://localhost:8000/health", timeout=5) as response:
                        if response.status == 200:
                            logger.info("✅ 配置器后端API健康检查通过")
                        else:
                            logger.warning(f"⚠️ 配置器后端API响应状态码: {response.status}")
                except Exception as e:
                    logger.error(f"❌ 配置器后端API测试失败: {e}")

                # 测试回复后端WebSocket
                try:
                    async with session.ws_connect("http://localhost:8095/ws", timeout=5) as ws:
                        logger.info("✅ 回复后端WebSocket连接成功")
                except Exception as e:
                    logger.error(f"❌ 回复后端WebSocket测试失败: {e}")

        except ImportError:
            logger.warning("aiohttp未安装，跳过API测试")
        except Exception as e:
            logger.error(f"API测试失败: {e}")

    async def run_simple_test(self):
        """运行简单测试"""
        logger.info("=" * 60)
        logger.info("MaiMBot 简单测试开始")
        logger.info("=" * 60)

        success = True

        # 1. 测试配置器后端
        if not await self.test_config_backend():
            success = False

        # 2. 测试回复后端
        if success:
            if not await self.test_reply_backend():
                success = False

        # 3. 测试API
        if success:
            await self.test_apis()

        # 4. 等待一段时间观察
        if success:
            logger.info("服务运行中，等待10秒观察状态...")
            await asyncio.sleep(10)

        # 5. 清理
        self.cleanup_processes()

        logger.info("=" * 60)
        if success:
            logger.info("✅ 简单测试完成!")
        else:
            logger.error("❌ 简单测试失败!")
        logger.info("=" * 60)

        return success

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
    runner = SimpleTestRunner()
    runner.setup_signal_handlers()

    try:
        success = await runner.run_simple_test()
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
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
