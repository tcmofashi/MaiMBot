"""
租户管理API接口 v2
作为内部服务，提供无需认证的租户管理功能
"""

import datetime
import secrets
import time
from typing import Optional, Dict, Any
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, validator

from src.common.database.database_model import TenantUsers
from src.common.logger import get_logger
from src.api.utils.response import APIResponse, get_request_id, calculate_execution_time

logger = get_logger(__name__)
router = APIRouter()


class TenantCreateRequest(BaseModel):
    """租户创建请求"""
    tenant_name: str
    tenant_type: str = "personal"
    description: Optional[str] = None
    contact_email: Optional[str] = None
    tenant_config: Optional[Dict[str, Any]] = None

    @validator("tenant_type")
    def validate_tenant_type(cls, v):
        if v not in ["personal", "enterprise"]:
            raise ValueError("租户类型必须是 personal 或 enterprise")
        return v

    @validator("tenant_name")
    def validate_tenant_name(cls, v):
        if len(v) < 1 or len(v) > 100:
            raise ValueError("租户名称长度必须在1-100个字符之间")
        return v

    @validator("contact_email")
    def validate_email(cls, v):
        if v is not None and "@" not in v:
            raise ValueError("邮箱格式无效")
        return v


@router.post("/tenants")
async def create_tenant(request_data: TenantCreateRequest, request: Request):
    """
    创建租户（无需认证）

    作为内部服务，提供租户创建功能，不需要任何认证。
    """
    start_time = time.time()
    request_id = get_request_id(request)

    try:
        # 生成新的租户ID
        new_tenant_id = f"tenant_{secrets.token_hex(8)}"
        # 生成临时的用户ID
        temp_user_id = f"temp_user_{secrets.token_hex(8)}"

        # 创建新租户记录
        new_tenant = TenantUsers.create(
            tenant_id=new_tenant_id,
            user_id=temp_user_id,
            username=f"temp_user_{new_tenant_id}",
            email=request_data.contact_email or f"temp_{new_tenant_id}@placeholder.com",
            phone=None,
            tenant_name=request_data.tenant_name,
            tenant_type=request_data.tenant_type,
            description=request_data.description,
            tenant_config=str(request_data.tenant_config) if request_data.tenant_config else None,
            api_key=None,
            status="active",
            created_at=datetime.datetime.utcnow(),
            updated_at=datetime.datetime.utcnow(),
            login_count=0
        )

        logger.info(f"租户创建成功: {request_data.tenant_name} (ID: {new_tenant_id})")

        return APIResponse.success(
            data={
                "tenant_id": new_tenant.tenant_id,
                "tenant_name": new_tenant.tenant_name,
                "tenant_type": new_tenant.tenant_type,
                "description": new_tenant.description,
                "tenant_config": eval(new_tenant.tenant_config) if new_tenant.tenant_config else None,
                "status": new_tenant.status,
                "created_at": new_tenant.created_at.isoformat()
            },
            message="租户创建成功",
            request_id=request_id,
            tenant_id=new_tenant_id,
            execution_time=calculate_execution_time(start_time)
        )

    except Exception as e:
        logger.error(f"租户创建失败: {e}")
        return APIResponse.error(
            message="租户创建失败，请稍后重试",
            error_code="INTERNAL_ERROR",
            error_details="服务器内部错误，请联系技术支持",
            request_id=request_id,
            execution_time=calculate_execution_time(start_time)
        )


@router.get("/tenants/{tenant_id}")
async def get_tenant(tenant_id: str, request: Request):
    """
    获取租户详情（无需认证）

    作为内部服务，提供租户查询功能，不需要任何认证。
    """
    start_time = time.time()
    request_id = get_request_id(request)

    try:
        # 查找租户
        tenant = TenantUsers.select().where(TenantUsers.tenant_id == tenant_id).first()

        if not tenant:
            return APIResponse.error(
                message="租户不存在",
                error_code="TENANT_NOT_FOUND",
                error_details=f"租户ID {tenant_id} 不存在",
                request_id=request_id,
                execution_time=calculate_execution_time(start_time)
            )

        return APIResponse.success(
            data={
                "tenant_id": tenant.tenant_id,
                "tenant_name": tenant.tenant_name,
                "tenant_type": tenant.tenant_type,
                "owner_id": tenant.user_id,
                "description": tenant.description,
                "tenant_config": eval(tenant.tenant_config) if tenant.tenant_config else None,
                "status": tenant.status,
                "created_at": tenant.created_at.isoformat(),
                "updated_at": tenant.updated_at.isoformat()
            },
            message="获取租户详情成功",
            request_id=request_id,
            tenant_id=tenant_id,
            execution_time=calculate_execution_time(start_time)
        )

    except Exception as e:
        logger.error(f"获取租户详情失败: {e}")
        return APIResponse.error(
            message="获取租户详情失败，请稍后重试",
            error_code="INTERNAL_ERROR",
            request_id=request_id,
            execution_time=calculate_execution_time(start_time)
        )