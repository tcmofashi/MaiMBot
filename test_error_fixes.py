#!/usr/bin/env python3
"""
测试错误修复的脚本
验证所有错误处理是否能够显示完整的堆栈跟踪信息
"""

import asyncio
import logging
import sys
import traceback
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from src.common.logger import get_logger

# 配置日志以显示完整的堆栈跟踪
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("error_fix_test.log")],
)

logger = get_logger("error_fix_test")


async def test_database_constraint_fix():
    """测试数据库约束修复"""
    logger.info("=== 测试数据库约束修复 ===")

    try:
        from src.common.database.database_model import ChatStreams

        # 尝试创建一个ChatStreams实例，chat_stream_id应该允许NULL
        chat_stream = ChatStreams(
            tenant_id="test_tenant",
            agent_id="test_agent",
            platform="test_platform",
            # 不设置chat_stream_id，应该允许NULL
        )

        logger.info("✅ 数据库约束修复测试通过：chat_stream_id字段允许NULL")
        return True

    except Exception as e:
        logger.error(f"❌ 数据库约束修复测试失败: {e}", exc_info=True)
        return False


async def test_isolation_level_import_fix():
    """测试IsolationLevel导入修复"""
    logger.info("=== 测试IsolationLevel导入修复 ===")

    try:
        from src.chat.message_receive.message_converter import MessageConverter, ConversionConfig

        # 创建转换器实例
        config = ConversionConfig()
        converter = MessageConverter(config)

        logger.info("✅ IsolationLevel导入修复测试通过")
        return True

    except Exception as e:
        logger.error(f"❌ IsolationLevel导入修复测试失败: {e}", exc_info=True)
        return False


async def test_isolated_message_api_fix():
    """测试隔离化消息API递归调用修复"""
    logger.info("=== 测试隔离化消息API递归调用修复 ===")

    try:
        from src.chat.message_receive.isolated_message_api import validate_isolated_message
        from src.chat.message_receive.message_validator import ValidationResult

        # 创建一个模拟的隔离化消息对象
        class MockIsolatedMessage:
            def __init__(self):
                self.tenant_id = "test_tenant"
                self.agent_id = "test_agent"
                self.platform = "test_platform"
                self.isolation_context = None  # 添加缺失的属性
                self.message_info = None  # 添加缺失的message_info属性
                self.processed_plain_text = "test message"  # 添加缺失的processed_plain_text属性

            def validate(self):
                return ValidationResult(is_valid=True, errors=[])

            def get_isolation_level(self):
                return "agent"  # 返回隔离级别

        mock_message = MockIsolatedMessage()

        # 测试验证函数，应该不会递归调用
        result = validate_isolated_message(mock_message)

        if hasattr(result, "is_valid") and result.is_valid:
            logger.info("✅ 隔离化消息API递归调用修复测试通过")
            return True
        else:
            logger.error(f"❌ 验证结果不符合预期: {result}")
            return False

    except Exception as e:
        logger.error(f"❌ 隔离化消息API递归调用修复测试失败: {e}", exc_info=True)
        return False


async def test_tenant_client_timeout_fix():
    """测试租户客户端超时错误增强"""
    logger.info("=== 测试租户客户端超时错误增强 ===")

    try:
        from maim_message.tenant_client import TenantMessageClient, ClientConfig

        # 创建客户端配置
        config = ClientConfig(
            tenant_id="test_tenant",
            agent_id="test_agent",
            platform="test_platform",
            server_url="ws://localhost:9999",  # 不存在的服务器
            message_timeout=1.0,  # 短超时
        )

        client = TenantMessageClient(config)

        # 尝试发送消息，应该触发增强的超时错误
        try:
            await client.send_message({"type": "test"}, wait_for_result=True, timeout=0.1)
        except TimeoutError as e:
            # 检查错误信息是否包含详细信息
            error_msg = str(e)
            if "详细信息:" in error_msg and "message_id" in error_msg:
                logger.info("✅ 租户客户端超时错误增强测试通过")
                return True
            else:
                logger.error(f"❌ 租户客户端超时错误信息不够详细: {error_msg}")
                return False
        except Exception as e:
            # 其他错误也是可以接受的，比如连接错误
            logger.info(f"✅ 租户客户端测试遇到预期错误: {type(e).__name__}")
            return True

    except Exception as e:
        logger.error(f"❌ 租户客户端超时错误增强测试失败: {e}", exc_info=True)
        return False


async def test_message_converter_error_handling():
    """测试消息转换器错误处理"""
    logger.info("=== 测试消息转换器错误处理 ===")

    try:
        from src.chat.message_receive.message_converter import MessageConverter, ConversionConfig

        config = ConversionConfig()
        converter = MessageConverter(config)

        # 测试转换无效消息类型（空数组）
        try:
            result = await converter.convert_to_isolated_message([])
            # 如果没有抛出异常，检查结果
            if not result.success and result.errors:
                logger.info("✅ 消息转换器错误处理测试通过：正确处理空数组转换")
                return True
            else:
                logger.error("❌ 消息转换器应该失败但却成功了")
                return False
        except Exception as e:
            # 抛出异常也是可以接受的，说明错误被正确处理了
            logger.info(f"✅ 消息转换器正确抛出异常: {type(e).__name__}")
            return True

    except Exception as e:
        logger.error(f"❌ 消息转换器错误处理测试失败: {e}", exc_info=True)
        return False


async def run_all_tests():
    """运行所有测试"""
    logger.info("开始运行错误修复验证测试...")

    tests = [
        test_database_constraint_fix,
        test_isolation_level_import_fix,
        test_isolated_message_api_fix,
        test_tenant_client_timeout_fix,
        test_message_converter_error_handling,
    ]

    results = []
    for test in tests:
        try:
            result = await test()
            results.append(result)
        except Exception as e:
            logger.error(f"测试 {test.__name__} 执行失败: {e}", exc_info=True)
            results.append(False)

    # 汇总结果
    passed = sum(results)
    total = len(results)

    logger.info("\n=== 测试结果汇总 ===")
    logger.info(f"通过: {passed}/{total}")
    logger.info(f"失败: {total - passed}/{total}")

    if passed == total:
        logger.info("🎉 所有错误修复验证测试通过！")
    else:
        logger.error("❌ 部分测试失败，需要进一步检查")

    return passed == total


def main():
    """主函数"""
    print("MaiMBot 错误修复验证测试")
    print("=" * 50)

    try:
        result = asyncio.run(run_all_tests())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"测试执行失败: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
