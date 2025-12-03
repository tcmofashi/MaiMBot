"""
API密钥管理API接口 v2
作为内部服务，提供无需认证的API密钥管理功能
"""

import datetime
import secrets
import time
import base64
from typing import Optional, List
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, validator

from src.common.database.database_model import AgentApiKeys
from src.common.logger import get_logger
from src.api.utils.response import APIResponse, get_request_id, calculate_execution_time

logger = get_logger(__name__)
router = APIRouter()


def generate_api_key(tenant_id: str, agent_id: str) -> str:
    """
    生成API密钥
    格式: mmc_{tenant_id}_{agent_id}_{random_hash}_{version}
    """
    # Base64编码租户ID和Agent ID
    tenant_b64 = base64.b64encode(tenant_id.encode()).decode().rstrip("=")
    agent_b64 = base64.b64encode(agent_id.encode()).decode().rstrip("=")
    random_hash = secrets.token_hex(16)
    version_b64 = base64.b64encode("v1".encode()).decode().rstrip("=")

    return f"mmc_{tenant_b64}_{agent_b64}_{random_hash}_{version_b64}"


class ApiKeyCreateRequest(BaseModel):
    """API密钥创建请求"""
    tenant_id: str
    agent_id: str
    name: str
    description: Optional[str] = None
    permissions: Optional[List[str]] = None
    expires_at: Optional[str] = None

    @validator("name")
    def validate_name(cls, v):
        if len(v) < 1 or len(v) > 100:
            raise ValueError("API密钥名称长度必须在1-100个字符之间")
        return v


class ApiKeyUpdateRequest(BaseModel):
    """API密钥更新请求"""
    name: Optional[str] = None
    description: Optional[str] = None
    permissions: Optional[List[str]] = None
    expires_at: Optional[str] = None

    @validator("name")
    def validate_name(cls, v):
        if v is not None and (len(v) < 1 or len(v) > 100):
            raise ValueError("API密钥名称长度必须在1-100个字符之间")
        return v


@router.post("/api-keys")
async def create_api_key(request_data: ApiKeyCreateRequest, request: Request):
    """
    创建API密钥（无需认证）

    作为内部服务，提供API密钥创建功能，不需要任何认证。
    """
    start_time = time.time()
    request_id = get_request_id(request)

    try:
        # 生成新的API密钥
        api_key = generate_api_key(request_data.tenant_id, request_data.agent_id)
        new_api_key_id = f"key_{secrets.token_hex(8)}"

        # 创建新API密钥记录
        new_api_key = AgentApiKeys.create(
            api_key_id=new_api_key_id,
            tenant_id=request_data.tenant_id,
            agent_id=request_data.agent_id,
            api_key=api_key,
            name=request_data.name,
            description=request_data.description,
            permissions=request_data.permissions or [],
            status="active",
            expires_at=datetime.datetime.fromisoformat(request_data.expires_at) if request_data.expires_at else None,
            created_at=datetime.datetime.utcnow(),
            updated_at=datetime.datetime.utcnow()
        )

        logger.info(f"API密钥创建成功: {request_data.name} (ID: {new_api_key_id})")

        return APIResponse.success(
            data={
                "api_key_id": new_api_key.api_key_id,
                "tenant_id": new_api_key.tenant_id,
                "agent_id": new_api_key.agent_id,
                "name": new_api_key.name,
                "description": new_api_key.description,
                "api_key": new_api_key.api_key,
                "permissions": new_api_key.permissions,
                "status": new_api_key.status,
                "expires_at": new_api_key.expires_at.isoformat() if new_api_key.expires_at else None,
                "created_at": new_api_key.created_at.isoformat()
            },
            message="API密钥创建成功",
            request_id=request_id,
            tenant_id=request_data.tenant_id,
            execution_time=calculate_execution_time(start_time)
        )

    except Exception as e:
        logger.error(f"API密钥创建失败: {e}")
        return APIResponse.error(
            message="API密钥创建失败，请稍后重试",
            error_code="INTERNAL_ERROR",
            error_details="服务器内部错误，请联系技术支持",
            request_id=request_id,
            execution_time=calculate_execution_time(start_time)
        )


@router.get("/api-keys/{api_key_id}")
async def get_api_key(api_key_id: str, request: Request):
    """
    获取API密钥详情（无需认证）

    作为内部服务，提供API密钥查询功能，不需要任何认证。
    """
    start_time = time.time()
    request_id = get_request_id(request)

    try:
        # 查找API密钥
        api_key = AgentApiKeys.select().where(AgentApiKeys.api_key_id == api_key_id).first()

        if not api_key:
            return APIResponse.error(
                message="API密钥不存在",
                error_code="API_KEY_NOT_FOUND",
                error_details=f"API密钥ID {api_key_id} 不存在",
                request_id=request_id,
                execution_time=calculate_execution_time(start_time)
            )

        return APIResponse.success(
            data={
                "api_key_id": api_key.api_key_id,
                "tenant_id": api_key.tenant_id,
                "agent_id": api_key.agent_id,
                "name": api_key.name,
                "description": api_key.description,
                "api_key": api_key.api_key,
                "permissions": api_key.permissions,
                "status": api_key.status,
                "expires_at": api_key.expires_at.isoformat() if api_key.expires_at else None,
                "created_at": api_key.created_at.isoformat(),
                "updated_at": api_key.updated_at.isoformat()
            },
            message="获取API密钥详情成功",
            request_id=request_id,
            execution_time=calculate_execution_time(start_time)
        )

    except Exception as e:
        logger.error(f"获取API密钥详情失败: {e}")
        return APIResponse.error(
            message="获取API密钥详情失败，请稍后重试",
            error_code="INTERNAL_ERROR",
            request_id=request_id,
            execution_time=calculate_execution_time(start_time)
        )


@router.get("/api-keys")
async def list_api_keys(
    request: Request,
    tenant_id: str = Query(..., description="租户ID（必需）"),
    agent_id: Optional[str] = Query(default=None, description="Agent ID过滤"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    status: Optional[str] = Query(default=None, description="状态过滤"),
):
    """
    获取指定租户的API密钥列表（无需认证）

    API密钥必须属于特定租户，因此tenant_id是必需参数。
    作为内部服务，提供API密钥列表查询功能，不需要任何认证。
    """
    start_time = time.time()
    request_id = get_request_id(request)

    try:
        # 构建查询 - API密钥必须属于指定租户
        query = AgentApiKeys.select().where(AgentApiKeys.tenant_id == tenant_id)

        # 应用Agent和状态过滤条件
        if agent_id:
            query = query.where(AgentApiKeys.agent_id == agent_id)
        if status:
            query = query.where(AgentApiKeys.status == status)

        # 获取总数
        total = query.count()

        # 分页查询
        api_keys = query.order_by(AgentApiKeys.created_at.desc()).limit(page_size).offset((page - 1) * page_size)

        api_key_list = []
        for key in api_keys:
            api_key_list.append({
                "api_key_id": key.api_key_id,
                "tenant_id": key.tenant_id,
                "agent_id": key.agent_id,
                "name": key.name,
                "description": key.description,
                "api_key": key.api_key,
                "permissions": key.permissions,
                "status": key.status,
                "expires_at": key.expires_at.isoformat() if key.expires_at else None,
                "created_at": key.created_at.isoformat(),
                "updated_at": key.updated_at.isoformat()
            })

        return APIResponse.paginated(
            items=api_key_list,
            total=total,
            page=page,
            page_size=page_size,
            message="获取租户API密钥列表成功",
            request_id=request_id,
            tenant_id=tenant_id,
            execution_time=calculate_execution_time(start_time)
        )

    except Exception as e:
        logger.error(f"获取API密钥列表失败: {e}")
        return APIResponse.error(
            message="获取API密钥列表失败，请稍后重试",
            error_code="INTERNAL_ERROR",
            request_id=request_id,
            execution_time=calculate_execution_time(start_time)
        )


@router.put("/api-keys/{api_key_id}")
async def update_api_key(api_key_id: str, request_data: ApiKeyUpdateRequest, request: Request):
    """
    更新API密钥（无需认证）

    作为内部服务，提供API密钥更新功能，不需要任何认证。
    """
    start_time = time.time()
    request_id = get_request_id(request)

    try:
        # 查找API密钥
        api_key = AgentApiKeys.select().where(AgentApiKeys.api_key_id == api_key_id).first()

        if not api_key:
            return APIResponse.error(
                message="API密钥不存在",
                error_code="API_KEY_NOT_FOUND",
                error_details=f"API密钥ID {api_key_id} 不存在",
                request_id=request_id,
                execution_time=calculate_execution_time(start_time)
            )

        # 更新字段
        if request_data.name:
            api_key.name = request_data.name
        if request_data.description is not None:
            api_key.description = request_data.description
        if request_data.permissions is not None:
            api_key.permissions = request_data.permissions
        if request_data.expires_at:
            api_key.expires_at = datetime.datetime.fromisoformat(request_data.expires_at)

        api_key.updated_at = datetime.datetime.utcnow()
        api_key.save()

        logger.info(f"API密钥更新成功: {api_key_id}")

        return APIResponse.success(
            data={
                "api_key_id": api_key.api_key_id,
                "updated_at": api_key.updated_at.isoformat()
            },
            message="API密钥更新成功",
            request_id=request_id,
            execution_time=calculate_execution_time(start_time)
        )

    except Exception as e:
        logger.error(f"API密钥更新失败: {e}")
        return APIResponse.error(
            message="API密钥更新失败，请稍后重试",
            error_code="INTERNAL_ERROR",
            request_id=request_id,
            execution_time=calculate_execution_time(start_time)
        )


@router.post("/api-keys/{api_key_id}/disable")
async def disable_api_key(api_key_id: str, request: Request):
    """
    禁用API密钥（无需认证）

    作为内部服务，提供API密钥禁用功能，不需要任何认证。
    """
    start_time = time.time()
    request_id = get_request_id(request)

    try:
        # 查找API密钥
        api_key = AgentApiKeys.select().where(AgentApiKeys.api_key_id == api_key_id).first()

        if not api_key:
            return APIResponse.error(
                message="API密钥不存在",
                error_code="API_KEY_NOT_FOUND",
                error_details=f"API密钥ID {api_key_id} 不存在",
                request_id=request_id,
                execution_time=calculate_execution_time(start_time)
            )

        # 禁用API密钥
        api_key.status = "disabled"
        api_key.updated_at = datetime.datetime.utcnow()
        api_key.save()

        logger.info(f"API密钥禁用成功: {api_key_id}")

        return APIResponse.success(
            data={
                "api_key_id": api_key.api_key_id,
                "status": "disabled",
                "disabled_at": api_key.updated_at.isoformat()
            },
            message="API密钥禁用成功",
            request_id=request_id,
            execution_time=calculate_execution_time(start_time)
        )

    except Exception as e:
        logger.error(f"API密钥禁用失败: {e}")
        return APIResponse.error(
            message="API密钥禁用失败，请稍后重试",
            error_code="INTERNAL_ERROR",
            request_id=request_id,
            execution_time=calculate_execution_time(start_time)
        )


@router.delete("/api-keys/{api_key_id}")
async def delete_api_key(api_key_id: str, request: Request):
    """
    删除API密钥（无需认证）

    作为内部服务，提供API密钥删除功能，不需要任何认证。
    """
    start_time = time.time()
    request_id = get_request_id(request)

    try:
        # 查找API密钥
        api_key = AgentApiKeys.select().where(AgentApiKeys.api_key_id == api_key_id).first()

        if not api_key:
            return APIResponse.error(
                message="API密钥不存在",
                error_code="API_KEY_NOT_FOUND",
                error_details=f"API密钥ID {api_key_id} 不存在",
                request_id=request_id,
                execution_time=calculate_execution_time(start_time)
            )

        # 删除API密钥
        api_key.delete_instance()

        logger.info(f"API密钥删除成功: {api_key_id}")

        return APIResponse.success(
            data={
                "api_key_id": api_key_id,
                "deleted_at": datetime.datetime.utcnow().isoformat()
            },
            message="API密钥删除成功",
            request_id=request_id,
            execution_time=calculate_execution_time(start_time)
        )

    except Exception as e:
        logger.error(f"API密钥删除失败: {e}")
        return APIResponse.error(
            message="API密钥删除失败，请稍后重试",
            error_code="INTERNAL_ERROR",
            request_id=request_id,
            execution_time=calculate_execution_time(start_time)
        )