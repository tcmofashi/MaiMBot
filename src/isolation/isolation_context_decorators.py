"""
隔离上下文装饰器
提供便捷的装饰器，自动注入隔离上下文，支持权限验证和错误处理
"""

import functools
import inspect
import logging
from typing import Any, Callable, Optional, Dict, List, TypeVar, ParamSpec
from dataclasses import dataclass

from .isolation_context import IsolationContext, IsolationLevel, IsolationValidator
from .isolation_context_factory import get_isolation_context_factory, ContextCreationHints
from .isolation_context_manager import get_isolation_context_manager

logger = logging.getLogger(__name__)

# 类型变量
P = ParamSpec("P")
T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class ContextRequirement:
    """上下文要求"""

    required_level: Optional[IsolationLevel] = None
    allowed_tenants: Optional[List[str]] = None
    allowed_agents: Optional[List[str]] = None
    allowed_platforms: Optional[List[str]] = None
    require_chat_scope: bool = False
    auto_create_context: bool = True
    inherit_from_parent: bool = True


def with_isolation_context(
    tenant_id: str = None,
    agent_id: str = None,
    platform: str = None,
    chat_stream_id: str = None,
    context_param: str = "context",
    requirement: Optional[ContextRequirement] = None,
):
    """
    为函数注入隔离上下文的装饰器

    Args:
        tenant_id: 租户ID
        agent_id: 智能体ID
        platform: 平台
        chat_stream_id: 聊天流ID
        context_param: 上下文参数名
        requirement: 上下文要求
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 尝试从参数中获取上下文信息
            context_info = _extract_context_from_args(func, args, kwargs)

            # 确定最终的上下文参数
            final_tenant_id = tenant_id or context_info.get("tenant_id")
            final_agent_id = agent_id or context_info.get("agent_id")
            final_platform = platform or context_info.get("platform")
            final_chat_stream_id = chat_stream_id or context_info.get("chat_stream_id")

            # 获取或创建上下文
            context = _get_or_create_context(
                final_tenant_id, final_agent_id, final_platform, final_chat_stream_id, requirement
            )

            # 验证上下文
            if requirement:
                _validate_context_requirements(context, requirement)

            # 注入上下文参数
            if context_param in kwargs:
                logger.warning(f"参数 {context_param} 已存在，将被覆盖")
            kwargs[context_param] = context

            return func(*args, **kwargs)

        return wrapper  # type: ignore

    return decorator


async def async_with_isolation_context(
    tenant_id: str = None,
    agent_id: str = None,
    platform: str = None,
    chat_stream_id: str = None,
    context_param: str = "context",
    requirement: Optional[ContextRequirement] = None,
):
    """
    为异步函数注入隔离上下文的装饰器
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 尝试从参数中获取上下文信息
            context_info = _extract_context_from_args(func, args, kwargs)

            # 确定最终的上下文参数
            final_tenant_id = tenant_id or context_info.get("tenant_id")
            final_agent_id = agent_id or context_info.get("agent_id")
            final_platform = platform or context_info.get("platform")
            final_chat_stream_id = chat_stream_id or context_info.get("chat_stream_id")

            # 获取或创建上下文
            context = _get_or_create_context(
                final_tenant_id, final_agent_id, final_platform, final_chat_stream_id, requirement
            )

            # 验证上下文
            if requirement:
                _validate_context_requirements(context, requirement)

            # 注入上下文参数
            if context_param in kwargs:
                logger.warning(f"参数 {context_param} 已存在，将被覆盖")
            kwargs[context_param] = context

            return await func(*args, **kwargs)

        return wrapper  # type: ignore

    return decorator


def with_tenant_context(tenant_id: str, **kwargs):
    """指定租户的隔离上下文装饰器"""
    return with_isolation_context(tenant_id=tenant_id, **kwargs)


def with_agent_context(tenant_id: str, agent_id: str, **kwargs):
    """指定智能体的隔离上下文装饰器"""
    return with_isolation_context(tenant_id=tenant_id, agent_id=agent_id, **kwargs)


def with_platform_context(tenant_id: str, agent_id: str, platform: str, **kwargs):
    """指定平台的隔离上下文装饰器"""
    return with_isolation_context(tenant_id=tenant_id, agent_id=agent_id, platform=platform, **kwargs)


def with_chat_context(tenant_id: str, agent_id: str, platform: str, chat_stream_id: str, **kwargs):
    """指定聊天流的隔离上下文装饰器"""
    return with_isolation_context(
        tenant_id=tenant_id, agent_id=agent_id, platform=platform, chat_stream_id=chat_stream_id, **kwargs
    )


def with_context_from_message(
    message_param: str = "message", context_param: str = "context", requirement: Optional[ContextRequirement] = None
):
    """从消息自动提取隔离上下文的装饰器"""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 获取消息参数
            message = kwargs.get(message_param)
            if not message:
                # 尝试从位置参数获取
                sig = inspect.signature(func)
                param_names = list(sig.parameters.keys())
                if message_param in param_names:
                    param_index = param_names.index(message_param)
                    if param_index < len(args):
                        message = args[param_index]

            if not message:
                raise ValueError(f"无法找到消息参数: {message_param}")

            # 从消息创建上下文
            factory = get_isolation_context_factory()
            context = factory.create_from_message(message)

            # 验证上下文
            if requirement:
                _validate_context_requirements(context, requirement)

            # 注入上下文参数
            if context_param in kwargs:
                logger.warning(f"参数 {context_param} 已存在，将被覆盖")
            kwargs[context_param] = context

            return func(*args, **kwargs)

        return wrapper  # type: ignore

    return decorator


async def async_with_context_from_message(
    message_param: str = "message", context_param: str = "context", requirement: Optional[ContextRequirement] = None
):
    """从消息自动提取隔离上下文的异步装饰器"""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 获取消息参数
            message = kwargs.get(message_param)
            if not message:
                # 尝试从位置参数获取
                sig = inspect.signature(func)
                param_names = list(sig.parameters.keys())
                if message_param in param_names:
                    param_index = param_names.index(message_param)
                    if param_index < len(args):
                        message = args[param_index]

            if not message:
                raise ValueError(f"无法找到消息参数: {message_param}")

            # 从消息创建上下文
            factory = get_isolation_context_factory()
            context = factory.create_from_message(message)

            # 验证上下文
            if requirement:
                _validate_context_requirements(context, requirement)

            # 注入上下文参数
            if context_param in kwargs:
                logger.warning(f"参数 {context_param} 已存在，将被覆盖")
            kwargs[context_param] = context

            return await func(*args, **kwargs)

        return wrapper  # type: ignore

    return decorator


def with_context_validation(requirement: ContextRequirement):
    """仅进行上下文验证的装饰器"""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 尝试从参数中找到上下文
            context = _find_context_in_args(func, args, kwargs)
            if not context:
                raise ValueError("无法在函数参数中找到隔离上下文")

            # 验证上下文
            _validate_context_requirements(context, requirement)

            return func(*args, **kwargs)

        return wrapper  # type: ignore

    return decorator


def with_context_auto_injection(context_param: str = "context", requirement: Optional[ContextRequirement] = None):
    """自动注入上下文的装饰器（智能推断）"""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 尝试从参数中获取上下文信息
            context_info = _extract_context_from_args(func, args, kwargs)

            # 尝试查找现有上下文
            existing_context = _find_context_in_args(func, args, kwargs)

            if existing_context:
                context = existing_context
            elif context_info:
                # 从信息创建上下文
                context = _get_or_create_context(
                    context_info.get("tenant_id"),
                    context_info.get("agent_id"),
                    context_info.get("platform"),
                    context_info.get("chat_stream_id"),
                    requirement,
                )
            else:
                # 创建默认上下文
                context = _get_or_create_context(None, None, None, None, requirement)

            # 验证上下文
            if requirement:
                _validate_context_requirements(context, requirement)

            # 注入上下文参数
            if context_param in kwargs:
                logger.warning(f"参数 {context_param} 已存在，将被覆盖")
            kwargs[context_param] = context

            return func(*args, **kwargs)

        return wrapper  # type: ignore

    return decorator


def with_context_error_handler(default_context: Optional[IsolationContext] = None, raise_on_error: bool = True):
    """带错误处理的上下文装饰器"""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if "isolation" in str(e).lower() or "context" in str(e).lower():
                    logger.error(f"隔离上下文相关错误: {e}")

                    if default_context:
                        # 尝试使用默认上下文
                        kwargs["context"] = default_context
                        return func(*args, **kwargs)

                    if not raise_on_error:
                        logger.error("跳过函数执行 due to 上下文错误")
                        return None

                raise

        return wrapper  # type: ignore

    return decorator


def with_context_caching(cache_key_func: Optional[Callable] = None):
    """带缓存功能的上下文装饰器"""

    def decorator(func: F) -> F:
        cache = {}

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 获取上下文
            context = _find_context_in_args(func, args, kwargs)
            if not context:
                return func(*args, **kwargs)

            # 生成缓存键
            if cache_key_func:
                cache_key = cache_key_func(context, *args, **kwargs)
            else:
                cache_key = str(context.scope)

            # 检查缓存
            if cache_key in cache:
                return cache[cache_key]

            # 执行函数并缓存结果
            result = func(*args, **kwargs)
            cache[cache_key] = result
            return result

        # 添加缓存清理方法
        wrapper.clear_cache = lambda: cache.clear()  # type: ignore
        wrapper.get_cache_size = lambda: len(cache)  # type: ignore

        return wrapper  # type: ignore

    return decorator


# 辅助函数
def _extract_context_from_args(func: Callable, args: tuple, kwargs: dict) -> Dict[str, str]:
    """从函数参数中提取上下文信息"""
    context_info = {}

    # 获取函数签名
    sig = inspect.signature(func)
    param_names = list(sig.parameters.keys())

    # 检查位置参数
    for i, arg in enumerate(args):
        if i < len(param_names):
            param_name = param_names[i]
            context_info.update(_extract_from_value(arg, param_name))

    # 检查关键字参数
    for param_name, value in kwargs.items():
        context_info.update(_extract_from_value(value, param_name))

    return context_info


def _extract_from_value(value: Any, param_name: str) -> Dict[str, str]:
    """从值中提取上下文信息"""
    context_info = {}

    # 如果是字典，尝试提取上下文字段
    if isinstance(value, dict):
        for field in ["tenant_id", "agent_id", "platform", "chat_stream_id"]:
            if field in value and value[field]:
                context_info[field] = value[field]

    # 如果是对象，尝试提取属性
    elif hasattr(value, "tenant_id"):
        context_info["tenant_id"] = value.tenant_id
    elif hasattr(value, "agent_id"):
        context_info["agent_id"] = value.agent_id
    elif hasattr(value, "platform"):
        context_info["platform"] = value.platform
    elif hasattr(value, "chat_stream_id"):
        context_info["chat_stream_id"] = value.chat_stream_id

    # 根据参数名推断
    elif param_name == "tenant_id" and value:
        context_info["tenant_id"] = str(value)
    elif param_name == "agent_id" and value:
        context_info["agent_id"] = str(value)
    elif param_name == "platform" and value:
        context_info["platform"] = str(value)
    elif param_name == "chat_stream_id" and value:
        context_info["chat_stream_id"] = str(value)

    return context_info


def _find_context_in_args(func: Callable, args: tuple, kwargs: dict) -> Optional[IsolationContext]:
    """在函数参数中查找隔离上下文"""
    # 检查关键字参数
    for value in kwargs.values():
        if isinstance(value, IsolationContext):
            return value

    # 检查位置参数
    for arg in args:
        if isinstance(arg, IsolationContext):
            return arg

    return None


def _get_or_create_context(
    tenant_id: str, agent_id: str, platform: str, chat_stream_id: str, requirement: Optional[ContextRequirement] = None
) -> IsolationContext:
    """获取或创建隔离上下文"""
    manager = get_isolation_context_manager()

    # 如果有完整的上下文信息，尝试获取现有上下文
    if tenant_id and agent_id:
        context = manager.get_context(
            tenant_id,
            agent_id,
            platform,
            chat_stream_id,
            auto_create=requirement.auto_create_context if requirement else True,
        )
        if context:
            return context

    # 使用工厂创建新上下文
    factory = get_isolation_context_factory()
    hints = ContextCreationHints(fallback_to_default=requirement.auto_create_context if requirement else True)

    return factory.create_explicit(tenant_id or "default", agent_id or "default", platform, chat_stream_id, hints)


def _validate_context_requirements(context: IsolationContext, requirement: ContextRequirement):
    """验证上下文要求"""
    # 验证隔离级别
    if requirement.required_level:
        if not IsolationValidator.validate_context(context, requirement.required_level):
            raise ValueError(f"上下文不满足要求的隔离级别: {requirement.required_level}")

    # 验证租户权限
    if requirement.allowed_tenants and context.tenant_id not in requirement.allowed_tenants:
        raise ValueError(f"租户 {context.tenant_id} 不在允许列表中: {requirement.allowed_tenants}")

    # 验证智能体权限
    if requirement.allowed_agents and context.agent_id not in requirement.allowed_agents:
        raise ValueError(f"智能体 {context.agent_id} 不在允许列表中: {requirement.allowed_agents}")

    # 验证平台权限
    if requirement.allowed_platforms:
        if not context.platform or context.platform not in requirement.allowed_platforms:
            raise ValueError(f"平台 {context.platform} 不在允许列表中: {requirement.allowed_platforms}")

    # 验证聊天范围要求
    if requirement.require_chat_scope and not context.chat_stream_id:
        raise ValueError("函数要求聊天流级别的隔离上下文")


# 便捷的验证要求创建函数
def tenant_level_requirement(allowed_tenants: List[str] = None) -> ContextRequirement:
    """创建租户级别要求"""
    return ContextRequirement(required_level=IsolationLevel.TENANT, allowed_tenants=allowed_tenants)


def agent_level_requirement(allowed_tenants: List[str] = None, allowed_agents: List[str] = None) -> ContextRequirement:
    """创建智能体级别要求"""
    return ContextRequirement(
        required_level=IsolationLevel.AGENT, allowed_tenants=allowed_tenants, allowed_agents=allowed_agents
    )


def platform_level_requirement(
    allowed_tenants: List[str] = None, allowed_agents: List[str] = None, allowed_platforms: List[str] = None
) -> ContextRequirement:
    """创建平台级别要求"""
    return ContextRequirement(
        required_level=IsolationLevel.PLATFORM,
        allowed_tenants=allowed_tenants,
        allowed_agents=allowed_agents,
        allowed_platforms=allowed_platforms,
    )


def chat_level_requirement(
    allowed_tenants: List[str] = None, allowed_agents: List[str] = None, allowed_platforms: List[str] = None
) -> ContextRequirement:
    """创建聊天级别要求"""
    return ContextRequirement(
        required_level=IsolationLevel.CHAT,
        allowed_tenants=allowed_tenants,
        allowed_agents=allowed_agents,
        allowed_platforms=allowed_platforms,
        require_chat_scope=True,
    )
