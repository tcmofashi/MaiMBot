#!/usr/bin/env python3
"""
SiliconFlow API诊断脚本
用于测试SiliconFlow API连接和配置问题
"""

import asyncio
import os
import sys
import traceback
from openai import AsyncOpenAI, APIConnectionError, APIStatusError

# 添加项目路径
sys.path.insert(0, "/home/tcmofashi/proj/MaiMBot")

from src.config.config import model_config
from src.config.api_ada_configs import ModelInfo
from src.llm_models.model_client.openai_client import OpenaiClient
from src.llm_models.payload_content.message import MessageBuilder
from src.common.logger import get_logger

logger = get_logger("SiliconFlow_API_Test")


async def test_direct_openai_client():
    """直接测试OpenAI客户端连接SiliconFlow"""
    print("\n" + "=" * 60)
    print("🔍 测试直接OpenAI客户端连接SiliconFlow")
    print("=" * 60)

    try:
        # 获取SiliconFlow配置
        siliconflow_provider = None
        for provider in model_config.api_providers:
            if provider.name == "SiliconFlow":
                siliconflow_provider = provider
                break

        if not siliconflow_provider:
            print("❌ 未找到SiliconFlow提供商配置")
            return False

        print("📋 SiliconFlow配置:")
        print(f"   - Name: {siliconflow_provider.name}")
        print(f"   - Base URL: {siliconflow_provider.base_url}")
        print(f"   - Client Type: {siliconflow_provider.client_type}")
        print(
            f"   - API Key: {'*' * 20}{siliconflow_provider.api_key[-10:] if siliconflow_provider.api_key else 'None'}"
        )
        print(f"   - Timeout: {siliconflow_provider.timeout}")

        # 创建OpenAI客户端
        client = AsyncOpenAI(
            base_url=siliconflow_provider.base_url,
            api_key=siliconflow_provider.api_key,
            max_retries=0,
            timeout=siliconflow_provider.timeout,
        )

        print("\n🚀 测试连接...")

        # 测试简单的聊天请求
        response = await client.chat.completions.create(
            model="deepseek-ai/DeepSeek-V3",
            messages=[{"role": "user", "content": "你好，请回复一个简短的问候"}],
            max_tokens=50,
            temperature=0.7,
        )

        if response and response.choices and len(response.choices) > 0:
            content = response.choices[0].message.content
            print("✅ API调用成功!")
            print(f"   响应内容: {content}")
            print(f"   模型: {response.model}")
            if response.usage:
                print(f"   Token使用: {response.usage}")
            return True
        else:
            print("❌ API响应为空")
            return False

    except APIConnectionError as e:
        print(f"❌ 连接错误: {str(e)}")
        print(f"   错误类型: {type(e)}")
        if hasattr(e, "__cause__") and e.__cause__:
            print(f"   底层错误: {str(e.__cause__)}")
        return False
    except APIStatusError as e:
        print(f"❌ API状态错误: {e.status_code} - {e.message}")
        return False
    except Exception as e:
        print(f"❌ 未知错误: {str(e)}")
        print(f"   错误类型: {type(e)}")
        traceback.print_exc()
        return False
    finally:
        if "client" in locals():
            await client.close()


async def test_openai_client_wrapper():
    """测试OpenAI客户端包装器"""
    print("\n" + "=" * 60)
    print("🔍 测试OpenAI客户端包装器")
    print("=" * 60)

    try:
        # 获取SiliconFlow配置
        siliconflow_provider = None
        for provider in model_config.api_providers:
            if provider.name == "SiliconFlow":
                siliconflow_provider = provider
                break

        if not siliconflow_provider:
            print("❌ 未找到SiliconFlow提供商配置")
            return False

        # 创建OpenAI客户端包装器
        openai_client = OpenaiClient(siliconflow_provider)

        # 创建模型信息
        model_info = ModelInfo(
            name="siliconflow-deepseek-v3",
            model_identifier="deepseek-ai/DeepSeek-V3",
            api_provider="SiliconFlow",
            force_stream_mode=False,
            extra_params={},
        )

        print("📋 模型信息:")
        print(f"   - Name: {model_info.name}")
        print(f"   - Identifier: {model_info.model_identifier}")
        print(f"   - Provider: {model_info.api_provider}")

        # 创建测试消息
        message_builder = MessageBuilder()
        message_builder.add_text_content("你好，请回复一个简短的问候")
        messages = [message_builder.build()]

        print("\n🚀 测试客户端包装器...")

        # 调用API
        response = await openai_client.get_response(
            model_info=model_info,
            message_list=messages,
            max_tokens=50,
            temperature=0.7,
        )

        if response and response.content:
            print("✅ 客户端包装器调用成功!")
            print(f"   响应内容: {response.content}")
            if response.reasoning_content:
                print(f"   推理内容: {response.reasoning_content}")
            if response.usage:
                print(f"   Token使用: {response.usage}")
            return True
        else:
            print("❌ 客户端包装器响应为空")
            return False

    except Exception as e:
        print(f"❌ 客户端包装器错误: {str(e)}")
        print(f"   错误类型: {type(e)}")
        traceback.print_exc()
        return False


async def test_model_config():
    """测试模型配置"""
    print("\n" + "=" * 60)
    print("🔍 测试模型配置")
    print("=" * 60)

    try:
        print("📋 所有API提供商:")
        for i, provider in enumerate(model_config.api_providers):
            print(f"   {i + 1}. {provider.name}")
            print(f"      - Type: {provider.client_type}")
            print(f"      - URL: {provider.base_url}")
            print(f"      - API Key: {'*' * 20}{provider.api_key[-10:] if provider.api_key else 'None'}")

        print("\n📋 所有模型:")
        # 检查models是字典还是列表
        if hasattr(model_config.models, "items"):
            # 字典格式
            model_items = model_config.models.items()
        else:
            # 列表格式，需要转换为字典
            model_items = [(model.name, model) for model in model_config.models]

        for model_name, model_info in model_items:
            print(f"   - {model_name}")
            print(f"      - Identifier: {model_info.model_identifier}")
            print(f"      - Provider: {model_info.api_provider}")
            print(f"      - Stream: {model_info.force_stream_mode}")

        # 检查特定模型
        target_models = ["siliconflow-deepseek-v3", "r1"]
        # 创建模型字典（如果models是列表）
        if hasattr(model_config.models, "items"):
            model_dict = model_config.models
        else:
            model_dict = {model.name: model for model in model_config.models}

        for model_name in target_models:
            if model_name in model_dict:
                model_info = model_dict[model_name]
                print(f"\n✅ 找到模型 {model_name}:")
                print(f"   - Identifier: {model_info.model_identifier}")
                print(f"   - Provider: {model_info.api_provider}")

                # 检查提供商是否存在
                provider = model_config.get_provider(model_info.api_provider)
                if provider:
                    print(f"   - Provider URL: {provider.base_url}")
                    print(f"   - Provider Type: {provider.client_type}")
                else:
                    print(f"   ❌ 提供商 {model_info.api_provider} 不存在!")
            else:
                print(f"\n❌ 未找到模型 {model_name}")

        return True

    except Exception as e:
        print(f"❌ 配置检查错误: {str(e)}")
        traceback.print_exc()
        return False


async def test_environment_variables():
    """测试环境变量"""
    print("\n" + "=" * 60)
    print("🔍 测试环境变量")
    print("=" * 60)

    env_vars = ["SILICONFLOW_API_KEY", "SILICONFLOW_BASE_URL", "OPENAI_API_KEY", "OPENAI_BASE_URL"]

    for var in env_vars:
        value = os.getenv(var)
        if value:
            print(f"✅ {var}: {'*' * 20}{value[-10:]}")
        else:
            print(f"❌ {var}: 未设置")

    return True


async def main():
    """主函数"""
    print("🤖 SiliconFlow API 诊断测试")
    print("=" * 60)

    results = []

    # 测试环境变量
    results.append(await test_environment_variables())

    # 测试配置
    results.append(await test_model_config())

    # 测试直接OpenAI客户端
    results.append(await test_direct_openai_client())

    # 测试OpenAI客户端包装器
    results.append(await test_openai_client_wrapper())

    # 总结
    print("\n" + "=" * 60)
    print("📊 测试总结")
    print("=" * 60)

    test_names = ["环境变量检查", "模型配置检查", "直接OpenAI客户端测试", "OpenAI客户端包装器测试"]

    for i, (name, result) in enumerate(zip(test_names, results)):
        status = "✅ 通过" if result else "❌ 失败"
        print(f"   {i + 1}. {name}: {status}")

    success_count = sum(results)
    total_count = len(results)
    print(f"\n🎯 总体结果: {success_count}/{total_count} 测试通过")

    if success_count == total_count:
        print("🎉 所有测试通过，SiliconFlow API配置正确!")
    else:
        print("⚠️  部分测试失败，需要检查配置")


if __name__ == "__main__":
    asyncio.run(main())
