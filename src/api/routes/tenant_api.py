"""
租户管理API接口
支持租户信息的查看、更新等功能
"""

import datetime
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, validator

from src.common.database.database_model import TenantUsers
from src.api.routes.auth_api import get_current_user
from src.common.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/v1/tenant", tags=["租户管理"])


class TenantUpdateRequest(BaseModel):
    """租户更新请求"""

    tenant_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    tenant_config: Optional[Dict[str, Any]] = None

    @validator("email")
    def validate_email(cls, v):
        if v is not None and "@" not in v:
            raise ValueError("邮箱格式无效")
        return v


class TenantInfo(BaseModel):
    """租户信息"""

    tenant_id: str
    user_id: str
    username: str
    email: Optional[str] = None
    phone: Optional[str] = None
    tenant_name: str
    tenant_type: str
    tenant_config: Optional[Dict[str, Any]] = None
    api_key: str
    status: str
    permissions: List[str]
    created_at: datetime.datetime
    updated_at: datetime.datetime
    last_login_at: Optional[datetime.datetime] = None
    login_count: int


class TenantStats(BaseModel):
    """租户统计信息"""

    tenant_id: str
    tenant_name: str
    total_agents: int
    total_messages: int
    total_api_calls: int
    total_cost: float
    last_active: Optional[datetime.datetime] = None


@router.get("/", response_model=TenantInfo)
async def get_tenant_info(current_user: TenantUsers = Depends(get_current_user)):
    """
    获取当前租户信息
    """
    try:
        # 解析权限列表
        permissions = []
        try:
            if current_user.permissions:
                permissions = (
                    eval(current_user.permissions)
                    if isinstance(current_user.permissions, str)
                    else current_user.permissions
                )
        except:
            permissions = []

        # 解析租户配置
        tenant_config = None
        try:
            if current_user.tenant_config:
                tenant_config = (
                    eval(current_user.tenant_config)
                    if isinstance(current_user.tenant_config, str)
                    else current_user.tenant_config
                )
        except:
            tenant_config = {}

        return TenantInfo(
            tenant_id=current_user.tenant_id,
            user_id=current_user.user_id,
            username=current_user.username,
            email=current_user.email,
            phone=current_user.phone,
            tenant_name=current_user.tenant_name,
            tenant_type=current_user.tenant_type,
            tenant_config=tenant_config,
            api_key=current_user.api_key,
            status=current_user.status,
            permissions=permissions,
            created_at=current_user.created_at,
            updated_at=current_user.updated_at,
            last_login_at=current_user.last_login_at,
            login_count=current_user.login_count,
        )

    except Exception as e:
        logger.error(f"获取租户信息失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="获取租户信息失败")


@router.put("/", response_model=TenantInfo)
async def update_tenant_info(request_data: TenantUpdateRequest, current_user: TenantUsers = Depends(get_current_user)):
    """
    更新租户信息
    """
    try:
        # 更新允许的字段
        if request_data.tenant_name is not None:
            current_user.tenant_name = request_data.tenant_name

        if request_data.email is not None:
            # 检查邮箱是否已被其他用户使用
            existing_user = (
                TenantUsers.select()
                .where((TenantUsers.email == request_data.email) & (TenantUsers.user_id != current_user.user_id))
                .first()
            )

            if existing_user:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="邮箱已被其他用户使用")

            current_user.email = request_data.email

        if request_data.phone is not None:
            current_user.phone = request_data.phone

        if request_data.tenant_config is not None:
            current_user.tenant_config = str(request_data.tenant_config)

        # 更新时间戳
        current_user.updated_at = datetime.datetime.utcnow()
        current_user.save()

        logger.info(f"租户信息更新成功: {current_user.username} (tenant: {current_user.tenant_id})")

        # 解析权限列表
        permissions = []
        try:
            if current_user.permissions:
                permissions = (
                    eval(current_user.permissions)
                    if isinstance(current_user.permissions, str)
                    else current_user.permissions
                )
        except:
            permissions = []

        # 解析租户配置
        tenant_config = None
        try:
            if current_user.tenant_config:
                tenant_config = (
                    eval(current_user.tenant_config)
                    if isinstance(current_user.tenant_config, str)
                    else current_user.tenant_config
                )
        except:
            tenant_config = {}

        return TenantInfo(
            tenant_id=current_user.tenant_id,
            user_id=current_user.user_id,
            username=current_user.username,
            email=current_user.email,
            phone=current_user.phone,
            tenant_name=current_user.tenant_name,
            tenant_type=current_user.tenant_type,
            tenant_config=tenant_config,
            api_key=current_user.api_key,
            status=current_user.status,
            permissions=permissions,
            created_at=current_user.created_at,
            updated_at=current_user.updated_at,
            last_login_at=current_user.last_login_at,
            login_count=current_user.login_count,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新租户信息失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="更新租户信息失败")


@router.get("/stats", response_model=TenantStats)
async def get_tenant_stats(current_user: TenantUsers = Depends(get_current_user)):
    """
    获取租户统计信息
    """
    try:
        from src.common.database.database_model import AgentRecord, Messages, LLMUsage

        tenant_id = current_user.tenant_id

        # 统计Agent数量
        agent_count = AgentRecord.select().where(AgentRecord.tenant_id == tenant_id).count()

        # 统计消息数量
        message_count = Messages.select().where(Messages.tenant_id == tenant_id).count()

        # 统计API调用次数和总成本
        api_usage = LLMUsage.select().where(LLMUsage.tenant_id == tenant_id)

        api_call_count = api_usage.count()
        total_cost = sum(usage.cost for usage in api_usage if usage.cost)

        # 获取最后活跃时间
        last_message = Messages.select().where(Messages.tenant_id == tenant_id).order_by(Messages.time.desc()).first()

        last_active = None
        if last_message:
            last_active = datetime.datetime.fromtimestamp(last_message.time)

        return TenantStats(
            tenant_id=tenant_id,
            tenant_name=current_user.tenant_name,
            total_agents=agent_count,
            total_messages=message_count,
            total_api_calls=api_call_count,
            total_cost=total_cost,
            last_active=last_active,
        )

    except Exception as e:
        logger.error(f"获取租户统计信息失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="获取租户统计信息失败")


@router.post("/upgrade")
async def upgrade_tenant(current_user: TenantUsers = Depends(get_current_user)):
    """
    升级租户（从个人版升级为企业版）
    """
    try:
        if current_user.tenant_type == "enterprise":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="租户已经是企业版")

        # 更新租户类型
        current_user.tenant_type = "enterprise"
        current_user.updated_at = datetime.datetime.utcnow()
        current_user.save()

        logger.info(f"租户升级成功: {current_user.username} (tenant: {current_user.tenant_id})")

        return {"message": "租户升级成功", "tenant_type": "enterprise", "tenant_id": current_user.tenant_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"租户升级失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="租户升级失败")


@router.get("/api-key")
async def get_api_key(current_user: TenantUsers = Depends(get_current_user)):
    """
    获取API密钥
    """
    return {"api_key": current_user.api_key, "tenant_id": current_user.tenant_id, "user_id": current_user.user_id}


@router.post("/regenerate-api-key")
async def regenerate_api_key(current_user: TenantUsers = Depends(get_current_user)):
    """
    重新生成API密钥
    """
    try:
        # 生成新的API密钥
        from src.common.database.database_model import generate_api_key

        new_api_key = generate_api_key()

        # 更新数据库
        current_user.api_key = new_api_key
        current_user.updated_at = datetime.datetime.utcnow()
        current_user.save()

        logger.info(f"API密钥重新生成成功: {current_user.username} (tenant: {current_user.tenant_id})")

        return {"message": "API密钥重新生成成功", "api_key": new_api_key, "tenant_id": current_user.tenant_id}

    except Exception as e:
        logger.error(f"重新生成API密钥失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="重新生成API密钥失败")
