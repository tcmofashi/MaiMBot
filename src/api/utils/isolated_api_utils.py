"""
隔离化API工具函数

提供便捷的API装饰器、工具函数、参数验证和响应格式化等功能。
支持多租户隔离的API开发。

作者：MaiBot
版本：1.0.0
"""

import json
import time
import uuid
from typing import Optional, Dict, Any, List, Callable, Tuple
from functools import wraps
from datetime import datetime
from pydantic import BaseModel, ValidationError as PydanticValidationError

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

try:
    from src.isolation.isolation_context import IsolationContext, create_isolation_context
except ImportError:
    # 向后兼容性处理
    class IsolationContext:
        def __init__(self, tenant_id: str, agent_id: str, platform: str = "default", chat_stream_id: str = None):
            self.tenant_id = tenant_id
            self.agent_id = agent_id
            self.platform = platform
            self.chat_stream_id = chat_stream_id

    def create_isolation_context(tenant_id: str, agent_id: str, platform: str = "default", chat_stream_id: str = None):
        return IsolationContext(tenant_id, agent_id, platform, chat_stream_id)


class APIResponse(BaseModel):
    """标准API响应格式"""

    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: datetime
    request_id: str
    tenant_id: Optional[str] = None
    execution_time: Optional[float] = None


class ChatRequest(BaseModel):
    """聊天请求模型"""

    message: str
    agent_id: str
    platform: str = "default"
    chat_identifier: Optional[str] = None
    user_id: Optional[str] = None
    group_id: Optional[str] = None
    metadata: Dict[str, Any] = {}


class ChatResponse(BaseModel):
    """聊天响应模型"""

    response: str
    agent_id: str
    platform: str
    chat_identifier: Optional[str] = None
    metadata: Dict[str, Any] = {}
    usage: Optional[Dict[str, Any]] = None


class APIError(Exception):
    """API错误基类"""

    def __init__(self, message: str, status_code: int = 500, error_code: str = None):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code or f"ERROR_{status_code}"
        super().__init__(self.message)


class ValidationError(APIError):
    """参数验证错误"""

    def __init__(self, message: str, field: str = None):
        super().__init__(message, 400, "VALIDATION_ERROR")
        self.field = field


class PermissionError(APIError):
    """权限错误"""

    def __init__(self, message: str, required_permission: str = None):
        super().__init__(message, 403, "PERMISSION_ERROR")
        self.required_permission = required_permission


class TenantNotFoundError(APIError):
    """租户不存在错误"""

    def __init__(self, tenant_id: str):
        super().__init__(f"租户不存在: {tenant_id}", 404, "TENANT_NOT_FOUND")
        self.tenant_id = tenant_id


class AgentNotFoundError(APIError):
    """智能体不存在错误"""

    def __init__(self, agent_id: str):
        super().__init__(f"智能体不存在: {agent_id}", 404, "AGENT_NOT_FOUND")
        self.agent_id = agent_id


def create_api_response(
    success: bool,
    message: str,
    data: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    request_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    execution_time: Optional[float] = None,
) -> APIResponse:
    """创建标准API响应"""
    return APIResponse(
        success=success,
        message=message,
        data=data,
        error=error,
        timestamp=datetime.utcnow(),
        request_id=request_id or str(uuid.uuid4()),
        tenant_id=tenant_id,
        execution_time=execution_time,
    )


def success_response(
    message: str,
    data: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    execution_time: Optional[float] = None,
) -> JSONResponse:
    """成功响应"""
    response = create_api_response(
        success=True,
        message=message,
        data=data,
        request_id=request_id,
        tenant_id=tenant_id,
        execution_time=execution_time,
    )
    return JSONResponse(content=response.dict())


def error_response(
    message: str,
    status_code: int = 500,
    error_code: str = None,
    request_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    execution_time: Optional[float] = None,
) -> JSONResponse:
    """错误响应"""
    response = create_api_response(
        success=False,
        message=message,
        error=message,
        request_id=request_id,
        tenant_id=tenant_id,
        execution_time=execution_time,
    )
    return JSONResponse(content=response.dict(), status_code=status_code)


def handle_api_error(error: Exception, request_id: str = None, tenant_id: str = None) -> JSONResponse:
    """处理API错误"""
    if isinstance(error, APIError):
        return error_response(
            message=error.message,
            status_code=error.status_code,
            error_code=error.error_code,
            request_id=request_id,
            tenant_id=tenant_id,
        )
    elif isinstance(error, HTTPException):
        return error_response(
            message=error.detail, status_code=error.status_code, request_id=request_id, tenant_id=tenant_id
        )
    else:
        return error_response(message="内部服务器错误", status_code=500, request_id=request_id, tenant_id=tenant_id)


def create_isolated_context(
    tenant_id: str, agent_id: str, platform: str = "default", chat_stream_id: str = None
) -> IsolationContext:
    """创建隔离上下文"""
    return create_isolation_context(tenant_id, agent_id, platform, chat_stream_id)


def validate_tenant_permission(tenant_id: str, current_tenant_id: str) -> bool:
    """验证租户权限"""
    return tenant_id == current_tenant_id


def extract_api_parameters(request: Request) -> Dict[str, Any]:
    """提取API参数"""
    params = {}

    # 路径参数
    params.update(request.path_params or {})

    # 查询参数
    params.update(request.query_params or {})

    # 如果有请求体，尝试解析
    if hasattr(request, "_json"):
        params.update(request._json or {})

    return params


def validate_chat_request(request_data: Dict[str, Any]) -> ChatRequest:
    """验证聊天请求"""
    try:
        return ChatRequest(**request_data)
    except PydanticValidationError as e:
        error_details = []
        for error in e.errors():
            field = ".".join(str(x) for x in error["loc"])
            message = error["msg"]
            error_details.append(f"{field}: {message}")

        raise ValidationError(f"参数验证失败: {'; '.join(error_details)}") from e


def validate_isolation_context(tenant_id: str, agent_id: str, platform: str = "default") -> IsolationContext:
    """验证并创建隔离上下文"""
    if not tenant_id:
        raise ValidationError("租户ID不能为空")

    if not agent_id:
        raise ValidationError("智能体ID不能为空")

    return create_isolated_context(tenant_id, agent_id, platform)


def format_api_response(
    success: bool,
    message: str,
    data: Any = None,
    error: str = None,
    request_id: str = None,
    tenant_id: str = None,
    execution_time: float = None,
) -> Dict[str, Any]:
    """格式化API响应"""
    response = {
        "success": success,
        "message": message,
        "timestamp": datetime.utcnow().isoformat(),
        "request_id": request_id or str(uuid.uuid4()),
    }

    if tenant_id:
        response["tenant_id"] = tenant_id

    if data is not None:
        response["data"] = data

    if error:
        response["error"] = error

    if execution_time is not None:
        response["execution_time"] = round(execution_time, 3)

    return response


# 装饰器
def api_endpoint(require_tenant: bool = True, require_agent: bool = True, permissions: List[str] = None):
    """API端点装饰器"""

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            request_id = str(uuid.uuid4())

            try:
                # 提取请求参数
                request = None
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

                if not request:
                    # 从kwargs中查找Request对象
                    request = kwargs.get("request")

                # 验证必需参数
                tenant_id = kwargs.get("tenant_id")
                agent_id = kwargs.get("agent_id")

                if require_tenant and not tenant_id:
                    raise ValidationError("缺少租户ID")

                if require_agent and not agent_id:
                    raise ValidationError("缺少智能体ID")

                # 验证隔离上下文
                if tenant_id and agent_id:
                    isolation_context = validate_isolation_context(
                        tenant_id, agent_id, kwargs.get("platform", "default")
                    )
                    kwargs["isolation_context"] = isolation_context

                # 执行函数
                result = await func(*args, **kwargs)

                # 计算执行时间
                execution_time = time.time() - start_time

                # 格式化响应
                if isinstance(result, tuple):
                    data, message = result
                else:
                    data = result
                    message = "操作成功"

                return format_api_response(
                    success=True,
                    message=message,
                    data=data,
                    request_id=request_id,
                    tenant_id=tenant_id,
                    execution_time=execution_time,
                )

            except Exception as e:
                execution_time = time.time() - start_time

                # 处理错误
                tenant_id = kwargs.get("tenant_id")
                raise handle_api_error(e, request_id, tenant_id) from e

        return wrapper

    return decorator


def tenant_isolated(func: Callable):
    """租户隔离装饰器"""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        tenant_id = kwargs.get("tenant_id")
        if not tenant_id:
            raise ValidationError("缺少租户ID")

        # 添加租户隔离逻辑
        kwargs["is_tenant_isolated"] = True
        return await func(*args, **kwargs)

    return wrapper


def agent_isolated(func: Callable):
    """智能体隔离装饰器"""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        tenant_id = kwargs.get("tenant_id")
        agent_id = kwargs.get("agent_id")

        if not tenant_id or not agent_id:
            raise ValidationError("缺少租户ID或智能体ID")

        # 添加智能体隔离逻辑
        kwargs["is_agent_isolated"] = True
        return await func(*args, **kwargs)

    return wrapper


# 工具函数
def generate_request_id() -> str:
    """生成请求ID"""
    return str(uuid.uuid4())


def get_client_ip(request: Request) -> str:
    """获取客户端IP"""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    return request.client.host if request.client else "unknown"


def log_api_request(
    request: Request,
    tenant_id: str = None,
    agent_id: str = None,
    execution_time: float = None,
    status_code: int = 200,
    error: str = None,
):
    """记录API请求日志"""
    log_data = {
        "method": request.method,
        "url": str(request.url),
        "client_ip": get_client_ip(request),
        "user_agent": request.headers.get("User-Agent"),
        "tenant_id": tenant_id,
        "agent_id": agent_id,
        "execution_time": execution_time,
        "status_code": status_code,
        "error": error,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # 这里应该使用实际的日志系统
    print(f"API Request: {json.dumps(log_data, ensure_ascii=False, indent=2)}")


def sanitize_input(data: Any) -> Any:
    """清理输入数据"""
    if isinstance(data, str):
        # 移除潜在的恶意字符
        dangerous_chars = ["<", ">", '"', "'", "&", "\x00", "\n", "\r", "\t"]
        for char in dangerous_chars:
            data = data.replace(char, "")
        return data.strip()
    elif isinstance(data, dict):
        return {key: sanitize_input(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [sanitize_input(item) for item in data]
    else:
        return data


def validate_pagination_params(page: int = 1, page_size: int = 20, max_page_size: int = 100) -> Tuple[int, int]:
    """验证分页参数"""
    if page < 1:
        page = 1

    if page_size < 1:
        page_size = 20
    elif page_size > max_page_size:
        page_size = max_page_size

    offset = (page - 1) * page_size
    return offset, page_size


def format_list_response(items: List[Any], total: int, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
    """格式化列表响应"""
    total_pages = (total + page_size - 1) // page_size

    return {
        "items": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
    }


# 错误代码常量
class ErrorCode:
    """错误代码常量"""

    SUCCESS = "SUCCESS"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    PERMISSION_ERROR = "PERMISSION_ERROR"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    TENANT_NOT_FOUND = "TENANT_NOT_FOUND"
    AGENT_NOT_FOUND = "AGENT_NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


# 响应消息常量
class ResponseMessage:
    """响应消息常量"""

    SUCCESS = "操作成功"
    CREATED = "创建成功"
    UPDATED = "更新成功"
    DELETED = "删除成功"
    NOT_FOUND = "资源不存在"
    PERMISSION_DENIED = "权限不足"
    INVALID_PARAMETERS = "参数无效"
    INTERNAL_ERROR = "内部服务器错误"
    SERVICE_UNAVAILABLE = "服务暂不可用"
