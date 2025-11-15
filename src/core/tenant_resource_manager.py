"""
租户资源管理器

实现租户级别的资源使用监控和限制。支持资源配额管理和超限告警，
提供租户资源的统计分析和优化建议。

主要功能：
1. 资源使用监控和限制
2. 配额管理和超限告警
3. 资源统计和分析
4. 优化建议和自动调整
5. 多维度资源指标收集
"""

import asyncio
import threading
import psutil
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ResourceType(Enum):
    """资源类型"""

    CPU = "cpu"
    MEMORY = "memory"
    DISK = "disk"
    NETWORK = "network"
    INSTANCES = "instances"
    REQUESTS = "requests"
    TOKENS = "tokens"
    API_CALLS = "api_calls"
    STORAGE = "storage"
    BANDWIDTH = "bandwidth"


class AlertLevel(Enum):
    """告警级别"""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class QuotaType(Enum):
    """配额类型"""

    HARD_LIMIT = "hard_limit"  # 硬限制
    SOFT_LIMIT = "soft_limit"  # 软限制
    BURST_LIMIT = "burst_limit"  # 突发限制
    DAILY_LIMIT = "daily_limit"  # 每日限制
    MONTHLY_LIMIT = "monthly_limit"  # 每月限制


@dataclass
class ResourceQuota:
    """资源配额"""

    resource_type: ResourceType
    quota_type: QuotaType
    limit_value: float
    current_usage: float = 0.0
    warning_threshold: float = 0.8
    critical_threshold: float = 0.95
    time_window: Optional[int] = None  # 时间窗口（秒）
    reset_interval: Optional[int] = None  # 重置间隔（秒）
    last_reset: datetime = field(default_factory=datetime.now)


@dataclass
class ResourceUsage:
    """资源使用记录"""

    resource_type: ResourceType
    usage_value: float
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResourceAlert:
    """资源告警"""

    tenant_id: str
    resource_type: ResourceType
    alert_level: AlertLevel
    message: str
    current_usage: float
    limit_value: float
    timestamp: datetime = field(default_factory=datetime.now)
    resolved: bool = False
    resolved_at: Optional[datetime] = None


@dataclass
class TenantResourceStats:
    """租户资源统计"""

    tenant_id: str
    cpu_usage_percent: float = 0.0
    memory_usage_mb: float = 0.0
    memory_limit_mb: float = 0.0
    disk_usage_mb: float = 0.0
    active_instances: int = 0
    total_requests: int = 0
    api_calls_count: int = 0
    tokens_used: int = 0
    network_bytes_sent: int = 0
    network_bytes_received: int = 0
    storage_used_mb: float = 0.0
    last_updated: datetime = field(default_factory=datetime.now)


class ResourceCollector:
    """资源收集器"""

    def __init__(self):
        self._collectors = {
            ResourceType.CPU: self._collect_cpu,
            ResourceType.MEMORY: self._collect_memory,
            ResourceType.DISK: self._collect_disk,
            ResourceType.NETWORK: self._collect_network,
        }

    def collect_system_resource(self, resource_type: ResourceType) -> float:
        """收集系统资源"""
        collector = self._collectors.get(resource_type)
        if collector:
            return collector()
        return 0.0

    def _collect_cpu(self) -> float:
        """收集CPU使用率"""
        try:
            return psutil.cpu_percent(interval=0.1)
        except Exception:
            return 0.0

    def _collect_memory(self) -> float:
        """收集内存使用量（MB）"""
        try:
            memory = psutil.virtual_memory()
            return memory.used / 1024 / 1024
        except Exception:
            return 0.0

    def _collect_disk(self) -> float:
        """收集磁盘使用量（MB）"""
        try:
            disk = psutil.disk_usage("/")
            return disk.used / 1024 / 1024
        except Exception:
            return 0.0

    def _collect_network(self) -> float:
        """收集网络使用量（字节）"""
        try:
            net = psutil.net_io_counters()
            return net.bytes_sent + net.bytes_recv
        except Exception:
            return 0.0


class TenantResourceManager:
    """
    租户资源管理器

    负责租户级别的资源监控、配额管理和告警。
    支持多种资源类型和配额策略。
    """

    _instance: Optional["TenantResourceManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "TenantResourceManager":
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

        # 租户配额配置
        self._tenant_quotas: Dict[str, Dict[ResourceType, ResourceQuota]] = defaultdict(dict)

        # 资源使用记录
        self._usage_history: Dict[str, Dict[ResourceType, deque]] = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=1000))
        )

        # 当前资源使用状态
        self._current_usage: Dict[str, Dict[ResourceType, float]] = defaultdict(lambda: defaultdict(float))

        # 资源告警
        self._alerts: Dict[str, List[ResourceAlert]] = defaultdict(list)

        # 资源统计
        self._tenant_stats: Dict[str, TenantResourceStats] = {}

        # 资源收集器
        self._collector = ResourceCollector()

        # 告警回调函数
        self._alert_callbacks: List[Callable[[ResourceAlert], None]] = []

        # 监控任务
        self._monitoring_task: Optional[asyncio.Task] = None
        self._monitoring_interval = 30  # 30秒监控一次

        # 默认配额
        self._default_quotas = {
            ResourceType.CPU: ResourceQuota(ResourceType.CPU, QuotaType.SOFT_LIMIT, 80.0),
            ResourceType.MEMORY: ResourceQuota(ResourceType.MEMORY, QuotaType.SOFT_LIMIT, 1024.0),
            ResourceType.INSTANCES: ResourceQuota(ResourceType.INSTANCES, QuotaType.HARD_LIMIT, 100.0),
            ResourceType.REQUESTS: ResourceQuota(ResourceType.REQUESTS, QuotaType.DAILY_LIMIT, 10000.0),
            ResourceType.TOKENS: ResourceQuota(ResourceType.TOKENS, QuotaType.MONTHLY_LIMIT, 1000000.0),
        }

        # 统计信息
        self._global_stats = {
            "monitored_tenants": 0,
            "active_alerts": 0,
            "quota_violations": 0,
            "last_monitoring": None,
            "total_resource_requests": 0,
        }

        # 启动监控任务
        self._start_monitoring()

        logger.info("TenantResourceManager initialized")

    def set_tenant_quota(
        self,
        tenant_id: str,
        resource_type: ResourceType,
        quota_type: QuotaType,
        limit_value: float,
        warning_threshold: float = 0.8,
        critical_threshold: float = 0.95,
        **kwargs,
    ) -> bool:
        """
        设置租户配额

        Args:
            tenant_id: 租户ID
            resource_type: 资源类型
            quota_type: 配额类型
            limit_value: 限制值
            warning_threshold: 警告阈值
            critical_threshold: 严重阈值
            **kwargs: 其他参数

        Returns:
            是否设置成功
        """
        with self._lock:
            quota = ResourceQuota(
                resource_type=resource_type,
                quota_type=quota_type,
                limit_value=limit_value,
                warning_threshold=warning_threshold,
                critical_threshold=critical_threshold,
                **kwargs,
            )

            self._tenant_quotas[tenant_id][resource_type] = quota

            # 初始化使用状态
            if tenant_id not in self._current_usage:
                self._current_usage[tenant_id] = defaultdict(float)
            if tenant_id not in self._tenant_stats:
                self._tenant_stats[tenant_id] = TenantResourceStats(tenant_id=tenant_id)

            logger.info(f"Set quota for tenant {tenant_id}: {resource_type.value} = {limit_value}")
            return True

    def get_tenant_quota(self, tenant_id: str, resource_type: ResourceType) -> Optional[ResourceQuota]:
        """获取租户配额"""
        # 优先使用租户特定配额
        if tenant_id in self._tenant_quotas and resource_type in self._tenant_quotas[tenant_id]:
            return self._tenant_quotas[tenant_id][resource_type]

        # 使用默认配额
        return self._default_quotas.get(resource_type)

    def record_resource_usage(
        self, tenant_id: str, resource_type: ResourceType, usage_value: float, metadata: Optional[Dict[str, Any]] = None
    ):
        """
        记录资源使用

        Args:
            tenant_id: 租户ID
            resource_type: 资源类型
            usage_value: 使用值
            metadata: 元数据
        """
        with self._lock:
            # 更新当前使用
            self._current_usage[tenant_id][resource_type] += usage_value

            # 记录历史
            usage_record = ResourceUsage(resource_type=resource_type, usage_value=usage_value, metadata=metadata or {})
            self._usage_history[tenant_id][resource_type].append(usage_record)

            # 检查配额
            self._check_quota(tenant_id, resource_type)

            # 更新统计
            self._global_stats["total_resource_requests"] += 1

    def _check_quota(self, tenant_id: str, resource_type: ResourceType):
        """检查配额"""
        quota = self.get_tenant_quota(tenant_id, resource_type)
        if not quota:
            return

        current_usage = self._current_usage[tenant_id][resource_type]

        # 检查是否需要重置配额
        self._check_quota_reset(tenant_id, resource_type, quota)

        # 计算使用率
        usage_ratio = current_usage / quota.limit_value if quota.limit_value > 0 else 0

        # 检查告警级别
        if usage_ratio >= quota.critical_threshold:
            self._create_alert(tenant_id, resource_type, AlertLevel.CRITICAL, current_usage, quota)
        elif usage_ratio >= quota.warning_threshold:
            self._create_alert(tenant_id, resource_type, AlertLevel.WARNING, current_usage, quota)

    def _check_quota_reset(self, tenant_id: str, resource_type: ResourceType, quota: ResourceQuota):
        """检查配额重置"""
        if quota.reset_interval is None:
            return

        now = datetime.now()
        if (now - quota.last_reset).total_seconds() >= quota.reset_interval:
            # 重置配额
            quota.current_usage = 0.0
            self._current_usage[tenant_id][resource_type] = 0.0
            quota.last_reset = now

            logger.info(f"Reset quota for tenant {tenant_id}: {resource_type.value}")

    def _create_alert(
        self,
        tenant_id: str,
        resource_type: ResourceType,
        alert_level: AlertLevel,
        current_usage: float,
        quota: ResourceQuota,
    ):
        """创建告警"""
        # 检查是否已有相同级别的未解决告警
        existing_alerts = self._alerts[tenant_id]
        for alert in existing_alerts:
            if alert.resource_type == resource_type and alert.alert_level == alert_level and not alert.resolved:
                return  # 已有告警，不重复创建

        # 创建新告警
        alert = ResourceAlert(
            tenant_id=tenant_id,
            resource_type=resource_type,
            alert_level=alert_level,
            message=f"Resource {resource_type.value} usage ({current_usage}) exceeds {alert_level.value} threshold",
            current_usage=current_usage,
            limit_value=quota.limit_value,
        )

        self._alerts[tenant_id].append(alert)
        self._global_stats["quota_violations"] += 1

        # 调用告警回调
        for callback in self._alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"Alert callback failed: {e}")

        logger.warning(f"Resource alert created: {alert}")

    def get_tenant_usage(self, tenant_id: str, resource_type: Optional[ResourceType] = None) -> Dict[str, float]:
        """获取租户资源使用"""
        with self._lock:
            if resource_type:
                return {resource_type.value: self._current_usage[tenant_id].get(resource_type, 0.0)}
            else:
                return {rt.value: usage for rt, usage in self._current_usage[tenant_id].items()}

    def get_tenant_alerts(self, tenant_id: str, resolved: Optional[bool] = None) -> List[ResourceAlert]:
        """获取租户告警"""
        with self._lock:
            alerts = self._alerts[tenant_id]
            if resolved is not None:
                alerts = [alert for alert in alerts if alert.resolved == resolved]
            return alerts

    def resolve_alert(self, tenant_id: str, alert_id: str) -> bool:
        """解决告警"""
        with self._lock:
            for alert in self._alerts[tenant_id]:
                # 简单的ID匹配（基于时间戳）
                if str(int(alert.timestamp.timestamp() * 1000)) == alert_id:
                    alert.resolved = True
                    alert.resolved_at = datetime.now()
                    logger.info(f"Resolved alert: {alert}")
                    return True
        return False

    def get_tenant_stats(self, tenant_id: str) -> TenantResourceStats:
        """获取租户资源统计"""
        with self._lock:
            if tenant_id not in self._tenant_stats:
                self._tenant_stats[tenant_id] = TenantResourceStats(tenant_id=tenant_id)

            stats = self._tenant_stats[tenant_id]

            # 更新统计数据
            usage = self._current_usage[tenant_id]
            stats.cpu_usage_percent = usage.get(ResourceType.CPU, 0.0)
            stats.memory_usage_mb = usage.get(ResourceType.MEMORY, 0.0)
            stats.active_instances = int(usage.get(ResourceType.INSTANCES, 0.0))
            stats.total_requests = int(usage.get(ResourceType.REQUESTS, 0.0))
            stats.tokens_used = int(usage.get(ResourceType.TOKENS, 0.0))
            stats.network_bytes_sent = int(usage.get(ResourceType.NETWORK, 0.0) / 2)
            stats.network_bytes_received = int(usage.get(ResourceType.NETWORK, 0.0) / 2)
            stats.last_updated = datetime.now()

            # 获取内存配额
            memory_quota = self.get_tenant_quota(tenant_id, ResourceType.MEMORY)
            if memory_quota:
                stats.memory_limit_mb = memory_quota.limit_value

            return stats

    def get_usage_history(self, tenant_id: str, resource_type: ResourceType, minutes: int = 60) -> List[ResourceUsage]:
        """获取使用历史"""
        with self._lock:
            cutoff_time = datetime.now() - timedelta(minutes=minutes)
            history = self._usage_history[tenant_id][resource_type]

            return [usage for usage in history if usage.timestamp >= cutoff_time]

    def add_alert_callback(self, callback: Callable[[ResourceAlert], None]):
        """添加告警回调"""
        self._alert_callbacks.append(callback)

    def remove_alert_callback(self, callback: Callable[[ResourceAlert], None]):
        """移除告警回调"""
        if callback in self._alert_callbacks:
            self._alert_callbacks.remove(callback)

    def check_resource_availability(
        self, tenant_id: str, resource_type: ResourceType, required_amount: float
    ) -> Tuple[bool, float]:
        """
        检查资源可用性

        Args:
            tenant_id: 租户ID
            resource_type: 资源类型
            required_amount: 需要的资源量

        Returns:
            (是否可用, 剩余可用量)
        """
        quota = self.get_tenant_quota(tenant_id, resource_type)
        if not quota:
            return True, float("inf")  # 无限制

        current_usage = self._current_usage[tenant_id].get(resource_type, 0.0)
        available = quota.limit_value - current_usage

        return available >= required_amount, max(0, available)

    def suggest_optimizations(self, tenant_id: str) -> List[str]:
        """建议优化措施"""
        suggestions = []

        with self._lock:
            usage = self._current_usage[tenant_id]
            alerts = self.get_tenant_alerts(tenant_id, resolved=False)

            # 分析高资源使用
            for resource_type, usage_value in usage.items():
                quota = self.get_tenant_quota(tenant_id, resource_type)
                if quota and quota.limit_value > 0:
                    usage_ratio = usage_value / quota.limit_value
                    if usage_ratio > 0.8:
                        if resource_type == ResourceType.MEMORY:
                            suggestions.append(f"内存使用率过高 ({usage_ratio:.1%})，建议优化内存使用或增加内存配额")
                        elif resource_type == ResourceType.CPU:
                            suggestions.append(f"CPU使用率过高 ({usage_ratio:.1%})，建议优化代码或增加CPU配额")
                        elif resource_type == ResourceType.INSTANCES:
                            suggestions.append(f"实例数量过多 ({int(usage_value)})，建议清理无用实例")

            # 分析告警
            critical_alerts = [alert for alert in alerts if alert.alert_level == AlertLevel.CRITICAL]
            if critical_alerts:
                suggestions.append(f"有 {len(critical_alerts)} 个严重告警需要处理")

            # 分析趋势
            for resource_type in [ResourceType.CPU, ResourceType.MEMORY]:
                history = self.get_usage_history(tenant_id, resource_type, minutes=60)
                if len(history) >= 10:
                    recent_usage = [usage.usage_value for usage in history[-10:]]
                    early_usage = [usage.usage_value for usage in history[:10]]
                    if sum(recent_usage) / len(recent_usage) > sum(early_usage) / len(early_usage) * 1.5:
                        suggestions.append(f"{resource_type.value} 使用量持续增长，建议关注并优化")

        return suggestions

    def _start_monitoring(self):
        """启动监控任务"""
        try:
            loop = asyncio.get_event_loop()
            self._monitoring_task = loop.create_task(self._monitoring_loop())
        except RuntimeError:
            logger.warning("No event loop available, monitoring task not started")

    async def _monitoring_loop(self):
        """监控循环"""
        while True:
            try:
                await asyncio.sleep(self._monitoring_interval)
                await self._perform_monitoring()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")

    async def _perform_monitoring(self):
        """执行监控"""
        with self._lock:
            self._global_stats["last_monitoring"] = datetime.now()
            self._global_stats["monitored_tenants"] = len(self._tenant_quotas)
            self._global_stats["active_alerts"] = sum(
                len([alert for alert in alerts if not alert.resolved]) for alerts in self._alerts.values()
            )

        # 收集系统资源（用于未来扩展）
        _ = self._collector.collect_system_resource(ResourceType.CPU)
        _ = self._collector.collect_system_resource(ResourceType.MEMORY)

        # 更新租户统计
        for tenant_id in self._tenant_quotas:
            self.get_tenant_stats(tenant_id)

    def get_global_stats(self) -> Dict[str, Any]:
        """获取全局统计"""
        with self._lock:
            stats = self._global_stats.copy()
            stats["total_quotas"] = sum(len(quotas) for quotas in self._tenant_quotas.values())
            return stats

    def cleanup_tenant_data(self, tenant_id: str) -> bool:
        """清理租户数据"""
        with self._lock:
            # 清理配额
            if tenant_id in self._tenant_quotas:
                del self._tenant_quotas[tenant_id]

            # 清理使用历史
            if tenant_id in self._usage_history:
                del self._usage_history[tenant_id]

            # 清理当前使用
            if tenant_id in self._current_usage:
                del self._current_usage[tenant_id]

            # 清理告警
            if tenant_id in self._alerts:
                del self._alerts[tenant_id]

            # 清理统计
            if tenant_id in self._tenant_stats:
                del self._tenant_stats[tenant_id]

            logger.info(f"Cleaned up data for tenant: {tenant_id}")
            return True

    def export_tenant_config(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """导出租户配置"""
        with self._lock:
            if tenant_id not in self._tenant_quotas:
                return None

            quotas = self._tenant_quotas[tenant_id]
            config = {"tenant_id": tenant_id, "quotas": {}, "created_at": datetime.now().isoformat()}

            for resource_type, quota in quotas.items():
                config["quotas"][resource_type.value] = {
                    "quota_type": quota.quota_type.value,
                    "limit_value": quota.limit_value,
                    "warning_threshold": quota.warning_threshold,
                    "critical_threshold": quota.critical_threshold,
                    "time_window": quota.time_window,
                    "reset_interval": quota.reset_interval,
                }

            return config

    def import_tenant_config(self, config: Dict[str, Any]) -> bool:
        """导入租户配置"""
        try:
            tenant_id = config["tenant_id"]
            quotas_config = config["quotas"]

            for resource_name, quota_config in quotas_config.items():
                resource_type = ResourceType(resource_name)
                quota_type = QuotaType(quota_config["quota_type"])

                self.set_tenant_quota(
                    tenant_id=tenant_id,
                    resource_type=resource_type,
                    quota_type=quota_type,
                    limit_value=quota_config["limit_value"],
                    warning_threshold=quota_config.get("warning_threshold", 0.8),
                    critical_threshold=quota_config.get("critical_threshold", 0.95),
                    time_window=quota_config.get("time_window"),
                    reset_interval=quota_config.get("reset_interval"),
                )

            logger.info(f"Imported config for tenant: {tenant_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to import tenant config: {e}")
            return False

    def shutdown(self):
        """关闭资源管理器"""
        if self._monitoring_task:
            self._monitoring_task.cancel()

        logger.info("TenantResourceManager shutdown")


# 全局租户资源管理器单例
global_tenant_resource_manager = TenantResourceManager()


def get_tenant_resource_manager() -> TenantResourceManager:
    """获取全局租户资源管理器单例"""
    return global_tenant_resource_manager


# 便捷函数
def set_tenant_quota(
    tenant_id: str, resource_type: ResourceType, quota_type: QuotaType, limit_value: float, **kwargs
) -> bool:
    """便捷函数：设置租户配额"""
    return global_tenant_resource_manager.set_tenant_quota(tenant_id, resource_type, quota_type, limit_value, **kwargs)


def record_resource_usage(tenant_id: str, resource_type: ResourceType, usage_value: float, **kwargs):
    """便捷函数：记录资源使用"""
    global_tenant_resource_manager.record_resource_usage(tenant_id, resource_type, usage_value, **kwargs)


def get_tenant_stats(tenant_id: str) -> TenantResourceStats:
    """便捷函数：获取租户统计"""
    return global_tenant_resource_manager.get_tenant_stats(tenant_id)
