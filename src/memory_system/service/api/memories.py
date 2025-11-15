"""
记忆服务的记忆管理API

提供记忆的CRUD操作、搜索、查询和聚合功能。
"""

import logging
from typing import List, Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from fastapi.responses import JSONResponse

from ..models.schemas import (
    MemoryCreate, MemoryUpdate, MemoryResponse, MemoryListResponse,
    MemorySearch, MemoryQuery, MemoryAggregate, BatchMemoryCreate,
    BatchDeleteRequest, BatchOperationResponse, SuccessResponse
)
from ..services.memory_service import MemoryService
from ..services.search_service import SearchService
from ..services.isolation_service import IsolationService
from ..utils.isolation import get_isolation_context_from_request

logger = logging.getLogger(__name__)

router = APIRouter()


def get_memory_service() -> MemoryService:
    """获取记忆服务实例"""
    return MemoryService()


def get_search_service() -> SearchService:
    """获取搜索服务实例"""
    return SearchService()


def get_isolation_service() -> IsolationService:
    """获取隔离服务实例"""
    return IsolationService()


@router.post("/", response_model=MemoryResponse, summary="添加记忆")
async def add_memory(
    memory_data: MemoryCreate,
    background_tasks: BackgroundTasks,
    request,
    memory_service: MemoryService = Depends(get_memory_service),
    isolation_service: IsolationService = Depends(get_isolation_service)
):
    """
    添加新的记忆

    Args:
        memory_data: 记忆数据
        background_tasks: 后台任务
        request: HTTP请求对象

    Returns:
        创建的记忆信息
    """
    try:
        # 获取隔离上下文
        isolation_context = await get_isolation_context_from_request(request)

        # 验证隔离权限
        await isolation_service.validate_memory_access(
            isolation_context, memory_data.level, memory_data.platform, memory_data.scope_id
        )

        # 创建记忆
        memory = await memory_service.create_memory(
            title=memory_data.title,
            content=memory_data.content,
            level=memory_data.level,
            tenant_id=isolation_context.tenant_id,
            agent_id=isolation_context.agent_id,
            platform=memory_data.platform or isolation_context.platform,
            scope_id=memory_data.scope_id or isolation_context.scope_id,
            tags=memory_data.tags,
            metadata=memory_data.metadata,
            expires_at=memory_data.expires_at
        )

        # 后台任务：更新统计和索引
        background_tasks.add_task(
            memory_service.update_memory_stats,
            isolation_context.tenant_id,
            isolation_context.agent_id
        )

        logger.info(f"成功添加记忆: {memory.id} (租户: {isolation_context.tenant_id})")

        return MemoryResponse(**memory.to_dict())

    except Exception as e:
        logger.error(f"添加记忆失败: {e}")
        raise HTTPException(status_code=500, detail=f"添加记忆失败: {str(e)}")


@router.get("/{memory_id}", response_model=MemoryResponse, summary="获取记忆")
async def get_memory(
    memory_id: UUID,
    request,
    memory_service: MemoryService = Depends(get_memory_service),
    isolation_service: IsolationService = Depends(get_isolation_service)
):
    """
    获取指定ID的记忆

    Args:
        memory_id: 记忆ID
        request: HTTP请求对象

    Returns:
        记忆详细信息
    """
    try:
        # 获取隔离上下文
        isolation_context = await get_isolation_context_from_request(request)

        # 获取记忆
        memory = await memory_service.get_memory(memory_id)

        if not memory:
            raise HTTPException(status_code=404, detail="记忆不存在")

        # 验证隔离权限
        await isolation_service.validate_memory_access(
            isolation_context, memory.level, memory.platform, memory.scope_id, memory_id=memory_id
        )

        # 更新访问统计
        await memory_service.increment_access_count(memory_id)

        logger.info(f"成功获取记忆: {memory_id} (租户: {isolation_context.tenant_id})")

        return MemoryResponse(**memory.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取记忆失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取记忆失败: {str(e)}")


@router.put("/{memory_id}", response_model=MemoryResponse, summary="更新记忆")
async def update_memory(
    memory_id: UUID,
    memory_data: MemoryUpdate,
    background_tasks: BackgroundTasks,
    request,
    memory_service: MemoryService = Depends(get_memory_service),
    isolation_service: IsolationService = Depends(get_isolation_service)
):
    """
    更新指定ID的记忆

    Args:
        memory_id: 记忆ID
        memory_data: 更新数据
        background_tasks: 后台任务
        request: HTTP请求对象

    Returns:
        更新后的记忆信息
    """
    try:
        # 获取隔离上下文
        isolation_context = await get_isolation_context_from_request(request)

        # 检查记忆是否存在
        existing_memory = await memory_service.get_memory(memory_id)
        if not existing_memory:
            raise HTTPException(status_code=404, detail="记忆不存在")

        # 验证隔离权限
        await isolation_service.validate_memory_access(
            isolation_context, existing_memory.level, existing_memory.platform, existing_memory.scope_id, memory_id
        )

        # 更新记忆
        updated_memory = await memory_service.update_memory(
            memory_id=memory_id,
            title=memory_data.title,
            content=memory_data.content,
            tags=memory_data.tags,
            metadata=memory_data.metadata,
            expires_at=memory_data.expires_at,
            status=memory_data.status
        )

        # 后台任务：更新统计和重新生成嵌入
        background_tasks.add_task(
            memory_service.regenerate_embedding,
            memory_id
        )

        logger.info(f"成功更新记忆: {memory_id} (租户: {isolation_context.tenant_id})")

        return MemoryResponse(**updated_memory.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新记忆失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新记忆失败: {str(e)}")


@router.delete("/{memory_id}", response_model=SuccessResponse, summary="删除记忆")
async def delete_memory(
    memory_id: UUID,
    background_tasks: BackgroundTasks,
    request,
    memory_service: MemoryService = Depends(get_memory_service),
    isolation_service: IsolationService = Depends(get_isolation_service)
):
    """
    删除指定ID的记忆

    Args:
        memory_id: 记忆ID
        background_tasks: 后台任务
        request: HTTP请求对象

    Returns:
        删除结果
    """
    try:
        # 获取隔离上下文
        isolation_context = await get_isolation_context_from_request(request)

        # 检查记忆是否存在
        existing_memory = await memory_service.get_memory(memory_id)
        if not existing_memory:
            raise HTTPException(status_code=404, detail="记忆不存在")

        # 验证隔离权限
        await isolation_service.validate_memory_access(
            isolation_context, existing_memory.level, existing_memory.platform, existing_memory.scope_id, memory_id
        )

        # 删除记忆
        success = await memory_service.delete_memory(memory_id)

        if not success:
            raise HTTPException(status_code=500, detail="删除记忆失败")

        # 后台任务：更新统计
        background_tasks.add_task(
            memory_service.update_memory_stats,
            isolation_context.tenant_id,
            isolation_context.agent_id
        )

        logger.info(f"成功删除记忆: {memory_id} (租户: {isolation_context.tenant_id})")

        return SuccessResponse(
            message="记忆删除成功",
            data={"memory_id": str(memory_id)}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除记忆失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除记忆失败: {str(e)}")


@router.post("/search", response_model=MemoryListResponse, summary="搜索记忆")
async def search_memories(
    search_data: MemorySearch,
    request,
    search_service: SearchService = Depends(get_search_service),
    isolation_service: IsolationService = Depends(get_isolation_service)
):
    """
    基于查询文本搜索记忆（支持向量相似度搜索）

    Args:
        search_data: 搜索参数
        request: HTTP请求对象

    Returns:
        搜索结果列表
    """
    try:
        # 获取隔离上下文
        isolation_context = await get_isolation_context_from_request(request)

        # 验证隔离权限
        await isolation_service.validate_memory_access(
            isolation_context, search_data.level, search_data.platform, search_data.scope_id
        )

        # 执行搜索
        result = await search_service.search_memories(
            query=search_data.query,
            tenant_id=isolation_context.tenant_id,
            agent_id=isolation_context.agent_id,
            level=search_data.level,
            platform=search_data.platform or isolation_context.platform,
            scope_id=search_data.scope_id or isolation_context.scope_id,
            tags=search_data.tags,
            limit=search_data.limit,
            offset=search_data.offset,
            similarity_threshold=search_data.similarity_threshold,
            date_from=search_data.date_from,
            date_to=search_data.date_to
        )

        # 转换为响应格式
        memories = [MemoryResponse(**memory.to_dict()) for memory in result["memories"]]

        response = MemoryListResponse(
            items=memories,
            total=result["total"],
            limit=search_data.limit,
            offset=search_data.offset,
            has_more=result["has_more"]
        )

        logger.info(f"搜索记忆完成: 查询='{search_data.query}', 结果={len(memories)}条 (租户: {isolation_context.tenant_id})")

        return response

    except Exception as e:
        logger.error(f"搜索记忆失败: {e}")
        raise HTTPException(status_code=500, detail=f"搜索记忆失败: {str(e)}")


@router.post("/query", response_model=MemoryListResponse, summary="复杂查询记忆")
async def query_memories(
    query_data: MemoryQuery,
    request,
    memory_service: MemoryService = Depends(get_memory_service),
    isolation_service: IsolationService = Depends(get_isolation_service)
):
    """
    基于复杂条件查询记忆

    Args:
        query_data: 查询参数
        request: HTTP请求对象

    Returns:
        查询结果列表
    """
    try:
        # 获取隔离上下文
        isolation_context = await get_isolation_context_from_request(request)

        # 构建查询过滤器（自动添加隔离条件）
        filters = query_data.filters.copy()
        filters.update({
            "tenant_id": isolation_context.tenant_id,
            "agent_id": isolation_context.agent_id,
        })

        # 执行查询
        result = await memory_service.query_memories(
            filters=filters,
            sort_by=query_data.sort_by,
            sort_order=query_data.sort_order,
            limit=query_data.limit,
            offset=query_data.offset
        )

        # 转换为响应格式
        memories = [MemoryResponse(**memory.to_dict()) for memory in result["memories"]]

        response = MemoryListResponse(
            items=memories,
            total=result["total"],
            limit=query_data.limit,
            offset=query_data.offset,
            has_more=result["has_more"]
        )

        logger.info(f"查询记忆完成: 过滤器={filters}, 结果={len(memories)}条 (租户: {isolation_context.tenant_id})")

        return response

    except Exception as e:
        logger.error(f"查询记忆失败: {e}")
        raise HTTPException(status_code=500, detail=f"查询记忆失败: {str(e)}")


@router.post("/aggregate", response_model=SuccessResponse, summary="聚合记忆")
async def aggregate_memories(
    aggregate_data: MemoryAggregate,
    background_tasks: BackgroundTasks,
    request,
    memory_service: MemoryService = Depends(get_memory_service),
    isolation_service: IsolationService = Depends(get_isolation_service)
):
    """
    将记忆从源作用域聚合到目标级别

    Args:
        aggregate_data: 聚合参数
        background_tasks: 后台任务
        request: HTTP请求对象

    Returns:
        聚合结果
    """
    try:
        # 获取隔离上下文
        isolation_context = await get_isolation_context_from_request(request)

        # 验证隔离权限
        await isolation_service.validate_memory_aggregation(
            isolation_context, aggregate_data.source_scopes, aggregate_data.target_level
        )

        # 执行聚合
        result = await memory_service.aggregate_memories(
            source_scopes=aggregate_data.source_scopes,
            target_level=aggregate_data.target_level,
            tenant_id=isolation_context.tenant_id,
            agent_id=isolation_context.agent_id,
            target_platform=aggregate_data.target_platform or isolation_context.platform,
            target_scope_id=aggregate_data.target_scope_id,
            merge_strategy=aggregate_data.merge_strategy
        )

        # 后台任务：更新统计
        background_tasks.add_task(
            memory_service.update_memory_stats,
            isolation_context.tenant_id,
            isolation_context.agent_id
        )

        logger.info(f"记忆聚合完成: 源={aggregate_data.source_scopes}, 目标={aggregate_data.target_level}, "
                   f"聚合数量={result['aggregated_count']} (租户: {isolation_context.tenant_id})")

        return SuccessResponse(
            message="记忆聚合成功",
            data=result
        )

    except Exception as e:
        logger.error(f"聚合记忆失败: {e}")
        raise HTTPException(status_code=500, detail=f"聚合记忆失败: {str(e)}")


@router.post("/batch", response_model=BatchOperationResponse, summary="批量创建记忆")
async def batch_create_memories(
    batch_data: BatchMemoryCreate,
    background_tasks: BackgroundTasks,
    request,
    memory_service: MemoryService = Depends(get_memory_service),
    isolation_service: IsolationService = Depends(get_isolation_service)
):
    """
    批量创建记忆

    Args:
        batch_data: 批量创建数据
        background_tasks: 后台任务
        request: HTTP请求对象

    Returns:
        批量操作结果
    """
    try:
        # 获取隔离上下文
        isolation_context = await get_isolation_context_from_request(request)

        # 验证批量操作权限
        await isolation_service.validate_batch_operation(
            isolation_context, len(batch_data.memories)
        )

        # 执行批量创建
        result = await memory_service.batch_create_memories(
            memories=batch_data.memories,
            tenant_id=isolation_context.tenant_id,
            agent_id=isolation_context.agent_id,
            default_platform=isolation_context.platform,
            default_scope_id=isolation_context.scope_id
        )

        # 后台任务：更新统计
        background_tasks.add_task(
            memory_service.update_memory_stats,
            isolation_context.tenant_id,
            isolation_context.agent_id
        )

        logger.info(f"批量创建记忆完成: 成功={result['successful']}, 失败={result['failed']} (租户: {isolation_context.tenant_id})")

        return BatchOperationResponse(**result)

    except Exception as e:
        logger.error(f"批量创建记忆失败: {e}")
        raise HTTPException(status_code=500, detail=f"批量创建记忆失败: {str(e)}")


@router.delete("/batch", response_model=BatchOperationResponse, summary="批量删除记忆")
async def batch_delete_memories(
    batch_data: BatchDeleteRequest,
    background_tasks: BackgroundTasks,
    request,
    memory_service: MemoryService = Depends(get_memory_service),
    isolation_service: IsolationService = Depends(get_isolation_service)
):
    """
    批量删除记忆

    Args:
        batch_data: 批量删除数据
        background_tasks: 后台任务
        request: HTTP请求对象

    Returns:
        批量操作结果
    """
    try:
        # 获取隔离上下文
        isolation_context = await get_isolation_context_from_request(request)

        # 验证批量操作权限
        await isolation_service.validate_batch_operation(
            isolation_context, len(batch_data.memory_ids)
        )

        # 执行批量删除
        result = await memory_service.batch_delete_memories(
            memory_ids=batch_data.memory_ids,
            tenant_id=isolation_context.tenant_id,
            agent_id=isolation_context.agent_id
        )

        # 后台任务：更新统计
        background_tasks.add_task(
            memory_service.update_memory_stats,
            isolation_context.tenant_id,
            isolation_context.agent_id
        )

        logger.info(f"批量删除记忆完成: 成功={result['successful']}, 失败={result['failed']} (租户: {isolation_context.tenant_id})")

        return BatchOperationResponse(**result)

    except Exception as e:
        logger.error(f"批量删除记忆失败: {e}")
        raise HTTPException(status_code=500, detail=f"批量删除记忆失败: {str(e)}")


# 租户级别的记忆端点
@router.get("/tenant/{tenant_id}/agent/{agent_id}", response_model=MemoryListResponse, summary="获取租户智能体的所有记忆")
async def get_tenant_agent_memories(
    tenant_id: str,
    agent_id: str,
    level: Optional[str] = Query(None, description="记忆级别过滤"),
    platform: Optional[str] = Query(None, description="平台过滤"),
    limit: int = Query(10, ge=1, le=100, description="返回数量限制"),
    offset: int = Query(0, ge=0, description="偏移量"),
    request: Request,
    memory_service: MemoryService = Depends(get_memory_service),
    isolation_service: IsolationService = Depends(get_isolation_service)
):
    """
    获取指定租户和智能体的所有记忆

    Args:
        tenant_id: 租户ID
        agent_id: 智能体ID
        level: 记忆级别过滤
        platform: 平台过滤
        limit: 返回数量限制
        offset: 偏移量
        request: HTTP请求对象

    Returns:
        记忆列表
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
        if level:
            filters["level"] = level
        if platform:
            filters["platform"] = platform

        # 执行查询
        result = await memory_service.query_memories(
            filters=filters,
            sort_by="created_at",
            sort_order="desc",
            limit=limit,
            offset=offset
        )

        # 转换为响应格式
        memories = [MemoryResponse(**memory.to_dict()) for memory in result["memories"]]

        response = MemoryListResponse(
            items=memories,
            total=result["total"],
            limit=limit,
            offset=offset,
            has_more=result["has_more"]
        )

        logger.info(f"获取租户智能体记忆完成: 租户={tenant_id}, 智能体={agent_id}, "
                   f"结果={len(memories)}条")

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取租户智能体记忆失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取记忆失败: {str(e)}")