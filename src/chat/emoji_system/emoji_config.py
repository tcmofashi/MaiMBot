"""
表情配置系统

支持多租户的表情配置管理，包括租户级别和智能体级别的表情定制，
支持表情导入导出功能和配置继承逻辑。
"""

import json
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from pathlib import Path
import threading

from src.common.logger import get_logger

logger = get_logger("emoji_config")


@dataclass
class EmojiPreference:
    """表情偏好设置"""

    emotions: List[str] = field(default_factory=list)  # 偏好的情感标签
    banned_emotions: List[str] = field(default_factory=list)  # 禁止的情感标签
    custom_rules: Dict[str, Any] = field(default_factory=dict)  # 自定义规则
    weights: Dict[str, float] = field(default_factory=dict)  # 情感权重


@dataclass
class EmojiCollection:
    """表情包集合配置"""

    name: str
    description: str = ""
    emoji_hashes: List[str] = field(default_factory=list)  # 表情包哈希列表
    is_active: bool = True
    created_time: float = field(default_factory=time.time)
    updated_time: float = field(default_factory=time.time)
    tags: List[str] = field(default_factory=list)


@dataclass
class TenantEmojiConfig:
    """租户表情配置"""

    tenant_id: str
    # 基础配置
    max_emoji_count: int = 500
    auto_replace: bool = True
    content_filter: bool = True
    filter_prompt: str = "可爱、萌、有趣、正能量"
    # 表情偏好
    preference: EmojiPreference = field(default_factory=EmojiPreference)
    # 表情包集合
    collections: Dict[str, EmojiCollection] = field(default_factory=dict)
    # 统计信息
    total_usage: int = 0
    daily_usage: int = 0
    last_reset_time: float = field(default_factory=time.time)


@dataclass
class AgentEmojiConfig:
    """智能体表情配置"""

    tenant_id: str
    agent_id: str
    # 继承设置
    inherit_from_tenant: bool = True
    inherit_collections: List[str] = field(default_factory=list)
    # 基础配置
    max_emoji_count: int = 200
    auto_replace: bool = True
    # 表情偏好（覆盖租户设置）
    preference: EmojiPreference = field(default_factory=EmojiPreference)
    # 表情包集合
    collections: Dict[str, EmojiCollection] = field(default_factory=dict)
    # 统计信息
    total_usage: int = 0
    daily_usage: int = 0
    last_reset_time: float = field(default_factory=time.time)


class EmojiConfigManager:
    """表情配置管理器"""

    def __init__(self, config_dir: str = "data/emoji_configs"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # 内存缓存
        self._tenant_configs: Dict[str, TenantEmojiConfig] = {}
        self._agent_configs: Dict[str, AgentEmojiConfig] = {}
        self._lock = threading.RLock()

        # 配置文件路径
        self.tenant_config_file = self.config_dir / "tenant_configs.json"
        self.agent_config_file = self.config_dir / "agent_configs.json"

        logger.info(f"初始化表情配置管理器: {config_dir}")

    def initialize(self) -> None:
        """初始化配置管理器"""
        try:
            self._load_configs()
            logger.info("表情配置管理器初始化完成")
        except Exception as e:
            logger.error(f"表情配置管理器初始化失败: {e}")
            raise

    def _load_configs(self) -> None:
        """加载配置文件"""
        try:
            # 加载租户配置
            if self.tenant_config_file.exists():
                with open(self.tenant_config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for tenant_id, config_data in data.items():
                        self._tenant_configs[tenant_id] = TenantEmojiConfig(**config_data)
                logger.info(f"加载租户配置: {len(self._tenant_configs)}个")

            # 加载智能体配置
            if self.agent_config_file.exists():
                with open(self.agent_config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for key, config_data in data.items():
                        tenant_id, agent_id = key.split(":", 1)
                        config_data["tenant_id"] = tenant_id
                        config_data["agent_id"] = agent_id
                        self._agent_configs[key] = AgentEmojiConfig(**config_data)
                logger.info(f"加载智能体配置: {len(self._agent_configs)}个")

        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")

    def _save_configs(self) -> None:
        """保存配置文件"""
        try:
            # 保存租户配置
            tenant_data = {tenant_id: asdict(config) for tenant_id, config in self._tenant_configs.items()}
            with open(self.tenant_config_file, "w", encoding="utf-8") as f:
                json.dump(tenant_data, f, ensure_ascii=False, indent=2)

            # 保存智能体配置
            agent_data = {key: asdict(config) for key, config in self._agent_configs.items()}
            with open(self.agent_config_file, "w", encoding="utf-8") as f:
                json.dump(agent_data, f, ensure_ascii=False, indent=2)

            logger.debug("配置文件保存成功")

        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")

    # ==================== 租户配置管理 ====================

    def get_tenant_config(self, tenant_id: str) -> TenantEmojiConfig:
        """获取租户表情配置"""
        with self._lock:
            if tenant_id not in self._tenant_configs:
                # 创建默认配置
                self._tenant_configs[tenant_id] = TenantEmojiConfig(tenant_id=tenant_id)
                self._save_configs()
            return self._tenant_configs[tenant_id]

    def update_tenant_config(self, tenant_id: str, **kwargs) -> bool:
        """更新租户表情配置"""
        try:
            with self._lock:
                config = self.get_tenant_config(tenant_id)

                # 更新配置
                for key, value in kwargs.items():
                    if hasattr(config, key):
                        setattr(config, key, value)

                self._save_configs()
                logger.info(f"更新租户配置: tenant={tenant_id}")
                return True

        except Exception as e:
            logger.error(f"更新租户配置失败: {e}")
            return False

    def delete_tenant_config(self, tenant_id: str) -> bool:
        """删除租户表情配置"""
        try:
            with self._lock:
                if tenant_id in self._tenant_configs:
                    del self._tenant_configs[tenant_id]
                    self._save_configs()
                    logger.info(f"删除租户配置: tenant={tenant_id}")
                    return True
                return False

        except Exception as e:
            logger.error(f"删除租户配置失败: {e}")
            return False

    # ==================== 智能体配置管理 ====================

    def get_agent_config(self, tenant_id: str, agent_id: str) -> AgentEmojiConfig:
        """获取智能体表情配置"""
        key = f"{tenant_id}:{agent_id}"

        with self._lock:
            if key not in self._agent_configs:
                # 创建默认配置
                self._agent_configs[key] = AgentEmojiConfig(tenant_id=tenant_id, agent_id=agent_id)
                self._save_configs()
            return self._agent_configs[key]

    def update_agent_config(self, tenant_id: str, agent_id: str, **kwargs) -> bool:
        """更新智能体表情配置"""
        try:
            with self._lock:
                config = self.get_agent_config(tenant_id, agent_id)

                # 更新配置
                for key_name, value in kwargs.items():
                    if hasattr(config, key_name):
                        setattr(config, key_name, value)

                self._save_configs()
                logger.info(f"更新智能体配置: tenant={tenant_id}, agent={agent_id}")
                return True

        except Exception as e:
            logger.error(f"更新智能体配置失败: {e}")
            return False

    def delete_agent_config(self, tenant_id: str, agent_id: str) -> bool:
        """删除智能体表情配置"""
        try:
            key = f"{tenant_id}:{agent_id}"

            with self._lock:
                if key in self._agent_configs:
                    del self._agent_configs[key]
                    self._save_configs()
                    logger.info(f"删除智能体配置: tenant={tenant_id}, agent={agent_id}")
                    return True
                return False

        except Exception as e:
            logger.error(f"删除智能体配置失败: {e}")
            return False

    # ==================== 表情包集合管理 ====================

    def add_emoji_collection(
        self,
        tenant_id: str,
        agent_id: Optional[str],
        collection_name: str,
        emoji_hashes: List[str],
        description: str = "",
        tags: List[str] = None,
    ) -> bool:
        """添加表情包集合"""
        try:
            collection = EmojiCollection(
                name=collection_name, description=description, emoji_hashes=emoji_hashes, tags=tags or []
            )

            if agent_id:
                # 智能体级别集合
                config = self.get_agent_config(tenant_id, agent_id)
                config.collections[collection_name] = collection
            else:
                # 租户级别集合
                config = self.get_tenant_config(tenant_id)
                config.collections[collection_name] = collection

            with self._lock:
                self._save_configs()

            logger.info(f"添加表情包集合: tenant={tenant_id}, agent={agent_id}, collection={collection_name}")
            return True

        except Exception as e:
            logger.error(f"添加表情包集合失败: {e}")
            return False

    def remove_emoji_collection(self, tenant_id: str, agent_id: Optional[str], collection_name: str) -> bool:
        """移除表情包集合"""
        try:
            if agent_id:
                # 智能体级别集合
                config = self.get_agent_config(tenant_id, agent_id)
                if collection_name in config.collections:
                    del config.collections[collection_name]
            else:
                # 租户级别集合
                config = self.get_tenant_config(tenant_id)
                if collection_name in config.collections:
                    del config.collections[collection_name]

            with self._lock:
                self._save_configs()

            logger.info(f"移除表情包集合: tenant={tenant_id}, agent={agent_id}, collection={collection_name}")
            return True

        except Exception as e:
            logger.error(f"移除表情包集合失败: {e}")
            return False

    def get_emoji_collections(self, tenant_id: str, agent_id: Optional[str]) -> Dict[str, EmojiCollection]:
        """获取表情包集合"""
        try:
            collections = {}

            # 获取租户级别集合
            tenant_config = self.get_tenant_config(tenant_id)
            collections.update(tenant_config.collections)

            if agent_id:
                # 获取智能体级别集合（覆盖租户级别的同名集合）
                agent_config = self.get_agent_config(tenant_id, agent_id)
                collections.update(agent_config.collections)

            return collections

        except Exception as e:
            logger.error(f"获取表情包集合失败: {e}")
            return {}

    # ==================== 配置继承逻辑 ====================

    def get_effective_config(self, tenant_id: str, agent_id: str) -> Dict[str, Any]:
        """获取有效的表情配置（包含继承逻辑）"""
        try:
            # 获取租户配置
            tenant_config = self.get_tenant_config(tenant_id)

            # 获取智能体配置
            agent_config = self.get_agent_config(tenant_id, agent_id)

            # 合并配置
            effective_config = {
                "max_emoji_count": agent_config.max_emoji_count,
                "auto_replace": agent_config.auto_replace,
                "content_filter": tenant_config.content_filter,
                "filter_prompt": tenant_config.filter_prompt,
            }

            # 合并情感偏好
            effective_preference = {
                "emotions": agent_config.preference.emotions + tenant_config.preference.emotions,
                "banned_emotions": agent_config.preference.banned_emotions + tenant_config.preference.banned_emotions,
                "weights": {**tenant_config.preference.weights, **agent_config.preference.weights},
                "custom_rules": {**tenant_config.preference.custom_rules, **agent_config.preference.custom_rules},
            }

            effective_config["preference"] = effective_preference

            # 获取表情包集合
            collections = {}
            if agent_config.inherit_from_tenant:
                collections.update(tenant_config.collections)
            collections.update(agent_config.collections)
            effective_config["collections"] = collections

            return effective_config

        except Exception as e:
            logger.error(f"获取有效配置失败: {e}")
            return {}

    # ==================== 导入导出功能 ====================

    def export_config(self, tenant_id: str, agent_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """导出配置"""
        try:
            if agent_id:
                # 导出智能体配置
                config = self.get_agent_config(tenant_id, agent_id)
                effective_config = self.get_effective_config(tenant_id, agent_id)

                export_data = {
                    "type": "agent",
                    "tenant_id": tenant_id,
                    "agent_id": agent_id,
                    "config": asdict(config),
                    "effective_config": effective_config,
                    "export_time": time.time(),
                }
            else:
                # 导出租户配置
                config = self.get_tenant_config(tenant_id)

                export_data = {
                    "type": "tenant",
                    "tenant_id": tenant_id,
                    "config": asdict(config),
                    "export_time": time.time(),
                }

            return export_data

        except Exception as e:
            logger.error(f"导出配置失败: {e}")
            return None

    def import_config(self, config_data: Dict[str, Any], overwrite: bool = False) -> bool:
        """导入配置"""
        try:
            config_type = config_data.get("type")
            tenant_id = config_data.get("tenant_id")

            if not tenant_id:
                logger.error("导入配置失败: 缺少租户ID")
                return False

            if config_type == "tenant":
                # 导入租户配置
                config_dict = config_data.get("config", {})
                if overwrite or tenant_id not in self._tenant_configs:
                    self._tenant_configs[tenant_id] = TenantEmojiConfig(**config_dict)
                    logger.info(f"导入租户配置: tenant={tenant_id}")
                else:
                    logger.warning(f"租户配置已存在，跳过导入: tenant={tenant_id}")
                    return False

            elif config_type == "agent":
                # 导入智能体配置
                agent_id = config_data.get("agent_id")
                if not agent_id:
                    logger.error("导入配置失败: 缺少智能体ID")
                    return False

                config_dict = config_data.get("config", {})
                key = f"{tenant_id}:{agent_id}"

                if overwrite or key not in self._agent_configs:
                    self._agent_configs[key] = AgentEmojiConfig(**config_dict)
                    logger.info(f"导入智能体配置: tenant={tenant_id}, agent={agent_id}")
                else:
                    logger.warning(f"智能体配置已存在，跳过导入: tenant={tenant_id}, agent={agent_id}")
                    return False

            else:
                logger.error(f"导入配置失败: 未知配置类型 {config_type}")
                return False

            with self._lock:
                self._save_configs()

            return True

        except Exception as e:
            logger.error(f"导入配置失败: {e}")
            return False

    # ==================== 统计和监控 ====================

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                "tenant_count": len(self._tenant_configs),
                "agent_count": len(self._agent_configs),
                "total_collections": sum(len(config.collections) for config in self._tenant_configs.values())
                + sum(len(config.collections) for config in self._agent_configs.values()),
                "config_dir": str(self.config_dir),
            }

    def reset_daily_usage(self, tenant_id: Optional[str] = None) -> None:
        """重置日使用统计"""
        try:
            with self._lock:
                if tenant_id:
                    # 重置指定租户
                    if tenant_id in self._tenant_configs:
                        self._tenant_configs[tenant_id].daily_usage = 0
                        self._tenant_configs[tenant_id].last_reset_time = time.time()

                    # 重置租户下的所有智能体
                    for key, config in self._agent_configs.items():
                        if key.startswith(f"{tenant_id}:"):
                            config.daily_usage = 0
                            config.last_reset_time = time.time()
                else:
                    # 重置所有
                    for config in self._tenant_configs.values():
                        config.daily_usage = 0
                        config.last_reset_time = time.time()

                    for config in self._agent_configs.values():
                        config.daily_usage = 0
                        config.last_reset_time = time.time()

                self._save_configs()
                logger.info(f"重置日使用统计: tenant={tenant_id or 'all'}")

        except Exception as e:
            logger.error(f"重置日使用统计失败: {e}")


# 全局配置管理器实例
_emoji_config_manager: Optional[EmojiConfigManager] = None
_config_lock = threading.Lock()


def get_emoji_config_manager() -> EmojiConfigManager:
    """获取表情配置管理器"""
    global _emoji_config_manager

    if _emoji_config_manager is None:
        with _config_lock:
            if _emoji_config_manager is None:
                _emoji_config_manager = EmojiConfigManager()
                _emoji_config_manager.initialize()

    return _emoji_config_manager


# 便捷函数
def get_tenant_emoji_config(tenant_id: str) -> TenantEmojiConfig:
    """获取租户表情配置"""
    return get_emoji_config_manager().get_tenant_config(tenant_id)


def get_agent_emoji_config(tenant_id: str, agent_id: str) -> AgentEmojiConfig:
    """获取智能体表情配置"""
    return get_emoji_config_manager().get_agent_config(tenant_id, agent_id)


def get_effective_emoji_config(tenant_id: str, agent_id: str) -> Dict[str, Any]:
    """获取有效的表情配置"""
    return get_emoji_config_manager().get_effective_config(tenant_id, agent_id)
