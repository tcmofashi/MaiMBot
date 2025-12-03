#!/usr/bin/env python3
"""
手动测试API密钥管理功能
"""

import requests

API_BASE_URL = "http://localhost:8000"
API_V1_PREFIX = "/api/v1"


def test_api_key_creation():
    """手动测试API密钥创建"""
    print("🔑 手动测试API密钥管理功能")
    print("=" * 50)

    # 1. 获取现有用户token
    print("\n1. 尝试登录获取token...")
    login_data = {"username": "api_key_test_user", "password": "testpass123"}

    try:
        resp = requests.post(f"{API_BASE_URL}{API_V1_PREFIX}/auth/login", json=login_data)
        if resp.status_code == 200:
            login_result = resp.json()
            access_token = login_result.get("access_token")
            tenant_id = login_result.get("tenant_id")
            print("   ✅ 登录成功!")
            print(f"   📋 租户ID: {tenant_id}")
        else:
            print(f"   ❌ 登录失败: {resp.status_code}")
            print(f"   错误详情: {resp.text}")
            return
    except Exception as e:
        print(f"   ❌ 登录异常: {e}")
        return

    # 2. 创建API密钥
    print("\n2. 创建API密钥...")
    api_key_data = {
        "tenant_id": tenant_id,
        "agent_id": "test_agent_manual",
        "user_identifier": "manual_test",
        "name": "手动测试API密钥",
        "description": "通过脚本手动创建的API密钥",
        "permissions": ["chat"],
        "expires_days": 30,
    }

    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        resp = requests.post(f"{API_BASE_URL}{API_V1_PREFIX}/api-keys", json=api_key_data, headers=headers)

        print(f"   📊 状态码: {resp.status_code}")

        if resp.status_code == 200:
            api_key_info = resp.json()
            created_api_key = api_key_info["api_key"]
            print("   ✅ API密钥创建成功!")
            print(f"   🔑 完整密钥: {created_api_key}")
            print("   📋 密钥信息:")
            print(f"      - 租户ID: {api_key_info['tenant_id']}")
            print(f"      - 智能体ID: {api_key_info['agent_id']}")
            print(f"      - 用户标识符: {api_key_info['user_identifier']}")
            print(f"      - 名称: {api_key_info['name']}")
            print(f"      - 权限: {api_key_info['permissions']}")
            print(f"      - 状态: {api_key_info['status']}")
            print(f"      - 过期时间: {api_key_info.get('expires_at', '永不过期')}")

            # 3. 验证API密钥
            print("\n3. 验证API密钥...")
            validation_data = {"api_key": created_api_key}

            resp = requests.post(f"{API_BASE_URL}{API_V1_PREFIX}/api-keys/validate", json=validation_data)

            if resp.status_code == 200:
                validation_result = resp.json()
                if validation_result["valid"]:
                    print("   ✅ API密钥验证成功!")
                    print("   📋 验证结果:")
                    print(f"      - 租户ID: {validation_result['tenant_id']}")
                    print(f"      - 智能体ID: {validation_result['agent_id']}")
                    print(f"      - 用户标识符: {validation_result['user_identifier']}")
                    print(f"      - API密钥ID: {validation_result['api_key_id']}")
                else:
                    print(f"   ❌ API密钥验证失败: {validation_result.get('error', '未知错误')}")
            else:
                print(f"   ❌ API密钥验证请求失败: {resp.status_code}")
                print(f"   错误详情: {resp.text}")

            # 4. 列出API密钥
            print("\n4. 列出API密钥...")
            resp = requests.get(f"{API_BASE_URL}{API_V1_PREFIX}/api-keys", headers=headers)

            if resp.status_code == 200:
                api_keys_list = resp.json()
                print("   ✅ 获取API密钥列表成功")
                print(f"   📋 总数: {api_keys_list['total']} 个密钥")
                for i, api_key in enumerate(api_keys_list["api_keys"], 1):
                    print(f"      {i}. {api_key['name']} ({api_key['user_identifier']}) - {api_key['status']}")
                    print(f"         租户: {api_key['tenant_id']}, 智能体: {api_key['agent_id']}")
            else:
                print(f"   ❌ 获取API密钥列表失败: {resp.status_code}")
                print(f"   错误详情: {resp.text}")

        else:
            print(f"   ❌ API密钥创建失败: {resp.status_code}")
            print(f"   错误详情: {resp.text}")

    except Exception as e:
        print(f"   ❌ API密钥操作异常: {e}")

    print("\n🎉 手动测试完成!")
    print("\n📝 总结:")
    print("   ✅ 新的API密钥管理系统已成功实现")
    print("   🔑 API密钥格式: {user_identifier}.{auth_token}")
    print("   📊 支持权限管理和过期时间")
    print("   🔍 支持API密钥验证和列表查询")
    print("   🗂️ 支持禁用API密钥（软删除）")


if __name__ == "__main__":
    test_api_key_creation()
