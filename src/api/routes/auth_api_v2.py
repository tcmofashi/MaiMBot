"""
API密钥管理API接口 v2
专注于API密钥解析和权限验证，不再包含用户认证功能
"""

import base64
import time
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.common.database.database_model import (
    AgentApiKeys,
    validate_agent_api_key,
)
from src.common.logger import get_logger
from src.api.utils.response import APIResponse, get_request_id, calculate_execution_time

logger = get_logger(__name__)
router = APIRouter()


class ApiKeyParseRequest(BaseModel):
    """API密钥解析请求"""
    api_key: str


class ApiKeyValidationRequest(BaseModel):
    """API密钥验证请求"""
    api_key: str
    required_permission: Optional[str] = None
    check_rate_limit: bool = True


class ApiKeyPermissionRequest(BaseModel):
    """API密钥权限检查请求"""
    api_key: str
    permission: str


def parse_api_key_format(api_key: str) -> Dict[str, Any]:
    """
    解析API密钥格式

    API密钥格式: mmc_{tenant_id}_{agent_id}_{random_hash}_{version}
    """
    try:
        if not api_key.startswith("mmc_"):
            raise ValueError("API密钥格式错误：前缀无效")

        parts = api_key.split("_")
        if len(parts) != 5:
            raise ValueError("API密钥格式错误：部分数量不正确")

        # 解码Base64部分
        tenant_id = base64.b64decode(parts[1] + "==").decode('utf-8')
        agent_id = base64.b64decode(parts[2]).decode('utf-8')
        random_hash = parts[3]
        version = base64.b64decode(parts[4] + "==").decode('utf-8')

        return {
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "random_hash": random_hash,
            "version": version
        }
    except Exception as e:
        raise ValueError(f"API密钥解析失败: {str(e)}")


@router.post("/parse-api-key")
async def parse_api_key(request_data: ApiKeyParseRequest, request: Request):
    """
    解析API密钥获取基本信息

    无需验证权限，仅解析密钥格式获取租户和Agent信息
    """
    start_time = time.time()
    request_id = get_request_id(request)

    try:
        # 解析API密钥格式
        parsed_info = parse_api_key_format(request_data.api_key)

        logger.info(f"API密钥解析成功: {request_data.api_key[:20]}...")

        return APIResponse.success(
            data={
                "tenant_id": parsed_info["tenant_id"],
                "agent_id": parsed_info["agent_id"],
                "version": parsed_info["version"],
                "format_valid": True
            },
            message="API密钥解析成功",
            request_id=request_id,
            execution_time=calculate_execution_time(start_time)
        )

    except ValueError as e:
        logger.warning(f"API密钥解析失败: {str(e)}")
        return APIResponse.error(
            message="API密钥解析失败",
            error_code="INVALID_API_KEY_FORMAT",
            error_details=str(e),
            request_id=request_id,
            execution_time=calculate_execution_time(start_time)
        )
    except Exception as e:
        logger.error(f"API密钥解析异常: {str(e)}")
        return APIResponse.error(
            message="服务器内部错误",
            error_code="INTERNAL_ERROR",
            error_details="API密钥解析过程中发生异常",
            request_id=request_id,
            execution_time=calculate_execution_time(start_time)
        )


@router.post("/validate-api-key")
async def validate_api_key(request_data: ApiKeyValidationRequest, request: Request):
    """
    验证API密钥的有效性和权限

    检查API密钥是否存在于数据库中，以及是否具有指定权限
    """
    start_time = time.time()
    request_id = get_request_id(request)

    try:
        # 先解析API密钥格式
        parsed_info = parse_api_key_format(request_data.api_key)

        # 从数据库验证API密钥
        api_key_record = validate_agent_api_key(
            request_data.api_key,
            required_permission=request_data.required_permission,
            check_rate_limit=request_data.check_rate_limit
        )

        if not api_key_record:
            return APIResponse.error(
                message="API密钥验证失败",
                error_code="API_KEY_INVALID",
                error_details="API密钥不存在或已失效",
                request_id=request_id,
                execution_time=calculate_execution_time(start_time)
            )

        # 检查权限
        has_permission = True
        if request_data.required_permission:
            permissions = api_key_record.permissions or []
            has_permission = request_data.required_permission in permissions

            if not has_permission:
                return APIResponse.error(
                    message="权限验证失败",
                    error_code="PERMISSION_DENIED",
                    error_details=f"API密钥缺少权限: {request_data.required_permission}",
                    request_id=request_id,
                    execution_time=calculate_execution_time(start_time)
                )

        logger.info(f"API密钥验证成功: {parsed_info['tenant_id']}/{parsed_info['agent_id']}")

        return APIResponse.success(
            data={
                "valid": True,
                "tenant_id": parsed_info["tenant_id"],
                "agent_id": parsed_info["agent_id"],
                "api_key_id": api_key_record.api_key_id,
                "permissions": api_key_record.permissions or [],
                "has_permission": has_permission,
                "status": api_key_record.status
            },
            message="API密钥验证成功",
            request_id=request_id,
            execution_time=calculate_execution_time(start_time)
        )

    except ValueError as e:
        logger.warning(f"API密钥验证失败（格式错误）: {str(e)}")
        return APIResponse.error(
            message="API密钥验证失败",
            error_code="INVALID_API_KEY_FORMAT",
            error_details=str(e),
            request_id=request_id,
            execution_time=calculate_execution_time(start_time)
        )
    except Exception as e:
        logger.error(f"API密钥验证异常: {str(e)}")
        return APIResponse.error(
            message="服务器内部错误",
            error_code="INTERNAL_ERROR",
            error_details="API密钥验证过程中发生异常",
            request_id=request_id,
            execution_time=calculate_execution_time(start_time)
        )


@router.post("/check-permission")
async def check_api_key_permission(request_data: ApiKeyPermissionRequest, request: Request):
    """
    检查API密钥是否具有指定权限

    专门用于权限检查的接口，返回详细的权限信息
    """
    start_time = time.time()
    request_id = get_request_id(request)

    try:
        # 先解析API密钥格式
        parsed_info = parse_api_key_format(request_data.api_key)

        # 从数据库验证API密钥
        api_key_record = validate_agent_api_key(request_data.api_key, check_rate_limit=False)

        if not api_key_record:
            return APIResponse.error(
                message="API密钥无效",
                error_code="API_KEY_INVALID",
                error_details="API密钥不存在或已失效",
                request_id=request_id,
                execution_time=calculate_execution_time(start_time)
            )

        # 检查权限
        permissions = api_key_record.permissions or []
        has_permission = request_data.permission in permissions

        logger.info(f"权限检查完成: {request_data.permission} -> {has_permission}")

        return APIResponse.success(
            data={
                "has_permission": has_permission,
                "permission": request_data.permission,
                "all_permissions": permissions,
                "tenant_id": parsed_info["tenant_id"],
                "agent_id": parsed_info["agent_id"],
                "api_key_status": api_key_record.status
            },
            message="权限检查完成",
            request_id=request_id,
            execution_time=calculate_execution_time(start_time)
        )

    except ValueError as e:
        logger.warning(f"权限检查失败（格式错误）: {str(e)}")
        return APIResponse.error(
            message="权限检查失败",
            error_code="INVALID_API_KEY_FORMAT",
            error_details=str(e),
            request_id=request_id,
            execution_time=calculate_execution_time(start_time)
        )
    except Exception as e:
        logger.error(f"权限检查异常: {str(e)}")
        return APIResponse.error(
            message="服务器内部错误",
            error_code="INTERNAL_ERROR",
            error_details="权限检查过程中发生异常",
            request_id=request_id,
            execution_time=calculate_execution_time(start_time)
        )