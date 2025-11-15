"""
便捷API接口
提供插件系统多租户隔离的便捷API接口，包括插件执行、管理和监控功能
"""

import asyncio
import time
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass

from src.common.logger import get_logger
from src.isolation.isolation_context import create_isolation_context
from src.plugin_system.core.isolated_plugin_executor import PluginExecutionConfig, PluginExecutionResult
from src.plugin_system.core.plugin_manager import (
    get_isolated_plugin_manager,
    configure_tenant_plugin,
    enable_tenant_plugin,
    disable_tenant_plugin,
)
from src.plugin_system.core.isolated_plugin_api import (
    IsolatedPluginAPI,
    create_isolated_plugin_api,
    create_limited_plugin_api,
    APIResourceType,
    APIPermission,
)
from src.plugin_system.core.plugin_isolation import (
    SecurityLevel,
    SecurityPolicy,
    validate_plugin_isolation,
    get_isolation_validator,
    get_plugin_violation_stats,
    register_plugin_security_policy,
)
from src.plugin_system.core.isolated_plugin_executor import PluginExecutionStatus

logger = get_logger("isolated_plugin_api_wrapper")


@dataclass
class PluginExecutionRequest:
    """插件执行请求"""

    plugin_name: str
    method_name: str
    tenant_id: str
    agent_id: str
    platform: str = None
    chat_stream_id: str = None
    config: Optional[PluginExecutionConfig] = None
    args: tuple = ()
    kwargs: dict = None

    def __post_init__(self):
        if self.kwargs is None:
            self.kwargs = {}


@dataclass
class PluginInfo:
    """插件信息"""

    name: str
    display_name: str = None
    version: str = None
    description: str = None
    author: str = None
    enabled: bool = True
    permissions: Dict[str, bool] = None
    config: Dict[str, Any] = None

    def __post_init__(self):
        if self.permissions is None:
            self.permissions = {}
        if self.config is None:
            self.config = {}


class IsolatedPluginSystem:
    """
    隔离化插件系统

    提供插件系统多租户隔离的统一接口
    """

    def __init__(self):
        self.validator = get_isolation_validator()
        logger.info("隔离化插件系统初始化完成")

    # === 插件执行API ===

    async def execute_plugin(self, request: PluginExecutionRequest) -> PluginExecutionResult:
        """
        执行插件

        Args:
            request: 插件执行请求

        Returns:
            PluginExecutionResult: 执行结果
        """
        try:
            # 获取插件实例
            from src.plugin_system.core.plugin_manager import plugin_manager

            plugin_instance = plugin_manager.get_plugin_instance(request.plugin_name)
            if not plugin_instance:
                raise ValueError(f"插件实例不存在: {request.plugin_name}")

            # 创建隔离上下文
            isolation_context = create_isolation_context(
                tenant_id=request.tenant_id,
                agent_id=request.agent_id,
                platform=request.platform,
                chat_stream_id=request.chat_stream_id,
            )

            # 验证隔离权限
            sandbox = validate_plugin_isolation(
                plugin_instance,
                isolation_context,
                request.config.security_level if request.config else SecurityLevel.MEDIUM,
            )

            # 在沙箱中执行插件
            async with sandbox.execute(request.plugin_name, request.tenant_id, request.agent_id):
                result = await execute_isolated_plugin(
                    plugin_instance,
                    request.method_name,
                    request.tenant_id,
                    request.agent_id,
                    request.platform,
                    request.config,
                    *request.args,
                    **request.kwargs,
                )

                # 记录违规
                violations = sandbox.get_violations()
                if violations:
                    for violation in violations:
                        self.validator.record_violation(violation)

                return result

        except Exception as e:
            logger.error(f"执行插件 {request.plugin_name} 失败: {e}")
            # 返回失败结果
            return PluginExecutionResult(
                plugin_name=request.plugin_name,
                execution_id=f"failed_{int(time.time())}",
                status=PluginExecutionResult.FAILED,
                start_time=time.time(),
                end_time=time.time(),
                execution_time=0.0,
                error=e,
            )

    async def execute_plugin_simple(
        self, plugin_name: str, method_name: str, tenant_id: str, agent_id: str, platform: str = None, *args, **kwargs
    ) -> PluginExecutionResult:
        """
        简化的插件执行方法

        Args:
            plugin_name: 插件名称
            method_name: 方法名称
            tenant_id: 租户ID
            agent_id: 智能体ID
            platform: 平台标识
            *args, **kwargs: 传递给插件方法的参数

        Returns:
            PluginExecutionResult: 执行结果
        """
        request = PluginExecutionRequest(
            plugin_name=plugin_name,
            method_name=method_name,
            tenant_id=tenant_id,
            agent_id=agent_id,
            platform=platform,
            args=args,
            kwargs=kwargs,
        )

        return await self.execute_plugin(request)

    # === 插件管理API ===

    def configure_plugin(
        self,
        tenant_id: str,
        plugin_name: str,
        config: Dict[str, Any] = None,
        permissions: Dict[str, bool] = None,
        priority: int = 0,
    ) -> bool:
        """配置插件"""
        return configure_tenant_plugin(tenant_id, plugin_name, config, permissions, priority)

    def enable_plugin(self, tenant_id: str, plugin_name: str) -> bool:
        """启用插件"""
        return enable_tenant_plugin(tenant_id, plugin_name)

    def disable_plugin(self, tenant_id: str, plugin_name: str) -> bool:
        """禁用插件"""
        return disable_tenant_plugin(tenant_id, plugin_name)

    def can_execute_plugin(self, tenant_id: str, plugin_name: str, agent_id: str = None, platform: str = None) -> bool:
        """检查是否可以执行插件"""
        from src.plugin_system.core.plugin_manager import can_tenant_execute_plugin

        return can_tenant_execute_plugin(tenant_id, plugin_name, agent_id, platform)

    def get_tenant_plugins(self, tenant_id: str) -> List[str]:
        """获取租户的插件列表"""
        manager = get_isolated_plugin_manager(tenant_id)
        return manager.get_enabled_plugins()

    def get_plugin_info(self, tenant_id: str, plugin_name: str) -> Optional[PluginInfo]:
        """获取插件信息"""
        try:
            from src.plugin_system.core.plugin_manager import plugin_manager

            plugin_instance = plugin_manager.get_plugin_instance(plugin_name)
            if not plugin_instance:
                return None

            manager = get_isolated_plugin_manager(tenant_id)
            config = manager.get_plugin_config(plugin_name)
            permissions = manager.get_plugin_permissions(plugin_name)
            enabled = manager.is_plugin_enabled(plugin_name)

            return PluginInfo(
                name=plugin_name,
                display_name=getattr(plugin_instance, "display_name", plugin_name),
                version=getattr(plugin_instance, "version", None),
                description=getattr(plugin_instance, "description", None),
                author=getattr(plugin_instance, "author", None),
                enabled=enabled,
                permissions=permissions,
                config=config,
            )

        except Exception as e:
            logger.error(f"获取插件信息失败: {e}")
            return None

    # === 插件API管理 ===

    def create_plugin_api(
        self,
        tenant_id: str,
        agent_id: str,
        platform: str = None,
        chat_stream_id: str = None,
        limited_permissions: bool = False,
    ) -> IsolatedPluginAPI:
        """创建插件API"""
        if limited_permissions:
            # 创建有限权限的API
            allowed_permissions = {
                APIResourceType.MESSAGE: [APIPermission.READ],
                APIResourceType.CONFIG: [APIPermission.READ],
                APIResourceType.MEMORY: [APIPermission.READ],
                APIResourceType.EVENT: [APIPermission.READ],
                APIResourceType.PLUGIN: [APIPermission.READ],
            }
            return create_limited_plugin_api(tenant_id, agent_id, allowed_permissions, platform, chat_stream_id)
        else:
            return create_isolated_plugin_api(tenant_id, agent_id, platform, chat_stream_id)

    # === 监控和统计API ===

    def get_execution_stats(self, tenant_id: str = None) -> Dict[str, Any]:
        """获取执行统计"""
        from src.plugin_system.core.isolated_plugin_executor import get_plugin_execution_stats

        return get_plugin_execution_stats(tenant_id)

    def get_plugin_stats(self, tenant_id: str) -> Dict[str, Any]:
        """获取插件统计"""
        from src.plugin_system.core.plugin_manager import get_tenant_plugin_stats

        return get_tenant_plugin_stats(tenant_id)

    def get_system_stats(self) -> Dict[str, Any]:
        """获取系统统计"""
        from src.plugin_system.core.isolated_plugin_executor import get_global_executor_manager
        from src.plugin_system.core.plugin_manager import get_global_plugin_manager_manager

        executor_stats = get_global_executor_manager().get_executor_stats()
        manager_stats = get_global_plugin_manager_manager().get_all_manager_stats()

        return {
            "executor_stats": executor_stats,
            "manager_stats": manager_stats,
            "total_tenants": manager_stats["total_managers"],
            "total_active_executors": executor_stats["active_executors"],
            "total_active_managers": manager_stats["active_managers"],
        }

    def get_violation_stats(self, days: int = 7) -> Dict[str, Any]:
        """获取违规统计"""
        return get_plugin_violation_stats(days)

    # === 生命周期管理API ===

    async def cleanup_tenant_resources(self, tenant_id: str):
        """清理租户资源"""
        try:
            # 清理插件执行器
            from src.plugin_system.core.isolated_plugin_executor import cleanup_tenant_plugin_executors

            await cleanup_tenant_plugin_executors(tenant_id)

            # 清理插件管理器
            from src.plugin_system.core.plugin_manager import get_global_plugin_manager_manager

            manager = get_global_plugin_manager_manager()
            manager.remove_manager(tenant_id)

            logger.info(f"已清理租户 {tenant_id} 的插件系统资源")

        except Exception as e:
            logger.error(f"清理租户资源失败: {e}")

    async def cleanup_all_resources(self):
        """清理所有资源"""
        try:
            # 清理所有插件执行器
            from src.plugin_system.core.isolated_plugin_executor import cleanup_all_plugin_executors

            await cleanup_all_plugin_executors()

            logger.info("已清理所有插件系统资源")

        except Exception as e:
            logger.error(f"清理所有资源失败: {e}")

    # === 安全策略API ===

    def register_security_policy(self, name: str, policy: SecurityPolicy):
        """注册安全策略"""
        register_plugin_security_policy(name, policy)

    def get_default_security_policies(self) -> Dict[str, SecurityPolicy]:
        """获取默认安全策略"""
        validator = get_isolation_validator()
        return validator.default_policies

    # === 健康检查API ===

    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            system_stats = self.get_system_stats()
            current_time = time.time()

            health_status = {
                "status": "healthy",
                "timestamp": current_time,
                "uptime": current_time,  # 这里应该记录系统启动时间
                "system_stats": system_stats,
                "checks": {},
            }

            # 检查执行器状态
            total_executors = system_stats["executor_stats"]["total_executors"]
            active_executors = system_stats["executor_stats"]["active_executors"]
            health_status["checks"]["executors"] = {
                "status": "healthy" if active_executors <= total_executors * 2 else "warning",
                "total": total_executors,
                "active": active_executors,
            }

            # 检查管理器状态
            total_managers = system_stats["manager_stats"]["total_managers"]
            active_managers = system_stats["manager_stats"]["active_managers"]
            health_status["checks"]["managers"] = {
                "status": "healthy" if active_managers == total_managers else "warning",
                "total": total_managers,
                "active": active_managers,
            }

            # 检查违规情况
            violation_stats = self.get_violation_stats(1)  # 最近1天
            total_violations = violation_stats["total_violations"]
            health_status["checks"]["violations"] = {
                "status": "healthy" if total_violations < 100 else "warning",
                "total_violations": total_violations,
                "recent_violations": total_violations,
            }

            # 如果有任何警告，整体状态为警告
            if any(check["status"] == "warning" for check in health_status["checks"].values()):
                health_status["status"] = "warning"

            return health_status

        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return {"status": "unhealthy", "timestamp": time.time(), "error": str(e)}


# 全局系统实例
_global_isolated_plugin_system = IsolatedPluginSystem()


def get_isolated_plugin_system() -> IsolatedPluginSystem:
    """获取全局隔离化插件系统"""
    return _global_isolated_plugin_system


# === 便捷函数 ===


async def execute_isolated_plugin_wrapper(
    plugin_name: str, method_name: str, tenant_id: str, agent_id: str, platform: str = None, *args, **kwargs
) -> PluginExecutionResult:
    """执行隔离化插件的便捷函数"""
    system = get_isolated_plugin_system()
    return await system.execute_plugin_simple(plugin_name, method_name, tenant_id, agent_id, platform, *args, **kwargs)


# 为了向后兼容，创建别名
execute_isolated_plugin = execute_isolated_plugin_wrapper


def configure_isolated_plugin(
    tenant_id: str,
    plugin_name: str,
    config: Dict[str, Any] = None,
    permissions: Dict[str, bool] = None,
    priority: int = 0,
) -> bool:
    """配置隔离化插件的便捷函数"""
    system = get_isolated_plugin_system()
    return system.configure_plugin(tenant_id, plugin_name, config, permissions, priority)


def enable_isolated_plugin(tenant_id: str, plugin_name: str) -> bool:
    """启用隔离化插件的便捷函数"""
    system = get_isolated_plugin_system()
    return system.enable_plugin(tenant_id, plugin_name)


def disable_isolated_plugin(tenant_id: str, plugin_name: str) -> bool:
    """禁用隔离化插件的便捷函数"""
    system = get_isolated_plugin_system()
    return system.disable_plugin(tenant_id, plugin_name)


def get_isolated_plugin_api(
    tenant_id: str, agent_id: str, platform: str = None, chat_stream_id: str = None
) -> IsolatedPluginAPI:
    """获取隔离化插件API的便捷函数"""
    system = get_isolated_plugin_system()
    return system.create_plugin_api(tenant_id, agent_id, platform, chat_stream_id)


def get_plugin_system_stats() -> Dict[str, Any]:
    """获取插件系统统计的便捷函数"""
    system = get_isolated_plugin_system()
    return system.get_system_stats()


async def cleanup_tenant_plugin_system(tenant_id: str):
    """清理租户插件系统的便捷函数"""
    system = get_isolated_plugin_system()
    await system.cleanup_tenant_resources(tenant_id)


async def plugin_system_health_check() -> Dict[str, Any]:
    """插件系统健康检查的便捷函数"""
    system = get_isolated_plugin_system()
    return await system.health_check()


# === 装饰器 ===


def isolated_plugin_execution(
    tenant_id: str, agent_id: str, platform: str = None, security_level: SecurityLevel = SecurityLevel.MEDIUM
):
    """隔离化插件执行装饰器"""

    def decorator(func: Callable) -> Callable:
        async def async_wrapper(*args, **kwargs):
            # 创建执行请求
            request = PluginExecutionRequest(
                plugin_name=func.__module__.split(".")[-1],  # 从模块名推断插件名
                method_name=func.__name__,
                tenant_id=tenant_id,
                agent_id=agent_id,
                platform=platform,
                args=args,
                kwargs=kwargs,
            )

            # 设置安全级别
            if not request.config:
                request.config = PluginExecutionConfig()
            request.config.security_level = security_level

            # 执行插件
            system = get_isolated_plugin_system()
            result = await system.execute_plugin(request)

            if result.status == PluginExecutionStatus.SUCCESS:
                return result.result
            else:
                raise result.error or Exception("插件执行失败")

        def sync_wrapper(*args, **kwargs):
            # 同步函数的包装器
            return asyncio.run(async_wrapper(*args, **kwargs))

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator
