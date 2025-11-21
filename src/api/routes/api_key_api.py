"""
API密钥管理API路由
提供Agent API密钥的创建、查询、删除等功能
"""

import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status, Depends, Query
from pydantic import BaseModel, Field

from src.common.database.database_model import (
    AgentApiKeys,
    create_agent_api_key,
    validate_agent_api_key,
    TenantUsers
)
from src.common.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


# Pydantic模型定义
class ApiKeyCreateRequest(BaseModel):
    """创建API密钥请求"""
    tenant_id: str = Field(..., description="租户ID")
    agent_id: str = Field(..., description="智能体ID")
    user_identifier: str = Field(..., description="用户标识符", min_length=3, max_length=50)
    name: Optional[str] = Field(None, description="API密钥名称")
    description: Optional[str] = Field(None, description="描述")
    permissions: Optional[List[str]] = Field(default=["chat"], description="权限列表")
    expires_days: Optional[int] = Field(None, description="有效期天数", ge=1)


class ApiKeyResponse(BaseModel):
    """API密钥响应"""
    id: int
    tenant_id: str
    agent_id: str
    user_identifier: str
    api_key: str
    name: Optional[str]
    description: Optional[str]
    permissions: List[str]
    status: str
    expires_at: Optional[datetime.datetime]
    last_used_at: Optional[datetime.datetime]
    usage_count: int
    created_at: datetime.datetime
    created_by: str


class ApiKeyListResponse(BaseModel):
    """API密钥列表响应"""
    api_keys: List[ApiKeyResponse]
    total: int


class ApiKeyValidationRequest(BaseModel):
    """API密钥验证请求"""
    api_key: str = Field(..., description="要验证的API密钥")


class ApiKeyValidationResponse(BaseModel):
    """API密钥验证响应"""
    valid: bool
    tenant_id: Optional[str] = None
    agent_id: Optional[str] = None
    user_identifier: Optional[str] = None
    api_key_id: Optional[int] = None
    error: Optional[str] = None


# 依赖注入：简单的认证验证（后续可以扩展为JWT等）
async def verify_auth_token(authorization: str = None) -> str:
    """验证认证token"""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证信息"
        )

    # 简单的Bearer token验证
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证格式错误"
        )

    token = authorization[7:]  # 移除"Bearer "前缀

    # 这里可以添加JWT验证等逻辑
    # 暂时返回token作为用户标识
    return token


@router.post("/api-keys", response_model=ApiKeyResponse, summary="创建API密钥")
async def create_api_key(
    request: ApiKeyCreateRequest,
    user_id: str = Depends(verify_auth_token)
):
    """
    为指定的租户和智能体创建新的API密钥

    API密钥格式：{user_identifier}.{auth_token}
    - user_identifier: 用户标识符（不变）
    - auth_token: 认证token（随机生成）
    """
    try:
        # 验证租户是否存在
        tenant_user = TenantUsers.get_or_none(TenantUsers.tenant_id == request.tenant_id)
        if not tenant_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"租户 {request.tenant_id} 不存在"
            )

        # 检查用户标识符是否已被该租户使用
        existing_key = AgentApiKeys.get_or_none(
            (AgentApiKeys.tenant_id == request.tenant_id) &
            (AgentApiKeys.user_identifier == request.user_identifier) &
            (AgentApiKeys.agent_id == request.agent_id) &
            (AgentApiKeys.status == "active")
        )

        if existing_key:
            logger.warning(f"用户标识符 {request.user_identifier} 已被租户 {request.tenant_id} 的智能体 {request.agent_id} 使用")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"用户标识符 {request.user_identifier} 已被使用"
            )

        # 计算过期时间
        expires_at = None
        if request.expires_days:
            expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=request.expires_days)

        # 创建API密钥
        api_key_record = create_agent_api_key(
            tenant_id=request.tenant_id,
            agent_id=request.agent_id,
            user_identifier=request.user_identifier,
            name=request.name,
            description=request.description,
            permissions=request.permissions,
            created_by=user_id,
            expires_at=expires_at,
        )

        logger.info(f"创建API密钥成功: {api_key_record.api_key} (租户: {request.tenant_id}, 智能体: {request.agent_id})")

        return ApiKeyResponse(
            id=api_key_record.id,
            tenant_id=api_key_record.tenant_id,
            agent_id=api_key_record.agent_id,
            user_identifier=api_key_record.user_identifier,
            api_key=api_key_record.api_key,
            name=api_key_record.name,
            description=api_key_record.description,
            permissions=eval(api_key_record.permissions),  # 转换JSON字符串为列表
            status=api_key_record.status,
            expires_at=api_key_record.expires_at,
            last_used_at=api_key_record.last_used_at,
            usage_count=api_key_record.usage_count,
            created_at=api_key_record.created_at,
            created_by=api_key_record.created_by,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建API密钥失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建API密钥失败: {str(e)}"
        )


@router.get("/api-keys", response_model=ApiKeyListResponse, summary="获取API密钥列表")
async def list_api_keys(
    tenant_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    status: Optional[str] = "active",
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user_id: str = Depends(verify_auth_token)
):
    """
    获取API密钥列表

    支持按租户ID、智能体ID、状态等条件过滤
    """
    try:
        query = AgentApiKeys.select()

        # 应用过滤条件
        if tenant_id:
            query = query.where(AgentApiKeys.tenant_id == tenant_id)
        if agent_id:
            query = query.where(AgentApiKeys.agent_id == agent_id)
        if status:
            query = query.where(AgentApiKeys.status == status)

        # 获取总数
        total = query.count()

        # 分页查询
        api_keys = query.order_by(AgentApiKeys.created_at.desc()).limit(limit).offset(offset)

        api_key_responses = []
        for api_key in api_keys:
            api_key_responses.append(ApiKeyResponse(
                id=api_key.id,
                tenant_id=api_key.tenant_id,
                agent_id=api_key.agent_id,
                user_identifier=api_key.user_identifier,
                api_key=api_key.api_key,
                name=api_key.name,
                description=api_key.description,
                permissions=eval(api_key.permissions),
                status=api_key.status,
                expires_at=api_key.expires_at,
                last_used_at=api_key.last_used_at,
                usage_count=api_key.usage_count,
                created_at=api_key.created_at,
                created_by=api_key.created_by,
            ))

        return ApiKeyListResponse(api_keys=api_key_responses, total=total)

    except Exception as e:
        logger.error(f"获取API密钥列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取API密钥列表失败: {str(e)}"
        )


@router.delete("/api-keys/{api_key_id}", summary="删除API密钥")
async def delete_api_key(
    api_key_id: int,
    user_id: str = Depends(verify_auth_token)
):
    """
    删除指定的API密钥（实际上是标记为disabled状态）
    """
    try:
        api_key = AgentApiKeys.get_or_none(AgentApiKeys.id == api_key_id)
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API密钥不存在"
            )

        # 标记为disabled而不是真正删除
        api_key.status = "disabled"
        api_key.updated_at = datetime.datetime.utcnow()
        api_key.save()

        logger.info(f"禁用API密钥成功: {api_key.api_key} (操作者: {user_id})")

        return {"message": "API密钥已禁用"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"禁用API密钥失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"禁用API密钥失败: {str(e)}"
        )


@router.post("/api-keys/validate", response_model=ApiKeyValidationResponse, summary="验证API密钥")
async def validate_api_key(request: ApiKeyValidationRequest):
    """
    验证API密钥的有效性

    返回密钥对应的租户ID、智能体ID等信息
    """
    try:
        result = validate_agent_api_key(request.api_key)

        if result["valid"]:
            logger.info(f"API密钥验证成功: {request.api_key[:20]}... -> 租户: {result['tenant_id']}, 智能体: {result['agent_id']}")

        return ApiKeyValidationResponse(**result)

    except Exception as e:
        logger.error(f"验证API密钥失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"验证API密钥失败: {str(e)}"
        )