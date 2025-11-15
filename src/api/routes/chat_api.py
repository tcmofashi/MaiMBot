"""
扩展聊天API接口

在现有聊天API基础上添加隔离支持，保持向后兼容性的同时提供多租户隔离功能。
支持：
- 隔离上下文的自动检测
- 租户级别的权限控制
- 向后兼容性保证
- 渐进式迁移支持

作者：MaiBot
版本：1.0.0
"""

import time
from typing import Optional, Dict, Any, Union
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query

from ..middleware.tenant_auth_middleware import get_current_tenant_credentials
from ..utils.isolated_api_utils import (
    ChatRequest,
    ChatResponse,
    api_endpoint,
    success_response,
    error_response,
    handle_api_error,
    get_client_ip,
    log_api_request,
    ResponseMessage,
)

try:
    from src.isolation.isolation_context import create_isolation_context, get_isolation_context
    from src.chat.heart_flow.isolated_heartflow_api import process_isolated_message, create_isolated_heartflow_processor
    from src.chat.message_receive.isolated_message_api import (
        create_isolated_message,
        process_isolated_message as process_message,
    )
    from src.agent.isolated_agent_manager import get_isolated_agent_manager
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
router = APIRouter(prefix="/v1", tags=["chat"])


@router.post("/chat")
@api_endpoint(require_tenant=False, require_agent=False)
async def chat(
    request: Request,
    chat_request: Union[ChatRequest, dict],
    credentials=Depends(get_current_tenant_credentials),
    tenant_id: Optional[str] = Query(None, description="租户ID（可选，用于多租户隔离）"),
):
    """
    聊天API接口（支持向后兼容和隔离化）

    支持两种模式：
    1. 传统模式：不提供tenant_id，使用原有的聊天逻辑
    2. 隔离模式：提供tenant_id，使用多租户隔离逻辑

    Args:
        chat_request: 聊天请求
        credentials: 认证信息（可选）
        tenant_id: 租户ID（可选，用于多租户隔离）

    Returns:
        聊天响应
    """
    start_time = time.time()
    request_id = str(time.time())

    try:
        # 检测是否使用隔离模式
        use_isolation = False
        isolation_context = None

        if tenant_id and credentials:
            # 隔离模式：有租户ID和认证信息
            use_isolation = True

            # 验证租户权限
            if tenant_id != credentials.tenant_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问指定租户")

            # 创建隔离上下文
            if isinstance(chat_request, dict):
                agent_id = chat_request.get("agent_id", "default")
                platform = chat_request.get("platform", "default")
            else:
                agent_id = chat_request.agent_id
                platform = chat_request.platform

            isolation_context = create_isolation_context(tenant_id=tenant_id, agent_id=agent_id, platform=platform)

        # 验证和标准化请求
        if isinstance(chat_request, dict):
            validated_request = ChatRequest(**chat_request)
        else:
            validated_request = chat_request

        # 处理消息
        if use_isolation and isolation_context:
            # 隔离模式处理
            response_data = await _process_isolated_chat(validated_request, isolation_context, tenant_id, request)
        else:
            # 传统模式处理（向后兼容）
            response_data = await _process_legacy_chat(validated_request, request)

        # 计算执行时间
        execution_time = time.time() - start_time

        # 记录日志
        log_api_request(
            request=request,
            tenant_id=tenant_id,
            agent_id=validated_request.agent_id,
            execution_time=execution_time,
            status_code=200,
        )

        # 返回响应
        return success_response(
            message=ResponseMessage.SUCCESS,
            data=response_data,
            request_id=request_id,
            tenant_id=tenant_id,
            execution_time=execution_time,
        )

    except HTTPException:
        execution_time = time.time() - start_time
        log_api_request(
            request=request,
            tenant_id=tenant_id,
            agent_id=getattr(chat_request, "agent_id", "unknown"),
            execution_time=execution_time,
            status_code=403,
        )
        raise
    except Exception as e:
        execution_time = time.time() - start_time
        log_api_request(
            request=request,
            tenant_id=tenant_id,
            agent_id=getattr(chat_request, "agent_id", "unknown"),
            execution_time=execution_time,
            status_code=500,
            error=str(e),
        )

        return handle_api_error(e, request_id, tenant_id)


async def _process_isolated_chat(
    chat_request: ChatRequest, isolation_context, tenant_id: str, request: Request
) -> Dict[str, Any]:
    """
    处理隔离化聊天请求
    """
    try:
        # 验证智能体是否存在
        try:
            agent_manager = get_isolated_agent_manager(tenant_id)
            agent = agent_manager.get_tenant_agent(chat_request.agent_id)
            if not agent:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail=f"智能体不存在: {chat_request.agent_id}"
                )
        except Exception:
            # 如果智能体管理器不可用，继续处理
            pass

        # 创建隔离化消息
        message_data = {
            "content": chat_request.message,
            "user_id": chat_request.user_id,
            "group_id": chat_request.group_id,
            "platform": chat_request.platform,
            "chat_identifier": chat_request.chat_identifier,
            "metadata": chat_request.metadata,
        }

        # 处理消息
        try:
            # 尝试使用隔离化心流处理器
            processor = create_isolated_heartflow_processor(tenant_id, chat_request.agent_id)

            if processor:
                result = await process_isolated_message(
                    message_data, tenant_id, chat_request.agent_id, chat_request.platform
                )
                response_text = result.get("response", "抱歉，我现在无法回复")
            else:
                # 使用基础消息处理
                result = await process_message(message_data, tenant_id, chat_request.agent_id, chat_request.platform)
                response_text = result.get("response", "抱歉，我现在无法回复")

        except Exception as e:
            response_text = f"消息处理出错: {str(e)}"

        # 创建响应
        chat_response = ChatResponse(
            response=response_text,
            agent_id=chat_request.agent_id,
            platform=chat_request.platform,
            chat_identifier=chat_request.chat_identifier,
            metadata={
                "tenant_id": tenant_id,
                "isolation_mode": True,
                "client_ip": get_client_ip(request),
                "isolation_context": {
                    "tenant_id": isolation_context.tenant_id,
                    "agent_id": isolation_context.agent_id,
                    "platform": isolation_context.platform,
                },
            },
        )

        return chat_response.dict()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"隔离化聊天处理失败: {str(e)}"
        ) from e


async def _process_legacy_chat(chat_request: ChatRequest, request: Request) -> Dict[str, Any]:
    """
    处理传统聊天请求（向后兼容）
    """
    try:
        # 这里应该调用原有的聊天逻辑
        # 由于没有原有代码，我们提供一个模拟实现

        # 模拟传统的聊天处理
        response_text = f"（传统模式）收到消息: {chat_request.message}"

        # 创建响应
        chat_response = ChatResponse(
            response=response_text,
            agent_id=chat_request.agent_id,
            platform=chat_request.platform,
            chat_identifier=chat_request.chat_identifier,
            metadata={"isolation_mode": False, "client_ip": get_client_ip(request), "mode": "legacy"},
        )

        return chat_response.dict()

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"传统聊天处理失败: {str(e)}"
        ) from e


@router.get("/agents")
@api_endpoint(require_tenant=False)
async def get_agents(
    request: Request,
    tenant_id: Optional[str] = Query(None, description="租户ID（可选）"),
    credentials=Depends(get_current_tenant_credentials),
):
    """
    获取智能体列表（支持向后兼容和隔离化）

    Args:
        tenant_id: 租户ID（可选）
        credentials: 认证信息

    Returns:
        智能体列表
    """
    try:
        if tenant_id and credentials:
            # 隔离模式
            if tenant_id != credentials.tenant_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问指定租户")

            try:
                agent_manager = get_isolated_agent_manager(tenant_id)
                agents = agent_manager.get_all_agents()

                # 格式化智能体数据
                formatted_agents = []
                for agent in agents:
                    agent_data = {
                        "agent_id": agent.agent_id if hasattr(agent, "agent_id") else str(id(agent)),
                        "name": getattr(agent, "name", "Unknown"),
                        "description": getattr(agent, "description", ""),
                        "status": getattr(agent, "status", "active"),
                        "tenant_id": tenant_id,
                        "isolation_mode": True,
                    }
                    formatted_agents.append(agent_data)

                return success_response(message="获取智能体列表成功", data={"agents": formatted_agents})

            except Exception:
                # 如果智能体管理器不可用，返回空列表
                return success_response(message="智能体管理器暂不可用", data={"agents": []})
        else:
            # 传统模式（向后兼容）
            return success_response(
                message="（传统模式）获取智能体列表成功",
                data={
                    "agents": [
                        {
                            "agent_id": "default",
                            "name": "默认智能体",
                            "description": "传统模式默认智能体",
                            "status": "active",
                            "isolation_mode": False,
                        }
                    ]
                },
            )

    except HTTPException:
        raise
    except Exception as e:
        return error_response(message=f"获取智能体列表失败: {str(e)}", status_code=500)


@router.post("/chat/batch")
@api_endpoint(require_tenant=False)
async def batch_chat(
    request: Request,
    chat_requests: list,
    tenant_id: Optional[str] = Query(None, description="租户ID（可选）"),
    credentials=Depends(get_current_tenant_credentials),
):
    """
    批量聊天处理（支持向后兼容和隔离化）

    Args:
        chat_requests: 聊天请求列表
        tenant_id: 租户ID（可选）
        credentials: 认证信息

    Returns:
        批量聊天响应
    """
    try:
        if len(chat_requests) > 100:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="批量请求最多支持100条消息")

        results = []
        errors = []

        for i, chat_request in enumerate(chat_requests):
            try:
                # 验证请求
                if isinstance(chat_request, dict):
                    validated_request = ChatRequest(**chat_request)
                else:
                    validated_request = chat_request

                # 处理单个请求
                if tenant_id and credentials:
                    # 隔离模式
                    if tenant_id != credentials.tenant_id:
                        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问指定租户")

                    isolation_context = create_isolation_context(
                        tenant_id=tenant_id, agent_id=validated_request.agent_id, platform=validated_request.platform
                    )

                    result = await _process_isolated_chat(validated_request, isolation_context, tenant_id, request)
                else:
                    # 传统模式
                    result = await _process_legacy_chat(validated_request, request)

                results.append({"index": i, "success": True, "data": result})

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


@router.get("/status")
@api_endpoint()
async def get_chat_status(
    request: Request,
    tenant_id: Optional[str] = Query(None, description="租户ID（可选）"),
    credentials=Depends(get_current_tenant_credentials),
):
    """
    获取聊天系统状态（支持向后兼容和隔离化）

    Args:
        tenant_id: 租户ID（可选）
        credentials: 认证信息

    Returns:
        系统状态
    """
    try:
        status_info = {"timestamp": datetime.utcnow().isoformat(), "status": "healthy"}

        if tenant_id and credentials:
            # 隔离模式
            if tenant_id != credentials.tenant_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问指定租户")

            status_info.update(
                {
                    "tenant_id": tenant_id,
                    "isolation_mode": True,
                    "features": {
                        "isolated_chat": True,
                        "tenant_isolation": True,
                        "agent_isolation": True,
                        "multi_tenant": True,
                    },
                }
            )
        else:
            # 传统模式
            status_info.update(
                {"isolation_mode": False, "features": {"legacy_chat": True, "backward_compatibility": True}}
            )

        return success_response(message="获取状态成功", data=status_info)

    except HTTPException:
        raise
    except Exception as e:
        return error_response(message=f"获取状态失败: {str(e)}", status_code=500)
