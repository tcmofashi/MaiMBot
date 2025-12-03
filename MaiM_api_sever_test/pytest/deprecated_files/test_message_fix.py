#!/usr/bin/env python3
"""
测试消息处理修复的简单脚本
"""

import asyncio
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def test_isolated_message_processing():
    """测试隔离化消息处理"""
    try:
        print("🔍 开始测试隔离化消息处理修复...")

        # 导入必要的模块
        from src.chat.message_receive.isolated_message import IsolatedMessageRecv
        from maim_message.message import BaseMessageInfo, Seg, UserInfo, GroupInfo
        from src.chat.message_receive.chat_stream import ChatStream

        print("✅ 模块导入成功")

        # 创建测试数据
        user_info = UserInfo(platform="test", user_id="test_user_123", user_nickname="测试用户")

        group_info = GroupInfo(platform="test", group_id="test_group_456", group_name="测试群组")

        # 创建聊天流
        chat_stream = ChatStream(
            stream_id="test_stream_789",
            platform="test",
            user_info=user_info,
            group_info=group_info,
            agent_id="agent_b08af8754e476747",
        )

        # 创建消息段
        message_segment = Seg(type="text", data="你好")

        # 创建消息信息
        message_info = BaseMessageInfo(
            message_id="test_message_123", time=1234567890, platform="test", sender_info=None, receiver_info=None
        )

        # 创建隔离化消息
        isolated_message = IsolatedMessageRecv(
            message_info=message_info,
            message_segment=message_segment,
            chat_stream=chat_stream,
            raw_message="你好",
            processed_plain_text="你好",
            tenant_id="tenant_db272553b1cba124",
            agent_id="agent_b08af8754e476747",
        )

        print("✅ 隔离化消息创建成功")
        print(f"   消息ID: {isolated_message.isolated_message_id}")
        print(f"   租户ID: {isolated_message.tenant_id}")
        print(f"   智能体ID: {isolated_message.agent_id}")

        # 测试基础消息处理
        print("🔄 开始测试基础消息处理...")
        await isolated_message.process()
        print("✅ 基础消息处理完成")

        # 测试完整的隔离化消息处理（包括心流处理器调用）
        print("🔄 开始测试完整隔离化消息处理...")
        await isolated_message.process_with_isolation()
        print("✅ 完整隔离化消息处理完成")

        print("🎉 所有测试通过！消息处理修复成功。")
        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_isolated_message_processing())
    sys.exit(0 if success else 1)
