#!/usr/bin/env python3
"""
API密钥管理功能测试脚本
"""

import asyncio
import aiohttp

# 配置
API_BASE_URL = "http://localhost:8000"
API_V1_PREFIX = "/api/v1"


async def test_api_key_management():
    """测试API密钥管理功能"""

    async with aiohttp.ClientSession() as session:
        print("🔑 开始API密钥管理功能测试\n")

        # 1. 首先创建一个测试用户用于认证
        print("1. 创建测试用户...")
        user_data = {
            "username": "api_key_test_user",
            "password": "testpass123",
            "email": "api_key_test@example.com",
            "tenant_name": "API密钥测试租户"
        }

        try:
            async with session.post(f"{API_BASE_URL}{API_V1_PREFIX}/auth/register", json=user_data) as resp:
                if resp.status in [200, 201]:
                    user_info = await resp.json()
                    print(f"   ✅ 用户创建成功: {user_info['username']}")
                    access_token = user_info.get('access_token')
                    tenant_id = user_info.get('tenant_id')
                else:
                    print(f"   ❌ 用户创建失败: {resp.status}")
                    return
        except Exception as e:
            print(f"   ❌ 用户创建异常: {e}")
            return

        # 2. 创建API密钥
        print("\n2. 创建API密钥...")
        api_key_data = {
            "tenant_id": tenant_id,
            "agent_id": "test_agent_001",
            "user_identifier": "testclient",
            "name": "测试客户端API密钥",
            "description": "用于测试API密钥管理功能",
            "permissions": ["chat", "read"],
            "expires_days": 30
        }

        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            async with session.post(
                f"{API_BASE_URL}{API_V1_PREFIX}/api-keys",
                json=api_key_data,
                headers=headers
            ) as resp:
                if resp.status == 200:
                    api_key_info = await resp.json()
                    created_api_key = api_key_info['api_key']
                    print(f"   ✅ API密钥创建成功: {created_api_key}")
                    print("   📋 密钥信息:")
                    print(f"      - 租户ID: {api_key_info['tenant_id']}")
                    print(f"      - 智能体ID: {api_key_info['agent_id']}")
                    print(f"      - 用户标识符: {api_key_info['user_identifier']}")
                    print(f"      - 状态: {api_key_info['status']}")
                    print(f"      - 有效期至: {api_key_info.get('expires_at', '永不过期')}")
                else:
                    error_text = await resp.text()
                    print(f"   ❌ API密钥创建失败: {resp.status}")
                    print(f"   错误详情: {error_text}")
                    return
        except Exception as e:
            print(f"   ❌ API密钥创建异常: {e}")
            return

        # 3. 验证API密钥
        print("\n3. 验证API密钥...")
        validation_data = {"api_key": created_api_key}

        try:
            async with session.post(
                f"{API_BASE_URL}{API_V1_PREFIX}/api-keys/validate",
                json=validation_data
            ) as resp:
                if resp.status == 200:
                    validation_result = await resp.json()
                    if validation_result['valid']:
                        print("   ✅ API密钥验证成功")
                        print("   📋 验证结果:")
                        print(f"      - 租户ID: {validation_result['tenant_id']}")
                        print(f"      - 智能体ID: {validation_result['agent_id']}")
                        print(f"      - 用户标识符: {validation_result['user_identifier']}")
                    else:
                        print(f"   ❌ API密钥验证失败: {validation_result.get('error', '未知错误')}")
                else:
                    print(f"   ❌ API密钥验证请求失败: {resp.status}")
        except Exception as e:
            print(f"   ❌ API密钥验证异常: {e}")

        # 4. 列出API密钥
        print("\n4. 列出API密钥...")
        try:
            async with session.get(
                f"{API_BASE_URL}{API_V1_PREFIX}/api-keys",
                headers=headers
            ) as resp:
                if resp.status == 200:
                    api_keys_list = await resp.json()
                    print("   ✅ 获取API密钥列表成功")
                    print(f"   📋 总数: {api_keys_list['total']} 个密钥")
                    for i, api_key in enumerate(api_keys_list['api_keys'][:3], 1):  # 只显示前3个
                        print(f"      {i}. {api_key['name']} ({api_key['user_identifier']}) - {api_key['status']}")
                else:
                    print(f"   ❌ 获取API密钥列表失败: {resp.status}")
        except Exception as e:
            print(f"   ❌ 获取API密钥列表异常: {e}")

        # 5. 创建第二个API密钥（同一个用户标识符，不同的智能体）
        print("\n5. 创建第二个API密钥（不同智能体）...")
        api_key_data2 = {
            "tenant_id": tenant_id,
            "agent_id": "test_agent_002",
            "user_identifier": "testclient",  # 相同的用户标识符
            "name": "测试客户端API密钥2",
            "description": "用于测试同一用户标识符多个智能体",
            "permissions": ["chat"],
            "expires_days": 15
        }

        try:
            async with session.post(
                f"{API_BASE_URL}{API_V1_PREFIX}/api-keys",
                json=api_key_data2,
                headers=headers
            ) as resp:
                if resp.status == 200:
                    api_key_info2 = await resp.json()
                    created_api_key2 = api_key_info2['api_key']
                    print(f"   ✅ 第二个API密钥创建成功: {created_api_key2}")
                    print(f"   📋 智能体ID: {api_key_info2['agent_id']}")
                else:
                    error_text = await resp.text()
                    print(f"   ❌ 第二个API密钥创建失败: {resp.status}")
                    print(f"   错误详情: {error_text}")
        except Exception as e:
            print(f"   ❌ 第二个API密钥创建异常: {e}")

        # 6. 测试重复用户标识符（应该失败）
        print("\n6. 测试重复用户标识符（应该失败）...")
        duplicate_data = {
            "tenant_id": tenant_id,
            "agent_id": "test_agent_001",  # 相同的智能体ID
            "user_identifier": "testclient",  # 相同的用户标识符
            "name": "重复密钥测试",
            "description": "这个应该失败"
        }

        try:
            async with session.post(
                f"{API_BASE_URL}{API_V1_PREFIX}/api-keys",
                json=duplicate_data,
                headers=headers
            ) as resp:
                if resp.status == 409:
                    print(f"   ✅ 重复用户标识符被正确拒绝: {resp.status}")
                else:
                    error_text = await resp.text()
                    print(f"   ❌ 重复用户标识符未被拒绝: {resp.status}")
                    print(f"   错误详情: {error_text}")
        except Exception as e:
            print(f"   ❌ 重复测试异常: {e}")

        print("\n🎉 API密钥管理功能测试完成!")
        print("\n📝 总结:")
        print("   - 新的API密钥格式: {user_identifier}.{auth_token}")
        print("   - 一个租户+智能体组合可以有多个API密钥")
        print("   - 同一用户标识符不能用于相同的智能体")
        print("   - API密钥支持权限管理和过期时间")


async def check_server_status():
    """检查服务器状态"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_BASE_URL}/api/") as resp:
                if resp.status == 200:
                    info = await resp.json()
                    print(f"✅ 服务器运行正常: {info.get('message', 'Unknown')}")
                    print("📋 可用端点:")
                    for endpoint, path in info.get('endpoints', {}).items():
                        if endpoint == 'api_keys':
                            print(f"   🔑 {endpoint}: {path} (新增)")
                        else:
                            print(f"   📡 {endpoint}: {path}")
                    return True
                else:
                    print(f"❌ 服务器状态异常: {resp.status}")
                    return False
    except Exception as e:
        print(f"❌ 无法连接到服务器: {e}")
        print("请确保API服务器正在运行: python src/api/main.py")
        return False


async def main():
    """主函数"""
    print("🔑 MaiMBot API密钥管理功能测试")
    print("=" * 50)

    # 检查服务器状态
    if not await check_server_status():
        return

    print()

    # 运行API密钥管理测试
    await test_api_key_management()


if __name__ == "__main__":
    asyncio.run(main())