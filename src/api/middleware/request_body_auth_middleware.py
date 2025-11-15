"""
请求体参数认证中间件
支持从请求体中提取租户和Agent信息进行认证和权限验证
"""

import json
from typing import Optional
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from ..middleware.tenant_auth_middleware import AuthCredentials
from ..routes.auth_api import verify_jwt_token
from src.common.database.database_model import TenantUsers
from src.common.logger import get_logger

logger = get_logger(__name__)
security = HTTPBearer(auto_error=False)


class RequestBodyAuthInfo(BaseModel):
    """请求体认证信息"""

    tenant_id: str
    agent_id: Optional[str] = None
    user_token: Optional[str] = None
    api_key: Optional[str] = None


async def extract_auth_from_request_body(request: Request) -> Optional[RequestBodyAuthInfo]:
    """
    从请求体中提取认证信息

    Args:
        request: FastAPI请求对象

    Returns:
        RequestBodyAuthInfo: 认证信息，如果无法提取则返回None
    """
    try:
        # 只对POST和PUT请求解析请求体
        if request.method not in ["POST", "PUT", "PATCH"]:
            return None

        # 获取请求体
        body = await request.body()
        if not body:
            return None

        # 解析JSON
        try:
            body_data = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

        # 提取认证信息
        auth_info = RequestBodyAuthInfo(
            tenant_id=body_data.get("tenant_id"),
            agent_id=body_data.get("agent_id"),
            user_token=body_data.get("user_token"),
            api_key=body_data.get("api_key"),
        )

        # 验证必需字段
        if not auth_info.tenant_id:
            return None

        return auth_info

    except Exception as e:
        logger.warning(f"提取请求体认证信息失败: {e}")
        return None


async def authenticate_request_with_body(
    request: Request, bearer_credentials: Optional[HTTPAuthorizationCredentials] = None, api_key: Optional[str] = None
) -> Optional[AuthCredentials]:
    """
    结合请求体和传统认证方式进行认证

    优先级：
    1. JWT Token认证
    2. API Key认证
    3. 请求体中的user_token
    4. 请求体中的api_key

    Args:
        request: FastAPI请求对象
        bearer_credentials: Bearer Token认证信息
        api_key: API Key认证信息

    Returns:
        AuthCredentials: 认证凭据，认证失败则返回None
    """
    try:
        # 1. 尝试JWT Token认证
        if bearer_credentials:
            try:
                payload = verify_jwt_token(bearer_credentials.credentials)
                return AuthCredentials(
                    tenant_id=payload.get("tenant_id"),
                    user_id=payload.get("user_id"),
                    permissions=payload.get("permissions", []),
                    expires_at=payload.get("exp"),
                    metadata={"auth_method": "jwt_token"},
                )
            except HTTPException:
                pass  # JWT认证失败，继续尝试其他方式

        # 2. 尝试API Key认证
        if api_key:
            try:
                # 这里应该实现API Key验证逻辑
                # 暂时跳过，因为需要数据库查询
                pass
            except Exception:
                pass  # API Key认证失败，继续尝试其他方式

        # 3. 尝试从请求体中提取认证信息
        body_auth = await extract_auth_from_request_body(request)
        if body_auth:
            # 尝试user_token认证
            if body_auth.user_token:
                try:
                    payload = verify_jwt_token(body_auth.user_token)
                    # 验证租户ID是否匹配
                    if payload.get("tenant_id") == body_auth.tenant_id:
                        return AuthCredentials(
                            tenant_id=body_auth.tenant_id,
                            user_id=payload.get("user_id"),
                            permissions=payload.get("permissions", []),
                            expires_at=payload.get("exp"),
                            metadata={"auth_method": "body_user_token"},
                        )
                except HTTPException:
                    pass  # user_token认证失败

            # 尝试api_key认证
            if body_auth.api_key:
                try:
                    # 查询用户
                    user = (
                        TenantUsers.select()
                        .where(
                            (TenantUsers.api_key == body_auth.api_key)
                            & (TenantUsers.tenant_id == body_auth.tenant_id)
                            & (TenantUsers.status == "active")
                        )
                        .first()
                    )

                    if user:
                        return AuthCredentials(
                            tenant_id=body_auth.tenant_id,
                            user_id=user.user_id,
                            permissions=json.loads(user.permissions) if user.permissions else [],
                            metadata={"auth_method": "body_api_key"},
                        )
                except Exception:
                    pass  # API Key认证失败

            # 如果没有有效的认证凭据，但提供了tenant_id，创建匿名凭据
            return AuthCredentials(
                tenant_id=body_auth.tenant_id,
                user_id=None,
                permissions=[],
                metadata={"auth_method": "anonymous", "agent_id": body_auth.agent_id},
            )

        return None

    except Exception as e:
        logger.error(f"请求体认证失败: {e}")
        return None


async def get_request_body_auth(
    request: Request,
    bearer_credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    api_key: Optional[str] = None,
) -> Optional[AuthCredentials]:
    """
    获取请求体认证信息的依赖注入函数

    Args:
        request: FastAPI请求对象
        bearer_credentials: Bearer Token认证信息
        api_key: API Key认证信息

    Returns:
        AuthCredentials: 认证凭据，可能为None
    """
    return await authenticate_request_with_body(request, bearer_credentials, api_key)


async def require_request_body_auth(
    request: Request,
    bearer_credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    api_key: Optional[str] = None,
) -> AuthCredentials:
    """
    必需的请求体认证依赖注入函数

    Args:
        request: FastAPI请求对象
        bearer_credentials: Bearer Token认证信息
        api_key: API Key认证信息

    Returns:
        AuthCredentials: 认证凭据

    Raises:
        HTTPException: 认证失败时抛出异常
    """
    credentials = await authenticate_request_with_body(request, bearer_credentials, api_key)

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供有效的认证信息",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return credentials


def check_tenant_permission(
    credentials: AuthCredentials, required_tenant_id: str, allow_anonymous: bool = False
) -> bool:
    """
    检查租户权限

    Args:
        credentials: 认证凭据
        required_tenant_id: 需要访问的租户ID
        allow_anonymous: 是否允许匿名访问

    Returns:
        bool: 是否有权限
    """
    # 匿名访问检查
    if credentials.user_id is None:
        return allow_anonymous and credentials.tenant_id == required_tenant_id

    # 检查租户ID是否匹配
    if credentials.tenant_id != required_tenant_id:
        return False

    # 检查用户状态
    try:
        user = (
            TenantUsers.select()
            .where((TenantUsers.user_id == credentials.user_id) & (TenantUsers.tenant_id == credentials.tenant_id))
            .first()
        )

        if not user or user.status != "active":
            return False

        return True

    except Exception as e:
        logger.error(f"检查用户状态失败: {e}")
        return False


def check_agent_permission(
    credentials: AuthCredentials, tenant_id: str, agent_id: str, allow_anonymous: bool = False
) -> bool:
    """
    检查Agent权限

    Args:
        credentials: 认证凭据
        tenant_id: 租户ID
        agent_id: Agent ID
        allow_anonymous: 是否允许匿名访问

    Returns:
        bool: 是否有权限
    """
    # 首先检查租户权限
    if not check_tenant_permission(credentials, tenant_id, allow_anonymous):
        return False

    # 匿名用户可以访问任何Agent（如果允许）
    if credentials.user_id is None and allow_anonymous:
        return True

    try:
        from src.common.database.database_model import AgentRecord

        # 检查Agent是否存在且属于该租户
        agent = (
            AgentRecord.select()
            .where((AgentRecord.tenant_id == tenant_id) & (AgentRecord.agent_id == agent_id))
            .first()
        )

        return agent is not None

    except Exception as e:
        logger.error(f"检查Agent权限失败: {e}")
        return False


async def get_tenant_from_request_body(request: Request) -> Optional[str]:
    """
    从请求体中提取租户ID

    Args:
        request: FastAPI请求对象

    Returns:
        str: 租户ID，如果无法提取则返回None
    """
    try:
        if request.method not in ["POST", "PUT", "PATCH"]:
            return None

        body = await request.body()
        if not body:
            return None

        body_data = json.loads(body.decode("utf-8"))
        return body_data.get("tenant_id")

    except Exception:
        return None


async def get_agent_from_request_body(request: Request) -> Optional[str]:
    """
    从请求体中提取Agent ID

    Args:
        request: FastAPI请求对象

    Returns:
        str: Agent ID，如果无法提取则返回None
    """
    try:
        if request.method not in ["POST", "PUT", "PATCH"]:
            return None

        body = await request.body()
        if not body:
            return None

        body_data = json.loads(body.decode("utf-8"))
        return body_data.get("agent_id")

    except Exception:
        return None
