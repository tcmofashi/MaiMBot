"""
API监控和统计

实现API调用的租户级别监控，支持性能统计、异常监控和API调用审计日志。
提供完整的API监控体系和运维支持。

作者：MaiBot
版本：1.0.0
"""

import time
import threading
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum

from fastapi import Request, Response

try:
    from src.config.isolated_config_manager import get_isolated_config_manager
except ImportError:

    def get_isolated_config_manager(*args, **kwargs):
        return None


class MetricType(Enum):
    """监控指标类型"""

    REQUEST_COUNT = "request_count"
    RESPONSE_TIME = "response_time"
    ERROR_RATE = "error_rate"
    THROUGHPUT = "throughput"
    MEMORY_USAGE = "memory_usage"
    CPU_USAGE = "cpu_usage"
    ACTIVE_CONNECTIONS = "active_connections"


class AlertLevel(Enum):
    """告警级别"""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    FATAL = "fatal"


@dataclass
class APIMetric:
    """API指标数据"""

    tenant_id: str
    agent_id: Optional[str]
    endpoint: str
    method: str
    status_code: int
    response_time: float
    timestamp: datetime
    user_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    request_size: int = 0
    response_size: int = 0
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class APIStats:
    """API统计数据"""

    tenant_id: str
    endpoint: str
    method: str
    total_requests: int = 0
    success_requests: int = 0
    error_requests: int = 0
    avg_response_time: float = 0.0
    min_response_time: float = float("inf")
    max_response_time: float = 0.0
    p95_response_time: float = 0.0
    p99_response_time: float = 0.0
    total_bytes_sent: int = 0
    total_bytes_received: int = 0
    last_request_time: Optional[datetime] = None
    last_error_time: Optional[datetime] = None
    status_code_distribution: Dict[int, int] = field(default_factory=dict)


@dataclass
class AlertRule:
    """告警规则"""

    name: str
    tenant_id: str
    metric_type: MetricType
    condition: str  # gt, lt, eq, gte, lte
    threshold: float
    level: AlertLevel
    duration: int = 300  # 持续时间（秒）
    enabled: bool = True
    description: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Alert:
    """告警信息"""

    id: str
    rule_name: str
    tenant_id: str
    level: AlertLevel
    message: str
    metric_value: float
    threshold: float
    triggered_at: datetime
    resolved_at: Optional[datetime] = None
    is_resolved: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class APIMonitor:
    """API监控器"""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self._metrics: deque = deque(maxlen=10000)  # 保留最近10000条记录
        self._stats: Dict[Tuple[str, str], APIStats] = {}  # (endpoint, method) -> stats
        self._alert_rules: Dict[str, AlertRule] = {}
        self._active_alerts: Dict[str, Alert] = {}
        self._lock = threading.RLock()

        # 实时统计数据
        self._realtime_stats = {
            "requests_per_minute": deque(maxlen=60),
            "requests_per_hour": deque(maxlen=60),
            "error_rate_per_minute": deque(maxlen=60),
            "avg_response_time_per_minute": deque(maxlen=60),
        }

        # 启动后台任务
        self._start_background_tasks()

    def _start_background_tasks(self):
        """启动后台监控任务"""
        # 启动统计计算任务
        stats_thread = threading.Thread(target=self._stats_calculator, daemon=True)
        stats_thread.start()

        # 启动告警检查任务
        alert_thread = threading.Thread(target=self._alert_checker, daemon=True)
        alert_thread.start()

        # 启动清理任务
        cleanup_thread = threading.Thread(target=self._cleanup_old_data, daemon=True)
        cleanup_thread.start()

    def record_request(
        self,
        request: Request,
        response: Response,
        response_time: float,
        tenant_id: str,
        agent_id: str = None,
        user_id: str = None,
        error_message: str = None,
    ):
        """
        记录API请求

        Args:
            request: 请求对象
            response: 响应对象
            response_time: 响应时间
            tenant_id: 租户ID
            agent_id: 智能体ID
            user_id: 用户ID
            error_message: 错误信息
        """
        metric = APIMetric(
            tenant_id=tenant_id,
            agent_id=agent_id,
            endpoint=str(request.url.path),
            method=request.method,
            status_code=response.status_code,
            response_time=response_time,
            timestamp=datetime.utcnow(),
            user_id=user_id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("User-Agent"),
            request_size=int(request.headers.get("Content-Length", 0)),
            response_size=int(response.headers.get("Content-Length", 0)),
            error_message=error_message,
            metadata={"query_params": dict(request.query_params), "path_params": dict(request.path_params)},
        )

        with self._lock:
            self._metrics.append(metric)
            self._update_stats(metric)
            self._update_realtime_stats(metric)

    def _update_stats(self, metric: APIMetric):
        """更新统计数据"""
        key = (metric.endpoint, metric.method)

        if key not in self._stats:
            self._stats[key] = APIStats(tenant_id=metric.tenant_id, endpoint=metric.endpoint, method=metric.method)

        stats = self._stats[key]
        stats.total_requests += 1

        if 200 <= metric.status_code < 400:
            stats.success_requests += 1
        else:
            stats.error_requests += 1
            stats.last_error_time = metric.timestamp

        # 更新响应时间
        stats.avg_response_time = (
            stats.avg_response_time * (stats.total_requests - 1) + metric.response_time
        ) / stats.total_requests
        stats.min_response_time = min(stats.min_response_time, metric.response_time)
        stats.max_response_time = max(stats.max_response_time, metric.response_time)

        # 更新字节数
        stats.total_bytes_sent += metric.request_size
        stats.total_bytes_received += metric.response_size

        # 更新状态码分布
        stats.status_code_distribution[metric.status_code] = (
            stats.status_code_distribution.get(metric.status_code, 0) + 1
        )

        stats.last_request_time = metric.timestamp

    def _update_realtime_stats(self, metric: APIMetric):
        """更新实时统计"""
        now = time.time()
        current_minute = int(now // 60)

        # 这里简化处理，实际应该按时间分组
        self._realtime_stats["requests_per_minute"].append((current_minute, 1))
        self._realtime_stats["error_rate_per_minute"].append((current_minute, 1 if metric.status_code >= 400 else 0))
        self._realtime_stats["avg_response_time_per_minute"].append((current_minute, metric.response_time))

    def _stats_calculator(self):
        """统计计算后台任务"""
        while True:
            try:
                time.sleep(60)  # 每分钟计算一次

                with self._lock:
                    self._calculate_percentiles()
                    self._aggregate_realtime_stats()

            except Exception as e:
                print(f"统计计算错误: {e}")

    def _calculate_percentiles(self):
        """计算百分位数"""
        for key, stats in self._stats.items():
            # 获取最近的响应时间数据
            recent_metrics = [
                m
                for m in self._metrics
                if m.endpoint == key[0] and m.method == key[1] and m.timestamp > datetime.utcnow() - timedelta(hours=1)
            ]

            if recent_metrics:
                response_times = sorted([m.response_time for m in recent_metrics])
                n = len(response_times)

                # 计算P95和P99
                stats.p95_response_time = response_times[int(n * 0.95)] if n > 0 else 0
                stats.p99_response_time = response_times[int(n * 0.99)] if n > 0 else 0

    def _aggregate_realtime_stats(self):
        """聚合实时统计数据"""
        now = time.time()
        current_minute = int(now // 60)

        # 聚合每分钟的请求数
        minute_requests = defaultdict(int)
        minute_errors = defaultdict(int)
        minute_response_times = defaultdict(list)

        for minute, value in self._realtime_stats["requests_per_minute"]:
            if current_minute - minute <= 60:  # 只保留最近60分钟
                minute_requests[minute] += value

        for minute, value in self._realtime_stats["error_rate_per_minute"]:
            if current_minute - minute <= 60:
                minute_errors[minute] += value

        for minute, value in self._realtime_stats["avg_response_time_per_minute"]:
            if current_minute - minute <= 60:
                minute_response_times[minute].append(value)

        # 清理过期数据
        self._cleanup_realtime_stats(current_minute)

    def _cleanup_realtime_stats(self, current_minute: int):
        """清理过期的实时统计数据"""
        cutoff_minute = current_minute - 60

        for stats_name in self._realtime_stats:
            self._realtime_stats[stats_name] = deque(
                [(minute, value) for minute, value in self._realtime_stats[stats_name] if minute > cutoff_minute],
                maxlen=60,
            )

    def _alert_checker(self):
        """告警检查后台任务"""
        while True:
            try:
                time.sleep(30)  # 每30秒检查一次

                with self._lock:
                    self._check_alert_rules()

            except Exception as e:
                print(f"告警检查错误: {e}")

    def _check_alert_rules(self):
        """检查告警规则"""
        now = datetime.utcnow()

        for rule_name, rule in self._alert_rules.items():
            if not rule.enabled or rule.tenant_id != self.tenant_id:
                continue

            try:
                current_value = self._get_metric_value(rule.metric_type)
                is_triggered = self._evaluate_condition(current_value, rule.condition, rule.threshold)

                alert_id = f"{rule_name}_{self.tenant_id}"

                if is_triggered:
                    if alert_id not in self._active_alerts:
                        # 触发新告警
                        alert = Alert(
                            id=alert_id,
                            rule_name=rule_name,
                            tenant_id=self.tenant_id,
                            level=rule.level,
                            message=f"{rule.description} - 当前值: {current_value}, 阈值: {rule.threshold}",
                            metric_value=current_value,
                            threshold=rule.threshold,
                            triggered_at=now,
                        )
                        self._active_alerts[alert_id] = alert
                        self._send_alert(alert)
                else:
                    if alert_id in self._active_alerts:
                        # 解决告警
                        alert = self._active_alerts[alert_id]
                        alert.is_resolved = True
                        alert.resolved_at = now
                        self._send_alert_resolved(alert)
                        del self._active_alerts[alert_id]

            except Exception as e:
                print(f"检查告警规则 {rule_name} 失败: {e}")

    def _get_metric_value(self, metric_type: MetricType) -> float:
        """获取指标值"""
        if metric_type == MetricType.REQUEST_COUNT:
            # 最近1分钟的请求数
            recent_metrics = [m for m in self._metrics if m.timestamp > datetime.utcnow() - timedelta(minutes=1)]
            return len(recent_metrics)

        elif metric_type == MetricType.RESPONSE_TIME:
            # 平均响应时间
            if self._stats:
                return sum(stats.avg_response_time for stats in self._stats.values()) / len(self._stats)
            return 0.0

        elif metric_type == MetricType.ERROR_RATE:
            # 错误率
            total_requests = sum(stats.total_requests for stats in self._stats.values())
            error_requests = sum(stats.error_requests for stats in self._stats.values())
            return (error_requests / total_requests * 100) if total_requests > 0 else 0.0

        return 0.0

    def _evaluate_condition(self, value: float, condition: str, threshold: float) -> bool:
        """评估条件"""
        if condition == "gt":
            return value > threshold
        elif condition == "lt":
            return value < threshold
        elif condition == "eq":
            return value == threshold
        elif condition == "gte":
            return value >= threshold
        elif condition == "lte":
            return value <= threshold
        return False

    def _send_alert(self, alert: Alert):
        """发送告警"""
        # 这里可以实现实际的告警发送逻辑（邮件、短信、webhook等）
        print(f"告警触发: {alert.level.value.upper()} - {alert.message}")

    def _send_alert_resolved(self, alert: Alert):
        """发送告警解决通知"""
        print(f"告警解决: {alert.rule_name} - {alert.message}")

    def _cleanup_old_data(self):
        """清理过期数据"""
        while True:
            try:
                time.sleep(3600)  # 每小时清理一次

                cutoff_time = datetime.utcnow() - timedelta(days=7)

                with self._lock:
                    # 清理过期指标数据
                    initial_count = len(self._metrics)
                    self._metrics = deque((m for m in self._metrics if m.timestamp > cutoff_time), maxlen=10000)
                    cleaned_count = initial_count - len(self._metrics)
                    if cleaned_count > 0:
                        print(f"清理了 {cleaned_count} 条过期指标数据")

                    # 清理过期统计数据
                    expired_keys = []
                    for key, stats in self._stats.items():
                        if stats.last_request_time and stats.last_request_time < cutoff_time:
                            expired_keys.append(key)

                    for key in expired_keys:
                        del self._stats[key]

                    if expired_keys:
                        print(f"清理了 {len(expired_keys)} 条过期统计数据")

            except Exception as e:
                print(f"清理过期数据错误: {e}")

    def get_stats(self, endpoint: str = None, method: str = None, hours: int = 24) -> Dict[str, Any]:
        """
        获取统计数据

        Args:
            endpoint: 端点过滤（可选）
            method: 方法过滤（可选）
            hours: 时间范围（小时）

        Returns:
            统计数据
        """
        with self._lock:
            if endpoint and method:
                # 获取特定端点的统计
                key = (endpoint, method)
                stats = self._stats.get(key)
                if stats:
                    return {
                        "endpoint": endpoint,
                        "method": method,
                        "tenant_id": self.tenant_id,
                        "total_requests": stats.total_requests,
                        "success_requests": stats.success_requests,
                        "error_requests": stats.error_requests,
                        "error_rate": (stats.error_requests / stats.total_requests * 100)
                        if stats.total_requests > 0
                        else 0,
                        "avg_response_time": stats.avg_response_time,
                        "min_response_time": stats.min_response_time,
                        "max_response_time": stats.max_response_time,
                        "p95_response_time": stats.p95_response_time,
                        "p99_response_time": stats.p99_response_time,
                        "total_bytes_sent": stats.total_bytes_sent,
                        "total_bytes_received": stats.total_bytes_received,
                        "last_request_time": stats.last_request_time.isoformat() if stats.last_request_time else None,
                        "status_code_distribution": stats.status_code_distribution,
                    }
                else:
                    return {}

            else:
                # 获取汇总统计
                total_requests = sum(stats.total_requests for stats in self._stats.values())
                success_requests = sum(stats.success_requests for stats in self._stats.values())
                error_requests = sum(stats.error_requests for stats in self._stats.values())

                avg_response_time = 0.0
                if self._stats:
                    avg_response_time = sum(stats.avg_response_time for stats in self._stats.values()) / len(
                        self._stats
                    )

                return {
                    "tenant_id": self.tenant_id,
                    "total_requests": total_requests,
                    "success_requests": success_requests,
                    "error_requests": error_requests,
                    "error_rate": (error_requests / total_requests * 100) if total_requests > 0 else 0,
                    "avg_response_time": avg_response_time,
                    "total_endpoints": len(self._stats),
                    "active_alerts": len(self._active_alerts),
                    "metrics_count": len(self._metrics),
                    "realtime_stats": {
                        "requests_per_minute": len(self._realtime_stats["requests_per_minute"]),
                        "avg_response_time_per_minute": sum(
                            rt for _, rt in self._realtime_stats["avg_response_time_per_minute"]
                        )
                        / len(self._realtime_stats["avg_response_time_per_minute"])
                        if self._realtime_stats["avg_response_time_per_minute"]
                        else 0,
                    },
                }

    def get_metrics(
        self, endpoint: str = None, method: str = None, status_code: int = None, hours: int = 24, limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        获取指标数据

        Args:
            endpoint: 端点过滤（可选）
            method: 方法过滤（可选）
            status_code: 状态码过滤（可选）
            hours: 时间范围（小时）
            limit: 限制数量

        Returns:
            指标数据列表
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)

        with self._lock:
            filtered_metrics = []
            for metric in self._metrics:
                if metric.timestamp < cutoff_time:
                    continue

                if endpoint and metric.endpoint != endpoint:
                    continue

                if method and metric.method != method:
                    continue

                if status_code and metric.status_code != status_code:
                    continue

                filtered_metrics.append(
                    {
                        "tenant_id": metric.tenant_id,
                        "agent_id": metric.agent_id,
                        "endpoint": metric.endpoint,
                        "method": metric.method,
                        "status_code": metric.status_code,
                        "response_time": metric.response_time,
                        "timestamp": metric.timestamp.isoformat(),
                        "user_id": metric.user_id,
                        "ip_address": metric.ip_address,
                        "request_size": metric.request_size,
                        "response_size": metric.response_size,
                        "error_message": metric.error_message,
                        "metadata": metric.metadata,
                    }
                )

                if len(filtered_metrics) >= limit:
                    break

            return filtered_metrics

    def add_alert_rule(self, rule: AlertRule) -> bool:
        """添加告警规则"""
        try:
            with self._lock:
                self._alert_rules[rule.name] = rule
            return True
        except Exception:
            return False

    def remove_alert_rule(self, rule_name: str) -> bool:
        """移除告警规则"""
        try:
            with self._lock:
                if rule_name in self._alert_rules:
                    del self._alert_rules[rule_name]
                    return True
            return False
        except Exception:
            return False

    def get_alerts(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """获取告警信息"""
        with self._lock:
            alerts = []
            source = self._active_alerts if active_only else {}

            for _alert_id, alert in source.items():
                alerts.append(
                    {
                        "id": alert.id,
                        "rule_name": alert.rule_name,
                        "tenant_id": alert.tenant_id,
                        "level": alert.level.value,
                        "message": alert.message,
                        "metric_value": alert.metric_value,
                        "threshold": alert.threshold,
                        "triggered_at": alert.triggered_at.isoformat(),
                        "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
                        "is_resolved": alert.is_resolved,
                        "metadata": alert.metadata,
                    }
                )

            return alerts

    def get_health_status(self) -> Dict[str, Any]:
        """获取健康状态"""
        with self._lock:
            total_requests = sum(stats.total_requests for stats in self._stats.values())
            error_requests = sum(stats.error_requests for stats in self._stats.values())
            error_rate = (error_requests / total_requests * 100) if total_requests > 0 else 0

            # 判断健康状态
            if error_rate > 10:
                health_status = "unhealthy"
            elif error_rate > 5:
                health_status = "warning"
            else:
                health_status = "healthy"

            return {
                "tenant_id": self.tenant_id,
                "status": health_status,
                "error_rate": error_rate,
                "active_alerts": len(self._active_alerts),
                "total_requests": total_requests,
                "monitored_endpoints": len(self._stats),
                "metrics_count": len(self._metrics),
                "timestamp": datetime.utcnow().isoformat(),
            }


# 全局监控器实例
_global_monitors: Dict[str, APIMonitor] = {}
_monitor_lock = threading.Lock()


def get_monitor(tenant_id: str) -> APIMonitor:
    """获取租户的监控器"""
    with _monitor_lock:
        if tenant_id not in _global_monitors:
            _global_monitors[tenant_id] = APIMonitor(tenant_id)
        return _global_monitors[tenant_id]


class MonitoringMiddleware:
    """监控中间件"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            # 这里需要实现实际的中间件逻辑
            # 由于FastAPI中间件的复杂性，这里提供框架代码
            pass

        await self.app(scope, receive, send)


def create_monitoring_middleware():
    """创建监控中间件"""
    return MonitoringMiddleware


# 便捷函数
def record_api_request(
    request: Request,
    response: Response,
    response_time: float,
    tenant_id: str,
    agent_id: str = None,
    user_id: str = None,
    error_message: str = None,
):
    """
    记录API请求的便捷函数

    Args:
        request: 请求对象
        response: 响应对象
        response_time: 响应时间
        tenant_id: 租户ID
        agent_id: 智能体ID
        user_id: 用户ID
        error_message: 错误信息
    """
    try:
        monitor = get_monitor(tenant_id)
        monitor.record_request(request, response, response_time, tenant_id, agent_id, user_id, error_message)
    except Exception as e:
        print(f"记录API请求失败: {e}")


def get_api_stats(tenant_id: str, **kwargs) -> Dict[str, Any]:
    """
    获取API统计的便捷函数

    Args:
        tenant_id: 租户ID
        **kwargs: 其他参数

    Returns:
        统计数据
    """
    try:
        monitor = get_monitor(tenant_id)
        return monitor.get_stats(**kwargs)
    except Exception:
        return {}


def get_api_health(tenant_id: str) -> Dict[str, Any]:
    """
    获取API健康状态的便捷函数

    Args:
        tenant_id: 租户ID

    Returns:
        健康状态
    """
    try:
        monitor = get_monitor(tenant_id)
        return monitor.get_health_status()
    except Exception:
        return {"tenant_id": tenant_id, "status": "unknown", "error": "无法获取健康状态"}
