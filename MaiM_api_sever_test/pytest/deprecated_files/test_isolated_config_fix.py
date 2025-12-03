#!/usr/bin/env python3
"""
测试隔离化配置修复

验证ChatStream和GeneratorAPI是否能正确使用隔离化配置
"""

import asyncio
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.common.logger import get_logger
from src.chat.message_receive.chat_stream import ChatStream
from src.plugin_system.apis import generator_api
from maim_message.message import UserInfo, GroupInfo

logger = get_logger("test_isolated_config_fix")


async def test_chat_stream_isolated_config():
    """测试ChatStream隔离化配置"""
    print("🧪 测试ChatStream隔离化配置...")

    # 创建测试用户和群组信息
    user_info = UserInfo(platform="test", user_id="test_user_123", user_nickname="测试用户", user_cardname="测试用户")

    group_info = GroupInfo(platform="test", group_id="test_group_456", group_name="测试群组")

    # 创建聊天流，指定租户ID和智能体ID
    chat_stream = ChatStream(
        stream_id="test_stream_789",
        platform="test",
        user_info=user_info,
        group_info=group_info,
        agent_id="test_agent_001",
        tenant_id="test_tenant_001",
    )

    print(f"✅ 创建聊天流: stream_id={chat_stream.stream_id}")
    print(f"   agent_id={chat_stream.agent_id}")
    print(f"   tenant_id={chat_stream.tenant_id}")

    # 测试配置获取
    try:
        config = chat_stream.get_effective_config()
        print(f"✅ 成功获取配置: {type(config)}")

        # 检查配置是否有chat属性
        if hasattr(config, "chat"):
            print(f"✅ 配置包含chat属性: {type(config.chat)}")

            # 测试chat方法
            if hasattr(config.chat, "get_talk_value"):
                talk_value = config.chat.get_talk_value(chat_stream.stream_id)
                print(f"✅ chat.get_talk_value() 成功: {talk_value}")
            else:
                print("❌ chat对象缺少get_talk_value方法")
        else:
            print("❌ 配置缺少chat属性")

    except Exception as e:
        print(f"❌ 获取配置失败: {e}")
        import traceback

        traceback.print_exc()
        return False

    return True


async def test_generator_api_config():
    """测试GeneratorAPI配置获取"""
    print("\n🧪 测试GeneratorAPI配置获取...")

    # 创建测试聊天流
    user_info = UserInfo(platform="test", user_id="test_user_456", user_nickname="测试用户2")

    chat_stream = ChatStream(
        stream_id="test_stream_abc",
        platform="test",
        user_info=user_info,
        agent_id="test_agent_002",
        tenant_id="test_tenant_002",
    )

    try:
        # 测试获取回复器
        replyer = generator_api.get_replyer(chat_stream, request_type="test")
        if replyer:
            print(f"✅ 成功获取回复器: {type(replyer)}")

            # 测试回复器配置（通过chat_stream获取）
            try:
                config = chat_stream.get_effective_config()
                print(f"✅ 通过chat_stream获取配置类型: {type(config)}")

                if hasattr(config, "chat"):
                    print(f"✅ 配置包含chat属性: {type(config.chat)}")
                else:
                    print("❌ 配置缺少chat属性")

            except Exception as e:
                print(f"❌ 获取配置失败: {e}")
                return False
        else:
            print("❌ 无法获取回复器")
            return False

    except Exception as e:
        print(f"❌ GeneratorAPI测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False

    return True


async def test_config_wrapper():
    """测试配置包装器"""
    print("\n🧪 测试配置包装器...")

    try:
        from src.config.config_wrapper import UnifiedConfigWrapper

        # 测试字典配置包装
        dict_config = {"chat": {"max_context_size": 10, "talk_value": 0.5}}

        wrapper = UnifiedConfigWrapper(dict_config)
        print(f"✅ 创建配置包装器: {type(wrapper)}")

        # 测试chat属性
        chat_wrapper = wrapper.chat
        if chat_wrapper:
            print(f"✅ chat包装器: {type(chat_wrapper)}")

            # 测试方法调用
            if hasattr(chat_wrapper, "get_talk_value"):
                talk_value = chat_wrapper.get_talk_value("test_stream")
                print(f"✅ get_talk_value() 成功: {talk_value}")
            else:
                print("❌ chat包装器缺少get_talk_value方法")
        else:
            print("❌ 无法获取chat包装器")
            return False

    except Exception as e:
        print(f"❌ 配置包装器测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False

    return True


async def main():
    """主测试函数"""
    print("🔧 开始隔离化配置修复测试")
    print("=" * 60)

    tests = [
        ("ChatStream隔离化配置", test_chat_stream_isolated_config),
        ("GeneratorAPI配置", test_generator_api_config),
        ("配置包装器", test_config_wrapper),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ 测试 '{test_name}' 出现异常: {e}")
            results.append((test_name, False))

    # 输出测试结果
    print("\n" + "=" * 60)
    print("📊 测试结果汇总:")

    passed = 0
    total = len(results)

    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"   {test_name}: {status}")
        if result:
            passed += 1

    print(f"\n🎯 总体结果: {passed}/{total} 测试通过")

    if passed == total:
        print("🎉 所有测试通过！隔离化配置修复成功！")
        return True
    else:
        print("⚠️  部分测试失败，需要进一步修复")
        return False


if __name__ == "__main__":
    asyncio.run(main())
