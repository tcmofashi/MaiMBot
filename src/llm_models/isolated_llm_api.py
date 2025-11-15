"""
隔离化LLM便捷API接口

提供简单易用的函数接口，支持T+A维度的多租户LLM调用。
"""

import time
from functools import wraps
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

from src.common.logger import get_logger
from src.config.api_ada_configs import TaskConfig
from src.isolation.isolation_context import create_isolation_context
from .isolated_llm_client import get_isolated_llm_client, clear_isolated_llm_client
from .isolated_request_manager import (
    get_request_manager,
    submit_isolated_request,
    get_request_info,
    get_request_stats,
    RequestPriority,
)
from .quota_manager import (
    get_quota_manager,
    configure_tenant_quota,
    check_tenant_quota,
    get_tenant_quota_status,
    get_tenant_usage_stats,
    get_quota_alerts,
)

logger = get_logger("isolated_llm_api")


# =============================================================================
# 便捷函数接口
# =============================================================================


async def generate_isolated_response(
    prompt: str,
    tenant_id: str,
    agent_id: str,
    platform: str = "default",
    chat_stream_id: str = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    model_config: Optional[str] = None,
    priority: RequestPriority = RequestPriority.NORMAL,
    timeout: float = 300.0,
    raise_on_error: bool = True,
) -> Tuple[str, Dict[str, Any]]:
    """生成隔离化响应

    Args:
        prompt: 提示词
        tenant_id: 租户ID
        agent_id: 智能体ID
        platform: 平台标识
        chat_stream_id: 聊天流ID
        temperature: 温度参数
        max_tokens: 最大token数
        tools: 工具列表
        model_config: 模型配置名称
        priority: 请求优先级
        timeout: 超时时间
        raise_on_error: 是否在错误时抛出异常

    Returns:
        Tuple[str, Dict[str, Any]]: (响应内容, 元数据)

    Example:
        >>> response, metadata = await generate_isolated_response(
        ...     "你好，请介绍一下自己", tenant_id="tenant1", agent_id="agent1", platform="qq"
        ... )
        >>> print(f"响应: {response}")
        >>> print(f"使用的模型: {metadata['model_name']}")
        >>> print(f"消耗的tokens: {metadata['tokens_used']}")
    """
    start_time = time.time()

    try:
        # 创建隔离上下文
        isolation_context = create_isolation_context(
            tenant_id=tenant_id, agent_id=agent_id, platform=platform, chat_stream_id=chat_stream_id
        )

        # 获取隔离化客户端
        client = get_isolated_llm_client(tenant_id, agent_id, isolation_context)

        # 生成响应
        content, metadata = await client.generate_response(
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            raise_when_empty=raise_on_error,
            isolation_context=isolation_context,
        )

        # 提取元数据
        reasoning_content, model_name, tool_calls = metadata
        execution_time = time.time() - start_time

        result_metadata = {
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "platform": platform,
            "chat_stream_id": chat_stream_id,
            "model_name": model_name,
            "reasoning_content": reasoning_content,
            "tool_calls": tool_calls,
            "execution_time": execution_time,
            "timestamp": datetime.now().isoformat(),
        }

        # 获取使用统计
        usage_stats = client.get_usage_stats()
        result_metadata.update(usage_stats)

        logger.debug(f"生成隔离化响应完成: tenant={tenant_id}, agent={agent_id}, 耗时={execution_time:.2f}s")
        return content, result_metadata

    except Exception as e:
        logger.error(f"生成隔离化响应失败: {e}")
        if raise_on_error:
            raise
        return "", {"error": str(e), "execution_time": time.time() - start_time}


async def generate_isolated_embedding(
    text: str, tenant_id: str, agent_id: str, model_config: Optional[str] = None, platform: str = "default"
) -> Tuple[List[float], Dict[str, Any]]:
    """生成隔离化嵌入向量

    Args:
        text: 输入文本
        tenant_id: 租户ID
        agent_id: 智能体ID
        model_config: 模型配置名称
        platform: 平台标识

    Returns:
        Tuple[List[float], Dict[str, Any]]: (嵌入向量, 元数据)

    Example:
        >>> embedding, metadata = await generate_isolated_embedding(
        ...     "这是一个测试句子", tenant_id="tenant1", agent_id="agent1"
        ... )
        >>> print(f"向量维度: {len(embedding)}")
        >>> print(f"使用的模型: {metadata['model_name']}")
    """
    start_time = time.time()

    try:
        # 创建隔离上下文
        isolation_context = create_isolation_context(tenant_id=tenant_id, agent_id=agent_id, platform=platform)

        # 获取隔离化客户端
        client = get_isolated_llm_client(tenant_id, agent_id, isolation_context)

        # 生成嵌入
        embedding, model_name = await client.get_embedding(embedding_input=text, isolation_context=isolation_context)

        execution_time = time.time() - start_time

        metadata = {
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "platform": platform,
            "model_name": model_name,
            "embedding_dimension": len(embedding),
            "execution_time": execution_time,
            "timestamp": datetime.now().isoformat(),
        }

        logger.debug(f"生成隔离化嵌入完成: tenant={tenant_id}, agent={agent_id}, 耗时={execution_time:.2f}s")
        return embedding, metadata

    except Exception as e:
        logger.error(f"生成隔离化嵌入失败: {e}")
        raise


async def submit_isolated_llm_request(
    request_type: str,
    tenant_id: str,
    agent_id: str,
    model_set: TaskConfig,
    priority: RequestPriority = RequestPriority.NORMAL,
    platform: str = "default",
    chat_stream_id: str = None,
    **kwargs,
) -> str:
    """提交隔离化LLM请求（异步模式）

    Args:
        request_type: 请求类型 ("response", "embedding", "audio")
        tenant_id: 租户ID
        agent_id: 智能体ID
        model_set: 模型配置
        priority: 请求优先级
        platform: 平台标识
        chat_stream_id: 聊天流ID
        **kwargs: 其他请求参数

    Returns:
        str: 请求ID

    Example:
        >>> request_id = await submit_isolated_llm_request(
        ...     request_type="response",
        ...     tenant_id="tenant1",
        ...     agent_id="agent1",
        ...     model_set=model_config,
        ...     priority=RequestPriority.HIGH,
        ... )
        >>> print(f"请求ID: {request_id}")
    """
    return await submit_isolated_request(
        tenant_id=tenant_id,
        agent_id=agent_id,
        model_set=model_set,
        request_type=request_type,
        priority=priority,
        platform=platform,
        chat_stream_id=chat_stream_id,
        **kwargs,
    )


async def get_isolated_request_result(request_id: str) -> Optional[Dict[str, Any]]:
    """获取隔离化请求结果

    Args:
        request_id: 请求ID

    Returns:
        Optional[Dict[str, Any]]: 请求结果，如果请求未完成则返回None

    Example:
        >>> result = await get_isolated_request_result(request_id)
        >>> if result:
        ...     print(f"请求状态: {result['status']}")
        ...     if result["status"] == "completed":
        ...         print(f"响应内容: {result['content']}")
    """
    return await get_request_info(request_id)


# =============================================================================
# 配额管理便捷接口
# =============================================================================


def setup_tenant_quota(
    tenant_id: str,
    daily_token_limit: int = 1000000,
    monthly_cost_limit: float = 100.0,
    daily_request_limit: int = 10000,
    warning_threshold: float = 0.8,
) -> bool:
    """设置租户配额

    Args:
        tenant_id: 租户ID
        daily_token_limit: 每日token限制
        monthly_cost_limit: 每月费用限制
        daily_request_limit: 每日请求限制
        warning_threshold: 警告阈值

    Returns:
        bool: 设置是否成功

    Example:
        >>> success = setup_tenant_quota(tenant_id="tenant1", daily_token_limit=500000, monthly_cost_limit=50.0)
        >>> print(f"配额设置{'成功' if success else '失败'}")
    """
    try:
        configure_tenant_quota(
            tenant_id=tenant_id,
            daily_token_limit=daily_token_limit,
            monthly_cost_limit=monthly_cost_limit,
            daily_request_limit=daily_request_limit,
            warning_threshold=warning_threshold,
        )
        logger.info(f"租户配额设置成功: {tenant_id}")
        return True
    except Exception as e:
        logger.error(f"租户配额设置失败: {e}")
        return False


def check_tenant_quota_status(tenant_id: str, tokens_needed: int = 1000) -> Dict[str, Any]:
    """检查租户配额状态

    Args:
        tenant_id: 租户ID
        tokens_needed: 预计需要的token数

    Returns:
        Dict[str, Any]: 配额状态信息

    Example:
        >>> status = check_tenant_quota_status("tenant1", tokens_needed=2000)
        >>> print(f"配额状态: {status['status']}")
        >>> print(f"Token使用率: {status['daily_tokens']['percentage']:.1%}")
    """
    try:
        # 检查配额
        quota_level = check_tenant_quota(tenant_id, tokens_needed)

        # 获取详细状态
        quota_status = get_tenant_quota_status(tenant_id)

        result = {
            "tenant_id": tenant_id,
            "quota_level": quota_level.value,
            "can_proceed": quota_level.value not in ["exceeded"],
            "quota_status": quota_status,
            "tokens_needed": tokens_needed,
        }

        return result
    except Exception as e:
        logger.error(f"检查租户配额状态失败: {e}")
        return {
            "tenant_id": tenant_id,
            "quota_level": "error",
            "can_proceed": False,
            "error": str(e),
            "tokens_needed": tokens_needed,
        }


def get_tenant_llm_stats(tenant_id: str, days: int = 30) -> Dict[str, Any]:
    """获取租户LLM使用统计

    Args:
        tenant_id: 租户ID
        days: 统计天数

    Returns:
        Dict[str, Any]: 使用统计信息

    Example:
        >>> stats = get_tenant_llm_stats("tenant1", days=7)
        >>> print(f"7天内Token使用量: {stats['monthly_tokens']}")
        >>> print(f"7天内费用: {stats['monthly_cost']:.2f}")
    """
    try:
        # 获取使用统计
        usage_stats = get_tenant_usage_stats(tenant_id, days)

        # 获取配额告警
        alerts = get_quota_alerts(tenant_id, hours=24 * days)

        return {"tenant_id": tenant_id, "usage_stats": usage_stats, "recent_alerts": alerts, "stats_period_days": days}
    except Exception as e:
        logger.error(f"获取租户LLM统计失败: {e}")
        return {"tenant_id": tenant_id, "error": str(e), "stats_period_days": days}


# =============================================================================
# 系统管理便捷接口
# =============================================================================


def get_isolated_llm_system_stats() -> Dict[str, Any]:
    """获取隔离化LLM系统统计

    Returns:
        Dict[str, Any]: 系统统计信息

    Example:
        >>> stats = get_isolated_llm_system_stats()
        >>> print(f"总请求数: {stats['total_requests']}")
        >>> print(f"活跃请求数: {stats['active_requests']}")
        >>> print(f"队列状态: {stats['queue_stats']}")
    """
    try:
        from .isolated_llm_client import get_llm_client_stats

        # 获取请求管理器统计
        request_stats = get_request_stats()

        # 获取客户端统计
        client_stats = get_llm_client_stats()

        # 获取配额管理器统计
        quota_manager = get_quota_manager()
        quota_stats = {
            "configured_tenants": len(quota_manager._tenant_quotas),
            "total_alerts": len(quota_manager._alerts),
        }

        return {
            "request_manager": request_stats,
            "client_manager": client_stats,
            "quota_manager": quota_stats,
            "system_status": "healthy",
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"获取系统统计失败: {e}")
        return {"system_status": "error", "error": str(e), "timestamp": datetime.now().isoformat()}


async def cleanup_isolated_llm_resources(max_age_hours: int = 24):
    """清理隔离化LLM资源

    Args:
        max_age_hours: 最大保留时间（小时）

    Example:
        >>> await cleanup_isolated_llm_resources(max_age_hours=48)
        >>> print("资源清理完成")
    """
    try:
        # 清理请求管理器
        request_manager = get_request_manager()
        request_manager.cleanup_old_requests(max_age_hours)

        # 清理配额管理器
        quota_manager = get_quota_manager()
        quota_manager.cleanup_old_data(max_age_hours)

        # 清理客户端缓存（如果需要）
        # 这里可以添加客户端缓存清理逻辑

        logger.info(f"隔离化LLM资源清理完成，保留时间: {max_age_hours}小时")

    except Exception as e:
        logger.error(f"清理隔离化LLM资源失败: {e}")
        raise


def clear_tenant_llm_resources(tenant_id: str, agent_id: str = None):
    """清理租户LLM资源

    Args:
        tenant_id: 租户ID
        agent_id: 智能体ID（可选，如果不提供则清理整个租户）

    Example:
        >>> clear_tenant_llm_resources("tenant1")  # 清理整个租户
        >>> clear_tenant_llm_resources("tenant1", "agent1")  # 清理特定智能体
    """
    try:
        if agent_id:
            # 清理特定智能体
            clear_isolated_llm_client(tenant_id, agent_id)
            logger.info(f"清理智能体LLM资源: tenant={tenant_id}, agent={agent_id}")
        else:
            # 清理整个租户
            from .isolated_llm_client import clear_tenant_llm_clients

            clear_tenant_llm_clients(tenant_id)
            logger.info(f"清理租户LLM资源: tenant={tenant_id}")

    except Exception as e:
        logger.error(f"清理租户LLM资源失败: {e}")
        raise


# =============================================================================
# 装饰器支持
# =============================================================================


def isolated_llm_call(
    tenant_id: str, agent_id: str, platform: str = "default", priority: RequestPriority = RequestPriority.NORMAL
):
    """隔离化LLM调用装饰器

    Args:
        tenant_id: 租户ID
        agent_id: 智能体ID
        platform: 平台标识
        priority: 请求优先级

    Example:
        >>> @isolated_llm_call(tenant_id="tenant1", agent_id="agent1")
        ... async def chat_with_bot(message: str) -> str:
        ...     return await generate_isolated_response(message, tenant_id="tenant1", agent_id="agent1")[0]
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 检查配额
            quota_status = check_tenant_quota_status(tenant_id)
            if not quota_status.get("can_proceed", False):
                raise Exception(f"租户配额不足: {quota_status.get('quota_level', 'unknown')}")

            # 执行函数
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                logger.error(f"隔离化LLM调用失败: {e}")
                raise

        return wrapper

    return decorator


# =============================================================================
# 健康检查接口
# =============================================================================


async def isolated_llm_health_check() -> Dict[str, Any]:
    """隔离化LLM系统健康检查

    Returns:
        Dict[str, Any]: 健康检查结果

    Example:
        >>> health = await isolated_llm_health_check()
        >>> print(f"系统状态: {health['overall_status']}")
        >>> print(f"检查时间: {health['check_time']}")
    """
    start_time = time.time()
    checks = {}

    try:
        # 检查请求管理器
        request_stats = get_request_stats()
        checks["request_manager"] = {
            "status": "healthy" if request_stats.get("processing", False) else "stopped",
            "active_requests": request_stats.get("active_requests", 0),
            "queue_size": request_stats.get("queue_stats", {}).get("total_requests", 0),
        }

        # 检查配额管理器
        quota_manager = get_quota_manager()
        checks["quota_manager"] = {
            "status": "healthy",
            "configured_tenants": len(quota_manager._tenant_quotas),
            "recent_alerts": len(quota_manager._alerts),
        }

        # 检查客户端管理器
        from .isolated_llm_client import get_llm_client_stats

        client_stats = get_llm_client_stats()
        checks["client_manager"] = {"status": "healthy", "total_clients": client_stats.get("total_clients", 0)}

        # 总体状态
        overall_status = "healthy"
        for _check_name, check_result in checks.items():
            if check_result.get("status") != "healthy":
                overall_status = "degraded"
                break

        check_time = time.time() - start_time

        return {
            "overall_status": overall_status,
            "check_time": check_time,
            "timestamp": datetime.now().isoformat(),
            "checks": checks,
        }

    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        return {
            "overall_status": "unhealthy",
            "check_time": time.time() - start_time,
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
        }


# =============================================================================
# 导出的便捷函数
# =============================================================================

__all__ = [
    # 基础LLM调用
    "generate_isolated_response",
    "generate_isolated_embedding",
    "submit_isolated_llm_request",
    "get_isolated_request_result",
    # 配额管理
    "setup_tenant_quota",
    "check_tenant_quota_status",
    "get_tenant_llm_stats",
    # 系统管理
    "get_isolated_llm_system_stats",
    "cleanup_isolated_llm_resources",
    "clear_tenant_llm_resources",
    # 装饰器
    "isolated_llm_call",
    # 健康检查
    "isolated_llm_health_check",
]

# 版本信息
__version__ = "1.0.0"
__author__ = "MaiBot Team"
__description__ = "隔离化LLM API接口 - 支持多租户的LLM调用便捷接口"
