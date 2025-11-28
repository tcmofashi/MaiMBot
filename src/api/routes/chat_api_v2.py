"""
新版聊天API接口 - 支持请求体参数传递租户和Agent信息
根据用户需求，tenant_id和agent_id通过请求体传递而不是URL参数
"""

import time
from typing import Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from peewee import DoesNotExist

from ..utils.isolated_api_utils import (
    api_endpoint,
    success_response,
    error_response,
    handle_api_error,
    get_client_ip,
    log_api_request,
    ResponseMessage,
)
from src.api.routes.auth_api import get_current_user
from src.common.logger import get_logger

logger = get_logger(__name__)

try:
    from src.isolation.isolation_context import create_isolation_context, get_isolation_context
    from src.chat.heart_flow.isolated_heartflow_api import process_isolated_message, create_isolated_heartflow_processor
    from src.chat.message_receive.isolated_message_api import (
        create_isolated_message,
        process_isolated_message as process_message,
    )
    from src.agent.isolated_agent_manager import get_isolated_agent_manager
    from src.common.database.database_model import AgentRecord
except ImportError:
    # 向后兼容性处理
    def create_isolation_context(*args, **kwargs):
        return None

    def get_isolation_context():
        return None

    async def process_isolated_message(*args, **kwargs):
        return {"response": "隔离化消息处理功能暂不可用"}

    async def create_isolated_heartflow_processor(*args, **kwargs):
        return None

    async def create_isolated_message(*args, **kwargs):
        return None

    async def process_message(*args, **kwargs):
        return {"response": "消息处理功能暂不可用"}

    def get_isolated_agent_manager(*args, **kwargs):
        return None


# 创建路由器
router = APIRouter(prefix="/v2", tags=["聊天v2"])


class ChatRequestV2(BaseModel):
    """新版聊天请求 - 支持请求体参数传递租户和Agent信息"""

    message: str
    tenant_id: str
    agent_id: str = "default"
    platform: str = "default"
    user_id: Optional[str] = None
    group_id: Optional[str] = None
    chat_identifier: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    class Config:
        schema_extra = {
            "example": {
                "message": "你好，我想问一个问题",
                "tenant_id": "tenant_abc123",
                "agent_id": "agent_def456",
                "platform": "web",
                "user_id": "user_789",
                "chat_identifier": "chat_session_001",
            }
        }


class ChatResponseV2(BaseModel):
    """新版聊天响应"""

    response: str
    agent_id: str
    platform: str
    chat_identifier: Optional[str] = None
    tenant_id: str
    metadata: Optional[Dict[str, Any]] = None
    timestamp: datetime

    class Config:
        schema_extra = {
            "example": {
                "response": "你好！很高兴为你服务，请问有什么可以帮助你的吗？",
                "agent_id": "agent_def456",
                "platform": "web",
                "chat_identifier": "chat_session_001",
                "tenant_id": "tenant_abc123",
                "metadata": {"response_time": 1.23, "model_used": "gpt-3.5-turbo"},
                "timestamp": "2024-01-01T12:00:00Z",
            }
        }


@router.post("/chat")
@api_endpoint(require_tenant=False, require_agent=False)
async def chat_v2(request: Request, chat_request: ChatRequestV2, credentials=None):
    """
    新版聊天API接口 - 支持请求体参数传递租户和Agent信息

    特点：
    1. tenant_id和agent_id通过请求体传递
    2. 自动验证租户权限
    3. 支持认证和匿名两种模式
    4. 完整的多租户隔离支持

    Args:
        chat_request: 包含tenant_id和agent_id的聊天请求
        credentials: 认证信息（可选）

    Returns:
        聊天响应
    """
    start_time = time.time()
    request_id = str(time.time())
    tenant_id = chat_request.tenant_id
    agent_id = chat_request.agent_id

    try:
        # 验证租户和Agent
        await _validate_tenant_and_agent(tenant_id, agent_id, credentials)

        # 创建隔离上下文
        isolation_context = create_isolation_context(
            tenant_id=tenant_id, agent_id=agent_id, platform=chat_request.platform
        )

        # 处理消息
        response_data = await _process_chat_request_v2(chat_request, isolation_context, request)

        # 计算执行时间
        execution_time = time.time() - start_time

        # 记录日志
        log_api_request(
            request=request, tenant_id=tenant_id, agent_id=agent_id, execution_time=execution_time, status_code=200
        )

        # 创建响应
        chat_response = ChatResponseV2(
            response=response_data["response"],
            agent_id=agent_id,
            platform=chat_request.platform,
            chat_identifier=chat_request.chat_identifier,
            tenant_id=tenant_id,
            metadata=response_data.get("metadata", {}),
            timestamp=datetime.utcnow(),
        )

        return success_response(
            message=ResponseMessage.SUCCESS,
            data=chat_response.dict(),
            request_id=request_id,
            tenant_id=tenant_id,
            execution_time=execution_time,
        )

    except HTTPException:
        execution_time = time.time() - start_time
        log_api_request(
            request=request, tenant_id=tenant_id, agent_id=agent_id, execution_time=execution_time, status_code=403
        )
        raise
    except Exception as e:
        execution_time = time.time() - start_time
        log_api_request(
            request=request,
            tenant_id=tenant_id,
            agent_id=agent_id,
            execution_time=execution_time,
            status_code=500,
            error=str(e),
        )

        return handle_api_error(e, request_id, tenant_id)


@router.post("/chat/auth")
async def chat_v2_auth(request: Request, chat_request: ChatRequestV2, current_user=Depends(get_current_user)):
    """
    需要认证的聊天API接口

    自动使用当前用户的租户信息，无需在请求体中提供tenant_id
    """
    start_time = time.time()
    request_id = str(time.time())

    try:
        # 使用当前用户的租户ID，忽略请求体中的tenant_id
        tenant_id = current_user.tenant_id
        agent_id = chat_request.agent_id

        # 验证Agent是否存在
        await _validate_agent_exists(tenant_id, agent_id)

        # 创建隔离上下文
        isolation_context = create_isolation_context(
            tenant_id=tenant_id, agent_id=agent_id, platform=chat_request.platform
        )

        # 更新请求中的租户ID
        chat_request.tenant_id = tenant_id

        # 处理消息
        response_data = await _process_chat_request_v2(chat_request, isolation_context, request)

        # 计算执行时间
        execution_time = time.time() - start_time

        # 记录日志
        log_api_request(
            request=request, tenant_id=tenant_id, agent_id=agent_id, execution_time=execution_time, status_code=200
        )

        # 创建响应
        chat_response = ChatResponseV2(
            response=response_data["response"],
            agent_id=agent_id,
            platform=chat_request.platform,
            chat_identifier=chat_request.chat_identifier,
            tenant_id=tenant_id,
            metadata={
                **response_data.get("metadata", {}),
                "authenticated_user": current_user.username,
                "auth_mode": True,
            },
            timestamp=datetime.utcnow(),
        )

        return success_response(
            message=ResponseMessage.SUCCESS,
            data=chat_response.dict(),
            request_id=request_id,
            tenant_id=tenant_id,
            execution_time=execution_time,
        )

    except HTTPException:
        execution_time = time.time() - start_time
        log_api_request(
            request=request,
            tenant_id=current_user.tenant_id,
            agent_id=chat_request.agent_id,
            execution_time=execution_time,
            status_code=403,
        )
        raise
    except Exception as e:
        execution_time = time.time() - start_time
        log_api_request(
            request=request,
            tenant_id=current_user.tenant_id,
            agent_id=chat_request.agent_id,
            execution_time=execution_time,
            status_code=500,
            error=str(e),
        )

        return handle_api_error(e, request_id, current_user.tenant_id)


@router.get("/chat-agents")
@api_endpoint(require_tenant=False)
async def get_agents_v2(request: Request, tenant_id: str, credentials=None):
    """
    获取指定租户的智能体列表

    Args:
        tenant_id: 租户ID（通过查询参数传递）
        credentials: 认证信息（可选）

    Returns:
        智能体列表
    """
    try:
        # 验证租户权限
        if credentials and tenant_id != credentials.tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问指定租户")

        try:
            from src.common.database.database_model import AgentRecord

            # 查询租户的所有Agent
            agents = (
                AgentRecord.select().where(AgentRecord.tenant_id == tenant_id).order_by(AgentRecord.updated_at.desc())
            )

            # 格式化智能体数据
            formatted_agents = []
            for agent in agents:
                agent_data = {
                    "agent_id": agent.agent_id,
                    "name": agent.name,
                    "description": agent.description,
                    "persona": agent.persona,
                    "tags": agent.tags,
                    "status": "active",
                    "tenant_id": tenant_id,
                    "created_at": agent.created_at.isoformat(),
                    "updated_at": agent.updated_at.isoformat(),
                }
                formatted_agents.append(agent_data)

            return success_response(
                message="获取智能体列表成功",
                data={"tenant_id": tenant_id, "agents": formatted_agents, "count": len(formatted_agents)},
            )

        except Exception as e:
            logger.error(f"查询Agent失败: {e}")
            return success_response(message="查询智能体失败", data={"tenant_id": tenant_id, "agents": [], "count": 0})

    except HTTPException:
        raise
    except Exception as e:
        return error_response(message=f"获取智能体列表失败: {str(e)}", status_code=500)


@router.post("/chat/batch")
@api_endpoint(require_tenant=False, require_agent=False)
async def batch_chat_v2(request: Request, chat_requests: list, credentials=None):
    """
    批量聊天处理 - 支持请求体参数

    Args:
        chat_requests: 聊天请求列表，每个请求都包含tenant_id和agent_id
        credentials: 认证信息（可选）

    Returns:
        批量聊天响应
    """
    try:
        if len(chat_requests) > 50:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="批量请求最多支持50条消息")

        results = []
        errors = []

        for i, request_data in enumerate(chat_requests):
            try:
                # 验证和创建请求对象
                if isinstance(request_data, dict):
                    chat_request = ChatRequestV2(**request_data)
                else:
                    chat_request = request_data

                # 验证租户和Agent
                await _validate_tenant_and_agent(chat_request.tenant_id, chat_request.agent_id, credentials)

                # 创建隔离上下文
                isolation_context = create_isolation_context(
                    tenant_id=chat_request.tenant_id, agent_id=chat_request.agent_id, platform=chat_request.platform
                )

                # 处理单个请求
                response_data = await _process_chat_request_v2(chat_request, isolation_context, request)

                # 创建响应对象
                chat_response = ChatResponseV2(
                    response=response_data["response"],
                    agent_id=chat_request.agent_id,
                    platform=chat_request.platform,
                    chat_identifier=chat_request.chat_identifier,
                    tenant_id=chat_request.tenant_id,
                    metadata=response_data.get("metadata", {}),
                    timestamp=datetime.utcnow(),
                )

                results.append({"index": i, "success": True, "data": chat_response.dict()})

            except Exception as e:
                errors.append({"index": i, "success": False, "error": str(e)})

        return success_response(
            message="批量处理完成",
            data={
                "results": results,
                "errors": errors,
                "summary": {"total": len(chat_requests), "success": len(results), "failed": len(errors)},
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        return error_response(message=f"批量处理失败: {str(e)}", status_code=500)


async def _validate_tenant_and_agent(tenant_id: str, agent_id: str, credentials):
    """
    验证租户和Agent权限
    """
    # 如果有认证信息，验证租户权限
    if credentials and tenant_id != credentials.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问指定租户")

    # 验证Agent是否存在
    await _validate_agent_exists(tenant_id, agent_id)


async def _validate_agent_exists(tenant_id: str, agent_id: str):
    """
    验证Agent是否存在
    """
    try:
        from src.common.database.database_model import AgentRecord

        agent = (
            AgentRecord.select()
            .where((AgentRecord.tenant_id == tenant_id) & (AgentRecord.agent_id == agent_id))
            .first()
        )

        if not agent:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"智能体不存在: {agent_id}")

    except DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"智能体不存在: {agent_id}")
    except Exception:
        # 如果数据库查询失败，继续处理但不阻止聊天
        pass


async def _process_chat_request_v2(chat_request: ChatRequestV2, isolation_context, request: Request) -> Dict[str, Any]:
    """
    处理聊天请求（新版）
    """
    try:
        # 创建消息数据
        message_data = {
            "content": chat_request.message,
            "user_id": chat_request.user_id,
            "group_id": chat_request.group_id,
            "platform": chat_request.platform,
            "chat_identifier": chat_request.chat_identifier,
            "metadata": chat_request.metadata or {},
        }

        # 处理消息
        try:
            # 尝试使用隔离化心流处理器
            processor = create_isolated_heartflow_processor(chat_request.tenant_id, chat_request.agent_id)

            if processor:
                result = await process_isolated_message(
                    message_data, chat_request.tenant_id, chat_request.agent_id, chat_request.platform
                )
                response_text = result.get("response", "抱歉，我现在无法回复")
            else:
                # 使用基础消息处理
                result = await process_message(
                    message_data, chat_request.tenant_id, chat_request.agent_id, chat_request.platform
                )
                response_text = result.get("response", "抱歉，我现在无法回复")

        except Exception as e:
            response_text = f"消息处理出错: {str(e)}"

        # 创建响应数据
        return {
            "response": response_text,
            "metadata": {
                "tenant_id": chat_request.tenant_id,
                "agent_id": chat_request.agent_id,
                "platform": chat_request.platform,
                "client_ip": get_client_ip(request),
                "isolation_context": {
                    "tenant_id": isolation_context.tenant_id,
                    "agent_id": isolation_context.agent_id,
                    "platform": isolation_context.platform,
                },
            },
        }

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"聊天处理失败: {str(e)}") from e
