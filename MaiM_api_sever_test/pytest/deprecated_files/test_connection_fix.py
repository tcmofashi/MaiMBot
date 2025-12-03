#!/usr/bin/env python3
"""
测试连接状态修复
"""

import asyncio
import logging
import sys
import os

# 添加项目路径
sys.path.insert(0, "/home/tcmofashi/proj/MaiMBot")
os.environ.setdefault("PYTHONPATH", "/home/tcmofashi/proj/MaiMBot")

from maim_message.client import WebSocketClient, create_client_config
from maim_message.message import APIMessageBase, MessageDim, BaseMessageInfo, SenderInfo, UserInfo, Seg

# 设置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def test_connection_state():
    print("🧪 开始测试连接状态修复...")

    try:
        # 1. 创建WebSocket客户端配置
        client_config = create_client_config(
            url="ws://localhost:8095/ws",
            api_key="tenant_test_123:agent_test_456",
            platform="test",
        )

        # 2. 创建WebSocket客户端
        ws_client = WebSocketClient(client_config)
        print("✅ WebSocket客户端创建成功")

        # 3. 启动客户端
        await ws_client.start()
        print("✅ WebSocket客户端启动成功")

        # 4. 尝试连接
        print("🔗 尝试连接到WebSocket服务器...")
        connected = await ws_client.connect()
        print(f"🔗 连接结果: {connected}")

        if connected:
            print("✅ 连接成功！")

            # 等待连接完全建立
            print("⏳ 等待连接稳定...")
            await asyncio.sleep(3)

            # 5. 尝试发送消息
            import time

            message = APIMessageBase(
                message_info=BaseMessageInfo(
                    platform="test",
                    message_id=f"test_{int(time.time() * 1000)}",
                    time=time.time(),
                    sender_info=SenderInfo(
                        user_info=UserInfo(
                            platform="test",
                            user_id="test_user",
                            user_nickname="测试用户",
                        ),
                    ),
                ),
                message_segment=Seg(type="text", data="测试连接状态修复"),
                message_dim=MessageDim(
                    api_key="tenant_test_123:agent_test_456",
                    platform="test",
                ),
            )

            print("📤 尝试发送消息...")
            msg_result = await ws_client.send_message(message)
            print(f"📨 发送结果: {msg_result}")

            if msg_result:
                print("🎉 连接状态修复成功！消息发送正常")
            else:
                print("❌ 连接状态仍有问题，消息发送失败")

            # 等待一下看是否有响应
            await asyncio.sleep(2)

        # 6. 关闭连接
        print("🔌 关闭WebSocket连接...")
        await ws_client.disconnect()
        await ws_client.stop()
        print("✅ 连接已关闭")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    # 直接运行测试（假设服务器已经在运行）
    print("🚀 假设MaiMBot服务器已在运行: HOST=0.0.0.0 PORT=8095")
    asyncio.run(test_connection_state())
