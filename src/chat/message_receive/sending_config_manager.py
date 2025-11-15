"""
消息发送配置管理器
实现租户级别的发送配置管理，支持平台特定的发送参数设置
"""

import threading
from typing import Dict, Any, Optional, List, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from src.common.logger import get_logger

logger = get_logger("sending_config")


class ConfigScope(Enum):
    """配置作用域"""

    GLOBAL = "global"  # 全局配置
    TENANT = "tenant"  # 租户配置
    PLATFORM = "platform"  # 平台配置


@dataclass
class SendingConfig:
    """发送配置"""

    tenant_id: str
    platform: str
    scope: ConfigScope = ConfigScope.PLATFORM

    # 基础发送配置
    typing_enabled: bool = True
    storage_enabled: bool = True
    log_enabled: bool = True
    retry_enabled: bool = True
    max_retries: int = 3

    # 消息配置
    max_message_length: int = 5000
    message_truncate_enabled: bool = True
    split_long_messages: bool = False

    # 时间配置
    typing_simulation: bool = True
    typing_speed: float = 100.0  # 字符/分钟
    min_typing_time: float = 1.0  # 秒
    max_typing_time: float = 30.0  # 秒

    # 频率控制
    rate_limit_enabled: bool = False
    max_messages_per_minute: int = 30
    max_messages_per_hour: int = 500
    cooldown_between_messages: float = 0.5  # 秒

    # 回复配置
    auto_reply_enabled: bool = True
    reply_probability: float = 1.0
    reply_delay_min: float = 0.0  # 秒
    reply_delay_max: float = 5.0  # 秒

    # 格式化配置
    message_format: str = "default"  # default, markdown, plain
    emoji_enabled: bool = True
    image_compression: bool = True
    image_quality: int = 80  # 1-100

    # 通知配置
    notification_enabled: bool = True
    mention_enabled: bool = True
    quote_reply: bool = False

    # 自定义配置
    custom_headers: Dict[str, str] = field(default_factory=dict)
    custom_params: Dict[str, Any] = field(default_factory=dict)

    # 元数据
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    version: int = 1
    description: Optional[str] = None


class SendingConfigManager:
    """发送配置管理器"""

    def __init__(self, tenant_id: str, platform: str):
        """
        初始化发送配置管理器

        Args:
            tenant_id: 租户ID
            platform: 平台标识
        """
        self.tenant_id = tenant_id
        self.platform = platform

        # 配置缓存
        self._config_cache: Optional[SendingConfig] = None
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = 300  # 5分钟缓存

        # 配置变更监听器
        self._config_listeners: List[Callable[[SendingConfig], None]] = []

        # 线程锁
        self._lock = threading.RLock()

        logger.debug(f"创建发送配置管理器: tenant={tenant_id}, platform={platform}")

    def _load_default_config(self) -> SendingConfig:
        """
        加载默认配置

        Returns:
            SendingConfig: 默认配置
        """
        return SendingConfig(
            tenant_id=self.tenant_id, platform=self.platform, scope=ConfigScope.PLATFORM, description="默认发送配置"
        )

    def _load_config_from_storage(self) -> Optional[SendingConfig]:
        """
        从存储加载配置
        实际实现中应该从数据库或配置文件加载

        Returns:
            Optional[SendingConfig]: 配置对象
        """
        # TODO: 实现从数据库或配置文件加载
        # 这里返回None，表示使用默认配置
        return None

    def _merge_configs(self, base_config: SendingConfig, override_config: SendingConfig) -> SendingConfig:
        """
        合并配置

        Args:
            base_config: 基础配置
            override_config: 覆盖配置

        Returns:
            SendingConfig: 合并后的配置
        """
        merged = SendingConfig(tenant_id=self.tenant_id, platform=self.platform, scope=override_config.scope)

        # 合并所有字段，使用覆盖配置的值（如果非None）
        for field_name in SendingConfig.__dataclass_fields__:
            base_value = getattr(base_config, field_name, None)
            override_value = getattr(override_config, field_name, None)

            if override_value is not None:
                setattr(merged, field_name, override_value)
            else:
                setattr(merged, field_name, base_value)

        # 更新元数据
        merged.created_at = base_config.created_at
        merged.updated_at = datetime.now()
        merged.version = base_config.version + 1

        return merged

    def get_config(self, use_cache: bool = True) -> SendingConfig:
        """
        获取有效配置

        Args:
            use_cache: 是否使用缓存

        Returns:
            SendingConfig: 有效配置
        """
        with self._lock:
            # 检查缓存
            if (
                use_cache
                and self._config_cache
                and self._cache_time
                and (datetime.now() - self._cache_time).seconds < self._cache_ttl
            ):
                return self._config_cache

            # 加载配置
            stored_config = self._load_config_from_storage()
            default_config = self._load_default_config()

            if stored_config:
                effective_config = self._merge_configs(default_config, stored_config)
            else:
                effective_config = default_config

            # 缓存配置
            self._config_cache = effective_config
            self._cache_time = datetime.now()

            return effective_config

    def get_effective_config(self) -> Dict[str, Any]:
        """
        获取有效配置的字典形式

        Returns:
            Dict[str, Any]: 配置字典
        """
        config = self.get_config()
        return {
            "typing_enabled": config.typing_enabled,
            "storage_enabled": config.storage_enabled,
            "log_enabled": config.log_enabled,
            "retry_enabled": config.retry_enabled,
            "max_retries": config.max_retries,
            "max_message_length": config.max_message_length,
            "message_truncate_enabled": config.message_truncate_enabled,
            "split_long_messages": config.split_long_messages,
            "typing_simulation": config.typing_simulation,
            "typing_speed": config.typing_speed,
            "min_typing_time": config.min_typing_time,
            "max_typing_time": config.max_typing_time,
            "rate_limit_enabled": config.rate_limit_enabled,
            "max_messages_per_minute": config.max_messages_per_minute,
            "max_messages_per_hour": config.max_messages_per_hour,
            "cooldown_between_messages": config.cooldown_between_messages,
            "auto_reply_enabled": config.auto_reply_enabled,
            "reply_probability": config.reply_probability,
            "reply_delay_min": config.reply_delay_min,
            "reply_delay_max": config.reply_delay_max,
            "message_format": config.message_format,
            "emoji_enabled": config.emoji_enabled,
            "image_compression": config.image_compression,
            "image_quality": config.image_quality,
            "notification_enabled": config.notification_enabled,
            "mention_enabled": config.mention_enabled,
            "quote_reply": config.quote_reply,
            "custom_headers": config.custom_headers.copy(),
            "custom_params": config.custom_params.copy(),
        }

    def update_config(self, **kwargs) -> bool:
        """
        更新配置

        Args:
            **kwargs: 配置参数

        Returns:
            bool: 是否更新成功
        """
        try:
            with self._lock:
                current_config = self.get_config(use_cache=False)

                # 创建新的配置对象
                new_config = SendingConfig(tenant_id=self.tenant_id, platform=self.platform, scope=ConfigScope.PLATFORM)

                # 复制现有配置
                for field_name in SendingConfig.__dataclass_fields__:
                    if field_name not in ["tenant_id", "platform", "scope"]:
                        setattr(new_config, field_name, getattr(current_config, field_name))

                # 应用更新
                for key, value in kwargs.items():
                    if hasattr(new_config, key):
                        setattr(new_config, key, value)
                    else:
                        logger.warning(f"未知的配置参数: {key}")

                # 更新元数据
                new_config.created_at = current_config.created_at
                new_config.updated_at = datetime.now()
                new_config.version = current_config.version + 1

                # TODO: 持久化配置到数据库
                # self._save_config_to_storage(new_config)

                # 更新缓存
                self._config_cache = new_config
                self._cache_time = datetime.now()

                # 通知监听器
                self._notify_config_changed(new_config)

                logger.info(f"更新租户 {self.tenant_id} 平台 {self.platform} 的发送配置")
                return True

        except Exception as e:
            logger.error(f"更新配置时出错: {e}")
            return False

    def reset_to_default(self) -> bool:
        """
        重置为默认配置

        Returns:
            bool: 是否重置成功
        """
        try:
            with self._lock:
                default_config = self._load_default_config()

                # TODO: 从数据库删除自定义配置
                # self._delete_config_from_storage()

                # 更新缓存
                self._config_cache = default_config
                self._cache_time = datetime.now()

                # 通知监听器
                self._notify_config_changed(default_config)

                logger.info(f"重置租户 {self.tenant_id} 平台 {self.platform} 的发送配置为默认值")
                return True

        except Exception as e:
            logger.error(f"重置配置时出错: {e}")
            return False

    def get_config_value(self, key: str, default: Any = None) -> Any:
        """
        获取单个配置值

        Args:
            key: 配置键
            default: 默认值

        Returns:
            Any: 配置值
        """
        config = self.get_config()
        return getattr(config, key, default)

    def set_config_value(self, key: str, value: Any) -> bool:
        """
        设置单个配置值

        Args:
            key: 配置键
            value: 配置值

        Returns:
            bool: 是否设置成功
        """
        if hasattr(SendingConfig(), key):
            return self.update_config(**{key: value})
        else:
            logger.warning(f"未知的配置参数: {key}")
            return False

    def add_config_listener(self, listener: Callable[[SendingConfig], None]) -> str:
        """
        添加配置变更监听器

        Args:
            listener: 监听器函数

        Returns:
            str: 监听器ID
        """
        with self._lock:
            listener_id = f"listener_{datetime.now().timestamp()}"
            self._config_listeners.append((listener_id, listener))
            logger.debug(f"添加配置监听器: {listener_id}")
            return listener_id

    def remove_config_listener(self, listener_id: str) -> bool:
        """
        移除配置变更监听器

        Args:
            listener_id: 监听器ID

        Returns:
            bool: 是否移除成功
        """
        with self._lock:
            for i, (lid, _) in enumerate(self._config_listeners):
                if lid == listener_id:
                    del self._config_listeners[i]
                    logger.debug(f"移除配置监听器: {listener_id}")
                    return True
            return False

    def _notify_config_changed(self, new_config: SendingConfig):
        """
        通知配置变更

        Args:
            new_config: 新配置
        """
        try:
            for listener_id, listener in self._config_listeners:
                try:
                    listener(new_config)
                except Exception as e:
                    logger.error(f"配置监听器 {listener_id} 执行出错: {e}")
        except Exception as e:
            logger.error(f"通知配置变更时出错: {e}")

    def clear_cache(self):
        """清除配置缓存"""
        with self._lock:
            self._config_cache = None
            self._cache_time = None
            logger.debug(f"清除租户 {self.tenant_id} 平台 {self.platform} 的配置缓存")

    def export_config(self) -> Dict[str, Any]:
        """
        导出配置

        Returns:
            Dict[str, Any]: 配置数据
        """
        config = self.get_config()
        return {
            "tenant_id": config.tenant_id,
            "platform": config.platform,
            "scope": config.scope.value,
            "config": {
                "typing_enabled": config.typing_enabled,
                "storage_enabled": config.storage_enabled,
                "log_enabled": config.log_enabled,
                "retry_enabled": config.retry_enabled,
                "max_retries": config.max_retries,
                "max_message_length": config.max_message_length,
                "message_truncate_enabled": config.message_truncate_enabled,
                "split_long_messages": config.split_long_messages,
                "typing_simulation": config.typing_simulation,
                "typing_speed": config.typing_speed,
                "min_typing_time": config.min_typing_time,
                "max_typing_time": config.max_typing_time,
                "rate_limit_enabled": config.rate_limit_enabled,
                "max_messages_per_minute": config.max_messages_per_minute,
                "max_messages_per_hour": config.max_messages_per_hour,
                "cooldown_between_messages": config.cooldown_between_messages,
                "auto_reply_enabled": config.auto_reply_enabled,
                "reply_probability": config.reply_probability,
                "reply_delay_min": config.reply_delay_min,
                "reply_delay_max": config.reply_delay_max,
                "message_format": config.message_format,
                "emoji_enabled": config.emoji_enabled,
                "image_compression": config.image_compression,
                "image_quality": config.image_quality,
                "notification_enabled": config.notification_enabled,
                "mention_enabled": config.mention_enabled,
                "quote_reply": config.quote_reply,
                "custom_headers": config.custom_headers,
                "custom_params": config.custom_params,
            },
            "metadata": {
                "created_at": config.created_at.isoformat(),
                "updated_at": config.updated_at.isoformat(),
                "version": config.version,
                "description": config.description,
            },
        }

    def import_config(self, config_data: Dict[str, Any], overwrite: bool = False) -> bool:
        """
        导入配置

        Args:
            config_data: 配置数据
            overwrite: 是否覆盖现有配置

        Returns:
            bool: 是否导入成功
        """
        try:
            if not overwrite:
                # 检查是否已有配置
                existing_config = self._load_config_from_storage()
                if existing_config:
                    logger.warning("租户已有配置，跳过导入（使用overwrite=True强制覆盖）")
                    return False

            config_section = config_data.get("config", {})
            metadata = config_data.get("metadata", {})

            # 更新配置
            success = self.update_config(**config_section)

            if success and metadata.get("description"):
                self.update_config(description=metadata["description"])

            logger.info(f"导入租户 {self.tenant_id} 平台 {self.platform} 的配置: {success}")
            return success

        except Exception as e:
            logger.error(f"导入配置时出错: {e}")
            return False

    def get_config_stats(self) -> Dict[str, Any]:
        """获取配置统计信息"""
        config = self.get_config()

        return {
            "tenant_id": self.tenant_id,
            "platform": self.platform,
            "scope": config.scope.value,
            "version": config.version,
            "created_at": config.created_at.isoformat(),
            "updated_at": config.updated_at.isoformat(),
            "description": config.description,
            "cache_status": {
                "cached": self._config_cache is not None,
                "cache_age_seconds": (datetime.now() - self._cache_time).seconds if self._cache_time else None,
            },
            "listener_count": len(self._config_listeners),
            "config_summary": {
                "typing_enabled": config.typing_enabled,
                "rate_limit_enabled": config.rate_limit_enabled,
                "max_message_length": config.max_message_length,
                "retry_enabled": config.retry_enabled,
                "message_format": config.message_format,
            },
        }


# 全局配置管理器缓存
_config_managers: Dict[Tuple[str, str], SendingConfigManager] = {}
_managers_lock = threading.RLock()


def get_sending_config_manager(tenant_id: str, platform: str) -> SendingConfigManager:
    """
    获取发送配置管理器的便捷函数

    Args:
        tenant_id: 租户ID
        platform: 平台标识

    Returns:
        SendingConfigManager: 配置管理器实例
    """
    key = (tenant_id, platform)

    with _managers_lock:
        if key not in _config_managers:
            _config_managers[key] = SendingConfigManager(tenant_id, platform)
        return _config_managers[key]


def clear_config_manager_cache():
    """清除所有配置管理器缓存"""
    with _managers_lock:
        _config_managers.clear()
        logger.info("清除所有发送配置管理器缓存")


def get_all_config_managers() -> Dict[Tuple[str, str], SendingConfigManager]:
    """获取所有配置管理器"""
    with _managers_lock:
        return _config_managers.copy()


def get_config_managers_by_tenant(tenant_id: str) -> Dict[str, SendingConfigManager]:
    """获取指定租户的所有配置管理器"""
    with _managers_lock:
        return {platform: manager for (tid, platform), manager in _config_managers.items() if tid == tenant_id}


def get_config_managers_by_platform(platform: str) -> Dict[str, SendingConfigManager]:
    """获取指定平台的所有配置管理器"""
    with _managers_lock:
        return {tenant_id: manager for (tenant_id, plat), manager in _config_managers.items() if plat == platform}
