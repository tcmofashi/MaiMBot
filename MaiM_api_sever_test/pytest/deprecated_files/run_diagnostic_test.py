#!/usr/bin/env python3
"""
消息处理超时问题诊断测试脚本
完整的测试流程：激活环境 -> 启动API服务器 -> 运行集成测试
"""

import os
import sys
import subprocess
import time
import signal
import logging
from pathlib import Path

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("diagnostic_test.log"), logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


class DiagnosticTestRunner:
    """诊断测试运行器"""

    def __init__(self):
        self.project_root = Path(__file__).parent
        self.api_server_process = None
        self.reply_backend_process = None
        self.maibot_env = None

    def find_conda_executable(self):
        """查找conda可执行文件"""
        conda_paths = [
            str(Path.home() / "anaconda3" / "bin" / "conda"),
            str(Path.home() / "miniconda3" / "bin" / "conda"),
            "/opt/conda/bin/conda",
            "conda",
        ]

        for conda_path in conda_paths:
            if os.path.exists(conda_path) or conda_path == "conda":
                return conda_path
        return None

    def activate_environment(self):
        """激活maibot环境"""
        logger.info("🔄 正在激活maibot环境...")

        # 检查是否已经在maibot环境中
        if "maibot" in os.environ.get("CONDA_DEFAULT_ENV", ""):
            logger.info("✅ 已在maibot环境中")
            self.maibot_env = sys.executable  # 使用当前Python解释器
            return True

        # 尝试使用conda activate
        conda_path = self.find_conda_executable()
        if conda_path and conda_path != "conda":
            # 使用shell执行conda activate
            activate_cmd = f"source {Path(conda_path).parent}/activate maibot"
            logger.info(f"执行激活命令: {activate_cmd}")

            # 更新当前进程的环境变量
            try:
                result = subprocess.run(
                    f"{activate_cmd} && python -c 'import sys; print(sys.executable)'",
                    shell=True,
                    capture_output=True,
                    text=True,
                    executable="/bin/bash",
                )
                if result.returncode == 0:
                    python_path = result.stdout.strip()
                    if "maibot" in python_path:
                        logger.info(f"✅ maibot环境Python路径: {python_path}")
                        self.maibot_env = python_path
                        return True
            except Exception as e:
                logger.warning(f"激活环境失败: {e}")

        # 检查当前Python是否已经是maibot
        current_python = sys.executable
        if "maibot" in current_python:
            logger.info(f"✅ 当前已在maibot环境: {current_python}")
            self.maibot_env = current_python
            return True

        # 尝试直接使用maibot的Python
        maibot_python = str(Path.home() / "anaconda3" / "envs" / "maibot" / "bin" / "python")
        if os.path.exists(maibot_python):
            logger.info(f"✅ 找到maibot Python: {maibot_python}")
            self.maibot_env = maibot_python
            return True

        logger.error("❌ 无法找到maibot环境")
        return False

    def start_reply_backend(self):
        """启动回复后端（WebSocket服务器）"""
        logger.info("🚀 正在启动回复后端...")

        # 设置环境变量
        env = os.environ.copy()
        env["PYTHONPATH"] = str(self.project_root)
        env["PORT"] = "8095"  # 设置回复后端端口为8095
        env["HOST"] = "0.0.0.0"  # 设置HOST环境变量

        # 启动回复后端
        try:
            if not self.maibot_env:
                logger.error("❌ maibot环境未设置")
                return False

            reply_backend_cmd = [self.maibot_env, "src/main.py"]
            logger.info(f"执行命令: {' '.join(reply_backend_cmd)}")

            self.reply_backend_process = subprocess.Popen(
                reply_backend_cmd,
                cwd=self.project_root,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            # 等待服务器启动
            logger.info("⏳ 等待回复后端启动...")
            time.sleep(15)  # 回复后端需要更长时间启动

            # 检查进程是否还在运行
            if self.reply_backend_process.poll() is None:
                logger.info("✅ 回复后端已启动")
                return True
            else:
                # 输出错误信息
                output, _ = self.reply_backend_process.communicate()
                logger.error(f"❌ 回复后端启动失败:\n{output}")
                return False

        except Exception as e:
            logger.error(f"❌ 启动回复后端失败: {e}")
            return False

    def start_api_server(self):
        """启动API服务器"""
        logger.info("🚀 正在启动API服务器...")

        # 设置环境变量
        env = os.environ.copy()
        env["PYTHONPATH"] = str(self.project_root)
        env["PORT"] = "18000"  # 设置API服务器端口为18000

        # 启动API服务器
        try:
            if not self.maibot_env:
                logger.error("❌ maibot环境未设置")
                return False

            api_server_cmd = [self.maibot_env, "src/api/main.py"]
            logger.info(f"执行命令: {' '.join(api_server_cmd)}")

            self.api_server_process = subprocess.Popen(
                api_server_cmd,
                cwd=self.project_root,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            # 等待服务器启动
            logger.info("⏳ 等待API服务器启动...")
            time.sleep(5)

            # 检查进程是否还在运行
            if self.api_server_process.poll() is None:
                logger.info("✅ API服务器已启动")
                return True
            else:
                # 输出错误信息
                output, _ = self.api_server_process.communicate()
                logger.error(f"❌ API服务器启动失败:\n{output}")
                return False

        except Exception as e:
            logger.error(f"❌ 启动API服务器失败: {e}")
            return False

    def start_all_servers(self):
        """启动所有服务器"""
        logger.info("🚀 正在启动所有服务器...")

        # 先启动回复后端
        if not self.start_reply_backend():
            logger.error("❌ 回复后端启动失败")
            return False

        # 再启动API服务器
        if not self.start_api_server():
            logger.error("❌ API服务器启动失败")
            return False

        # 等待所有服务完全就绪
        logger.info("⏳ 等待所有服务完全就绪...")
        time.sleep(10)

        logger.info("✅ 所有服务器启动成功")
        return True

    def run_integration_test(self):
        """运行集成测试"""
        logger.info("🧪 正在运行集成测试...")

        try:
            test_cmd = [self.maibot_env, "-m", "integration_tests.simple_test_runner"]
            logger.info(f"执行测试命令: {' '.join(test_cmd)}")

            # 设置环境变量
            env = os.environ.copy()
            env["PYTHONPATH"] = str(self.project_root)

            # 运行测试
            result = subprocess.run(
                test_cmd,
                cwd=self.project_root,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,  # 2分钟超时
            )

            logger.info("=== 测试输出 ===")
            logger.info(result.stdout)

            if result.stderr:
                logger.warning("=== 错误输出 ===")
                logger.warning(result.stderr)

            logger.info("=== 测试完成 ===")

            return result.returncode == 0

        except subprocess.TimeoutExpired:
            logger.error("❌ 测试超时")
            return False
        except Exception as e:
            logger.error(f"❌ 运行测试失败: {e}")
            return False

    def cleanup(self):
        """清理资源"""
        logger.info("🧹 正在清理资源...")

        # 清理API服务器
        if self.api_server_process:
            try:
                self.api_server_process.terminate()
                self.api_server_process.wait(timeout=5)
                logger.info("✅ API服务器已停止")
            except subprocess.TimeoutExpired:
                self.api_server_process.kill()
                logger.info("✅ API服务器已强制停止")
            except Exception as e:
                logger.warning(f"停止API服务器时出错: {e}")

        # 清理回复后端
        if self.reply_backend_process:
            try:
                self.reply_backend_process.terminate()
                self.reply_backend_process.wait(timeout=5)
                logger.info("✅ 回复后端已停止")
            except subprocess.TimeoutExpired:
                self.reply_backend_process.kill()
                logger.info("✅ 回复后端已强制停止")
            except Exception as e:
                logger.warning(f"停止回复后端时出错: {e}")

    def run_diagnostic_test(self):
        """运行完整的诊断测试"""
        logger.info("=" * 60)
        logger.info("🔍 开始消息处理超时问题诊断测试")
        logger.info("=" * 60)

        try:
            # 步骤1: 激活环境
            if not self.activate_environment():
                logger.error("❌ 环境激活失败，测试终止")
                return False

            # 步骤2: 启动所有服务器
            if not self.start_all_servers():
                logger.error("❌ 服务器启动失败，测试终止")
                return False

            # 步骤3: 运行集成测试
            test_success = self.run_integration_test()

            if test_success:
                logger.info("🎉 诊断测试完成")
            else:
                logger.error("❌ 诊断测试失败")

            return test_success

        except KeyboardInterrupt:
            logger.info("⏹️ 测试被用户中断")
            return False
        except Exception as e:
            logger.error(f"❌ 诊断测试过程中发生错误: {e}")
            return False
        finally:
            # 清理资源
            self.cleanup()
            logger.info("=" * 60)
            logger.info("🏁 诊断测试结束")
            logger.info("=" * 60)


def main():
    """主函数"""
    runner = DiagnosticTestRunner()

    # 设置信号处理
    def signal_handler(signum, frame):
        logger.info("接收到中断信号，正在清理...")
        runner.cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 运行诊断测试
    success = runner.run_diagnostic_test()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
