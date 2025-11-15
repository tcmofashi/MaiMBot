"""
MaiBot 多租户数据库监控工具
提供数据库性能监控、租户数据使用统计、异常检测和告警功能

作者: Claude
创建时间: 2025-01-12
"""

import datetime
import time
from typing import Dict, List, Optional, Any
from collections import defaultdict, deque
from dataclasses import dataclass

from src.common.logger import get_logger
from .database import db

logger = get_logger("database_monitoring")


@dataclass
class MonitoringMetrics:
    """监控指标数据类"""

    timestamp: datetime.datetime
    metric_name: str
    metric_value: float
    tenant_id: Optional[str] = None
    agent_id: Optional[str] = None
    tags: Optional[Dict[str, str]] = None


@dataclass
class Alert:
    """告警数据类"""

    alert_id: str
    severity: str  # "info", "warning", "critical"
    title: str
    message: str
    timestamp: datetime.datetime
    tenant_id: Optional[str] = None
    agent_id: Optional[str] = None
    resolved: bool = False
    resolved_at: Optional[datetime.datetime] = None


class DatabaseMonitor:
    """数据库监控器"""

    def __init__(self):
        self.metrics_history = defaultdict(lambda: deque(maxlen=1000))  # 保留最近1000个指标
        self.active_alerts = []
        self.alert_rules = self._initialize_alert_rules()
        self.performance_baseline = {}

    def _initialize_alert_rules(self) -> Dict[str, Dict]:
        """初始化告警规则"""
        return {
            "database_size": {"warning_threshold_mb": 500, "critical_threshold_mb": 1000, "enabled": True},
            "query_performance": {
                "slow_query_threshold_ms": 1000,
                "very_slow_query_threshold_ms": 5000,
                "enabled": True,
            },
            "connection_issues": {
                "failure_rate_threshold": 0.1,  # 10%
                "enabled": True,
            },
            "data_growth": {"daily_growth_threshold_mb": 100, "enabled": True},
            "isolation_violations": {"max_allowed_violations": 0, "enabled": True},
        }

    def collect_all_metrics(self) -> Dict[str, List[MonitoringMetrics]]:
        """
        收集所有监控指标

        Returns:
            Dict: 指标名称到指标列表的映射
        """
        logger.debug("开始收集数据库监控指标...")
        start_time = time.time()

        metrics = {}

        try:
            # 1. 基础数据库指标
            metrics.update(self._collect_database_metrics())

            # 2. 租户使用指标
            metrics.update(self._collect_tenant_metrics())

            # 3. 性能指标
            metrics.update(self._collect_performance_metrics())

            # 4. 数据质量指标
            metrics.update(self._collect_data_quality_metrics())

            # 5. 业务指标
            metrics.update(self._collect_business_metrics())

        except Exception as e:
            logger.exception(f"收集监控指标失败: {e}")

        collection_time = time.time() - start_time
        logger.debug(f"指标收集完成，耗时: {collection_time:.2f}秒")

        return metrics

    def _collect_database_metrics(self) -> Dict[str, List[MonitoringMetrics]]:
        """收集基础数据库指标"""
        metrics = {}
        current_time = datetime.datetime.now()

        try:
            with db:
                # 数据库大小
                cursor = db.execute_sql("SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()")
                size_bytes = cursor.fetchone()[0] if cursor.fetchone() else 0
                size_mb = size_bytes / (1024 * 1024)

                metrics["database_size_mb"] = [
                    MonitoringMetrics(timestamp=current_time, metric_name="database_size_mb", metric_value=size_mb)
                ]

                # 页面统计
                cursor = db.execute_sql("SELECT page_count FROM pragma_page_count()")
                page_count = cursor.fetchone()[0] or 0

                metrics["database_pages"] = [
                    MonitoringMetrics(
                        timestamp=current_time, metric_name="database_pages", metric_value=float(page_count)
                    )
                ]

                # 表统计
                tables = [
                    "agents",
                    "chat_streams",
                    "messages",
                    "memory_chest",
                    "llm_usage",
                    "expression",
                    "action_records",
                    "jargon",
                    "person_info",
                    "group_info",
                ]

                total_rows = 0
                for table_name in tables:
                    if db.table_exists(table_name):
                        cursor = db.execute_sql(f"SELECT COUNT(*) FROM {table_name}")
                        row_count = cursor.fetchone()[0]
                        total_rows += row_count

                metrics["total_rows"] = [
                    MonitoringMetrics(timestamp=current_time, metric_name="total_rows", metric_value=float(total_rows))
                ]

        except Exception as e:
            logger.exception(f"收集基础数据库指标失败: {e}")

        return metrics

    def _collect_tenant_metrics(self) -> Dict[str, List[MonitoringMetrics]]:
        """收集租户使用指标"""
        metrics = {}
        current_time = datetime.datetime.now()

        try:
            with db:
                # 租户数量
                cursor = db.execute_sql("SELECT COUNT(DISTINCT tenant_id) FROM agents")
                tenant_count = cursor.fetchone()[0] or 0

                metrics["tenant_count"] = [
                    MonitoringMetrics(
                        timestamp=current_time, metric_name="tenant_count", metric_value=float(tenant_count)
                    )
                ]

                # 各租户的数据量分布
                cursor = db.execute_sql("""
                    SELECT tenant_id, COUNT(*) as message_count
                    FROM messages
                    WHERE tenant_id IS NOT NULL
                    GROUP BY tenant_id
                    ORDER BY message_count DESC
                    LIMIT 10
                """)

                for row in cursor.fetchall():
                    tenant_id, message_count = row
                    metrics[f"tenant_message_count_{tenant_id}"] = [
                        MonitoringMetrics(
                            timestamp=current_time,
                            metric_name="tenant_message_count",
                            metric_value=float(message_count),
                            tenant_id=tenant_id,
                        )
                    ]

                # 各租户的LLM使用量（最近7天）
                cursor = db.execute_sql("""
                    SELECT tenant_id, COUNT(*) as request_count,
                           COALESCE(SUM(total_tokens), 0) as total_tokens,
                           COALESCE(SUM(cost), 0) as total_cost
                    FROM llm_usage
                    WHERE timestamp >= datetime('now', '-7 days')
                      AND tenant_id IS NOT NULL
                    GROUP BY tenant_id
                    ORDER BY total_cost DESC
                """)

                for row in cursor.fetchall():
                    tenant_id, request_count, total_tokens, total_cost = row

                    metrics[f"tenant_weekly_tokens_{tenant_id}"] = [
                        MonitoringMetrics(
                            timestamp=current_time,
                            metric_name="tenant_weekly_tokens",
                            metric_value=float(total_tokens),
                            tenant_id=tenant_id,
                        )
                    ]

                    metrics[f"tenant_weekly_cost_{tenant_id}"] = [
                        MonitoringMetrics(
                            timestamp=current_time,
                            metric_name="tenant_weekly_cost",
                            metric_value=float(total_cost),
                            tenant_id=tenant_id,
                        )
                    ]

        except Exception as e:
            logger.exception(f"收集租户指标失败: {e}")

        return metrics

    def _collect_performance_metrics(self) -> Dict[str, List[MonitoringMetrics]]:
        """收集性能指标"""
        metrics = {}
        current_time = datetime.datetime.now()

        try:
            with db:
                # 模拟查询性能测试
                test_queries = [
                    "SELECT COUNT(*) FROM messages",
                    "SELECT COUNT(*) FROM chat_streams",
                    "SELECT COUNT(*) FROM memory_chest",
                ]

                total_query_time = 0
                for query in test_queries:
                    start_time = time.time()
                    try:
                        db.execute_sql(query)
                        query_time = (time.time() - start_time) * 1000  # 转换为毫秒
                        total_query_time += query_time
                    except Exception as e:
                        logger.warning(f"性能测试查询失败: {query}, 错误: {e}")
                        query_time = 1000  # 设置一个较高的默认值

                avg_query_time = total_query_time / len(test_queries)

                metrics["avg_query_time_ms"] = [
                    MonitoringMetrics(
                        timestamp=current_time, metric_name="avg_query_time_ms", metric_value=avg_query_time
                    )
                ]

                # 缓存命中率（SQLite特有）
                try:
                    cursor = db.execute_sql("PRAGMA cache_size")
                    cache_size = cursor.fetchone()[0] or 0

                    metrics["cache_size"] = [
                        MonitoringMetrics(
                            timestamp=current_time, metric_name="cache_size", metric_value=float(cache_size)
                        )
                    ]
                except Exception as e:
                    logger.warning(f"获取缓存信息失败: {e}")

        except Exception as e:
            logger.exception(f"收集性能指标失败: {e}")

        return metrics

    def _collect_data_quality_metrics(self) -> Dict[str, List[MonitoringMetrics]]:
        """收集数据质量指标"""
        metrics = {}
        current_time = datetime.datetime.now()

        try:
            with db:
                # 孤立记录统计
                cursor = db.execute_sql("""
                    SELECT COUNT(*) FROM messages m
                    LEFT JOIN chat_streams cs ON m.chat_stream_id = cs.chat_stream_id
                    WHERE m.chat_stream_id IS NOT NULL AND cs.chat_stream_id IS NULL
                """)
                orphaned_messages = cursor.fetchone()[0] or 0

                metrics["orphaned_messages"] = [
                    MonitoringMetrics(
                        timestamp=current_time, metric_name="orphaned_messages", metric_value=float(orphaned_messages)
                    )
                ]

                # 空隔离字段统计
                null_isolation_fields = 0
                tables_with_isolation = ["chat_streams", "messages", "memory_chest", "llm_usage"]

                for table_name in tables_with_isolation:
                    if db.table_exists(table_name):
                        for field in ["tenant_id", "agent_id"]:
                            cursor = db.execute_sql(
                                f"SELECT COUNT(*) FROM {table_name} WHERE {field} IS NULL OR {field} = ''"
                            )
                            null_count = cursor.fetchone()[0] or 0
                            null_isolation_fields += null_count

                metrics["null_isolation_fields"] = [
                    MonitoringMetrics(
                        timestamp=current_time,
                        metric_name="null_isolation_fields",
                        metric_value=float(null_isolation_fields),
                    )
                ]

                # 重复记录统计（MemoryChest）
                cursor = db.execute_sql("""
                    SELECT COUNT(*) - COUNT(DISTINCT tenant_id, agent_id, COALESCE(platform, ''),
                               COALESCE(chat_stream_id, ''), title, content) as duplicates
                    FROM memory_chest
                """)
                duplicate_memories = cursor.fetchone()[0] or 0

                metrics["duplicate_memories"] = [
                    MonitoringMetrics(
                        timestamp=current_time, metric_name="duplicate_memories", metric_value=float(duplicate_memories)
                    )
                ]

        except Exception as e:
            logger.exception(f"收集数据质量指标失败: {e}")

        return metrics

    def _collect_business_metrics(self) -> Dict[str, List[MonitoringMetrics]]:
        """收集业务指标"""
        metrics = {}
        current_time = datetime.datetime.now()

        try:
            with db:
                # 活跃聊天流统计（最近24小时）
                cursor = db.execute_sql("""
                    SELECT COUNT(DISTINCT chat_stream_id) FROM messages
                    WHERE time >= strftime('%s', 'now', '-1 day')
                """)
                active_chats = cursor.fetchone()[0] or 0

                metrics["active_chats_24h"] = [
                    MonitoringMetrics(
                        timestamp=current_time, metric_name="active_chats_24h", metric_value=float(active_chats)
                    )
                ]

                # 每日消息量趋势
                cursor = db.execute_sql("""
                    SELECT DATE(datetime(time, 'unixepoch')) as date,
                           COUNT(*) as message_count
                    FROM messages
                    WHERE time >= strftime('%s', 'now', '-7 days')
                    GROUP BY date
                    ORDER BY date
                """)

                for row in cursor.fetchall():
                    date_str, message_count = row
                    metrics[f"daily_messages_{date_str}"] = [
                        MonitoringMetrics(
                            timestamp=current_time,
                            metric_name="daily_messages",
                            metric_value=float(message_count),
                            tags={"date": date_str},
                        )
                    ]

                # LLM使用量趋势（最近7天）
                cursor = db.execute_sql("""
                    SELECT DATE(timestamp) as date,
                           COUNT(*) as request_count,
                           COALESCE(SUM(total_tokens), 0) as total_tokens
                    FROM llm_usage
                    WHERE timestamp >= date('now', '-7 days')
                    GROUP BY date
                    ORDER BY date
                """)

                for row in cursor.fetchall():
                    date_str, request_count, total_tokens = row
                    metrics[f"daily_llm_requests_{date_str}"] = [
                        MonitoringMetrics(
                            timestamp=current_time,
                            metric_name="daily_llm_requests",
                            metric_value=float(request_count),
                            tags={"date": date_str},
                        )
                    ]

                    metrics[f"daily_llm_tokens_{date_str}"] = [
                        MonitoringMetrics(
                            timestamp=current_time,
                            metric_name="daily_llm_tokens",
                            metric_value=float(total_tokens),
                            tags={"date": date_str},
                        )
                    ]

        except Exception as e:
            logger.exception(f"收集业务指标失败: {e}")

        return metrics

    def check_alerts(self, metrics: Dict[str, List[MonitoringMetrics]]) -> List[Alert]:
        """
        检查告警条件

        Args:
            metrics: 监控指标

        Returns:
            List[Alert]: 新产生的告警列表
        """
        new_alerts = []
        current_time = datetime.datetime.now()

        try:
            # 1. 数据库大小告警
            if self.alert_rules["database_size"]["enabled"]:
                size_metrics = metrics.get("database_size_mb", [])
                if size_metrics:
                    size_mb = size_metrics[0].metric_value
                    warning_threshold = self.alert_rules["database_size"]["warning_threshold_mb"]
                    critical_threshold = self.alert_rules["database_size"]["critical_threshold_mb"]

                    if size_mb >= critical_threshold:
                        new_alerts.append(
                            Alert(
                                alert_id=f"db_size_critical_{int(current_time.timestamp())}",
                                severity="critical",
                                title="数据库大小严重超标",
                                message=f"数据库大小已达到 {size_mb:.1f}MB，超过临界阈值 {critical_threshold}MB",
                                timestamp=current_time,
                            )
                        )
                    elif size_mb >= warning_threshold:
                        new_alerts.append(
                            Alert(
                                alert_id=f"db_size_warning_{int(current_time.timestamp())}",
                                severity="warning",
                                title="数据库大小超标",
                                message=f"数据库大小已达到 {size_mb:.1f}MB，超过警告阈值 {warning_threshold}MB",
                                timestamp=current_time,
                            )
                        )

            # 2. 查询性能告警
            if self.alert_rules["query_performance"]["enabled"]:
                perf_metrics = metrics.get("avg_query_time_ms", [])
                if perf_metrics:
                    avg_time = perf_metrics[0].metric_value
                    slow_threshold = self.alert_rules["query_performance"]["slow_query_threshold_ms"]
                    very_slow_threshold = self.alert_rules["query_performance"]["very_slow_query_threshold_ms"]

                    if avg_time >= very_slow_threshold:
                        new_alerts.append(
                            Alert(
                                alert_id=f"query_performance_critical_{int(current_time.timestamp())}",
                                severity="critical",
                                title="查询性能严重下降",
                                message=f"平均查询时间已达到 {avg_time:.1f}ms，严重超过正常水平",
                                timestamp=current_time,
                            )
                        )
                    elif avg_time >= slow_threshold:
                        new_alerts.append(
                            Alert(
                                alert_id=f"query_performance_warning_{int(current_time.timestamp())}",
                                severity="warning",
                                title="查询性能下降",
                                message=f"平均查询时间已达到 {avg_time:.1f}ms，超过正常水平",
                                timestamp=current_time,
                            )
                        )

            # 3. 数据质量告警
            if metrics.get("null_isolation_fields"):
                null_fields = metrics["null_isolation_fields"][0].metric_value
                if null_fields > 0:
                    new_alerts.append(
                        Alert(
                            alert_id=f"data_quality_isolation_{int(current_time.timestamp())}",
                            severity="warning",
                            title="隔离字段数据质量问题",
                            message=f"发现 {int(null_fields)} 个空的隔离字段，可能影响多租户隔离效果",
                            timestamp=current_time,
                        )
                    )

            if metrics.get("orphaned_messages"):
                orphaned = metrics["orphaned_messages"][0].metric_value
                if orphaned > 0:
                    new_alerts.append(
                        Alert(
                            alert_id=f"data_quality_orphaned_{int(current_time.timestamp())}",
                            severity="warning",
                            title="孤立数据记录",
                            message=f"发现 {int(orphaned)} 条孤立消息记录，建议清理",
                            timestamp=current_time,
                        )
                    )

            # 4. 业务指标告警
            active_chats_metrics = metrics.get("active_chats_24h", [])
            if active_chats_metrics and active_chats_metrics[0].metric_value == 0:
                new_alerts.append(
                    Alert(
                        alert_id=f"business_no_activity_{int(current_time.timestamp())}",
                        severity="warning",
                        title="24小时内无活跃聊天",
                        message="最近24小时内没有任何活跃聊天，请检查系统运行状态",
                        timestamp=current_time,
                    )
                )

        except Exception as e:
            logger.exception(f"告警检查失败: {e}")

        # 更新活跃告警列表
        self.active_alerts.extend(new_alerts)

        # 限制活跃告警数量
        if len(self.active_alerts) > 100:
            self.active_alerts = self.active_alerts[-100:]

        return new_alerts

    def get_tenant_usage_report(self, days: int = 7) -> Dict[str, Any]:
        """
        获取租户使用报告

        Args:
            days: 统计天数

        Returns:
            Dict: 租户使用报告
        """
        logger.info(f"生成最近{days}天的租户使用报告...")

        report = {
            "report_period_days": days,
            "generated_at": datetime.datetime.now().isoformat(),
            "tenant_summaries": {},
            "total_usage": {"total_messages": 0, "total_tokens": 0, "total_cost": 0.0, "active_tenants": 0},
        }

        try:
            with db:
                # 获取各租户的使用统计
                cursor = db.execute_sql(f"""
                    SELECT
                        m.tenant_id,
                        COUNT(DISTINCT m.chat_stream_id) as active_chats,
                        COUNT(m.id) as message_count,
                        COALESCE(SUM(l.total_tokens), 0) as total_tokens,
                        COALESCE(SUM(l.cost), 0) as total_cost,
                        COUNT(DISTINCT DATE(datetime(m.time, 'unixepoch'))) as active_days
                    FROM messages m
                    LEFT JOIN llm_usage l ON m.tenant_id = l.tenant_id
                        AND l.timestamp >= date('now', '-{days} days')
                    WHERE m.time >= strftime('%s', 'now', '-{days} days')
                      AND m.tenant_id IS NOT NULL
                    GROUP BY m.tenant_id
                    ORDER BY total_cost DESC
                """)

                for row in cursor.fetchall():
                    tenant_id, active_chats, message_count, total_tokens, total_cost, active_days = row

                    report["tenant_summaries"][tenant_id] = {
                        "active_chats": active_chats,
                        "message_count": message_count,
                        "total_tokens": total_tokens or 0,
                        "total_cost": total_cost or 0.0,
                        "active_days": active_days,
                        "avg_messages_per_day": message_count / max(active_days, 1),
                        "avg_cost_per_day": (total_cost or 0.0) / max(active_days, 1),
                    }

                    # 累计总使用量
                    report["total_usage"]["total_messages"] += message_count
                    report["total_usage"]["total_tokens"] += total_tokens or 0
                    report["total_usage"]["total_cost"] += total_cost or 0.0

                report["total_usage"]["active_tenants"] = len(report["tenant_summaries"])

        except Exception as e:
            logger.exception(f"生成租户使用报告失败: {e}")

        return report

    def get_performance_summary(self) -> Dict[str, Any]:
        """获取性能摘要"""
        summary = {
            "generated_at": datetime.datetime.now().isoformat(),
            "database_size_mb": 0,
            "avg_query_time_ms": 0,
            "total_rows": 0,
            "table_sizes": {},
            "data_quality_score": 100,  # 数据质量评分
        }

        try:
            with db:
                # 数据库大小
                cursor = db.execute_sql("SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()")
                size_bytes = cursor.fetchone()[0] if cursor.fetchone() else 0
                summary["database_size_mb"] = size_bytes / (1024 * 1024)

                # 总行数
                tables = [
                    "agents",
                    "chat_streams",
                    "messages",
                    "memory_chest",
                    "llm_usage",
                    "expression",
                    "action_records",
                    "jargon",
                    "person_info",
                    "group_info",
                ]

                for table_name in tables:
                    if db.table_exists(table_name):
                        cursor = db.execute_sql(f"SELECT COUNT(*) FROM {table_name}")
                        row_count = cursor.fetchone()[0]
                        summary["total_rows"] += row_count
                        summary["table_sizes"][table_name] = row_count

                # 数据质量评分
                quality_deductions = 0

                # 检查孤立记录
                cursor = db.execute_sql("""
                    SELECT COUNT(*) FROM messages m
                    LEFT JOIN chat_streams cs ON m.chat_stream_id = cs.chat_stream_id
                    WHERE m.chat_stream_id IS NOT NULL AND cs.chat_stream_id IS NULL
                """)
                orphaned_count = cursor.fetchone()[0] or 0
                if orphaned_count > 0:
                    quality_deductions += min(orphaned_count / 100, 20)  # 最多扣20分

                # 检查空隔离字段
                null_isolation_count = 0
                for table_name in ["chat_streams", "messages", "memory_chest"]:
                    if db.table_exists(table_name):
                        cursor = db.execute_sql(f"""
                            SELECT COUNT(*) FROM {table_name}
                            WHERE tenant_id IS NULL OR tenant_id = '' OR agent_id IS NULL OR agent_id = ''
                        """)
                        null_count = cursor.fetchone()[0] or 0
                        null_isolation_count += null_count

                if null_isolation_count > 0:
                    quality_deductions += min(null_isolation_count / 1000, 30)  # 最多扣30分

                summary["data_quality_score"] = max(0, 100 - quality_deductions)

        except Exception as e:
            logger.exception(f"获取性能摘要失败: {e}")

        return summary

    def store_metrics(self, metrics: Dict[str, List[MonitoringMetrics]]):
        """存储指标到历史记录"""
        try:
            for metric_name, metric_list in metrics.items():
                for metric in metric_list:
                    self.metrics_history[metric_name].append(metric)
        except Exception as e:
            logger.exception(f"存储指标失败: {e}")

    def get_metrics_history(self, metric_name: str, limit: int = 100) -> List[MonitoringMetrics]:
        """获取指标历史记录"""
        return list(self.metrics_history[metric_name])[-limit:]

    def get_active_alerts(self, severity: Optional[str] = None) -> List[Alert]:
        """获取活跃告警"""
        if severity:
            return [alert for alert in self.active_alerts if alert.severity == severity and not alert.resolved]
        return [alert for alert in self.active_alerts if not alert.resolved]

    def resolve_alert(self, alert_id: str) -> bool:
        """解决告警"""
        for alert in self.active_alerts:
            if alert.alert_id == alert_id:
                alert.resolved = True
                alert.resolved_at = datetime.datetime.now()
                return True
        return False


def run_database_monitoring() -> Dict[str, Any]:
    """
    便捷函数：运行完整的数据库监控

    Returns:
        Dict: 监控结果
    """
    monitor = DatabaseMonitor()

    # 收集指标
    metrics = monitor.collect_all_metrics()

    # 存储指标
    monitor.store_metrics(metrics)

    # 检查告警
    new_alerts = monitor.check_alerts(metrics)

    # 生成报告
    return {
        "timestamp": datetime.datetime.now().isoformat(),
        "metrics_collected": len(metrics),
        "new_alerts_count": len(new_alerts),
        "new_alerts": [
            {"id": alert.alert_id, "severity": alert.severity, "title": alert.title, "message": alert.message}
            for alert in new_alerts
        ],
        "tenant_usage_report": monitor.get_tenant_usage_report(),
        "performance_summary": monitor.get_performance_summary(),
    }


if __name__ == "__main__":
    # 运行监控
    result = run_database_monitoring()

    print("=== 数据库监控报告 ===")
    print(f"监控时间: {result['timestamp']}")
    print(f"收集指标数: {result['metrics_collected']}")
    print(f"新告警数: {result['new_alerts_count']}")

    if result["new_alerts"]:
        print("\n=== 新告警 ===")
        for alert in result["new_alerts"]:
            print(f"[{alert['severity'].upper()}] {alert['title']}")
            print(f"  {alert['message']}")

    print("\n=== 性能摘要 ===")
    perf = result["performance_summary"]
    print(f"数据库大小: {perf['database_size_mb']:.1f} MB")
    print(f"总记录数: {perf['total_rows']:,}")
    print(f"数据质量评分: {perf['data_quality_score']:.1f}/100")

    print("\n=== 租户使用情况 ===")
    usage = result["tenant_usage_report"]
    print(f"活跃租户数: {usage['total_usage']['active_tenants']}")
    print(f"总消息数: {usage['total_usage']['total_messages']:,}")
    print(f"总Token数: {usage['total_usage']['total_tokens']:,}")
    print(f"总成本: ${usage['total_usage']['total_cost']:.2f}")
