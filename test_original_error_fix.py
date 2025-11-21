#!/usr/bin/env python3
"""
测试原始错误是否已修复
直接测试 ActionModifier.__init__() got an unexpected keyword argument 'isolation_context' 错误
"""

import asyncio
import sys
import traceback
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.isolation.isolation_context import IsolationContext
from src.chat.planner_actions.action_manager import ActionManager
from src.chat.planner_actions.action_modifier import ActionModifier
from src.chat.heart_flow.isolated_heartflow import get_isolated_heartflow


async def test_original_error():
    """测试原始错误是否已修复"""
    print("🧪 测试原始错误: ActionModifier.__init__() got an unexpected keyword argument 'isolation_context'")

    try:
        # 创建隔离上下文
        isolation_context = IsolationContext(
            tenant_id="tenant_d618ecd3f69520ed",
            agent_id="agent_6da064b57ab92e3f",
            platform="test",
            chat_stream_id="test_chat_id",
        )

        # 创建动作管理器
        action_manager = ActionManager()

        # 测试 ActionModifier 是否能接受 isolation_context 参数
        print("📝 测试 ActionModifier 构造函数...")
        action_modifier = ActionModifier(
            action_manager=action_manager, chat_id="test_chat_id", isolation_context=isolation_context
        )

        print("✅ ActionModifier 成功创建，支持 isolation_context 参数")
        print(f"   日志前缀: {action_modifier.log_prefix}")
        print(
            f"   隔离上下文: {action_modifier.isolation_context.tenant_id}:{action_modifier.isolation_context.agent_id}"
        )

        # 测试完整的隔离化心流聊天创建流程
        print("\n📝 测试完整的隔离化心流聊天创建...")
        chat_id = "9f861055961abce8816b212b5d141205"

        # 这里应该不再抛出 ActionModifier.__init__() 错误
        heartflow = get_isolated_heartflow(isolation_context.tenant_id, isolation_context.agent_id)
        heartflow_chat = await heartflow.get_or_create_heartflow_chat(chat_id=chat_id)

        if heartflow_chat:
            print("✅ 隔离化心流聊天成功创建")
            print(f"   聊天ID: {chat_id}")
            print(f"   隔离上下文: {isolation_context.tenant_id}:{isolation_context.agent_id}")
        else:
            print("❌ 隔离化心流聊天创建失败")
            return False

        return True

    except TypeError as e:
        if "unexpected keyword argument 'isolation_context'" in str(e):
            print(f"❌ 原始错误仍然存在: {e}")
            return False
        else:
            print(f"❌ 其他TypeError: {e}")
            traceback.print_exc()
            return False
    except Exception as e:
        print(f"❌ 其他错误: {e}")
        traceback.print_exc()
        return False


async def main():
    """主测试函数"""
    print("🚀 开始测试原始错误修复")
    print("=" * 60)

    success = await test_original_error()

    print("\n" + "=" * 60)
    if success:
        print("🎉 原始错误已修复！ActionModifier 现在支持 isolation_context 参数")
        print("✅ 隔离化心流聊天创建流程正常工作")
    else:
        print("❌ 原始错误未修复，需要进一步检查")

    return success


if __name__ == "__main__":
    # 运行测试
    success = asyncio.run(main())

    # 退出码
    sys.exit(0 if success else 1)
