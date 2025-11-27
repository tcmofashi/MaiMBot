#!/usr/bin/env python3
"""
调试配置错误的脚本
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from src.isolation.isolation_context import IsolationContext
from src.config.config_wrapper import UnifiedConfigWrapper


def test_config_wrapper():
    """测试配置包装器"""
    print("=== 测试配置包装器 ===")

    # 测试字典配置
    dict_config = {
        "chat": {"talk_value": 1.0, "auto_chat_value": 1.0, "planner_smooth": 0, "mentioned_bot_reply": True}
    }

    wrapper = UnifiedConfigWrapper(dict_config)
    print(f"配置类型: {type(wrapper)}")
    print(f"配置数据: {wrapper._config_data}")

    # 测试chat属性
    try:
        chat_config = wrapper.chat
        print(f"Chat配置类型: {type(chat_config)}")
        print(f"Talk value: {chat_config.get_talk_value('test_stream')}")
    except Exception as e:
        print(f"获取chat配置失败: {e}")
        import traceback

        traceback.print_exc()

    # 测试对象配置
    class MockConfig:
        def __init__(self):
            self.chat = MockChatConfig()

    class MockChatConfig:
        def __init__(self):
            self.talk_value = 0.5

        def get_talk_value(self, stream_id):
            return self.talk_value

    obj_config = MockConfig()
    wrapper2 = UnifiedConfigWrapper(obj_config)
    print(f"\n对象配置类型: {type(wrapper2)}")

    try:
        chat_config2 = wrapper2.chat
        print(f"Chat配置类型: {type(chat_config2)}")
        print(f"Talk value: {chat_config2.get_talk_value('test_stream')}")
    except Exception as e:
        print(f"获取chat配置失败: {e}")
        import traceback

        traceback.print_exc()


def test_isolation_context_config():
    """测试隔离上下文配置"""
    print("\n=== 测试隔离上下文配置 ===")

    try:
        # 创建隔离上下文
        isolation_context = IsolationContext(
            tenant_id="test_tenant", agent_id="test_agent", platform="test", chat_stream_id="test_stream"
        )

        print(f"隔离上下文: {isolation_context}")
        print(f"是否有get_config_manager: {hasattr(isolation_context, 'get_config_manager')}")

        if hasattr(isolation_context, "get_config_manager"):
            config_manager = isolation_context.get_config_manager()
            print(f"配置管理器: {config_manager}")

            if hasattr(config_manager, "get_isolated_config"):
                raw_config = config_manager.get_isolated_config(platform="test")
                print(f"原始配置类型: {type(raw_config)}")
                print(f"原始配置: {raw_config}")

                wrapper = UnifiedConfigWrapper(raw_config)
                print(f"包装器类型: {type(wrapper)}")

                try:
                    chat_config = wrapper.chat
                    print(f"Chat配置类型: {type(chat_config)}")
                    print(f"Talk value: {chat_config.get_talk_value('test_stream')}")
                except Exception as e:
                    print(f"获取chat配置失败: {e}")
                    import traceback

                    traceback.print_exc()
            else:
                print("配置管理器没有get_isolated_config方法")
        else:
            print("隔离上下文没有get_config_manager方法")

    except Exception as e:
        print(f"测试隔离上下文配置失败: {e}")
        import traceback

        traceback.print_exc()


def test_global_config():
    """测试全局配置"""
    print("\n=== 测试全局配置 ===")

    try:
        from src.config.config import global_config

        print(f"全局配置类型: {type(global_config)}")

        wrapper = UnifiedConfigWrapper(global_config)
        print(f"包装器类型: {type(wrapper)}")

        try:
            chat_config = wrapper.chat
            print(f"Chat配置类型: {type(chat_config)}")
            print(f"Talk value: {chat_config.get_talk_value('test_stream')}")
        except Exception as e:
            print(f"获取chat配置失败: {e}")
            import traceback

            traceback.print_exc()

    except Exception as e:
        print(f"测试全局配置失败: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_config_wrapper()
    test_isolation_context_config()
    test_global_config()
