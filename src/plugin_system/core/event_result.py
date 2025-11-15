"""
事件结果隔离存储和管理
支持T+A+C+P四维隔离的事件结果存储、查询和聚合
"""

import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict

from src.common.logger import get_logger
from src.isolation.isolation_context import IsolationContext

logger = get_logger("event_result")


class ResultStatus(Enum):
    """结果状态枚举"""

    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    PARTIAL = "partial"


class ResultPriority(Enum):
    """结果优先级枚举"""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class EventResult:
    """隔离化事件结果"""

    # 基本信息
    id: str
    event_type: str
    event_id: str
    isolation_context: IsolationContext

    # 结果数据
    status: ResultStatus
    result_data: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None

    # 处理器信息
    processor_name: str = ""
    processor_id: str = ""
    execution_time: float = 0.0  # 执行时间（秒）

    # 时间信息
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    # 元数据
    priority: ResultPriority = ResultPriority.NORMAL
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # 关联信息
    correlation_id: Optional[str] = None
    parent_result_id: Optional[str] = None
    child_result_ids: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.id:
            self.id = f"{self.event_id}:{self.processor_id}:{int(time.time())}"

    @property
    def is_success(self) -> bool:
        """是否成功"""
        return self.status == ResultStatus.SUCCESS

    @property
    def is_failure(self) -> bool:
        """是否失败"""
        return self.status in [ResultStatus.FAILURE, ResultStatus.TIMEOUT, ResultStatus.CANCELLED]

    @property
    def duration(self) -> Optional[float]:
        """获取处理时长"""
        if self.completed_at:
            return (self.completed_at - self.created_at).total_seconds()
        return None

    @property
    def scope_key(self) -> str:
        """获取范围键"""
        return str(self.isolation_context.scope)

    def add_tag(self, tag: str):
        """添加标签"""
        if tag not in self.tags:
            self.tags.append(tag)

    def has_tag(self, tag: str) -> bool:
        """检查是否包含标签"""
        return tag in self.tags

    def add_child_result(self, child_result_id: str):
        """添加子结果"""
        if child_result_id not in self.child_result_ids:
            self.child_result_ids.append(child_result_id)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        # 转换日期时间为字符串
        data["created_at"] = self.created_at.isoformat()
        if self.completed_at:
            data["completed_at"] = self.completed_at.isoformat()
        # 转换隔离上下文
        data["isolation_context"] = {
            "tenant_id": self.isolation_context.tenant_id,
            "agent_id": self.isolation_context.agent_id,
            "platform": self.isolation_context.platform,
            "chat_stream_id": self.isolation_context.chat_stream_id,
        }
        # 转换枚举
        data["status"] = self.status.value
        data["priority"] = self.priority.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EventResult":
        """从字典创建结果"""
        # 转换隔离上下文
        isolation_data = data.pop("isolation_context")
        isolation_context = IsolationContext(**isolation_data)

        # 转换日期时间
        if isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if data.get("completed_at") and isinstance(data["completed_at"], str):
            data["completed_at"] = datetime.fromisoformat(data["completed_at"])

        # 转换枚举
        data["status"] = ResultStatus(data["status"])
        data["priority"] = ResultPriority(data["priority"])

        return cls(isolation_context=isolation_context, **data)


class EventResultStorage:
    """事件结果存储接口"""

    def __init__(self, max_size: int = 10000, cleanup_interval: int = 300):
        self.max_size = max_size
        self.cleanup_interval = cleanup_interval
        self._storage: Dict[str, EventResult] = {}
        self._by_scope: Dict[str, List[str]] = defaultdict(list)
        self._by_event_type: Dict[str, List[str]] = defaultdict(list)
        self._by_status: Dict[ResultStatus, List[str]] = defaultdict(list)
        self._lock = threading.RLock()
        self._last_cleanup = time.time()

    def store_result(self, result: EventResult) -> bool:
        """存储事件结果"""
        with self._lock:
            try:
                # 检查存储限制
                if len(self._storage) >= self.max_size:
                    self._cleanup_old_results()

                # 存储结果
                self._storage[result.id] = result

                # 更新索引
                self._by_scope[result.scope_key].append(result.id)
                self._by_event_type[result.event_type].append(result.id)
                self._by_status[result.status].append(result.id)

                logger.debug(f"存储事件结果: {result.id}")
                return True

            except Exception as e:
                logger.error(f"存储事件结果失败: {result.id}, 错误: {e}")
                return False

    def get_result(self, result_id: str) -> Optional[EventResult]:
        """获取事件结果"""
        with self._lock:
            return self._storage.get(result_id)

    def get_results_by_scope(
        self,
        isolation_context: IsolationContext,
        limit: Optional[int] = None,
        status_filter: Optional[ResultStatus] = None,
    ) -> List[EventResult]:
        """根据隔离范围获取结果"""
        scope_key = str(isolation_context.scope)
        with self._lock:
            result_ids = self._by_scope.get(scope_key, [])

            if status_filter:
                result_ids = [
                    rid for rid in result_ids if rid in self._storage and self._storage[rid].status == status_filter
                ]

            results = [self._storage[rid] for rid in result_ids if rid in self._storage]

            # 按时间倒序排列
            results.sort(key=lambda r: r.created_at, reverse=True)

            if limit:
                results = results[:limit]

            return results

    def get_results_by_event_type(
        self, event_type: str, isolation_context: Optional[IsolationContext] = None, limit: Optional[int] = None
    ) -> List[EventResult]:
        """根据事件类型获取结果"""
        with self._lock:
            result_ids = self._by_event_type.get(event_type, [])
            results = [self._storage[rid] for rid in result_ids if rid in self._storage]

            # 过滤隔离范围
            if isolation_context:
                results = [r for r in results if r.scope_key == str(isolation_context.scope)]

            # 按时间倒序排列
            results.sort(key=lambda r: r.created_at, reverse=True)

            if limit:
                results = results[:limit]

            return results

    def get_results_by_time_range(
        self,
        start_time: datetime,
        end_time: datetime,
        isolation_context: Optional[IsolationContext] = None,
        event_types: Optional[List[str]] = None,
    ) -> List[EventResult]:
        """根据时间范围获取结果"""
        with self._lock:
            results = []
            for result in self._storage.values():
                # 时间范围过滤
                if not (start_time <= result.created_at <= end_time):
                    continue

                # 隔离范围过滤
                if isolation_context and result.scope_key != str(isolation_context.scope):
                    continue

                # 事件类型过滤
                if event_types and result.event_type not in event_types:
                    continue

                results.append(result)

            # 按时间倒序排列
            results.sort(key=lambda r: r.created_at, reverse=True)
            return results

    def delete_result(self, result_id: str) -> bool:
        """删除事件结果"""
        with self._lock:
            if result_id not in self._storage:
                return False

            result = self._storage.pop(result_id)

            # 更新索引
            self._by_scope[result.scope_key].remove(result_id)
            self._by_event_type[result.event_type].remove(result_id)
            self._by_status[result.status].remove(result_id)

            logger.debug(f"删除事件结果: {result_id}")
            return True

    def clear_results_by_scope(self, isolation_context: IsolationContext) -> int:
        """清理指定隔离范围的结果"""
        scope_key = str(isolation_context.scope)
        with self._lock:
            result_ids = self._by_scope.get(scope_key, []).copy()
            count = 0
            for result_id in result_ids:
                if self.delete_result(result_id):
                    count += 1

            logger.info(f"清理隔离范围 {scope_key} 的 {count} 个事件结果")
            return count

    def _cleanup_old_results(self):
        """清理旧结果"""
        current_time = time.time()
        if current_time - self._last_cleanup < self.cleanup_interval:
            return

        # 清理超过7天的结果
        cutoff_time = datetime.now() - timedelta(days=7)
        old_result_ids = []

        for result_id, result in self._storage.items():
            if result.created_at < cutoff_time:
                old_result_ids.append(result_id)

        for result_id in old_result_ids:
            self.delete_result(result_id)

        self._last_cleanup = current_time
        logger.info(f"清理了 {len(old_result_ids)} 个旧事件结果")

    def get_statistics(self, isolation_context: Optional[IsolationContext] = None) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            stats = {"total_results": len(self._storage), "by_status": {}, "by_event_type": {}, "by_scope": {}}

            results = list(self._storage.values())

            # 过滤隔离范围
            if isolation_context:
                results = [r for r in results if r.scope_key == str(isolation_context.scope)]

            # 按状态统计
            for status in ResultStatus:
                count = sum(1 for r in results if r.status == status)
                stats["by_status"][status.value] = count

            # 按事件类型统计
            event_type_counts = defaultdict(int)
            for result in results:
                event_type_counts[result.event_type] += 1
            stats["by_event_type"] = dict(event_type_counts)

            # 按隔离范围统计
            scope_counts = defaultdict(int)
            for result in results:
                scope_counts[result.scope_key] += 1
            stats["by_scope"] = dict(scope_counts)

            return stats


class EventResultAggregator:
    """事件结果聚合器"""

    def __init__(self, storage: EventResultStorage):
        self.storage = storage

    def aggregate_by_time(
        self,
        isolation_context: IsolationContext,
        interval: str = "hour",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """按时间聚合结果"""
        if not start_time:
            start_time = datetime.now() - timedelta(days=1)
        if not end_time:
            end_time = datetime.now()

        results = self.storage.get_results_by_time_range(start_time, end_time, isolation_context)

        # 按时间间隔分组
        time_groups = defaultdict(list)
        for result in results:
            if interval == "hour":
                key = result.created_at.strftime("%Y-%m-%d %H:00")
            elif interval == "day":
                key = result.created_at.strftime("%Y-%m-%d")
            elif interval == "minute":
                key = result.created_at.strftime("%Y-%m-%d %H:%M")
            else:
                key = result.created_at.strftime("%Y-%m-%d %H:00")

            time_groups[key].append(result)

        # 生成聚合数据
        aggregation = {}
        for time_key, group_results in time_groups.items():
            aggregation[time_key] = {
                "total": len(group_results),
                "success": sum(1 for r in group_results if r.is_success),
                "failure": sum(1 for r in group_results if r.is_failure),
                "avg_execution_time": sum(r.execution_time for r in group_results) / len(group_results)
                if group_results
                else 0,
            }

        return aggregation

    def aggregate_by_event_type(
        self,
        isolation_context: IsolationContext,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """按事件类型聚合结果"""
        if not start_time:
            start_time = datetime.now() - timedelta(days=1)
        if not end_time:
            end_time = datetime.now()

        results = self.storage.get_results_by_time_range(start_time, end_time, isolation_context)

        # 按事件类型分组
        type_groups = defaultdict(list)
        for result in results:
            type_groups[result.event_type].append(result)

        # 生成聚合数据
        aggregation = {}
        for event_type, group_results in type_groups.items():
            aggregation[event_type] = {
                "total": len(group_results),
                "success": sum(1 for r in group_results if r.is_success),
                "failure": sum(1 for r in group_results if r.is_failure),
                "success_rate": sum(1 for r in group_results if r.is_success) / len(group_results)
                if group_results
                else 0,
                "avg_execution_time": sum(r.execution_time for r in group_results) / len(group_results)
                if group_results
                else 0,
                "processors": list(set(r.processor_name for r in group_results)),
            }

        return aggregation

    def aggregate_cross_platform(
        self, tenant_id: str, agent_id: str, event_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """跨平台聚合结果"""
        aggregation = {}

        # 获取租户下的所有平台
        # 这里需要根据实际的平台数据来获取
        # 为了演示，假设有一些平台
        platforms = ["qq", "wechat", "discord"]

        for platform in platforms:
            context = IsolationContext(tenant_id, agent_id, platform)

            if event_types:
                results = []
                for event_type in event_types:
                    results.extend(self.storage.get_results_by_event_type(event_type, context))
            else:
                results = self.storage.get_results_by_scope(context)

            if results:
                aggregation[platform] = {
                    "total": len(results),
                    "success": sum(1 for r in results if r.is_success),
                    "failure": sum(1 for r in results if r.is_failure),
                    "success_rate": sum(1 for r in results if r.is_success) / len(results) if results else 0,
                    "avg_execution_time": sum(r.execution_time for r in results) / len(results) if results else 0,
                }

        return aggregation


class IsolatedEventResultManager:
    """隔离化事件结果管理器"""

    def __init__(self):
        self._storages: Dict[str, EventResultStorage] = {}
        self._aggregators: Dict[str, EventResultAggregator] = {}
        self._lock = threading.RLock()

    def _get_storage_key(self, tenant_id: str, agent_id: str) -> str:
        """获取存储键"""
        return f"{tenant_id}:{agent_id}"

    def get_storage(self, isolation_context: IsolationContext) -> EventResultStorage:
        """获取事件结果存储"""
        storage_key = self._get_storage_key(isolation_context.tenant_id, isolation_context.agent_id)

        with self._lock:
            if storage_key not in self._storages:
                self._storages[storage_key] = EventResultStorage()
                self._aggregators[storage_key] = EventResultAggregator(self._storages[storage_key])

            return self._storages[storage_key]

    def get_aggregator(self, isolation_context: IsolationContext) -> EventResultAggregator:
        """获取事件结果聚合器"""
        storage_key = self._get_storage_key(isolation_context.tenant_id, isolation_context.agent_id)

        with self._lock:
            if storage_key not in self._aggregators:
                storage = self.get_storage(isolation_context)
                self._aggregators[storage_key] = EventResultAggregator(storage)

            return self._aggregators[storage_key]

    def store_result(self, result: EventResult) -> bool:
        """存储事件结果"""
        storage = self.get_storage(result.isolation_context)
        return storage.store_result(result)

    def get_result(self, result_id: str, isolation_context: IsolationContext) -> Optional[EventResult]:
        """获取事件结果"""
        storage = self.get_storage(isolation_context)
        return storage.get_result(result_id)

    def get_results(
        self,
        isolation_context: IsolationContext,
        limit: Optional[int] = None,
        status_filter: Optional[ResultStatus] = None,
    ) -> List[EventResult]:
        """获取事件结果列表"""
        storage = self.get_storage(isolation_context)
        return storage.get_results_by_scope(isolation_context, limit, status_filter)

    def query_results(
        self,
        isolation_context: IsolationContext,
        event_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[EventResult]:
        """查询事件结果"""
        storage = self.get_storage(isolation_context)

        if event_type:
            return storage.get_results_by_event_type(event_type, isolation_context, limit)
        elif start_time and end_time:
            return storage.get_results_by_time_range(
                start_time, end_time, isolation_context, [event_type] if event_type else None
            )
        else:
            return storage.get_results_by_scope(isolation_context, limit)

    def delete_result(self, result_id: str, isolation_context: IsolationContext) -> bool:
        """删除事件结果"""
        storage = self.get_storage(isolation_context)
        return storage.delete_result(result_id)

    def clear_results(self, isolation_context: IsolationContext) -> int:
        """清理事件结果"""
        storage = self.get_storage(isolation_context)
        return storage.clear_results_by_scope(isolation_context)

    def get_statistics(self, isolation_context: IsolationContext) -> Dict[str, Any]:
        """获取统计信息"""
        storage = self.get_storage(isolation_context)
        return storage.get_statistics(isolation_context)

    def aggregate_results(
        self, isolation_context: IsolationContext, aggregation_type: str = "time", **kwargs
    ) -> Dict[str, Any]:
        """聚合事件结果"""
        aggregator = self.get_aggregator(isolation_context)

        if aggregation_type == "time":
            return aggregator.aggregate_by_time(isolation_context, **kwargs)
        elif aggregation_type == "event_type":
            return aggregator.aggregate_by_event_type(isolation_context, **kwargs)
        elif aggregation_type == "cross_platform":
            return aggregator.aggregate_cross_platform(
                isolation_context.tenant_id, isolation_context.agent_id, **kwargs
            )
        else:
            raise ValueError(f"不支持的聚合类型: {aggregation_type}")

    def cleanup_tenant_results(self, tenant_id: str):
        """清理租户的所有结果"""
        with self._lock:
            keys_to_remove = []
            for key in self._storages.keys():
                if key.startswith(f"{tenant_id}:"):
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                del self._storages[key]
                if key in self._aggregators:
                    del self._aggregators[key]

            logger.info(f"已清理租户 {tenant_id} 的所有事件结果")


# 全局管理器实例
_global_result_manager = IsolatedEventResultManager()


def get_isolated_result_manager() -> IsolatedEventResultManager:
    """获取全局隔离化事件结果管理器"""
    return _global_result_manager


def create_event_result(
    event_type: str,
    event_id: str,
    isolation_context: IsolationContext,
    status: ResultStatus = ResultStatus.SUCCESS,
    result_data: Optional[Dict[str, Any]] = None,
    processor_name: str = "",
    processor_id: str = "",
    **kwargs,
) -> EventResult:
    """创建事件结果的便捷函数"""
    return EventResult(
        id="",
        event_type=event_type,
        event_id=event_id,
        isolation_context=isolation_context,
        status=status,
        result_data=result_data or {},
        processor_name=processor_name,
        processor_id=processor_id,
        **kwargs,
    )


def store_event_result(result: EventResult) -> bool:
    """存储事件结果的便捷函数"""
    return _global_result_manager.store_result(result)


def get_event_results(
    isolation_context: IsolationContext, limit: Optional[int] = None, status_filter: Optional[ResultStatus] = None
) -> List[EventResult]:
    """获取事件结果的便捷函数"""
    return _global_result_manager.get_results(isolation_context, limit, status_filter)


def query_event_results(
    isolation_context: IsolationContext,
    event_type: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: Optional[int] = None,
) -> List[EventResult]:
    """查询事件结果的便捷函数"""
    return _global_result_manager.query_results(isolation_context, event_type, start_time, end_time, limit)
