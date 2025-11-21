#!/usr/bin/env python3
"""
调试WebSocket认证和连接问题
"""

import asyncio
import sys
import os
import logging

# 添加项目路径
sys.path.insert(0, '/home/tcmofashi/proj/MaiMBot')
os.environ.setdefault('PYTHONPATH', '/home/tcmofashi/proj/MaiMBot')

from integration_tests.api_client import TestUser
from maim_message.client import create_client_config, WebSocketClient

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def debug_auth():
    print('🧪 开始WebSocket认证调试测试')

    # 创建测试用户
    user = TestUser(
        user_id='test_user_001',
        username='测试用户',
        tenant_id='tenant_test_123',
        email='test@example.com',
        password='password123',
        tenant_name='测试租户',
        access_token='test_token',
        api_key='test_api_key'
    )

    # 创建agent
    class MockAgent:
        agent_id = 'agent_test_456'
        name = '测试Agent'

    agent = MockAgent()

    print(f'🔑 用户信息: tenant_id={user.tenant_id}, user_id={user.user_id}')
    print(f'🤖 Agent信息: agent_id={agent.agent_id}, name={agent.name}')

    try:
        # 1. 创建WebSocket客户端配置
        agent_api_key = f"{user.tenant_id}:{agent.agent_id}"
        print(f'🔧 构造API Key: {agent_api_key}')

        client_config = create_client_config(
            url="ws://localhost:8095/ws",
            api_key=agent_api_key,
            platform="test",
        )

        print('✅ WebSocket客户端配置创建成功')

        # 2. 创建WebSocket客户端
        ws_client = WebSocketClient(client_config)
        print('✅ WebSocket客户端创建成功')

        # 3. 启动客户端
        await ws_client.start()
        print('✅ WebSocket客户端启动成功')

        # 4. 尝试连接
        print('🔗 尝试连接到WebSocket服务器...')
        connected = await ws_client.connect()
        print(f'🔗 连接结果: {connected}')

        if connected:
            print('✅ 连接成功！')

            # 等待连接完全建立
            print('⏳ 等待连接稳定...')
            await asyncio.sleep(2)

            # 5. 尝试发送消息
            from maim_message.message import APIMessageBase, MessageDim, BaseMessageInfo, SenderInfo, UserInfo, Seg
            import time

            message = APIMessageBase(
                message_info=BaseMessageInfo(
                    platform="test",
                    message_id=f"debug_{int(time.time() * 1000)}",
                    time=time.time(),
                    sender_info=SenderInfo(
                        user_info=UserInfo(
                            platform="test",
                            user_id=user.user_id,
                            user_nickname=user.username,
                        ),
                    ),
                ),
                message_segment=Seg(type="text", data="调试认证测试消息"),
                message_dim=MessageDim(
                    api_key=agent_api_key,
                    platform="test",
                ),
            )

            print(f'📤 尝试发送消息: API Key={agent_api_key}')
            msg_result = await ws_client.send_message(message)
            print(f'📨 发送结果: {msg_result}')

            # 等待一下看是否有响应
            await asyncio.sleep(2)

        # 6. 关闭连接
        print('🔌 关闭WebSocket连接...')
        await ws_client.disconnect()
        await ws_client.stop()
        print('✅ 连接已关闭')

    except Exception as e:
        print(f'❌ 测试失败: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_auth())