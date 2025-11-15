"""
多租户隔离模块
提供T+A+C+P四维隔离支持
"""

from .isolation_context import (
    IsolationContext,
    IsolationScope,
    IsolationLevel,
    IsolationContextManager,
    get_isolation_context_manager,
    create_isolation_context,
    get_isolation_context,
    with_isolation_context,
    async_with_isolation_context,
    IsolationValidator,
    parse_isolation_scope,
    generate_isolated_id,
    extract_isolation_from_id,
)

from .isolated_chat_stream import (
    IsolatedChatMessageContext,
    IsolatedChatStream,
    IsolatedChatManager,
    IsolatedChatManagerManager,
    get_isolated_chat_manager,
    clear_isolated_chat_manager,
    clear_all_isolated_chat_managers,
)

from .multi_tenant_adapter import (
    TenantMessageConfig,
    MultiTenantMessageAdapter,
    get_multi_tenant_adapter,
    initialize_multi_tenant_system,
    process_tenant_message,
    send_tenant_message,
)

from .isolated_chat_bot import (
    IsolatedChatBot,
    IsolatedChatBotManager,
    get_isolated_chat_bot,
    cleanup_isolated_chat_bot,
    cleanup_all_isolated_chat_bots,
    get_isolated_chat_bot_manager,
)

__all__ = [
    "IsolationContext",
    "IsolationScope",
    "IsolationLevel",
    "IsolationContextManager",
    "get_isolation_context_manager",
    "create_isolation_context",
    "get_isolation_context",
    "with_isolation_context",
    "async_with_isolation_context",
    "IsolationValidator",
    "parse_isolation_scope",
    "generate_isolated_id",
    "extract_isolation_from_id",
    "IsolatedChatMessageContext",
    "IsolatedChatStream",
    "IsolatedChatManager",
    "IsolatedChatManagerManager",
    "get_isolated_chat_manager",
    "clear_isolated_chat_manager",
    "clear_all_isolated_chat_managers",
    "TenantMessageConfig",
    "MultiTenantMessageAdapter",
    "get_multi_tenant_adapter",
    "initialize_multi_tenant_system",
    "process_tenant_message",
    "send_tenant_message",
    "IsolatedChatBot",
    "IsolatedChatBotManager",
    "get_isolated_chat_bot",
    "cleanup_isolated_chat_bot",
    "cleanup_all_isolated_chat_bots",
    "get_isolated_chat_bot_manager",
]
