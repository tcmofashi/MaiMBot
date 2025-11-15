"""
隔离上下文使用示例
展示如何使用完整的隔离上下文抽象系统
"""

from typing import Dict, Any

from .isolation_context import IsolationContext
from .isolation_context_factory import get_isolation_context_factory
from .isolation_context_manager import get_isolation_context_manager
from .isolation_context_decorators import with_isolation_context, with_context_from_message, tenant_level_requirement
from .isolation_context_utils import serialize_context, analyze_context, compare_contexts


def example_basic_usage():
    """基础使用示例"""
    print("=== 基础使用示例 ===")

    # 1. 创建隔离上下文
    context = IsolationContext(tenant_id="company_a", agent_id="bot_001", platform="qq", chat_stream_id="group_123")

    # 2. 获取隔离资源
    context.get_config_manager()
    context.get_memory_chest()
    context.get_chat_manager()

    print(f"记忆范围: {context.get_memory_scope()}")
    print(f"隔离级别: {context.get_isolation_level()}")

    # 3. 创建子上下文
    sub_context = context.create_sub_context(chat_stream_id="group_456")
    print(f"子上下文范围: {sub_context.get_memory_scope()}")


def example_factory_usage():
    """工厂使用示例"""
    print("\n=== 工厂使用示例 ===")

    factory = get_isolation_context_factory()

    # 模拟消息数据
    message_data = {"tenant_id": "company_b", "agent_id": "bot_002", "platform": "wechat", "chat_stream_id": "chat_789"}

    # 从消息创建上下文
    context = factory.create_from_message(message_data)
    print(f"从消息创建的上下文: {context.get_memory_scope()}")

    # 从用户请求创建上下文
    user_request = {"user_id": "user123", "tenant_id": "company_c", "agent_id": "bot_003"}
    context = factory.create_from_user_request("user123", user_request)
    print(f"从用户请求创建的上下文: {context.get_memory_scope()}")


def example_manager_usage():
    """管理器使用示例"""
    print("\n=== 管理器使用示例 ===")

    manager = get_isolation_context_manager()

    # 创建上下文
    context1 = manager.create_context(tenant_id="company_a", agent_id="bot_001", platform="qq")

    # 创建子上下文
    context2 = manager.create_child_context(parent_context=context1, chat_stream_id="group_123")

    # 获取统计信息
    stats = manager.get_context_statistics()
    print(f"活跃上下文数量: {stats['total_contexts']}")
    print(f"上下文层次: {len(manager.get_context_hierarchy(context2))}")


@with_isolation_context(tenant_id="company_a", agent_id="bot_001", requirement=tenant_level_requirement())
def example_decorator_usage(context: IsolationContext, message: str):
    """装饰器使用示例"""
    print("\n=== 装饰器使用示例 ===")
    print(f"上下文范围: {context.get_memory_scope()}")
    print(f"处理消息: {message}")

    # 获取隔离资源
    context.get_config_manager()
    context.get_memory_chest()
    print("成功获取隔离资源")


def example_utils_usage():
    """工具使用示例"""
    print("\n=== 工具使用示例 ===")

    context1 = IsolationContext("company_a", "bot_001", "qq", "group_123")
    context2 = IsolationContext("company_a", "bot_001", "wechat")

    # 序列化
    serialized = serialize_context(context1, "json")
    print(f"序列化长度: {len(serialized)} 字符")

    # 分析
    analysis = analyze_context(context1)
    print(f"隔离深度: {analysis['isolation_depth']['depth']}")
    print(f"隔离维度: {analysis['isolation_depth']['dimensions']}")

    # 比较
    comparison = compare_contexts(context1, context2)
    print(f"上下文相等: {comparison['equal']}")
    print(f"上下文兼容: {comparison['compatible']}")


@with_context_from_message(message_param="msg")
def example_message_decorator(context: IsolationContext, msg: Dict[str, Any]):
    """消息装饰器使用示例"""
    print("\n=== 消息装饰器使用示例 ===")
    print(f"从消息推断的上下文: {context.get_memory_scope()}")
    print(f"消息内容: {msg.get('content', 'No content')}")


def main():
    """主函数，运行所有示例"""
    try:
        example_basic_usage()
        example_factory_usage()
        example_manager_usage()
        example_decorator_usage("Hello, World!")
        example_utils_usage()

        # 消息装饰器示例
        message = {
            "tenant_id": "company_d",
            "agent_id": "bot_004",
            "platform": "discord",
            "content": "Hello from Discord!",
        }
        example_message_decorator(message)

        print("\n=== 所有示例运行完成 ===")

    except Exception as e:
        print(f"示例运行出错: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
