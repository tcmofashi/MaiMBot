#!/usr/bin/env python3
"""
调试模型客户端配置问题
"""

import sys
import asyncio
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.config.config import model_config
from src.llm_models.model_client.base_client import client_registry
from src.llm_models.utils_model import LLMRequest
from src.common.logger import get_logger

logger = get_logger("model_client_debug")


async def test_model_client():
    """测试模型客户端配置和调用"""

    print("=" * 60)
    print("🔍 模型客户端配置调试")
    print("=" * 60)

    # 1. 检查模型配置
    print("\n📋 检查模型配置...")
    try:
        r1_model_info = model_config.get_model_info("r1")
        print(f"✅ R1模型信息: {r1_model_info}")
        print(f"   - 模型标识符: {r1_model_info.model_identifier}")
        print(f"   - API提供商: {r1_model_info.api_provider}")

        # 检查API提供商配置
        provider = model_config.get_provider(r1_model_info.api_provider)
        print(f"✅ API提供商信息: {provider}")
        print(f"   - 名称: {provider.name}")
        print(f"   - Base URL: {provider.base_url}")
        print(f"   - 客户端类型: {provider.client_type}")
        print(f"   - 超时: {provider.timeout}")

    except Exception as e:
        print(f"❌ 模型配置错误: {e}")
        return False

    # 2. 检查客户端注册
    print("\n🔧 检查客户端注册...")
    try:
        # 获取客户端
        client = client_registry.get_client_class_instance(provider)
        print(f"✅ 客户端获取成功: {type(client).__name__}")

        # 检查客户端配置
        if hasattr(client, "client"):
            openai_client = client.client
            print(f"   - Base URL: {openai_client.base_url}")
            print(f"   - API Key: {'***' + openai_client.api_key[-10:] if openai_client.api_key else 'None'}")
            print(f"   - Timeout: {openai_client.timeout}")

    except Exception as e:
        print(f"❌ 客户端获取失败: {e}")
        return False

    # 3. 测试模型调用
    print("\n🚀 测试模型调用...")
    try:
        # 创建LLMRequest实例
        llm_request = LLMRequest(model_set=model_config.model_task_config.planner, request_type="test")
        print("✅ LLMRequest创建成功")
        print(f"   - 模型列表: {llm_request.model_for_task.model_list}")

        # 测试调用
        print("📤 发送测试请求...")
        response, (reasoning_content, model_name, tool_calls) = await llm_request.generate_response_async(
            prompt="你好，请简单回复一下", max_tokens=50, temperature=0.3
        )

        print("✅ 模型调用成功!")
        print(f"   - 响应内容: {response[:100] if response else 'None'}")
        print(f"   - 推理内容: {reasoning_content[:100] if reasoning_content else 'None'}")
        print(f"   - 使用模型: {model_name}")

        return True

    except Exception as e:
        print(f"❌ 模型调用失败: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_direct_openai_client():
    """直接测试OpenAI客户端"""
    print("\n🔧 直接测试OpenAI客户端...")

    try:
        from openai import AsyncOpenAI

        # 获取配置
        r1_model_info = model_config.get_model_info("r1")
        provider = model_config.get_provider(r1_model_info.api_provider)

        # 创建客户端
        client = AsyncOpenAI(
            base_url=provider.base_url, api_key=provider.api_key, timeout=provider.timeout, max_retries=0
        )

        print(f"📤 直接调用API: {r1_model_info.model_identifier}")

        # 测试调用
        response = await client.chat.completions.create(
            model=r1_model_info.model_identifier,
            messages=[{"role": "user", "content": "你好，请简单回复"}],
            max_tokens=50,
            temperature=0.3,
        )

        print("✅ 直接调用成功!")
        print(f"   - 响应: {response.choices[0].message.content}")

        return True

    except Exception as e:
        print(f"❌ 直接调用失败: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """主函数"""
    print("🎯 开始模型客户端调试...")

    # 测试系统内部调用
    success1 = await test_model_client()

    # 测试直接调用
    success2 = await test_direct_openai_client()

    print("\n" + "=" * 60)
    print("📊 调试结果总结")
    print("=" * 60)
    print(f"系统内部调用: {'✅ 成功' if success1 else '❌ 失败'}")
    print(f"直接API调用: {'✅ 成功' if success2 else '❌ 失败'}")

    if success2 and not success1:
        print("\n🔍 分析: 直接API调用成功但系统内部调用失败")
        print("   可能的原因:")
        print("   1. 客户端配置问题")
        print("   2. 消息格式转换问题")
        print("   3. 错误处理机制问题")
    elif not success1 and not success2:
        print("\n🔍 分析: 两种调用都失败")
        print("   可能的原因:")
        print("   1. API配置错误")
        print("   2. 网络连接问题")
        print("   3. API密钥问题")
    elif success1 and success2:
        print("\n🎉 两种调用都成功!")

    return success1


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
