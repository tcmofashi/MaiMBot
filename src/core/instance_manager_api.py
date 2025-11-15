"""
实例管理器便捷API接口

提供便捷的函数：`get_isolated_instance()`, `clear_tenant_instances()` 等。
实现实例的批量操作和异步管理，提供实例统计和健康检查功能。

主要功能：
1. 便捷的实例管理API
2. 批量操作支持
3. 异步管理功能
4. 实例统计和健康检查
5. 统一的管理接口
"""

import functools
from typing import Dict, Any, Optional, List, TypeVar
from datetime import datetime
from dataclasses import dataclass
from contextlib import asynccontextmanager
import logging

from .global_instance_manager import get_global_instance_manager
from .instance_lifecycle_manager import get_lifecycle_manager
from .instance_registry import get_instance_registry
from .tenant_resource_manager import get_tenant_resource_manager, ResourceType, QuotaType
from .instance_monitoring import get_instance_monitoring
from src.isolation.isolation_context import IsolationContext

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class InstanceOperationResult:
    """实例操作结果"""

    success: bool
    message: str
    instance_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    error: Optional[Exception] = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class BatchOperationResult:
    """批量操作结果"""

    total_count: int
    success_count: int
    failure_count: int
    results: List[InstanceOperationResult]
    start_time: datetime
    end_time: datetime

    @property
    def duration_seconds(self) -> float:
        return (self.end_time - self.start_time).total_seconds()

    @property
    def success_rate(self) -> float:
        return self.success_count / self.total_count if self.total_count > 0 else 0.0

    @property
    def success(self) -> bool:
        """判断批量操作是否整体成功"""
        return self.success_count >= self.failure_count and self.total_count > 0


class InstanceManagerAPI:
    """
    实例管理器API

    提供统一的高级API接口，整合所有实例管理功能。
    """

    def __init__(self):
        self.global_manager = get_global_instance_manager()
        self.lifecycle_manager = get_lifecycle_manager()
        self.registry = get_instance_registry()
        self.resource_manager = get_tenant_resource_manager()
        self.monitoring = get_instance_monitoring()

    # === 实例获取和管理 ===

    async def get_isolated_instance(
        self,
        instance_type: str,
        tenant_id: str,
        agent_id: str,
        chat_stream_id: Optional[str] = None,
        platform: Optional[str] = None,
        auto_create: bool = True,
        **kwargs,
    ) -> Optional[T]:
        """
        获取隔离的实例

        Args:
            instance_type: 实例类型
            tenant_id: 租户ID
            agent_id: 智能体ID
            chat_stream_id: 聊天流ID
            platform: 平台
            auto_create: 是否自动创建
            **kwargs: 其他参数

        Returns:
            实例对象或None
        """
        try:
            # 检查资源配额
            if not self._check_resource_quota(tenant_id, ResourceType.INSTANCES, 1):
                logger.warning(f"Resource quota exceeded for tenant {tenant_id}")
                return None

            # 获取实例
            instance = self.global_manager.get_isolated_instance(
                instance_type, tenant_id, agent_id, chat_stream_id, platform, **kwargs
            )

            if instance and auto_create:
                # 注册生命周期管理
                instance_id = self._generate_instance_id(instance_type, tenant_id, agent_id, chat_stream_id)

                # 先注册实例到生命周期管理器
                registration_success = self.lifecycle_manager.register_instance(
                    instance_id=instance_id,
                    instance=instance,
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    chat_stream_id=chat_stream_id,
                    platform=platform,
                    instance_type=instance_type,
                )

                if registration_success:
                    # 激活实例生命周期
                    success = await self.lifecycle_manager.activate_instance(instance_id)
                    if not success:
                        logger.warning(f"Failed to activate instance lifecycle: {instance_id}")
                else:
                    logger.warning(f"Failed to register instance: {instance_id}")

                # 注册监控
                self.monitoring.register_instance(instance_id, instance)

            return instance

        except Exception as e:
            logger.error(f"Failed to get isolated instance: {e}")
            return None

    def create_isolation_context(
        self, tenant_id: str, agent_id: str, platform: Optional[str] = None, chat_stream_id: Optional[str] = None
    ) -> IsolationContext:
        """创建隔离上下文"""
        return self.global_manager.create_isolation_context(tenant_id, agent_id, platform, chat_stream_id)

    # === 租户管理 ===

    async def clear_tenant_instances(
        self, tenant_id: str, instance_types: Optional[List[str]] = None, force: bool = False
    ) -> BatchOperationResult:
        """
        清理租户实例

        Args:
            tenant_id: 租户ID
            instance_types: 实例类型列表，None表示所有类型
            force: 是否强制清理

        Returns:
            批量操作结果
        """
        start_time = datetime.now()
        results = []

        try:
            # 获取租户实例
            tenant_instances = self.global_manager.get_tenant_instances(tenant_id)

            # 过滤实例类型
            if instance_types:
                tenant_instances = {
                    itype: instances for itype, instances in tenant_instances.items() if itype in instance_types
                }

            total_count = sum(len(instances) for instances in tenant_instances.values())
            success_count = 0
            failure_count = 0

            # 清理每种类型的实例
            for instance_type, instances in tenant_instances.items():
                for instance_info in instances:
                    try:
                        instance_id = instance_info.instance_id

                        # 清理生命周期
                        await self.lifecycle_manager.cleanup_instance(instance_id, force)

                        # 清理全局管理器
                        cleared = self.global_manager.clear_tenant_instances(tenant_id, instance_type)

                        if cleared > 0:
                            results.append(
                                InstanceOperationResult(
                                    success=True,
                                    message=f"Successfully cleared instance: {instance_id}",
                                    instance_id=instance_id,
                                )
                            )
                            success_count += 1
                        else:
                            results.append(
                                InstanceOperationResult(
                                    success=False,
                                    message=f"Failed to clear instance: {instance_id}",
                                    instance_id=instance_id,
                                )
                            )
                            failure_count += 1

                    except Exception as e:
                        results.append(
                            InstanceOperationResult(
                                success=False,
                                message=f"Error clearing instance: {instance_info.instance_id}",
                                instance_id=instance_info.instance_id,
                                error=e,
                            )
                        )
                        failure_count += 1

            # 清理资源管理器数据
            self.resource_manager.cleanup_tenant_data(tenant_id)

            return BatchOperationResult(
                total_count=total_count,
                success_count=success_count,
                failure_count=failure_count,
                results=results,
                start_time=start_time,
                end_time=datetime.now(),
            )

        except Exception as e:
            return BatchOperationResult(
                total_count=0,
                success_count=0,
                failure_count=1,
                results=[
                    InstanceOperationResult(
                        success=False, message=f"Failed to clear tenant instances: {str(e)}", error=e
                    )
                ],
                start_time=start_time,
                end_time=datetime.now(),
            )

    def get_tenant_summary(self, tenant_id: str) -> Dict[str, Any]:
        """获取租户摘要"""
        summary = {
            "tenant_id": tenant_id,
            "timestamp": datetime.now().isoformat(),
        }

        # 实例信息
        tenant_instances = self.global_manager.get_tenant_instances(tenant_id)
        summary["instance_counts"] = {
            instance_type: len(instances) for instance_type, instances in tenant_instances.items()
        }
        summary["total_instances"] = sum(len(instances) for instances in tenant_instances.values())

        # 资源统计
        resource_stats = self.resource_manager.get_tenant_stats(tenant_id)
        summary["resource_stats"] = {
            "cpu_usage_percent": resource_stats.cpu_usage_percent,
            "memory_usage_mb": resource_stats.memory_usage_mb,
            "memory_limit_mb": resource_stats.memory_limit_mb,
            "active_instances": resource_stats.active_instances,
            "total_requests": resource_stats.total_requests,
            "tokens_used": resource_stats.tokens_used,
            "last_updated": resource_stats.last_updated.isoformat(),
        }

        # 健康状态
        health_info = {}
        for _, instances in tenant_instances.items():
            for instance_info in instances:
                instance_id = instance_info.instance_id
                health = self.monitoring.get_instance_health(instance_id)
                health_info[instance_id] = health.get("overall_health", "unknown")

        summary["health_status"] = {
            "healthy": sum(1 for status in health_info.values() if status == "healthy"),
            "degraded": sum(1 for status in health_info.values() if status == "degraded"),
            "unhealthy": sum(1 for status in health_info.values() if status == "unhealthy"),
            "unknown": sum(1 for status in health_info.values() if status == "unknown"),
        }

        # 告警信息
        alerts = self.resource_manager.get_tenant_alerts(tenant_id, resolved=False)
        summary["active_alerts"] = len(alerts)

        return summary

    # === 批量操作 ===

    async def batch_create_instances(self, instance_configs: List[Dict[str, Any]]) -> BatchOperationResult:
        """
        批量创建实例

        Args:
            instance_configs: 实例配置列表

        Returns:
            批量操作结果
        """
        start_time = datetime.now()
        results = []

        for config in instance_configs:
            try:
                instance = await self.get_isolated_instance(**config)
                if instance:
                    results.append(
                        InstanceOperationResult(
                            success=True, message="Successfully created instance", data={"config": config}
                        )
                    )
                else:
                    results.append(
                        InstanceOperationResult(
                            success=False, message="Failed to create instance", data={"config": config}
                        )
                    )
            except Exception as e:
                results.append(
                    InstanceOperationResult(
                        success=False, message=f"Error creating instance: {str(e)}", data={"config": config}, error=e
                    )
                )

        return BatchOperationResult(
            total_count=len(instance_configs),
            success_count=sum(1 for r in results if r.success),
            failure_count=sum(1 for r in results if not r.success),
            results=results,
            start_time=start_time,
            end_time=datetime.now(),
        )

    async def batch_health_check(
        self, tenant_id: Optional[str] = None, instance_types: Optional[List[str]] = None
    ) -> BatchOperationResult:
        """
        批量健康检查

        Args:
            tenant_id: 租户ID，None表示所有租户
            instance_types: 实例类型列表，None表示所有类型

        Returns:
            批量操作结果
        """
        start_time = datetime.now()
        results = []

        try:
            # 获取要检查的实例
            if tenant_id:
                tenant_instances = self.global_manager.get_tenant_instances(tenant_id)
                instances_to_check = []
                for itype, instances in tenant_instances.items():
                    if instance_types is None or itype in instance_types:
                        instances_to_check.extend(instances)
            else:
                # 获取所有实例
                instances_to_check = []
                # 这里需要从全局管理器获取所有实例的逻辑
                # 简化实现，实际应该遍历所有租户
                pass

            total_count = len(instances_to_check)
            success_count = 0
            failure_count = 0

            # 执行健康检查
            for instance_info in instances_to_check:
                try:
                    instance_id = instance_info.instance_id
                    health = self.monitoring.get_instance_health(instance_id)

                    overall_health = health.get("overall_health", "unknown")
                    is_healthy = overall_health == "healthy"

                    results.append(
                        InstanceOperationResult(
                            success=is_healthy,
                            message=f"Health status: {overall_health}",
                            instance_id=instance_id,
                            data={"health": health},
                        )
                    )

                    if is_healthy:
                        success_count += 1
                    else:
                        failure_count += 1

                except Exception as e:
                    results.append(
                        InstanceOperationResult(
                            success=False,
                            message=f"Health check failed: {str(e)}",
                            instance_id=instance_info.instance_id,
                            error=e,
                        )
                    )
                    failure_count += 1

            return BatchOperationResult(
                total_count=total_count,
                success_count=success_count,
                failure_count=failure_count,
                results=results,
                start_time=start_time,
                end_time=datetime.now(),
            )

        except Exception as e:
            return BatchOperationResult(
                total_count=0,
                success_count=0,
                failure_count=1,
                results=[
                    InstanceOperationResult(success=False, message=f"Batch health check failed: {str(e)}", error=e)
                ],
                start_time=start_time,
                end_time=datetime.now(),
            )

    # === 资源管理 ===

    def setup_tenant_quotas(self, tenant_id: str, quotas: Dict[str, Dict[str, Any]]) -> bool:
        """
        设置租户配额

        Args:
            tenant_id: 租户ID
            quotas: 配额配置

        Returns:
            是否设置成功
        """
        success = True

        for resource_name, quota_config in quotas.items():
            try:
                resource_type = ResourceType(resource_name)
                quota_type = QuotaType(quota_config.get("quota_type", "soft_limit"))
                limit_value = quota_config.get("limit_value", 0)
                warning_threshold = quota_config.get("warning_threshold", 0.8)
                critical_threshold = quota_config.get("critical_threshold", 0.95)

                result = self.resource_manager.set_tenant_quota(
                    tenant_id=tenant_id,
                    resource_type=resource_type,
                    quota_type=quota_type,
                    limit_value=limit_value,
                    warning_threshold=warning_threshold,
                    critical_threshold=critical_threshold,
                )

                if not result:
                    success = False

            except Exception as e:
                logger.error(f"Failed to set quota for {resource_name}: {e}")
                success = False

        return success

    def check_resource_availability(self, tenant_id: str, resource_type: str, required_amount: float) -> Dict[str, Any]:
        """
        检查资源可用性

        Args:
            tenant_id: 租户ID
            resource_type: 资源类型
            required_amount: 需要的资源量

        Returns:
            可用性信息
        """
        try:
            resource_enum = ResourceType(resource_type)
            available, remaining = self.resource_manager.check_resource_availability(
                tenant_id, resource_enum, required_amount
            )

            return {
                "available": available,
                "remaining": remaining,
                "required": required_amount,
                "sufficient": remaining >= required_amount,
                "resource_type": resource_type,
                "tenant_id": tenant_id,
            }

        except Exception as e:
            return {"available": False, "error": str(e), "resource_type": resource_type, "tenant_id": tenant_id}

    # === 统计和监控 ===

    def get_system_stats(self) -> Dict[str, Any]:
        """获取系统统计"""
        stats = {
            "timestamp": datetime.now().isoformat(),
            "global_manager": self.global_manager.get_stats(),
            "lifecycle_manager": self.lifecycle_manager.get_global_stats(),
            "resource_manager": self.resource_manager.get_global_stats(),
            "monitoring": self.monitoring.get_system_overview(),
        }

        return stats

    async def health_check(self) -> Dict[str, Any]:
        """系统健康检查"""
        health_status = {"overall_status": "healthy", "timestamp": datetime.now().isoformat(), "components": {}}

        # 检查各个组件
        components = [
            ("global_manager", lambda: self._check_global_manager_health()),
            ("lifecycle_manager", lambda: self._check_lifecycle_manager_health()),
            ("registry", lambda: self._check_registry_health()),
            ("resource_manager", lambda: self._check_resource_manager_health()),
            ("monitoring", lambda: self._check_monitoring_health()),
        ]

        for name, check_func in components:
            try:
                component_health = check_func()
                health_status["components"][name] = component_health

                if component_health["status"] != "healthy":
                    health_status["overall_status"] = "degraded"
                    if component_health["status"] == "unhealthy":
                        health_status["overall_status"] = "unhealthy"

            except Exception as e:
                health_status["components"][name] = {"status": "unhealthy", "error": str(e)}
                health_status["overall_status"] = "unhealthy"

        return health_status

    def _check_global_manager_health(self) -> Dict[str, Any]:
        """检查全局管理器健康状态"""
        stats = self.global_manager.get_stats()
        return {"status": "healthy", "stats": stats}

    def _check_lifecycle_manager_health(self) -> Dict[str, Any]:
        """检查生命周期管理器健康状态"""
        stats = self.lifecycle_manager.get_global_stats()
        error_rate = stats.get("errors_detected", 0) / max(stats.get("total_instances", 1), 1)

        status = "healthy"
        if error_rate > 0.1:
            status = "degraded"
        if error_rate > 0.3:
            status = "unhealthy"

        return {"status": status, "stats": stats, "error_rate": error_rate}

    def _check_registry_health(self) -> Dict[str, Any]:
        """检查注册中心健康状态"""
        stats = self.registry.get_stats()
        return {"status": "healthy", "stats": stats}

    def _check_resource_manager_health(self) -> Dict[str, Any]:
        """检查资源管理器健康状态"""
        stats = self.resource_manager.get_global_stats()
        alert_count = stats.get("active_alerts", 0)

        status = "healthy"
        if alert_count > 10:
            status = "degraded"
        if alert_count > 50:
            status = "unhealthy"

        return {"status": status, "stats": stats, "active_alerts": alert_count}

    def _check_monitoring_health(self) -> Dict[str, Any]:
        """检查监控系统健康状态"""
        overview = self.monitoring.get_system_overview()
        stats = overview.get("global_stats", {})

        unhealthy_count = stats.get("unhealthy_instances", 0)
        total_count = stats.get("monitored_instances", 1)
        unhealthy_rate = unhealthy_count / total_count

        status = "healthy"
        if unhealthy_rate > 0.1:
            status = "degraded"
        if unhealthy_rate > 0.3:
            status = "unhealthy"

        return {"status": status, "stats": stats, "unhealthy_rate": unhealthy_rate}

    # === 辅助方法 ===

    def _generate_instance_id(
        self, instance_type: str, tenant_id: str, agent_id: str, chat_stream_id: Optional[str] = None
    ) -> str:
        """生成实例ID"""
        if chat_stream_id:
            return f"{instance_type}:{tenant_id}:{agent_id}:{chat_stream_id}"
        else:
            return f"{instance_type}:{tenant_id}:{agent_id}"

    def _check_resource_quota(self, tenant_id: str, resource_type: ResourceType, required_amount: float) -> bool:
        """检查资源配额"""
        available, _ = self.resource_manager.check_resource_availability(tenant_id, resource_type, required_amount)
        return available

    # === 上下文管理器 ===

    @asynccontextmanager
    async def temporary_instance(
        self, instance_type: str, tenant_id: str, agent_id: str, chat_stream_id: Optional[str] = None, **kwargs
    ):
        """临时实例上下文管理器"""
        instance = await self.get_isolated_instance(instance_type, tenant_id, agent_id, chat_stream_id, **kwargs)
        try:
            yield instance
        finally:
            # 自动清理
            if chat_stream_id:
                await self.clear_tenant_instances(tenant_id, [instance_type])

    @asynccontextmanager
    async def isolated_operation(self, tenant_id: str, agent_id: str, platform: Optional[str] = None):
        """隔离操作上下文管理器"""
        isolation_context = self.create_isolation_context(tenant_id, agent_id, platform)
        try:
            yield isolation_context
        finally:
            # 清理资源（如果需要）
            pass


# 全局API实例
instance_manager_api = InstanceManagerAPI()


def get_instance_manager_api() -> InstanceManagerAPI:
    """获取实例管理器API实例"""
    return instance_manager_api


# === 便捷函数 ===


async def get_isolated_instance(
    instance_type: str,
    tenant_id: str,
    agent_id: str,
    chat_stream_id: Optional[str] = None,
    platform: Optional[str] = None,
    **kwargs,
) -> Optional[T]:
    """便捷函数：获取隔离实例"""
    return await instance_manager_api.get_isolated_instance(
        instance_type, tenant_id, agent_id, chat_stream_id, platform, **kwargs
    )


async def clear_tenant_instances(
    tenant_id: str, instance_types: Optional[List[str]] = None, force: bool = False
) -> BatchOperationResult:
    """便捷函数：清理租户实例"""
    return await instance_manager_api.clear_tenant_instances(tenant_id, instance_types, force)


def get_tenant_summary(tenant_id: str) -> Dict[str, Any]:
    """便捷函数：获取租户摘要"""
    return instance_manager_api.get_tenant_summary(tenant_id)


async def batch_create_instances(instance_configs: List[Dict[str, Any]]) -> BatchOperationResult:
    """便捷函数：批量创建实例"""
    return await instance_manager_api.batch_create_instances(instance_configs)


async def batch_health_check(
    tenant_id: Optional[str] = None, instance_types: Optional[List[str]] = None
) -> BatchOperationResult:
    """便捷函数：批量健康检查"""
    return await instance_manager_api.batch_health_check(tenant_id, instance_types)


def setup_tenant_quotas(tenant_id: str, quotas: Dict[str, Dict[str, Any]]) -> bool:
    """便捷函数：设置租户配额"""
    return instance_manager_api.setup_tenant_quotas(tenant_id, quotas)


def get_system_stats() -> Dict[str, Any]:
    """便捷函数：获取系统统计"""
    return instance_manager_api.get_system_stats()


async def system_health_check() -> Dict[str, Any]:
    """便捷函数：系统健康检查"""
    return await instance_manager_api.health_check()


# === 装饰器 ===


def with_isolated_instance(instance_type: str, tenant_id: str, agent_id: str, chat_stream_id: Optional[str] = None):
    """装饰器：自动提供隔离实例"""

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            instance = await get_isolated_instance(instance_type, tenant_id, agent_id, chat_stream_id)
            if instance:
                return await func(instance, *args, **kwargs)
            else:
                raise RuntimeError(f"Failed to get isolated instance: {instance_type}")

        return wrapper

    return decorator


def with_tenant_context(tenant_id: str, agent_id: str):
    """装饰器：自动提供租户上下文"""

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            async with instance_manager_api.isolated_operation(tenant_id, agent_id) as context:
                return await func(context, *args, **kwargs)

        return wrapper

    return decorator


def monitor_instance_performance(instance_id: str):
    """装饰器：监控实例性能"""

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                result = await func(*args, **kwargs)
                success = True
                return result
            except Exception:
                success = False
                raise
            finally:
                # 记录性能指标
                monitoring = get_instance_monitoring()
                span = monitoring.create_span(func.__name__, instance_id)
                if span:
                    monitoring.finish_span(span.span_id, "ok" if success else "error")

        return wrapper

    return decorator
