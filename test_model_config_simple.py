#!/usr/bin/env python3
"""
简化的模型配置测试脚本
只检查配置文件的语法和结构，不导入复杂的系统依赖
"""

import os
import sys
import toml
from typing import Dict, Any

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def load_model_config() -> Dict[str, Any]:
    """加载模型配置文件"""
    config_path = os.path.join(os.path.dirname(__file__), "config", "model_config.toml")

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"模型配置文件不存在: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = toml.load(f)

    return config


def validate_model_config(config: Dict[str, Any]) -> bool:
    """验证模型配置的正确性"""
    print("🔍 验证模型配置...")

    # 检查基本结构 - 使用实际的配置结构
    required_sections = ["api_providers", "models", "model_task_config"]
    for section in required_sections:
        if section not in config:
            print(f"❌ 缺少必需的配置节: {section}")
            return False
        print(f"✅ 找到配置节: {section}")

    # 检查model_task_config中的planner和replyer配置
    model_task_config = config.get("model_task_config", {})

    if "planner" not in model_task_config:
        print("❌ model_task_config配置缺少planner字段")
        return False

    if "replyer" not in model_task_config:
        print("❌ model_task_config配置缺少replyer字段")
        return False

    planner_config = model_task_config["planner"]
    replyer_config = model_task_config["replyer"]

    # 获取模型列表
    planner_models = planner_config.get("model_list", [])
    replyer_models = replyer_config.get("model_list", [])

    if not planner_models:
        print("❌ planner配置中没有指定模型")
        return False

    if not replyer_models:
        print("❌ replyer配置中没有指定模型")
        return False

    planner_model = planner_models[0]  # 取第一个模型
    replyer_model = replyer_models[0]  # 取第一个模型

    print(f"📋 Planner模型: {planner_model}")
    print(f"📋 Replyer模型: {replyer_model}")

    # 检查模型是否在models配置中定义
    models_config = config.get("models", [])
    models_dict = {model["name"]: model for model in models_config}

    for model_name in [planner_model, replyer_model]:
        if model_name not in models_dict:
            print(f"❌ 模型 {model_name} 在models中未定义")
            return False

        model_info = models_dict[model_name]
        if "api_provider" not in model_info:
            print(f"❌ 模型 {model_name} 缺少api_provider配置")
            return False

        api_provider = model_info["api_provider"]
        print(f"✅ 模型 {model_name} 使用API提供商: {api_provider}")

        # 检查API提供商配置
        api_providers = config.get("api_providers", [])
        providers_dict = {provider["name"]: provider for provider in api_providers}

        if api_provider not in providers_dict:
            print(f"❌ API提供商 {api_provider} 未配置")
            return False

        provider_config = providers_dict[api_provider]
        if "base_url" not in provider_config:
            print(f"⚠️  API提供商 {api_provider} 缺少base_url配置")
        else:
            print(f"✅ API提供商 {api_provider} base_url: {provider_config['base_url']}")

    return True


def check_api_provider_consistency(config: Dict[str, Any]) -> bool:
    """检查API提供商一致性"""
    print("\n🔍 检查API提供商一致性...")

    models_config = config.get("models", [])
    api_providers_config = config.get("api_providers", [])

    # 转换为字典便于查找
    api_providers_dict = {provider["name"]: provider for provider in api_providers_config}

    # 检查每个模型的API提供商是否正确配置
    for model_config in models_config:
        model_name = model_config.get("name")
        api_provider = model_config.get("api_provider")

        if not model_name:
            print("❌ 发现缺少name的模型配置")
            return False

        if not api_provider:
            print(f"❌ 模型 {model_name} 未指定API提供商")
            return False

        if api_provider not in api_providers_dict:
            print(f"❌ 模型 {model_name} 的API提供商 {api_provider} 未在api_providers中定义")
            return False

        provider_config = api_providers_dict[api_provider]

        # 检查关键配置项
        required_keys = ["base_url"]
        for key in required_keys:
            if key not in provider_config:
                print(f"⚠️  API提供商 {api_provider} 缺少 {key} 配置")

        print(f"✅ 模型 {model_name} -> API提供商 {api_provider} 配置正确")

    return True


def main():
    """主函数"""
    print("🧪 开始简化模型配置测试")
    print("=" * 50)

    try:
        # 加载配置
        print("📂 加载模型配置文件...")
        config = load_model_config()
        print("✅ 配置文件加载成功")

        # 验证配置结构
        if not validate_model_config(config):
            print("\n❌ 模型配置验证失败")
            return False

        # 检查API提供商一致性
        if not check_api_provider_consistency(config):
            print("\n❌ API提供商一致性检查失败")
            return False

        print("\n🎉 模型配置验证通过！")
        print("\n📋 配置摘要:")

        model_task_config = config.get("model_task_config", {})
        models_config = config.get("models", [])
        models_dict = {model["name"]: model for model in models_config}

        planner_models = model_task_config.get("planner", {}).get("model_list", [])
        replyer_models = model_task_config.get("replyer", {}).get("model_list", [])

        planner_model = planner_models[0] if planner_models else "N/A"
        replyer_model = replyer_models[0] if replyer_models else "N/A"

        print(f"  • Planner模型: {planner_model}")
        if planner_model in models_dict:
            print(f"    - API提供商: {models_dict[planner_model].get('api_provider')}")
            print(f"    - 模型标识符: {models_dict[planner_model].get('model_identifier', 'N/A')}")

        print(f"  • Replyer模型: {replyer_model}")
        if replyer_model in models_dict:
            print(f"    - API提供商: {models_dict[replyer_model].get('api_provider')}")
            print(f"    - 模型标识符: {models_dict[replyer_model].get('model_identifier', 'N/A')}")

        return True

    except Exception as e:
        print(f"\n❌ 测试过程中发生错误: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
