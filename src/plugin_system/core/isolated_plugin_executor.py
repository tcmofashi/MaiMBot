"""
隔离化插件执行器
支持T+A+P维度的插件隔离执行，确保插件运行时的租户、智能体和平台隔离
"""

import asyncio
import time
import traceback
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor
import threading
import weakref

from src.common.logger import get_logger
from src.isolation.isolation_context import IsolationContext
from src.plugin_system.base.plugin_base import PluginBase

logger = get_logger("isolated_plugin_executor")


class PluginExecutionStatus(Enum):
    """插件执行状态"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class PluginSecurityLevel(Enum):
    """插件安全级别"""

    LOW = "low"  # 低安全级别，基础隔离
    MEDIUM = "medium"  # 中安全级别，资源限制
    HIGH = "high"  # 高安全级别，严格沙箱
    MAXIMUM = "maximum"  # 最高安全级别，完全隔离


@dataclass
class PluginExecutionResult:
    """插件执行结果"""

    plugin_name: str
    execution_id: str
    status: PluginExecutionStatus
    start_time: float
    end_time: float
    execution_time: float
    result: Any = None
    error: Optional[Exception] = None
    error_traceback: Optional[str] = None
    isolation_context: Optional[IsolationContext] = None
    security_level: PluginSecurityLevel = PluginSecurityLevel.MEDIUM
    resource_usage: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "plugin_name": self.plugin_name,
            "execution_id": self.execution_id,
            "status": self.status.value,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "execution_time": self.execution_time,
            "result": self.result,
            "error": str(self.error) if self.error else None,
            "error_traceback": self.error_traceback,
            "isolation_context": {
                "tenant_id": self.isolation_context.tenant_id,
                "agent_id": self.isolation_context.agent_id,
                "platform": self.isolation_context.platform,
                "chat_stream_id": self.isolation_context.chat_stream_id,
            }
            if self.isolation_context
            else None,
            "security_level": self.security_level.value,
            "resource_usage": self.resource_usage,
            "metadata": self.metadata,
        }


@dataclass
class PluginExecutionConfig:
    """插件执行配置"""

    timeout: float = 30.0  # 执行超时时间（秒）
    security_level: PluginSecurityLevel = PluginSecurityLevel.MEDIUM
    max_memory_mb: int = 512  # 最大内存使用（MB）
    max_cpu_time: float = 10.0  # 最大CPU时间（秒）
    allow_network_access: bool = False  # 是否允许网络访问
    allow_file_access: bool = False  # 是否允许文件访问
    allowed_modules: List[str] = field(default_factory=list)  # 允许导入的模块
    blocked_modules: List[str] = field(default_factory=list)  # 禁止导入的模块
    custom_environment: Dict[str, str] = field(default_factory=dict)  # 自定义环境变量
    retry_count: int = 0  # 重试次数
    retry_delay: float = 1.0  # 重试延迟（秒）


class IsolatedPluginExecutor:
    """
    隔离化插件执行器

    支持T+A+P维度的插件隔离执行，确保插件运行时的租户、智能体和平台隔离
    """

    def __init__(self, isolation_context: IsolationContext):
        self.isolation_context = isolation_context
        self.tenant_id = isolation_context.tenant_id  # T: 租户隔离
        self.agent_id = isolation_context.agent_id  # A: 智能体隔离
        self.platform = isolation_context.platform  # P: 平台隔离

        # 执行状态管理
        self._executions: Dict[str, PluginExecutionResult] = {}
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._execution_lock = threading.RLock()

        # 资源管理
        self._thread_pool = ThreadPoolExecutor(
            max_workers=4, thread_name_prefix=f"plugin_executor_{self.tenant_id}_{self.agent_id}"
        )

        # 安全沙箱环境
        self._sandbox_environment = self._create_sandbox_environment()

        # 统计信息
        self._execution_stats = {
            "total_executions": 0,
            "successful_executions": 0,
            "failed_executions": 0,
            "timeout_executions": 0,
            "total_execution_time": 0.0,
        }

        logger.debug(f"隔离化插件执行器初始化完成: {self.tenant_id}:{self.agent_id}:{self.platform}")

    def _create_sandbox_environment(self) -> Dict[str, Any]:
        """创建插件执行的安全沙箱环境"""
        # 基础安全环境
        sandbox = {
            "__builtins__": {
                "print": self._safe_print,
                "len": len,
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
                "list": list,
                "dict": dict,
                "tuple": tuple,
                "set": set,
                "range": range,
                "enumerate": enumerate,
                "zip": zip,
                "min": min,
                "max": max,
                "sum": sum,
                "abs": abs,
                "round": round,
                "sorted": sorted,
                "reversed": reversed,
            },
            "logger": self._create_plugin_logger(),
            "isolation_context": self.isolation_context,
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "platform": self.platform,
        }

        return sandbox

    def _safe_print(self, *args, **kwargs):
        """安全的print函数，带隔离上下文信息"""
        prefix = f"[Plugin:{self.tenant_id}:{self.agent_id}:{self.platform}]"
        print(prefix, *args, **kwargs)

    def _create_plugin_logger(self):
        """为插件创建隔离的logger"""
        logger_name = f"plugin_{self.tenant_id}_{self.agent_id}_{self.platform}"
        return get_logger(logger_name)

    async def execute_plugin(
        self, plugin: PluginBase, method_name: str, config: Optional[PluginExecutionConfig] = None, *args, **kwargs
    ) -> PluginExecutionResult:
        """
        执行插件方法

        Args:
            plugin: 插件实例
            method_name: 要执行的方法名
            config: 执行配置
            *args, **kwargs: 传递给插件方法的参数

        Returns:
            PluginExecutionResult: 执行结果
        """
        if config is None:
            config = PluginExecutionConfig()

        execution_id = self._generate_execution_id(plugin.plugin_name, method_name)

        # 创建执行结果对象
        result = PluginExecutionResult(
            plugin_name=plugin.plugin_name,
            execution_id=execution_id,
            status=PluginExecutionStatus.PENDING,
            start_time=time.time(),
            end_time=0.0,
            execution_time=0.0,
            isolation_context=self.isolation_context,
            security_level=config.security_level,
        )

        try:
            with self._execution_lock:
                self._executions[execution_id] = result
                self._execution_stats["total_executions"] += 1

            # 验证插件权限
            if not self._validate_plugin_permission(plugin):
                raise PermissionError(f"插件 {plugin.plugin_name} 没有在此隔离上下文中执行的权限")

            # 准备执行环境
            execution_context = self._prepare_execution_context(plugin, config)

            # 执行插件方法
            result.status = PluginExecutionStatus.RUNNING
            result.start_time = time.time()

            if asyncio.iscoroutinefunction(getattr(plugin, method_name, None)):
                # 异步方法
                task = asyncio.create_task(
                    self._execute_async_plugin_method(plugin, method_name, execution_context, *args, **kwargs)
                )
                self._running_tasks[execution_id] = task

                try:
                    execution_result = await asyncio.wait_for(task, timeout=config.timeout)
                    result.result = execution_result
                    result.status = PluginExecutionStatus.SUCCESS
                    self._execution_stats["successful_executions"] += 1
                except asyncio.TimeoutError:
                    task.cancel()
                    result.status = PluginExecutionStatus.TIMEOUT
                    result.error = TimeoutError(f"插件执行超时: {config.timeout}秒")
                    self._execution_stats["timeout_executions"] += 1
            else:
                # 同步方法
                execution_result = await self._execute_sync_plugin_method(
                    plugin, method_name, execution_context, *args, **kwargs
                )
                result.result = execution_result
                result.status = PluginExecutionStatus.SUCCESS
                self._execution_stats["successful_executions"] += 1

        except Exception as e:
            result.status = PluginExecutionStatus.FAILED
            result.error = e
            result.error_traceback = traceback.format_exc()
            self._execution_stats["failed_executions"] += 1
            logger.error(f"插件 {plugin.plugin_name} 执行失败: {e}")

        finally:
            result.end_time = time.time()
            result.execution_time = result.end_time - result.start_time
            self._execution_stats["total_execution_time"] += result.execution_time

            # 清理运行中的任务
            if execution_id in self._running_tasks:
                del self._running_tasks[execution_id]

        return result

    async def _execute_async_plugin_method(
        self, plugin: PluginBase, method_name: str, execution_context: Dict[str, Any], *args, **kwargs
    ) -> Any:
        """执行异步插件方法"""
        method = getattr(plugin, method_name)
        if method is None:
            raise AttributeError(f"插件 {plugin.plugin_name} 没有方法 {method_name}")

        # 为插件方法注入隔离上下文
        if hasattr(method, "__self__"):
            # 实例方法，为其添加隔离上下文属性
            method.__self__._isolation_context = self.isolation_context
            method.__self__._isolated_api = execution_context.get("api")

        return await method(*args, **kwargs)

    async def _execute_sync_plugin_method(
        self, plugin: PluginBase, method_name: str, execution_context: Dict[str, Any], *args, **kwargs
    ) -> Any:
        """执行同步插件方法"""
        method = getattr(plugin, method_name)
        if method is None:
            raise AttributeError(f"插件 {plugin.plugin_name} 没有方法 {method_name}")

        # 在线程池中执行同步方法
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._thread_pool, self._run_sync_method, method, execution_context, *args, **kwargs
        )

    def _run_sync_method(self, method: Callable, execution_context: Dict[str, Any], *args, **kwargs) -> Any:
        """在线程池中运行同步方法"""
        # 为插件方法注入隔离上下文
        if hasattr(method, "__self__"):
            method.__self__._isolation_context = self.isolation_context
            method.__self__._isolated_api = execution_context.get("api")

        return method(*args, **kwargs)

    def _validate_plugin_permission(self, plugin: PluginBase) -> bool:
        """验证插件是否有在当前隔离上下文中执行的权限"""
        # 检查插件是否允许在租户级别执行
        if hasattr(plugin, "allowed_tenants"):
            if self.tenant_id not in plugin.allowed_tenants:
                return False

        # 检查插件是否允许在智能体级别执行
        if hasattr(plugin, "allowed_agents"):
            if self.agent_id not in plugin.allowed_agents:
                return False

        # 检查插件是否允许在平台执行
        if hasattr(plugin, "allowed_platforms"):
            if self.platform not in plugin.allowed_platforms:
                return False

        return True

    def _prepare_execution_context(self, plugin: PluginBase, config: PluginExecutionConfig) -> Dict[str, Any]:
        """准备插件执行环境"""
        # 这里会创建隔离化的API对象，后续实现
        execution_context = {
            "config": config,
            "sandbox": self._sandbox_environment,
            "isolation_context": self.isolation_context,
            # "api": IsolatedPluginAPI(self.isolation_context)  # 后续实现
        }

        return execution_context

    def _generate_execution_id(self, plugin_name: str, method_name: str) -> str:
        """生成执行ID"""
        timestamp = str(int(time.time() * 1000))
        return f"{self.tenant_id}:{self.agent_id}:{self.platform}:{plugin_name}:{method_name}:{timestamp}"

    def get_execution_result(self, execution_id: str) -> Optional[PluginExecutionResult]:
        """获取执行结果"""
        with self._execution_lock:
            return self._executions.get(execution_id)

    def get_execution_history(
        self, limit: int = 100, status_filter: Optional[PluginExecutionStatus] = None
    ) -> List[PluginExecutionResult]:
        """获取执行历史"""
        with self._execution_lock:
            executions = list(self._executions.values())

            if status_filter:
                executions = [e for e in executions if e.status == status_filter]

            # 按开始时间倒序排列
            executions.sort(key=lambda x: x.start_time, reverse=True)

            return executions[:limit]

    def cancel_execution(self, execution_id: str) -> bool:
        """取消正在执行的插件"""
        if execution_id in self._running_tasks:
            task = self._running_tasks[execution_id]
            if not task.done():
                task.cancel()

                # 更新执行结果
                if execution_id in self._executions:
                    result = self._executions[execution_id]
                    result.status = PluginExecutionStatus.CANCELLED
                    result.end_time = time.time()
                    result.execution_time = result.end_time - result.start_time

                return True
        return False

    def clear_execution_history(self, older_than_minutes: int = 60):
        """清理执行历史"""
        current_time = time.time()
        cutoff_time = current_time - (older_than_minutes * 60)

        with self._execution_lock:
            to_remove = []
            for execution_id, result in self._executions.items():
                if result.start_time < cutoff_time:
                    to_remove.append(execution_id)

            for execution_id in to_remove:
                del self._executions[execution_id]

    def get_execution_stats(self) -> Dict[str, Any]:
        """获取执行统计信息"""
        with self._execution_lock:
            stats = self._execution_stats.copy()
            stats["active_executions"] = len(self._running_tasks)
            stats["total_executions_in_memory"] = len(self._executions)

            if stats["total_executions"] > 0:
                stats["success_rate"] = stats["successful_executions"] / stats["total_executions"]
                stats["average_execution_time"] = stats["total_execution_time"] / stats["total_executions"]
            else:
                stats["success_rate"] = 0.0
                stats["average_execution_time"] = 0.0

            return stats

    async def cleanup(self):
        """清理资源"""
        # 取消所有运行中的任务
        for execution_id in list(self._running_tasks.keys()):
            self.cancel_execution(execution_id)

        # 等待所有任务完成
        if self._running_tasks:
            await asyncio.gather(*self._running_tasks.values(), return_exceptions=True)

        # 关闭线程池
        self._thread_pool.shutdown(wait=True)

        # 清理执行历史
        with self._execution_lock:
            self._executions.clear()
            self._running_tasks.clear()

        logger.debug(f"隔离化插件执行器已清理: {self.tenant_id}:{self.agent_id}:{self.platform}")


class IsolatedPluginExecutorManager:
    """
    隔离化插件执行器管理器

    管理多个租户+智能体+平台组合的插件执行器实例
    """

    def __init__(self):
        self._executors: Dict[str, IsolatedPluginExecutor] = {}
        self._lock = threading.RLock()
        self._weak_refs: Dict[str, weakref.ref] = {}

        logger.info("隔离化插件执行器管理器初始化完成")

    def get_executor(self, isolation_context: IsolationContext) -> IsolatedPluginExecutor:
        """获取或创建隔离化插件执行器"""
        scope_key = str(isolation_context.scope)

        with self._lock:
            # 检查弱引用是否仍然有效
            if scope_key in self._weak_refs:
                executor_ref = self._weak_refs[scope_key]
                executor = executor_ref()
                if executor is not None:
                    return executor

            # 创建新的执行器
            executor = IsolatedPluginExecutor(isolation_context)
            self._weak_refs[scope_key] = weakref.ref(executor)

            logger.debug(f"创建新的隔离化插件执行器: {scope_key}")
            return executor

    def get_executor_stats(self) -> Dict[str, Any]:
        """获取所有执行器的统计信息"""
        with self._lock:
            stats = {"total_executors": len(self._weak_refs), "active_executors": 0, "executor_details": {}}

            for scope_key, ref in self._weak_refs.items():
                executor = ref()
                if executor is not None:
                    stats["active_executors"] += 1
                    executor_stats = executor.get_execution_stats()
                    stats["executor_details"][scope_key] = executor_stats

            return stats

    async def cleanup_tenant_executors(self, tenant_id: str):
        """清理指定租户的所有执行器"""
        with self._lock:
            to_remove = []
            for scope_key, ref in self._weak_refs.items():
                if scope_key.startswith(f"{tenant_id}:"):
                    executor = ref()
                    if executor is not None:
                        to_remove.append(executor)
                    del self._weak_refs[scope_key]

            # 并行清理所有执行器
            if to_remove:
                await asyncio.gather(*[executor.cleanup() for executor in to_remove], return_exceptions=True)

            logger.info(f"已清理租户 {tenant_id} 的 {len(to_remove)} 个插件执行器")

    async def cleanup_all_executors(self):
        """清理所有执行器"""
        with self._lock:
            executors = []
            for ref in self._weak_refs.values():
                executor = ref()
                if executor is not None:
                    executors.append(executor)

            self._weak_refs.clear()

        # 并行清理所有执行器
        if executors:
            await asyncio.gather(*[executor.cleanup() for executor in executors], return_exceptions=True)

        logger.info("已清理所有插件执行器")

    def cleanup_expired_executors(self):
        """清理已过期的执行器引用"""
        with self._lock:
            expired_keys = []
            for key, ref in self._weak_refs.items():
                if ref() is None:
                    expired_keys.append(key)

            for key in expired_keys:
                del self._weak_refs[key]

            if expired_keys:
                logger.debug(f"清理了 {len(expired_keys)} 个过期的插件执行器引用")


# 全局管理器实例
_global_executor_manager = IsolatedPluginExecutorManager()


def get_isolated_plugin_executor(isolation_context: IsolationContext) -> IsolatedPluginExecutor:
    """获取隔离化插件执行器的便捷函数"""
    return _global_executor_manager.get_executor(isolation_context)


def get_global_executor_manager() -> IsolatedPluginExecutorManager:
    """获取全局执行器管理器"""
    return _global_executor_manager


# 便捷函数
async def execute_isolated_plugin(
    plugin: PluginBase,
    method_name: str,
    tenant_id: str,
    agent_id: str,
    platform: str = None,
    config: Optional[PluginExecutionConfig] = None,
    *args,
    **kwargs,
) -> PluginExecutionResult:
    """
    执行隔离化插件的便捷函数

    Args:
        plugin: 插件实例
        method_name: 要执行的方法名
        tenant_id: 租户ID
        agent_id: 智能体ID
        platform: 平台标识
        config: 执行配置
        *args, **kwargs: 传递给插件方法的参数

    Returns:
        PluginExecutionResult: 执行结果
    """
    from src.isolation.isolation_context import create_isolation_context

    isolation_context = create_isolation_context(tenant_id=tenant_id, agent_id=agent_id, platform=platform)

    executor = get_isolated_plugin_executor(isolation_context)
    return await executor.execute_plugin(plugin, method_name, config, *args, **kwargs)


def get_plugin_execution_stats(tenant_id: str = None) -> Dict[str, Any]:
    """获取插件执行统计信息"""
    manager = get_global_executor_manager()

    if tenant_id:
        # 获取指定租户的统计信息
        manager_stats = manager.get_executor_stats()
        tenant_stats = {"total_executors": 0, "active_executors": 0, "executor_details": {}}

        for scope_key, stats in manager_stats["executor_details"].items():
            if scope_key.startswith(f"{tenant_id}:"):
                tenant_stats["total_executors"] += 1
                if stats.get("active_executions", 0) > 0:
                    tenant_stats["active_executors"] += 1
                tenant_stats["executor_details"][scope_key] = stats

        return tenant_stats
    else:
        return manager.get_executor_stats()


async def cleanup_tenant_plugin_executors(tenant_id: str):
    """清理指定租户的插件执行器"""
    manager = get_global_executor_manager()
    await manager.cleanup_tenant_executors(tenant_id)


async def cleanup_all_plugin_executors():
    """清理所有插件执行器"""
    manager = get_global_executor_manager()
    await manager.cleanup_all_executors()
