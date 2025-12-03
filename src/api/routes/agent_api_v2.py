"""
Agent管理API接口 v2
作为内部服务，提供无需认证的Agent管理功能
"""

import datetime
import json
import secrets
import time
from typing import Optional, Dict, Any
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, validator

from src.common.database.database_model import AgentRecord
from src.common.logger import get_logger
from src.api.utils.response import APIResponse, get_request_id, calculate_execution_time

logger = get_logger(__name__)
router = APIRouter()


class AgentCreateRequest(BaseModel):
    """Agent创建请求"""
    tenant_id: str
    name: str
    description: Optional[str] = None
    template_id: Optional[str] = None
    config: Optional[Dict[str, Any]] = None

    @validator("name")
    def validate_name(cls, v):
        if len(v) < 1 or len(v) > 100:
            raise ValueError("Agent名称长度必须在1-100个字符之间")
        return v


class AgentUpdateRequest(BaseModel):
    """Agent更新请求"""
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[Dict[str, Any]] = None

    @validator("name")
    def validate_name(cls, v):
        if v is not None and (len(v) < 1 or len(v) > 100):
            raise ValueError("Agent名称长度必须在1-100个字符之间")
        return v


@router.post("/agents")
async def create_agent(request_data: AgentCreateRequest, request: Request):
    """
    创建Agent（无需认证）

    作为内部服务，提供Agent创建功能，不需要任何认证。
    """
    start_time = time.time()
    request_id = get_request_id(request)

    try:
        # 生成新的Agent ID
        new_agent_id = f"agent_{secrets.token_hex(8)}"

        # 创建新Agent记录
        config = request_data.config or {}
        new_agent = AgentRecord.create(
            agent_id=new_agent_id,
            tenant_id=request_data.tenant_id,
            name=request_data.name,
            description=request_data.description,
            persona=config.get("persona", ""),
            bot_overrides=json.dumps(config.get("bot_overrides", {})) if config.get("bot_overrides") else None,
            config_overrides=json.dumps(config.get("config_overrides", {})) if config.get("config_overrides") else None,
            tags=json.dumps(config.get("tags", [])) if config.get("tags") else None,
            created_at=datetime.datetime.utcnow(),
            updated_at=datetime.datetime.utcnow()
        )

        logger.info(f"Agent创建成功: {request_data.name} (ID: {new_agent_id})")

        # 构建配置对象
        config = {
            "persona": new_agent.persona,
            "bot_overrides": json.loads(new_agent.bot_overrides) if new_agent.bot_overrides else {},
            "config_overrides": json.loads(new_agent.config_overrides) if new_agent.config_overrides else {},
            "tags": json.loads(new_agent.tags) if new_agent.tags else []
        }

        return APIResponse.success(
            data={
                "agent_id": new_agent.agent_id,
                "tenant_id": new_agent.tenant_id,
                "name": new_agent.name,
                "description": new_agent.description,
                "template_id": None,
                "config": config,
                "status": "active",
                "created_at": new_agent.created_at.isoformat()
            },
            message="Agent创建成功",
            request_id=request_id,
            tenant_id=request_data.tenant_id,
            execution_time=calculate_execution_time(start_time)
        )

    except Exception as e:
        logger.error(f"Agent创建失败: {e}")
        return APIResponse.error(
            message="Agent创建失败，请稍后重试",
            error_code="INTERNAL_ERROR",
            error_details="服务器内部错误，请联系技术支持",
            request_id=request_id,
            execution_time=calculate_execution_time(start_time)
        )


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str, request: Request):
    """
    获取Agent详情（无需认证）

    作为内部服务，提供Agent查询功能，不需要任何认证。
    """
    start_time = time.time()
    request_id = get_request_id(request)

    try:
        # 查找Agent
        agent = AgentRecord.select().where(AgentRecord.agent_id == agent_id).first()

        if not agent:
            return APIResponse.error(
                message="Agent不存在",
                error_code="AGENT_NOT_FOUND",
                error_details=f"Agent ID {agent_id} 不存在",
                request_id=request_id,
                execution_time=calculate_execution_time(start_time)
            )

        # 构建配置对象
        config = {
            "persona": agent.persona,
            "bot_overrides": json.loads(agent.bot_overrides) if agent.bot_overrides else {},
            "config_overrides": json.loads(agent.config_overrides) if agent.config_overrides else {},
            "tags": json.loads(agent.tags) if agent.tags else []
        }

        return APIResponse.success(
            data={
                "agent_id": agent.agent_id,
                "tenant_id": agent.tenant_id,
                "name": agent.name,
                "description": agent.description,
                "template_id": None,
                "config": config,
                "status": "active",
                "created_at": agent.created_at.isoformat(),
                "updated_at": agent.updated_at.isoformat()
            },
            message="获取Agent详情成功",
            request_id=request_id,
            execution_time=calculate_execution_time(start_time)
        )

    except Exception as e:
        logger.error(f"获取Agent详情失败: {e}")
        return APIResponse.error(
            message="获取Agent详情失败，请稍后重试",
            error_code="INTERNAL_ERROR",
            request_id=request_id,
            execution_time=calculate_execution_time(start_time)
        )


@router.get("/agents")
async def list_agents(
    request: Request,
    tenant_id: str = Query(..., description="租户ID（必需）"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    status: Optional[str] = Query(default=None, description="状态过滤"),
):
    """
    获取指定租户的Agent列表（无需认证）

    Agent必须属于特定租户，因此tenant_id是必需参数。
    作为内部服务，提供Agent列表查询功能，不需要任何认证。
    """
    start_time = time.time()
    request_id = get_request_id(request)

    try:
        # 构建查询 - Agent必须属于指定租户
        query = AgentRecord.select().where(AgentRecord.tenant_id == tenant_id)

        # 应用状态过滤条件
        if status:
            query = query.where(AgentRecord.status == status)

        # 获取总数
        total = query.count()

        # 分页查询
        agents = query.order_by(AgentRecord.created_at.desc()).limit(page_size).offset((page - 1) * page_size)

        agent_list = []
        for agent in agents:
            # 构建配置对象
            config = {
                "persona": agent.persona,
                "bot_overrides": json.loads(agent.bot_overrides) if agent.bot_overrides else {},
                "config_overrides": json.loads(agent.config_overrides) if agent.config_overrides else {},
                "tags": json.loads(agent.tags) if agent.tags else []
            }

            agent_list.append({
                "agent_id": agent.agent_id,
                "tenant_id": agent.tenant_id,
                "name": agent.name,
                "description": agent.description,
                "template_id": None,
                "config": config,
                "status": "active",
                "created_at": agent.created_at.isoformat(),
                "updated_at": agent.updated_at.isoformat()
            })

        return APIResponse.paginated(
            items=agent_list,
            total=total,
            page=page,
            page_size=page_size,
            message="获取租户Agent列表成功",
            request_id=request_id,
            tenant_id=tenant_id,
            execution_time=calculate_execution_time(start_time)
        )

    except Exception as e:
        logger.error(f"获取Agent列表失败: {e}")
        return APIResponse.error(
            message="获取Agent列表失败，请稍后重试",
            error_code="INTERNAL_ERROR",
            request_id=request_id,
            execution_time=calculate_execution_time(start_time)
        )


@router.put("/agents/{agent_id}")
async def update_agent(agent_id: str, request_data: AgentUpdateRequest, request: Request):
    """
    更新Agent（无需认证）

    作为内部服务，提供Agent更新功能，不需要任何认证。
    """
    start_time = time.time()
    request_id = get_request_id(request)

    try:
        # 查找Agent
        agent = AgentRecord.select().where(AgentRecord.agent_id == agent_id).first()

        if not agent:
            return APIResponse.error(
                message="Agent不存在",
                error_code="AGENT_NOT_FOUND",
                error_details=f"Agent ID {agent_id} 不存在",
                request_id=request_id,
                execution_time=calculate_execution_time(start_time)
            )

        # 更新字段
        if request_data.name:
            agent.name = request_data.name
        if request_data.description is not None:
            agent.description = request_data.description

        # 更新配置字段
        if request_data.config is not None:
            config = request_data.config
            if config.get("persona") is not None:
                agent.persona = config["persona"]
            if config.get("bot_overrides") is not None:
                agent.bot_overrides = json.dumps(config["bot_overrides"])
            if config.get("config_overrides") is not None:
                agent.config_overrides = json.dumps(config["config_overrides"])
            if config.get("tags") is not None:
                agent.tags = json.dumps(config["tags"])

        agent.updated_at = datetime.datetime.utcnow()
        agent.save()

        logger.info(f"Agent更新成功: {agent_id}")

        return APIResponse.success(
            data={
                "agent_id": agent.agent_id,
                "updated_at": agent.updated_at.isoformat()
            },
            message="Agent更新成功",
            request_id=request_id,
            execution_time=calculate_execution_time(start_time)
        )

    except Exception as e:
        logger.error(f"Agent更新失败: {e}")
        return APIResponse.error(
            message="Agent更新失败，请稍后重试",
            error_code="INTERNAL_ERROR",
            request_id=request_id,
            execution_time=calculate_execution_time(start_time)
        )


@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str, request: Request):
    """
    删除Agent（无需认证）

    作为内部服务，提供Agent删除功能，不需要任何认证。
    """
    start_time = time.time()
    request_id = get_request_id(request)

    try:
        # 查找Agent
        agent = AgentRecord.select().where(AgentRecord.agent_id == agent_id).first()

        if not agent:
            return APIResponse.error(
                message="Agent不存在",
                error_code="AGENT_NOT_FOUND",
                error_details=f"Agent ID {agent_id} 不存在",
                request_id=request_id,
                execution_time=calculate_execution_time(start_time)
            )

        # 删除Agent
        agent.delete_instance()

        logger.info(f"Agent删除成功: {agent_id}")

        return APIResponse.success(
            data={
                "agent_id": agent_id,
                "deleted_at": datetime.datetime.utcnow().isoformat()
            },
            message="Agent删除成功",
            request_id=request_id,
            execution_time=calculate_execution_time(start_time)
        )

    except Exception as e:
        logger.error(f"Agent删除失败: {e}")
        return APIResponse.error(
            message="Agent删除失败，请稍后重试",
            error_code="INTERNAL_ERROR",
            request_id=request_id,
            execution_time=calculate_execution_time(start_time)
        )