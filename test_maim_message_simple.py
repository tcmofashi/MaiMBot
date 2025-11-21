#!/usr/bin/env python3
"""
简单测试maim_message修复效果
测试立即响应+异步处理功能
"""

import asyncio
import json
import time
import websockets


async def test_immediate_response():
    """测试立即响应功能"""
    print("🧪 测试maim_message立即响应功能")

    # 连接参数
    tenant_id = "test_tenant_immediate"
    agent_id = "test_agent_immediate"
    platform = "test"
    uri = "ws://localhost:8095/ws"

    try:
        # 连接WebSocket
        print(f"🔌 连接到: {uri}")
        async with websockets.connect(uri, ping_interval=None, ping_timeout=None) as websocket:
            # 发送认证消息
            auth_message = {"type": "auth", "tenant_id": tenant_id, "agent_id": agent_id, "platform": platform}

            print(f"📤 发送认证消息: {auth_message}")
            await websocket.send(json.dumps(auth_message))

            # 等待连接确认
            response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            connection_data = json.loads(response)
            print(f"📥 连接确认: {connection_data}")

            if connection_data.get("type") != "connection_confirmed":
                print("❌ 连接确认失败")
                return False

            print("✅ 连接建立成功")

            # 测试立即响应功能
            test_message = {
                "type": "chat",
                "message_id": f"test_immediate_{int(time.time() * 1000)}",
                "content": "测试立即响应功能",
                "user_id": "test_user",
                "group_id": "test_group",
            }

            print(f"📤 发送测试消息: {test_message}")
            start_time = time.time()

            # 发送消息
            await websocket.send(json.dumps(test_message))

            # 等待立即响应
            try:
                immediate_response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                response_time = time.time() - start_time
                response_data = json.loads(immediate_response)

                print(f"📥 立即响应: {response_data}")
                print(f"⏱️ 响应时间: {response_time:.3f}秒")

                # 验证响应格式
                if response_data.get("type") == "message_received":
                    if response_data.get("status") == "received":
                        if response_data.get("processing_status") == "queued":
                            print("✅ 立即响应测试通过 - 消息已接收并排队处理")
                            return True
                        else:
                            print(f"⚠️ 处理状态异常: {response_data.get('processing_status')}")
                    else:
                        print(f"⚠️ 接收状态异常: {response_data.get('status')}")
                elif response_data.get("type") == "message_error":
                    print(f"⚠️ 消息错误: {response_data.get('error')}")
                else:
                    print(f"⚠️ 响应类型异常: {response_data.get('type')}")

            except asyncio.TimeoutError:
                print("❌ 立即响应超时")
                return False

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

    return False


async def test_multiple_connections():
    """测试多连接并发"""
    print("\n🧪 测试多连接并发处理")

    async def single_connection_test(conn_id: int):
        """单个连接测试"""
        tenant_id = f"test_tenant_{conn_id}"
        agent_id = f"test_agent_{conn_id}"
        platform = "test"
        uri = "ws://localhost:8095/ws"

        try:
            async with websockets.connect(uri, ping_interval=None, ping_timeout=None) as websocket:
                # 认证
                auth_message = {"type": "auth", "tenant_id": tenant_id, "agent_id": agent_id, "platform": platform}
                await websocket.send(json.dumps(auth_message))

                # 等待连接确认
                response = await asyncio.wait_for(websocket.recv(), timeout=3.0)
                connection_data = json.loads(response)

                if connection_data.get("type") != "connection_confirmed":
                    return False, conn_id, "连接确认失败"

                # 发送测试消息
                test_message = {
                    "type": "chat",
                    "message_id": f"test_multi_{conn_id}_{int(time.time() * 1000)}",
                    "content": f"多连接测试消息 {conn_id}",
                    "user_id": f"test_user_{conn_id}",
                    "group_id": "test_group",
                }

                start_time = time.time()
                await websocket.send(json.dumps(test_message))

                # 等待立即响应
                immediate_response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                response_time = time.time() - start_time
                response_data = json.loads(immediate_response)

                if response_data.get("type") == "message_received":
                    return True, conn_id, response_time
                else:
                    return False, conn_id, f"响应异常: {response_data}"

        except Exception as e:
            return False, conn_id, str(e)

    # 并发测试多个连接
    connection_count = 5
    tasks = [single_connection_test(i) for i in range(connection_count)]

    print(f"🚀 启动 {connection_count} 个并发连接测试")
    start_time = time.time()

    results = await asyncio.gather(*tasks, return_exceptions=True)
    total_time = time.time() - start_time

    # 分析结果
    success_count = 0
    response_times = []

    for result in results:
        if isinstance(result, Exception):
            print(f"❌ 连接异常: {result}")
            continue

        success, conn_id, info = result
        if success:
            success_count += 1
            response_times.append(info)
            print(f"✅ 连接 {conn_id}: 响应时间 {info:.3f}秒")
        else:
            print(f"❌ 连接 {conn_id}: {info}")

    print("\n📊 并发测试结果:")
    print(f"   成功连接: {success_count}/{connection_count}")
    print(f"   总耗时: {total_time:.3f}秒")
    if response_times:
        avg_response_time = sum(response_times) / len(response_times)
        print(f"   平均响应时间: {avg_response_time:.3f}秒")

    return success_count == connection_count


async def main():
    """主测试函数"""
    print("🤖 maim_message修复效果测试")
    print("=" * 50)

    # 测试1: 立即响应功能
    immediate_success = await test_immediate_response()

    # 测试2: 多连接并发
    concurrent_success = await test_multiple_connections()

    # 总结
    print("\n" + "=" * 50)
    print("📋 测试结果总结:")
    print(f"   立即响应功能: {'✅ 通过' if immediate_success else '❌ 失败'}")
    print(f"   多连接并发: {'✅ 通过' if concurrent_success else '❌ 失败'}")

    if immediate_success and concurrent_success:
        print("\n🎉 所有测试通过！maim_message修复成功")
        print("   - 客户端发送消息后，服务器立即返回接收确认")
        print("   - 消息被送入异步处理队列")
        print("   - 支持多连接并发处理")
        return True
    else:
        print("\n❌ 部分测试失败，需要进一步检查")
        return False


if __name__ == "__main__":
    # 检查是否安装了websockets库
    try:
        import websockets
    except ImportError:
        print("❌ 缺少websockets库，请安装: pip install websockets")
        exit(1)

    # 运行测试
    success = asyncio.run(main())
    exit(0 if success else 1)
