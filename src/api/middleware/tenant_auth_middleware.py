"""
租户认证中间件

提供API级别的租户身份验证和权限控制，支持多种认证方式：
- JWT Token认证
- API Key认证
- 基础认证
- 租户级别和用户级别的权限控制

作者：MaiBot
版本：1.0.0
"""

import time
import hashlib
from typing import Optional, Dict, Any, List
from functools import wraps
from datetime import datetime, timedelta

from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.security import APIKeyHeader
import jwt
from pydantic import BaseModel

try:
    from src.isolation.isolation_context import IsolationContext, create_isolation_context
    from src.config.isolated_config_manager import get_isolated_config_manager
except ImportError:
    # 向后兼容性处理
    class IsolationContext:
        def __init__(self, tenant_id: str, agent_id: str, platform: str = "default", chat_stream_id: str = None):
            self.tenant_id = tenant_id
            self.agent_id = agent_id
            self.platform = platform
            self.chat_stream_id = chat_stream_id

    def create_isolation_context(tenant_id: str, agent_id: str, platform: str = "default", chat_stream_id: str = None):
        return IsolationContext(tenant_id, agent_id, platform, chat_stream_id)

    def get_isolated_config_manager(tenant_id: str, agent_id: str):
        return None


class AuthCredentials(BaseModel):
    """认证凭据模型"""

    tenant_id: str
    user_id: Optional[str] = None
    permissions: List[str] = []
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = {}


class TenantPermission(BaseModel):
    """租户权限模型"""

    tenant_id: str
    resource_type: str
    permissions: List[str]
    restrictions: Dict[str, Any] = {}


class TenantAuthConfig(BaseModel):
    """租户认证配置"""

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24
    api_keys: List[str] = []
    rate_limits: Dict[str, int] = {"requests_per_minute": 60, "requests_per_hour": 1000, "requests_per_day": 10000}
    allowed_origins: List[str] = ["*"]


class JWTAuthManager:
    """JWT认证管理器"""

    def __init__(self, config: TenantAuthConfig):
        self.config = config
        self._blacklist: set = set()

    def generate_token(self, credentials: AuthCredentials) -> str:
        """生成JWT Token"""
        payload = {
            "tenant_id": credentials.tenant_id,
            "user_id": credentials.user_id,
            "permissions": credentials.permissions,
            "metadata": credentials.metadata,
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(hours=self.config.jwt_expire_hours),
        }

        token = jwt.encode(payload, self.config.jwt_secret_key, algorithm=self.config.jwt_algorithm)

        return token

    def verify_token(self, token: str) -> AuthCredentials:
        """验证JWT Token"""
        if token in self._blacklist:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token已失效")

        try:
            payload = jwt.decode(token, self.config.jwt_secret_key, algorithms=[self.config.jwt_algorithm])

            credentials = AuthCredentials(
                tenant_id=payload["tenant_id"],
                user_id=payload.get("user_id"),
                permissions=payload.get("permissions", []),
                metadata=payload.get("metadata", {}),
                expires_at=datetime.fromtimestamp(payload["exp"]) if "exp" in payload else None,
            )

            return credentials

        except jwt.ExpiredSignatureError as err:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token已过期") from err
        except jwt.InvalidTokenError as err:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的Token") from err

    def revoke_token(self, token: str):
        """撤销Token"""
        self._blacklist.add(token)


class APIKeyAuthManager:
    """API Key认证管理器"""

    def __init__(self, config: TenantAuthConfig):
        self.config = config
        self._api_key_mapping: Dict[str, AuthCredentials] = {}
        self._init_api_keys()

    def _init_api_keys(self):
        """初始化API Key映射"""
        for i, api_key in enumerate(self.config.api_keys):
            # 使用API Key的哈希作为租户ID
            tenant_id = f"api_key_{hashlib.sha256(api_key.encode()).hexdigest()[:8]}"
            self._api_key_mapping[api_key] = AuthCredentials(
                tenant_id=tenant_id, permissions=["read", "write"], metadata={"auth_type": "api_key", "key_index": i}
            )

    def verify_api_key(self, api_key: str) -> AuthCredentials:
        """验证API Key"""
        if api_key not in self._api_key_mapping:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的API Key")

        return self._api_key_mapping[api_key]


class RateLimiter:
    """API限流器"""

    def __init__(self, config: TenantAuthConfig):
        self.config = config
        self._requests: Dict[str, List[float]] = {}

    def check_rate_limit(self, tenant_id: str) -> bool:
        """检查租户是否超限"""
        now = time.time()

        if tenant_id not in self._requests:
            self._requests[tenant_id] = []

        # 清理过期请求
        self._requests[tenant_id] = [
            req_time
            for req_time in self._requests[tenant_id]
            if now - req_time < 86400  # 24小时
        ]

        # 检查各级别限制
        minute_ago = now - 60
        hour_ago = now - 3600
        day_ago = now - 86400

        minute_count = sum(1 for req_time in self._requests[tenant_id] if req_time > minute_ago)
        hour_count = sum(1 for req_time in self._requests[tenant_id] if req_time > hour_ago)
        day_count = sum(1 for req_time in self._requests[tenant_id] if req_time > day_ago)

        if minute_count >= self.config.rate_limits.get("requests_per_minute", 60):
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="每分钟请求次数超限")

        if hour_count >= self.config.rate_limits.get("requests_per_hour", 1000):
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="每小时请求次数超限")

        if day_count >= self.config.rate_limits.get("requests_per_day", 10000):
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="每日请求次数超限")

        # 记录当前请求
        self._requests[tenant_id].append(now)
        return True


class TenantAuthMiddleware:
    """租户认证中间件"""

    def __init__(self, config: TenantAuthConfig):
        self.config = config
        self.jwt_manager = JWTAuthManager(config)
        self.api_key_manager = APIKeyAuthManager(config)
        self.rate_limiter = RateLimiter(config)

        # FastAPI安全方案
        self.bearer = HTTPBearer(auto_error=False)
        self.api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

    async def authenticate_request(
        self,
        request: Request,
        bearer_credentials: Optional[HTTPAuthorizationCredentials] = None,
        api_key: Optional[str] = None,
    ) -> AuthCredentials:
        """认证请求"""
        credentials = None

        # 尝试JWT认证
        if bearer_credentials:
            try:
                credentials = self.jwt_manager.verify_token(bearer_credentials.credentials)
            except HTTPException:
                pass

        # 尝试API Key认证
        if not credentials and api_key:
            try:
                credentials = self.api_key_manager.verify_api_key(api_key)
            except HTTPException:
                pass

        # 如果都失败，返回错误
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="认证失败，请提供有效的JWT Token或API Key"
            )

        # 检查限流
        self.rate_limiter.check_rate_limit(credentials.tenant_id)

        # 检查租户状态
        await self._validate_tenant_status(credentials.tenant_id)

        return credentials

    async def _validate_tenant_status(self, tenant_id: str):
        """验证租户状态"""
        try:
            config_manager = get_isolated_config_manager(tenant_id, "system")
            if config_manager:
                # 检查租户是否被禁用
                tenant_config = config_manager.get_config("tenant", "status", default="active")
                if tenant_config == "disabled":
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="租户已被禁用")
        except Exception:
            # 如果无法获取配置，默认允许访问
            pass

    def check_permission(self, credentials: AuthCredentials, required_permission: str) -> bool:
        """检查权限"""
        if "admin" in credentials.permissions:
            return True

        if required_permission in credentials.permissions:
            return True

        return False

    def create_isolation_context(
        self, credentials: AuthCredentials, agent_id: str, platform: str = "default"
    ) -> IsolationContext:
        """创建隔离上下文"""
        return create_isolation_context(tenant_id=credentials.tenant_id, agent_id=agent_id, platform=platform)


# 全局认证配置实例
DEFAULT_AUTH_CONFIG = TenantAuthConfig(
    jwt_secret_key="your-secret-key-here",  # 应该从环境变量获取
    jwt_algorithm="HS256",
    jwt_expire_hours=24,
    api_keys=[],
    rate_limits={"requests_per_minute": 60, "requests_per_hour": 1000, "requests_per_day": 10000},
)

# 全局认证中间件实例
_global_auth_middleware: Optional[TenantAuthMiddleware] = None


def get_auth_middleware() -> TenantAuthMiddleware:
    """获取全局认证中间件实例"""
    global _global_auth_middleware
    if _global_auth_middleware is None:
        _global_auth_middleware = TenantAuthMiddleware(DEFAULT_AUTH_CONFIG)
    return _global_auth_middleware


def configure_auth(config: TenantAuthConfig):
    """配置认证系统"""
    global _global_auth_middleware
    _global_auth_middleware = TenantAuthMiddleware(config)


# 依赖注入函数
async def get_current_tenant_credentials(
    request: Request,
    bearer_credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    api_key: Optional[str] = Depends(APIKeyHeader(name="X-API-Key", auto_error=False)),
) -> AuthCredentials:
    """获取当前租户认证信息"""
    auth_middleware = get_auth_middleware()
    return await auth_middleware.authenticate_request(request, bearer_credentials, api_key)


def require_permission(permission: str):
    """权限要求装饰器工厂"""

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 从kwargs中获取credentials
            credentials = kwargs.get("credentials")
            if not credentials:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少认证信息")

            auth_middleware = get_auth_middleware()
            if not auth_middleware.check_permission(credentials, permission):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"需要权限: {permission}")

            return await func(*args, **kwargs)

        return wrapper

    return decorator


# 便捷依赖函数
async def get_current_tenant_id(credentials: AuthCredentials = Depends(get_current_tenant_credentials)) -> str:
    """获取当前租户ID"""
    return credentials.tenant_id


async def get_isolation_context_from_auth(
    agent_id: str, platform: str = "default", credentials: AuthCredentials = Depends(get_current_tenant_credentials)
) -> IsolationContext:
    """从认证信息创建隔离上下文"""
    auth_middleware = get_auth_middleware()
    return auth_middleware.create_isolation_context(credentials, agent_id, platform)


# 权限常量
class Permission:
    """权限常量"""

    READ = "read"
    WRITE = "write"
    ADMIN = "admin"
    CHAT = "chat"
    CONFIG = "config"
    MEMORY = "memory"
    PLUGIN = "plugin"
    MONITOR = "monitor"


# 错误处理
class TenantAuthError(Exception):
    """租户认证错误"""

    def __init__(self, message: str, status_code: int = 401):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


# 工具函数
def generate_api_key() -> str:
    """生成API Key"""
    import secrets

    return secrets.token_urlsafe(32)


def hash_api_key(api_key: str) -> str:
    """哈希API Key"""
    return hashlib.sha256(api_key.encode()).hexdigest()


# CORS支持
async def check_cors_origin(request: Request) -> bool:
    """检查CORS来源"""
    auth_middleware = get_auth_middleware()
    origin = request.headers.get("origin")

    if not origin:
        return True

    allowed_origins = auth_middleware.config.allowed_origins
    if "*" in allowed_origins or origin in allowed_origins:
        return True

    return False
