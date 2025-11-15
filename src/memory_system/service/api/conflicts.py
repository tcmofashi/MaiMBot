"""
记忆服务的冲突跟踪API

提供冲突记录的创建、查询、更新和删除功能。
"""

import logging
from typing import List, Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from fastapi.responses import JSONResponse

from ..models.schemas import (
    ConflictCreate, ConflictUpdate, ConflictResponse, SuccessResponse
)
from ..services.memory_service import MemoryService
from ..services.isolation_service import IsolationService
from ..utils.isolation import get_isolation_context_from_request

logger = logging.getLogger(__name__)

router = APIRouter()


def get_memory_service() -> MemoryService:
    """获取记忆服务实例"""
    return MemoryService()


def get_isolation_service() -> IsolationService:
    """获取隔离服务实例"""
    return IsolationService()


@router.post("/", response_model=ConflictResponse, summary="创建冲突记录")
async def create_conflict(
    conflict_data: ConflictCreate,
    background_tasks: BackgroundTasks,
    request,
    memory_service: MemoryService = Depends(get_memory_service),
    isolation_service: IsolationService = Depends(get_isolation_service)
):
    """
    创建新的冲突记录

    Args:
        conflict_data: 冲突数据
        background_tasks: 后台任务
        request: HTTP请求对象

    Returns:
        创建的冲突记录信息
    """
    try:
        # 获取隔离上下文
        isolation_context = await get_isolation_context_from_request(request)

        # 验证隔离权限
        await isolation_service.validate_conflict_access(
            isolation_context, conflict_data.platform, conflict_data.chat_id
        )

        # 创建冲突记录
        conflict = await memory_service.create_conflict(
            title=conflict_data.title,
            context=conflict_data.context,
            tenant_id=isolation_context.tenant_id,
            agent_id=isolation_context.agent_id,
            platform=conflict_data.platform or isolation_context.platform,
            scope_id=isolation_context.scope_id,
            chat_id=conflict_data.chat_id,
            start_following=conflict_data.start_following
        )

        # 如果需要跟踪，添加到后台任务
        if conflict_data.start_following:
            background_tasks.add_task(
                memory_service.start_conflict_tracking,
                conflict.id
            )

        logger.info(f"成功创建冲突记录: {conflict.id} (租户: {isolation_context.tenant_id})")

        return ConflictResponse(**conflict.to_dict())

    except Exception as e:
        logger.error(f"创建冲突记录失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建冲突记录失败: {str(e)}")


@router.get("/{conflict_id}", response_model=ConflictResponse, summary="获取冲突记录")
async def get_conflict(
    conflict_id: UUID,
    request,
    memory_service: MemoryService = Depends(get_memory_service),
    isolation_service: IsolationService = Depends(get_isolation_service)
):
    """
    获取指定ID的冲突记录

    Args:
        conflict_id: 冲突ID
        request: HTTP请求对象

    Returns:
        冲突记录详细信息
    """
    try:
        # 获取隔离上下文
        isolation_context = await get_isolation_context_from_request(request)

        # 获取冲突记录
        conflict = await memory_service.get_conflict(conflict_id)

        if not conflict:
            raise HTTPException(status_code=404, detail="冲突记录不存在")

        # 验证隔离权限
        await isolation_service.validate_conflict_access(
            isolation_context, conflict.platform, conflict.chat_id, conflict_id
        )

        logger.info(f"成功获取冲突记录: {conflict_id} (租户: {isolation_context.tenant_id})")

        return ConflictResponse(**conflict.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取冲突记录失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取冲突记录失败: {str(e)}")


@router.put("/{conflict_id}", response_model=ConflictResponse, summary="更新冲突记录")
async def update_conflict(
    conflict_id: UUID,
    conflict_data: ConflictUpdate,
    background_tasks: BackgroundTasks,
    request,
    memory_service: MemoryService = Depends(get_memory_service),
    isolation_service: IsolationService = Depends(get_isolation_service)
):
    """
    更新指定ID的冲突记录

    Args:
        conflict_id: 冲突ID
        conflict_data: 更新数据
        background_tasks: 后台任务
        request: HTTP请求对象

    Returns:
        更新后的冲突记录信息
    """
    try:
        # 获取隔离上下文
        isolation_context = await get_isolation_context_from_request(request)

        # 检查冲突记录是否存在
        existing_conflict = await memory_service.get_conflict(conflict_id)
        if not existing_conflict:
            raise HTTPException(status_code=404, detail="冲突记录不存在")

        # 验证隔离权限
        await isolation_service.validate_conflict_access(
            isolation_context, existing_conflict.platform, existing_conflict.chat_id, conflict_id
        )

        # 更新冲突记录
        updated_conflict = await memory_service.update_conflict(
            conflict_id=conflict_id,
            title=conflict_data.title,
            context=conflict_data.context,
            start_following=conflict_data.start_following,
            resolved=conflict_data.resolved
        )

        # 如果状态变化，处理相应的后台任务
        if conflict_data.start_following != existing_conflict.start_following:
            if conflict_data.start_following:
                background_tasks.add_task(
                    memory_service.start_conflict_tracking,
                    conflict_id
                )
            else:
                background_tasks.add_task(
                    memory_service.stop_conflict_tracking,
                    conflict_id
                )

        if conflict_data.resolved and not existing_conflict.resolved:
            background_tasks.add_task(
                memory_service.resolve_conflict,
                conflict_id
            )

        logger.info(f"成功更新冲突记录: {conflict_id} (租户: {isolation_context.tenant_id})")

        return ConflictResponse(**updated_conflict.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新冲突记录失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新冲突记录失败: {str(e)}")


@router.delete("/{conflict_id}", response_model=SuccessResponse, summary="删除冲突记录")
async def delete_conflict(
    conflict_id: UUID,
    background_tasks: BackgroundTasks,
    request,
    memory_service: MemoryService = Depends(get_memory_service),
    isolation_service: IsolationService = Depends(get_isolation_service)
):
    """
    删除指定ID的冲突记录

    Args:
        conflict_id: 冲突ID
        background_tasks: 后台任务
        request: HTTP请求对象

    Returns:
        删除结果
    """
    try:
        # 获取隔离上下文
        isolation_context = await get_isolation_context_from_request(request)

        # 检查冲突记录是否存在
        existing_conflict = await memory_service.get_conflict(conflict_id)
        if not existing_conflict:
            raise HTTPException(status_code=404, detail="冲突记录不存在")

        # 验证隔离权限
        await isolation_service.validate_conflict_access(
            isolation_context, existing_conflict.platform, existing_conflict.chat_id, conflict_id
        )

        # 停止跟踪（如果正在跟踪）
        if existing_conflict.start_following:
            background_tasks.add_task(
                memory_service.stop_conflict_tracking,
                conflict_id
            )

        # 删除冲突记录
        success = await memory_service.delete_conflict(conflict_id)

        if not success:
            raise HTTPException(status_code=500, detail="删除冲突记录失败")

        logger.info(f"成功删除冲突记录: {conflict_id} (租户: {isolation_context.tenant_id})")

        return SuccessResponse(
            message="冲突记录删除成功",
            data={"conflict_id": str(conflict_id)}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除冲突记录失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除冲突记录失败: {str(e)}")


@router.get("/", response_model=List[ConflictResponse], summary="查询冲突记录列表")
async def list_conflicts(
    request,
    resolved: Optional[bool] = Query(None, description="是否已解决过滤"),
    following: Optional[bool] = Query(None, description="是否跟踪中过滤"),
    platform: Optional[str] = Query(None, description="平台过滤"),
    chat_id: Optional[str] = Query(None, description="聊天ID过滤"),
    limit: int = Query(10, ge=1, le=100, description="返回数量限制"),
    offset: int = Query(0, ge=0, description="偏移量"),
    memory_service: MemoryService = Depends(get_memory_service),
    isolation_service: IsolationService = Depends(get_isolation_service)
):
    """
    查询冲突记录列表

    Args:
        request: HTTP请求对象
        resolved: 是否已解决过滤
        following: 是否跟踪中过滤
        platform: 平台过滤
        chat_id: 聊天ID过滤
        limit: 返回数量限制
        offset: 偏移量

    Returns:
        冲突记录列表
    """
    try:
        # 获取隔离上下文
        isolation_context = await get_isolation_context_from_request(request)

        # 构建查询过滤器（自动添加隔离条件）
        filters = {
            "tenant_id": isolation_context.tenant_id,
            "agent_id": isolation_context.agent_id,
        }
        if resolved is not None:
            filters["resolved"] = resolved
        if following is not None:
            filters["start_following"] = following
        if platform:
            filters["platform"] = platform
        if chat_id:
            filters["chat_id"] = chat_id

        # 执行查询
        conflicts = await memory_service.list_conflicts(
            filters=filters,
            limit=limit,
            offset=offset
        )

        # 转换为响应格式
        conflict_responses = [ConflictResponse(**conflict.to_dict()) for conflict in conflicts]

        logger.info(f"查询冲突记录完成: 过滤器={filters}, 结果={len(conflict_responses)}条 "
                   f"(租户: {isolation_context.tenant_id})")

        return conflict_responses

    except Exception as e:
        logger.error(f"查询冲突记录失败: {e}")
        raise HTTPException(status_code=500, detail=f"查询冲突记录失败: {str(e)}")


@router.post("/{conflict_id}/resolve", response_model=ConflictResponse, summary="解决冲突")
async def resolve_conflict(
    conflict_id: UUID,
    background_tasks: BackgroundTasks,
    request,
    memory_service: MemoryService = Depends(get_memory_service),
    isolation_service: IsolationService = Depends(get_isolation_service)
):
    """
    标记冲突为已解决

    Args:
        conflict_id: 冲突ID
        background_tasks: 后台任务
        request: HTTP请求对象

    Returns:
        更新后的冲突记录
    """
    try:
        # 获取隔离上下文
        isolation_context = await get_isolation_context_from_request(request)

        # 检查冲突记录是否存在
        existing_conflict = await memory_service.get_conflict(conflict_id)
        if not existing_conflict:
            raise HTTPException(status_code=404, detail="冲突记录不存在")

        # 验证隔离权限
        await isolation_service.validate_conflict_access(
            isolation_context, existing_conflict.platform, existing_conflict.chat_id, conflict_id
        )

        # 解决冲突
        resolved_conflict = await memory_service.resolve_conflict(conflict_id)

        # 后台任务：停止跟踪，清理相关资源
        background_tasks.add_task(
            memory_service.stop_conflict_tracking,
            conflict_id
        )
        background_tasks.add_task(
            memory_service.cleanup_conflict_resources,
            conflict_id
        )

        logger.info(f"成功解决冲突: {conflict_id} (租户: {isolation_context.tenant_id})")

        return ConflictResponse(**resolved_conflict.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"解决冲突失败: {e}")
        raise HTTPException(status_code=500, detail=f"解决冲突失败: {str(e)}")


@router.post("/{conflict_id}/follow", response_model=ConflictResponse, summary="开始跟踪冲突")
async def start_following_conflict(
    conflict_id: UUID,
    background_tasks: BackgroundTasks,
    request,
    memory_service: MemoryService = Depends(get_memory_service),
    isolation_service: IsolationService = Depends(get_isolation_service)
):
    """
    开始跟踪指定冲突

    Args:
        conflict_id: 冲突ID
        background_tasks: 后台任务
        request: HTTP请求对象

    Returns:
        更新后的冲突记录
    """
    try:
        # 获取隔离上下文
        isolation_context = await get_isolation_context_from_request(request)

        # 检查冲突记录是否存在
        existing_conflict = await memory_service.get_conflict(conflict_id)
        if not existing_conflict:
            raise HTTPException(status_code=404, detail="冲突记录不存在")

        # 验证隔离权限
        await isolation_service.validate_conflict_access(
            isolation_context, existing_conflict.platform, existing_conflict.chat_id, conflict_id
        )

        # 开始跟踪
        updated_conflict = await memory_service.start_conflict_tracking(conflict_id)

        # 后台任务：设置跟踪逻辑
        background_tasks.add_task(
            memory_service.setup_conflict_monitoring,
            conflict_id
        )

        logger.info(f"成功开始跟踪冲突: {conflict_id} (租户: {isolation_context.tenant_id})")

        return ConflictResponse(**updated_conflict.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"开始跟踪冲突失败: {e}")
        raise HTTPException(status_code=500, detail=f"开始跟踪冲突失败: {str(e)}")


@router.post("/{conflict_id}/unfollow", response_model=ConflictResponse, summary="停止跟踪冲突")
async def stop_following_conflict(
    conflict_id: UUID,
    background_tasks: BackgroundTasks,
    request,
    memory_service: MemoryService = Depends(get_memory_service),
    isolation_service: IsolationService = Depends(get_isolation_service)
):
    """
    停止跟踪指定冲突

    Args:
        conflict_id: 冲突ID
        background_tasks: 后台任务
        request: HTTP请求对象

    Returns:
        更新后的冲突记录
    """
    try:
        # 获取隔离上下文
        isolation_context = await get_isolation_context_from_request(request)

        # 检查冲突记录是否存在
        existing_conflict = await memory_service.get_conflict(conflict_id)
        if not existing_conflict:
            raise HTTPException(status_code=404, detail="冲突记录不存在")

        # 验证隔离权限
        await isolation_service.validate_conflict_access(
            isolation_context, existing_conflict.platform, existing_conflict.chat_id, conflict_id
        )

        # 停止跟踪
        updated_conflict = await memory_service.stop_conflict_tracking(conflict_id)

        # 后台任务：清理跟踪资源
        background_tasks.add_task(
            memory_service.cleanup_conflict_monitoring,
            conflict_id
        )

        logger.info(f"成功停止跟踪冲突: {conflict_id} (租户: {isolation_context.tenant_id})")

        return ConflictResponse(**updated_conflict.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"停止跟踪冲突失败: {e}")
        raise HTTPException(status_code=500, detail=f"停止跟踪冲突失败: {str(e)}")


@router.get("/{conflict_id}/related-memories", response_model=List[dict], summary="获取冲突相关记忆")
async def get_conflict_related_memories(
    conflict_id: UUID,
    request,
    memory_service: MemoryService = Depends(get_memory_service),
    isolation_service: IsolationService = Depends(get_isolation_service)
):
    """
    获取与指定冲突相关的记忆

    Args:
        conflict_id: 冲突ID
        request: HTTP请求对象

    Returns:
        相关记忆列表
    """
    try:
        # 获取隔离上下文
        isolation_context = await get_isolation_context_from_request(request)

        # 检查冲突记录是否存在并验证权限
        existing_conflict = await memory_service.get_conflict(conflict_id)
        if not existing_conflict:
            raise HTTPException(status_code=404, detail="冲突记录不存在")

        await isolation_service.validate_conflict_access(
            isolation_context, existing_conflict.platform, existing_conflict.chat_id, conflict_id
        )

        # 获取相关记忆
        related_memories = await memory_service.get_conflict_related_memories(conflict_id)

        logger.info(f"获取冲突相关记忆完成: 冲突={conflict_id}, 相关记忆={len(related_memories)}条 "
                   f"(租户: {isolation_context.tenant_id})")

        return related_memories

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取冲突相关记忆失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取冲突相关记忆失败: {str(e)}")


# 租户级别的冲突端点
@router.get("/tenant/{tenant_id}/agent/{agent_id}", response_model=List[ConflictResponse], summary="获取租户智能体的所有冲突")
async def get_tenant_agent_conflicts(
    tenant_id: str,
    agent_id: str,
    resolved: Optional[bool] = Query(None, description="是否已解决过滤"),
    following: Optional[bool] = Query(None, description="是否跟踪中过滤"),
    limit: int = Query(10, ge=1, le=100, description="返回数量限制"),
    offset: int = Query(0, ge=0, description="偏移量"),
    request: Request,
    memory_service: MemoryService = Depends(get_memory_service),
    isolation_service: IsolationService = Depends(get_isolation_service)
):
    """
    获取指定租户和智能体的所有冲突记录

    Args:
        tenant_id: 租户ID
        agent_id: 智能体ID
        resolved: 是否已解决过滤
        following: 是否跟踪中过滤
        limit: 返回数量限制
        offset: 偏移量
        request: HTTP请求对象

    Returns:
        冲突记录列表
    """
    try:
        # 获取当前用户的隔离上下文
        current_context = await get_isolation_context_from_request(request)

        # 验证访问权限（只有同租户用户可以访问）
        await isolation_service.validate_tenant_access(current_context, tenant_id)

        # 构建查询过滤器
        filters = {
            "tenant_id": tenant_id,
            "agent_id": agent_id,
        }
        if resolved is not None:
            filters["resolved"] = resolved
        if following is not None:
            filters["start_following"] = following

        # 执行查询
        conflicts = await memory_service.list_conflicts(
            filters=filters,
            limit=limit,
            offset=offset
        )

        # 转换为响应格式
        conflict_responses = [ConflictResponse(**conflict.to_dict()) for conflict in conflicts]

        logger.info(f"获取租户智能体冲突记录完成: 租户={tenant_id}, 智能体={agent_id}, "
                   f"结果={len(conflict_responses)}条")

        return conflict_responses

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取租户智能体冲突记录失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取冲突记录失败: {str(e)}")