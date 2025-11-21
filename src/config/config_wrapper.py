"""
配置包装器类
用于统一隔离配置对象和全局配置对象的接口
集成简化配置系统，提供向后兼容性
"""

from typing import Any, Dict, Optional, Union
from src.common.logger import get_logger

logger = get_logger(__name__)

# 尝试导入简化配置系统
try:
    from .config_integration import get_unified_config as get_simplified_unified_config
    from .config_integration import get_chat_config as get_simplified_chat_config
    from .config_integration import is_integration_enabled

    SIMPLIFIED_CONFIG_AVAILABLE = True
    logger.info("简化配置系统已加载")
except ImportError as e:
    SIMPLIFIED_CONFIG_AVAILABLE = False
    logger.warning(f"简化配置系统不可用，回退到原有系统: {e}")


class ConfigSectionWrapper:
    """配置节包装器，提供统一的属性访问接口"""

    def __init__(self, config_data: Union[Dict[str, Any], Any], section_name: str = ""):
        """
        初始化配置节包装器

        Args:
            config_data: 配置数据（字典或对象）
            section_name: 节名称
        """
        self._config_data = config_data
        self._section_name = section_name

    def __getattr__(self, name: str) -> Any:
        """获取属性，支持字典和对象两种方式"""
        if hasattr(self._config_data, name):
            return getattr(self._config_data, name)
        elif isinstance(self._config_data, dict) and name in self._config_data:
            return self._config_data[name]
        else:
            raise AttributeError(f"'{self._section_name}' object has no attribute '{name}'")

    def __getitem__(self, key: str) -> Any:
        """支持字典式访问"""
        return self.__getattr__(key)

    def __hasattr__(self, name: str) -> bool:
        """检查属性是否存在"""
        if hasattr(self._config_data, name):
            return True
        elif isinstance(self._config_data, dict) and name in self._config_data:
            return True
        return False


class ChatConfigWrapper:
    """聊天配置包装器，提供聊天相关的方法"""

    def __init__(self, chat_config: Union[Dict[str, Any], Any]):
        """
        初始化聊天配置包装器

        Args:
            chat_config: 聊天配置数据（字典或对象）
        """
        self._chat_config = chat_config

    def get_talk_value(self, stream_id: str) -> float:
        """获取聊天频率值"""
        try:
            if hasattr(self._chat_config, "get_talk_value"):
                # 如果是配置对象，直接调用方法
                return self._chat_config.get_talk_value(stream_id)
            elif isinstance(self._chat_config, dict):
                # 如果是字典，尝试获取talk_value或返回默认值
                talk_value = self._chat_config.get("talk_value", 1.0)  # 修改默认值为1.0
                if callable(talk_value):
                    return talk_value(stream_id)
                else:
                    return float(talk_value)
            else:
                # 回退到默认值（修改为1.0确保必定回复）
                return 1.0
        except Exception as e:
            logger.warning(f"获取talk_value失败，使用默认值1.0: {e}")
            return 1.0

    def get_auto_chat_value(self, stream_id: str) -> float:
        """获取主动聊天频率值"""
        try:
            if hasattr(self._chat_config, "get_auto_chat_value"):
                # 如果是配置对象，直接调用方法
                return self._chat_config.get_auto_chat_value(stream_id)
            elif isinstance(self._chat_config, dict):
                # 如果是字典，尝试获取auto_chat_value或返回默认值
                auto_chat_value = self._chat_config.get("auto_chat_value", 1.0)
                if callable(auto_chat_value):
                    return auto_chat_value(stream_id)
                else:
                    return float(auto_chat_value)
            else:
                # 回退到默认值
                return 1.0
        except Exception as e:
            logger.warning(f"获取auto_chat_value失败，使用默认值: {e}")
            return 1.0

    def __getattr__(self, name: str) -> Any:
        """获取其他属性"""
        if hasattr(self._chat_config, name):
            return getattr(self._chat_config, name)
        elif isinstance(self._chat_config, dict) and name in self._chat_config:
            return self._chat_config[name]
        else:
            # 为常见的聊天配置属性提供默认值
            default_values = {
                "max_context_size": 18,
                "talk_value": 1.0,
                "auto_chat_value": 1.0,
                "planner_smooth": 0,  # 修改默认值为0，确保最快反应
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


class UnifiedConfigWrapper:
    """统一配置包装器，提供一致的配置访问接口"""

    def __init__(self, config_data_or_tenant: Union[Dict[str, Any], Any, str], agent_id: Optional[str] = None):
        """
        初始化统一配置包装器

        Args:
            config_data_or_tenant: 配置数据（字典或配置对象），或者租户ID
            agent_id: 智能体ID（当第一个参数是租户ID时使用）
        """
        # 检查是否使用简化配置系统
        if SIMPLIFIED_CONFIG_AVAILABLE and isinstance(config_data_or_tenant, str) and agent_id:
            try:
                tenant_id = config_data_or_tenant
                logger.info(f"使用简化配置系统: tenant={tenant_id}, agent={agent_id}")
                self._config_data = get_simplified_unified_config(tenant_id, agent_id)
                self._chat_wrapper = None
                self._using_simplified = True
                return
            except Exception as e:
                logger.warning(f"简化配置系统初始化失败，回退到原有系统: {e}")

        # 原有的初始化逻辑
        self._config_data = config_data_or_tenant
        self._chat_wrapper = None
        self._using_simplified = False

    @property
    def chat(self) -> ChatConfigWrapper:
        """获取聊天配置包装器"""
        if self._chat_wrapper is None:
            if hasattr(self._config_data, "chat"):
                chat_config = self._config_data.chat
            elif isinstance(self._config_data, dict) and "chat" in self._config_data:
                chat_config = self._config_data["chat"]
            else:
                # 如果没有chat配置，创建空字典
                chat_config = {}

            self._chat_wrapper = ChatConfigWrapper(chat_config)

        return self._chat_wrapper

    def __getattr__(self, name: str) -> Any:
        """获取其他配置节"""
        if hasattr(self._config_data, name):
            attr_value = getattr(self._config_data, name)
            # 如果是复杂对象，包装它
            if hasattr(attr_value, "__dict__") or isinstance(attr_value, dict):
                return ConfigSectionWrapper(attr_value, name)
            return attr_value
        elif isinstance(self._config_data, dict) and name in self._config_data:
            attr_value = self._config_data[name]
            # 如果是复杂对象，包装它
            if isinstance(attr_value, dict):
                return ConfigSectionWrapper(attr_value, name)
            return attr_value
        else:
            # 为常见的配置节提供默认值
            default_sections = {
                "personality": {
                    "personality": "是一个女大学生，现在在读大二，会刷贴吧。",
                    "reply_style": "请回复的平淡一些，简短一些，说中文，不要刻意突出自身学科背景。可以参考贴吧，知乎和微博的回复风格。",
                    "interest": "对技术相关话题，游戏和动漫相关话题感兴趣，也对日常话题感兴趣，不喜欢太过沉重严肃的话题",
                },
                "bot": {"platform": "qq", "nickname": "小千", "alias_names": ["小千"]},
                "expression": {"mode": "classic", "learning_list": [["", "enable", "enable", "1.0"]]},
                "memory": {"max_memory_number": 100, "max_memory_size": 2048, "memory_build_frequency": 1},
                "mood": {
                    "enable_mood": False,
                    "mood_update_threshold": 1,
                    "emotion_style": "情绪较为稳定，但遭遇特定事件的时候起伏较大",
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
                "tool": {"enable_tool": False},
                "response_splitter": {"enable": False},
                "chinese_typo": {"enable": False},
            }
            if name in default_sections:
                logger.warning(f"配置缺少节 '{name}'，使用默认配置")
                return ConfigSectionWrapper(default_sections[name], name)
            else:
                raise AttributeError(f"'config' object has no attribute '{name}'")

    def __getitem__(self, key: str) -> Any:
        """支持字典式访问"""
        return self.__getattr__(key)
