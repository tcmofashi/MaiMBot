"""
记忆服务的隔离工具

提供T+A+P+C四维隔离的验证和管理功能。
"""

import logging
from typing import Optional, Dict, Any, List
from fastapi import Request

logger = logging.getLogger(__name__)


class IsolationContext:
    """隔离上下文类"""

    def __init__(self, tenant_id: str, agent_id: str, platform: Optional[str] = None, scope_id: Optional[str] = None):
        """
        初始化隔离上下文

        Args:
            tenant_id: 租户ID
            agent_id: 智能体ID
            platform: 平台标识
            scope_id: 作用域ID（聊天流ID）
        """
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.platform = platform
        self.scope_id = scope_id

    def __str__(self) -> str:
        """字符串表示"""
        parts = [self.tenant_id, self.agent_id]
        if self.platform:
            parts.append(self.platform)
        if self.scope_id:
            parts.append(self.scope_id)
        return ":".join(parts)

    def __repr__(self) -> str:
        """调试表示"""
        return f"IsolationContext(tenant='{self.tenant_id}', agent='{self.agent_id}', platform='{self.platform}', scope='{self.scope_id}')"

    def __eq__(self, other) -> bool:
        """相等性比较"""
        if not isinstance(other, IsolationContext):
            return False
        return (
            self.tenant_id == other.tenant_id
            and self.agent_id == other.agent_id
            and self.platform == other.platform
            and self.scope_id == other.scope_id
        )

    def __hash__(self) -> int:
        """哈希值计算"""
        return hash((self.tenant_id, self.agent_id, self.platform, self.scope_id))

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "platform": self.platform,
            "scope_id": self.scope_id,
        }

    def copy(
        self,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        platform: Optional[str] = None,
        scope_id: Optional[str] = None,
    ) -> "IsolationContext":
        """
        创建隔离上下文的副本

        Args:
            tenant_id: 新的租户ID
            agent_id: 新的智能体ID
            platform: 新的平台标识
            scope_id: 新的作用域ID

        Returns:
            新的隔离上下文
        """
        return IsolationContext(
            tenant_id=tenant_id if tenant_id is not None else self.tenant_id,
            agent_id=agent_id if agent_id is not None else self.agent_id,
            platform=platform if platform is not None else self.platform,
            scope_id=scope_id if scope_id is not None else self.scope_id,
        )

    def create_sub_context(self, platform: Optional[str] = None, scope_id: Optional[str] = None) -> "IsolationContext":
        """
        创建子隔离上下文（继承当前上下文的基础信息）

        Args:
            platform: 平台标识
            scope_id: 作用域ID

        Returns:
            子隔离上下文
        """
        return IsolationContext(
            tenant_id=self.tenant_id,
            agent_id=self.agent_id,
            platform=platform or self.platform,
            scope_id=scope_id or self.scope_id,
        )

    def get_isolation_level(self) -> int:
        """
        获取隔离级别（1-4）

        Returns:
            隔离级别数字
        """
        level = 1  # 租户级别
        if self.agent_id:
            level = 2  # 智能体级别
        if self.platform:
            level = 3  # 平台级别
        if self.scope_id:
            level = 4  # 聊天流级别
        return level

    def is_same_tenant(self, other: "IsolationContext") -> bool:
        """检查是否属于同一租户"""
        return self.tenant_id == other.tenant_id

    def is_same_agent(self, other: "IsolationContext") -> bool:
        """检查是否属于同一智能体"""
        return self.tenant_id == other.tenant_id and self.agent_id == other.agent_id

    def is_same_platform(self, other: "IsolationContext") -> bool:
        """检查是否属于同一平台"""
        return self.tenant_id == other.tenant_id and self.agent_id == other.agent_id and self.platform == other.platform

    def is_same_scope(self, other: "IsolationContext") -> bool:
        """检查是否属于同一作用域"""
        return self == other

    def can_access(self, resource_context: "IsolationContext", resource_type: str = "memory") -> bool:
        """
        检查当前上下文是否可以访问指定资源

        Args:
            resource_context: 资源的隔离上下文
            resource_type: 资源类型（memory, conflict等）

        Returns:
            是否可以访问
        """
        # 必须是同一租户
        if not self.is_same_tenant(resource_context):
            return False

        # 根据资源类型和隔离级别检查访问权限
        if resource_type == "memory":
            return self._can_access_memory(resource_context)
        elif resource_type == "conflict":
            return self._can_access_conflict(resource_context)
        else:
            # 默认规则：只能访问同一租户的资源
            return True

    def _can_access_memory(self, resource_context: "IsolationContext") -> bool:
        """检查记忆访问权限"""
        # 同一智能体可以访问所有记忆
        if self.is_same_agent(resource_context):
            return True

        # 不同智能体只能访问公开级别的记忆
        if self.tenant_id == resource_context.tenant_id:
            return True

        return False

    def _can_access_conflict(self, resource_context: "IsolationContext") -> bool:
        """检查冲突访问权限"""
        # 冲突通常需要更严格的访问控制
        return self.is_same_agent(resource_context)


async def get_isolation_context_from_request(request: Request) -> IsolationContext:
    """
    从HTTP请求中提取隔离上下文

    Args:
        request: HTTP请求对象

    Returns:
        隔离上下文
    """
    try:
        # 优先使用request.state中的隔离上下文（由中间件设置）
        if hasattr(request.state, "isolation_context"):
            return request.state.isolation_context

        # 从请求头中获取隔离信息
        tenant_id = request.headers.get("X-Tenant-ID")
        agent_id = request.headers.get("X-Agent-ID")
        platform = request.headers.get("X-Platform")
        scope_id = request.headers.get("X-Scope-ID")

        if not tenant_id or not agent_id:
            raise ValueError("缺少必需的隔离上下文信息：X-Tenant-ID 和 X-Agent-ID")

        return IsolationContext(tenant_id=tenant_id, agent_id=agent_id, platform=platform, scope_id=scope_id)

    except Exception as e:
        logger.error(f"提取隔离上下文失败: {e}")
        raise ValueError(f"无效的隔离上下文: {str(e)}")


async def validate_isolation_context(
    tenant_id: str, agent_id: str, platform: Optional[str] = None, scope_id: Optional[str] = None
) -> IsolationContext:
    """
    验证并创建隔离上下文

    Args:
        tenant_id: 租户ID
        agent_id: 智能体ID
        platform: 平台标识
        scope_id: 作用域ID

    Returns:
        验证后的隔离上下文
    """
    try:
        # 验证必需字段
        if not tenant_id or not tenant_id.strip():
            raise ValueError("租户ID不能为空")
        if not agent_id or not agent_id.strip():
            raise ValueError("智能体ID不能为空")

        # 清理字段
        tenant_id = tenant_id.strip()
        agent_id = agent_id.strip()
        platform = platform.strip() if platform and platform.strip() else None
        scope_id = scope_id.strip() if scope_id and scope_id.strip() else None

        # 创建隔离上下文
        context = IsolationContext(tenant_id=tenant_id, agent_id=agent_id, platform=platform, scope_id=scope_id)

        return context

    except Exception as e:
        logger.error(f"验证隔离上下文失败: {e}")
        raise ValueError(f"无效的隔离上下文: {str(e)}")


def validate_isolation_string(isolation_string: str) -> Optional[IsolationContext]:
    """
    从隔离字符串解析隔离上下文

    Args:
        isolation_string: 隔离字符串格式："tenant:agent:platform:scope"

    Returns:
        隔离上下文或None
    """
    try:
        if not isolation_string:
            return None

        parts = isolation_string.split(":")
        if len(parts) < 2:
            return None

        tenant_id = parts[0].strip()
        agent_id = parts[1].strip()
        platform = parts[2].strip() if len(parts) > 2 else None
        scope_id = parts[3].strip() if len(parts) > 3 else None

        if not tenant_id or not agent_id:
            return None

        return IsolationContext(tenant_id=tenant_id, agent_id=agent_id, platform=platform, scope_id=scope_id)

    except Exception as e:
        logger.error(f"解析隔离字符串失败: {e}")
        return None


def generate_cache_key(
    base_key: str, isolation_context: IsolationContext, additional_params: Optional[Dict[str, Any]] = None
) -> str:
    """
    生成包含隔离信息的缓存键

    Args:
        base_key: 基础键
        isolation_context: 隔离上下文
        additional_params: 额外参数

    Returns:
        缓存键
    """
    key_parts = [base_key, str(isolation_context)]

    if additional_params:
        sorted_params = sorted(additional_params.items())
        for k, v in sorted_params:
            key_parts.append(f"{k}={v}")

    return ":".join(key_parts)


def merge_isolation_contexts(contexts: List[IsolationContext]) -> Optional[IsolationContext]:
    """
    合并多个隔离上下文（取最具体的层级）

    Args:
        contexts: 隔离上下文列表

    Returns:
        合并后的隔离上下文或None
    """
    if not contexts:
        return None

    # 获取最具体的上下文（隔离级别最高的）
    most_specific = max(contexts, key=lambda x: x.get_isolation_level())

    # 验证所有上下文都属于同一租户和智能体
    for context in contexts:
        if not most_specific.is_same_tenant(context):
            logger.warning("尝试合并不同租户的隔离上下文")
            return None

    return most_specific


def filter_by_isolation_context(
    items: List[Dict[str, Any]],
    isolation_context: IsolationContext,
    tenant_field: str = "tenant_id",
    agent_field: str = "agent_id",
    platform_field: str = "platform",
    scope_field: str = "scope_id",
) -> List[Dict[str, Any]]:
    """
    根据隔离上下文过滤项目列表

    Args:
        items: 项目列表
        isolation_context: 隔离上下文
        tenant_field: 租户字段名
        agent_field: 智能体字段名
        platform_field: 平台字段名
        scope_field: 作用域字段名

    Returns:
        过滤后的项目列表
    """
    filtered_items = []

    for item in items:
        # 检查租户匹配
        if item.get(tenant_field) != isolation_context.tenant_id:
            continue

        # 检查智能体匹配
        if item.get(agent_field) != isolation_context.agent_id:
            continue

        # 检查平台匹配（如果指定）
        if isolation_context.platform and item.get(platform_field) != isolation_context.platform:
            continue

        # 检查作用域匹配（如果指定）
        if isolation_context.scope_id and item.get(scope_field) != isolation_context.scope_id:
            continue

        filtered_items.append(item)

    return filtered_items


class IsolationValidator:
    """隔离验证器"""

    def __init__(self):
        self.allowed_tenants: Dict[str, Any] = {}
        self.allowed_agents: Dict[str, Dict[str, Any]] = {}
        self.allowed_platforms: List[str] = []

    def add_allowed_tenant(self, tenant_id: str, tenant_config: Optional[Dict[str, Any]] = None):
        """添加允许的租户"""
        self.allowed_tenants[tenant_id] = tenant_config or {}

    def add_allowed_agent(self, tenant_id: str, agent_id: str, agent_config: Optional[Dict[str, Any]] = None):
        """添加允许的智能体"""
        if tenant_id not in self.allowed_agents:
            self.allowed_agents[tenant_id] = {}
        self.allowed_agents[tenant_id][agent_id] = agent_config or {}

    def add_allowed_platform(self, platform: str):
        """添加允许的平台"""
        if platform not in self.allowed_platforms:
            self.allowed_platforms.append(platform)

    async def validate_tenant(self, tenant_id: str) -> bool:
        """验证租户是否被允许"""
        if not self.allowed_tenants:
            return True  # 如果没有限制，则允许所有租户

        return tenant_id in self.allowed_tenants

    async def validate_agent(self, tenant_id: str, agent_id: str) -> bool:
        """验证智能体是否被允许"""
        if not self.allowed_agents:
            return True  # 如果没有限制，则允许所有智能体

        return tenant_id in self.allowed_agents and agent_id in self.allowed_agents[tenant_id]

    async def validate_platform(self, platform: str) -> bool:
        """验证平台是否被允许"""
        if not self.allowed_platforms:
            return True  # 如果没有限制，则允许所有平台

        return platform in self.allowed_platforms

    async def validate_isolation_context(self, context: IsolationContext) -> Dict[str, bool]:
        """
        验证隔离上下文

        Args:
            context: 隔离上下文

        Returns:
            验证结果
        """
        return {
            "tenant": await self.validate_tenant(context.tenant_id),
            "agent": await self.validate_agent(context.tenant_id, context.agent_id),
            "platform": await self.validate_platform(context.platform) if context.platform else True,
        }


# 全局隔离验证器
isolation_validator = IsolationValidator()


async def validate_isolation_access(
    context: IsolationContext, resource_context: IsolationContext, resource_type: str = "memory"
) -> bool:
    """
    验证隔离访问权限

    Args:
        context: 当前隔离上下文
        resource_context: 资源隔离上下文
        resource_type: 资源类型

    Returns:
        是否有访问权限
    """
    try:
        # 验证租户权限
        if not await isolation_validator.validate_tenant(context.tenant_id):
            return False

        # 验证智能体权限
        if not await isolation_validator.validate_agent(context.tenant_id, context.agent_id):
            return False

        # 验证平台权限（如果指定）
        if context.platform and not await isolation_validator.validate_platform(context.platform):
            return False

        # 验证资源访问权限
        return context.can_access(resource_context, resource_type)

    except Exception as e:
        logger.error(f"验证隔离访问权限失败: {e}")
        return False
