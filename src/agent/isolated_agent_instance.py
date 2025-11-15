"""
智能体实例管理
支持T+A维度的隔离化智能体实例管理
"""

from typing import Dict, Any, Optional, List, Callable
import threading
import weakref
import asyncio
from datetime import datetime, timedelta

from src.agent.agent import Agent
from src.isolation.isolation_context import IsolationContext, create_isolation_context


class IsolatedAgentInstance:
    """隔离化的智能体实例

    每个租户+智能体组合拥有独立的实例，支持隔离化的状态管理
    """

    def __init__(self, agent: Agent, tenant_id: str, isolation_context: IsolationContext):
        self.agent = agent
        self.tenant_id = tenant_id
        self.isolation_context = isolation_context

        # 实例状态
        self.is_active = False
        self.created_at = datetime.utcnow()
        self.last_activity = self.created_at
        self.usage_count = 0

        # 隔离化的状态数据
        self._instance_state: Dict[str, Any] = {}
        self._state_lock = threading.RLock()

        # 资源管理
        self._resources: Dict[str, Any] = {}
        self._resource_lock = threading.RLock()

        # 事件回调
        self._event_callbacks: Dict[str, List[Callable]] = {}

    def activate(self):
        """激活智能体实例"""
        self.is_active = True
        self.last_activity = datetime.utcnow()
        self._trigger_event("activated")

    def deactivate(self):
        """停用智能体实例"""
        self.is_active = False
        self._trigger_event("deactivated")

    def update_activity(self):
        """更新活动时间"""
        self.last_activity = datetime.utcnow()
        self.usage_count += 1

    def set_state(self, key: str, value: Any):
        """设置实例状态（隔离化）"""
        with self._state_lock:
            self._instance_state[key] = value
            self.update_activity()

    def get_state(self, key: str, default: Any = None) -> Any:
        """获取实例状态"""
        with self._state_lock:
            return self._instance_state.get(key, default)

    def clear_state(self, key: Optional[str] = None):
        """清理实例状态"""
        with self._state_lock:
            if key is None:
                self._instance_state.clear()
            elif key in self._instance_state:
                del self._instance_state[key]

    def add_resource(self, resource_id: str, resource: Any):
        """添加实例资源"""
        with self._resource_lock:
            self._resources[resource_id] = resource
            self.update_activity()

    def get_resource(self, resource_id: str) -> Optional[Any]:
        """获取实例资源"""
        with self._resource_lock:
            return self._resources.get(resource_id)

    def remove_resource(self, resource_id: str) -> bool:
        """移除实例资源"""
        with self._resource_lock:
            if resource_id in self._resources:
                del self._resources[resource_id]
                return True
            return False

    def clear_resources(self):
        """清理所有资源"""
        with self._resource_lock:
            self._resources.clear()

    def add_event_callback(self, event_type: str, callback: Callable):
        """添加事件回调"""
        if event_type not in self._event_callbacks:
            self._event_callbacks[event_type] = []
        self._event_callbacks[event_type].append(callback)

    def remove_event_callback(self, event_type: str, callback: Callable):
        """移除事件回调"""
        if event_type in self._event_callbacks:
            try:
                self._event_callbacks[event_type].remove(callback)
            except ValueError:
                pass

    def _trigger_event(self, event_type: str, *args, **kwargs):
        """触发事件"""
        if event_type in self._event_callbacks:
            for callback in self._event_callbacks[event_type]:
                try:
                    callback(self, *args, **kwargs)
                except Exception:
                    pass  # 忽略回调中的错误

    def get_instance_info(self) -> Dict[str, Any]:
        """获取实例信息"""
        with self._state_lock, self._resource_lock:
            return {
                "agent_id": self.agent.agent_id,
                "tenant_id": self.tenant_id,
                "is_active": self.is_active,
                "created_at": self.created_at.isoformat(),
                "last_activity": self.last_activity.isoformat(),
                "usage_count": self.usage_count,
                "state_keys": list(self._instance_state.keys()),
                "resource_count": len(self._resources),
                "resource_ids": list(self._resources.keys()),
                "isolation_scope": str(self.isolation_context.scope),
            }

    def is_expired(self, max_inactive_minutes: int = 30) -> bool:
        """检查实例是否过期"""
        inactive_time = datetime.utcnow() - self.last_activity
        return inactive_time > timedelta(minutes=max_inactive_minutes)

    async def cleanup(self):
        """清理实例资源"""
        # 停用实例
        self.deactivate()

        # 清理状态
        self.clear_state()

        # 清理资源
        self.clear_resources()

        # 清理回调
        self._event_callbacks.clear()


class IsolatedAgentInstanceManager:
    """隔离化智能体实例管理器"""

    def __init__(self):
        self._instances: Dict[str, IsolatedAgentInstance] = {}
        self._lock = threading.RLock()
        self._weak_refs: Dict[str, weakref.ref] = {}

        # 自动清理任务
        self._cleanup_task: Optional[asyncio.Task] = None
        self._cleanup_interval = 300  # 5分钟
        self._max_inactive_minutes = 30

    def get_or_create_instance(self, agent: Agent, tenant_id: str) -> IsolatedAgentInstance:
        """获取或创建智能体实例"""
        instance_key = f"{tenant_id}:{agent.agent_id}"

        with self._lock:
            # 检查弱引用
            if instance_key in self._weak_refs:
                instance_ref = self._weak_refs[instance_key]
                instance = instance_ref()
                if instance is not None and not instance.is_expired(self._max_inactive_minutes):
                    return instance

            # 创建隔离上下文
            isolation_context = create_isolation_context(tenant_id, agent.agent_id)

            # 创建新实例
            instance = IsolatedAgentInstance(agent, tenant_id, isolation_context)

            # 存储实例
            self._instances[instance_key] = instance
            self._weak_refs[instance_key] = weakref.ref(instance)

            # 启动自动清理任务
            self._start_cleanup_task()

            return instance

    def get_instance(self, tenant_id: str, agent_id: str) -> Optional[IsolatedAgentInstance]:
        """获取智能体实例"""
        instance_key = f"{tenant_id}:{agent_id}"

        with self._lock:
            instance_ref = self._weak_refs.get(instance_key)
            if instance_ref:
                return instance_ref()
            return None

    def remove_instance(self, tenant_id: str, agent_id: str) -> bool:
        """移除智能体实例"""
        instance_key = f"{tenant_id}:{agent_id}"

        with self._lock:
            instance = None
            if instance_key in self._instances:
                instance = self._instances.get(instance_key)
                del self._instances[instance_key]

            if instance_key in self._weak_refs:
                del self._weak_refs[instance_key]

            if instance:
                # 异步清理
                asyncio.create_task(instance.cleanup())
                return True

            return False

    def clear_tenant_instances(self, tenant_id: str) -> int:
        """清理租户的所有实例"""
        removed_count = 0
        instance_keys_to_remove = []

        with self._lock:
            for instance_key in self._instances.keys():
                if instance_key.startswith(f"{tenant_id}:"):
                    instance_keys_to_remove.append(instance_key)

            for instance_key in instance_keys_to_remove:
                if self.remove_instance(instance_key.split(":", 1)[0], instance_key.split(":", 1)[1]):
                    removed_count += 1

        return removed_count

    def clear_all_instances(self):
        """清理所有实例"""
        with self._lock:
            instances = list(self._instances.values())
            self._instances.clear()
            self._weak_refs.clear()

        # 异步清理所有实例
        for instance in instances:
            asyncio.create_task(instance.cleanup())

    def get_instance_stats(self) -> Dict[str, Any]:
        """获取实例统计信息"""
        self._cleanup_expired_instances()

        stats = {
            "total_instances": len(self._instances),
            "active_instances": 0,
            "expired_instances": 0,
            "instances_by_tenant": {},
            "instances": {},
        }

        with self._lock:
            for instance_key, instance in self._instances.items():
                if instance:
                    tenant_id = instance.tenant_id

                    # 统计活跃/过期实例
                    if instance.is_active:
                        stats["active_instances"] += 1
                    if instance.is_expired(self._max_inactive_minutes):
                        stats["expired_instances"] += 1

                    # 按租户统计
                    if tenant_id not in stats["instances_by_tenant"]:
                        stats["instances_by_tenant"][tenant_id] = {"count": 0, "active": 0, "inactive": 0}

                    stats["instances_by_tenant"][tenant_id]["count"] += 1
                    if instance.is_active:
                        stats["instances_by_tenant"][tenant_id]["active"] += 1
                    else:
                        stats["instances_by_tenant"][tenant_id]["inactive"] += 1

                    # 实例详细信息
                    stats["instances"][instance_key] = instance.get_instance_info()

        return stats

    def _start_cleanup_task(self):
        """启动自动清理任务"""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self):
        """自动清理循环"""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                self._cleanup_expired_instances()
            except asyncio.CancelledError:
                break
            except Exception:
                pass  # 忽略清理过程中的错误

    def _cleanup_expired_instances(self):
        """清理过期实例"""
        expired_keys = []

        with self._lock:
            for instance_key, instance in list(self._instances.items()):
                if instance and instance.is_expired(self._max_inactive_minutes):
                    expired_keys.append(instance_key)

            for instance_key in expired_keys:
                tenant_id, agent_id = instance_key.split(":", 1)
                self.remove_instance(tenant_id, agent_id)

    def set_cleanup_interval(self, seconds: int):
        """设置清理间隔"""
        self._cleanup_interval = seconds

    def set_max_inactive_minutes(self, minutes: int):
        """设置最大不活跃时间"""
        self._max_inactive_minutes = minutes

    async def shutdown(self):
        """关闭实例管理器"""
        # 停止清理任务
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # 清理所有实例
        self.clear_all_instances()


# 全局实例管理器
_global_instance_manager = IsolatedAgentInstanceManager()


def get_global_instance_manager() -> IsolatedAgentInstanceManager:
    """获取全局实例管理器"""
    return _global_instance_manager


def get_agent_instance(agent: Agent, tenant_id: str) -> IsolatedAgentInstance:
    """获取智能体实例的便捷函数"""
    return _global_instance_manager.get_or_create_instance(agent, tenant_id)


def get_tenant_agent_instance(tenant_id: str, agent_id: str) -> Optional[IsolatedAgentInstance]:
    """获取租户智能体实例的便捷函数"""
    return _global_instance_manager.get_instance(tenant_id, agent_id)


def remove_agent_instance(tenant_id: str, agent_id: str) -> bool:
    """移除智能体实例的便捷函数"""
    return _global_instance_manager.remove_instance(tenant_id, agent_id)


def clear_tenant_agent_instances(tenant_id: str) -> int:
    """清理租户所有智能体实例的便捷函数"""
    return _global_instance_manager.clear_tenant_instances(tenant_id)


def get_instance_management_stats() -> Dict[str, Any]:
    """获取实例管理统计信息的便捷函数"""
    return _global_instance_manager.get_instance_stats()
