"""
Core模块 - 实例管理器核心组件

提供完整的多租户实例管理功能，包括：
- 全局实例管理器
- 实例生命周期管理
- 实例注册和发现
- 租户资源管理
- 实例监控和诊断
- 便捷API接口
"""

from .global_instance_manager import (
    GlobalInstanceManager,
    get_global_instance_manager,
    get_isolated_instance,
    clear_tenant_instances,
    get_tenant_instances,
    get_instance_stats,
)

from .instance_lifecycle_manager import (
    InstanceLifecycleManager,
    get_lifecycle_manager,
    InstanceState,
    LifecycleEvent,
    activate_instance,
    deactivate_instance,
    cleanup_instance,
    get_instance_state,
)

from .instance_registry import (
    InstanceRegistry,
    get_instance_registry,
    InstanceDefinition,
    InstanceScope,
    DependencyType,
    InstanceFactory,
    register_instance,
    get_instance,
    inject,
)

from .tenant_resource_manager import (
    TenantResourceManager,
    get_tenant_resource_manager,
    ResourceQuota,
    ResourceType,
    QuotaType,
    AlertLevel,
    TenantResourceStats,
    set_tenant_quota,
    record_resource_usage,
    get_tenant_stats,
)

from .instance_monitoring import (
    InstanceMonitoringSystem,
    get_instance_monitoring,
    InstanceMonitor,
    HealthStatus,
    MetricType,
    SeverityLevel,
    register_instance_monitoring,
    create_span,
)

from .instance_manager_api import (
    InstanceManagerAPI,
    get_instance_manager_api,
    InstanceOperationResult,
    BatchOperationResult,
    get_isolated_instance,
    clear_tenant_instances,
    get_tenant_summary,
    batch_create_instances,
    batch_health_check,
    setup_tenant_quotas,
    get_system_stats,
    system_health_check,
    with_isolated_instance,
    with_tenant_context,
    monitor_instance_performance,
)

__all__ = [
    # Global Instance Manager
    "GlobalInstanceManager",
    "get_global_instance_manager",
    "get_isolated_instance",
    "clear_tenant_instances",
    "get_tenant_instances",
    "get_instance_stats",
    # Lifecycle Manager
    "InstanceLifecycleManager",
    "get_lifecycle_manager",
    "InstanceState",
    "LifecycleEvent",
    "activate_instance",
    "deactivate_instance",
    "cleanup_instance",
    "get_instance_state",
    # Instance Registry
    "InstanceRegistry",
    "get_instance_registry",
    "InstanceDefinition",
    "InstanceScope",
    "DependencyType",
    "InstanceFactory",
    "register_instance",
    "get_instance",
    "inject",
    # Tenant Resource Manager
    "TenantResourceManager",
    "get_tenant_resource_manager",
    "ResourceQuota",
    "ResourceType",
    "QuotaType",
    "AlertLevel",
    "TenantResourceStats",
    "set_tenant_quota",
    "record_resource_usage",
    "get_tenant_stats",
    # Instance Monitoring
    "InstanceMonitoringSystem",
    "get_instance_monitoring",
    "InstanceMonitor",
    "HealthStatus",
    "MetricType",
    "SeverityLevel",
    "register_instance_monitoring",
    "create_span",
    # Instance Manager API
    "InstanceManagerAPI",
    "get_instance_manager_api",
    "InstanceOperationResult",
    "BatchOperationResult",
    "get_isolated_instance",
    "clear_tenant_instances",
    "get_tenant_summary",
    "batch_create_instances",
    "batch_health_check",
    "setup_tenant_quotas",
    "get_system_stats",
    "system_health_check",
    "with_isolated_instance",
    "with_tenant_context",
    "monitor_instance_performance",
]

# 版本信息
__version__ = "1.0.0"
__description__ = "MaiBot Core - Multi-tenant Instance Management System"
