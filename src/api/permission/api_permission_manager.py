"""
API权限管理

实现API级别的权限验证，支持资源访问控制和细粒度的权限配置。
提供租户级别的权限管理和资源保护。

作者：MaiBot
版本：1.0.0
"""

from typing import Optional, Dict, Any, List, Set, Tuple
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field

from fastapi import HTTPException, status

try:
    from src.config.isolated_config_manager import get_isolated_config_manager
except ImportError:

    def get_isolated_config_manager(*args, **kwargs):
        return None


class ResourceType(Enum):
    """资源类型枚举"""

    CHAT = "chat"
    AGENT = "agent"
    MEMORY = "memory"
    CONFIG = "config"
    PLUGIN = "plugin"
    MONITOR = "monitor"
    SYSTEM = "system"
    USER = "user"
    TENANT = "tenant"


class Permission(Enum):
    """权限枚举"""

    READ = "read"
    WRITE = "write"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    ADMIN = "admin"
    EXECUTE = "execute"
    SHARE = "share"


class AccessLevel(Enum):
    """访问级别枚举"""

    NONE = 0
    READ_ONLY = 1
    READ_WRITE = 2
    ADMIN = 3
    OWNER = 4


@dataclass
class ResourcePermission:
    """资源权限配置"""

    resource_type: ResourceType
    resource_id: str
    tenant_id: str
    permissions: Set[Permission] = field(default_factory=set)
    access_level: AccessLevel = AccessLevel.NONE
    restrictions: Dict[str, Any] = field(default_factory=dict)
    expires_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class UserPermission:
    """用户权限配置"""

    user_id: str
    tenant_id: str
    permissions: Dict[ResourceType, Set[Permission]] = field(default_factory=dict)
    global_permissions: Set[Permission] = field(default_factory=set)
    roles: List[str] = field(default_factory=list)
    restrictions: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RolePermission:
    """角色权限配置"""

    role_name: str
    tenant_id: str
    permissions: Dict[ResourceType, Set[Permission]] = field(default_factory=dict)
    global_permissions: Set[Permission] = field(default_factory=set)
    description: str = ""
    is_system_role: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class PermissionCheck:
    """权限检查结果"""

    allowed: bool
    resource_type: ResourceType
    permission: Permission
    resource_id: str
    tenant_id: str
    reason: str = ""
    access_level: AccessLevel = AccessLevel.NONE
    restrictions: Dict[str, Any] = field(default_factory=dict)


class APIPermissionManager:
    """API权限管理器"""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self._user_permissions: Dict[str, UserPermission] = {}
        self._resource_permissions: Dict[str, ResourcePermission] = {}
        self._role_permissions: Dict[str, RolePermission] = {}
        self._permission_cache: Dict[str, Tuple[bool, datetime]] = {}
        self._cache_ttl = 300  # 5分钟缓存

        # 初始化系统角色
        self._init_system_roles()

    def _init_system_roles(self):
        """初始化系统角色"""
        # 管理员角色
        admin_role = RolePermission(
            role_name="admin",
            tenant_id=self.tenant_id,
            global_permissions={perm for perm in Permission},
            is_system_role=True,
            description="系统管理员，拥有所有权限",
        )
        self._role_permissions["admin"] = admin_role

        # 用户角色
        user_role = RolePermission(
            role_name="user",
            tenant_id=self.tenant_id,
            permissions={
                ResourceType.CHAT: {Permission.READ, Permission.WRITE, Permission.EXECUTE},
                ResourceType.AGENT: {Permission.READ},
                ResourceType.MEMORY: {Permission.READ, Permission.WRITE},
            },
            global_permissions={Permission.READ},
            is_system_role=True,
            description="普通用户，基础使用权限",
        )
        self._role_permissions["user"] = user_role

        # 只读角色
        readonly_role = RolePermission(
            role_name="readonly",
            tenant_id=self.tenant_id,
            permissions={
                ResourceType.CHAT: {Permission.READ},
                ResourceType.AGENT: {Permission.READ},
                ResourceType.MEMORY: {Permission.READ},
            },
            global_permissions={Permission.READ},
            is_system_role=True,
            description="只读用户，只能查看信息",
        )
        self._role_permissions["readonly"] = readonly_role

    def check_permission(
        self,
        user_id: str,
        resource_type: ResourceType,
        permission: Permission,
        resource_id: str = None,
        context: Dict[str, Any] = None,
    ) -> PermissionCheck:
        """
        检查用户权限

        Args:
            user_id: 用户ID
            resource_type: 资源类型
            permission: 所需权限
            resource_id: 资源ID（可选）
            context: 上下文信息（可选）

        Returns:
            PermissionCheck: 权限检查结果
        """
        context = context or {}

        # 检查缓存
        cache_key = f"{user_id}:{resource_type.value}:{permission.value}:{resource_id or 'global'}"
        if cache_key in self._permission_cache:
            allowed, cached_time = self._permission_cache[cache_key]
            if datetime.utcnow() - cached_time < timedelta(seconds=self._cache_ttl):
                return PermissionCheck(
                    allowed=allowed,
                    resource_type=resource_type,
                    permission=permission,
                    resource_id=resource_id or "global",
                    tenant_id=self.tenant_id,
                    reason="缓存命中",
                    access_level=self._get_access_level(user_id, resource_type, resource_id),
                )

        # 执行权限检查
        result = self._check_permission_internal(user_id, resource_type, permission, resource_id, context)

        # 缓存结果
        self._permission_cache[cache_key] = (result.allowed, datetime.utcnow())

        return result

    def _check_permission_internal(
        self,
        user_id: str,
        resource_type: ResourceType,
        permission: Permission,
        resource_id: str = None,
        context: Dict[str, Any] = None,
    ) -> PermissionCheck:
        """内部权限检查逻辑"""
        # 1. 检查全局权限
        user_perm = self._get_user_permission(user_id)
        if Permission.ADMIN in user_perm.global_permissions:
            return PermissionCheck(
                allowed=True,
                resource_type=resource_type,
                permission=permission,
                resource_id=resource_id or "global",
                tenant_id=self.tenant_id,
                reason="拥有管理员权限",
                access_level=AccessLevel.ADMIN,
            )

        # 2. 检查资源特定权限
        if resource_id:
            resource_perm = self._get_resource_permission(resource_id, resource_type)
            if permission in resource_perm.permissions:
                return PermissionCheck(
                    allowed=True,
                    resource_type=resource_type,
                    permission=permission,
                    resource_id=resource_id,
                    tenant_id=self.tenant_id,
                    reason="拥有资源权限",
                    access_level=resource_perm.access_level,
                )

        # 3. 检查类型权限
        if resource_type in user_perm.permissions:
            if permission in user_perm.permissions[resource_type]:
                return PermissionCheck(
                    allowed=True,
                    resource_type=resource_type,
                    permission=permission,
                    resource_id=resource_id or "global",
                    tenant_id=self.tenant_id,
                    reason="拥有类型权限",
                    access_level=self._get_access_level(user_id, resource_type, resource_id),
                )

        # 4. 检查角色权限
        for role_name in user_perm.roles:
            if role_name in self._role_permissions:
                role_perm = self._role_permissions[role_name]

                # 检查全局角色权限
                if permission in role_perm.global_permissions:
                    return PermissionCheck(
                        allowed=True,
                        resource_type=resource_type,
                        permission=permission,
                        resource_id=resource_id or "global",
                        tenant_id=self.tenant_id,
                        reason=f"角色'{role_name}'拥有全局权限",
                        access_level=AccessLevel.READ_WRITE,
                    )

                # 检查角色类型权限
                if resource_type in role_perm.permissions:
                    if permission in role_perm.permissions[resource_type]:
                        return PermissionCheck(
                            allowed=True,
                            resource_type=resource_type,
                            permission=permission,
                            resource_id=resource_id or "global",
                            tenant_id=self.tenant_id,
                            reason=f"角色'{role_name}'拥有类型权限",
                            access_level=AccessLevel.READ_WRITE,
                        )

        # 5. 权限不足
        return PermissionCheck(
            allowed=False,
            resource_type=resource_type,
            permission=permission,
            resource_id=resource_id or "global",
            tenant_id=self.tenant_id,
            reason="权限不足",
            access_level=AccessLevel.NONE,
        )

    def _get_user_permission(self, user_id: str) -> UserPermission:
        """获取用户权限配置"""
        if user_id not in self._user_permissions:
            # 创建默认用户权限
            default_perm = UserPermission(
                user_id=user_id,
                tenant_id=self.tenant_id,
                roles=["user"],  # 默认给予用户角色
            )
            self._user_permissions[user_id] = default_perm

        return self._user_permissions[user_id]

    def _get_resource_permission(self, resource_id: str, resource_type: ResourceType) -> ResourcePermission:
        """获取资源权限配置"""
        key = f"{resource_type.value}:{resource_id}"
        if key not in self._resource_permissions:
            # 创建默认资源权限
            default_perm = ResourcePermission(
                resource_type=resource_type,
                resource_id=resource_id,
                tenant_id=self.tenant_id,
                access_level=AccessLevel.NONE,
            )
            self._resource_permissions[key] = default_perm

        return self._resource_permissions[key]

    def _get_access_level(self, user_id: str, resource_type: ResourceType, resource_id: str = None) -> AccessLevel:
        """获取用户的访问级别"""
        user_perm = self._get_user_permission(user_id)

        # 检查是否有管理员权限
        if Permission.ADMIN in user_perm.global_permissions:
            return AccessLevel.ADMIN

        # 检查资源权限
        if resource_id:
            resource_perm = self._get_resource_permission(resource_id, resource_type)
            if resource_perm.access_level > AccessLevel.NONE:
                return resource_perm.access_level

        # 检查是否有写权限
        if resource_type in user_perm.permissions:
            perms = user_perm.permissions[resource_type]
            if Permission.WRITE in perms or Permission.UPDATE in perms:
                return AccessLevel.READ_WRITE
            elif Permission.READ in perms:
                return AccessLevel.READ_ONLY

        return AccessLevel.NONE

    def grant_user_permission(
        self, user_id: str, resource_type: ResourceType, permission: Permission, resource_id: str = None
    ) -> bool:
        """
        授予用户权限

        Args:
            user_id: 用户ID
            resource_type: 资源类型
            permission: 权限
            resource_id: 资源ID（可选，为空则为类型权限）

        Returns:
            bool: 是否成功
        """
        try:
            user_perm = self._get_user_permission(user_id)

            if resource_id:
                # 资源权限
                resource_perm = self._get_resource_permission(resource_id, resource_type)
                resource_perm.permissions.add(permission)
                if permission in [Permission.ADMIN, Permission.DELETE]:
                    resource_perm.access_level = AccessLevel.ADMIN
                elif permission in [Permission.WRITE, Permission.UPDATE, Permission.CREATE]:
                    resource_perm.access_level = max(resource_perm.access_level, AccessLevel.READ_WRITE)
                elif permission == Permission.READ:
                    resource_perm.access_level = max(resource_perm.access_level, AccessLevel.READ_ONLY)
            else:
                # 类型权限
                if resource_type not in user_perm.permissions:
                    user_perm.permissions[resource_type] = set()
                user_perm.permissions[resource_type].add(permission)

            # 更新时间
            user_perm.updated_at = datetime.utcnow()

            # 清除相关缓存
            self._clear_permission_cache(user_id, resource_type, resource_id)

            return True

        except Exception:
            return False

    def revoke_user_permission(
        self, user_id: str, resource_type: ResourceType, permission: Permission, resource_id: str = None
    ) -> bool:
        """
        撤销用户权限

        Args:
            user_id: 用户ID
            resource_type: 资源类型
            permission: 权限
            resource_id: 资源ID（可选）

        Returns:
            bool: 是否成功
        """
        try:
            user_perm = self._get_user_permission(user_id)

            if resource_id:
                # 资源权限
                resource_perm = self._get_resource_permission(resource_id, resource_type)
                resource_perm.permissions.discard(permission)
            else:
                # 类型权限
                if resource_type in user_perm.permissions:
                    user_perm.permissions[resource_type].discard(permission)

            # 更新时间
            user_perm.updated_at = datetime.utcnow()

            # 清除相关缓存
            self._clear_permission_cache(user_id, resource_type, resource_id)

            return True

        except Exception:
            return False

    def assign_role(self, user_id: str, role_name: str) -> bool:
        """
        分配角色给用户

        Args:
            user_id: 用户ID
            role_name: 角色名称

        Returns:
            bool: 是否成功
        """
        try:
            if role_name not in self._role_permissions:
                return False

            user_perm = self._get_user_permission(user_id)
            if role_name not in user_perm.roles:
                user_perm.roles.append(role_name)
                user_perm.updated_at = datetime.utcnow()

            # 清除用户权限缓存
            self._clear_user_cache(user_id)

            return True

        except Exception:
            return False

    def remove_role(self, user_id: str, role_name: str) -> bool:
        """
        移除用户角色

        Args:
            user_id: 用户ID
            role_name: 角色名称

        Returns:
            bool: 是否成功
        """
        try:
            user_perm = self._get_user_permission(user_id)
            if role_name in user_perm.roles:
                user_perm.roles.remove(role_name)
                user_perm.updated_at = datetime.utcnow()

            # 清除用户权限缓存
            self._clear_user_cache(user_id)

            return True

        except Exception:
            return False

    def create_role(
        self,
        role_name: str,
        permissions: Dict[ResourceType, List[Permission]] = None,
        global_permissions: List[Permission] = None,
        description: str = "",
    ) -> bool:
        """
        创建自定义角色

        Args:
            role_name: 角色名称
            permissions: 类型权限
            global_permissions: 全局权限
            description: 角色描述

        Returns:
            bool: 是否成功
        """
        try:
            if role_name in self._role_permissions:
                return False  # 角色已存在

            role_perm = RolePermission(
                role_name=role_name,
                tenant_id=self.tenant_id,
                permissions={rt: set(perms) for rt, perms in (permissions or {}).items()},
                global_permissions=set(global_permissions or []),
                description=description,
                is_system_role=False,
            )

            self._role_permissions[role_name] = role_perm
            return True

        except Exception:
            return False

    def get_user_permissions(self, user_id: str) -> Dict[str, Any]:
        """获取用户权限信息"""
        user_perm = self._get_user_permission(user_id)

        # 计算有效权限
        effective_permissions = {
            "global": list(user_perm.global_permissions),
            "by_type": {rt.value: list(perms) for rt, perms in user_perm.permissions.items()},
        }

        # 添加角色权限
        role_permissions = {}
        for role_name in user_perm.roles:
            if role_name in self._role_permissions:
                role_perm = self._role_permissions[role_name]
                role_permissions[role_name] = {
                    "global": list(role_perm.global_permissions),
                    "by_type": {rt.value: list(perms) for rt, perms in role_perm.permissions.items()},
                    "description": role_perm.description,
                }

        return {
            "user_id": user_id,
            "tenant_id": self.tenant_id,
            "roles": user_perm.roles,
            "effective_permissions": effective_permissions,
            "role_permissions": role_permissions,
            "created_at": user_perm.created_at.isoformat(),
            "updated_at": user_perm.updated_at.isoformat(),
        }

    def get_resource_permissions(self, resource_type: ResourceType, resource_id: str) -> List[Dict[str, Any]]:
        """获取资源的权限信息"""
        key = f"{resource_type.value}:{resource_id}"
        if key not in self._resource_permissions:
            return []

        resource_perm = self._resource_permissions[key]

        # 查找拥有该资源权限的用户
        users_with_permission = []
        for user_id, _user_perm in self._user_permissions.items():
            check_result = self.check_permission(user_id, resource_type, Permission.READ, resource_id)
            if check_result.allowed:
                users_with_permission.append(
                    {"user_id": user_id, "access_level": check_result.access_level.value, "reason": check_result.reason}
                )

        return [
            {
                "resource_type": resource_type.value,
                "resource_id": resource_id,
                "tenant_id": self.tenant_id,
                "permissions": list(resource_perm.permissions),
                "access_level": resource_perm.access_level.value,
                "restrictions": resource_perm.restrictions,
                "expires_at": resource_perm.expires_at.isoformat() if resource_perm.expires_at else None,
                "created_at": resource_perm.created_at.isoformat(),
                "users_with_access": users_with_permission,
            }
        ]

    def _clear_permission_cache(self, user_id: str, resource_type: ResourceType, resource_id: str = None):
        """清除特定权限缓存"""
        keys_to_remove = []
        for key in self._permission_cache:
            if key.startswith(f"{user_id}:{resource_type.value}"):
                if resource_id is None or key.endswith(f":{resource_id}"):
                    keys_to_remove.append(key)

        for key in keys_to_remove:
            del self._permission_cache[key]

    def _clear_user_cache(self, user_id: str):
        """清除用户所有权限缓存"""
        keys_to_remove = [key for key in self._permission_cache if key.startswith(f"{user_id}:")]
        for key in keys_to_remove:
            del self._permission_cache[key]

    def cleanup_expired_permissions(self):
        """清理过期的权限"""
        now = datetime.utcnow()

        # 清理过期的资源权限
        expired_resources = []
        for key, resource_perm in self._resource_permissions.items():
            if resource_perm.expires_at and resource_perm.expires_at < now:
                expired_resources.append(key)

        for key in expired_resources:
            del self._resource_permissions[key]

        # 清理过期的权限缓存
        expired_cache = []
        for key, (_, cached_time) in self._permission_cache.items():
            if now - cached_time > timedelta(seconds=self._cache_ttl):
                expired_cache.append(key)

        for key in expired_cache:
            del self._permission_cache[key]

    def get_permission_stats(self) -> Dict[str, Any]:
        """获取权限统计信息"""
        return {
            "tenant_id": self.tenant_id,
            "users_count": len(self._user_permissions),
            "resources_count": len(self._resource_permissions),
            "roles_count": len(self._role_permissions),
            "cache_size": len(self._permission_cache),
            "system_roles": [name for name, role in self._role_permissions.items() if role.is_system_role],
            "custom_roles": [name for name, role in self._role_permissions.items() if not role.is_system_role],
        }


# 全局权限管理器缓存
_global_permission_managers: Dict[str, APIPermissionManager] = {}


def get_permission_manager(tenant_id: str) -> APIPermissionManager:
    """获取租户的权限管理器"""
    if tenant_id not in _global_permission_managers:
        _global_permission_managers[tenant_id] = APIPermissionManager(tenant_id)
    return _global_permission_managers[tenant_id]


def require_permission(resource_type: ResourceType, permission: Permission, resource_id_param: str = None):
    """
    权限要求装饰器工厂

    Args:
        resource_type: 资源类型
        permission: 所需权限
        resource_id_param: 资源ID参数名（可选）
    """

    def decorator(func):
        async def wrapper(*args, **kwargs):
            # 从kwargs中获取参数
            tenant_id = kwargs.get("tenant_id")
            user_id = kwargs.get("user_id") or kwargs.get("current_user_id")

            if not tenant_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少租户ID")

            if not user_id:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少用户ID")

            # 获取资源ID
            resource_id = None
            if resource_id_param:
                resource_id = kwargs.get(resource_id_param)

            # 获取权限管理器并检查权限
            permission_manager = get_permission_manager(tenant_id)
            check_result = permission_manager.check_permission(user_id, resource_type, permission, resource_id)

            if not check_result.allowed:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"权限不足: {check_result.reason}")

            # 将权限检查结果添加到kwargs
            kwargs["permission_check"] = check_result

            return await func(*args, **kwargs)

        return wrapper

    return decorator


# 便捷权限检查函数
def check_user_permission(
    tenant_id: str, user_id: str, resource_type: ResourceType, permission: Permission, resource_id: str = None
) -> bool:
    """
    检查用户权限的便捷函数

    Args:
        tenant_id: 租户ID
        user_id: 用户ID
        resource_type: 资源类型
        permission: 权限
        resource_id: 资源ID（可选）

    Returns:
        bool: 是否有权限
    """
    try:
        permission_manager = get_permission_manager(tenant_id)
        result = permission_manager.check_permission(user_id, resource_type, permission, resource_id)
        return result.allowed
    except Exception:
        return False


def grant_user_permission_simple(
    tenant_id: str, user_id: str, resource_type: ResourceType, permission: Permission, resource_id: str = None
) -> bool:
    """
    授予用户权限的便捷函数

    Args:
        tenant_id: 租户ID
        user_id: 用户ID
        resource_type: 资源类型
        permission: 权限
        resource_id: 资源ID（可选）

    Returns:
        bool: 是否成功
    """
    try:
        permission_manager = get_permission_manager(tenant_id)
        return permission_manager.grant_user_permission(user_id, resource_type, permission, resource_id)
    except Exception:
        return False
