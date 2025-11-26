#!/usr/bin/env python3
"""
测试规划器模型配置修复
"""

import sys
import asyncio
import traceback
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.common.logger import get_logger
from src.config.config import model_config

logger = get_logger("planner_model_fix")


async def test_planner_model_config():
    """测试规划器模型配置"""
    try:
        logger.info("=== 测试规划器模型配置 ===")

        # 检查模型配置
        logger.info(f"模型配置类型: {type(model_config)}")

        # 检查planner任务配置
        if hasattr(model_config, "model_task_config"):
            planner_config = model_config.model_task_config.planner
            logger.info(f"规划器配置: {planner_config}")
            if hasattr(planner_config, "model_list"):
                logger.info(f"规划器模型列表: {planner_config.model_list}")
            else:
                logger.error("规划器配置中没有model_list属性")
        else:
            logger.error("模型配置中没有model_task_config属性")

        # 尝试获取planner模型信息
        try:
            if hasattr(model_config, "get_model_info"):
                # 获取第一个planner模型
                if planner_config.model_list:
                    first_model = planner_config.model_list[0]
                    model_info = model_config.get_model_info(first_model)
                    logger.info(f"第一个规划器模型信息: {model_info}")

                    # 测试LLMRequest
                    from src.llm_models.utils_model import LLMRequest

                    request = LLMRequest(planner_config, "planner")
                    logger.info(f"LLMRequest创建成功: {request}")

                    # 测试简单的模型调用
                    test_response = await request.generate_response_async(prompt="测试", max_tokens=10)
                    logger.info(f"规划器模型测试响应: {test_response}")
                else:
                    logger.error("规划器模型列表为空")
            else:
                logger.error("model_config没有get_model_info方法")

        except Exception as e:
            logger.error(f"规划器模型测试失败: {e}")
            traceback.print_exc()

    except Exception as e:
        logger.error(f"测试失败: {e}")
        traceback.print_exc()


async def test_model_availability():
    """测试模型可用性"""
    try:
        logger.info("=== 测试模型可用性 ===")

        from src.llm_models.utils_model import LLMRequest
        from src.config.api_ada_configs import TaskConfig

        # 测试不同的模型
        models_to_test = ["siliconflow-deepseek-v3", "r1", "qwen3-30b"]

        for model_name in models_to_test:
            try:
                logger.info(f"测试模型: {model_name}")

                # 获取模型信息
                try:
                    model_info = model_config.get_model_info(model_name)
                    logger.info(f"模型 {model_name} 信息: {model_info}")

                    # 创建简单的任务配置
                    task_config = TaskConfig(model_list=[model_name], temperature=0.7, max_tokens=100)

                    # 创建LLMRequest
                    request = LLMRequest(task_config, "test")

                    # 测试调用
                    response = await request.generate_response_async(prompt="Hello", max_tokens=5)
                    logger.info(f"模型 {model_name} 测试成功: {response}")

                except KeyError as e:
                    logger.error(f"模型 {model_name} 不存在: {e}")
                except Exception as e:
                    logger.error(f"模型 {model_name} 测试失败: {e}")

            except Exception as e:
                logger.error(f"测试模型 {model_name} 时发生错误: {e}")

    except Exception as e:
        logger.error(f"测试失败: {e}")
        traceback.print_exc()


async def test_direct_client_access():
    """测试直接客户端访问"""
    try:
        logger.info("=== 测试直接客户端访问 ===")

        from src.llm_models.model_client.base_client import client_registry

        # 测试获取客户端
        if hasattr(model_config, "api_providers_dict"):
            for provider_name, provider in model_config.api_providers_dict.items():
                logger.info(f"测试API提供商: {provider_name}")
                try:
                    client = client_registry.get_client_class_instance(provider)
                    logger.info(f"提供商 {provider_name} 客户端获取成功: {client}")
                except Exception as e:
                    logger.error(f"提供商 {provider_name} 客户端获取失败: {e}")
        else:
            logger.error("model_config没有api_providers_dict属性")

    except Exception as e:
        logger.error(f"直接客户端访问测试失败: {e}")
        traceback.print_exc()


async def main():
    """主函数"""
    logger.info("开始规划器模型配置测试")

    await test_planner_model_config()
    await test_model_availability()
    await test_direct_client_access()

    logger.info("测试完成")


if __name__ == "__main__":
    asyncio.run(main())
