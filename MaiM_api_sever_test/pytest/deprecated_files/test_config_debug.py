#!/usr/bin/env python3
"""
配置调试脚本
用于验证配置是否正确加载和应用
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config.isolated_config_manager import get_isolated_config_manager
from src.config.config_wrapper import UnifiedConfigWrapper
from src.config.config import global_config


def test_global_config():
    """测试全局配置"""
    print("=== 测试全局配置 ===")
    try:
        print(f"全局配置 talk_value: {global_config.chat.talk_value}")
        print(f"全局配置 auto_chat_value: {global_config.chat.auto_chat_value}")
        print(f"全局配置 planner_smooth: {global_config.chat.planner_smooth}")
    except Exception as e:
        print(f"全局配置测试失败: {e}")


def test_isolated_config():
    """测试隔离配置"""
    print("\n=== 测试隔离配置 ===")
    try:
        # 使用测试租户和智能体ID
        tenant_id = "tenant_test"
        agent_id = "agent_test"

        config_manager = get_isolated_config_manager(tenant_id, agent_id)
        effective_config = config_manager.get_effective_config()

        print(f"隔离配置原始数据: {effective_config}")

        # 测试配置包装器
        wrapper = UnifiedConfigWrapper(effective_config)
        print(f"包装器 talk_value: {wrapper.chat.get_talk_value('test_stream')}")
        print(f"包装器 auto_chat_value: {wrapper.chat.get_auto_chat_value('test_stream')}")
        print(f"包装器 planner_smooth: {wrapper.chat.planner_smooth}")

    except Exception as e:
        print(f"隔离配置测试失败: {e}")
        import traceback

        traceback.print_exc()


def test_config_direct():
    """直接测试配置文件"""
    print("\n=== 测试配置文件 ===")
    try:
        import tomlkit

        with open("config/bot_config.toml", "r", encoding="utf-8") as f:
            config_data = tomlkit.load(f)

        chat_config = config_data.get("chat", {})
        print(f"配置文件 talk_value: {chat_config.get('talk_value')}")
        print(f"配置文件 auto_chat_value: {chat_config.get('auto_chat_value')}")
        print(f"配置文件 planner_smooth: {chat_config.get('planner_smooth')}")

        # 测试包装器
        wrapper = UnifiedConfigWrapper(config_data)
        print(f"包装器 talk_value: {wrapper.chat.get_talk_value('test_stream')}")
        print(f"包装器 auto_chat_value: {wrapper.chat.get_auto_chat_value('test_stream')}")
        print(f"包装器 planner_smooth: {wrapper.chat.planner_smooth}")

    except Exception as e:
        print(f"配置文件测试失败: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_config_direct()
    test_global_config()
    test_isolated_config()
