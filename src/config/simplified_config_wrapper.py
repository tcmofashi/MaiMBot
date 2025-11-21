"""
简化的配置包装器
基于双层配置系统（bot_config + agent_config）提供统一的配置访问接口
"""

from typing import Any, Dict
from src.common.logger import get_logger

logger = get_logger(__name__)


class SimplifiedConfigSection:
    """简化配置节包装器"""

    def __init__(self, config_data: Dict[str, Any], section_name: str = ""):
        """
        初始化配置节包装器

        Args:
            config_data: 配置数据字典
            section_name: 节名称
        """
        self._config_data = config_data
        self._section_name = section_name

    def __getattr__(self, name: str) -> Any:
        """获取属性"""
        if name in self._config_data:
            return self._config_data[name]
        else:
            raise AttributeError(f"'{self._section_name}' object has no attribute '{name}'")

    def __getitem__(self, key: str) -> Any:
        """支持字典式访问"""
        return self.__getattr__(key)

    def __hasattr__(self, name: str) -> bool:
        """检查属性是否存在"""
        return name in self._config_data

    def get(self, key: str, default: Any = None) -> Any:
        """安全的get方法"""
        return self._config_data.get(key, default)


class SimplifiedChatConfigWrapper:
    """简化的聊天配置包装器"""

    def __init__(self, chat_config: Dict[str, Any]):
        """
        初始化聊天配置包装器

        Args:
            chat_config: 聊天配置数据字典
        """
        self._chat_config = chat_config or {}

    def get_talk_value(self, stream_id: str) -> float:
        """获取聊天频率值"""
        try:
            talk_value = self._chat_config.get("talk_value", 1.0)
            if callable(talk_value):
                return talk_value(stream_id)
            else:
                return float(talk_value)
        except Exception as e:
            logger.warning(f"获取talk_value失败，使用默认值1.0: {e}")
            return 1.0

    def get_auto_chat_value(self, stream_id: str) -> float:
        """获取主动聊天频率值"""
        try:
            auto_chat_value = self._chat_config.get("auto_chat_value", 1.0)
            if callable(auto_chat_value):
                return auto_chat_value(stream_id)
            else:
                return float(auto_chat_value)
        except Exception as e:
            logger.warning(f"获取auto_chat_value失败，使用默认值: {e}")
            return 1.0

    def __getattr__(self, name: str) -> Any:
        """获取其他属性"""
        if name in self._chat_config:
            return self._chat_config[name]
        else:
            # 为常见的聊天配置属性提供默认值
            default_values = {
                "max_context_size": 18,
                "talk_value": 1.0,
                "auto_chat_value": 1.0,
                "planner_smooth": 0,
                "mentioned_bot_reply": True,
                "enable_talk_value_rules": True,
                "enable_auto_chat_value_rules": False,
                "talk_value_rules": [],
                "auto_chat_value_rules": [],
            }
            if name in default_values:
                logger.warning(f"聊天配置缺少属性 '{name}'，使用默认值: {default_values[name]}")
                return default_values[name]
            else:
                raise AttributeError(f"'chat_config' object has no attribute '{name}'")


class SimplifiedUnifiedConfigWrapper:
    """简化的统一配置包装器"""

    def __init__(self, config_data: Dict[str, Any]):
        """
        初始化统一配置包装器

        Args:
            config_data: 完整的配置数据字典
        """
        self._config_data = config_data or {}
        self._chat_wrapper = None

    @property
    def chat(self) -> SimplifiedChatConfigWrapper:
        """获取聊天配置包装器"""
        if self._chat_wrapper is None:
            chat_config = self._config_data.get("chat", {})
            self._chat_wrapper = SimplifiedChatConfigWrapper(chat_config)

        return self._chat_wrapper

    def __getattr__(self, name: str) -> Any:
        """获取其他配置节"""
        if name in self._config_data:
            attr_value = self._config_data[name]
            # 如果是字典，包装它
            if isinstance(attr_value, dict):
                return SimplifiedConfigSection(attr_value, name)
            return attr_value
        else:
            # 为常见的配置节提供默认值
            default_sections = {
                "personality": {
                    "personality": "是一个友好的AI助手，乐于帮助用户解决问题。",
                    "reply_style": "回复简洁明了，语气友好。",
                    "interest": "对各种话题都感兴趣，喜欢与人交流。",
                },
                "bot": {"platform": "test", "nickname": "小千", "alias_names": ["小千"]},
                "expression": {"mode": "classic", "learning_enabled": True, "default_learning_intensity": 1.0},
                "memory": {"max_memory_number": 100, "max_memory_size": 2048, "memory_build_frequency": 1},
                "mood": {
                    "enable_mood": False,
                    "mood_update_threshold": 1,
                    "emotion_style": "情绪稳定，友好亲切",
                },
                "emoji": {
                    "emoji_chance": 0.4,
                    "max_reg_num": 40,
                    "do_replace": True,
                    "check_interval": 120,
                    "steal_emoji": True,
                    "content_filtration": True,
                    "filtration_prompt": "动漫风格，画风可爱",
                },
                "tool": {"enable_tool": True, "tool_cache_ttl": 3, "max_tool_execution_time": 30},
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
            }
            if name in default_sections:
                logger.warning(f"配置缺少节 '{name}'，使用默认配置")
                return SimplifiedConfigSection(default_sections[name], name)
            else:
                raise AttributeError(f"'config' object has no attribute '{name}'")

    def __getitem__(self, key: str) -> Any:
        """支持字典式访问"""
        return self.__getattr__(key)

    def get_full_config(self) -> Dict[str, Any]:
        """获取完整的配置数据"""
        return self._config_data.copy()

    def get_config_value(self, section: str, key: str = None, default: Any = None) -> Any:
        """直接获取配置值"""
        try:
            if section not in self._config_data:
                return default

            section_data = self._config_data[section]

            if key is None:
                return section_data

            if isinstance(section_data, dict):
                return section_data.get(key, default)
            else:
                return section_data

        except Exception as e:
            logger.error(f"获取配置值失败 {section}.{key}: {e}")
            return default
