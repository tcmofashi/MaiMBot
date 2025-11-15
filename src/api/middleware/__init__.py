"""
API中间件模块

提供认证、权限控制、限流等中间件功能。
"""

from .tenant_auth_middleware import (
    TenantAuthMiddleware,
    TenantAuthConfig,
    AuthCredentials,
    TenantPermission,
    JWTAuthManager,
    APIKeyAuthManager,
    RateLimiter,
    get_auth_middleware,
    configure_auth,
    get_current_tenant_credentials,
    get_current_tenant_id,
    get_isolation_context_from_auth,
    require_permission,
    Permission,
    generate_api_key,
    hash_api_key,
    check_cors_origin,
)

__all__ = [
    "TenantAuthMiddleware",
    "TenantAuthConfig",
    "AuthCredentials",
    "TenantPermission",
    "JWTAuthManager",
    "APIKeyAuthManager",
    "RateLimiter",
    "get_auth_middleware",
    "configure_auth",
    "get_current_tenant_credentials",
    "get_current_tenant_id",
    "get_isolation_context_from_auth",
    "require_permission",
    "Permission",
    "generate_api_key",
    "hash_api_key",
    "check_cors_origin",
]
