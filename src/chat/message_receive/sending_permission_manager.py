"""
消息发送权限管理器
实现租户级别的发送权限验证，支持平台级别的发送限制和黑名单
"""

import threading
from typing import Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from src.common.logger import get_logger

# 导入隔离上下文
try:
    from src.isolation.isolation_context import IsolationContext
except ImportError:
    # 兼容性处理
    class IsolationContext:
        def __init__(self, *args, **kwargs):
            pass


from src.chat.message_receive.message import MessageSending

logger = get_logger("sending_permission")


class PermissionLevel(Enum):
    """权限级别"""

    ALLOWED = "allowed"  # 允许发送
    DENIED = "denied"  # 拒绝发送
    RESTRICTED = "restricted"  # 受限制发送
    UNKNOWN = "unknown"  # 未知状态


class RestrictionType(Enum):
    """限制类型"""

    BLACKLIST = "blacklist"  # 黑名单
    WHITELIST = "whitelist"  # 白名单
    RATE_LIMIT = "rate_limit"  # 频率限制
    TIME_WINDOW = "time_window"  # 时间窗口限制


@dataclass
class SendingPermission:
    """发送权限配置"""

    tenant_id: str
    platform: str
    permission_level: PermissionLevel = PermissionLevel.ALLOWED

    # 限制配置
    max_messages_per_hour: Optional[int] = None
    max_messages_per_day: Optional[int] = None
    max_message_length: Optional[int] = None

    # 时间窗口限制
    allowed_time_start: Optional[str] = None  # HH:MM格式
    allowed_time_end: Optional[str] = None  # HH:MM格式
    allowed_days: Optional[Set[int]] = None  # 0-6，0为周一

    # 黑白名单
    blocked_chat_ids: Set[str] = field(default_factory=set)
    allowed_chat_ids: Set[str] = field(default_factory=set)
    blocked_user_ids: Set[str] = field(default_factory=set)
    allowed_user_ids: Set[str] = field(default_factory=set)

    # 元数据
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    notes: Optional[str] = None

    def __post_init__(self):
        """初始化后处理"""
        if isinstance(self.allowed_days, list):
            self.allowed_days = set(self.allowed_days)


@dataclass
class PermissionCheckResult:
    """权限检查结果"""

    allowed: bool
    permission_level: PermissionLevel
    reason: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


class SendingPermissionManager:
    """发送权限管理器"""

    def __init__(self, tenant_id: str, platform: str):
        """
        初始化发送权限管理器

        Args:
            tenant_id: 租户ID
            platform: 平台标识
        """
        self.tenant_id = tenant_id
        self.platform = platform

        # 权限配置缓存
        self._permission_cache: Optional[SendingPermission] = None
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = 300  # 5分钟缓存

        # 临时限制（运行时设置）
        self._temp_restrictions: Dict[str, Dict[str, Any]] = {}

        # 线程锁
        self._lock = threading.RLock()

        logger.debug(f"创建发送权限管理器: tenant={tenant_id}, platform={platform}")

    def _load_permission_config(self) -> SendingPermission:
        """
        加载权限配置
        这里可以实现从数据库、配置文件或其他存储加载配置
        目前使用默认配置作为示例

        Returns:
            SendingPermission: 权限配置
        """
        # TODO: 实现从数据库或配置文件加载
        # 这里返回一个默认的允许配置
        return SendingPermission(
            tenant_id=self.tenant_id,
            platform=self.platform,
            permission_level=PermissionLevel.ALLOWED,
            max_messages_per_hour=100,
            max_messages_per_day=2000,
            max_message_length=10000,
            allowed_time_start="00:00",
            allowed_time_end="23:59",
            allowed_days={0, 1, 2, 3, 4, 5, 6},  # 所有天
            notes="默认权限配置",
        )

    def get_permission_config(self, use_cache: bool = True) -> SendingPermission:
        """
        获取权限配置

        Args:
            use_cache: 是否使用缓存

        Returns:
            SendingPermission: 权限配置
        """
        with self._lock:
            # 检查缓存
            if (
                use_cache
                and self._permission_cache
                and self._cache_time
                and (datetime.now() - self._cache_time).seconds < self._cache_ttl
            ):
                return self._permission_cache

            # 加载新配置
            config = self._load_permission_config()
            self._permission_cache = config
            self._cache_time = datetime.now()

            return config

    def _check_time_window(self, config: SendingPermission) -> Tuple[bool, str]:
        """
        检查时间窗口限制

        Args:
            config: 权限配置

        Returns:
            Tuple[bool, str]: (是否允许, 原因)
        """
        try:
            now = datetime.now()

            # 检查允许的日期
            if config.allowed_days is not None:
                # 0为周一，6为周日
                current_day = now.weekday()
                if current_day not in config.allowed_days:
                    return False, f"今天不允许发送消息（只允许: {sorted(config.allowed_days)}）"

            # 检查允许的时间段
            if config.allowed_time_start and config.allowed_time_end:
                current_time = now.time()
                start_time = datetime.strptime(config.allowed_time_start, "%H:%M").time()
                end_time = datetime.strptime(config.allowed_time_end, "%H:%M").time()

                if start_time <= end_time:
                    # 同一天的时间范围
                    if not (start_time <= current_time <= end_time):
                        return (
                            False,
                            f"当前时间不在允许发送时间段内（{config.allowed_time_start} - {config.allowed_time_end}）",
                        )
                else:
                    # 跨天的时间范围
                    if not (current_time >= start_time or current_time <= end_time):
                        return (
                            False,
                            f"当前时间不在允许发送时间段内（{config.allowed_time_start} - {config.allowed_time_end}）",
                        )

            return True, "时间窗口检查通过"

        except Exception as e:
            logger.error(f"检查时间窗口时出错: {e}")
            return True, "时间窗口检查出错，默认允许"

    def _check_blacklist_whitelist(self, message: MessageSending, config: SendingPermission) -> Tuple[bool, str]:
        """
        检查黑白名单

        Args:
            message: 消息对象
            config: 权限配置

        Returns:
            Tuple[bool, str]: (是否允许, 原因)
        """
        try:
            # 获取聊天流和用户信息
            chat_id = None
            user_id = None

            if hasattr(message, "chat_stream") and message.chat_stream:
                chat_id = getattr(message.chat_stream, "stream_id", None)

            if hasattr(message, "message_info") and hasattr(message.message_info, "sender_info"):
                user_id = getattr(message.message_info.sender_info, "user_id", None)

            # 检查聊天流黑名单
            if chat_id and config.blocked_chat_ids and chat_id in config.blocked_chat_ids:
                return False, f"聊天流 {chat_id} 在黑名单中"

            # 检查用户黑名单
            if user_id and config.blocked_user_ids and user_id in config.blocked_user_ids:
                return False, f"用户 {user_id} 在黑名单中"

            # 如果有白名单，检查是否在白名单中
            if config.allowed_chat_ids and chat_id not in config.allowed_chat_ids:
                return False, f"聊天流 {chat_id} 不在白名单中"

            if config.allowed_user_ids and user_id not in config.allowed_user_ids:
                return False, f"用户 {user_id} 不在白名单中"

            return True, "黑白名单检查通过"

        except Exception as e:
            logger.error(f"检查黑白名单时出错: {e}")
            return True, "黑白名单检查出错，默认允许"

    def _check_message_length(self, message: MessageSending, config: SendingPermission) -> Tuple[bool, str]:
        """
        检查消息长度

        Args:
            message: 消息对象
            config: 权限配置

        Returns:
            Tuple[bool, str]: (是否允许, 原因)
        """
        try:
            if not config.max_message_length:
                return True, "无消息长度限制"

            message_length = 0
            if hasattr(message, "processed_plain_text"):
                message_length = len(message.processed_plain_text)
            elif hasattr(message, "plain_text"):
                message_length = len(message.plain_text)

            if message_length > config.max_message_length:
                return False, f"消息长度 {message_length} 超过限制 {config.max_message_length}"

            return True, "消息长度检查通过"

        except Exception as e:
            logger.error(f"检查消息长度时出错: {e}")
            return True, "消息长度检查出错，默认允许"

    def _check_rate_limit(self, config: SendingPermission) -> Tuple[bool, str]:
        """
        检查频率限制
        这里需要实现基于Redis或其他存储的频率计数
        目前返回通过作为示例

        Args:
            config: 权限配置

        Returns:
            Tuple[bool, str]: (是否允许, 原因)
        """
        try:
            # TODO: 实现实际的频率限制逻辑
            # 这里需要访问持久化存储来计数
            # 可以使用Redis的滑动窗口算法或数据库计数

            # 示例：简单的时间窗口计数（基于内存，仅适用于单实例）
            if config.max_messages_per_hour or config.max_messages_per_day:
                # 这里应该实现实际的计数逻辑
                pass

            return True, "频率限制检查通过"

        except Exception as e:
            logger.error(f"检查频率限制时出错: {e}")
            return True, "频率限制检查出错，默认允许"

    def _check_temp_restrictions(self, message: MessageSending) -> Tuple[bool, str]:
        """
        检查临时限制

        Args:
            message: 消息对象

        Returns:
            Tuple[bool, str]: (是否允许, 原因)
        """
        try:
            if not self._temp_restrictions:
                return True, "无临时限制"

            now = datetime.now()
            expired_keys = []

            for key, restriction in self._temp_restrictions.items():
                # 检查是否过期
                if restriction.get("expires_at"):
                    expires_at = restriction["expires_at"]
                    if isinstance(expires_at, str):
                        expires_at = datetime.fromisoformat(expires_at)
                    if now > expires_at:
                        expired_keys.append(key)
                        continue

                # 检查限制类型
                restriction_type = restriction.get("type")
                if restriction_type == "block_all":
                    return False, restriction.get("reason", "临时限制：禁止所有发送")
                elif restriction_type == "block_chat":
                    chat_id = restriction.get("chat_id")
                    if (
                        hasattr(message, "chat_stream")
                        and message.chat_stream
                        and hasattr(message.chat_stream, "stream_id")
                        and message.chat_stream.stream_id == chat_id
                    ):
                        return False, restriction.get("reason", f"临时限制：禁止发送到聊天流 {chat_id}")
                elif restriction_type == "block_user":
                    user_id = restriction.get("user_id")
                    if (
                        hasattr(message, "message_info")
                        and hasattr(message.message_info, "sender_info")
                        and hasattr(message.message_info.sender_info, "user_id")
                        and message.message_info.sender_info.user_id == user_id
                    ):
                        return False, restriction.get("reason", f"临时限制：禁止用户 {user_id} 发送")

            # 清理过期的临时限制
            for key in expired_keys:
                del self._temp_restrictions[key]

            return True, "临时限制检查通过"

        except Exception as e:
            logger.error(f"检查临时限制时出错: {e}")
            return True, "临时限制检查出错，默认允许"

    def can_send_message(self, message: MessageSending, isolation_context: Optional[IsolationContext] = None) -> bool:
        """
        检查是否可以发送消息（简化版本）

        Args:
            message: 消息对象
            isolation_context: 隔离上下文

        Returns:
            bool: 是否允许发送
        """
        result = self.check_permission(message, isolation_context)
        return result.allowed

    def check_permission(
        self, message: MessageSending, isolation_context: Optional[IsolationContext] = None
    ) -> PermissionCheckResult:
        """
        检查发送权限（详细版本）

        Args:
            message: 消息对象
            isolation_context: 隔离上下文

        Returns:
            PermissionCheckResult: 权限检查结果
        """
        try:
            # 获取权限配置
            config = self.get_permission_config()

            # 检查基本权限级别
            if config.permission_level == PermissionLevel.DENIED:
                return PermissionCheckResult(
                    allowed=False, permission_level=PermissionLevel.DENIED, reason="租户发送权限被拒绝"
                )

            # 执行各项检查
            checks = [
                ("时间窗口", self._check_time_window, config),
                ("黑白名单", self._check_blacklist_whitelist, message, config),
                ("消息长度", self._check_message_length, message, config),
                ("频率限制", self._check_rate_limit, config),
                ("临时限制", self._check_temp_restrictions, message),
            ]

            details = {}
            for check_name, check_func, *args in checks:
                try:
                    allowed, reason = check_func(*args)
                    details[check_name] = {"allowed": allowed, "reason": reason}
                    if not allowed:
                        return PermissionCheckResult(
                            allowed=False,
                            permission_level=config.permission_level,
                            reason=f"{check_name}检查失败: {reason}",
                            details=details,
                        )
                except Exception as e:
                    logger.error(f"{check_name}检查时出错: {e}")
                    details[check_name] = {"allowed": False, "reason": f"检查出错: {e}"}
                    return PermissionCheckResult(
                        allowed=False,
                        permission_level=config.permission_level,
                        reason=f"{check_name}检查出错",
                        details=details,
                    )

            # 所有检查通过
            return PermissionCheckResult(
                allowed=True, permission_level=config.permission_level, reason="所有权限检查通过", details=details
            )

        except Exception as e:
            logger.error(f"检查发送权限时出错: {e}")
            return PermissionCheckResult(
                allowed=False, permission_level=PermissionLevel.UNKNOWN, reason=f"权限检查出错: {e}"
            )

    def add_temp_restriction(
        self,
        restriction_type: str,
        reason: str,
        expires_at: Optional[datetime] = None,
        chat_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> str:
        """
        添加临时限制

        Args:
            restriction_type: 限制类型 (block_all, block_chat, block_user)
            reason: 限制原因
            expires_at: 过期时间
            chat_id: 聊天流ID（block_chat时需要）
            user_id: 用户ID（block_user时需要）

        Returns:
            str: 限制键
        """
        with self._lock:
            key = f"{restriction_type}_{datetime.now().timestamp()}"

            restriction = {
                "type": restriction_type,
                "reason": reason,
                "created_at": datetime.now(),
                "expires_at": expires_at,
            }

            if chat_id:
                restriction["chat_id"] = chat_id
            if user_id:
                restriction["user_id"] = user_id

            self._temp_restrictions[key] = restriction
            logger.info(f"添加临时限制: {restriction_type} - {reason}")

            return key

    def remove_temp_restriction(self, key: str) -> bool:
        """
        移除临时限制

        Args:
            key: 限制键

        Returns:
            bool: 是否成功移除
        """
        with self._lock:
            if key in self._temp_restrictions:
                del self._temp_restrictions[key]
                logger.info(f"移除临时限制: {key}")
                return True
            return False

    def get_temp_restrictions(self) -> Dict[str, Dict[str, Any]]:
        """获取所有临时限制"""
        with self._lock:
            # 清理过期的限制
            now = datetime.now()
            expired_keys = []

            for key, restriction in self._temp_restrictions.items():
                if restriction.get("expires_at"):
                    expires_at = restriction["expires_at"]
                    if isinstance(expires_at, str):
                        expires_at = datetime.fromisoformat(expires_at)
                    if now > expires_at:
                        expired_keys.append(key)

            for key in expired_keys:
                del self._temp_restrictions[key]

            return self._temp_restrictions.copy()

    def clear_cache(self):
        """清除权限配置缓存"""
        with self._lock:
            self._permission_cache = None
            self._cache_time = None
            logger.debug(f"清除租户 {self.tenant_id} 平台 {self.platform} 的权限配置缓存")

    def update_permission_config(self, config: SendingPermission) -> bool:
        """
        更新权限配置
        目前只是更新缓存，实际实现中应该持久化到数据库

        Args:
            config: 新的权限配置

        Returns:
            bool: 是否更新成功
        """
        try:
            with self._lock:
                # TODO: 实现数据库更新逻辑
                config.updated_at = datetime.now()
                self._permission_cache = config
                self._cache_time = datetime.now()

                logger.info(f"更新租户 {self.tenant_id} 平台 {self.platform} 的权限配置")
                return True

        except Exception as e:
            logger.error(f"更新权限配置时出错: {e}")
            return False

    def get_permission_stats(self) -> Dict[str, Any]:
        """获取权限统计信息"""
        config = self.get_permission_config()
        temp_restrictions = self.get_temp_restrictions()

        return {
            "tenant_id": self.tenant_id,
            "platform": self.platform,
            "permission_level": config.permission_level.value,
            "config_details": {
                "max_messages_per_hour": config.max_messages_per_hour,
                "max_messages_per_day": config.max_messages_per_day,
                "max_message_length": config.max_message_length,
                "has_time_window": bool(config.allowed_time_start and config.allowed_time_end),
                "has_allowed_days": bool(config.allowed_days),
                "blocked_chats_count": len(config.blocked_chat_ids),
                "allowed_chats_count": len(config.allowed_chat_ids),
                "blocked_users_count": len(config.blocked_user_ids),
                "allowed_users_count": len(config.allowed_user_ids),
                "last_updated": config.updated_at.isoformat(),
            },
            "temp_restrictions": {
                "count": len(temp_restrictions),
                "types": list(set(r.get("type") for r in temp_restrictions.values())),
            },
            "cache_status": {
                "cached": self._permission_cache is not None,
                "cache_age_seconds": (datetime.now() - self._cache_time).seconds if self._cache_time else None,
            },
        }


# 全局权限管理器缓存
_permission_managers: Dict[Tuple[str, str], SendingPermissionManager] = {}
_managers_lock = threading.RLock()


def get_sending_permission_manager(tenant_id: str, platform: str) -> SendingPermissionManager:
    """
    获取发送权限管理器的便捷函数

    Args:
        tenant_id: 租户ID
        platform: 平台标识

    Returns:
        SendingPermissionManager: 权限管理器实例
    """
    key = (tenant_id, platform)

    with _managers_lock:
        if key not in _permission_managers:
            _permission_managers[key] = SendingPermissionManager(tenant_id, platform)
        return _permission_managers[key]


def clear_permission_manager_cache():
    """清除所有权限管理器缓存"""
    with _managers_lock:
        _permission_managers.clear()
        logger.info("清除所有发送权限管理器缓存")


def get_all_permission_managers() -> Dict[Tuple[str, str], SendingPermissionManager]:
    """获取所有权限管理器"""
    with _managers_lock:
        return _permission_managers.copy()
