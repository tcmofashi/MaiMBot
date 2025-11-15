"""
API权限管理模块

提供API级别的权限验证、资源访问控制和细粒度权限配置功能。
"""

from .api_permission_manager import (
    ResourceType,
    Permission,
    AccessLevel,
    ResourcePermission,
    UserPermission,
    RolePermission,
    PermissionCheck,
    APIPermissionManager,
    get_permission_manager,
    require_permission,
    check_user_permission,
    grant_user_permission_simple,
)

__all__ = [
    "ResourceType",
    "Permission",
    "AccessLevel",
    "ResourcePermission",
    "UserPermission",
    "RolePermission",
    "PermissionCheck",
    "APIPermissionManager",
    "get_permission_manager",
    "require_permission",
    "check_user_permission",
    "grant_user_permission_simple",
]
