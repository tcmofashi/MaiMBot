"""
记忆服务的系统管理API

提供系统统计、维护任务和管理功能。
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query
from fastapi.responses import JSONResponse

from ..models.schemas import (
    SystemStatsResponse, MaintenanceRequest, MaintenanceResponse,
    HealthCheckResponse
)
from ..services.memory_service import MemoryService
from ..services.search_service import SearchService
from ..services.isolation_service import IsolationService
from ..utils.isolation import get_isolation_context_from_request
from ..database.connection import get_connection_pool_stats
from ..cache.redis_client import get_redis_stats

logger = logging.getLogger(__name__)

router = APIRouter()

# 维护任务状态存储
_maintenance_tasks: Dict[str, Dict[str, Any]] = {}


def get_memory_service() -> MemoryService:
    """获取记忆服务实例"""
    return MemoryService()


def get_search_service() -> SearchService:
    """获取搜索服务实例"""
    return SearchService()


def get_isolation_service() -> IsolationService:
    """获取隔离服务实例"""
    return IsolationService()


@router.get("/stats", response_model=SystemStatsResponse, summary="获取系统统计信息")
async def get_system_stats(
    request,
    memory_service: MemoryService = Depends(get_memory_service)
):
    """
    获取系统的详细统计信息

    Args:
        request: HTTP请求对象
        memory_service: 记忆服务实例

    Returns:
        系统统计信息
    """
    try:
        # 获取隔离上下文
        isolation_context = await get_isolation_context_from_request(request)

        # 获取基本统计
        stats = await memory_service.get_system_stats()

        # 获取按级别统计的记忆数量
        memory_by_level = await memory_service.get_memory_stats_by_level(
            isolation_context.tenant_id,
            isolation_context.agent_id
        )

        # 获取最近活动
        recent_activity = await memory_service.get_recent_activity(
            hours=24,
            tenant_id=isolation_context.tenant_id
        )

        # 获取存储使用情况
        storage_usage = await memory_service.get_storage_usage(
            tenant_id=isolation_context.tenant_id,
            agent_id=isolation_context.agent_id
        )

        # 获取连接池统计
        db_pool_stats = await get_connection_pool_stats()
        redis_stats = await get_redis_stats()

        response = SystemStatsResponse(
            total_memories=stats.get("total_memories", 0),
            total_conflicts=stats.get("total_conflicts", 0),
            active_tenants=stats.get("active_tenants", 0),
            memory_by_level=memory_by_level,
            recent_activity=recent_activity,
            storage_usage={
                "database": storage_usage,
                "redis": redis_stats,
                "connection_pool": db_pool_stats,
            }
        )

        logger.info(f"获取系统统计完成 (租户: {isolation_context.tenant_id})")

        return response

    except Exception as e:
        logger.error(f"获取系统统计失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取系统统计失败: {str(e)}")


@router.get("/health", response_model=HealthCheckResponse, summary="详细健康检查")
async def detailed_health_check():
    """
    获取详细的系统健康检查信息

    Returns:
        详细的健康检查结果
    """
    try:
        from ..api.health import (
            check_database_health, check_redis_health,
            get_database_component_status, get_redis_component_status,
            get_memory_service_status, get_isolation_service_status,
            format_uptime, get_environment_info
        )

        # 检查各组件健康状态
        db_health = await check_database_health()
        redis_health = await check_redis_health()
        db_component = await get_database_component_status()
        redis_component = await get_redis_component_status()
        memory_service_status = await get_memory_service_status()
        isolation_service_status = await get_isolation_service_status()

        # 计算整体状态
        overall_status = "healthy"
        if not all([
            db_component.get("healthy", False),
            redis_component.get("healthy", False),
            memory_service_status.get("healthy", False),
            isolation_service_status.get("healthy", False)
        ]):
            overall_status = "unhealthy"

        # 获取环境信息
        env_info = get_environment_info()

        response = HealthCheckResponse(
            status=overall_status,
            version="1.0.0",
            database=db_health,
            redis=redis_health,
            uptime=0.0,  # 这里可以从启动时间计算
            timestamp=datetime.utcnow(),
        )

        # 扩展响应以包含更多详细信息
        response_dict = response.dict()
        response_dict.update({
            "components": {
                "database": db_component,
                "redis": redis_component,
                "memory_service": memory_service_status,
                "isolation_service": isolation_service_status,
            },
            "environment": env_info,
        })

        return response_dict

    except Exception as e:
        logger.error(f"详细健康检查失败: {e}")
        raise HTTPException(status_code=500, detail=f"健康检查失败: {str(e)}")


@router.post("/maintenance/cleanup", response_model=MaintenanceResponse, summary="清理过期数据")
async def cleanup_expired_data(
    background_tasks: BackgroundTasks,
    dry_run: bool = Query(False, description="是否试运行"),
    older_than_days: int = Query(30, description="清理多少天前的数据"),
    request: Request,
    memory_service: MemoryService = Depends(get_memory_service)
):
    """
    清理过期的记忆和冲突数据

    Args:
        background_tasks: 后台任务
        dry_run: 是否试运行
        older_than_days: 清理多少天前的数据
        request: HTTP请求对象
        memory_service: 记忆服务实例

    Returns:
        维护任务结果
    """
    try:
        # 获取隔离上下文
        isolation_context = await get_isolation_context_from_request(request)

        # 验证管理员权限
        await isolation_service.validate_admin_access(isolation_context)

        # 创建任务ID
        task_id = str(uuid4())

        # 记录任务开始
        _maintenance_tasks[task_id] = {
            "task_id": task_id,
            "task_type": "cleanup",
            "status": "running",
            "message": "清理任务开始",
            "started_at": datetime.utcnow(),
            "parameters": {
                "dry_run": dry_run,
                "older_than_days": older_than_days,
                "tenant_id": isolation_context.tenant_id,
            }
        }

        # 启动后台任务
        if dry_run:
            background_tasks.add_task(
                _run_cleanup_dry_run,
                task_id,
                older_than_days,
                isolation_context.tenant_id,
                isolation_context.agent_id,
                memory_service
            )
        else:
            background_tasks.add_task(
                _run_cleanup_task,
                task_id,
                older_than_days,
                isolation_context.tenant_id,
                isolation_context.agent_id,
                memory_service
            )

        logger.info(f"启动清理任务: {task_id} (租户: {isolation_context.tenant_id}, 试运行: {dry_run})")

        return MaintenanceResponse(
            task_id=task_id,
            status="running",
            message="清理任务已启动",
            started_at=_maintenance_tasks[task_id]["started_at"]
        )

    except Exception as e:
        logger.error(f"启动清理任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"启动清理任务失败: {str(e)}")


@router.post("/maintenance/backup", response_model=MaintenanceResponse, summary="数据备份")
async def backup_data(
    background_tasks: BackgroundTasks,
    include_embeddings: bool = Query(True, description="是否包含嵌入数据"),
    request: Request,
    memory_service: MemoryService = Depends(get_memory_service)
):
    """
    备份记忆和冲突数据

    Args:
        background_tasks: 后台任务
        include_embeddings: 是否包含嵌入数据
        request: HTTP请求对象
        memory_service: 记忆服务实例

    Returns:
        维护任务结果
    """
    try:
        # 获取隔离上下文
        isolation_context = await get_isolation_context_from_request(request)

        # 验证管理员权限
        await isolation_context.validate_admin_access(isolation_context)

        # 创建任务ID
        task_id = str(uuid4())

        # 记录任务开始
        _maintenance_tasks[task_id] = {
            "task_id": task_id,
            "task_type": "backup",
            "status": "running",
            "message": "备份任务开始",
            "started_at": datetime.utcnow(),
            "parameters": {
                "include_embeddings": include_embeddings,
                "tenant_id": isolation_context.tenant_id,
                "agent_id": isolation_context.agent_id,
            }
        }

        # 启动后台任务
        background_tasks.add_task(
            _run_backup_task,
            task_id,
            include_embeddings,
            isolation_context.tenant_id,
            isolation_context.agent_id,
            memory_service
        )

        logger.info(f"启动备份任务: {task_id} (租户: {isolation_context.tenant_id})")

        return MaintenanceResponse(
            task_id=task_id,
            status="running",
            message="备份任务已启动",
            started_at=_maintenance_tasks[task_id]["started_at"]
        )

    except Exception as e:
        logger.error(f"启动备份任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"启动备份任务失败: {str(e)}")


@router.post("/maintenance/optimize", response_model=MaintenanceResponse, summary="数据库优化")
async def optimize_database(
    background_tasks: BackgroundTasks,
    analyze_only: bool = Query(False, description="仅分析而不执行优化"),
    request: Request,
    memory_service: MemoryService = Depends(get_memory_service)
):
    """
    优化数据库性能

    Args:
        background_tasks: 后台任务
        analyze_only: 仅分析而不执行优化
        request: HTTP请求对象
        memory_service: 记忆服务实例

    Returns:
        维护任务结果
    """
    try:
        # 获取隔离上下文
        isolation_context = await get_isolation_context_from_request(request)

        # 验证管理员权限
        await isolation_context.validate_admin_access(isolation_context)

        # 创建任务ID
        task_id = str(uuid4())

        # 记录任务开始
        _maintenance_tasks[task_id] = {
            "task_id": task_id,
            "task_type": "optimize",
            "status": "running",
            "message": "优化任务开始",
            "started_at": datetime.utcnow(),
            "parameters": {
                "analyze_only": analyze_only,
            }
        }

        # 启动后台任务
        background_tasks.add_task(
            _run_optimize_task,
            task_id,
            analyze_only,
            memory_service
        )

        logger.info(f"启动优化任务: {task_id} (分析模式: {analyze_only})")

        return MaintenanceResponse(
            task_id=task_id,
            status="running",
            message="优化任务已启动",
            started_at=_maintenance_tasks[task_id]["started_at"]
        )

    except Exception as e:
        logger.error(f"启动优化任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"启动优化任务失败: {str(e)}")


@router.get("/maintenance/{task_id}", response_model=MaintenanceResponse, summary="获取维护任务状态")
async def get_maintenance_task_status(task_id: str):
    """
    获取指定维护任务的状态

    Args:
        task_id: 任务ID

    Returns:
        任务状态信息
    """
    try:
        if task_id not in _maintenance_tasks:
            raise HTTPException(status_code=404, detail="任务不存在")

        task = _maintenance_tasks[task_id]

        response = MaintenanceResponse(
            task_id=task["task_id"],
            status=task["status"],
            message=task["message"],
            started_at=task["started_at"],
            completed_at=task.get("completed_at"),
            result=task.get("result")
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取维护任务状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取任务状态失败: {str(e)}")


@router.get("/maintenance/tasks", summary="获取维护任务列表")
async def list_maintenance_tasks():
    """
    获取所有维护任务的状态列表

    Returns:
        任务列表
    """
    try:
        tasks = []
        for task_id, task in _maintenance_tasks.items():
            tasks.append({
                "task_id": task_id,
                "task_type": task["task_type"],
                "status": task["status"],
                "message": task["message"],
                "started_at": task["started_at"].isoformat(),
                "completed_at": task.get("completed_at", {}).isoformat() if task.get("completed_at") else None,
                "parameters": task.get("parameters", {}),
            })

        # 按开始时间倒序排列
        tasks.sort(key=lambda x: x["started_at"], reverse=True)

        return {"tasks": tasks, "total": len(tasks)}

    except Exception as e:
        logger.error(f"获取维护任务列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取任务列表失败: {str(e)}")


@router.delete("/maintenance/tasks/{task_id}", summary="删除维护任务记录")
async def delete_maintenance_task(task_id: str):
    """
    删除指定维护任务的记录

    Args:
        task_id: 任务ID

    Returns:
        删除结果
    """
    try:
        if task_id not in _maintenance_tasks:
            raise HTTPException(status_code=404, detail="任务不存在")

        # 检查任务是否已完成
        task = _maintenance_tasks[task_id]
        if task["status"] == "running":
            raise HTTPException(status_code=400, detail="无法删除运行中的任务")

        # 删除任务记录
        del _maintenance_tasks[task_id]

        logger.info(f"删除维护任务记录: {task_id}")

        return {"message": "任务记录删除成功"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除维护任务记录失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除任务记录失败: {str(e)}")


# 后台任务函数
async def _run_cleanup_dry_run(
    task_id: str,
    older_than_days: int,
    tenant_id: str,
    agent_id: str,
    memory_service: MemoryService
):
    """执行清理试运行任务"""
    try:
        # 更新任务状态
        _maintenance_tasks[task_id]["message"] = "正在分析待清理数据..."

        # 分析过期数据
        cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)

        # 统计过期记忆
        expired_memories = await memory_service.count_expired_memories(
            tenant_id=tenant_id,
            agent_id=agent_id,
            cutoff_date=cutoff_date
        )

        # 统计过期冲突
        expired_conflicts = await memory_service.count_expired_conflicts(
            tenant_id=tenant_id,
            agent_id=agent_id,
            cutoff_date=cutoff_date
        )

        # 更新任务完成状态
        _maintenance_tasks[task_id].update({
            "status": "completed",
            "message": "清理分析完成",
            "completed_at": datetime.utcnow(),
            "result": {
                "dry_run": True,
                "expired_memories": expired_memories,
                "expired_conflicts": expired_conflicts,
                "total_items": expired_memories + expired_conflicts,
                "cutoff_date": cutoff_date.isoformat(),
            }
        })

        logger.info(f"清理试运行任务完成: {task_id}, 待清理项目: {expired_memories + expired_conflicts}")

    except Exception as e:
        _maintenance_tasks[task_id].update({
            "status": "failed",
            "message": f"清理试运行失败: {str(e)}",
            "completed_at": datetime.utcnow(),
        })
        logger.error(f"清理试运行任务失败: {task_id}, 错误: {e}")


async def _run_cleanup_task(
    task_id: str,
    older_than_days: int,
    tenant_id: str,
    agent_id: str,
    memory_service: MemoryService
):
    """执行实际清理任务"""
    try:
        # 更新任务状态
        _maintenance_tasks[task_id]["message"] = "正在清理过期数据..."

        cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)

        # 清理过期记忆
        deleted_memories = await memory_service.delete_expired_memories(
            tenant_id=tenant_id,
            agent_id=agent_id,
            cutoff_date=cutoff_date
        )

        # 清理过期冲突
        deleted_conflicts = await memory_service.delete_expired_conflicts(
            tenant_id=tenant_id,
            agent_id=agent_id,
            cutoff_date=cutoff_date
        )

        # 更新任务完成状态
        _maintenance_tasks[task_id].update({
            "status": "completed",
            "message": "数据清理完成",
            "completed_at": datetime.utcnow(),
            "result": {
                "dry_run": False,
                "deleted_memories": deleted_memories,
                "deleted_conflicts": deleted_conflicts,
                "total_deleted": deleted_memories + deleted_conflicts,
                "cutoff_date": cutoff_date.isoformat(),
            }
        })

        logger.info(f"清理任务完成: {task_id}, 删除项目: {deleted_memories + deleted_conflicts}")

    except Exception as e:
        _maintenance_tasks[task_id].update({
            "status": "failed",
            "message": f"数据清理失败: {str(e)}",
            "completed_at": datetime.utcnow(),
        })
        logger.error(f"清理任务失败: {task_id}, 错误: {e}")


async def _run_backup_task(
    task_id: str,
    include_embeddings: bool,
    tenant_id: str,
    agent_id: str,
    memory_service: MemoryService
):
    """执行数据备份任务"""
    try:
        # 更新任务状态
        _maintenance_tasks[task_id]["message"] = "正在备份数据..."

        # 执行备份
        backup_result = await memory_service.backup_data(
            tenant_id=tenant_id,
            agent_id=agent_id,
            include_embeddings=include_embeddings
        )

        # 更新任务完成状态
        _maintenance_tasks[task_id].update({
            "status": "completed",
            "message": "数据备份完成",
            "completed_at": datetime.utcnow(),
            "result": backup_result
        })

        logger.info(f"备份任务完成: {task_id}")

    except Exception as e:
        _maintenance_tasks[task_id].update({
            "status": "failed",
            "message": f"数据备份失败: {str(e)}",
            "completed_at": datetime.utcnow(),
        })
        logger.error(f"备份任务失败: {task_id}, 错误: {e}")


async def _run_optimize_task(
    task_id: str,
    analyze_only: bool,
    memory_service: MemoryService
):
    """执行数据库优化任务"""
    try:
        # 更新任务状态
        _maintenance_tasks[task_id]["message"] = "正在优化数据库..."

        # 执行优化
        optimize_result = await memory_service.optimize_database(analyze_only=analyze_only)

        # 更新任务完成状态
        _maintenance_tasks[task_id].update({
            "status": "completed",
            "message": "数据库优化完成" if not analyze_only else "数据库分析完成",
            "completed_at": datetime.utcnow(),
            "result": optimize_result
        })

        logger.info(f"优化任务完成: {task_id}, 分析模式: {analyze_only}")

    except Exception as e:
        _maintenance_tasks[task_id].update({
            "status": "failed",
            "message": f"数据库优化失败: {str(e)}",
            "completed_at": datetime.utcnow(),
        })
        logger.error(f"优化任务失败: {task_id}, 错误: {e}")