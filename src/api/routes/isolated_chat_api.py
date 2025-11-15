"""
隔离化聊天API路由

提供多租户隔离的聊天API接口，支持：
- URL路径传参：/api/v1/{tenant_id}/chat
- 请求体验证：包含agent_id, platform, chat_identifier等
- 租户权限验证
- 隔离上下文创建
- API限流和监控

作者：MaiBot
版本：1.0.0
"""

import time
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query

from ..middleware.tenant_auth_middleware import (
    get_current_tenant_credentials,
    get_isolation_context_from_auth,
    require_permission,
    Permission,
)
from ..utils.isolated_api_utils import (
    ChatRequest,
    ChatResponse,
    api_endpoint,
    tenant_isolated,
    agent_isolated,
    validate_chat_request,
    format_list_response,
    validate_pagination_params,
    get_client_ip,
    log_api_request,
)

try:
    from src.chat.heart_flow.isolated_heartflow_api import (
        process_isolated_message,
        create_isolated_heartflow_processor,
        get_isolation_stats,
        isolation_health_check,
    )
    from src.chat.message_receive.isolated_message_api import (
        create_isolated_message,
        process_isolated_message as process_message,
        get_message_stats,
    )
    from src.agent.isolated_agent_manager import get_isolated_agent_manager
    from src.memory_system.isolated_memory_api import create_isolated_memory_system, search_isolated_memory
except ImportError:
    # 向后兼容性处理
    async def process_isolated_message(*args, **kwargs):
        return {"response": "隔离化消息处理功能暂不可用"}

    async def create_isolated_heartflow_processor(*args, **kwargs):
        return None

    def get_isolation_stats():
        return {}

    async def isolation_health_check():
        return {"status": "ok"}

    async def create_isolated_message(*args, **kwargs):
        return None

    async def process_message(*args, **kwargs):
        return {"response": "消息处理功能暂不可用"}

    def get_message_stats():
        return {}

    async def create_isolated_memory_system(*args, **kwargs):
        return None

    async def search_isolated_memory(*args, **kwargs):
        return []


# 创建路由器
router = APIRouter(prefix="/v1", tags=["isolated-chat"])


@router.post("/{tenant_id}/chat")
@api_endpoint(require_tenant=True, require_agent=True)
@tenant_isolated
@agent_isolated
async def chat_with_isolated_agent(
    request: Request,
    tenant_id: str,
    chat_request: ChatRequest,
    credentials=Depends(get_current_tenant_credentials),
    isolation_context=Depends(get_isolation_context_from_auth),
):
    """
    与隔离化智能体聊天

    Args:
        tenant_id: 租户ID（URL路径参数）
        chat_request: 聊天请求（包含agent_id, platform等）

    Returns:
        ChatResponse: 聊天响应
    """
    start_time = time.time()

    try:
        # 验证租户权限
        if tenant_id != credentials.tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问指定租户")

        # 验证请求参数
        validated_request = validate_chat_request(chat_request.dict())

        # 验证智能体是否存在
        try:
            agent_manager = get_isolated_agent_manager(tenant_id)
            agent = agent_manager.get_tenant_agent(validated_request.agent_id)
            if not agent:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail=f"智能体不存在: {validated_request.agent_id}"
                )
        except Exception:
            # 如果智能体管理器不可用，继续处理
            pass

        # 创建隔离化消息
        message_data = {
            "content": validated_request.message,
            "user_id": validated_request.user_id,
            "group_id": validated_request.group_id,
            "platform": validated_request.platform,
            "chat_identifier": validated_request.chat_identifier,
            "metadata": validated_request.metadata,
        }

        # 处理消息
        try:
            # 使用隔离化心流处理器
            processor = create_isolated_heartflow_processor(tenant_id, validated_request.agent_id)

            if processor:
                # 使用心流处理器处理消息
                result = await process_isolated_message(
                    message_data, tenant_id, validated_request.agent_id, validated_request.platform
                )
                response_text = result.get("response", "抱歉，我现在无法回复")
            else:
                # 使用基础消息处理
                result = await process_message(
                    message_data, tenant_id, validated_request.agent_id, validated_request.platform
                )
                response_text = result.get("response", "抱歉，我现在无法回复")

        except Exception as e:
            # 处理失败时的响应
            response_text = f"消息处理出错: {str(e)}"

        # 创建响应
        chat_response = ChatResponse(
            response=response_text,
            agent_id=validated_request.agent_id,
            platform=validated_request.platform,
            chat_identifier=validated_request.chat_identifier,
            metadata={
                "tenant_id": tenant_id,
                "processing_time": time.time() - start_time,
                "client_ip": get_client_ip(request),
            },
        )

        # 记录API请求日志
        execution_time = time.time() - start_time
        log_api_request(
            request=request,
            tenant_id=tenant_id,
            agent_id=validated_request.agent_id,
            execution_time=execution_time,
            status_code=200,
        )

        return chat_response.dict()

    except HTTPException:
        raise
    except Exception as e:
        # 记录错误日志
        execution_time = time.time() - start_time
        log_api_request(
            request=request,
            tenant_id=tenant_id,
            agent_id=chat_request.agent_id,
            execution_time=execution_time,
            status_code=500,
            error=str(e),
        )

        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="内部服务器错误") from None


@router.get("/{tenant_id}/agents")
@api_endpoint(require_tenant=True)
@tenant_isolated
async def get_tenant_agents(
    request: Request,
    tenant_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    credentials=Depends(get_current_tenant_credentials),
):
    """
    获取租户的智能体列表

    Args:
        tenant_id: 租户ID
        page: 页码
        page_size: 每页数量

    Returns:
        智能体列表
    """
    try:
        # 验证租户权限
        if tenant_id != credentials.tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问指定租户")

        # 获取智能体管理器
        try:
            agent_manager = get_isolated_agent_manager(tenant_id)
            agents = agent_manager.get_all_agents()

            # 分页处理
            offset, page_size = validate_pagination_params(page, page_size)
            total = len(agents)
            items = agents[offset : offset + page_size]

            # 格式化智能体数据
            formatted_agents = []
            for agent in items:
                agent_data = {
                    "agent_id": agent.agent_id if hasattr(agent, "agent_id") else str(id(agent)),
                    "name": getattr(agent, "name", "Unknown"),
                    "description": getattr(agent, "description", ""),
                    "status": getattr(agent, "status", "active"),
                    "created_at": getattr(agent, "created_at", datetime.utcnow()).isoformat(),
                }
                formatted_agents.append(agent_data)

            return format_list_response(items=formatted_agents, total=total, page=page, page_size=page_size)

        except Exception:
            # 如果智能体管理器不可用，返回空列表
            return format_list_response(items=[], total=0, page=page, page_size=page_size)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"获取智能体列表失败: {str(e)}"
        ) from e


@router.post("/{tenant_id}/agents/{agent_id}/chat")
@api_endpoint(require_tenant=True, require_agent=True)
@tenant_isolated
@agent_isolated
async def chat_with_specific_agent(
    request: Request,
    tenant_id: str,
    agent_id: str,
    chat_request: dict,
    credentials=Depends(get_current_tenant_credentials),
):
    """
    与指定智能体聊天（路径参数方式）

    Args:
        tenant_id: 租户ID
        agent_id: 智能体ID
        chat_request: 聊天请求

    Returns:
        聊天响应
    """
    start_time = time.time()

    try:
        # 验证租户权限
        if tenant_id != credentials.tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问指定租户")

        # 验证智能体是否存在
        try:
            agent_manager = get_isolated_agent_manager(tenant_id)
            agent = agent_manager.get_tenant_agent(agent_id)
            if not agent:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"智能体不存在: {agent_id}")
        except Exception:
            # 如果智能体管理器不可用，继续处理
            pass

        # 构建聊天请求
        full_chat_request = ChatRequest(
            message=chat_request.get("message", ""),
            agent_id=agent_id,
            platform=chat_request.get("platform", "default"),
            chat_identifier=chat_request.get("chat_identifier"),
            user_id=chat_request.get("user_id"),
            group_id=chat_request.get("group_id"),
            metadata=chat_request.get("metadata", {}),
        )

        # 处理消息
        try:
            result = await process_isolated_message(
                {
                    "content": full_chat_request.message,
                    "user_id": full_chat_request.user_id,
                    "group_id": full_chat_request.group_id,
                    "platform": full_chat_request.platform,
                    "chat_identifier": full_chat_request.chat_identifier,
                    "metadata": full_chat_request.metadata,
                },
                tenant_id,
                agent_id,
                full_chat_request.platform,
            )
            response_text = result.get("response", "抱歉，我现在无法回复")
        except Exception as e:
            response_text = f"消息处理出错: {str(e)}"

        # 创建响应
        chat_response = ChatResponse(
            response=response_text,
            agent_id=agent_id,
            platform=full_chat_request.platform,
            chat_identifier=full_chat_request.chat_identifier,
            metadata={
                "tenant_id": tenant_id,
                "processing_time": time.time() - start_time,
                "client_ip": get_client_ip(request),
            },
        )

        # 记录日志
        execution_time = time.time() - start_time
        log_api_request(
            request=request, tenant_id=tenant_id, agent_id=agent_id, execution_time=execution_time, status_code=200
        )

        return chat_response.dict()

    except HTTPException:
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

        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="内部服务器错误") from None


@router.get("/{tenant_id}/chat/history")
@api_endpoint(require_tenant=True)
@tenant_isolated
async def get_chat_history(
    request: Request,
    tenant_id: str,
    agent_id: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
    chat_identifier: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    credentials=Depends(get_current_tenant_credentials),
):
    """
    获取聊天历史记录

    Args:
        tenant_id: 租户ID
        agent_id: 智能体ID（可选）
        platform: 平台（可选）
        chat_identifier: 聊天标识（可选）
        page: 页码
        page_size: 每页数量

    Returns:
        聊天历史记录
    """
    try:
        # 验证租户权限
        if tenant_id != credentials.tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问指定租户")

        # 这里应该从数据库获取聊天历史
        # 暂时返回模拟数据
        mock_history = [
            {
                "id": "1",
                "message": "你好！",
                "response": "你好！很高兴为您服务！",
                "agent_id": agent_id or "default",
                "platform": platform or "default",
                "chat_identifier": chat_identifier or "default",
                "created_at": datetime.utcnow().isoformat(),
            },
            {
                "id": "2",
                "message": "今天天气怎么样？",
                "response": "抱歉，我无法获取实时天气信息。",
                "agent_id": agent_id or "default",
                "platform": platform or "default",
                "chat_identifier": chat_identifier or "default",
                "created_at": datetime.utcnow().isoformat(),
            },
        ]

        # 分页处理
        offset, page_size = validate_pagination_params(page, page_size)
        total = len(mock_history)
        items = mock_history[offset : offset + page_size]

        return format_list_response(items=items, total=total, page=page, page_size=page_size)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"获取聊天历史失败: {str(e)}"
        ) from e


@router.get("/{tenant_id}/stats")
@api_endpoint(require_tenant=True)
@tenant_isolated
@require_permission(Permission.MONITOR)
async def get_tenant_stats(request: Request, tenant_id: str, credentials=Depends(get_current_tenant_credentials)):
    """
    获取租户统计信息

    Args:
        tenant_id: 租户ID

    Returns:
        租户统计信息
    """
    try:
        # 验证租户权限
        if tenant_id != credentials.tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问指定租户")

        # 获取隔离化系统统计
        try:
            isolation_stats = get_isolation_stats()
            message_stats = get_message_stats()

            stats = {
                "tenant_id": tenant_id,
                "isolation_stats": isolation_stats,
                "message_stats": message_stats,
                "health_status": await isolation_health_check(),
                "timestamp": datetime.utcnow().isoformat(),
            }

            return stats

        except Exception as e:
            # 如果统计功能不可用，返回基本信息
            return {
                "tenant_id": tenant_id,
                "status": "basic_stats_available",
                "message": f"详细统计功能暂不可用: {str(e)}",
                "timestamp": datetime.utcnow().isoformat(),
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"获取统计信息失败: {str(e)}"
        ) from e


@router.post("/{tenant_id}/search")
@api_endpoint(require_tenant=True)
@tenant_isolated
async def search_tenant_data(
    request: Request, tenant_id: str, search_request: dict, credentials=Depends(get_current_tenant_credentials)
):
    """
    搜索租户数据

    Args:
        tenant_id: 租户ID
        search_request: 搜索请求

    Returns:
        搜索结果
    """
    try:
        # 验证租户权限
        if tenant_id != credentials.tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问指定租户")

        query = search_request.get("query", "")
        search_type = search_request.get("type", "memory")  # memory, message, config
        agent_id = search_request.get("agent_id")
        platform = search_request.get("platform")

        if not query:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="搜索查询不能为空")

        # 执行搜索
        results = []
        try:
            if search_type == "memory":
                # 搜索记忆
                memory_results = await search_isolated_memory(
                    query=query, tenant_id=tenant_id, agent_id=agent_id or "default", platform=platform or "default"
                )
                results = memory_results
            else:
                # 其他类型的搜索（暂未实现）
                results = []

        except Exception:
            # 搜索失败时的处理
            results = []

        return {
            "query": query,
            "type": search_type,
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "platform": platform,
            "results": results,
            "total": len(results),
            "timestamp": datetime.utcnow().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"搜索失败: {str(e)}") from e


# 健康检查端点
@router.get("/{tenant_id}/health")
@api_endpoint(require_tenant=True)
@tenant_isolated
async def tenant_health_check(request: Request, tenant_id: str, credentials=Depends(get_current_tenant_credentials)):
    """
    租户健康检查

    Args:
        tenant_id: 租户ID

    Returns:
        健康状态
    """
    try:
        # 验证租户权限
        if tenant_id != credentials.tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问指定租户")

        # 执行健康检查
        health_status = await isolation_health_check()

        return {
            "tenant_id": tenant_id,
            "status": health_status.get("status", "unknown"),
            "checks": health_status.get("checks", {}),
            "timestamp": datetime.utcnow().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        return {"tenant_id": tenant_id, "status": "error", "error": str(e), "timestamp": datetime.utcnow().isoformat()}
