#!/usr/bin/env python3
"""
测试租户模式下插件禁用功能
"""

import sys
import os
import asyncio
import logging

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config.config import global_config
from src.plugin_system.core.plugin_manager import plugin_manager

# 设置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def test_plugin_config():
    """测试插件配置"""
    logger.info("=== 测试插件配置 ===")

    try:
        plugin_config = global_config.plugin
        logger.info(f"插件启用状态: {plugin_config.enable_plugins}")
        logger.info(f"租户模式禁用插件: {plugin_config.tenant_mode_disable_plugins}")
        logger.info(f"允许的插件列表: {plugin_config.allowed_plugins}")
        logger.info(f"阻止的插件列表: {plugin_config.blocked_plugins}")

        return plugin_config
    except Exception as e:
        logger.error(f"获取插件配置失败: {e}")
        return None


def test_plugin_loading():
    """测试插件加载"""
    logger.info("=== 测试插件加载 ===")

    try:
        # 检查插件管理器状态
        logger.info(f"插件管理器类型: {type(plugin_manager)}")
        logger.info(f"已加载插件数量: {len(plugin_manager.plugins)}")

        # 列出已加载的插件
        for plugin_name, plugin_info in plugin_manager.plugins.items():
            logger.info(f"已加载插件: {plugin_name} - {plugin_info}")

        return len(plugin_manager.plugins)
    except Exception as e:
        logger.error(f"测试插件加载失败: {e}")
        return 0


async def test_tenant_mode_detection():
    """测试租户模式检测"""
    logger.info("=== 测试租户模式检测 ===")

    try:
        # 模拟主系统的租户模式检测逻辑
        from src.core.instance_manager_api import get_instance_manager_api

        instance_manager = get_instance_manager_api()
        is_tenant_mode = hasattr(instance_manager, "__class__") and instance_manager is not None

        logger.info(f"实例管理器类型: {type(instance_manager)}")
        logger.info(f"检测到租户模式: {is_tenant_mode}")

        return is_tenant_mode
    except Exception as e:
        logger.error(f"租户模式检测失败: {e}")
        return False


async def main():
    """主测试函数"""
    logger.info("开始测试租户模式下插件禁用功能...")

    # 测试插件配置
    plugin_config = test_plugin_config()
    if not plugin_config:
        logger.error("插件配置测试失败，退出测试")
        return

    # 测试租户模式检测
    is_tenant_mode = await test_tenant_mode_detection()

    # 根据配置决定是否应该加载插件
    should_load_plugins = True

    if not plugin_config.enable_plugins:
        logger.info("插件系统已禁用")
        should_load_plugins = False
    elif plugin_config.tenant_mode_disable_plugins and is_tenant_mode:
        logger.info("租户模式下禁用插件")
        should_load_plugins = False

    logger.info(f"是否应该加载插件: {should_load_plugins}")

    # 测试插件加载
    if should_load_plugins:
        logger.info("开始加载插件...")
        plugin_manager.load_all_plugins()
        logger.info("插件加载完成")
    else:
        logger.info("跳过插件加载")

    # 检查最终结果
    loaded_count = test_plugin_loading()

    if should_load_plugins and loaded_count > 0:
        logger.info("✅ 测试通过：插件已正常加载")
    elif not should_load_plugins and loaded_count == 0:
        logger.info("✅ 测试通过：插件已正确禁用")
    elif should_load_plugins and loaded_count == 0:
        logger.warning("⚠️  测试警告：应该加载插件但没有插件被加载")
    else:
        logger.warning("⚠️  测试警告：不应该加载插件但仍有插件被加载")

    logger.info("测试完成")


if __name__ == "__main__":
    asyncio.run(main())
