"""
统一响应格式工具
提供API响应的标准格式
"""

import time
import uuid
from typing import Any, Dict, Optional, List
from fastapi import Request


class APIResponse:
    """API统一响应格式"""

    @staticmethod
    def success(
        data: Any = None,
        message: str = "操作成功",
        request_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        execution_time: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        成功响应格式

        Args:
            data: 响应数据
            message: 响应消息
            request_id: 请求ID
            tenant_id: 租户ID
            execution_time: 执行时间

        Returns:
            Dict: 标准响应格式
        """
        response = {
            "success": True,
            "message": message,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "request_id": request_id or str(uuid.uuid4()),
        }

        if data is not None:
            response["data"] = data

        if tenant_id:
            response["tenant_id"] = tenant_id

        if execution_time is not None:
            response["execution_time"] = execution_time

        return response

    @staticmethod
    def error(
        message: str = "操作失败",
        error_code: str = "INTERNAL_ERROR",
        error_details: Optional[str] = None,
        request_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        execution_time: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        错误响应格式

        Args:
            message: 错误消息
            error_code: 错误码
            error_details: 详细错误信息
            request_id: 请求ID
            tenant_id: 租户ID
            execution_time: 执行时间

        Returns:
            Dict: 标准错误响应格式
        """
        response = {
            "success": False,
            "message": message,
            "error": error_details or message,
            "error_code": error_code,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "request_id": request_id or str(uuid.uuid4()),
        }

        if tenant_id:
            response["tenant_id"] = tenant_id

        if execution_time is not None:
            response["execution_time"] = execution_time

        return response

    @staticmethod
    def paginated(
        items: List[Any],
        total: int,
        page: int = 1,
        page_size: int = 20,
        message: str = "获取数据成功",
        request_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        execution_time: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        分页响应格式

        Args:
            items: 数据项列表
            total: 总数
            page: 当前页码
            page_size: 每页大小
            message: 响应消息
            request_id: 请求ID
            tenant_id: 租户ID
            execution_time: 执行时间

        Returns:
            Dict: 标准分页响应格式
        """
        total_pages = (total + page_size - 1) // page_size

        return APIResponse.success(
            data={
                "items": items,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1,
                }
            },
            message=message,
            request_id=request_id,
            tenant_id=tenant_id,
            execution_time=execution_time
        )


def get_request_id(request: Request) -> str:
    """从请求中获取或生成请求ID"""
    # 优先从header获取
    request_id = request.headers.get("X-Request-ID")
    if request_id:
        return request_id

    # 生成新的请求ID
    return str(uuid.uuid4())


def calculate_execution_time(start_time: float) -> float:
    """计算执行时间"""
    return round(time.time() - start_time, 3)