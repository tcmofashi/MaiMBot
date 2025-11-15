"""
配额和计费管理系统

实现租户级别的配额管理、计费统计和使用量分析功能。
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any

from src.common.logger import get_logger
from src.common.database.database_model import LLMUsage

logger = get_logger("quota_manager")


class QuotaAlertLevel(Enum):
    """配额告警级别"""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EXCEEDED = "exceeded"


@dataclass
class QuotaAlert:
    """配额告警"""

    tenant_id: str
    alert_level: QuotaAlertLevel
    message: str
    current_usage: float
    limit: float
    usage_percentage: float
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "tenant_id": self.tenant_id,
            "alert_level": self.alert_level.value,
            "message": self.message,
            "current_usage": self.current_usage,
            "limit": self.limit,
            "usage_percentage": self.usage_percentage,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class TenantUsageStats:
    """租户使用统计"""

    tenant_id: str
    date: datetime
    daily_tokens: int = 0
    daily_requests: int = 0
    daily_cost: float = 0.0
    monthly_tokens: int = 0
    monthly_requests: int = 0
    monthly_cost: float = 0.0
    agent_usage: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def add_usage(self, agent_id: str, tokens: int, cost: float):
        """添加使用量"""
        self.daily_tokens += tokens
        self.daily_requests += 1
        self.daily_cost += cost
        self.monthly_tokens += tokens
        self.monthly_requests += 1
        self.monthly_cost += cost

        # 记录智能体使用量
        if agent_id not in self.agent_usage:
            self.agent_usage[agent_id] = {"tokens": 0, "requests": 0, "cost": 0.0}

        self.agent_usage[agent_id]["tokens"] += tokens
        self.agent_usage[agent_id]["requests"] += 1
        self.agent_usage[agent_id]["cost"] += cost

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "tenant_id": self.tenant_id,
            "date": self.date.isoformat(),
            "daily_tokens": self.daily_tokens,
            "daily_requests": self.daily_requests,
            "daily_cost": self.daily_cost,
            "monthly_tokens": self.monthly_tokens,
            "monthly_requests": self.monthly_requests,
            "monthly_cost": self.monthly_cost,
            "agent_usage": self.agent_usage,
        }


class IsolatedQuotaManager:
    """隔离化配额管理器

    负责管理租户级别的配额限制、使用量统计和计费分析。
    """

    def __init__(self):
        # 租户配额配置
        self._tenant_quotas: Dict[str, "TenantQuotaConfig"] = {}

        # 使用统计缓存
        self._usage_stats: Dict[str, TenantUsageStats] = {}

        # 告警记录
        self._alerts: List[QuotaAlert] = []

        # 线程安全锁
        self._quota_lock = threading.RLock()
        self._stats_lock = threading.RLock()
        self._alerts_lock = threading.RLock()

        # 配额监听器
        self._quota_listeners: List[callable] = []

        logger.debug("初始化隔离化配额管理器")

    def configure_tenant_quota(
        self,
        tenant_id: str,
        daily_token_limit: int = 1000000,
        monthly_cost_limit: float = 100.0,
        daily_request_limit: int = 10000,
        warning_threshold: float = 0.8,
    ):
        """配置租户配额"""
        with self._quota_lock:
            quota = TenantQuotaConfig(
                tenant_id=tenant_id,
                daily_token_limit=daily_token_limit,
                monthly_cost_limit=monthly_cost_limit,
                daily_request_limit=daily_request_limit,
                warning_threshold=warning_threshold,
            )

            self._tenant_quotas[tenant_id] = quota
            logger.info(
                f"配置租户配额: {tenant_id}, 日Token限制: {daily_token_limit}, 月费用限制: {monthly_cost_limit}"
            )

    def get_tenant_quota(self, tenant_id: str) -> Optional["TenantQuotaConfig"]:
        """获取租户配额配置"""
        with self._quota_lock:
            return self._tenant_quotas.get(tenant_id)

    def check_quota(self, tenant_id: str, tokens_needed: int = 0) -> QuotaAlertLevel:
        """检查配额状态"""
        with self._quota_lock:
            quota = self._tenant_quotas.get(tenant_id)
            if not quota:
                # 如果没有配置配额，返回正常状态
                return QuotaAlertLevel.INFO

            # 重置每日使用量
            quota.reset_daily_usage()

            # 检查各项限制
            alerts = []

            # 检查每日token限制
            token_usage_ratio = quota.daily_tokens_used / quota.daily_token_limit if quota.daily_token_limit > 0 else 0
            if quota.daily_tokens_used + tokens_needed > quota.daily_token_limit:
                alerts.append((QuotaAlertLevel.EXCEEDED, "daily_tokens", token_usage_ratio))
            elif token_usage_ratio >= quota.warning_threshold:
                alerts.append((QuotaAlertLevel.WARNING, "daily_tokens", token_usage_ratio))

            # 检查每月费用限制
            cost_usage_ratio = quota.monthly_cost_used / quota.monthly_cost_limit if quota.monthly_cost_limit > 0 else 0
            if quota.monthly_cost_used > quota.monthly_cost_limit:
                alerts.append((QuotaAlertLevel.EXCEEDED, "monthly_cost", cost_usage_ratio))
            elif cost_usage_ratio >= quota.warning_threshold:
                alerts.append((QuotaAlertLevel.WARNING, "monthly_cost", cost_usage_ratio))

            # 检查每日请求限制
            request_usage_ratio = (
                quota.daily_requests_used / quota.daily_request_limit if quota.daily_request_limit > 0 else 0
            )
            if quota.daily_requests_used >= quota.daily_request_limit:
                alerts.append((QuotaAlertLevel.EXCEEDED, "daily_requests", request_usage_ratio))
            elif request_usage_ratio >= quota.warning_threshold:
                alerts.append((QuotaAlertLevel.WARNING, "daily_requests", request_usage_ratio))

            # 返回最高级别的告警
            if alerts:
                highest_alert = max(alerts, key=lambda x: x[0].value)
                alert_level, alert_type, usage_ratio = highest_alert

                # 生成告警
                self._generate_quota_alert(tenant_id, alert_level, alert_type, usage_ratio, quota)

                return alert_level

            return QuotaAlertLevel.INFO

    def record_usage(self, tenant_id: str, tokens_used: int, cost_incurred: float, agent_id: str = "default"):
        """记录使用量"""
        with self._quota_lock:
            quota = self._tenant_quotas.get(tenant_id)
            if quota:
                quota.record_usage(tokens_used, cost_incurred)

        # 更新使用统计
        self._update_usage_stats(tenant_id, agent_id, tokens_used, cost_incurred)

        # 重新检查配额状态
        self.check_quota(tenant_id)

        logger.debug(f"记录使用量: 租户={tenant_id}, 智能体={agent_id}, Tokens={tokens_used}, 费用={cost_incurred}")

    def get_quota_status(self, tenant_id: str) -> Dict[str, Any]:
        """获取配额状态"""
        with self._quota_lock:
            quota = self._tenant_quotas.get(tenant_id)
            if not quota:
                return {"status": "not_configured", "tenant_id": tenant_id}

            quota.reset_daily_usage()

            return {
                "tenant_id": tenant_id,
                "daily_tokens": {
                    "used": quota.daily_tokens_used,
                    "limit": quota.daily_token_limit,
                    "percentage": quota.daily_tokens_used / quota.daily_token_limit
                    if quota.daily_token_limit > 0
                    else 0,
                },
                "monthly_cost": {
                    "used": quota.monthly_cost_used,
                    "limit": quota.monthly_cost_limit,
                    "percentage": quota.monthly_cost_used / quota.monthly_cost_limit
                    if quota.monthly_cost_limit > 0
                    else 0,
                },
                "daily_requests": {
                    "used": quota.daily_requests_used,
                    "limit": quota.daily_request_limit,
                    "percentage": quota.daily_requests_used / quota.daily_request_limit
                    if quota.daily_request_limit > 0
                    else 0,
                },
                "status": self.check_quota(tenant_id).value,
                "last_reset": quota.last_reset_date.isoformat(),
            }

    def get_usage_stats(self, tenant_id: str, days: int = 30) -> Dict[str, Any]:
        """获取使用统计"""
        with self._stats_lock:
            stats = self._usage_stats.get(tenant_id)
            if not stats:
                # 从数据库加载统计数据
                stats = self._load_usage_stats_from_db(tenant_id, days)
                self._usage_stats[tenant_id] = stats

            return stats.to_dict()

    def get_recent_alerts(self, tenant_id: str = None, hours: int = 24) -> List[Dict[str, Any]]:
        """获取最近的告警"""
        with self._alerts_lock:
            cutoff_time = datetime.now() - timedelta(hours=hours)

            alerts = self._alerts
            if tenant_id:
                alerts = [alert for alert in alerts if alert.tenant_id == tenant_id]

            alerts = [alert for alert in alerts if alert.timestamp >= cutoff_time]

            return [alert.to_dict() for alert in alerts]

    def add_quota_listener(self, listener: callable):
        """添加配额监听器"""
        self._quota_listeners.append(listener)

    def remove_quota_listener(self, listener: callable):
        """移除配额监听器"""
        if listener in self._quota_listeners:
            self._quota_listeners.remove(listener)

    def _generate_quota_alert(
        self,
        tenant_id: str,
        alert_level: QuotaAlertLevel,
        alert_type: str,
        usage_ratio: float,
        quota: "TenantQuotaConfig",
    ):
        """生成配额告警"""
        with self._alerts_lock:
            message = self._build_alert_message(alert_level, alert_type, usage_ratio, quota)

            alert = QuotaAlert(
                tenant_id=tenant_id,
                alert_level=alert_level,
                message=message,
                current_usage=self._get_current_usage(alert_type, quota),
                limit=self._get_limit(alert_type, quota),
                usage_percentage=usage_ratio,
            )

            self._alerts.append(alert)

            # 限制告警记录数量
            if len(self._alerts) > 1000:
                self._alerts = self._alerts[-500:]  # 保留最近500条

            # 通知监听器
            self._notify_quota_listeners(alert)

            logger.warning(f"配额告警: {message}")

    def _build_alert_message(
        self, alert_level: QuotaAlertLevel, alert_type: str, usage_ratio: float, quota: "TenantQuotaConfig"
    ) -> str:
        """构建告警消息"""
        type_names = {"daily_tokens": "每日Token使用量", "monthly_cost": "每月费用", "daily_requests": "每日请求次数"}

        level_names = {
            QuotaAlertLevel.WARNING: "警告",
            QuotaAlertLevel.CRITICAL: "严重",
            QuotaAlertLevel.EXCEEDED: "超限",
        }

        type_name = type_names.get(alert_type, alert_type)
        level_name = level_names.get(alert_level, "信息")

        return f"租户 {quota.tenant_id} {level_name}: {type_name}已达 {usage_ratio:.1%}"

    def _get_current_usage(self, alert_type: str, quota: "TenantQuotaConfig") -> float:
        """获取当前使用量"""
        if alert_type == "daily_tokens":
            return quota.daily_tokens_used
        elif alert_type == "monthly_cost":
            return quota.monthly_cost_used
        elif alert_type == "daily_requests":
            return quota.daily_requests_used
        return 0.0

    def _get_limit(self, alert_type: str, quota: "TenantQuotaConfig") -> float:
        """获取限制值"""
        if alert_type == "daily_tokens":
            return quota.daily_token_limit
        elif alert_type == "monthly_cost":
            return quota.monthly_cost_limit
        elif alert_type == "daily_requests":
            return quota.daily_request_limit
        return 0.0

    def _update_usage_stats(self, tenant_id: str, agent_id: str, tokens: int, cost: float):
        """更新使用统计"""
        with self._stats_lock:
            today = datetime.now().date()
            stats_key = f"{tenant_id}:{today}"

            if stats_key not in self._usage_stats:
                self._usage_stats[stats_key] = TenantUsageStats(tenant_id=tenant_id, date=datetime.now())

            self._usage_stats[stats_key].add_usage(agent_id, tokens, cost)

    def _load_usage_stats_from_db(self, tenant_id: str, days: int) -> TenantUsageStats:
        """从数据库加载使用统计"""
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            # 查询数据库
            query = LLMUsage.select().where(
                (LLMUsage.user_id.startswith(f"{tenant_id}:"))
                & (LLMUsage.timestamp >= start_date)
                & (LLMUsage.timestamp <= end_date)
            )

            stats = TenantUsageStats(tenant_id=tenant_id, date=datetime.now())

            for record in query:
                # 解析用户ID获取agent_id
                parts = record.user_id.split(":")
                agent_id = parts[1] if len(parts) > 1 else "default"

                stats.add_usage(agent_id=agent_id, tokens=record.total_tokens, cost=record.cost)

            logger.debug(f"从数据库加载使用统计: {tenant_id}, 记录数: {len(query)}")
            return stats

        except Exception as e:
            logger.error(f"从数据库加载使用统计失败: {e}")
            return TenantUsageStats(tenant_id=tenant_id, date=datetime.now())

    def _notify_quota_listeners(self, alert: QuotaAlert):
        """通知配额监听器"""
        for listener in self._quota_listeners:
            try:
                listener(alert)
            except Exception as e:
                logger.error(f"配额监听器通知失败: {e}")

    def cleanup_old_data(self, days: int = 90):
        """清理旧数据"""
        cutoff_date = datetime.now() - timedelta(days=days)

        with self._alerts_lock:
            self._alerts = [alert for alert in self._alerts if alert.timestamp >= cutoff_date]

        with self._stats_lock:
            keys_to_remove = [key for key, stats in self._usage_stats.items() if stats.date < cutoff_date]

            for key in keys_to_remove:
                del self._usage_stats[key]

        logger.info(f"清理 {days} 天前的配额数据完成")


@dataclass
class TenantQuotaConfig:
    """租户配额配置"""

    tenant_id: str
    daily_token_limit: int = 1000000
    monthly_cost_limit: float = 100.0
    daily_request_limit: int = 10000
    warning_threshold: float = 0.8

    # 使用量统计
    daily_tokens_used: int = 0
    daily_requests_used: int = 0
    monthly_cost_used: float = 0.0
    last_reset_date: datetime = field(default_factory=datetime.now)

    def reset_daily_usage(self):
        """重置每日使用量"""
        today = datetime.now().date()
        if self.last_reset_date.date() < today:
            self.daily_tokens_used = 0
            self.daily_requests_used = 0
            self.last_reset_date = datetime.now()

    def record_usage(self, tokens_used: int, cost_incurred: float):
        """记录使用量"""
        self.reset_daily_usage()
        self.daily_tokens_used += tokens_used
        self.daily_requests_used += 1
        self.monthly_cost_used += cost_incurred

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "tenant_id": self.tenant_id,
            "daily_token_limit": self.daily_token_limit,
            "monthly_cost_limit": self.monthly_cost_limit,
            "daily_request_limit": self.daily_request_limit,
            "warning_threshold": self.warning_threshold,
            "daily_tokens_used": self.daily_tokens_used,
            "daily_requests_used": self.daily_requests_used,
            "monthly_cost_used": self.monthly_cost_used,
            "last_reset_date": self.last_reset_date.isoformat(),
        }


# 全局配额管理器实例
_quota_manager = IsolatedQuotaManager()


def get_quota_manager() -> IsolatedQuotaManager:
    """获取全局配额管理器"""
    return _quota_manager


def configure_tenant_quota(
    tenant_id: str,
    daily_token_limit: int = 1000000,
    monthly_cost_limit: float = 100.0,
    daily_request_limit: int = 10000,
    warning_threshold: float = 0.8,
):
    """配置租户配额（便捷函数）"""
    _quota_manager.configure_tenant_quota(
        tenant_id=tenant_id,
        daily_token_limit=daily_token_limit,
        monthly_cost_limit=monthly_cost_limit,
        daily_request_limit=daily_request_limit,
        warning_threshold=warning_threshold,
    )


def check_tenant_quota(tenant_id: str, tokens_needed: int = 0) -> QuotaAlertLevel:
    """检查租户配额（便捷函数）"""
    return _quota_manager.check_quota(tenant_id, tokens_needed)


def get_tenant_quota_status(tenant_id: str) -> Dict[str, Any]:
    """获取租户配额状态（便捷函数）"""
    return _quota_manager.get_quota_status(tenant_id)


def get_tenant_usage_stats(tenant_id: str, days: int = 30) -> Dict[str, Any]:
    """获取租户使用统计（便捷函数）"""
    return _quota_manager.get_usage_stats(tenant_id, days)


def get_quota_alerts(tenant_id: str = None, hours: int = 24) -> List[Dict[str, Any]]:
    """获取配额告警（便捷函数）"""
    return _quota_manager.get_recent_alerts(tenant_id, hours)
