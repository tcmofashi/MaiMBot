#!/usr/bin/env python3
"""
MaiBot 集成测试运行脚本

简化版运行脚本，用于快速启动多租户集成测试
"""

import asyncio
import logging
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from integration_tests.client import TestRunner

# 设置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

logger = logging.getLogger(__name__)


async def main():
    """主函数"""
    print("🚀 启动 MaiBot 多租户集成测试")
    print("=" * 50)

    try:
        # 创建测试运行器
        runner = TestRunner()

        # 运行测试
        print("📋 运行场景测试...")
        result = await runner.run_test(mode="scenarios")

        # 显示报告
        print("\n" + result["report"])
        print("=" * 50)
        print("✅ 测试完成!")

    except KeyboardInterrupt:
        print("\n❌ 测试被用户中断")
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
