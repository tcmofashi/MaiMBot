#!/usr/bin/env python3
"""
完整的隔离化心流聊天测试
包括聊天流创建和IsolatedHeartFChatting初始化
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def test_complete_isolated_heartflow():
    """测试完整的隔离化心流聊天创建流程"""
    print("🧪 开始完整隔离化心流聊天测试...")

    try:
        # 导入必要的模块
        from src.isolation.isolation_context import IsolationContext
        from src.chat.message_receive.chat_stream import get_isolated_chat_manager, ChatStream
        from src.chat.heart_flow.isolated_heartFC_chat import IsolatedHeartFChatting
        from src.chat.planner_actions.action_modifier import ActionModifier
        from src.chat.planner_actions.action_manager import ActionManager

        print("✅ 模块导入成功")

        # 1. 创建隔离上下文
        isolation_context = IsolationContext(
            tenant_id="test_tenant", agent_id="test_agent", platform="test_platform", chat_stream_id="test_chat"
        )

        print(f"✅ 隔离上下文创建成功: {isolation_context}")

        # 2. 获取隔离化聊天管理器
        chat_manager = get_isolated_chat_manager(isolation_context.tenant_id, isolation_context.agent_id)
        print(f"✅ 隔离化聊天管理器获取成功: {chat_manager}")

        # 3. 创建聊天流（如果不存在）
        chat_stream = chat_manager.get_stream("test_chat_id")
        if not chat_stream:
            print("📝 聊天流不存在，尝试创建...")

            # 创建一个基本的聊天流对象
            from maim_message import UserInfo

            user_info = UserInfo(
                platform="test_platform", user_id="test_user", user_nickname="测试用户", user_cardname="测试用户"
            )
            chat_stream = ChatStream(
                stream_id="test_chat_id",
                platform="test_platform",
                user_info=user_info,
                agent_id="test_agent",
                tenant_id="test_tenant",
            )

            # 手动添加到聊天管理器（模拟创建过程）
            chat_manager.streams["test_chat_id"] = chat_stream
            print("✅ 聊天流创建成功")
        else:
            print("✅ 聊天流已存在")

        # 4. 测试ActionModifier（确保之前的修复有效）
        action_manager = ActionManager()
        action_modifier = ActionModifier(
            action_manager=action_manager, chat_id="test_chat_id", isolation_context=isolation_context
        )

        print("✅ ActionModifier创建成功")
        print(f"   日志前缀: {action_modifier.log_prefix}")

        # 5. 测试IsolatedHeartFChatting创建
        print("🚀 开始创建IsolatedHeartFChatting...")

        # 修改隔离上下文的chat_stream_id以匹配测试
        isolation_context.chat_stream_id = "test_chat_id"

        heart_flow_chat = IsolatedHeartFChatting(chat_id="test_chat_id", isolation_context=isolation_context)

        print("✅ IsolatedHeartFChatting创建成功！")
        print(f"   日志前缀: {heart_flow_chat.log_prefix}")
        print(f"   租户ID: {heart_flow_chat.tenant_id}")
        print(f"   智能体ID: {heart_flow_chat.agent_id}")
        print(f"   平台: {heart_flow_chat.platform}")
        print(f"   聊天流ID: {heart_flow_chat.chat_stream_id}")
        print(f"   隔离信息: {heart_flow_chat.get_isolation_info()}")

        # 6. 验证组件初始化
        print("\n🔍 验证组件初始化...")

        # 检查ActionModifier是否正确初始化
        assert hasattr(heart_flow_chat, "action_modifier"), "ActionModifier未初始化"
        assert heart_flow_chat.action_modifier.isolation_context == isolation_context, "ActionModifier隔离上下文不正确"
        print("✅ ActionModifier组件验证通过")

        # 检查ActionPlanner是否正确初始化
        assert hasattr(heart_flow_chat, "action_planner"), "ActionPlanner未初始化"
        print("✅ ActionPlanner组件验证通过")

        # 检查聊天流是否正确关联
        assert heart_flow_chat.chat_stream is not None, "聊天流未正确关联"
        assert heart_flow_chat.chat_stream.stream_id == "test_chat_id", "聊天流ID不匹配"
        print("✅ 聊天流关联验证通过")

        print("\n🎉 完整隔离化心流聊天测试成功！")
        print("📋 测试总结:")
        print("   - ✅ 隔离上下文创建")
        print("   - ✅ 隔离化聊天管理器获取")
        print("   - ✅ 聊天流创建/获取")
        print("   - ✅ ActionModifier隔离支持")
        print("   - ✅ IsolatedHeartFChatting完整初始化")
        print("   - ✅ 所有组件隔离上下文正确传递")

        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        print(f"错误详情:\n{traceback.format_exc()}")
        return False


if __name__ == "__main__":
    success = test_complete_isolated_heartflow()
    sys.exit(0 if success else 1)
