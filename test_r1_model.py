#!/usr/bin/env python3
"""
测试 R1 模型的可用性
"""

from openai import OpenAI


def test_r1_model():
    """测试 R1 模型"""

    # SiliconFlow API 配置
    api_key = "sk-esuvnjcyclavodrahnnpbinlmhdllnthnvmfstsnwwfiiimm"
    base_url = "https://api.siliconflow.cn/v1"

    print("🧪 测试 R1 模型可用性...")

    # 创建客户端
    client = OpenAI(api_key=api_key, base_url=base_url)

    # 测试不同的 R1 模型变体
    models_to_test = [
        "deepseek-ai/DeepSeek-R1",
        "Pro/deepseek-ai/DeepSeek-R1",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B",
        "Pro/deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
    ]

    for model_id in models_to_test:
        print(f"\n📋 测试模型: {model_id}")
        try:
            # 简单的测试请求
            response = client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": "你好，请简单回复一下"}],
                max_tokens=50,
                temperature=0.3,
            )

            print(f"✅ 模型 {model_id} 测试成功!")
            print(f"📝 回复: {response.choices[0].message.content}")

            # 如果成功，返回这个模型ID
            return model_id

        except Exception as e:
            print(f"❌ 模型 {model_id} 测试失败: {e}")

    return None


def test_alternative_models():
    """测试替代模型"""

    print("\n🔄 测试可用的替代模型...")

    # SiliconFlow API 配置
    api_key = "sk-esuvnjcyclavodrahnnpbinlmhdllnthnvmfstsnwwfiiimm"
    base_url = "https://api.siliconflow.cn/v1"

    client = OpenAI(api_key=api_key, base_url=base_url)

    # 测试一些可用的替代模型
    alternative_models = [
        "Pro/deepseek-ai/DeepSeek-V3",
        "deepseek-ai/DeepSeek-V3",
        "Qwen/Qwen3-30B-A3B",
        "Qwen/Qwen3-14B",
    ]

    successful_models = []

    for model_id in alternative_models:
        print(f"\n📋 测试替代模型: {model_id}")
        try:
            response = client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": "你好，请简单回复一下"}],
                max_tokens=50,
                temperature=0.3,
            )

            print(f"✅ 模型 {model_id} 测试成功!")
            print(f"📝 回复: {response.choices[0].message.content}")
            successful_models.append(model_id)

        except Exception as e:
            print(f"❌ 模型 {model_id} 测试失败: {e}")

    return successful_models


if __name__ == "__main__":
    print("=" * 60)
    print("🔍 R1 模型诊断测试")
    print("=" * 60)

    # 测试 R1 模型
    working_r1_model = test_r1_model()

    if working_r1_model:
        print(f"\n🎉 找到可用的 R1 模型: {working_r1_model}")
        print("💡 建议将 model_config.toml 中的 r1 模型的 model_identifier 更改为:")
        print(f'   model_identifier = "{working_r1_model}"')
    else:
        print("\n❌ 所有 R1 模型都不可用")

        # 测试替代模型
        alternatives = test_alternative_models()

        if alternatives:
            print(f"\n💡 可用的替代模型: {alternatives}")
            print("💡 建议将 model_config.toml 中的 planner 模型更改为:")
            print(f"   model_list = ['{alternatives[0]}']")
            print("   并在 models 部分添加对应的配置")
        else:
            print("\n❌ 没有找到可用的模型，请检查 API 配置")

    print("\n" + "=" * 60)
