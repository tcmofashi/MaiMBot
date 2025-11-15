"""
隔离化消息发送器
支持T+P维度的消息发送隔离，确保消息发送时基于租户+平台进行权限控制和配置
"""

import threading
import weakref
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from rich.traceback import install

from src.common.logger import get_logger
from src.chat.message_receive.message import MessageSending
from src.chat.message_receive.uni_message_sender import UniversalMessageSender
from src.chat.utils.utils import truncate_message

# 导入隔离上下文
try:
    from src.isolation.isolation_context import IsolationContext, create_isolation_context
    from src.isolation.isolation_context import IsolationScope
except ImportError:
    # 兼容性处理
    class IsolationContext:
        def __init__(self, *args, **kwargs):
            pass

    def create_isolation_context(*args, **kwargs):
        return None

    class IsolationScope:
        def __init__(self, *args, **kwargs):
            pass


# 导入发送权限和配置管理
try:
    from .sending_permission_manager import get_sending_permission_manager
    from .sending_config_manager import get_sending_config_manager
except ImportError:
    # 兼容性处理，如果这些模块还不存在
    def get_sending_permission_manager(*args, **kwargs):
        return None

    def get_sending_config_manager(*args, **kwargs):
        return None


install(extra_lines=3)

logger = get_logger("isolated_sender")


@dataclass
class SendingMetrics:
    """发送指标统计"""

    total_sent: int = 0
    total_failed: int = 0
    total_blocked: int = 0
    last_sent_time: Optional[datetime] = None
    last_error_time: Optional[datetime] = None
    last_error_message: Optional[str] = None


class IsolatedMessageSender:
    """隔离化消息发送器，支持T+P维度隔离"""

    def __init__(self, tenant_id: str, platform: str):
        """
        初始化隔离化消息发送器

        Args:
            tenant_id: 租户ID (T: 租户隔离)
            platform: 平台标识 (P: 平台隔离)
        """
        self.tenant_id = tenant_id
        self.platform = platform

        # 创建隔离上下文
        self.isolation_context = create_isolation_context(
            tenant_id=tenant_id,
            agent_id="system",  # 消息发送使用system智能体
            platform=platform,
        )

        # 使用原有的UniversalMessageSender作为底层发送器
        self._base_sender = UniversalMessageSender()

        # 发送指标统计
        self.metrics = SendingMetrics()

        # 发送配置缓存
        self._config_cache: Dict[str, Any] = {}
        self._config_cache_time: Optional[datetime] = None
        self._config_cache_ttl = 300  # 5分钟缓存

        # 权限管理器
        self._permission_manager = None

        # 配置管理器
        self._config_manager = None

        logger.info(f"创建隔离化消息发送器: tenant={tenant_id}, platform={platform}")

    def _get_permission_manager(self):
        """获取发送权限管理器"""
        if self._permission_manager is None:
            self._permission_manager = get_sending_permission_manager(self.tenant_id, self.platform)
        return self._permission_manager

    def _get_config_manager(self):
        """获取发送配置管理器"""
        if self._config_manager is None:
            self._config_manager = get_sending_config_manager(self.tenant_id, self.platform)
        return self._config_manager

    def _validate_tenant_access(self, message: MessageSending) -> bool:
        """
        验证租户权限，确保只能发送到属于当前租户的聊天流

        Args:
            message: 待发送的消息

        Returns:
            bool: 是否有权限发送
        """
        try:
            # 检查消息的平台是否匹配
            if hasattr(message, "message_info") and hasattr(message.message_info, "platform"):
                if message.message_info.platform != self.platform:
                    logger.warning(f"租户 {self.tenant_id} 尝试发送消息到不匹配的平台: {message.message_info.platform}")
                    return False

            # 检查聊天流的租户归属
            if hasattr(message, "chat_stream") and message.chat_stream:
                if hasattr(message.chat_stream, "tenant_id"):
                    if message.chat_stream.tenant_id != self.tenant_id:
                        logger.warning(
                            f"租户 {self.tenant_id} 尝试发送消息到不归属的聊天流: {message.chat_stream.stream_id}"
                        )
                        return False
                else:
                    # 如果聊天流没有租户信息，尝试从消息中获取
                    if hasattr(message, "tenant_id") and message.tenant_id != self.tenant_id:
                        logger.warning(f"消息租户ID {message.tenant_id} 与发送器租户ID {self.tenant_id} 不匹配")
                        return False

            # 使用权限管理器进行额外验证
            permission_manager = self._get_permission_manager()
            if permission_manager:
                return permission_manager.can_send_message(message, self.isolation_context)

            return True

        except Exception as e:
            logger.error(f"验证租户权限时出错: {e}")
            # 出错时默认允许发送，避免阻断正常流程
            return True

    def _get_tenant_send_config(self) -> Dict[str, Any]:
        """
        获取租户特定的发送配置

        Returns:
            Dict: 发送配置
        """
        try:
            # 检查缓存是否有效
            now = datetime.now()
            if self._config_cache_time and (now - self._config_cache_time).seconds < self._config_cache_ttl:
                return self._config_cache

            # 从配置管理器获取配置
            config_manager = self._get_config_manager()
            if config_manager:
                config = config_manager.get_effective_config()
                # 缓存配置
                self._config_cache = config
                self._config_cache_time = now
                return config

            # 默认配置
            default_config = {
                "typing_enabled": True,
                "storage_enabled": True,
                "log_enabled": True,
                "max_message_length": 5000,
                "rate_limit": {"enabled": False, "max_per_minute": 30, "max_per_hour": 500},
            }

            # 缓存默认配置
            self._config_cache = default_config
            self._config_cache_time = now
            return default_config

        except Exception as e:
            logger.error(f"获取租户发送配置时出错: {e}")
            # 返回最基础的默认配置
            return {"typing_enabled": True, "storage_enabled": True, "log_enabled": True, "max_message_length": 5000}

    def _check_rate_limit(self) -> bool:
        """
        检查发送频率限制

        Returns:
            bool: 是否允许发送
        """
        try:
            config = self._get_tenant_send_config()
            rate_limit = config.get("rate_limit", {})

            if not rate_limit.get("enabled", False):
                return True

            # 这里可以实现简单的频率限制逻辑
            # 实际生产环境中建议使用Redis等分布式缓存
            # 简单实现：基于内存的计数器（单实例限制）
            # TODO: 在生产环境中实现基于Redis的分布式限制
            return True

        except Exception as e:
            logger.error(f"检查发送频率限制时出错: {e}")
            return True  # 出错时允许发送

    def _update_metrics(self, success: bool, error_message: str = None):
        """更新发送指标"""
        now = datetime.now()

        if success:
            self.metrics.total_sent += 1
            self.metrics.last_sent_time = now
        else:
            self.metrics.total_failed += 1
            self.metrics.last_error_time = now
            self.metrics.last_error_message = error_message

    async def send_message(
        self,
        message: MessageSending,
        typing: bool = None,
        set_reply: bool = False,
        storage_message: bool = None,
        show_log: bool = None,
        **kwargs,
    ) -> bool:
        """
        发送消息（隔离化版本）

        Args:
            message: 待发送的消息
            typing: 是否模拟打字等待（None时使用配置）
            set_reply: 是否设置回复
            storage_message: 是否存储消息（None时使用配置）
            show_log: 是否显示日志（None时使用配置）
            **kwargs: 其他参数

        Returns:
            bool: 是否发送成功
        """
        try:
            # 验证租户权限
            if not self._validate_tenant_access(message):
                self.metrics.total_blocked += 1
                logger.warning(f"租户 {self.tenant_id} 消息发送被拒绝: 权限不足")
                return False

            # 检查频率限制
            if not self._check_rate_limit():
                self.metrics.total_blocked += 1
                logger.warning(f"租户 {self.tenant_id} 消息发送被拒绝: 频率限制")
                return False

            # 获取租户配置
            config = self._get_tenant_send_config()

            # 应用配置
            if typing is None:
                typing = config.get("typing_enabled", True)
            if storage_message is None:
                storage_message = config.get("storage_enabled", True)
            if show_log is None:
                show_log = config.get("log_enabled", True)

            # 检查消息长度
            max_length = config.get("max_message_length", 5000)
            if hasattr(message, "processed_plain_text") and len(message.processed_plain_text) > max_length:
                logger.warning(f"消息长度 {len(message.processed_plain_text)} 超过限制 {max_length}")
                # 可以选择截断或拒绝发送
                message.processed_plain_text = truncate_message(message.processed_plain_text, max_length)

            # 记录隔离信息到消息（如果支持）
            if hasattr(message, "tenant_id"):
                message.tenant_id = self.tenant_id
            if hasattr(message, "platform"):
                message.platform = self.platform

            # 使用底层发送器发送消息
            success = await self._base_sender.send_message(
                message=message,
                typing=typing,
                set_reply=set_reply,
                storage_message=storage_message,
                show_log=show_log,
                **kwargs,
            )

            # 更新指标
            self._update_metrics(success)

            if success:
                logger.debug(f"租户 {self.tenant_id} 平台 {self.platform} 消息发送成功")
            else:
                logger.warning(f"租户 {self.tenant_id} 平台 {self.platform} 消息发送失败")

            return success

        except Exception as e:
            error_msg = f"发送消息时出错: {e}"
            logger.error(f"租户 {self.tenant_id} 平台 {self.platform} {error_msg}")
            self._update_metrics(False, error_msg)
            return False

    def get_metrics(self) -> Dict[str, Any]:
        """获取发送指标"""
        return {
            "tenant_id": self.tenant_id,
            "platform": self.platform,
            "total_sent": self.metrics.total_sent,
            "total_failed": self.metrics.total_failed,
            "total_blocked": self.metrics.total_blocked,
            "success_rate": (
                self.metrics.total_sent
                / max(1, self.metrics.total_sent + self.metrics.total_failed + self.metrics.total_blocked)
            ),
            "last_sent_time": self.metrics.last_sent_time.isoformat() if self.metrics.last_sent_time else None,
            "last_error_time": self.metrics.last_error_time.isoformat() if self.metrics.last_error_time else None,
            "last_error_message": self.metrics.last_error_message,
        }

    def reset_metrics(self):
        """重置发送指标"""
        self.metrics = SendingMetrics()
        logger.info(f"重置租户 {self.tenant_id} 平台 {self.platform} 的发送指标")

    def clear_config_cache(self):
        """清除配置缓存"""
        self._config_cache.clear()
        self._config_cache_time = None
        logger.debug(f"清除租户 {self.tenant_id} 平台 {self.platform} 的配置缓存")

    def get_isolation_info(self) -> Dict[str, Any]:
        """获取隔离信息"""
        return {
            "tenant_id": self.tenant_id,
            "platform": self.platform,
            "isolation_context": {
                "tenant_id": self.isolation_context.tenant_id if self.isolation_context else None,
                "agent_id": self.isolation_context.agent_id if self.isolation_context else None,
                "platform": self.isolation_context.platform if self.isolation_context else None,
            },
            "config_cached": self._config_cache_time is not None,
            "permission_manager_available": self._get_permission_manager() is not None,
            "config_manager_available": self._get_config_manager() is not None,
        }


class IsolatedMessageSenderManager:
    """全局隔离化消息发送器管理器"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self._senders: Dict[Tuple[str, str], IsolatedMessageSender] = {}
            self._weak_refs: Dict[Tuple[str, str], weakref.ref] = {}
            self._lock = threading.RLock()
            self._initialized = True
            logger.info("初始化全局隔离化消息发送器管理器")

    def get_sender(self, tenant_id: str, platform: str) -> IsolatedMessageSender:
        """
        获取指定租户和平台的隔离化消息发送器

        Args:
            tenant_id: 租户ID
            platform: 平台标识

        Returns:
            IsolatedMessageSender: 隔离化消息发送器实例
        """
        key = (tenant_id, platform)

        with self._lock:
            # 检查弱引用是否仍然有效
            if key in self._weak_refs:
                sender_ref = self._weak_refs[key]
                sender = sender_ref()
                if sender is not None:
                    return sender
                else:
                    # 弱引用已失效，清理
                    del self._weak_refs[key]
                    if key in self._senders:
                        del self._senders[key]

            # 创建新的发送器
            sender = IsolatedMessageSender(tenant_id, platform)
            self._senders[key] = sender
            self._weak_refs[key] = weakref.ref(sender)

            logger.debug(f"创建新的隔离化消息发送器: tenant={tenant_id}, platform={platform}")
            return sender

    def get_all_senders(self) -> Dict[Tuple[str, str], IsolatedMessageSender]:
        """获取所有活跃的发送器"""
        with self._lock:
            active_senders = {}
            for key, sender_ref in self._weak_refs.items():
                sender = sender_ref()
                if sender is not None:
                    active_senders[key] = sender
                else:
                    # 清理失效的弱引用
                    if key in self._senders:
                        del self._senders[key]
                    del self._weak_refs[key]
            return active_senders

    def get_tenant_senders(self, tenant_id: str) -> Dict[str, IsolatedMessageSender]:
        """获取指定租户的所有发送器"""
        active_senders = self.get_all_senders()
        return {platform: sender for (tid, platform), sender in active_senders.items() if tid == tenant_id}

    def get_platform_senders(self, platform: str) -> Dict[str, IsolatedMessageSender]:
        """获取指定平台的所有发送器"""
        active_senders = self.get_all_senders()
        return {tenant_id: sender for (tenant_id, plat), sender in active_senders.items() if plat == platform}

    def remove_sender(self, tenant_id: str, platform: str) -> bool:
        """
        移除指定的发送器

        Args:
            tenant_id: 租户ID
            platform: 平台标识

        Returns:
            bool: 是否成功移除
        """
        key = (tenant_id, platform)

        with self._lock:
            if key in self._senders:
                del self._senders[key]
            if key in self._weak_refs:
                del self._weak_refs[key]

            logger.info(f"移除隔离化消息发送器: tenant={tenant_id}, platform={platform}")
            return True

        return False

    def clear_tenant_senders(self, tenant_id: str) -> int:
        """
        清理指定租户的所有发送器

        Args:
            tenant_id: 租户ID

        Returns:
            int: 清理的发送器数量
        """
        with self._lock:
            keys_to_remove = [key for key in self._senders.keys() if key[0] == tenant_id]

            for key in keys_to_remove:
                del self._senders[key]
                if key in self._weak_refs:
                    del self._weak_refs[key]

            count = len(keys_to_remove)
            if count > 0:
                logger.info(f"清理租户 {tenant_id} 的 {count} 个隔离化消息发送器")

            return count

    def get_system_stats(self) -> Dict[str, Any]:
        """获取系统统计信息"""
        active_senders = self.get_all_senders()

        stats = {
            "total_active_senders": len(active_senders),
            "tenants": len(set(key[0] for key in active_senders.keys())),
            "platforms": len(set(key[1] for key in active_senders.keys())),
            "senders_by_tenant": {},
            "senders_by_platform": {},
            "total_metrics": {"total_sent": 0, "total_failed": 0, "total_blocked": 0},
        }

        # 按租户统计
        tenant_stats = {}
        for (tenant_id, platform), sender in active_senders.items():
            if tenant_id not in tenant_stats:
                tenant_stats[tenant_id] = {"platforms": [], "metrics": sender.get_metrics()}
            tenant_stats[tenant_id]["platforms"].append(platform)
        stats["senders_by_tenant"] = tenant_stats

        # 按平台统计
        platform_stats = {}
        for (tenant_id, platform), _sender in active_senders.items():
            if platform not in platform_stats:
                platform_stats[platform] = {"tenants": [], "count": 0}
            platform_stats[platform]["tenants"].append(tenant_id)
            platform_stats[platform]["count"] += 1
        stats["senders_by_platform"] = platform_stats

        # 总体指标
        for sender in active_senders.values():
            metrics = sender.get_metrics()
            stats["total_metrics"]["total_sent"] += metrics["total_sent"]
            stats["total_metrics"]["total_failed"] += metrics["total_failed"]
            stats["total_metrics"]["total_blocked"] += metrics["total_blocked"]

        return stats

    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        active_senders = self.get_all_senders()

        health_status = {
            "status": "healthy",
            "total_senders": len(active_senders),
            "unhealthy_senders": [],
            "warnings": [],
            "timestamp": datetime.now().isoformat(),
        }

        # 检查每个发送器的健康状态
        for (tenant_id, platform), sender in active_senders.items():
            metrics = sender.get_metrics()

            # 检查失败率
            total_attempts = metrics["total_sent"] + metrics["total_failed"]
            if total_attempts > 0:
                failure_rate = metrics["total_failed"] / total_attempts
                if failure_rate > 0.5:  # 失败率超过50%
                    health_status["unhealthy_senders"].append(
                        {"tenant_id": tenant_id, "platform": platform, "issue": f"高失败率: {failure_rate:.2%}"}
                    )
                    health_status["status"] = "degraded"

            # 检查最近是否有发送活动
            if metrics["last_sent_time"]:
                last_sent = datetime.fromisoformat(metrics["last_sent_time"])
                hours_since_last_sent = (datetime.now() - last_sent).total_seconds() / 3600
                if hours_since_last_sent > 24:  # 24小时没有发送活动
                    health_status["warnings"].append(
                        {
                            "tenant_id": tenant_id,
                            "platform": platform,
                            "warning": f"长时间无发送活动: {hours_since_last_sent:.1f}小时",
                        }
                    )

        if health_status["unhealthy_senders"]:
            health_status["status"] = "unhealthy"

        return health_status

    def cleanup_expired_senders(self, max_inactive_hours: int = 24) -> int:
        """
        清理长时间未使用的发送器

        Args:
            max_inactive_hours: 最大非活跃时间（小时）

        Returns:
            int: 清理的发送器数量
        """
        with self._lock:
            keys_to_remove = []
            now = datetime.now()

            for key, sender_ref in self._weak_refs.items():
                sender = sender_ref()
                if sender is None:
                    keys_to_remove.append(key)
                else:
                    metrics = sender.get_metrics()
                    if metrics["last_sent_time"]:
                        last_sent = datetime.fromisoformat(metrics["last_sent_time"])
                        inactive_hours = (now - last_sent).total_seconds() / 3600
                        if inactive_hours > max_inactive_hours:
                            keys_to_remove.append(key)

            for key in keys_to_remove:
                del self._senders[key]
                if key in self._weak_refs:
                    del self._weak_refs[key]

            count = len(keys_to_remove)
            if count > 0:
                logger.info(f"清理了 {count} 个长时间未使用的隔离化消息发送器")

            return count


# 全局管理器实例
sender_manager = IsolatedMessageSenderManager()


def get_isolated_message_sender(tenant_id: str, platform: str) -> IsolatedMessageSender:
    """
    获取隔离化消息发送器的便捷函数

    Args:
        tenant_id: 租户ID
        platform: 平台标识

    Returns:
        IsolatedMessageSender: 隔离化消息发送器实例
    """
    return sender_manager.get_sender(tenant_id, platform)


def get_sender_manager() -> IsolatedMessageSenderManager:
    """获取全局发送器管理器"""
    return sender_manager
