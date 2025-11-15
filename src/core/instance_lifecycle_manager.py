"""
实例生命周期管理器

负责实例的创建、激活、停用、清理等生命周期管理。
支持实例的自动过期和资源回收，提供实例状态监控和健康检查。

主要功能：
1. 实例状态管理（创建、激活、停用、清理）
2. 生命周期钩子和事件处理
3. 自动过期和资源回收
4. 健康检查和故障恢复
5. 生命周期统计和监控
"""

import asyncio
import threading
import weakref
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable
from enum import Enum
from dataclasses import dataclass, field
from collections import defaultdict
import logging


logger = logging.getLogger(__name__)


class InstanceState(Enum):
    """实例状态枚举"""

    CREATING = "creating"  # 创建中
    ACTIVE = "active"  # 活跃
    INACTIVE = "inactive"  # 非活跃
    PAUSED = "paused"  # 暂停
    ERROR = "error"  # 错误
    TERMINATING = "terminating"  # 终止中
    TERMINATED = "terminated"  # 已终止


class LifecycleEvent(Enum):
    """生命周期事件枚举"""

    BEFORE_CREATE = "before_create"
    AFTER_CREATE = "after_create"
    BEFORE_ACTIVATE = "before_activate"
    AFTER_ACTIVATE = "after_activate"
    BEFORE_DEACTIVATE = "before_deactivate"
    AFTER_DEACTIVATE = "after_deactivate"
    BEFORE_CLEANUP = "before_cleanup"
    AFTER_CLEANUP = "after_cleanup"
    ON_ERROR = "on_error"
    ON_HEALTH_CHECK = "on_health_check"


@dataclass
class LifecycleConfig:
    """生命周期配置"""

    max_inactive_minutes: int = 30  # 最大非活跃时间（分钟）
    health_check_interval: int = 60  # 健康检查间隔（秒）
    max_error_count: int = 3  # 最大错误次数
    auto_cleanup: bool = True  # 自动清理
    retry_on_error: bool = True  # 错误时重试
    max_retry_attempts: int = 3  # 最大重试次数
    retry_delay: float = 1.0  # 重试延迟（秒）
    enable_metrics: bool = True  # 启用指标收集


@dataclass
class InstanceMetrics:
    """实例指标"""

    created_at: datetime = field(default_factory=datetime.now)
    activated_at: Optional[datetime] = None
    last_active_at: datetime = field(default_factory=datetime.now)
    last_health_check: Optional[datetime] = None
    error_count: int = 0
    health_check_count: int = 0
    active_duration: float = 0.0
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0


class LifecycleHook:
    """生命周期钩子"""

    def __init__(self, event: LifecycleEvent, handler: Callable, priority: int = 0):
        self.event = event
        self.handler = handler
        self.priority = priority
        self.enabled = True

    async def execute(self, instance_id: str, context: Dict[str, Any]) -> bool:
        """执行钩子"""
        if not self.enabled:
            return True

        try:
            if asyncio.iscoroutinefunction(self.handler):
                result = await self.handler(instance_id, context)
            else:
                result = self.handler(instance_id, context)

            return bool(result)
        except Exception as e:
            logger.error(f"Lifecycle hook failed for {self.event} on {instance_id}: {e}")
            return False


class InstanceLifecycleManager:
    """
    实例生命周期管理器

    负责管理实例的完整生命周期，包括创建、激活、停用、清理等阶段。
    支持生命周期钩子、健康检查、自动清理等功能。
    """

    _instance: Optional["InstanceLifecycleManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "InstanceLifecycleManager":
        """单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return

        self._initialized = True
        self._lock = threading.RLock()

        # 实例状态管理
        self._instance_states: Dict[str, InstanceState] = {}
        self._instance_configs: Dict[str, LifecycleConfig] = {}
        self._instance_metrics: Dict[str, InstanceMetrics] = {}
        self._instance_contexts: Dict[str, Dict[str, Any]] = {}

        # 实例引用（弱引用）
        self._instance_refs: Dict[str, weakref.ref] = {}

        # 生命周期钩子
        self._hooks: Dict[LifecycleEvent, List[LifecycleHook]] = defaultdict(list)

        # 健康检查任务
        self._health_check_tasks: Dict[str, asyncio.Task] = {}
        self._cleanup_task: Optional[asyncio.Task] = None

        # 统计信息
        self._global_stats = {
            "total_instances": 0,
            "active_instances": 0,
            "error_instances": 0,
            "cleaned_instances": 0,
            "health_checks_performed": 0,
            "errors_detected": 0,
            "auto_cleanups_performed": 0,
            "last_cleanup": None,
        }

        # 默认配置
        self._default_config = LifecycleConfig()

        logger.info("InstanceLifecycleManager initialized")

    def register_instance(
        self, instance_id: str, instance: Any, config: Optional[LifecycleConfig] = None, **context
    ) -> bool:
        """
        注册实例

        Args:
            instance_id: 实例ID
            instance: 实例对象
            config: 生命周期配置
            **context: 上下文信息

        Returns:
            是否注册成功
        """
        with self._lock:
            if instance_id in self._instance_states:
                logger.warning(f"Instance {instance_id} already registered")
                return False

            try:
                # 设置配置
                if config is None:
                    config = self._default_config
                self._instance_configs[instance_id] = config

                # 设置状态
                self._instance_states[instance_id] = InstanceState.CREATING

                # 设置上下文
                self._instance_contexts[instance_id] = context.copy()

                # 设置指标
                self._instance_metrics[instance_id] = InstanceMetrics()

                # 设置弱引用
                self._instance_refs[instance_id] = weakref.ref(instance)

                # 执行创建前钩子
                asyncio.create_task(self._execute_hooks(LifecycleEvent.BEFORE_CREATE, instance_id))

                logger.info(f"Instance {instance_id} registered")
                return True

            except Exception as e:
                logger.error(f"Failed to register instance {instance_id}: {e}")
                return False

    async def activate_instance(self, instance_id: str) -> bool:
        """
        激活实例

        Args:
            instance_id: 实例ID

        Returns:
            是否激活成功
        """
        with self._lock:
            if instance_id not in self._instance_states:
                logger.error(f"Instance {instance_id} not found")
                return False

            if self._instance_states[instance_id] != InstanceState.CREATING:
                logger.warning(f"Instance {instance_id} is not in CREATING state")
                return False

        try:
            # 执行激活前钩子
            success = await self._execute_hooks(LifecycleEvent.BEFORE_ACTIVATE, instance_id)
            if not success:
                return False

            with self._lock:
                self._instance_states[instance_id] = InstanceState.ACTIVE
                metrics = self._instance_metrics[instance_id]
                metrics.activated_at = datetime.now()
                metrics.last_active_at = datetime.now()

            # 启动健康检查
            if self._instance_configs[instance_id].health_check_interval > 0:
                await self._start_health_check(instance_id)

            # 执行激活后钩子
            await self._execute_hooks(LifecycleEvent.AFTER_ACTIVATE, instance_id)

            logger.info(f"Instance {instance_id} activated")
            return True

        except Exception as e:
            await self._handle_instance_error(instance_id, e)
            return False

    async def deactivate_instance(self, instance_id: str) -> bool:
        """
        停用实例

        Args:
            instance_id: 实例ID

        Returns:
            是否停用成功
        """
        with self._lock:
            if instance_id not in self._instance_states:
                logger.error(f"Instance {instance_id} not found")
                return False

            if self._instance_states[instance_id] != InstanceState.ACTIVE:
                logger.warning(f"Instance {instance_id} is not active")
                return False

        try:
            # 执行停用前钩子
            await self._execute_hooks(LifecycleEvent.BEFORE_DEACTIVATE, instance_id)

            with self._lock:
                self._instance_states[instance_id] = InstanceState.INACTIVE
                metrics = self._instance_metrics[instance_id]
                if metrics.activated_at:
                    metrics.active_duration += (datetime.now() - metrics.activated_at).total_seconds()
                    metrics.activated_at = None

            # 停止健康检查
            await self._stop_health_check(instance_id)

            # 执行停用后钩子
            await self._execute_hooks(LifecycleEvent.AFTER_DEACTIVATE, instance_id)

            logger.info(f"Instance {instance_id} deactivated")
            return True

        except Exception as e:
            await self._handle_instance_error(instance_id, e)
            return False

    async def cleanup_instance(self, instance_id: str, force: bool = False) -> bool:
        """
        清理实例

        Args:
            instance_id: 实例ID
            force: 是否强制清理

        Returns:
            是否清理成功
        """
        with self._lock:
            if instance_id not in self._instance_states:
                logger.warning(f"Instance {instance_id} not found for cleanup")
                return True

            current_state = self._instance_states[instance_id]
            if not force and current_state == InstanceState.ACTIVE:
                logger.warning(f"Cannot cleanup active instance {instance_id}, use force=True")
                return False

        try:
            # 设置为终止中状态
            with self._lock:
                self._instance_states[instance_id] = InstanceState.TERMINATING

            # 执行清理前钩子
            await self._execute_hooks(LifecycleEvent.BEFORE_CLEANUP, instance_id)

            # 停止健康检查
            await self._stop_health_check(instance_id)

            # 执行实例清理（如果实例有cleanup方法）
            instance_ref = self._instance_refs.get(instance_id)
            if instance_ref:
                instance = instance_ref()
                if instance and hasattr(instance, "cleanup"):
                    try:
                        if asyncio.iscoroutinefunction(instance.cleanup):
                            await instance.cleanup()
                        else:
                            instance.cleanup()
                    except Exception as e:
                        logger.error(f"Instance cleanup failed for {instance_id}: {e}")

            # 清理管理器中的数据
            with self._lock:
                if instance_id in self._instance_states:
                    del self._instance_states[instance_id]
                if instance_id in self._instance_configs:
                    del self._instance_configs[instance_id]
                if instance_id in self._instance_metrics:
                    del self._instance_metrics[instance_id]
                if instance_id in self._instance_contexts:
                    del self._instance_contexts[instance_id]
                if instance_id in self._instance_refs:
                    del self._instance_refs[instance_id]

                self._global_stats["cleaned_instances"] += 1

            # 执行清理后钩子
            await self._execute_hooks(LifecycleEvent.AFTER_CLEANUP, instance_id)

            logger.info(f"Instance {instance_id} cleaned up")
            return True

        except Exception as e:
            logger.error(f"Failed to cleanup instance {instance_id}: {e}")
            return False

    def add_lifecycle_hook(self, event: LifecycleEvent, handler: Callable, priority: int = 0) -> str:
        """
        添加生命周期钩子

        Args:
            event: 生命周期事件
            handler: 处理函数
            priority: 优先级

        Returns:
            钩子ID
        """
        hook = LifecycleHook(event, handler, priority)
        hook_id = f"{event.value}_{id(hook)}"

        with self._lock:
            self._hooks[event].append(hook)
            # 按优先级排序
            self._hooks[event].sort(key=lambda h: h.priority, reverse=True)

        logger.debug(f"Added lifecycle hook for {event}: {hook_id}")
        return hook_id

    def remove_lifecycle_hook(self, hook_id: str) -> bool:
        """
        移除生命周期钩子

        Args:
            hook_id: 钩子ID

        Returns:
            是否移除成功
        """
        with self._lock:
            for hooks in self._hooks.values():
                for i, hook in enumerate(hooks):
                    if f"{hook.event.value}_{id(hook)}" == hook_id:
                        hooks.pop(i)
                        logger.debug(f"Removed lifecycle hook: {hook_id}")
                        return True

        return False

    async def _execute_hooks(self, event: LifecycleEvent, instance_id: str) -> bool:
        """执行生命周期钩子"""
        hooks = self._hooks.get(event, [])
        success = True

        for hook in hooks:
            try:
                result = await hook.execute(instance_id, self._instance_contexts.get(instance_id, {}))
                if not result:
                    success = False
            except Exception as e:
                logger.error(f"Hook execution failed: {e}")
                success = False

        return success

    async def _start_health_check(self, instance_id: str):
        """启动健康检查"""
        config = self._instance_configs[instance_id]
        if config.health_check_interval <= 0:
            return

        task = asyncio.create_task(self._health_check_loop(instance_id))
        self._health_check_tasks[instance_id] = task

    async def _stop_health_check(self, instance_id: str):
        """停止健康检查"""
        if instance_id in self._health_check_tasks:
            task = self._health_check_tasks[instance_id]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self._health_check_tasks[instance_id]

    async def _health_check_loop(self, instance_id: str):
        """健康检查循环"""
        config = self._instance_configs[instance_id]

        while True:
            try:
                await asyncio.sleep(config.health_check_interval)
                await self._perform_health_check(instance_id)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check loop error for {instance_id}: {e}")

    async def _perform_health_check(self, instance_id: str):
        """执行健康检查"""
        with self._lock:
            if instance_id not in self._instance_states:
                return

            metrics = self._instance_metrics[instance_id]
            metrics.last_health_check = datetime.now()
            metrics.health_check_count += 1

        try:
            # 获取实例引用
            instance_ref = self._instance_refs.get(instance_id)
            if not instance_ref:
                await self._handle_instance_error(instance_id, Exception("Instance reference lost"))
                return

            instance = instance_ref()
            if not instance:
                await self._handle_instance_error(instance_id, Exception("Instance garbage collected"))
                return

            # 执行健康检查钩子
            await self._execute_hooks(LifecycleEvent.ON_HEALTH_CHECK, instance_id)

            # 如果实例有health_check方法，调用它
            if hasattr(instance, "health_check"):
                try:
                    if asyncio.iscoroutinefunction(instance.health_check):
                        is_healthy = await instance.health_check()
                    else:
                        is_healthy = instance.health_check()

                    if not is_healthy:
                        await self._handle_instance_error(instance_id, Exception("Instance health check failed"))

                except Exception as e:
                    await self._handle_instance_error(instance_id, e)

            # 更新活跃时间
            with self._lock:
                if instance_id in self._instance_metrics:
                    self._instance_metrics[instance_id].last_active_at = datetime.now()

            self._global_stats["health_checks_performed"] += 1

        except Exception as e:
            await self._handle_instance_error(instance_id, e)

    async def _handle_instance_error(self, instance_id: str, error: Exception):
        """处理实例错误"""
        with self._lock:
            if instance_id not in self._instance_states:
                return

            self._instance_states[instance_id] = InstanceState.ERROR
            metrics = self._instance_metrics[instance_id]
            metrics.error_count += 1

        self._global_stats["errors_detected"] += 1

        # 执行错误钩子
        await self._execute_hooks(LifecycleEvent.ON_ERROR, instance_id)

        # 检查是否需要重试
        config = self._instance_configs[instance_id]
        if config.retry_on_error and metrics.error_count <= config.max_retry_attempts:
            logger.info(f"Retrying instance {instance_id} after error (attempt {metrics.error_count})")
            await asyncio.sleep(config.retry_delay)
            await self.activate_instance(instance_id)
        else:
            logger.error(f"Instance {instance_id} exceeded max error count, marking for cleanup")
            # 标记为待清理
            asyncio.create_task(self.cleanup_instance(instance_id))

    def get_instance_state(self, instance_id: str) -> Optional[InstanceState]:
        """获取实例状态"""
        with self._lock:
            return self._instance_states.get(instance_id)

    def get_instance_metrics(self, instance_id: str) -> Optional[InstanceMetrics]:
        """获取实例指标"""
        with self._lock:
            return self._instance_metrics.get(instance_id)

    def get_all_instance_states(self) -> Dict[str, InstanceState]:
        """获取所有实例状态"""
        with self._lock:
            return self._instance_states.copy()

    async def cleanup_expired_instances(self, max_inactive_minutes: Optional[int] = None) -> int:
        """清理过期实例"""
        cleaned_count = 0
        now = datetime.now()

        with self._lock:
            expired_instances = []
            for instance_id, metrics in self._instance_metrics.items():
                config = self._instance_configs.get(instance_id, self._default_config)
                inactive_threshold = max_inactive_minutes or config.max_inactive_minutes

                # 检查是否过期
                inactive_time = (now - metrics.last_active_at).total_seconds() / 60
                if inactive_time > inactive_threshold:
                    state = self._instance_states.get(instance_id)
                    if state not in [InstanceState.TERMINATING, InstanceState.TERMINATED]:
                        expired_instances.append(instance_id)

            # 清理过期实例
            for instance_id in expired_instances:
                if await self.cleanup_instance(instance_id):
                    cleaned_count += 1

        if cleaned_count > 0:
            self._global_stats["auto_cleanups_performed"] += cleaned_count
            logger.info(f"Auto-cleaned {cleaned_count} expired instances")

        return cleaned_count

    def get_global_stats(self) -> Dict[str, Any]:
        """获取全局统计信息"""
        with self._lock:
            self._global_stats["total_instances"] = len(self._instance_states)
            self._global_stats["active_instances"] = sum(
                1 for state in self._instance_states.values() if state == InstanceState.ACTIVE
            )
            self._global_stats["error_instances"] = sum(
                1 for state in self._instance_states.values() if state == InstanceState.ERROR
            )
            return self._global_stats.copy()

    def shutdown(self):
        """关闭生命周期管理器"""
        logger.info("Shutting down InstanceLifecycleManager")

        # 停止所有健康检查任务
        for task in self._health_check_tasks.values():
            task.cancel()
        self._health_check_tasks.clear()

        # 清理所有实例
        instance_ids = list(self._instance_states.keys())
        for instance_id in instance_ids:
            asyncio.create_task(self.cleanup_instance(instance_id, force=True))

        logger.info("InstanceLifecycleManager shutdown complete")


# 全局生命周期管理器单例
global_lifecycle_manager = InstanceLifecycleManager()


def get_lifecycle_manager() -> InstanceLifecycleManager:
    """获取全局生命周期管理器单例"""
    return global_lifecycle_manager


# 便捷函数
async def activate_instance(instance_id: str) -> bool:
    """便捷函数：激活实例"""
    return await global_lifecycle_manager.activate_instance(instance_id)


async def deactivate_instance(instance_id: str) -> bool:
    """便捷函数：停用实例"""
    return await global_lifecycle_manager.deactivate_instance(instance_id)


async def cleanup_instance(instance_id: str, force: bool = False) -> bool:
    """便捷函数：清理实例"""
    return await global_lifecycle_manager.cleanup_instance(instance_id, force)


def get_instance_state(instance_id: str) -> Optional[InstanceState]:
    """便捷函数：获取实例状态"""
    return global_lifecycle_manager.get_instance_state(instance_id)
