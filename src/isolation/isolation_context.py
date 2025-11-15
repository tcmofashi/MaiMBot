"""
多租户隔离上下文抽象层
管理T+A+C+P四维隔离：租户(T) + 智能体(A) + 聊天流(C) + 平台(P)
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum
import threading
import weakref


class IsolationLevel(Enum):
    """隔离级别枚举"""

    TENANT = "tenant"  # 租户级别隔离
    AGENT = "agent"  # 智能体级别隔离
    CHAT = "chat"  # 聊天流级别隔离
    PLATFORM = "platform"  # 平台级别隔离


@dataclass
class IsolationScope:
    """隔离范围标识"""

    tenant_id: str  # T: 租户标识
    agent_id: str  # A: 智能体标识
    platform: Optional[str] = None  # P: 平台标识
    chat_stream_id: Optional[str] = None  # C: 聊天流标识

    def __str__(self) -> str:
        """生成隔离范围的字符串表示"""
        components = [self.tenant_id, self.agent_id]
        if self.platform:
            components.append(self.platform)
        if self.chat_stream_id:
            components.append(self.chat_stream_id)
        return ":".join(components)

    def __hash__(self) -> int:
        """支持作为字典键"""
        return hash(str(self))

    def __eq__(self, other) -> bool:
        """支持比较"""
        if not isinstance(other, IsolationScope):
            return False
        return str(self) == str(other)


class IsolationContext:
    """隔离上下文抽象类，管理T+A+C+P四维隔离"""

    def __init__(self, tenant_id: str, agent_id: str, platform: str = None, chat_stream_id: str = None):
        self.tenant_id = tenant_id  # T: 租户隔离
        self.agent_id = agent_id  # A: 智能体隔离
        self.platform = platform  # P: 平台隔离
        self.chat_stream_id = chat_stream_id  # C: 聊天流隔离

        # 生成隔离范围
        self.scope = IsolationScope(
            tenant_id=tenant_id, agent_id=agent_id, platform=platform, chat_stream_id=chat_stream_id
        )

        # 缓存管理器实例，避免重复创建
        self._manager_cache: Dict[str, Any] = {}
        self._cache_lock = threading.RLock()

    def get_memory_scope(self) -> str:
        """生成记忆域标识"""
        return str(self.scope)

    def get_config_scope(self) -> str:
        """生成配置域标识"""
        return str(self.scope)

    def get_event_scope(self) -> str:
        """生成事件域标识"""
        return str(self.scope)

    def get_isolation_level(self) -> IsolationLevel:
        """确定当前的隔离级别"""
        if self.chat_stream_id:
            return IsolationLevel.CHAT
        elif self.platform:
            return IsolationLevel.PLATFORM
        elif self.agent_id:
            return IsolationLevel.AGENT
        else:
            return IsolationLevel.TENANT

    def create_sub_context(self, platform: str = None, chat_stream_id: str = None) -> "IsolationContext":
        """创建子隔离上下文"""
        return IsolationContext(
            tenant_id=self.tenant_id,
            agent_id=self.agent_id,
            platform=platform or self.platform,
            chat_stream_id=chat_stream_id,
        )

    def get_cached_manager(self, manager_type: str, factory_func):
        """获取缓存的管理器实例"""
        cache_key = f"{manager_type}:{str(self.scope)}"

        with self._cache_lock:
            if cache_key not in self._manager_cache:
                self._manager_cache[cache_key] = factory_func()
            return self._manager_cache[cache_key]

    def clear_cache(self):
        """清理缓存"""
        with self._cache_lock:
            self._manager_cache.clear()

    def get_config_manager(self):
        """获取隔离的配置管理器"""
        from src.config.isolated_config_manager import get_isolated_config_manager

        return get_isolated_config_manager(self.tenant_id, self.agent_id)

    def get_memory_chest(self):
        """获取隔离的记忆系统"""
        from src.memory_system.isolated_memory_chest import get_isolated_memory_chest

        return get_isolated_memory_chest(self.tenant_id, self.agent_id, self.platform, self.chat_stream_id)

    def get_chat_manager(self):
        """获取隔离的聊天管理器"""
        from src.chat.heart_flow.isolated_heartflow import get_isolated_chat_manager

        return get_isolated_chat_manager(self.tenant_id, self.agent_id, self.platform)

    def get_events_manager(self):
        """获取隔离的事件管理器"""
        raise NotImplementedError("子类需要实现此方法")

    def get_agent_manager(self):
        """获取隔离的智能体管理器"""
        # 动态导入避免循环依赖
        from src.agent.manager import get_isolated_agent_manager

        return get_isolated_agent_manager(self.tenant_id)


class IsolationContextManager:
    """隔离上下文管理器，负责创建和管理隔离上下文实例"""

    def __init__(self):
        self._contexts: Dict[str, IsolationContext] = {}
        self._lock = threading.RLock()
        self._weak_refs: Dict[str, weakref.ref] = {}

    def create_context(
        self, tenant_id: str, agent_id: str, platform: str = None, chat_stream_id: str = None
    ) -> IsolationContext:
        """创建隔离上下文"""
        scope = IsolationScope(tenant_id, agent_id, platform, chat_stream_id)
        scope_key = str(scope)

        with self._lock:
            # 检查弱引用是否仍然有效
            if scope_key in self._weak_refs:
                context_ref = self._weak_refs[scope_key]
                context = context_ref()
                if context is not None:
                    return context

            # 创建新的上下文
            context = IsolationContext(tenant_id, agent_id, platform, chat_stream_id)

            # 使用弱引用存储，避免内存泄漏
            self._weak_refs[scope_key] = weakref.ref(context)

            return context

    def get_context(
        self, tenant_id: str, agent_id: str, platform: str = None, chat_stream_id: str = None
    ) -> IsolationContext:
        """获取隔离上下文（不存在则创建）"""
        return self.create_context(tenant_id, agent_id, platform, chat_stream_id)

    def clear_tenant_contexts(self, tenant_id: str):
        """清理指定租户的所有上下文"""
        with self._lock:
            keys_to_remove = []
            for key, _ref in self._weak_refs.items():
                if key.startswith(f"{tenant_id}:"):
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                del self._weak_refs[key]

    def cleanup_expired_contexts(self):
        """清理已过期的上下文引用"""
        with self._lock:
            expired_keys = []
            for key, ref in self._weak_refs.items():
                if ref() is None:
                    expired_keys.append(key)

            for key in expired_keys:
                del self._weak_refs[key]

    def get_active_context_count(self) -> int:
        """获取活跃的上下文数量"""
        self.cleanup_expired_contexts()
        with self._lock:
            return len(self._weak_refs)


# 全局隔离上下文管理器实例
_global_context_manager = IsolationContextManager()


def get_isolation_context_manager() -> IsolationContextManager:
    """获取全局隔离上下文管理器"""
    return _global_context_manager


def create_isolation_context(
    tenant_id: str, agent_id: str, platform: str = None, chat_stream_id: str = None
) -> IsolationContext:
    """创建隔离上下文的便捷函数"""
    return _global_context_manager.create_context(tenant_id, agent_id, platform, chat_stream_id)


def get_isolation_context(
    tenant_id: str, agent_id: str, platform: str = None, chat_stream_id: str = None
) -> IsolationContext:
    """获取隔离上下文的便捷函数"""
    return _global_context_manager.get_context(tenant_id, agent_id, platform, chat_stream_id)


# 隔离上下文装饰器
def with_isolation_context(tenant_id: str, agent_id: str, platform: str = None, chat_stream_id: str = None):
    """为函数注入隔离上下文的装饰器"""

    def decorator(func):
        def wrapper(*args, **kwargs):
            context = create_isolation_context(tenant_id, agent_id, platform, chat_stream_id)
            return func(context, *args, **kwargs)

        return wrapper

    return decorator


async def async_with_isolation_context(tenant_id: str, agent_id: str, platform: str = None, chat_stream_id: str = None):
    """为异步函数注入隔离上下文的装饰器"""

    def decorator(func):
        async def wrapper(*args, **kwargs):
            context = create_isolation_context(tenant_id, agent_id, platform, chat_stream_id)
            return await func(context, *args, **kwargs)

        return wrapper

    return decorator


# 隔离上下文验证器
class IsolationValidator:
    """隔离上下文验证器"""

    @staticmethod
    def validate_context(context: IsolationContext, required_level: IsolationLevel) -> bool:
        """验证隔离上下文是否满足要求的隔离级别"""
        current_level = context.get_isolation_level()

        level_priority = {
            IsolationLevel.TENANT: 1,
            IsolationLevel.AGENT: 2,
            IsolationLevel.PLATFORM: 3,
            IsolationLevel.CHAT: 4,
        }

        return level_priority.get(current_level, 0) >= level_priority.get(required_level, 0)

    @staticmethod
    def validate_tenant_access(context: IsolationContext, target_tenant_id: str) -> bool:
        """验证租户访问权限"""
        return context.tenant_id == target_tenant_id

    @staticmethod
    def validate_agent_access(context: IsolationContext, target_agent_id: str) -> bool:
        """验证智能体访问权限"""
        return context.tenant_id == target_agent_id.split(":")[0] and context.agent_id == target_agent_id.split(":")[1]


# 隔离上下文工具函数
def parse_isolation_scope(scope_str: str) -> IsolationScope:
    """从字符串解析隔离范围"""
    parts = scope_str.split(":")

    if len(parts) < 2:
        raise ValueError("隔离范围字符串至少需要包含tenant_id和agent_id")

    return IsolationScope(
        tenant_id=parts[0],
        agent_id=parts[1],
        platform=parts[2] if len(parts) > 2 else None,
        chat_stream_id=parts[3] if len(parts) > 3 else None,
    )


def generate_isolated_id(base_id: str, context: IsolationContext, prefix: str = "") -> str:
    """生成带隔离上下文的ID"""
    scope_str = str(context.scope)
    if prefix:
        return f"{prefix}:{scope_str}:{base_id}"
    else:
        return f"{scope_str}:{base_id}"


def extract_isolation_from_id(isolated_id: str) -> tuple[str, str]:
    """从隔离ID中提取基础ID和隔离范围"""
    parts = isolated_id.split(":", 2)  # 最多分割2次
    if len(parts) >= 2:
        scope_str = parts[0]
        base_id = ":".join(parts[1:]) if len(parts) > 2 else parts[1]
        return base_id, scope_str
    return isolated_id, ""
