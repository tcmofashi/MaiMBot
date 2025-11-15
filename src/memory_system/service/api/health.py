"""
记忆服务的健康检查API

提供服务健康状态检查和监控端点。
"""

import logging
import time
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..database.connection import check_database_health, get_connection_pool_stats
from ..cache.redis_client import check_redis_health, get_redis_stats
from ..services.memory_service import MemoryService
from ..services.isolation_service import IsolationService

logger = logging.getLogger(__name__)

router = APIRouter()

# 服务启动时间
SERVICE_START_TIME = time.time()


@router.get("/health", summary="健康检查")
async def health_check(request: Request) -> Dict[str, Any]:
    """
    检查服务的整体健康状态

    Returns:
        健康状态信息，包括数据库、Redis和服务状态
    """
    try:
        # 检查数据库健康状态
        db_health = await check_database_health()
        db_status = "healthy" if db_health.get("status") == "healthy" else "unhealthy"

        # 检查Redis健康状态
        redis_health = await check_redis_health()
        redis_status = "healthy" if redis_health.get("status") == "connected" else "unhealthy"

        # 计算整体状态
        overall_status = "healthy"
        if db_status != "healthy" or redis_status != "healthy":
            overall_status = "unhealthy"

        # 计算运行时间
        uptime = time.time() - SERVICE_START_TIME

        # 获取连接池统计
        db_pool_stats = await get_connection_pool_stats()
        redis_stats = await get_redis_stats()

        response_data = {
            "status": overall_status,
            "version": "1.0.0",
            "timestamp": datetime.utcnow().isoformat(),
            "uptime_seconds": round(uptime, 2),
            "uptime_human": format_uptime(uptime),
            "database": {
                "status": db_status,
                "details": db_health,
                "connection_pool": db_pool_stats,
            },
            "redis": {
                "status": redis_status,
                "details": redis_health,
                "stats": redis_stats,
            },
            "service": {
                "name": "记忆服务",
                "environment": get_environment_info(),
                "host": request.client.host if request.client else "unknown",
            },
        }

        # 如果状态不健康，返回503状态码
        if overall_status != "healthy":
            return JSONResponse(status_code=503, content=response_data)

        return response_data

    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )


@router.get("/health/readiness", summary="就绪检查")
async def readiness_check():
    """
    检查服务是否准备就绪接受请求

    Returns:
        就绪状态信息
    """
    try:
        # 检查关键组件是否就绪
        db_ready = await check_database_readiness()
        redis_ready = await check_redis_readiness()

        is_ready = db_ready and redis_ready

        response = {
            "ready": is_ready,
            "checks": {
                "database": "ready" if db_ready else "not_ready",
                "redis": "ready" if redis_ready else "not_ready",
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

        if not is_ready:
            return JSONResponse(status_code=503, content=response)

        return response

    except Exception as e:
        logger.error(f"就绪检查失败: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "ready": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )


@router.get("/health/liveness", summary="存活检查")
async def liveness_check():
    """
    检查服务是否存活

    Returns:
        存活状态信息
    """
    return {
        "alive": True,
        "timestamp": datetime.utcnow().isoformat(),
        "uptime_seconds": round(time.time() - SERVICE_START_TIME, 2),
    }


@router.get("/health/components", summary="组件状态检查")
async def components_health_check():
    """
    检查各个组件的详细健康状态

    Returns:
        各组件的详细状态信息
    """
    try:
        components = {}

        # 数据库组件
        components["database"] = await get_database_component_status()

        # Redis组件
        components["redis"] = await get_redis_component_status()

        # 记忆服务组件
        components["memory_service"] = await get_memory_service_status()

        # 隔离服务组件
        components["isolation_service"] = await get_isolation_service_status()

        # 计算整体状态
        overall_healthy = all(component.get("healthy", False) for component in components.values())

        return {
            "overall_healthy": overall_healthy,
            "components": components,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"组件状态检查失败: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "overall_healthy": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )


# 辅助函数
async def check_database_readiness() -> bool:
    """检查数据库是否就绪"""
    try:
        db_health = await check_database_health()
        return db_health.get("status") == "healthy"
    except Exception:
        return False


async def check_redis_readiness() -> bool:
    """检查Redis是否就绪"""
    try:
        redis_health = await check_redis_health()
        return redis_health.get("status") == "connected"
    except Exception:
        return False


async def get_database_component_status() -> Dict[str, Any]:
    """获取数据库组件状态"""
    try:
        db_health = await check_database_health()
        pool_stats = await get_connection_pool_stats()

        return {
            "healthy": db_health.get("status") == "healthy",
            "status": db_health.get("status"),
            "details": db_health,
            "connection_pool": pool_stats,
        }
    except Exception as e:
        return {
            "healthy": False,
            "error": str(e),
        }


async def get_redis_component_status() -> Dict[str, Any]:
    """获取Redis组件状态"""
    try:
        redis_health = await check_redis_health()
        redis_stats = await get_redis_stats()

        return {
            "healthy": redis_health.get("status") == "connected",
            "status": redis_health.get("status"),
            "details": redis_health,
            "stats": redis_stats,
        }
    except Exception as e:
        return {
            "healthy": False,
            "error": str(e),
        }


async def get_memory_service_status() -> Dict[str, Any]:
    """获取记忆服务组件状态"""
    try:
        # 执行一个简单的查询来测试记忆服务
        memory_service = MemoryService()
        test_result = await memory_service.health_check()

        return {
            "healthy": test_result.get("status") == "healthy",
            "status": test_result.get("status"),
            "details": test_result,
        }
    except Exception as e:
        return {
            "healthy": False,
            "error": str(e),
        }


async def get_isolation_service_status() -> Dict[str, Any]:
    """获取隔离服务组件状态"""
    try:
        # 测试隔离服务
        isolation_service = IsolationService()
        test_result = await isolation_service.health_check()

        return {
            "healthy": test_result.get("status") == "healthy",
            "status": test_result.get("status"),
            "details": test_result,
        }
    except Exception as e:
        return {
            "healthy": False,
            "error": str(e),
        }


def format_uptime(seconds: float) -> str:
    """格式化运行时间"""
    if seconds < 60:
        return f"{seconds:.1f}秒"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}分钟"
    elif seconds < 86400:
        hours = seconds / 3600
        return f"{hours:.1f}小时"
    else:
        days = seconds / 86400
        return f"{days:.1f}天"


def get_environment_info() -> Dict[str, str]:
    """获取环境信息"""
    import os

    return {
        "environment": os.getenv("ENVIRONMENT", "development"),
        "debug": os.getenv("DEBUG", "false"),
        "log_level": os.getenv("LOG_LEVEL", "INFO"),
    }
