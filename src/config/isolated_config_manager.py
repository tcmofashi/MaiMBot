"""
多租户隔离配置管理器
支持T+A+P三维隔离的多层配置继承系统
实现配置继承逻辑：Global < Tenant < Agent < Platform
"""

import json
import threading
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
import tomlkit

from src.common.logger import get_logger
from src.config.config import global_config, model_config
from src.config.isolated_config_models import (
    TenantConfig,
    AgentConfig,
    PlatformConfig,
    ConfigHistory,
    ConfigQueryBuilder,
    create_isolated_config_tables,
)

logger = get_logger(__name__)


@dataclass
class ConfigCacheEntry:
    """配置缓存条目"""

    value: Any
    cache_time: datetime
    ttl: timedelta = field(default=timedelta(minutes=5))
    source: str = "unknown"  # 配置来源标识

    def is_expired(self) -> bool:
        """检查缓存是否过期"""
        return datetime.now() > self.cache_time + self.ttl


class ConfigCacheManager:
    """配置缓存管理器"""

    def __init__(self):
        self._cache: Dict[str, ConfigCacheEntry] = {}
        self._lock = threading.RLock()
        self._cleanup_interval = timedelta(minutes=10)
        self._last_cleanup = datetime.now()

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        with self._lock:
            self._cleanup_expired()
            entry = self._cache.get(key)
            if entry and not entry.is_expired():
                logger.debug(f"Config cache hit: {key}")
                return entry.value
            elif entry:
                logger.debug(f"Config cache expired: {key}")
                del self._cache[key]
            return None

    def set(self, key: str, value: Any, ttl: timedelta = None, source: str = "unknown"):
        """设置缓存值"""
        with self._lock:
            self._cache[key] = ConfigCacheEntry(
                value=value, cache_time=datetime.now(), ttl=ttl or timedelta(minutes=5), source=source
            )
            logger.debug(f"Config cache set: {key} from {source}")

    def invalidate(self, pattern: str = None):
        """失效缓存"""
        with self._lock:
            if pattern:
                keys_to_remove = [k for k in self._cache.keys() if pattern in k]
                for key in keys_to_remove:
                    del self._cache[key]
                    logger.debug(f"Config cache invalidated: {key}")
            else:
                self._cache.clear()
                logger.debug("All config cache cleared")

    def _cleanup_expired(self):
        """清理过期缓存"""
        now = datetime.now()
        if now - self._last_cleanup < self._cleanup_interval:
            return

        expired_keys = []
        for key, entry in self._cache.items():
            if entry.is_expired():
                expired_keys.append(key)

        for key in expired_keys:
            del self._cache[key]

        self._last_cleanup = now
        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired config cache entries")


class ConfigChangeNotifier:
    """配置变更通知器"""

    def __init__(self):
        self._listeners: Dict[str, List[Callable]] = {}
        self._lock = threading.RLock()

    def subscribe(self, config_key: str, callback: Callable):
        """订阅配置变更通知"""
        with self._lock:
            if config_key not in self._listeners:
                self._listeners[config_key] = []
            self._listeners[config_key].append(callback)
            logger.debug(f"Subscribed to config change: {config_key}")

    def unsubscribe(self, config_key: str, callback: Callable):
        """取消订阅配置变更通知"""
        with self._lock:
            if config_key in self._listeners:
                try:
                    self._listeners[config_key].remove(callback)
                    logger.debug(f"Unsubscribed from config change: {config_key}")
                except ValueError:
                    pass

    def notify(self, config_key: str, old_value: Any, new_value: Any, context: Dict[str, str]):
        """通知配置变更"""
        with self._lock:
            listeners = self._listeners.get(config_key, [])
            for callback in listeners:
                try:
                    callback(config_key, old_value, new_value, context)
                except Exception as e:
                    logger.error(f"Error in config change callback: {e}")


class IsolatedConfigManager:
    """多租户隔离配置管理器"""

    def __init__(self, tenant_id: str, agent_id: str):
        self.tenant_id = tenant_id
        self.agent_id = agent_id

        # 缓存和通知管理器
        self.cache_manager = ConfigCacheManager()
        self.change_notifier = ConfigChangeNotifier()

        # 全局配置的缓存（共享）
        self._global_config_cache = global_config
        self._global_model_config_cache = model_config

        # 配置文件路径
        self._config_dir = Path("config")
        self._tenant_config_dir = self._config_dir / "tenants" / tenant_id / "agents" / agent_id

        # 初始化数据库表
        self._init_database()

        # 加载配置
        self._load_initial_configs()

    def _init_database(self):
        """初始化数据库表"""
        try:
            create_isolated_config_tables()
        except Exception as e:
            logger.error(f"Failed to create isolated config tables: {e}")

    def _load_initial_configs(self):
        """加载初始配置"""
        try:
            # 确保租户配置目录存在
            self._tenant_config_dir.mkdir(parents=True, exist_ok=True)

            # 从数据库加载配置
            self._load_from_database()

            # 从文件加载配置（如果存在）
            self._load_from_files()

        except Exception as e:
            logger.error(f"Failed to load initial configs for {self.tenant_id}:{self.agent_id}: {e}")

    def _load_from_database(self):
        """从数据库加载配置"""
        try:
            # 查询该租户+智能体的所有配置
            configs = ConfigQueryBuilder.get_effective_configs(self.tenant_id, self.agent_id)

            # 将配置加载到缓存
            for key, config_info in configs.items():
                cache_key = f"{self.tenant_id}:{self.agent_id}:db:{key}"
                value = self._parse_config_value(config_info["value"], config_info["type"])
                self.cache_manager.set(cache_key, value, source=f"db:{config_info['level']}")

        except Exception as e:
            logger.error(f"Failed to load configs from database: {e}")

    def _load_from_files(self):
        """从文件加载配置"""
        try:
            # 租户级别配置文件
            tenant_config_file = self._config_dir / "tenants" / self.tenant_id / "tenant_config.toml"
            if tenant_config_file.exists():
                self._load_toml_file(tenant_config_file, "tenant")

            # 智能体级别配置文件
            agent_config_file = self._tenant_config_dir / "agent_config.toml"
            if agent_config_file.exists():
                self._load_toml_file(agent_config_file, "agent")

        except Exception as e:
            logger.error(f"Failed to load configs from files: {e}")

    def _load_toml_file(self, file_path: Path, config_level: str):
        """加载TOML配置文件"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                config_data = tomlkit.load(f)

            self._merge_config_dict(config_data, config_level, f"file:{config_level}")

        except Exception as e:
            logger.error(f"Failed to load TOML file {file_path}: {e}")

    def _merge_config_dict(self, config_dict: Dict[str, Any], config_level: str, source: str):
        """合并配置字典到缓存"""
        for category, category_data in config_dict.items():
            if category in ["inner", "version"]:  # 跳过元数据
                continue

            if isinstance(category_data, dict):
                for key, value in category_data.items():
                    cache_key = f"{self.tenant_id}:{self.agent_id}:{category}.{key}"
                    self.cache_manager.set(cache_key, value, source=source)

                    # 同步到数据库
                    self._save_to_database(category, key, value, config_level, source)

    def _save_to_database(self, category: str, key: str, value: Any, level: str, source: str):
        """保存配置到数据库"""
        try:
            # 根据级别选择对应的模型
            if level == "tenant":
                model_class = TenantConfig
                create_kwargs = {"tenant_id": self.tenant_id}
            elif level == "agent":
                model_class = AgentConfig
                create_kwargs = {"tenant_id": self.tenant_id, "agent_id": self.agent_id}
            elif level == "platform":
                model_class = PlatformConfig
                create_kwargs = {"tenant_id": self.tenant_id, "agent_id": self.agent_id, "platform": self.platform}
            else:
                return

            # 检查是否已存在
            existing = (
                model_class.select()
                .where(
                    (model_class.tenant_id == self.tenant_id)
                    & (model_class.agent_id == self.agent_id)
                    & (model_class.config_category == category)
                    & (model_class.config_key == key)
                )
                .first()
            )

            config_value = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
            config_type = "json" if not isinstance(value, str) else "string"

            if existing:
                # 更新现有配置
                old_value = existing.config_value
                if old_value != config_value:
                    existing.config_value = config_value
                    existing.config_type = config_type
                    existing.save()

                    # 记录变更历史
                    self._record_config_change(category, key, old_value, config_value, "update", source)
                    logger.info(f"Updated config {category}.{key} for {self.tenant_id}:{self.agent_id}")
            else:
                # 创建新配置
                model_class.create(
                    **create_kwargs,
                    config_category=category,
                    config_key=key,
                    config_value=config_value,
                    config_type=config_type,
                    description=f"Loaded from {source}",
                )

                # 记录变更历史
                self._record_config_change(category, key, None, config_value, "create", source)
                logger.info(f"Created config {category}.{key} for {self.tenant_id}:{self.agent_id}")

        except Exception as e:
            logger.error(f"Failed to save config to database: {e}")

    def _record_config_change(
        self, category: str, key: str, old_value: str, new_value: str, change_type: str, source: str
    ):
        """记录配置变更历史"""
        try:
            ConfigHistory.create(
                tenant_id=self.tenant_id,
                agent_id=self.agent_id,
                platform=getattr(self, "platform", None),
                config_category=category,
                config_key=key,
                old_value=old_value,
                new_value=new_value,
                change_type=change_type,
                change_reason=f"Updated from {source}",
            )
        except Exception as e:
            logger.error(f"Failed to record config change: {e}")

    def _parse_config_value(self, value: str, value_type: str) -> Any:
        """解析配置值"""
        try:
            if value_type == "json":
                return json.loads(value)
            elif value_type == "int":
                return int(value)
            elif value_type == "float":
                return float(value)
            elif value_type == "bool":
                return value.lower() in ("true", "1", "yes", "on")
            else:  # string
                return value
        except Exception as e:
            logger.warning(f"Failed to parse config value {value} as {value_type}: {e}")
            return value

    def get_config(self, category: str, key: str, default: Any = None, platform: str = None) -> Any:
        """获取配置值（支持继承逻辑）"""
        cache_key = f"{self.tenant_id}:{self.agent_id}:{platform or 'default'}:{category}.{key}"

        # 尝试从缓存获取
        cached_value = self.cache_manager.get(cache_key)
        if cached_value is not None:
            return cached_value

        # 按优先级查询配置
        config_value = self._query_config_hierarchy(category, key, platform)

        if config_value is not None:
            # 缓存结果
            self.cache_manager.set(cache_key, config_value, source="hierarchy")
            return config_value

        # 回退到全局配置
        return self._get_global_config(category, key, default)

    def _query_config_hierarchy(self, category: str, key: str, platform: str = None) -> Any:
        """按配置层级查询配置"""
        try:
            # 1. 平台级别配置（最高优先级）
            if platform:
                platform_config = (
                    PlatformConfig.select()
                    .where(
                        (PlatformConfig.tenant_id == self.tenant_id)
                        & (PlatformConfig.agent_id == self.agent_id)
                        & (PlatformConfig.platform == platform)
                        & (PlatformConfig.config_category == category)
                        & (PlatformConfig.config_key == key)
                        & (PlatformConfig.is_active)
                    )
                    .first()
                )

                if platform_config:
                    return self._parse_config_value(platform_config.config_value, platform_config.config_type)

            # 2. 智能体级别配置
            agent_config = (
                AgentConfig.select()
                .where(
                    (AgentConfig.tenant_id == self.tenant_id)
                    & (AgentConfig.agent_id == self.agent_id)
                    & (AgentConfig.config_category == category)
                    & (AgentConfig.config_key == key)
                    & (AgentConfig.is_active)
                )
                .first()
            )

            if agent_config:
                return self._parse_config_value(agent_config.config_value, agent_config.config_type)

            # 3. 租户级别配置
            tenant_config = (
                TenantConfig.select()
                .where(
                    (TenantConfig.tenant_id == self.tenant_id)
                    & (TenantConfig.config_category == category)
                    & (TenantConfig.config_key == key)
                    & (TenantConfig.is_active)
                )
                .first()
            )

            if tenant_config:
                return self._parse_config_value(tenant_config.config_value, tenant_config.config_type)

            return None

        except Exception as e:
            logger.error(f"Failed to query config hierarchy: {e}")
            return None

    def _get_global_config(self, category: str, key: str, default: Any = None) -> Any:
        """获取全局配置"""
        try:
            # 从全局配置对象获取
            if hasattr(self._global_config_cache, category):
                category_obj = getattr(self._global_config_cache, category)
                if hasattr(category_obj, key):
                    return getattr(category_obj, key)

            return default

        except Exception as e:
            logger.error(f"Failed to get global config {category}.{key}: {e}")
            return default

    def set_config(
        self, category: str, key: str, value: Any, level: str = "agent", platform: str = None, description: str = None
    ):
        """设置配置值"""
        try:
            # 确定模型类
            if level == "tenant":
                model_class = TenantConfig
                create_kwargs = {"tenant_id": self.tenant_id}
            elif level == "agent":
                model_class = AgentConfig
                create_kwargs = {"tenant_id": self.tenant_id, "agent_id": self.agent_id}
            elif level == "platform":
                if not platform:
                    raise ValueError("Platform level config requires platform parameter")
                model_class = PlatformConfig
                create_kwargs = {"tenant_id": self.tenant_id, "agent_id": self.agent_id, "platform": platform}
            else:
                raise ValueError(f"Invalid config level: {level}")

            # 获取旧值
            old_config = (
                model_class.select()
                .where(
                    (model_class.tenant_id == create_kwargs["tenant_id"])
                    & (model_class.agent_id == create_kwargs.get("agent_id", ""))
                    & (model_class.platform == create_kwargs.get("platform"))
                    & (model_class.config_category == category)
                    & (model_class.config_key == key)
                )
                .first()
            )

            old_value = old_config.config_value if old_config else None

            # 准备配置值
            config_value = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
            config_type = "json" if not isinstance(value, str) else "string"

            # 创建或更新配置
            if old_config:
                old_config.config_value = config_value
                old_config.config_type = config_type
                old_config.description = description
                old_config.save()
                change_type = "update"
            else:
                model_class.create(
                    **create_kwargs,
                    config_category=category,
                    config_key=key,
                    config_value=config_value,
                    config_type=config_type,
                    description=description,
                )
                change_type = "create"

            # 清理缓存
            cache_pattern = f"{self.tenant_id}:{self.agent_id}:*:{category}.{key}"
            self.cache_manager.invalidate(cache_pattern)

            # 记录变更历史
            self._record_config_change(category, key, old_value, config_value, change_type, "manual")

            # 通知变更
            self.change_notifier.notify(
                f"{category}.{key}",
                self._parse_config_value(old_value, "json") if old_value else None,
                value,
                {"tenant_id": self.tenant_id, "agent_id": self.agent_id, "platform": platform, "level": level},
            )

            logger.info(f"Set config {category}.{key} = {value} for {self.tenant_id}:{self.agent_id} at {level} level")

        except Exception as e:
            logger.error(f"Failed to set config {category}.{key}: {e}")
            raise

    def get_effective_config(self, platform: str = None) -> Dict[str, Any]:
        """获取完整的有效配置（合并所有级别）"""
        try:
            # 获取所有级别的配置
            configs = ConfigQueryBuilder.get_effective_configs(self.tenant_id, self.agent_id, platform)

            # 转换为配置对象格式
            result = {}

            # 按分类组织配置
            for key, config_info in configs.items():
                if "." not in key:
                    continue

                category, config_key = key.split(".", 1)
                value = self._parse_config_value(config_info["value"], config_info["type"])

                if category not in result:
                    result[category] = {}
                result[category][config_key] = value

            return result

        except Exception as e:
            logger.error(f"Failed to get effective config: {e}")
            return {}

    def reload_config(self):
        """重新加载配置"""
        try:
            logger.info(f"Reloading config for {self.tenant_id}:{self.agent_id}")

            # 清理缓存
            self.cache_manager.invalidate()

            # 重新加载配置
            self._load_from_database()
            self._load_from_files()

            logger.info(f"Config reloaded for {self.tenant_id}:{self.agent_id}")

        except Exception as e:
            logger.error(f"Failed to reload config: {e}")
            raise

    def subscribe_to_changes(self, config_key: str, callback: Callable):
        """订阅配置变更"""
        self.change_notifier.subscribe(config_key, callback)

    def unsubscribe_from_changes(self, config_key: str, callback: Callable):
        """取消订阅配置变更"""
        self.change_notifier.unsubscribe(config_key, callback)

    def get_config_history(self, category: str = None, key: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """获取配置变更历史"""
        try:
            query = ConfigHistory.select().where(
                (ConfigHistory.tenant_id == self.tenant_id) & (ConfigHistory.agent_id == self.agent_id)
            )

            if category:
                query = query.where(ConfigHistory.config_category == category)
            if key:
                query = query.where(ConfigHistory.config_key == key)

            histories = list(query.order_by(ConfigHistory.operated_at.desc()).limit(limit))

            return [
                {
                    "category": h.config_category,
                    "key": h.config_key,
                    "old_value": h.old_value,
                    "new_value": h.new_value,
                    "change_type": h.change_type,
                    "change_reason": h.change_reason,
                    "operated_by": h.operated_by,
                    "operated_at": h.operated_at,
                }
                for h in histories
            ]

        except Exception as e:
            logger.error(f"Failed to get config history: {e}")
            return []


# 全局配置管理器缓存
_isolated_config_managers: Dict[str, IsolatedConfigManager] = {}
_managers_lock = threading.RLock()


def get_isolated_config_manager(tenant_id: str, agent_id: str) -> IsolatedConfigManager:
    """获取隔离配置管理器实例（带缓存）"""
    manager_key = f"{tenant_id}:{agent_id}"

    with _managers_lock:
        if manager_key not in _isolated_config_managers:
            _isolated_config_managers[manager_key] = IsolatedConfigManager(tenant_id, agent_id)
            logger.debug(f"Created new isolated config manager for {manager_key}")

        return _isolated_config_managers[manager_key]


def clear_isolated_config_manager(tenant_id: str, agent_id: str = None):
    """清理隔离配置管理器缓存"""
    with _managers_lock:
        if agent_id:
            manager_key = f"{tenant_id}:{agent_id}"
            if manager_key in _isolated_config_managers:
                del _isolated_config_managers[manager_key]
                logger.debug(f"Cleared isolated config manager for {manager_key}")
        else:
            # 清理该租户的所有管理器
            keys_to_remove = [k for k in _isolated_config_managers.keys() if k.startswith(f"{tenant_id}:")]
            for key in keys_to_remove:
                del _isolated_config_managers[key]
                logger.debug(f"Cleared isolated config manager for {key}")


def get_all_isolated_config_managers() -> Dict[str, IsolatedConfigManager]:
    """获取所有隔离配置管理器"""
    with _managers_lock:
        return _isolated_config_managers.copy()
