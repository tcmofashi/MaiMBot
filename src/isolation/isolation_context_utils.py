"""
隔离上下文工具类
提供隔离上下文的操作工具、序列化、比较和验证功能
"""

import json
import pickle
import hashlib
from typing import Dict, Any, List, Optional, Union
from dataclasses import asdict
import logging

from .isolation_context import IsolationContext, IsolationScope, IsolationLevel, IsolationValidator

logger = logging.getLogger(__name__)


class IsolationContextSerializer:
    """隔离上下文序列化器"""

    @staticmethod
    def to_dict(context: IsolationContext) -> Dict[str, Any]:
        """将隔离上下文转换为字典"""
        return {
            "tenant_id": context.tenant_id,
            "agent_id": context.agent_id,
            "platform": context.platform,
            "chat_stream_id": context.chat_stream_id,
            "scope": asdict(context.scope),
            "isolation_level": context.get_isolation_level().value,
            "memory_scope": context.get_memory_scope(),
            "config_scope": context.get_config_scope(),
            "event_scope": context.get_event_scope(),
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> IsolationContext:
        """从字典创建隔离上下文"""
        context = IsolationContext(
            tenant_id=data["tenant_id"],
            agent_id=data["agent_id"],
            platform=data.get("platform"),
            chat_stream_id=data.get("chat_stream_id"),
        )
        return context

    @staticmethod
    def to_json(context: IsolationContext, indent: Optional[int] = None) -> str:
        """将隔离上下文转换为JSON字符串"""
        data = IsolationContextSerializer.to_dict(context)
        return json.dumps(data, indent=indent, ensure_ascii=False)

    @staticmethod
    def from_json(json_str: str) -> IsolationContext:
        """从JSON字符串创建隔离上下文"""
        data = json.loads(json_str)
        return IsolationContextSerializer.from_dict(data)

    @staticmethod
    def to_pickle(context: IsolationContext) -> bytes:
        """将隔离上下文序列化为pickle字节"""
        return pickle.dumps(context)

    @staticmethod
    def from_pickle(data: bytes) -> IsolationContext:
        """从pickle字节创建隔离上下文"""
        return pickle.loads(data)


class IsolationContextComparator:
    """隔离上下文比较器"""

    @staticmethod
    def are_equal(context1: IsolationContext, context2: IsolationContext) -> bool:
        """比较两个隔离上下文是否相等"""
        return (
            context1.tenant_id == context2.tenant_id
            and context1.agent_id == context2.agent_id
            and context1.platform == context2.platform
            and context1.chat_stream_id == context2.chat_stream_id
        )

    @staticmethod
    def are_compatible(context1: IsolationContext, context2: IsolationContext) -> bool:
        """检查两个隔离上下文是否兼容（可以访问相同资源）"""
        # 租户必须相同
        if context1.tenant_id != context2.tenant_id:
            return False

        # 智能体必须相同
        if context1.agent_id != context2.agent_id:
            return False

        return True

    @staticmethod
    def can_access(
        source_context: IsolationContext, target_context: IsolationContext, required_level: IsolationLevel = None
    ) -> bool:
        """检查源上下文是否可以访问目标上下文"""
        # 验证基本兼容性
        if not IsolationContextComparator.are_compatible(source_context, target_context):
            return False

        # 验证隔离级别
        if required_level:
            if not IsolationValidator.validate_context(source_context, required_level):
                return False

        # 检查平台权限
        if target_context.platform and source_context.platform:
            if source_context.platform != target_context.platform:
                # 在某些情况下，跨平台访问可能是允许的
                # 这里可以根据业务规则进行定制
                pass

        return True

    @staticmethod
    def get_access_level(context: IsolationContext) -> Dict[str, Any]:
        """获取上下文的访问级别信息"""
        return {
            "isolation_level": context.get_isolation_level().value,
            "tenant_scope": context.tenant_id,
            "agent_scope": context.agent_id,
            "platform_scope": context.platform,
            "chat_scope": context.chat_stream_id,
            "can_cross_tenant": False,
            "can_cross_agent": False,
            "can_cross_platform": context.platform is None,
            "can_cross_chat": context.chat_stream_id is None,
        }


class IsolationContextHasher:
    """隔离上下文哈希器"""

    @staticmethod
    def get_hash(context: IsolationContext, algorithm: str = "md5") -> str:
        """获取隔离上下文的哈希值"""
        # 创建标准化的字符串表示
        context_str = f"{context.tenant_id}:{context.agent_id}:{context.platform or ''}:{context.chat_stream_id or ''}"

        hash_obj = hashlib.new(algorithm)
        hash_obj.update(context_str.encode("utf-8"))
        return hash_obj.hexdigest()

    @staticmethod
    def get_scope_hash(scope: IsolationScope, algorithm: str = "md5") -> str:
        """获取隔离范围的哈希值"""
        scope_str = str(scope)

        hash_obj = hashlib.new(algorithm)
        hash_obj.update(scope_str.encode("utf-8"))
        return hash_obj.hexdigest()

    @staticmethod
    def get_consistent_id(context: IsolationContext, prefix: str = "") -> str:
        """获取一致的上下文ID"""
        hash_value = IsolationContextHasher.get_hash(context)
        if prefix:
            return f"{prefix}_{hash_value}"
        return hash_value


class IsolationContextMerger:
    """隔离上下文合并器"""

    @staticmethod
    def merge_scopes(scopes: List[IsolationScope]) -> IsolationScope:
        """合并多个隔离范围，返回最通用的范围"""
        if not scopes:
            raise ValueError("至少需要一个隔离范围")

        if len(scopes) == 1:
            return scopes[0]

        # 找到最通用的范围（最不具体的）
        base_scope = scopes[0]

        for scope in scopes[1:]:
            base_scope = IsolationContextMerger._find_common_scope(base_scope, scope)

        return base_scope

    @staticmethod
    def merge_contexts(contexts: List[IsolationContext]) -> IsolationContext:
        """合并多个隔离上下文，返回最通用的上下文"""
        if not contexts:
            raise ValueError("至少需要一个隔离上下文")

        if len(contexts) == 1:
            return contexts[0]

        scopes = [context.scope for context in contexts]
        merged_scope = IsolationContextMerger.merge_scopes(scopes)

        return IsolationContext(
            tenant_id=merged_scope.tenant_id,
            agent_id=merged_scope.agent_id,
            platform=merged_scope.platform,
            chat_stream_id=merged_scope.chat_stream_id,
        )

    @staticmethod
    def _find_common_scope(scope1: IsolationScope, scope2: IsolationScope) -> IsolationScope:
        """找到两个范围的共同范围"""
        # 租户必须相同
        if scope1.tenant_id != scope2.tenant_id:
            raise ValueError(f"租户不匹配: {scope1.tenant_id} vs {scope2.tenant_id}")

        # 智能体必须相同
        if scope1.agent_id != scope2.agent_id:
            raise ValueError(f"智能体不匹配: {scope1.agent_id} vs {scope2.agent_id}")

        # 找到最通用的平台
        platform = scope1.platform if scope1.platform == scope2.platform else None

        # 找到最通用的聊天流
        chat_stream_id = scope1.chat_stream_id if scope1.chat_stream_id == scope2.chat_stream_id else None

        return IsolationScope(
            tenant_id=scope1.tenant_id, agent_id=scope1.agent_id, platform=platform, chat_stream_id=chat_stream_id
        )


class IsolationContextAnalyzer:
    """隔离上下文分析器"""

    @staticmethod
    def analyze_isolation_depth(context: IsolationContext) -> Dict[str, Any]:
        """分析隔离深度"""
        depth = 0
        dimensions = []

        if context.tenant_id:
            depth += 1
            dimensions.append("tenant")

        if context.agent_id:
            depth += 1
            dimensions.append("agent")

        if context.platform:
            depth += 1
            dimensions.append("platform")

        if context.chat_stream_id:
            depth += 1
            dimensions.append("chat")

        return {
            "depth": depth,
            "max_depth": 4,
            "dimensions": dimensions,
            "isolation_level": context.get_isolation_level().value,
            "is_strictly_isolated": depth == 4,
        }

    @staticmethod
    def get_resource_scope_prefix(context: IsolationContext) -> str:
        """获取资源范围前缀"""
        return f"{context.tenant_id}:{context.agent_id}"

    @staticmethod
    def get_full_resource_path(context: IsolationContext, resource_name: str) -> str:
        """获取完整的资源路径"""
        base_path = IsolationContextAnalyzer.get_resource_scope_prefix(context)

        path_components = [base_path]
        if context.platform:
            path_components.append(context.platform)
        if context.chat_stream_id:
            path_components.append(context.chat_stream_id)

        path_components.append(resource_name)
        return "/".join(path_components)

    @staticmethod
    def extract_isolation_dimensions(context: IsolationContext) -> Dict[str, str]:
        """提取隔离维度"""
        return {
            "tenant": context.tenant_id,
            "agent": context.agent_id,
            "platform": context.platform or "any",
            "chat": context.chat_stream_id or "any",
        }

    @staticmethod
    def validate_completeness(context: IsolationContext) -> List[str]:
        """验证上下文完整性，返回缺失的维度列表"""
        missing = []

        if not context.tenant_id:
            missing.append("tenant_id")
        if not context.agent_id:
            missing.append("agent_id")

        return missing


class IsolationContextBuilder:
    """隔离上下文构建器"""

    def __init__(self):
        self._tenant_id = None
        self._agent_id = None
        self._platform = None
        self._chat_stream_id = None

    def tenant(self, tenant_id: str) -> "IsolationContextBuilder":
        """设置租户ID"""
        self._tenant_id = tenant_id
        return self

    def agent(self, agent_id: str) -> "IsolationContextBuilder":
        """设置智能体ID"""
        self._agent_id = agent_id
        return self

    def platform(self, platform: str) -> "IsolationContextBuilder":
        """设置平台"""
        self._platform = platform
        return self

    def chat(self, chat_stream_id: str) -> "IsolationContextBuilder":
        """设置聊天流ID"""
        self._chat_stream_id = chat_stream_id
        return self

    def from_dict(self, data: Dict[str, Any]) -> "IsolationContextBuilder":
        """从字典设置属性"""
        self._tenant_id = data.get("tenant_id")
        self._agent_id = data.get("agent_id")
        self._platform = data.get("platform")
        self._chat_stream_id = data.get("chat_stream_id")
        return self

    def from_context(self, context: IsolationContext) -> "IsolationContextBuilder":
        """从现有上下文复制属性"""
        self._tenant_id = context.tenant_id
        self._agent_id = context.agent_id
        self._platform = context.platform
        self._chat_stream_id = context.chat_stream_id
        return self

    def build(self) -> IsolationContext:
        """构建隔离上下文"""
        if not self._tenant_id or not self._agent_id:
            raise ValueError("租户ID和智能体ID是必需的")

        return IsolationContext(
            tenant_id=self._tenant_id,
            agent_id=self._agent_id,
            platform=self._platform,
            chat_stream_id=self._chat_stream_id,
        )


# 便捷函数
def serialize_context(context: IsolationContext, format: str = "json") -> Union[str, bytes, Dict[str, Any]]:
    """序列化隔离上下文的便捷函数"""
    if format == "json":
        return IsolationContextSerializer.to_json(context)
    elif format == "dict":
        return IsolationContextSerializer.to_dict(context)
    elif format == "pickle":
        return IsolationContextSerializer.to_pickle(context)
    else:
        raise ValueError(f"不支持的序列化格式: {format}")


def deserialize_context(data: Union[str, bytes, Dict[str, Any]], format: str = "json") -> IsolationContext:
    """反序列化隔离上下文的便捷函数"""
    if format == "json":
        return IsolationContextSerializer.from_json(data)
    elif format == "dict":
        return IsolationContextSerializer.from_dict(data)
    elif format == "pickle":
        return IsolationContextSerializer.from_pickle(data)
    else:
        raise ValueError(f"不支持的序列化格式: {format}")


def compare_contexts(context1: IsolationContext, context2: IsolationContext) -> Dict[str, Any]:
    """比较两个上下文的便捷函数"""
    return {
        "equal": IsolationContextComparator.are_equal(context1, context2),
        "compatible": IsolationContextComparator.are_compatible(context1, context2),
        "context1_access_level": IsolationContextComparator.get_access_level(context1),
        "context2_access_level": IsolationContextComparator.get_access_level(context2),
    }


def context_builder() -> IsolationContextBuilder:
    """创建上下文构建器的便捷函数"""
    return IsolationContextBuilder()


def analyze_context(context: IsolationContext) -> Dict[str, Any]:
    """分析隔离上下文的便捷函数"""
    return {
        "isolation_depth": IsolationContextAnalyzer.analyze_isolation_depth(context),
        "resource_prefix": IsolationContextAnalyzer.get_resource_scope_prefix(context),
        "dimensions": IsolationContextAnalyzer.extract_isolation_dimensions(context),
        "missing_dimensions": IsolationContextAnalyzer.validate_completeness(context),
        "hash": IsolationContextHasher.get_hash(context),
    }
