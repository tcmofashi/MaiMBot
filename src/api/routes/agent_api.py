"""
Agent模板和配置管理API接口
支持Agent的创建、查询、更新、删除等功能
"""

import datetime
import json
import secrets
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends, status, Query
from pydantic import BaseModel, validator
from peewee import DoesNotExist

from src.common.database.database_model import AgentRecord, AgentTemplates, create_agent_template
from src.api.routes.auth_api import get_current_user
from src.common.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/v1/agents", tags=["Agent管理"])


class AgentTemplateInfo(BaseModel):
    """Agent模板信息"""

    template_id: str
    name: str
    description: Optional[str] = None
    category: str
    tags: List[str]
    is_active: bool
    is_system: bool
    usage_count: int
    persona: str
    personality_traits: Optional[Dict[str, Any]] = None
    response_style: Optional[str] = None
    memory_config: Optional[Dict[str, Any]] = None
    plugin_config: List[str]
    config_schema: Optional[Dict[str, Any]] = None
    default_config: Optional[Dict[str, Any]] = None
    created_by: Optional[str] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime


class AgentCreateRequest(BaseModel):
    """Agent创建请求"""

    name: str
    description: Optional[str] = None
    tags: Optional[str] = None
    template_id: Optional[str] = None
    persona: Optional[str] = None
    personality_traits: Optional[Dict[str, Any]] = None
    response_style: Optional[str] = None
    memory_config: Optional[Dict[str, Any]] = None
    plugin_config: Optional[List[str]] = None
    bot_overrides: Optional[str] = None
    config_overrides: Optional[str] = None

    @validator("name")
    def validate_name(cls, v):
        if len(v) < 1 or len(v) > 100:
            raise ValueError("Agent名称长度必须在1-100个字符之间")
        return v


class AgentUpdateRequest(BaseModel):
    """Agent更新请求"""

    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[str] = None
    persona: Optional[str] = None
    personality_traits: Optional[Dict[str, Any]] = None
    response_style: Optional[str] = None
    memory_config: Optional[Dict[str, Any]] = None
    plugin_config: Optional[List[str]] = None
    bot_overrides: Optional[str] = None
    config_overrides: Optional[str] = None


class AgentInfo(BaseModel):
    """Agent信息"""

    agent_id: str
    tenant_id: str
    name: str
    description: Optional[str] = None
    tags: Optional[str] = None
    persona: str
    bot_overrides: Optional[str] = None
    config_overrides: Optional[str] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime


class AgentTemplateCreateRequest(BaseModel):
    """Agent模板创建请求"""

    template_id: str
    name: str
    description: Optional[str] = None
    category: str = "general"
    tags: Optional[List[str]] = None
    persona: str
    personality_traits: Optional[Dict[str, Any]] = None
    response_style: Optional[str] = None
    memory_config: Optional[Dict[str, Any]] = None
    plugin_config: Optional[List[str]] = None
    config_schema: Optional[Dict[str, Any]] = None
    default_config: Optional[Dict[str, Any]] = None

    @validator("template_id")
    def validate_template_id(cls, v):
        if len(v) < 3 or len(v) > 50:
            raise ValueError("模板ID长度必须在3-50个字符之间")
        return v

    @validator("name")
    def validate_name(cls, v):
        if len(v) < 1 or len(v) > 100:
            raise ValueError("模板名称长度必须在1-100个字符之间")
        return v


def generate_agent_id() -> str:
    """生成Agent ID"""
    return f"agent_{secrets.token_hex(8)}"


def parse_json_field(field_value: Optional[str]) -> Optional[Any]:
    """安全解析JSON字段"""
    if field_value is None:
        return None
    try:
        return json.loads(field_value)
    except (json.JSONDecodeError, TypeError):
        return None


@router.get("/templates", response_model=List[AgentTemplateInfo])
async def list_agent_templates(
    category: Optional[str] = Query(None, description="模板分类过滤"),
    is_active: Optional[bool] = Query(True, description="是否只显示启用的模板"),
    current_user=None,  # 模板列表不需要认证
):
    """
    获取Agent模板列表
    """
    try:
        query = AgentTemplates.select()

        # 应用过滤条件
        if category:
            query = query.where(AgentTemplates.category == category)

        if is_active is not None:
            query = query.where(AgentTemplates.is_active == is_active)

        templates = query.order_by(AgentTemplates.usage_count.desc())

        result = []
        for template in templates:
            # 解析JSON字段
            tags = parse_json_field(template.tags) or []
            personality_traits = parse_json_field(template.personality_traits)
            memory_config = parse_json_field(template.memory_config)
            plugin_config = parse_json_field(template.plugin_config) or []
            config_schema = parse_json_field(template.config_schema)
            default_config = parse_json_field(template.default_config)

            result.append(
                AgentTemplateInfo(
                    template_id=template.template_id,
                    name=template.name,
                    description=template.description,
                    category=template.category,
                    tags=tags,
                    is_active=template.is_active,
                    is_system=template.is_system,
                    usage_count=template.usage_count,
                    persona=template.persona,
                    personality_traits=personality_traits,
                    response_style=template.response_style,
                    memory_config=memory_config,
                    plugin_config=plugin_config,
                    config_schema=config_schema,
                    default_config=default_config,
                    created_by=template.created_by,
                    created_at=template.created_at,
                    updated_at=template.updated_at,
                )
            )

        return result

    except Exception as e:
        logger.error(f"获取Agent模板列表失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="获取Agent模板列表失败")


@router.get("/templates/{template_id}", response_model=AgentTemplateInfo)
async def get_agent_template(
    template_id: str,
    current_user=None,  # 获取单个模板不需要认证
):
    """
    获取指定Agent模板详情
    """
    try:
        template = AgentTemplates.get(AgentTemplates.template_id == template_id)

        # 解析JSON字段
        tags = parse_json_field(template.tags) or []
        personality_traits = parse_json_field(template.personality_traits)
        memory_config = parse_json_field(template.memory_config)
        plugin_config = parse_json_field(template.plugin_config) or []
        config_schema = parse_json_field(template.config_schema)
        default_config = parse_json_field(template.default_config)

        return AgentTemplateInfo(
            template_id=template.template_id,
            name=template.name,
            description=template.description,
            category=template.category,
            tags=tags,
            is_active=template.is_active,
            is_system=template.is_system,
            usage_count=template.usage_count,
            persona=template.persona,
            personality_traits=personality_traits,
            response_style=template.response_style,
            memory_config=memory_config,
            plugin_config=plugin_config,
            config_schema=config_schema,
            default_config=default_config,
            created_by=template.created_by,
            created_at=template.created_at,
            updated_at=template.updated_at,
        )

    except DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent模板不存在")
    except Exception as e:
        logger.error(f"获取Agent模板失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="获取Agent模板失败")


@router.post("/", response_model=AgentInfo)
async def create_agent(request_data: AgentCreateRequest, current_user=Depends(get_current_user)):
    """
    创建新Agent
    """
    try:
        tenant_id = current_user.tenant_id
        agent_id = generate_agent_id()

        # 如果提供了模板ID，从模板获取配置
        if request_data.template_id:
            try:
                template = AgentTemplates.get(AgentTemplates.template_id == request_data.template_id)

                # 合并模板配置和请求配置
                persona = request_data.persona or template.persona
                personality_traits = request_data.personality_traits or parse_json_field(template.personality_traits)
                response_style = request_data.response_style or template.response_style
                memory_config = request_data.memory_config or parse_json_field(template.memory_config)
                plugin_config = request_data.plugin_config or parse_json_field(template.plugin_config)

                # 增加模板使用次数
                template.usage_count += 1
                template.save()

            except DoesNotExist:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="指定的Agent模板不存在")
        else:
            # 使用请求中的配置
            persona = request_data.persona or "一个友好的人工智能助手"
            personality_traits = request_data.personality_traits
            response_style = request_data.response_style
            memory_config = request_data.memory_config
            plugin_config = request_data.plugin_config or []

        # 创建Agent记录
        agent = AgentRecord.create(
            tenant_id=tenant_id,
            agent_id=agent_id,
            name=request_data.name,
            description=request_data.description,
            tags=request_data.tags,
            persona=persona,
            bot_overrides=request_data.bot_overrides,
            config_overrides=request_data.config_overrides,
        )

        logger.info(f"创建Agent成功: {agent.name} (tenant: {tenant_id}, agent: {agent_id})")

        return AgentInfo(
            agent_id=agent.agent_id,
            tenant_id=agent.tenant_id,
            name=agent.name,
            description=agent.description,
            tags=agent.tags,
            persona=agent.persona,
            bot_overrides=agent.bot_overrides,
            config_overrides=agent.config_overrides,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建Agent失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="创建Agent失败")


@router.get("/", response_model=List[AgentInfo])
async def list_agents(current_user=Depends(get_current_user)):
    """
    获取当前租户的Agent列表
    """
    try:
        tenant_id = current_user.tenant_id

        agents = AgentRecord.select().where(AgentRecord.tenant_id == tenant_id).order_by(AgentRecord.updated_at.desc())

        result = []
        for agent in agents:
            result.append(
                AgentInfo(
                    agent_id=agent.agent_id,
                    tenant_id=agent.tenant_id,
                    name=agent.name,
                    description=agent.description,
                    tags=agent.tags,
                    persona=agent.persona,
                    bot_overrides=agent.bot_overrides,
                    config_overrides=agent.config_overrides,
                    created_at=agent.created_at,
                    updated_at=agent.updated_at,
                )
            )

        return result

    except Exception as e:
        logger.error(f"获取Agent列表失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="获取Agent列表失败")


@router.get("/{agent_id}", response_model=AgentInfo)
async def get_agent(agent_id: str, current_user=Depends(get_current_user)):
    """
    获取指定Agent详情
    """
    try:
        tenant_id = current_user.tenant_id

        agent = AgentRecord.get((AgentRecord.tenant_id == tenant_id) & (AgentRecord.agent_id == agent_id))

        return AgentInfo(
            agent_id=agent.agent_id,
            tenant_id=agent.tenant_id,
            name=agent.name,
            description=agent.description,
            tags=agent.tags,
            persona=agent.persona,
            bot_overrides=agent.bot_overrides,
            config_overrides=agent.config_overrides,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
        )

    except DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent不存在")
    except Exception as e:
        logger.error(f"获取Agent失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="获取Agent失败")


@router.put("/{agent_id}", response_model=AgentInfo)
async def update_agent(agent_id: str, request_data: AgentUpdateRequest, current_user=Depends(get_current_user)):
    """
    更新Agent配置
    """
    try:
        tenant_id = current_user.tenant_id

        agent = AgentRecord.get((AgentRecord.tenant_id == tenant_id) & (AgentRecord.agent_id == agent_id))

        # 更新允许的字段
        if request_data.name is not None:
            agent.name = request_data.name

        if request_data.description is not None:
            agent.description = request_data.description

        if request_data.tags is not None:
            agent.tags = request_data.tags

        if request_data.persona is not None:
            agent.persona = request_data.persona

        if request_data.bot_overrides is not None:
            agent.bot_overrides = request_data.bot_overrides

        if request_data.config_overrides is not None:
            agent.config_overrides = request_data.config_overrides

        # 更新时间戳
        agent.updated_at = datetime.datetime.utcnow()
        agent.save()

        logger.info(f"更新Agent成功: {agent.name} (tenant: {tenant_id}, agent: {agent_id})")

        return AgentInfo(
            agent_id=agent.agent_id,
            tenant_id=agent.tenant_id,
            name=agent.name,
            description=agent.description,
            tags=agent.tags,
            persona=agent.persona,
            bot_overrides=agent.bot_overrides,
            config_overrides=agent.config_overrides,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
        )

    except DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent不存在")
    except Exception as e:
        logger.error(f"更新Agent失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="更新Agent失败")


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str, current_user=Depends(get_current_user)):
    """
    删除Agent
    """
    try:
        tenant_id = current_user.tenant_id

        agent = AgentRecord.get((AgentRecord.tenant_id == tenant_id) & (AgentRecord.agent_id == agent_id))

        agent_name = agent.name
        agent.delete_instance()

        logger.info(f"删除Agent成功: {agent_name} (tenant: {tenant_id}, agent: {agent_id})")

        return {"message": f"Agent '{agent_name}' 删除成功"}

    except DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent不存在")
    except Exception as e:
        logger.error(f"删除Agent失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="删除Agent失败")


# 管理员接口 - 创建Agent模板
@router.post("/templates", response_model=AgentTemplateInfo)
async def create_agent_template_api(request_data: AgentTemplateCreateRequest, current_user=Depends(get_current_user)):
    """
    创建Agent模板（管理员功能）
    """
    try:
        # 检查是否为管理员
        permissions = parse_json_field(current_user.permissions) or []
        if "admin" not in permissions and current_user.tenant_type != "enterprise":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有权限创建Agent模板")

        # 检查模板ID是否已存在
        existing_template = (
            AgentTemplates.select().where(AgentTemplates.template_id == request_data.template_id).first()
        )

        if existing_template:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="模板ID已存在")

        # 创建模板
        template = create_agent_template(
            template_id=request_data.template_id,
            name=request_data.name,
            persona=request_data.persona,
            description=request_data.description,
            category=request_data.category,
            personality_traits=request_data.personality_traits,
            response_style=request_data.response_style,
            memory_config=request_data.memory_config,
            plugin_config=request_data.plugin_config,
            is_system=False,
            created_by=current_user.user_id,
        )

        # 更新配置字段
        if request_data.config_schema:
            template.config_schema = json.dumps(request_data.config_schema)
        if request_data.default_config:
            template.default_config = json.dumps(request_data.default_config)
        if request_data.tags:
            template.tags = json.dumps(request_data.tags)

        template.save()

        logger.info(f"创建Agent模板成功: {template.name} (template: {template.template_id})")

        # 解析JSON字段返回
        tags = parse_json_field(template.tags) or []
        personality_traits = parse_json_field(template.personality_traits)
        memory_config = parse_json_field(template.memory_config)
        plugin_config = parse_json_field(template.plugin_config) or []
        config_schema = parse_json_field(template.config_schema)
        default_config = parse_json_field(template.default_config)

        return AgentTemplateInfo(
            template_id=template.template_id,
            name=template.name,
            description=template.description,
            category=template.category,
            tags=tags,
            is_active=template.is_active,
            is_system=template.is_system,
            usage_count=template.usage_count,
            persona=template.persona,
            personality_traits=personality_traits,
            response_style=template.response_style,
            memory_config=memory_config,
            plugin_config=plugin_config,
            config_schema=config_schema,
            default_config=default_config,
            created_by=template.created_by,
            created_at=template.created_at,
            updated_at=template.updated_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建Agent模板失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="创建Agent模板失败")
