"""
隔离上下文管理器
实现隔离上下文的生命周期管理、缓存复用、传播和继承机制
"""

import threading
import time
import weakref
from typing import Dict, Optional, List, Set, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
import logging

from .isolation_context import IsolationContext, IsolationScope

logger = logging.getLogger(__name__)


class ContextLifecycleState(Enum):
    """上下文生命周期状态"""

    CREATING = "creating"  # 创建中
    ACTIVE = "active"  # 活跃
    IDLE = "idle"  # 空闲
    EXPIRING = "expiring"  # 过期中
    DESTROYED = "destroyed"  # 已销毁


@dataclass
class ContextMetadata:
    """上下文元数据"""

    created_time: float
    last_accessed_time: float
    access_count: int = 0
    lifecycle_state: ContextLifecycleState = ContextLifecycleState.ACTIVE
    expiration_time: Optional[float] = None
    parent_context_id: Optional[str] = None
    child_context_ids: Set[str] = field(default_factory=set)
    tags: Set[str] = field(default_factory=set)
    custom_data: Dict[str, Any] = field(default_factory=dict)


class IsolationContextManager:
    """增强的隔离上下文管理器"""

    def __init__(self, max_cache_size: int = 1000, default_ttl: float = 3600):
        self._contexts: Dict[str, IsolationContext] = {}
        self._metadata: Dict[str, ContextMetadata] = {}
        self._lock = threading.RLock()
        self._weak_refs: Dict[str, weakref.ref] = {}

        # 配置参数
        self.max_cache_size = max_cache_size
        self.default_ttl = default_ttl

        # 生命周期管理
        self._cleanup_running = False
        self._cleanup_thread: Optional[threading.Thread] = None
        self._cleanup_interval = 300  # 5分钟清理一次

        # 继承关系管理
        self._inheritance_tree: Dict[str, List[str]] = {}

        # 事件回调
        self._lifecycle_callbacks: Dict[str, List[Callable]] = {
            "created": [],
            "accessed": [],
            "expired": [],
            "destroyed": [],
        }

    def create_context(
        self,
        tenant_id: str,
        agent_id: str,
        platform: str = None,
        chat_stream_id: str = None,
        ttl: float = None,
        tags: List[str] = None,
        parent_context: Optional[IsolationContext] = None,
    ) -> IsolationContext:
        """创建隔离上下文"""
        scope = IsolationScope(tenant_id, agent_id, platform, chat_stream_id)
        scope_key = str(scope)

        with self._lock:
            # 检查是否已存在
            existing_context = self._get_existing_context(scope_key)
            if existing_context:
                self._update_access_time(scope_key)
                return existing_context

            # 检查缓存大小
            if len(self._contexts) >= self.max_cache_size:
                self._evict_least_recently_used()

            # 创建新上下文
            context = IsolationContext(tenant_id, agent_id, platform, chat_stream_id)

            # 创建元数据
            current_time = time.time()
            metadata = ContextMetadata(
                created_time=current_time,
                last_accessed_time=current_time,
                access_count=1,
                expiration_time=current_time + (ttl or self.default_ttl),
                tags=set(tags or []),
                parent_context_id=str(parent_context.scope) if parent_context else None,
            )

            # 处理继承关系
            if parent_context:
                parent_key = str(parent_context.scope)
                if parent_key in self._metadata:
                    self._metadata[parent_key].child_context_ids.add(scope_key)
                    self._inheritance_tree.setdefault(parent_key, []).append(scope_key)

            # 存储上下文
            self._contexts[scope_key] = context
            self._metadata[scope_key] = metadata
            self._weak_refs[scope_key] = weakref.ref(context)

            # 触发创建事件
            self._trigger_lifecycle_event("created", context, metadata)

            # 启动清理线程（如果尚未启动）
            self._ensure_cleanup_thread_running()

            return context

    def get_context(
        self, tenant_id: str, agent_id: str, platform: str = None, chat_stream_id: str = None, auto_create: bool = True
    ) -> Optional[IsolationContext]:
        """获取隔离上下文"""
        scope = IsolationScope(tenant_id, agent_id, platform, chat_stream_id)
        scope_key = str(scope)

        with self._lock:
            context = self._get_existing_context(scope_key)
            if context:
                self._update_access_time(scope_key)
                return context

            if auto_create:
                return self.create_context(tenant_id, agent_id, platform, chat_stream_id)

            return None

    def get_context_by_scope(self, scope: IsolationScope) -> Optional[IsolationContext]:
        """通过隔离范围获取上下文"""
        scope_key = str(scope)
        return self._get_existing_context(scope_key)

    def get_context_by_id(self, context_id: str) -> Optional[IsolationContext]:
        """通过ID获取上下文"""
        return self._get_existing_context(context_id)

    def create_child_context(
        self,
        parent_context: IsolationContext,
        platform: str = None,
        chat_stream_id: str = None,
        ttl: float = None,
        tags: List[str] = None,
    ) -> IsolationContext:
        """创建子上下文"""
        return self.create_context(
            tenant_id=parent_context.tenant_id,
            agent_id=parent_context.agent_id,
            platform=platform or parent_context.platform,
            chat_stream_id=chat_stream_id,
            ttl=ttl,
            tags=tags,
            parent_context=parent_context,
        )

    def get_child_contexts(self, parent_context: IsolationContext) -> List[IsolationContext]:
        """获取子上下文列表"""
        parent_key = str(parent_context.scope)
        child_contexts = []

        with self._lock:
            child_keys = list(self._inheritance_tree.get(parent_key, []))
            for child_key in child_keys:
                child_context = self._get_existing_context(child_key)
                if child_context:
                    child_contexts.append(child_context)

        return child_contexts

    def get_context_hierarchy(self, context: IsolationContext) -> List[IsolationContext]:
        """获取上下文层次结构"""
        hierarchy = [context]
        current_key = str(context.scope)

        with self._lock:
            # 向上查找父上下文
            while current_key in self._metadata:
                parent_key = self._metadata[current_key].parent_context_id
                if not parent_key or parent_key not in self._contexts:
                    break

                parent_context = self._contexts[parent_key]
                hierarchy.insert(0, parent_context)
                current_key = parent_key

        return hierarchy

    def update_context_tags(self, context: IsolationContext, tags: List[str]):
        """更新上下文标签"""
        scope_key = str(context.scope)
        with self._lock:
            if scope_key in self._metadata:
                self._metadata[scope_key].tags.update(tags)

    def add_custom_data(self, context: IsolationContext, key: str, value: Any):
        """添加自定义数据"""
        scope_key = str(context.scope)
        with self._lock:
            if scope_key in self._metadata:
                self._metadata[scope_key].custom_data[key] = value

    def get_custom_data(self, context: IsolationContext, key: str) -> Any:
        """获取自定义数据"""
        scope_key = str(context.scope)
        with self._lock:
            if scope_key in self._metadata:
                return self._metadata[scope_key].custom_data.get(key)
        return None

    def find_contexts_by_tag(self, tag: str) -> List[IsolationContext]:
        """通过标签查找上下文"""
        matching_contexts = []

        with self._lock:
            for scope_key, metadata in self._metadata.items():
                if tag in metadata.tags:
                    context = self._get_existing_context(scope_key)
                    if context:
                        matching_contexts.append(context)

        return matching_contexts

    def extend_context_ttl(self, context: IsolationContext, additional_ttl: float):
        """扩展上下文TTL"""
        scope_key = str(context.scope)
        with self._lock:
            if scope_key in self._metadata:
                self._metadata[scope_key].expiration_time = self._metadata[scope_key].expiration_time + additional_ttl

    def invalidate_context(self, context: IsolationContext):
        """使上下文失效"""
        scope_key = str(context.scope)
        with self._lock:
            if scope_key in self._metadata:
                self._metadata[scope_key].lifecycle_state = ContextLifecycleState.EXPIRING
                self._metadata[scope_key].expiration_time = time.time()

    def clear_tenant_contexts(self, tenant_id: str):
        """清理指定租户的所有上下文"""
        with self._lock:
            keys_to_remove = []
            for key, context in self._contexts.items():
                if context.tenant_id == tenant_id:
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                self._remove_context(key)

    def clear_expired_contexts(self) -> int:
        """清理过期上下文，返回清理的数量"""
        current_time = time.time()
        keys_to_remove = []

        with self._lock:
            for key, metadata in self._metadata.items():
                if (
                    metadata.expiration_time and metadata.expiration_time < current_time
                ) or metadata.lifecycle_state == ContextLifecycleState.DESTROYED:
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                self._remove_context(key)

        return len(keys_to_remove)

    def get_context_statistics(self) -> Dict[str, Any]:
        """获取上下文统计信息"""
        with self._lock:
            stats = {
                "total_contexts": len(self._contexts),
                "active_contexts": 0,
                "idle_contexts": 0,
                "expired_contexts": 0,
                "contexts_by_tenant": {},
                "contexts_by_platform": {},
                "average_access_count": 0,
                "oldest_context_age": 0,
                "newest_context_age": 0,
            }

            if not self._contexts:
                return stats

            current_time = time.time()
            access_counts = []
            creation_times = []

            for key, metadata in self._metadata.items():
                # 统计状态
                if metadata.lifecycle_state == ContextLifecycleState.ACTIVE:
                    stats["active_contexts"] += 1
                elif metadata.lifecycle_state == ContextLifecycleState.IDLE:
                    stats["idle_contexts"] += 1
                elif metadata.expiration_time and metadata.expiration_time < current_time:
                    stats["expired_contexts"] += 1

                # 统计租户和平台
                context = self._contexts.get(key)
                if context:
                    tenant_id = context.tenant_id
                    platform = context.platform or "unknown"

                    stats["contexts_by_tenant"][tenant_id] = stats["contexts_by_tenant"].get(tenant_id, 0) + 1
                    stats["contexts_by_platform"][platform] = stats["contexts_by_platform"].get(platform, 0) + 1

                # 统计访问次数和创建时间
                access_counts.append(metadata.access_count)
                creation_times.append(metadata.created_time)

            if access_counts:
                stats["average_access_count"] = sum(access_counts) / len(access_counts)
                oldest_time = min(creation_times)
                newest_time = max(creation_times)
                stats["oldest_context_age"] = current_time - oldest_time
                stats["newest_context_age"] = current_time - newest_time

        return stats

    def add_lifecycle_callback(self, event: str, callback: Callable):
        """添加生命周期回调"""
        if event in self._lifecycle_callbacks:
            self._lifecycle_callbacks[event].append(callback)

    def shutdown(self):
        """关闭管理器"""
        self._cleanup_running = False
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=5)

        # 清理所有上下文
        with self._lock:
            keys_to_remove = list(self._contexts.keys())
            for key in keys_to_remove:
                self._remove_context(key)

    # 私有方法
    def _get_existing_context(self, scope_key: str) -> Optional[IsolationContext]:
        """获取现有上下文"""
        # 检查弱引用
        if scope_key in self._weak_refs:
            context_ref = self._weak_refs[scope_key]
            context = context_ref()
            if context is not None:
                return context
            else:
                # 清理无效的弱引用
                del self._weak_refs[scope_key]
                if scope_key in self._contexts:
                    del self._contexts[scope_key]
                if scope_key in self._metadata:
                    del self._metadata[scope_key]

        return None

    def _update_access_time(self, scope_key: str):
        """更新访问时间"""
        if scope_key in self._metadata:
            self._metadata[scope_key].last_accessed_time = time.time()
            self._metadata[scope_key].access_count += 1

            # 触发访问事件
            context = self._contexts.get(scope_key)
            if context:
                self._trigger_lifecycle_event("accessed", context, self._metadata[scope_key])

    def _evict_least_recently_used(self):
        """驱逐最少使用的上下文"""
        if not self._metadata:
            return

        # 找到最少使用的上下文
        lru_key = min(self._metadata.keys(), key=lambda k: self._metadata[k].last_accessed_time)

        self._remove_context(lru_key)

    def _remove_context(self, scope_key: str):
        """移除上下文"""
        context = self._contexts.get(scope_key)
        metadata = self._metadata.get(scope_key)

        if context and metadata:
            # 触发销毁事件
            self._trigger_lifecycle_event("destroyed", context, metadata)

        # 清理数据
        self._contexts.pop(scope_key, None)
        self._metadata.pop(scope_key, None)
        self._weak_refs.pop(scope_key, None)

        # 清理继承关系
        if scope_key in self._inheritance_tree:
            del self._inheritance_tree[scope_key]

        # 从父上下文的子列表中移除
        if metadata and metadata.parent_context_id:
            parent_key = metadata.parent_context_id
            if parent_key in self._metadata:
                self._metadata[parent_key].child_context_ids.discard(scope_key)
            if parent_key in self._inheritance_tree:
                self._inheritance_tree[parent_key] = [
                    child for child in self._inheritance_tree[parent_key] if child != scope_key
                ]

    def _trigger_lifecycle_event(self, event: str, context: IsolationContext, metadata: ContextMetadata):
        """触发生命周期事件"""
        try:
            for callback in self._lifecycle_callbacks.get(event, []):
                callback(context, metadata)
        except Exception as e:
            logger.error(f"触发生命周期事件失败 {event}: {e}")

    def _ensure_cleanup_thread_running(self):
        """确保清理线程正在运行"""
        if not self._cleanup_running:
            self._cleanup_running = True
            self._cleanup_thread = threading.Thread(target=self._cleanup_worker, daemon=True)
            self._cleanup_thread.start()

    def _cleanup_worker(self):
        """清理工作线程"""
        while self._cleanup_running:
            try:
                cleared_count = self.clear_expired_contexts()
                if cleared_count > 0:
                    logger.info(f"清理了 {cleared_count} 个过期上下文")

                time.sleep(self._cleanup_interval)
            except Exception as e:
                logger.error(f"清理线程出错: {e}")
                time.sleep(self._cleanup_interval)


# 全局管理器实例
_global_context_manager = IsolationContextManager()


def get_isolation_context_manager() -> IsolationContextManager:
    """获取全局隔离上下文管理器"""
    return _global_context_manager


def shutdown_global_context_manager():
    """关闭全局上下文管理器"""
    _global_context_manager.shutdown()
