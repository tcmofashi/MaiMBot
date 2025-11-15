"""
隔离上下文工厂
支持多种方式创建隔离上下文，提供便捷的推断和创建功能
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import logging

from .isolation_context import IsolationContext, IsolationScope, IsolationLevel

logger = logging.getLogger(__name__)


@dataclass
class ContextCreationHints:
    """上下文创建提示"""

    preferred_tenant_id: Optional[str] = None
    preferred_agent_id: Optional[str] = None
    preferred_platform: Optional[str] = None
    preferred_chat_stream_id: Optional[str] = None
    required_isolation_level: Optional[IsolationLevel] = None
    allow_context_inheritance: bool = True
    fallback_to_default: bool = True


class IsolationContextFactory:
    """隔离上下文工厂类"""

    def __init__(self):
        self._default_tenant_id = "default"
        self._default_agent_id = "default"
        self._default_platform = "default"
        self._context_creation_rules: List[callable] = []
        self._global_hints = ContextCreationHints()

    def set_defaults(self, tenant_id: str = "default", agent_id: str = "default", platform: str = "default"):
        """设置默认值"""
        self._default_tenant_id = tenant_id
        self._default_agent_id = agent_id
        self._default_platform = platform

    def set_global_hints(self, hints: ContextCreationHints):
        """设置全局提示"""
        self._global_hints = hints

    def add_creation_rule(self, rule_func: callable):
        """添加上下文创建规则"""
        self._context_creation_rules.append(rule_func)

    def create_from_message(self, message: Any, hints: Optional[ContextCreationHints] = None) -> IsolationContext:
        """从消息创建隔离上下文"""
        hints = hints or self._global_hints

        # 尝试从消息中提取隔离信息
        tenant_id, agent_id, platform, chat_stream_id = self._extract_from_message(message)

        # 应用提示
        tenant_id = hints.preferred_tenant_id or tenant_id or self._default_tenant_id
        agent_id = hints.preferred_agent_id or agent_id or self._default_agent_id
        platform = hints.preferred_platform or platform or self._default_platform
        chat_stream_id = hints.preferred_chat_stream_id or chat_stream_id

        return self._create_context_with_validation(tenant_id, agent_id, platform, chat_stream_id, hints)

    def create_from_user_request(
        self, user_id: str, request_data: Dict[str, Any], hints: Optional[ContextCreationHints] = None
    ) -> IsolationContext:
        """从用户请求创建隔离上下文"""
        hints = hints or self._global_hints

        # 从请求数据中提取隔离信息
        tenant_id = request_data.get("tenant_id")
        agent_id = request_data.get("agent_id")
        platform = request_data.get("platform")
        chat_stream_id = request_data.get("chat_stream_id")

        # 如果没有提供租户ID，尝试从用户ID推断
        if not tenant_id and user_id:
            tenant_id = self._infer_tenant_from_user(user_id)

        # 应用提示
        tenant_id = hints.preferred_tenant_id or tenant_id or self._default_tenant_id
        agent_id = hints.preferred_agent_id or agent_id or self._default_agent_id
        platform = hints.preferred_platform or platform or self._default_platform
        chat_stream_id = hints.preferred_chat_stream_id or chat_stream_id

        return self._create_context_with_validation(tenant_id, agent_id, platform, chat_stream_id, hints)

    def create_from_config(
        self, config: Dict[str, Any], hints: Optional[ContextCreationHints] = None
    ) -> IsolationContext:
        """从配置创建隔离上下文"""
        hints = hints or self._global_hints

        tenant_id = config.get("tenant_id")
        agent_id = config.get("agent_id")
        platform = config.get("platform")
        chat_stream_id = config.get("chat_stream_id")

        # 应用提示
        tenant_id = hints.preferred_tenant_id or tenant_id or self._default_tenant_id
        agent_id = hints.preferred_agent_id or agent_id or self._default_agent_id
        platform = hints.preferred_platform or platform or self._default_platform
        chat_stream_id = hints.preferred_chat_stream_id or chat_stream_id

        return self._create_context_with_validation(tenant_id, agent_id, platform, chat_stream_id, hints)

    def create_from_scope(
        self, scope: IsolationScope, hints: Optional[ContextCreationHints] = None
    ) -> IsolationContext:
        """从隔离范围创建隔离上下文"""
        hints = hints or self._global_hints

        tenant_id = hints.preferred_tenant_id or scope.tenant_id
        agent_id = hints.preferred_agent_id or scope.agent_id
        platform = hints.preferred_platform or scope.platform
        chat_stream_id = hints.preferred_chat_stream_id or scope.chat_stream_id

        return self._create_context_with_validation(tenant_id, agent_id, platform, chat_stream_id, hints)

    def create_inherited_context(
        self,
        parent_context: IsolationContext,
        platform: str = None,
        chat_stream_id: str = None,
        hints: Optional[ContextCreationHints] = None,
    ) -> IsolationContext:
        """创建继承的隔离上下文"""
        hints = hints or self._global_hints

        if not hints.allow_context_inheritance:
            logger.warning("上下文继承被禁用，将创建新的上下文")
            return self.create_explicit(
                hints.preferred_tenant_id or self._default_tenant_id,
                hints.preferred_agent_id or self._default_agent_id,
                platform or hints.preferred_platform or self._default_platform,
                chat_stream_id or hints.preferred_chat_stream_id,
            )

        # 创建子上下文
        return parent_context.create_sub_context(
            platform=platform or parent_context.platform, chat_stream_id=chat_stream_id
        )

    def create_explicit(
        self,
        tenant_id: str,
        agent_id: str,
        platform: str = None,
        chat_stream_id: str = None,
        hints: Optional[ContextCreationHints] = None,
    ) -> IsolationContext:
        """显式创建隔离上下文"""
        hints = hints or self._global_hints

        tenant_id = hints.preferred_tenant_id or tenant_id
        agent_id = hints.preferred_agent_id or agent_id
        platform = hints.preferred_platform or platform
        chat_stream_id = hints.preferred_chat_stream_id or chat_stream_id

        return self._create_context_with_validation(tenant_id, agent_id, platform, chat_stream_id, hints)

    def create_default(self) -> IsolationContext:
        """创建默认隔离上下文"""
        return self.create_explicit(self._default_tenant_id, self._default_agent_id, self._default_platform)

    def _extract_from_message(self, message: Any) -> tuple[str, str, str, str]:
        """从消息中提取隔离信息"""
        try:
            # 尝试从maim_message格式提取
            if hasattr(message, "sender_info"):
                tenant_id = getattr(message.sender_info, "tenant_id", None)
                agent_id = getattr(message.sender_info, "agent_id", None)
                platform = getattr(message.sender_info, "platform", None)
                chat_stream_id = getattr(message, "chat_stream_id", None)
                return tenant_id, agent_id, platform, chat_stream_id

            # 尝试从字典格式提取
            if isinstance(message, dict):
                tenant_id = message.get("tenant_id")
                agent_id = message.get("agent_id")
                platform = message.get("platform")
                chat_stream_id = message.get("chat_stream_id")
                return tenant_id, agent_id, platform, chat_stream_id

            # 尝试从属性提取
            tenant_id = getattr(message, "tenant_id", None)
            agent_id = getattr(message, "agent_id", None)
            platform = getattr(message, "platform", None)
            chat_stream_id = getattr(message, "chat_stream_id", None)
            return tenant_id, agent_id, platform, chat_stream_id

        except Exception as e:
            logger.warning(f"从消息提取隔离信息失败: {e}")
            return None, None, None, None

    def _infer_tenant_from_user(self, user_id: str) -> Optional[str]:
        """从用户ID推断租户ID"""
        # 应用自定义推断规则
        for rule in self._context_creation_rules:
            try:
                result = rule("infer_tenant", user_id=user_id)
                if result:
                    return result
            except Exception as e:
                logger.warning(f"应用租户推断规则失败: {e}")

        # 默认推断策略：使用用户ID的前缀作为租户ID
        if ":" in user_id:
            return user_id.split(":")[0]

        return None

    def _create_context_with_validation(
        self, tenant_id: str, agent_id: str, platform: str, chat_stream_id: str, hints: ContextCreationHints
    ) -> IsolationContext:
        """创建并验证隔离上下文"""
        try:
            context = IsolationContext(tenant_id, agent_id, platform, chat_stream_id)

            # 验证隔离级别
            if hints.required_isolation_level:
                from .isolation_context import IsolationValidator

                if not IsolationValidator.validate_context(context, hints.required_isolation_level):
                    if hints.fallback_to_default:
                        logger.warning(f"隔离上下文不满足要求的级别 {hints.required_isolation_level}，使用默认上下文")
                        return self.create_default()
                    else:
                        raise ValueError(f"隔离上下文不满足要求的级别: {hints.required_isolation_level}")

            return context

        except Exception as e:
            if hints.fallback_to_default:
                logger.error(f"创建隔离上下文失败，使用默认上下文: {e}")
                return self.create_default()
            else:
                raise

    def validate_and_standardize_context(self, context: IsolationContext) -> IsolationContext:
        """验证和标准化隔离上下文"""
        # 标准化字段
        if not context.tenant_id:
            context.tenant_id = self._default_tenant_id
        if not context.agent_id:
            context.agent_id = self._default_agent_id
        if not context.platform:
            context.platform = self._default_platform

        # 验证必要字段
        if not context.tenant_id or not context.agent_id:
            raise ValueError("租户ID和智能体ID是必需的")

        return context


# 全局工厂实例
_global_factory = IsolationContextFactory()


def get_isolation_context_factory() -> IsolationContextFactory:
    """获取全局隔离上下文工厂"""
    return _global_factory


def set_isolation_context_factory_defaults(
    tenant_id: str = "default", agent_id: str = "default", platform: str = "default"
):
    """设置全局工厂默认值"""
    _global_factory.set_defaults(tenant_id, agent_id, platform)


# 便捷函数
def create_context_from_message(message: Any, hints: Optional[ContextCreationHints] = None) -> IsolationContext:
    """从消息创建隔离上下文的便捷函数"""
    return _global_factory.create_from_message(message, hints)


def create_context_from_request(
    user_id: str, request_data: Dict[str, Any], hints: Optional[ContextCreationHints] = None
) -> IsolationContext:
    """从用户请求创建隔离上下文的便捷函数"""
    return _global_factory.create_from_user_request(user_id, request_data, hints)


def create_context_from_config(
    config: Dict[str, Any], hints: Optional[ContextCreationHints] = None
) -> IsolationContext:
    """从配置创建隔离上下文的便捷函数"""
    return _global_factory.create_from_config(config, hints)


def create_default_context() -> IsolationContext:
    """创建默认隔离上下文的便捷函数"""
    return _global_factory.create_default()
