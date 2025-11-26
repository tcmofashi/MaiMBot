#!/usr/bin/env python3
"""
测试模型配置是否正确
"""

import asyncio
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.llm_models.utils_model import LLMRequest
from src.config.config import model_config


async def test_planner_model():
    """测试planner模型配置"""
    print("🧪 测试planner模型配置...")

    try:
        # 获取planner配置
        planner_config = model_config.model_task_config.planner
        print(f"📋 Planner模型列表: {planner_config.model_list}")
        print(f"🌡️ 温度: {planner_config.temperature}")
        print(f"📝 最大tokens: {planner_config.max_tokens}")

        # 创建LLM请求
        llm_request = LLMRequest(planner_config, "planner_test")

        # 测试简单请求
        test_prompt = '你好，这是一个测试。请回复一个简单的JSON：{"action": "test", "reason": "测试原因"}'

        print("📤 发送测试请求...")
        response, (reasoning, model_name, tool_calls) = await llm_request.generate_response_async(
            prompt=test_prompt, temperature=0.3, max_tokens=100
        )

        print(f"✅ 使用模型: {model_name}")
        print(f"💬 响应内容: {response}")
        print(f"🧠 推理内容: {reasoning}")

        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_replyer_model():
    """测试replyer模型配置"""
    print("\n🧪 测试replyer模型配置...")

    try:
        # 获取replyer配置
        replyer_config = model_config.model_task_config.replyer
        print(f"📋 Replyer模型列表: {replyer_config.model_list}")
        print(f"🌡️ 温度: {replyer_config.temperature}")
        print(f"📝 最大tokens: {replyer_config.max_tokens}")

        # 创建LLM请求
        llm_request = LLMRequest(replyer_config, "replyer_test")

        # 测试简单请求
        test_prompt = "你好，请简单回复一下这个测试消息。"

        print("📤 发送测试请求...")
        response, (reasoning, model_name, tool_calls) = await llm_request.generate_response_async(
            prompt=test_prompt, temperature=0.3, max_tokens=100
        )

        print(f"✅ 使用模型: {model_name}")
        print(f"💬 响应内容: {response}")

        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """主测试函数"""
    print("🚀 开始模型配置测试")
    print("=" * 50)

    # 测试planner模型
    planner_success = await test_planner_model()

    # 测试replyer模型
    replyer_success = await test_replyer_model()

    print("\n" + "=" * 50)
    print("📊 测试结果:")
    print(f"   Planner模型: {'✅ 通过' if planner_success else '❌ 失败'}")
    print(f"   Replyer模型: {'✅ 通过' if replyer_success else '❌ 失败'}")

    if planner_success and replyer_success:
        print("🎉 所有模型配置测试通过！")
        return 0
    else:
        print("⚠️ 部分测试失败，请检查配置")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
