"""
简化的双层配置管理器
只保留两层配置：bot_config（底层）和 agent_config（上层）
agent_config 可以覆盖 bot_config 的配置项
"""

import threading
from typing import Dict, Any
from pathlib import Path
import tomlkit
from dataclasses import dataclass

from src.common.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ConfigLayer:
    """配置层"""

    name: str
    config_data: Dict[str, Any]
    priority: int  # 优先级，数字越大优先级越高


class SimplifiedConfigManager:
    """简化的双层配置管理器"""

    def __init__(self, tenant_id: str, agent_id: str):
        self.tenant_id = tenant_id
        self.agent_id = agent_id

        # 配置层
        self._bot_config = None  # 底层配置
        self._agent_config = None  # 上层配置
        self._merged_config = None  # 合并后的配置

        # 配置文件路径
        self._config_dir = Path("config")
        self._bot_config_file = self._config_dir / "bot_config.toml"
        self._agent_config_dir = self._config_dir / "tenants" / tenant_id / "agents" / agent_id
        self._agent_config_file = self._agent_config_dir / "agent_config.toml"

        # 线程锁
        self._lock = threading.RLock()

        # 初始化配置
        self._load_configs()

    def _load_configs(self):
        """加载配置"""
        with self._lock:
            try:
                # 1. 加载底层 bot_config
                self._load_bot_config()

                # 2. 加载上层 agent_config
                self._load_agent_config()

                # 3. 合并配置
                self._merge_configs()

                logger.info(f"简化配置管理器初始化完成: {self.tenant_id}:{self.agent_id}")

            except Exception as e:
                logger.error(f"加载配置失败: {e}")
                # 使用最小可用配置
                self._load_minimal_config()

    def _load_bot_config(self):
        """加载底层 bot_config"""
        try:
            if self._bot_config_file.exists():
                with open(self._bot_config_file, "r", encoding="utf-8") as f:
                    self._bot_config = tomlkit.load(f)
                logger.debug(f"成功加载 bot_config: {self._bot_config_file}")
            else:
                # 使用内存中的全局配置作为底层配置
                self._bot_config = self._convert_global_config_to_dict()
                logger.debug("使用全局配置作为 bot_config")

        except Exception as e:
            logger.error(f"加载 bot_config 失败: {e}")
            self._bot_config = {}

    def _load_agent_config(self):
        """加载上层 agent_config"""
        try:
            # 确保目录存在
            self._agent_config_dir.mkdir(parents=True, exist_ok=True)

            if self._agent_config_file.exists():
                with open(self._agent_config_file, "r", encoding="utf-8") as f:
                    self._agent_config = tomlkit.load(f)
                logger.debug(f"成功加载 agent_config: {self._agent_config_file}")
            else:
                # 创建默认的 agent_config
                self._agent_config = self._create_default_agent_config()
                self._save_agent_config()
                logger.debug("创建默认 agent_config")

        except Exception as e:
            logger.error(f"加载 agent_config 失败: {e}")
            self._agent_config = {}

    def _create_default_agent_config(self) -> Dict[str, Any]:
        """创建默认的 agent_config"""
        return {
            "inner": {"version": "1.0.0", "created_at": "2025-11-17", "description": f"Agent {self.agent_id} 默认配置"},
            "chat": {
                "talk_value": 1.0,
                "mentioned_bot_reply": True,
                "max_context_size": 18,
                "auto_chat_value": 1.0,
                "planner_smooth": 0,
            },
            "tool": {
                "enable_tool": True,
                "tool_cache_ttl": 3,
                "max_tool_execution_time": 30,
                "enable_tool_parallel": False,
            },
            "response_splitter": {
                "enable": True,
                "max_length": 256,
                "max_sentence_num": 4,
                "enable_kaomoji_protection": False,
                "split_delimiters": ["。", "！", "？", "；", "~"],
            },
            "chinese_typo": {
                "enable": True,
                "error_rate": 0.001,
                "min_freq": 9,
                "tone_error_rate": 0.1,
                "word_replace_rate": 0.006,
            },
            "personality": {
                "personality": "是一个友好的AI助手，乐于帮助用户解决问题。",
                "reply_style": "回复简洁明了，语气友好。",
                "interest": "对各种话题都感兴趣，喜欢与人交流。",
            },
            "bot": {"platform": "test", "nickname": "小千", "alias_names": ["小千"]},
            "expression": {"mode": "classic", "learning_enabled": True, "default_learning_intensity": 1.0},
            "memory": {
                "max_memory_number": 100,
                "max_memory_size": 2048,
                "memory_build_frequency": 1,
                "enable_memory_compression": True,
            },
            "mood": {"enable_mood": False, "mood_update_threshold": 1, "emotion_style": "情绪稳定，友好亲切"},
            "emoji": {
                "emoji_chance": 0.4,
                "max_reg_num": 40,
                "do_replace": True,
                "check_interval": 120,
                "steal_emoji": True,
                "content_filtration": True,
                "filtration_prompt": "动漫风格，画风可爱",
            },
        }

    def _save_agent_config(self):
        """保存 agent_config 到文件"""
        try:
            with open(self._agent_config_file, "w", encoding="utf-8") as f:
                tomlkit.dump(self._agent_config, f)
            logger.debug(f"保存 agent_config: {self._agent_config_file}")
        except Exception as e:
            logger.error(f"保存 agent_config 失败: {e}")

    def _convert_global_config_to_dict(self) -> Dict[str, Any]:
        """将全局配置对象转换为字典"""
        try:
            # 从现有的 bot_config.toml 读取
            if self._bot_config_file.exists():
                with open(self._bot_config_file, "r", encoding="utf-8") as f:
                    return tomlkit.load(f)
            else:
                # 使用代码中的默认配置
                return self._create_default_bot_config()
        except Exception as e:
            logger.error(f"转换全局配置失败: {e}")
            return self._create_default_bot_config()

    def _create_default_bot_config(self) -> Dict[str, Any]:
        """创建默认的 bot_config"""
        return {
            "inner": {"version": "6.20.1"},
            "bot": {"platform": "qq", "nickname": "小千", "alias_names": ["小千"]},
            "personality": {
                "personality": "是一个女大学生，现在在读大二，会刷贴吧。",
                "reply_style": "请回复的平淡一些，简短一些，说中文，不要刻意突出自身学科背景。可以参考贴吧，知乎和微博的回复风格。",
                "interest": "对技术相关话题，游戏和动漫相关话题感兴趣，也对日常话题感兴趣，不喜欢太过沉重严肃的话题",
            },
            "chat": {
                "talk_value": 1.0,
                "mentioned_bot_reply": True,
                "max_context_size": 18,
                "auto_chat_value": 1.0,
                "planner_smooth": 0,
            },
            "tool": {"enable_tool": True},
            "response_splitter": {"enable": True, "max_length": 256, "max_sentence_num": 4},
            "chinese_typo": {"enable": True, "error_rate": 0.001},
            "expression": {"mode": "classic", "learning_list": [["", "enable", "enable", "1.0"]]},
            "memory": {"max_memory_number": 100, "max_memory_size": 2048, "memory_build_frequency": 1},
            "mood": {"enable_mood": False, "mood_update_threshold": 1},
            "emoji": {"emoji_chance": 0.4, "max_reg_num": 40, "do_replace": True},
        }

    def _merge_configs(self):
        """合并配置：agent_config 覆盖 bot_config"""
        try:
            # 深度合并配置
            self._merged_config = self._deep_merge(self._bot_config.copy(), self._agent_config)
            logger.debug("配置合并完成")
        except Exception as e:
            logger.error(f"合并配置失败: {e}")
            self._merged_config = self._bot_config.copy()

    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """深度合并字典"""
        result = base.copy()

        for key, value in override.items():
            if key == "inner":  # 跳过元数据
                continue

            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    def get_config(self, section: str, key: str = None, default: Any = None) -> Any:
        """获取配置值"""
        with self._lock:
            try:
                if self._merged_config is None:
                    self._merge_configs()

                if section not in self._merged_config:
                    logger.warning(f"配置节不存在: {section}")
                    return default

                section_config = self._merged_config[section]

                if key is None:
                    return section_config

                if key not in section_config:
                    logger.warning(f"配置键不存在: {section}.{key}")
                    return default

                return section_config[key]

            except Exception as e:
                logger.error(f"获取配置失败 {section}.{key}: {e}")
                return default

    def get_full_config(self) -> Dict[str, Any]:
        """获取完整的合并配置"""
        with self._lock:
            if self._merged_config is None:
                self._merge_configs()
            return self._merged_config.copy()

    def get_merged_config(self) -> Dict[str, Any]:
        """获取合并后的配置（别名方法）"""
        return self.get_full_config()

    def get_unified_config(self) -> "SimplifiedUnifiedConfigWrapper":
        """获取统一配置包装器"""
        from .simplified_config_wrapper import SimplifiedUnifiedConfigWrapper

        return SimplifiedUnifiedConfigWrapper(self._merged_config)

    def update_agent_config(self, section: str, key: str, value: Any):
        """更新 agent_config"""
        with self._lock:
            try:
                # 确保配置节存在
                if section not in self._agent_config:
                    self._agent_config[section] = {}

                # 更新值
                self._agent_config[section][key] = value

                # 重新合并配置
                self._merge_configs()

                # 保存到文件
                self._save_agent_config()

                logger.info(f"更新 agent_config: {section}.{key} = {value}")

            except Exception as e:
                logger.error(f"更新 agent_config 失败: {e}")
                raise

    def reload_config(self):
        """重新加载配置"""
        with self._lock:
            logger.info("重新加载配置...")
            self._load_configs()
            logger.info("配置重新加载完成")

    def get_config_layers_info(self) -> Dict[str, Any]:
        """获取配置层信息（用于调试）"""
        return {
            "bot_config_sections": list(self._bot_config.keys()) if self._bot_config else [],
            "agent_config_sections": list(self._agent_config.keys()) if self._agent_config else [],
            "merged_config_sections": list(self._merged_config.keys()) if self._merged_config else [],
        }

    def _load_minimal_config(self):
        """加载最小可用配置（降级方案）"""
        logger.warning("使用最小配置降级方案")
        self._bot_config = self._create_default_bot_config()
        self._agent_config = self._create_default_agent_config()
        self._merge_configs()


# 全局配置管理器缓存
_simplified_config_managers: Dict[str, SimplifiedConfigManager] = {}
_managers_lock = threading.RLock()


def get_simplified_config_manager(tenant_id: str, agent_id: str) -> SimplifiedConfigManager:
    """获取简化配置管理器实例（带缓存）"""
    manager_key = f"{tenant_id}:{agent_id}"

    with _managers_lock:
        if manager_key not in _simplified_config_managers:
            _simplified_config_managers[manager_key] = SimplifiedConfigManager(tenant_id, agent_id)
            logger.debug(f"创建新的简化配置管理器: {manager_key}")

        return _simplified_config_managers[manager_key]


def clear_simplified_config_manager(tenant_id: str, agent_id: str = None):
    """清理简化配置管理器缓存"""
    with _managers_lock:
        if agent_id:
            manager_key = f"{tenant_id}:{agent_id}"
            if manager_key in _simplified_config_managers:
                del _simplified_config_managers[manager_key]
                logger.debug(f"清理简化配置管理器: {manager_key}")
        else:
            # 清理该租户的所有管理器
            keys_to_remove = [k for k in _simplified_config_managers.keys() if k.startswith(f"{tenant_id}:")]
            for key in keys_to_remove:
                del _simplified_config_managers[key]
                logger.debug(f"清理简化配置管理器: {key}")


def get_all_simplified_config_managers() -> Dict[str, SimplifiedConfigManager]:
    """获取所有简化配置管理器"""
    with _managers_lock:
        return _simplified_config_managers.copy()
