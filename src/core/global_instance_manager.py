"""
全局实例管理器 - 多租户隔离架构的核心组件

按T+A+C维度管理各种实例，支持租户资源的统一管理和清理。

主要功能：
1. 按租户+智能体+聊天流维度管理实例
2. 支持实例的自动创建、缓存和清理
3. 提供租户级别的资源管理
4. 支持实例的批量操作和统计
"""

import asyncio
import weakref
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable, TypeVar
from dataclasses import dataclass, field
from collections import defaultdict
from contextlib import contextmanager
import logging
import gc

from src.isolation.isolation_context import IsolationContext, create_isolation_context

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class InstanceInfo:
    """实例信息"""

    instance_id: str
    instance_type: str
    tenant_id: str
    agent_id: str
    chat_stream_id: Optional[str] = None
    platform: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def update_access(self):
        """更新访问信息"""
        self.last_accessed = datetime.now()
        self.access_count += 1

    def is_expired(self, max_inactive_minutes: int = 30) -> bool:
        """检查实例是否过期"""
        if not self.is_active:
            return True
        inactive_time = datetime.now() - self.last_accessed
        return inactive_time > timedelta(minutes=max_inactive_minutes)


class GlobalInstanceManager:
    """
    全局实例管理器

    按T+A+C维度管理实例，支持多租户隔离和资源管理。
    使用弱引用避免内存泄漏，支持自动清理过期实例。
    """

    _instance: Optional["GlobalInstanceManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "GlobalInstanceManager":
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

        # 按T+A+C维度分层的实例存储
        self._instances: Dict[str, Dict[str, Dict[str, Dict[str, weakref.ref]]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(dict))
        )

        # 实例信息存储
        self._instance_info: Dict[str, InstanceInfo] = {}

        # 实例工厂函数注册
        self._factories: Dict[str, Callable] = {}

        # 清理任务
        self._cleanup_task: Optional[asyncio.Task] = None
        self._cleanup_interval = 300  # 5分钟清理一次
        self._max_inactive_minutes = 30

        # 统计信息
        self._stats = {
            "total_instances": 0,
            "active_instances": 0,
            "tenants_count": 0,
            "agents_count": 0,
            "chats_count": 0,
            "cleanup_runs": 0,
            "last_cleanup": None,
        }

        # 启动清理任务
        self._start_cleanup_task()

        logger.info("GlobalInstanceManager initialized")

    def _get_instance_key(
        self,
        instance_type: str,
        tenant_id: str,
        agent_id: str,
        chat_stream_id: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> str:
        """生成实例键"""
        if chat_stream_id:
            return f"{instance_type}:{tenant_id}:{agent_id}:{chat_stream_id}"
        elif platform:
            return f"{instance_type}:{tenant_id}:{agent_id}:{platform}"
        else:
            return f"{instance_type}:{tenant_id}:{agent_id}"

    def _get_isolation_path(self, tenant_id: str, agent_id: str, chat_stream_id: Optional[str] = None) -> tuple:
        """获取隔离路径"""
        if chat_stream_id:
            return (tenant_id, agent_id, chat_stream_id)
        else:
            return (tenant_id, agent_id, "global")

    def register_factory(self, instance_type: str, factory_func: Callable) -> None:
        """
        注册实例工厂函数

        Args:
            instance_type: 实例类型
            factory_func: 工厂函数，签名为 (tenant_id, agent_id, chat_stream_id, **kwargs) -> instance
        """
        with self._lock:
            self._factories[instance_type] = factory_func
            logger.info(f"Registered factory for instance type: {instance_type}")

    def get_isolated_instance(
        self,
        instance_type: str,
        tenant_id: str,
        agent_id: str,
        chat_stream_id: Optional[str] = None,
        platform: Optional[str] = None,
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
            **kwargs: 其他参数

        Returns:
            实例对象或None
        """
        instance_key = self._get_instance_key(instance_type, tenant_id, agent_id, chat_stream_id, platform)

        with self._lock:
            # 尝试从缓存获取
            tenant_path, agent_path, chat_path = self._get_isolation_path(tenant_id, agent_id, chat_stream_id)

            if instance_key in self._instances[tenant_path][agent_path][chat_path]:
                weak_ref = self._instances[tenant_path][agent_path][chat_path][instance_key]
                instance = weak_ref()
                if instance is not None:
                    # 更新访问信息
                    if instance_key in self._instance_info:
                        self._instance_info[instance_key].update_access()
                    return instance
                else:
                    # 弱引用已失效，清理
                    del self._instances[tenant_path][agent_path][chat_path][instance_key]
                    if instance_key in self._instance_info:
                        del self._instance_info[instance_key]

            # 创建新实例
            if instance_type not in self._factories:
                logger.error(f"No factory registered for instance type: {instance_type}")
                return None

            try:
                factory = self._factories[instance_type]
                instance = factory(tenant_id, agent_id, chat_stream_id, platform=platform, **kwargs)

                if instance is None:
                    logger.error(f"Factory returned None for instance type: {instance_type}")
                    return None

                # 存储弱引用
                weak_ref = weakref.ref(instance)
                self._instances[tenant_path][agent_path][chat_path][instance_key] = weak_ref

                # 存储实例信息
                instance_info = InstanceInfo(
                    instance_id=instance_key,
                    instance_type=instance_type,
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    chat_stream_id=chat_stream_id,
                    platform=platform,
                    metadata=kwargs.copy(),
                )
                self._instance_info[instance_key] = instance_info

                # 更新统计
                self._update_stats()

                logger.debug(f"Created new instance: {instance_key}")
                return instance

            except Exception as e:
                logger.error(f"Failed to create instance {instance_key}: {e}")
                return None

    def create_isolation_context(
        self, tenant_id: str, agent_id: str, platform: Optional[str] = None, chat_stream_id: Optional[str] = None
    ) -> IsolationContext:
        """
        创建隔离上下文

        Args:
            tenant_id: 租户ID
            agent_id: 智能体ID
            platform: 平台
            chat_stream_id: 聊天流ID

        Returns:
            隔离上下文
        """
        return create_isolation_context(tenant_id, agent_id, platform, chat_stream_id)

    def get_instance_info(
        self,
        instance_type: Optional[str] = None,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        chat_stream_id: Optional[str] = None,
    ) -> List[InstanceInfo]:
        """
        获取实例信息

        Args:
            instance_type: 实例类型过滤
            tenant_id: 租户ID过滤
            agent_id: 智能体ID过滤
            chat_stream_id: 聊天流ID过滤

        Returns:
            实例信息列表
        """
        with self._lock:
            result = []
            for info in self._instance_info.values():
                # 应用过滤条件
                if instance_type and info.instance_type != instance_type:
                    continue
                if tenant_id and info.tenant_id != tenant_id:
                    continue
                if agent_id and info.agent_id != agent_id:
                    continue
                if chat_stream_id and info.chat_stream_id != chat_stream_id:
                    continue

                result.append(info)

            return result

    def get_tenant_instances(self, tenant_id: str) -> Dict[str, List[InstanceInfo]]:
        """
        获取租户的所有实例

        Args:
            tenant_id: 租户ID

        Returns:
            按类型分组的实例信息
        """
        instances_by_type = defaultdict(list)

        for info in self.get_instance_info(tenant_id=tenant_id):
            instances_by_type[info.instance_type].append(info)

        return dict(instances_by_type)

    def clear_tenant_instances(self, tenant_id: str, instance_type: Optional[str] = None) -> int:
        """
        清理租户的实例

        Args:
            tenant_id: 租户ID
            instance_type: 实例类型，None表示清理所有类型

        Returns:
            清理的实例数量
        """
        cleared_count = 0

        with self._lock:
            # 找到要清理的实例
            to_remove = []
            for instance_key, info in self._instance_info.items():
                if info.tenant_id == tenant_id:
                    if instance_type is None or info.instance_type == instance_type:
                        to_remove.append(instance_key)

            # 清理实例
            for instance_key in to_remove:
                info = self._instance_info[instance_key]
                tenant_path, agent_path, chat_path = self._get_isolation_path(
                    info.tenant_id, info.agent_id, info.chat_stream_id
                )

                # 从实例存储中删除
                if instance_key in self._instances[tenant_path][agent_path][chat_path]:
                    del self._instances[tenant_path][agent_path][chat_path][instance_key]

                # 删除实例信息
                del self._instance_info[instance_key]
                cleared_count += 1

            # 清理空的字典
            self._cleanup_empty_dicts()

            # 更新统计
            self._update_stats()

            logger.info(f"Cleared {cleared_count} instances for tenant: {tenant_id}")

            # 强制垃圾回收
            gc.collect()

        return cleared_count

    def clear_expired_instances(self, max_inactive_minutes: Optional[int] = None) -> int:
        """
        清理过期的实例

        Args:
            max_inactive_minutes: 最大非活跃分钟数，None使用默认值

        Returns:
            清理的实例数量
        """
        if max_inactive_minutes is None:
            max_inactive_minutes = self._max_inactive_minutes

        cleared_count = 0

        with self._lock:
            # 找到过期的实例
            to_remove = []
            for instance_key, info in self._instance_info.items():
                if info.is_expired(max_inactive_minutes):
                    to_remove.append(instance_key)

            # 清理过期实例
            for instance_key in to_remove:
                info = self._instance_info[instance_key]
                tenant_path, agent_path, chat_path = self._get_isolation_path(
                    info.tenant_id, info.agent_id, info.chat_stream_id
                )

                # 从实例存储中删除
                if instance_key in self._instances[tenant_path][agent_path][chat_path]:
                    del self._instances[tenant_path][agent_path][chat_path][instance_key]

                # 删除实例信息
                del self._instance_info[instance_key]
                cleared_count += 1

            # 清理空的字典
            self._cleanup_empty_dicts()

            # 更新统计
            self._update_stats()

            self._stats["cleanup_runs"] += 1
            self._stats["last_cleanup"] = datetime.now()

            if cleared_count > 0:
                logger.info(f"Cleared {cleared_count} expired instances")

            # 强制垃圾回收
            gc.collect()

        return cleared_count

    def _cleanup_empty_dicts(self):
        """清理空的字典"""
        # 清理聊天流级别
        for tenant_id in list(self._instances.keys()):
            for agent_id in list(self._instances[tenant_id].keys()):
                for chat_id in list(self._instances[tenant_id][agent_id].keys()):
                    if not self._instances[tenant_id][agent_id][chat_id]:
                        del self._instances[tenant_id][agent_id][chat_id]

                if not self._instances[tenant_id][agent_id]:
                    del self._instances[tenant_id][agent_id]

            if not self._instances[tenant_id]:
                del self._instances[tenant_id]

    def _update_stats(self):
        """更新统计信息"""
        self._stats["total_instances"] = len(self._instance_info)
        self._stats["active_instances"] = sum(1 for info in self._instance_info.values() if info.is_active)
        self._stats["tenants_count"] = len(set(info.tenant_id for info in self._instance_info.values()))
        self._stats["agents_count"] = len(set((info.tenant_id, info.agent_id) for info in self._instance_info.values()))
        self._stats["chats_count"] = len(
            set(info.chat_stream_id for info in self._instance_info.values() if info.chat_stream_id)
        )

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            self._update_stats()
            return self._stats.copy()

    def _start_cleanup_task(self):
        """启动清理任务"""
        try:
            loop = asyncio.get_event_loop()
            self._cleanup_task = loop.create_task(self._cleanup_loop())
        except RuntimeError:
            # 没有事件循环，跳过
            logger.warning("No event loop available, cleanup task not started")

    async def _cleanup_loop(self):
        """清理循环"""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                self.clear_expired_instances()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup task error: {e}")

    def shutdown(self):
        """关闭管理器"""
        if self._cleanup_task:
            self._cleanup_task.cancel()

        # 清理所有实例
        with self._lock:
            self._instances.clear()
            self._instance_info.clear()
            self._factories.clear()

        logger.info("GlobalInstanceManager shutdown")

    @contextmanager
    def temporary_instance(
        self, instance_type: str, tenant_id: str, agent_id: str, chat_stream_id: Optional[str] = None, **kwargs
    ):
        """
        临时实例上下文管理器

        Args:
            instance_type: 实例类型
            tenant_id: 租户ID
            agent_id: 智能体ID
            chat_stream_id: 聊天流ID
            **kwargs: 其他参数
        """
        instance = self.get_isolated_instance(instance_type, tenant_id, agent_id, chat_stream_id, **kwargs)
        try:
            yield instance
        finally:
            # 上下文结束后自动清理
            if instance and chat_stream_id:
                instance_key = self._get_instance_key(instance_type, tenant_id, agent_id, chat_stream_id)
                with self._lock:
                    if instance_key in self._instance_info:
                        tenant_path, agent_path, chat_path = self._get_isolation_path(
                            tenant_id, agent_id, chat_stream_id
                        )

                        if instance_key in self._instances[tenant_path][agent_path][chat_path]:
                            del self._instances[tenant_path][agent_path][chat_path][instance_key]
                        del self._instance_info[instance_key]


# 全局实例管理器单例
global_instance_manager = GlobalInstanceManager()


def get_global_instance_manager() -> GlobalInstanceManager:
    """获取全局实例管理器单例"""
    return global_instance_manager


# 便捷函数
def get_isolated_instance(
    instance_type: str, tenant_id: str, agent_id: str, chat_stream_id: Optional[str] = None, **kwargs
) -> Optional[T]:
    """便捷函数：获取隔离实例"""
    return global_instance_manager.get_isolated_instance(instance_type, tenant_id, agent_id, chat_stream_id, **kwargs)


def clear_tenant_instances(tenant_id: str, instance_type: Optional[str] = None) -> int:
    """便捷函数：清理租户实例"""
    return global_instance_manager.clear_tenant_instances(tenant_id, instance_type)


def get_tenant_instances(tenant_id: str) -> Dict[str, List[InstanceInfo]]:
    """便捷函数：获取租户实例"""
    return global_instance_manager.get_tenant_instances(tenant_id)


def get_instance_stats() -> Dict[str, Any]:
    """便捷函数：获取实例统计"""
    return global_instance_manager.get_stats()
