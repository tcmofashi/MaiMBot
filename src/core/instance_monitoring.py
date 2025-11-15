"""
实例监控和诊断系统

实现实例的性能监控和异常诊断。支持实例调用链追踪和性能分析，
提供实例故障检测和自动恢复。

主要功能：
1. 性能监控和指标收集
2. 异常检测和诊断
3. 调用链追踪
4. 故障检测和自动恢复
5. 健康检查和状态报告
"""

import asyncio
import threading
import time
import traceback
import psutil
import weakref
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum
import logging
import uuid

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """指标类型"""

    COUNTER = "counter"  # 计数器
    GAUGE = "gauge"  # 仪表盘
    HISTOGRAM = "histogram"  # 直方图
    TIMER = "timer"  # 计时器
    RATE = "rate"  # 速率


class HealthStatus(Enum):
    """健康状态"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class SeverityLevel(Enum):
    """严重程度"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class MetricValue:
    """指标值"""

    name: str
    value: float
    metric_type: MetricType
    timestamp: datetime = field(default_factory=datetime.now)
    tags: Dict[str, str] = field(default_factory=dict)
    instance_id: Optional[str] = None


@dataclass
class PerformanceMetric:
    """性能指标"""

    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    memory_percent: float = 0.0
    disk_io_read_mb: float = 0.0
    disk_io_write_mb: float = 0.0
    network_io_sent_mb: float = 0.0
    network_io_recv_mb: float = 0.0
    thread_count: int = 0
    file_descriptor_count: int = 0
    response_time_ms: float = 0.0
    request_count: int = 0
    error_count: int = 0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class HealthCheck:
    """健康检查"""

    instance_id: str
    check_name: str
    status: HealthStatus
    message: str
    response_time_ms: float
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DiagnosticEvent:
    """诊断事件"""

    instance_id: str
    event_type: str
    severity: SeverityLevel
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    stack_trace: Optional[str] = None
    correlation_id: Optional[str] = None


@dataclass
class CallSpan:
    """调用链跨度"""

    span_id: str
    trace_id: str
    parent_span_id: Optional[str]
    operation_name: str
    instance_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    tags: Dict[str, Any] = field(default_factory=dict)
    status: str = "ok"
    error: Optional[str] = None


class MetricsCollector:
    """指标收集器"""

    def __init__(self):
        self._metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10000))
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = defaultdict(float)
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._timers: Dict[str, List[float]] = defaultdict(list)

    def record_counter(
        self, name: str, value: float = 1.0, tags: Optional[Dict[str, str]] = None, instance_id: Optional[str] = None
    ):
        """记录计数器"""
        self._counters[name] += value
        metric = MetricValue(name, self._counters[name], MetricType.COUNTER, tags=tags or {}, instance_id=instance_id)
        self._metrics[name].append(metric)

    def set_gauge(
        self, name: str, value: float, tags: Optional[Dict[str, str]] = None, instance_id: Optional[str] = None
    ):
        """设置仪表盘值"""
        self._gauges[name] = value
        metric = MetricValue(name, value, MetricType.GAUGE, tags=tags or {}, instance_id=instance_id)
        self._metrics[name].append(metric)

    def record_histogram(
        self, name: str, value: float, tags: Optional[Dict[str, str]] = None, instance_id: Optional[str] = None
    ):
        """记录直方图"""
        self._histograms[name].append(value)
        metric = MetricValue(name, value, MetricType.HISTOGRAM, tags=tags or {}, instance_id=instance_id)
        self._metrics[name].append(metric)

    def record_timer(
        self, name: str, duration_ms: float, tags: Optional[Dict[str, str]] = None, instance_id: Optional[str] = None
    ):
        """记录计时器"""
        self._timers[name].append(duration_ms)
        metric = MetricValue(name, duration_ms, MetricType.TIMER, tags=tags or {}, instance_id=instance_id)
        self._metrics[name].append(metric)

    def get_metrics(self, name: str, minutes: int = 5) -> List[MetricValue]:
        """获取指标"""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        return [metric for metric in self._metrics[name] if metric.timestamp >= cutoff_time]

    def get_aggregated_metrics(self, name: str, minutes: int = 5) -> Dict[str, float]:
        """获取聚合指标"""
        metrics = self.get_metrics(name, minutes)
        if not metrics:
            return {}

        values = [metric.value for metric in metrics]
        return {
            "count": len(values),
            "sum": sum(values),
            "avg": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
            "latest": values[-1] if values else 0.0,
        }


class TracingManager:
    """调用链追踪管理器"""

    def __init__(self):
        self._active_spans: Dict[str, CallSpan] = {}
        self._completed_spans: deque = deque(maxlen=10000)
        self._lock = threading.Lock()

    def start_span(
        self,
        operation_name: str,
        instance_id: str,
        trace_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
        tags: Optional[Dict[str, Any]] = None,
    ) -> CallSpan:
        """开始跨度"""
        span_id = str(uuid.uuid4())
        if trace_id is None:
            trace_id = span_id

        span = CallSpan(
            span_id=span_id,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            operation_name=operation_name,
            instance_id=instance_id,
            start_time=datetime.now(),
            tags=tags or {},
        )

        with self._lock:
            self._active_spans[span_id] = span

        return span

    def finish_span(self, span_id: str, status: str = "ok", error: Optional[str] = None):
        """结束跨度"""
        with self._lock:
            if span_id not in self._active_spans:
                return

            span = self._active_spans[span_id]
            span.end_time = datetime.now()
            span.duration_ms = (span.end_time - span.start_time).total_seconds() * 1000
            span.status = status
            span.error = error

            # 移动到已完成跨度
            self._completed_spans.append(span)
            del self._active_spans[span_id]

    def get_trace(self, trace_id: str) -> List[CallSpan]:
        """获取调用链"""
        spans = []
        for span in self._completed_spans:
            if span.trace_id == trace_id:
                spans.append(span)

        # 检查活跃跨度
        with self._lock:
            for span in self._active_spans.values():
                if span.trace_id == trace_id:
                    spans.append(span)

        # 按开始时间排序
        spans.sort(key=lambda s: s.start_time)
        return spans

    def get_active_spans(self, instance_id: Optional[str] = None) -> List[CallSpan]:
        """获取活跃跨度"""
        with self._lock:
            spans = list(self._active_spans.values())
            if instance_id:
                spans = [span for span in spans if span.instance_id == instance_id]
            return spans


class InstanceMonitor:
    """实例监控器"""

    def __init__(self, instance_id: str):
        self.instance_id = instance_id
        self.metrics_collector = MetricsCollector()
        self.health_checks: Dict[str, HealthCheck] = {}
        self.diagnostic_events: deque = deque(maxlen=1000)
        self.process = psutil.Process() if hasattr(psutil, "Process") else None
        self.last_health_check = datetime.now()
        self.health_check_interval = 60  # 60秒健康检查一次

    def collect_performance_metrics(self) -> PerformanceMetric:
        """收集性能指标"""
        try:
            if self.process:
                # CPU和内存
                cpu_percent = self.process.cpu_percent()
                memory_info = self.process.memory_info()
                memory_mb = memory_info.rss / 1024 / 1024
                memory_percent = self.process.memory_percent()

                # 磁盘IO
                io_counters = self.process.io_counters()
                disk_io_read_mb = io_counters.read_bytes / 1024 / 1024
                disk_io_write_mb = io_counters.write_bytes / 1024 / 1024

                # 网络IO（如果可用）
                network_io_sent_mb = 0.0
                network_io_recv_mb = 0.0

                # 线程和文件描述符
                thread_count = self.process.num_threads()
                try:
                    file_descriptor_count = self.process.num_fds()
                except (AttributeError, psutil.AccessDenied):
                    file_descriptor_count = 0
            else:
                # 系统级别指标
                cpu_percent = psutil.cpu_percent()
                memory = psutil.virtual_memory()
                memory_mb = memory.used / 1024 / 1024
                memory_percent = memory.percent
                disk_io_read_mb = 0.0
                disk_io_write_mb = 0.0
                network_io_sent_mb = 0.0
                network_io_recv_mb = 0.0
                thread_count = 0
                file_descriptor_count = 0

            metric = PerformanceMetric(
                cpu_percent=cpu_percent,
                memory_mb=memory_mb,
                memory_percent=memory_percent,
                disk_io_read_mb=disk_io_read_mb,
                disk_io_write_mb=disk_io_write_mb,
                network_io_sent_mb=network_io_sent_mb,
                network_io_recv_mb=network_io_recv_mb,
                thread_count=thread_count,
                file_descriptor_count=file_descriptor_count,
            )

            # 记录到指标收集器
            self.metrics_collector.set_gauge("cpu_usage", cpu_percent, instance_id=self.instance_id)
            self.metrics_collector.set_gauge("memory_usage_mb", memory_mb, instance_id=self.instance_id)
            self.metrics_collector.set_gauge("memory_usage_percent", memory_percent, instance_id=self.instance_id)
            self.metrics_collector.set_gauge("thread_count", thread_count, instance_id=self.instance_id)

            return metric

        except Exception as e:
            logger.error(f"Failed to collect performance metrics for {self.instance_id}: {e}")
            return PerformanceMetric()

    def record_diagnostic_event(
        self,
        event_type: str,
        severity: SeverityLevel,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ):
        """记录诊断事件"""
        event = DiagnosticEvent(
            instance_id=self.instance_id,
            event_type=event_type,
            severity=severity,
            message=message,
            details=details or {},
            correlation_id=correlation_id,
            stack_trace=traceback.format_exc() if severity in [SeverityLevel.HIGH, SeverityLevel.CRITICAL] else None,
        )

        self.diagnostic_events.append(event)

        # 记录指标
        self.metrics_collector.record_counter(
            f"diagnostic_events_{event_type}", tags={"severity": severity.value}, instance_id=self.instance_id
        )

        logger.info(f"Diagnostic event for {self.instance_id}: {message}")

    def add_health_check(
        self,
        check_name: str,
        status: HealthStatus,
        message: str,
        response_time_ms: float,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """添加健康检查结果"""
        health_check = HealthCheck(
            instance_id=self.instance_id,
            check_name=check_name,
            status=status,
            message=message,
            response_time_ms=response_time_ms,
            metadata=metadata or {},
        )

        self.health_checks[check_name] = health_check
        self.last_health_check = datetime.now()

        # 记录指标
        status_value = 1 if status == HealthStatus.HEALTHY else 0
        self.metrics_collector.set_gauge(
            f"health_check_{check_name}", status_value, tags={"status": status.value}, instance_id=self.instance_id
        )

    def get_overall_health(self) -> HealthStatus:
        """获取整体健康状态"""
        if not self.health_checks:
            return HealthStatus.UNKNOWN

        statuses = [check.status for check in self.health_checks.values()]

        if all(status == HealthStatus.HEALTHY for status in statuses):
            return HealthStatus.HEALTHY
        elif any(status == HealthStatus.UNHEALTHY for status in statuses):
            return HealthStatus.UNHEALTHY
        elif any(status == HealthStatus.DEGRADED for status in statuses):
            return HealthStatus.DEGRADED
        else:
            return HealthStatus.UNKNOWN

    def get_metrics_summary(self, minutes: int = 5) -> Dict[str, Any]:
        """获取指标摘要"""
        summary = {
            "instance_id": self.instance_id,
            "overall_health": self.get_overall_health().value,
            "last_health_check": self.last_health_check.isoformat(),
            "metrics": {},
        }

        # 收集各种指标
        for metric_name in ["cpu_usage", "memory_usage_mb", "memory_usage_percent", "thread_count"]:
            aggregated = self.metrics_collector.get_aggregated_metrics(metric_name, minutes)
            if aggregated:
                summary["metrics"][metric_name] = aggregated

        return summary


class InstanceMonitoringSystem:
    """
    实例监控系统

    负责监控所有实例的性能、健康状态和异常。
    支持自动故障检测和恢复。
    """

    _instance: Optional["InstanceMonitoringSystem"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "InstanceMonitoringSystem":
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

        # 监控器存储
        self._monitors: Dict[str, InstanceMonitor] = {}
        self._monitor_refs: Dict[str, weakref.ref] = {}

        # 调用链管理
        self.tracing_manager = TracingManager()

        # 监控任务
        self._monitoring_task: Optional[asyncio.Task] = None
        self._monitoring_interval = 30  # 30秒监控一次

        # 健康检查配置
        self._health_checkers: Dict[str, Callable] = {}
        self._auto_recovery_enabled = True

        # 诊断规则
        self._diagnostic_rules: List[Callable[[InstanceMonitor], List[str]]] = []

        # 告警回调
        self._alert_callbacks: List[Callable[[DiagnosticEvent], None]] = []

        # 统计信息
        self._global_stats = {
            "monitored_instances": 0,
            "healthy_instances": 0,
            "unhealthy_instances": 0,
            "total_health_checks": 0,
            "total_diagnostic_events": 0,
            "auto_recoveries": 0,
            "last_monitoring": None,
        }

        # 注册默认健康检查器
        self._register_default_health_checkers()

        # 启动监控任务
        self._start_monitoring()

        logger.info("InstanceMonitoringSystem initialized")

    def register_instance(self, instance_id: str, instance: Any) -> bool:
        """注册实例监控"""
        with self._lock:
            if instance_id in self._monitors:
                logger.warning(f"Instance {instance_id} already monitored")
                return False

            try:
                monitor = InstanceMonitor(instance_id)
                self._monitors[instance_id] = monitor
                self._monitor_refs[instance_id] = weakref.ref(instance)

                # 执行初始健康检查
                asyncio.create_task(self._perform_initial_health_check(instance_id))

                logger.info(f"Registered monitoring for instance: {instance_id}")
                return True

            except Exception as e:
                logger.error(f"Failed to register monitoring for {instance_id}: {e}")
                return False

    def unregister_instance(self, instance_id: str) -> bool:
        """注销实例监控"""
        with self._lock:
            if instance_id not in self._monitors:
                logger.warning(f"Instance {instance_id} not monitored")
                return False

            del self._monitors[instance_id]
            if instance_id in self._monitor_refs:
                del self._monitor_refs[instance_id]

            logger.info(f"Unregistered monitoring for instance: {instance_id}")
            return True

    def get_monitor(self, instance_id: str) -> Optional[InstanceMonitor]:
        """获取实例监控器"""
        with self._lock:
            return self._monitors.get(instance_id)

    def create_span(
        self,
        operation_name: str,
        instance_id: str,
        trace_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
    ) -> Optional[CallSpan]:
        """创建调用链跨度"""
        return self.tracing_manager.start_span(operation_name, instance_id, trace_id, parent_span_id)

    def finish_span(self, span_id: str, status: str = "ok", error: Optional[str] = None):
        """结束调用链跨度"""
        self.tracing_manager.finish_span(span_id, status, error)

    def get_trace(self, trace_id: str) -> List[CallSpan]:
        """获取调用链"""
        return self.tracing_manager.get_trace(trace_id)

    def register_health_checker(self, name: str, checker: Callable[[str], Tuple[HealthStatus, str, float]]):
        """注册健康检查器"""
        self._health_checkers[name] = checker
        logger.info(f"Registered health checker: {name}")

    def add_diagnostic_rule(self, rule: Callable[[InstanceMonitor], List[str]]):
        """添加诊断规则"""
        self._diagnostic_rules.append(rule)

    def add_alert_callback(self, callback: Callable[[DiagnosticEvent], None]):
        """添加告警回调"""
        self._alert_callbacks.append(callback)

    async def _perform_initial_health_check(self, instance_id: str):
        """执行初始健康检查"""
        monitor = self._monitors.get(instance_id)
        if not monitor:
            return

        # 执行所有健康检查
        for checker_name, checker in self._health_checkers.items():
            try:
                status, message, response_time = checker(instance_id)
                monitor.add_health_check(checker_name, status, message, response_time)
            except Exception as e:
                logger.error(f"Health check {checker_name} failed for {instance_id}: {e}")

    async def _perform_monitoring(self):
        """执行监控"""
        with self._lock:
            self._global_stats["last_monitoring"] = datetime.now()
            self._global_stats["monitored_instances"] = len(self._monitors)

        healthy_count = 0
        unhealthy_count = 0

        for instance_id, monitor in self._monitors.items():
            try:
                # 检查实例是否还存在
                instance_ref = self._monitor_refs.get(instance_id)
                if instance_ref and not instance_ref():
                    # 实例已被垃圾回收
                    self.unregister_instance(instance_id)
                    continue

                # 收集性能指标
                monitor.collect_performance_metrics()

                # 执行健康检查
                if (datetime.now() - monitor.last_health_check).total_seconds() >= monitor.health_check_interval:
                    await self._perform_health_checks(instance_id)

                # 执行诊断规则
                await self._run_diagnostic_rules(monitor)

                # 统计健康状态
                overall_health = monitor.get_overall_health()
                if overall_health == HealthStatus.HEALTHY:
                    healthy_count += 1
                else:
                    unhealthy_count += 1

                # 自动恢复
                if self._auto_recovery_enabled and overall_health == HealthStatus.UNHEALTHY:
                    await self._attempt_auto_recovery(instance_id)

            except Exception as e:
                logger.error(f"Monitoring failed for {instance_id}: {e}")
                monitor.record_diagnostic_event("monitoring_error", SeverityLevel.HIGH, f"Monitoring failed: {str(e)}")

        with self._lock:
            self._global_stats["healthy_instances"] = healthy_count
            self._global_stats["unhealthy_instances"] = unhealthy_count

    async def _perform_health_checks(self, instance_id: str):
        """执行健康检查"""
        monitor = self._monitors.get(instance_id)
        if not monitor:
            return

        for checker_name, checker in self._health_checkers.items():
            try:
                status, message, response_time = checker(instance_id)
                monitor.add_health_check(checker_name, status, message, response_time)
                self._global_stats["total_health_checks"] += 1
            except Exception as e:
                logger.error(f"Health check {checker_name} failed for {instance_id}: {e}")

    async def _run_diagnostic_rules(self, monitor: InstanceMonitor):
        """运行诊断规则"""
        for rule in self._diagnostic_rules:
            try:
                issues = rule(monitor)
                for issue in issues:
                    monitor.record_diagnostic_event(
                        "diagnostic_rule", SeverityLevel.MEDIUM, f"Diagnostic rule detected: {issue}"
                    )
            except Exception as e:
                logger.error(f"Diagnostic rule failed: {e}")

    async def _attempt_auto_recovery(self, instance_id: str):
        """尝试自动恢复"""
        monitor = self._monitors.get(instance_id)
        if not monitor:
            return

        try:
            # 获取实例引用
            instance_ref = self._monitor_refs.get(instance_id)
            if not instance_ref:
                return

            instance = instance_ref()
            if not instance:
                return

            # 尝试恢复操作
            if hasattr(instance, "recover"):
                if asyncio.iscoroutinefunction(instance.recover):
                    await instance.recover()
                else:
                    instance.recover()

                monitor.record_diagnostic_event("auto_recovery", SeverityLevel.LOW, "Automatic recovery attempted")

                self._global_stats["auto_recoveries"] += 1
                logger.info(f"Auto recovery attempted for {instance_id}")

        except Exception as e:
            monitor.record_diagnostic_event(
                "auto_recovery_failed", SeverityLevel.HIGH, f"Auto recovery failed: {str(e)}"
            )

    def _register_default_health_checkers(self):
        """注册默认健康检查器"""

        def basic_health_check(instance_id: str) -> Tuple[HealthStatus, str, float]:
            """基础健康检查"""
            start_time = time.time()
            monitor = self._monitors.get(instance_id)
            if not monitor:
                return HealthStatus.UNHEALTHY, "Monitor not found", 0.0

            # 检查CPU使用率
            if monitor.process:
                try:
                    cpu_percent = monitor.process.cpu_percent()
                    if cpu_percent > 90:
                        return HealthStatus.UNHEALTHY, f"High CPU usage: {cpu_percent:.1f}%", time.time() - start_time
                    elif cpu_percent > 70:
                        return (
                            HealthStatus.DEGRADED,
                            f"Elevated CPU usage: {cpu_percent:.1f}%",
                            time.time() - start_time,
                        )
                except psutil.NoSuchProcess:
                    return HealthStatus.UNHEALTHY, "Process not found", time.time() - start_time

            return HealthStatus.HEALTHY, "OK", time.time() - start_time

        self.register_health_checker("basic", basic_health_check)

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

    def get_instance_health(self, instance_id: str) -> Dict[str, Any]:
        """获取实例健康状态"""
        monitor = self._monitors.get(instance_id)
        if not monitor:
            return {"status": "not_monitored"}

        return {
            "instance_id": instance_id,
            "overall_health": monitor.get_overall_health().value,
            "health_checks": {
                name: {
                    "status": check.status.value,
                    "message": check.message,
                    "response_time_ms": check.response_time_ms,
                    "timestamp": check.timestamp.isoformat(),
                }
                for name, check in monitor.health_checks.items()
            },
            "last_health_check": monitor.last_health_check.isoformat(),
        }

    def get_instance_metrics(self, instance_id: str, minutes: int = 5) -> Dict[str, Any]:
        """获取实例指标"""
        monitor = self._monitors.get(instance_id)
        if not monitor:
            return {}

        return monitor.get_metrics_summary(minutes)

    def get_system_overview(self) -> Dict[str, Any]:
        """获取系统概览"""
        with self._lock:
            overview = {"global_stats": self._global_stats.copy(), "instances": {}}

            for instance_id, monitor in self._monitors.items():
                overview["instances"][instance_id] = {
                    "health": monitor.get_overall_health().value,
                    "last_health_check": monitor.last_health_check.isoformat(),
                    "recent_events": len(
                        [
                            event
                            for event in monitor.diagnostic_events
                            if (datetime.now() - event.timestamp).total_seconds() < 3600
                        ]
                    ),
                }

            return overview

    def shutdown(self):
        """关闭监控系统"""
        if self._monitoring_task:
            self._monitoring_task.cancel()

        with self._lock:
            self._monitors.clear()
            self._monitor_refs.clear()

        logger.info("InstanceMonitoringSystem shutdown")


# 全局实例监控系统单例
global_instance_monitoring = InstanceMonitoringSystem()


def get_instance_monitoring() -> InstanceMonitoringSystem:
    """获取全局实例监控系统单例"""
    return global_instance_monitoring


# 便捷函数
def register_instance_monitoring(instance_id: str, instance: Any) -> bool:
    """便捷函数：注册实例监控"""
    return global_instance_monitoring.register_instance(instance_id, instance)


def create_span(operation_name: str, instance_id: str, **kwargs) -> Optional[CallSpan]:
    """便捷函数：创建调用链跨度"""
    return global_instance_monitoring.create_span(operation_name, instance_id, **kwargs)
