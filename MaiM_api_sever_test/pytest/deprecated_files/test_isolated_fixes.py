#!/usr/bin/env python3
"""
测试隔离化修复的验证脚本
验证 ActionModifier 隔离上下文支持和配置管理器修复
"""

import asyncio
import sys
import traceback
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.isolation.isolation_context import IsolationContext
from src.config.isolated_config_manager import get_isolated_config_manager
from src.chat.planner_actions.action_manager import ActionManager
from src.chat.planner_actions.action_modifier import ActionModifier


async def test_isolated_config_manager():
    """测试隔离化配置管理器"""
    print("🧪 测试隔离化配置管理器...")

    try:
        # 创建隔离化配置管理器
        config_manager = get_isolated_config_manager("test_tenant", "test_agent")

        # 测试 get_isolated_config 方法
        config = config_manager.get_isolated_config(platform="test")
        print(f"✅ get_isolated_config 方法正常工作，返回配置类型: {type(config)}")

        # 测试 get_effective_config 方法
        effective_config = config_manager.get_effective_config(platform="test")
        print(f"✅ get_effective_config 方法正常工作，返回配置类型: {type(effective_config)}")

        return True

    except Exception as e:
        print(f"❌ 隔离化配置管理器测试失败: {e}")
        traceback.print_exc()
        return False


async def test_action_modifier_isolation():
    """测试 ActionModifier 隔离上下文支持"""
    print("🧪 测试 ActionModifier 隔离上下文支持...")

    try:
        # 创建隔离上下文
        isolation_context = IsolationContext(
            tenant_id="test_tenant", agent_id="test_agent", platform="test_platform", chat_stream_id="test_chat_id"
        )

        # 创建动作管理器
        action_manager = ActionManager()

        # 测试带隔离上下文的 ActionModifier
        action_modifier = ActionModifier(
            action_manager=action_manager, chat_id="test_chat_id", isolation_context=isolation_context
        )

        print("✅ ActionModifier 创建成功，支持隔离上下文")
        print(f"日志前缀: {action_modifier.log_prefix}")
        print(f"隔离上下文: {action_modifier.isolation_context.tenant_id}:{action_modifier.isolation_context.agent_id}")

        # 测试不带隔离上下文的 ActionModifier（向后兼容性）
        action_modifier_legacy = ActionModifier(action_manager=action_manager, chat_id="test_chat_id")

        print("✅ ActionModifier 创建成功，兼容旧版本")
        print(f"日志前缀: {action_modifier_legacy.log_prefix}")

        return True

    except Exception as e:
        print(f"❌ ActionModifier 隔离上下文测试失败: {e}")
        traceback.print_exc()
        return False


async def test_config_integration():
    """测试配置集成"""
    print("🧪 测试配置集成...")

    try:
        # 创建隔离上下文
        isolation_context = IsolationContext(
            tenant_id="test_tenant", agent_id="test_agent", platform="test_platform", chat_stream_id="test_chat_id"
        )

        # 测试隔离上下文的配置管理器集成
        if hasattr(isolation_context, "get_config_manager"):
            print("❌ 隔离上下文不应该有 get_config_manager 方法")
            return False
        else:
            print("✅ 隔离上下文正确地没有 get_config_manager 方法")

        # 测试通过 get_isolated_config_manager 获取配置管理器
        config_manager = get_isolated_config_manager("test_tenant", "test_agent")
        isolated_config = config_manager.get_isolated_config(platform="test_platform")

        print(f"✅ 配置集成测试通过，获取到配置: {type(isolated_config)}")

        return True

    except Exception as e:
        print(f"❌ 配置集成测试失败: {e}")
        traceback.print_exc()
        return False


async def main():
    """主测试函数"""
    print("🚀 开始隔离化修复验证测试")
    print("=" * 60)

    tests = [
        ("隔离化配置管理器", test_isolated_config_manager),
        ("ActionModifier 隔离上下文", test_action_modifier_isolation),
        ("配置集成", test_config_integration),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n📋 运行测试: {test_name}")
        print("-" * 40)

        try:
            result = await test_func()
            if result:
                passed += 1
                print(f"✅ {test_name} 测试通过")
            else:
                print(f"❌ {test_name} 测试失败")
        except Exception as e:
            print(f"❌ {test_name} 测试异常: {e}")
            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"📊 测试结果: {passed}/{total} 通过")

    if passed == total:
        print("🎉 所有测试通过！隔离化修复验证成功")
        return True
    else:
        print("⚠️  部分测试失败，需要进一步修复")
        return False


if __name__ == "__main__":
    # 运行测试
    success = asyncio.run(main())

    # 退出码
    sys.exit(0 if success else 1)
