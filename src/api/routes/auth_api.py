"""
用户认证和注册API接口
支持多租户单用户模式的用户注册、登录、登出等功能
"""

import datetime
import secrets
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, validator
import jwt
from peewee import DoesNotExist, IntegrityError

from src.common.database.database_model import (
    TenantUsers,
    UserSessions,
    verify_password,
    create_user_session,
    create_tenant_user,
)
from src.common.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/v1/auth", tags=["认证"])
security = HTTPBearer(auto_error=False)

# JWT配置
JWT_SECRET_KEY = "your-secret-key-here"  # 在生产环境中应该从环境变量获取
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_HOURS = 24
JWT_REFRESH_TOKEN_EXPIRE_DAYS = 30


class UserRegisterRequest(BaseModel):
    """用户注册请求"""

    username: str
    password: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    tenant_name: Optional[str] = None
    tenant_type: str = "personal"

    @validator("username")
    def validate_username(cls, v):
        if len(v) < 3 or len(v) > 50:
            raise ValueError("用户名长度必须在3-50个字符之间")
        return v

    @validator("password")
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError("密码长度不能少于6个字符")
        return v

    @validator("tenant_type")
    def validate_tenant_type(cls, v):
        if v not in ["personal", "enterprise"]:
            raise ValueError("租户类型必须是 personal 或 enterprise")
        return v


class UserLoginRequest(BaseModel):
    """用户登录请求"""

    username: str
    password: str


class UserLoginResponse(BaseModel):
    """用户登录响应"""

    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int
    user_info: Dict[str, Any]


class UserInfo(BaseModel):
    """用户信息"""

    user_id: str
    tenant_id: str
    username: str
    email: Optional[str] = None
    phone: Optional[str] = None
    tenant_name: str
    tenant_type: str
    api_key: str
    status: str
    created_at: datetime.datetime
    last_login_at: Optional[datetime.datetime] = None


def generate_tokens(user_id: str, tenant_id: str) -> tuple:
    """
    生成JWT访问令牌和刷新令牌

    Args:
        user_id: 用户ID
        tenant_id: 租户ID

    Returns:
        tuple: (access_token, refresh_token, expires_at)
    """
    now = datetime.datetime.utcnow()

    # 访问令牌
    access_token_payload = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "type": "access",
        "exp": now + datetime.timedelta(hours=JWT_ACCESS_TOKEN_EXPIRE_HOURS),
        "iat": now,
    }
    access_token = jwt.encode(access_token_payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    # 刷新令牌
    refresh_token_payload = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "type": "refresh",
        "exp": now + datetime.timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        "iat": now,
    }
    refresh_token = jwt.encode(refresh_token_payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    expires_at = now + datetime.timedelta(hours=JWT_ACCESS_TOKEN_EXPIRE_HOURS)

    return access_token, refresh_token, expires_at


def verify_jwt_token(token: str) -> Dict[str, Any]:
    """
    验证JWT令牌

    Args:
        token: JWT令牌

    Returns:
        Dict: 令牌payload

    Raises:
        HTTPException: 令牌无效时抛出异常
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌已过期",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    except jwt.JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌无效",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


def get_current_user_from_token(token: str) -> TenantUsers:
    """
    从令牌获取当前用户

    Args:
        token: JWT令牌

    Returns:
        TenantUsers: 用户记录

    Raises:
        HTTPException: 用户不存在时抛出异常
    """
    payload = verify_jwt_token(token)
    user_id = payload.get("user_id")
    tenant_id = payload.get("tenant_id")

    if not user_id or not tenant_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="令牌格式无效")

    try:
        user = TenantUsers.get((TenantUsers.user_id == user_id) & (TenantUsers.tenant_id == tenant_id))
        if user.status != "active":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户账户已被禁用")
        return user
    except DoesNotExist:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在") from None


def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> TenantUsers:
    """
    获取当前用户依赖注入

    Args:
        credentials: HTTP认证凭据

    Returns:
        TenantUsers: 当前用户
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return get_current_user_from_token(credentials.credentials)


@router.post("/register", response_model=UserLoginResponse, status_code=status.HTTP_201_CREATED)
async def register_user(request_data: UserRegisterRequest, request: Request):
    """
    用户注册（自动创建租户）
    """
    try:
        # 检查用户名是否已存在
        query = TenantUsers.username == request_data.username
        if request_data.email:
            query = query | (TenantUsers.email == request_data.email)

        existing_user = TenantUsers.select().where(query).first()

        if existing_user:
            if existing_user.username == request_data.username:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")
            elif request_data.email and existing_user.email == request_data.email:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="邮箱已被使用")

        # 生成租户ID和用户ID
        tenant_id = f"tenant_{secrets.token_hex(8)}"
        user_id = f"user_{secrets.token_hex(8)}"

        # 创建租户用户
        user = create_tenant_user(
            tenant_id=tenant_id,
            user_id=user_id,
            username=request_data.username,
            password=request_data.password,
            tenant_name=request_data.tenant_name,
            email=request_data.email,
            phone=request_data.phone,
            tenant_type=request_data.tenant_type,
        )

        # 生成令牌
        access_token, refresh_token, expires_at = generate_tokens(user_id, tenant_id)

        # 创建会话记录
        ip_address = request.client.host
        user_agent = request.headers.get("user-agent")
        create_user_session(
            user_id=user_id,
            tenant_id=tenant_id,
            jwt_token=access_token,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # 更新登录信息
        user.last_login_at = datetime.datetime.utcnow()
        user.login_count = 1
        user.save()

        logger.info(f"新用户注册成功: {request_data.username} (tenant: {tenant_id})")

        return UserLoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=int(JWT_ACCESS_TOKEN_EXPIRE_HOURS * 3600),
            user_info={
                "user_id": user.user_id,
                "tenant_id": user.tenant_id,
                "username": user.username,
                "email": user.email,
                "phone": user.phone,
                "tenant_name": user.tenant_name,
                "tenant_type": user.tenant_type,
                "api_key": user.api_key,
                "status": user.status,
                "created_at": user.created_at.isoformat(),
                "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
            },
        )

    except IntegrityError as e:
        logger.error(f"用户注册失败(数据完整性错误): {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名或邮箱已被使用") from None
    except HTTPException:
        # 重新抛出HTTPException，不要捕获
        raise
    except Exception as e:
        logger.error(f"用户注册失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="注册失败，请稍后重试") from None


@router.post("/login", response_model=UserLoginResponse)
async def login_user(request_data: UserLoginRequest, request: Request):
    """
    用户登录
    """
    try:
        # 查找用户
        user = TenantUsers.select().where(TenantUsers.username == request_data.username).first()

        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

        # 验证密码
        if not verify_password(request_data.password, user.salt, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

        # 检查用户状态
        if user.status != "active":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户账户已被禁用")

        # 生成令牌
        access_token, refresh_token, expires_at = generate_tokens(user.user_id, user.tenant_id)

        # 创建会话记录
        ip_address = request.client.host
        user_agent = request.headers.get("user-agent")
        create_user_session(
            user_id=user.user_id,
            tenant_id=user.tenant_id,
            jwt_token=access_token,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # 更新登录信息
        user.last_login_at = datetime.datetime.utcnow()
        user.login_count += 1
        user.save()

        logger.info(f"用户登录成功: {request_data.username} (tenant: {user.tenant_id})")

        return UserLoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=int(JWT_ACCESS_TOKEN_EXPIRE_HOURS * 3600),
            user_info={
                "user_id": user.user_id,
                "tenant_id": user.tenant_id,
                "username": user.username,
                "email": user.email,
                "phone": user.phone,
                "tenant_name": user.tenant_name,
                "tenant_type": user.tenant_type,
                "api_key": user.api_key,
                "status": user.status,
                "created_at": user.created_at.isoformat(),
                "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"用户登录失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="登录失败，请稍后重试") from None


@router.post("/logout")
async def logout_user(current_user: TenantUsers = Depends(get_current_user)):
    """
    用户登出
    """
    try:
        # 将用户的所有活跃会话标记为非活跃
        UserSessions.update(is_active=False).where(
            (UserSessions.user_id == current_user.user_id)
            & (UserSessions.tenant_id == current_user.tenant_id)
            & UserSessions.is_active
        ).execute()

        logger.info(f"用户登出成功: {current_user.username} (tenant: {current_user.tenant_id})")

        return {"message": "登出成功"}

    except HTTPException:
        # 重新抛出HTTPException，不要捕获
        raise
    except Exception as e:
        logger.error(f"用户登出失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="登出失败，请稍后重试") from None


@router.get("/me", response_model=UserInfo)
async def get_current_user_info(current_user: TenantUsers = Depends(get_current_user)):
    """
    获取当前用户信息
    """
    return UserInfo(
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        username=current_user.username,
        email=current_user.email,
        phone=current_user.phone,
        tenant_name=current_user.tenant_name,
        tenant_type=current_user.tenant_type,
        api_key=current_user.api_key,
        status=current_user.status,
        created_at=current_user.created_at,
        last_login_at=current_user.last_login_at,
    )


@router.post("/refresh")
async def refresh_token(request: Request):
    """
    刷新访问令牌
    """
    try:
        # 从请求体获取刷新令牌
        request_data = await request.json()
        refresh_token = request_data.get("refresh_token")

        if not refresh_token:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少刷新令牌")

        # 验证刷新令牌
        payload = verify_jwt_token(refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="令牌类型无效")

        user_id = payload.get("user_id")
        tenant_id = payload.get("tenant_id")

        # 验证用户存在且活跃
        user = TenantUsers.get((TenantUsers.user_id == user_id) & (TenantUsers.tenant_id == tenant_id))

        if user.status != "active":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户账户已被禁用")

        # 生成新的访问令牌
        access_token, _, expires_at = generate_tokens(user_id, tenant_id)

        # 创建新的会话记录
        ip_address = request.client.host
        user_agent = request.headers.get("user-agent")
        create_user_session(
            user_id=user_id,
            tenant_id=tenant_id,
            jwt_token=access_token,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": int(JWT_ACCESS_TOKEN_EXPIRE_HOURS * 3600),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"刷新令牌失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="刷新令牌失败，请稍后重试"
        ) from None
