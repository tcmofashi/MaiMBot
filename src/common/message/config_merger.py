"""
配置融合器
用于将Agent配置与基础默认配置融合，生成最终的global_config和model_config
"""

import copy
from typing import Dict, Any, Optional
from dataclasses import asdict

from .agent_config import AgentConfig
from src.common.logger import get_logger
from src.config.official_configs import (
    BotConfig,
    PersonalityConfig,
    ChatConfig,
    RelationshipConfig,
    ExpressionConfig,
    MemoryConfig,
    MoodConfig,
    EmojiConfig,
    ToolConfig,
    VoiceConfig,
    KeywordReactionConfig,
)


class ConfigMerger:
    """配置融合器"""

    def __init__(self):
        self.logger = get_logger("config_merger")
        self._base_global_config = None
        self._base_model_config = None

    def _load_base_configs(self) -> None:
        """加载基础配置"""
        try:
            from src.config.config import global_config

            # 获取当前全局配置作为基础配置
            self._base_global_config = global_config
            self.logger.info("基础配置加载成功")
        except Exception as e:
            self.logger.error(f"加载基础配置失败: {e}")
            raise

    def _merge_dict(self, base: Dict[str, Any], override: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """递归合并字典"""
        if not override:
            return base

        result = copy.deepcopy(base)
        for key, value in override.items():
            if value is not None:
                if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = self._merge_dict(result[key], value)
                else:
                    result[key] = value
        return result

    def _merge_config_object(self, base_config_obj: Any, overrides: Dict[str, Any]) -> Any:
        """合并配置对象"""
        if not overrides:
            return base_config_obj

        # 获取基础配置的字典表示
        base_dict = asdict(base_config_obj) if hasattr(base_config_obj, "__dict__") else {}

        # 合并覆盖项
        merged_dict = self._merge_dict(base_dict, overrides)

        # 创建新的配置对象
        config_class = type(base_config_obj)
        try:
            return config_class(**merged_dict)
        except TypeError as e:
            self.logger.warning(f"无法创建配置对象 {config_class.__name__}: {e}")
            # 如果创建失败，返回修改后的原对象
            for key, value in overrides.items():
                if value is not None and hasattr(base_config_obj, key):
                    setattr(base_config_obj, key, value)
            return base_config_obj

    def merge_bot_config(self, agent_config: AgentConfig) -> BotConfig:
        """融合Bot配置"""
        if not self._base_global_config:
            self._load_base_configs()

        base_bot_config = self._base_global_config.bot

        # 准备覆盖配置
        overrides = {}
        if agent_config.bot_overrides.platform:
            overrides["platform"] = agent_config.bot_overrides.platform
        if agent_config.bot_overrides.qq_account:
            overrides["qq_account"] = agent_config.bot_overrides.qq_account
        if agent_config.bot_overrides.nickname:
            overrides["nickname"] = agent_config.bot_overrides.nickname
        if agent_config.bot_overrides.platforms:
            overrides["platforms"] = agent_config.bot_overrides.platforms
        if agent_config.bot_overrides.alias_names:
            overrides["alias_names"] = agent_config.bot_overrides.alias_names

        return self._merge_config_object(base_bot_config, overrides)

    def merge_personality_config(self, agent_config: AgentConfig) -> PersonalityConfig:
        """融合人格配置"""
        if not self._base_global_config:
            self._load_base_configs()

        base_personality_config = self._base_global_config.personality

        # 优先使用Agent的persona配置
        overrides = {
            "personality": agent_config.persona.personality or base_personality_config.personality,
            "reply_style": agent_config.persona.reply_style or base_personality_config.reply_style,
            "interest": agent_config.persona.interest or base_personality_config.interest,
            "plan_style": agent_config.persona.plan_style or base_personality_config.plan_style,
            "private_plan_style": agent_config.persona.private_plan_style or base_personality_config.private_plan_style,
            "visual_style": agent_config.persona.visual_style or base_personality_config.visual_style,
            "states": agent_config.persona.states or base_personality_config.states,
            "state_probability": agent_config.persona.state_probability
            if agent_config.persona.state_probability > 0
            else base_personality_config.state_probability,
        }

        # 检查是否有额外的覆盖配置
        if agent_config.config_overrides.personality:
            personality_overrides = agent_config.config_overrides.personality
            if personality_overrides.personality:
                overrides["personality"] = personality_overrides.personality
            if personality_overrides.reply_style:
                overrides["reply_style"] = personality_overrides.reply_style
            if personality_overrides.interest:
                overrides["interest"] = personality_overrides.interest
            if personality_overrides.plan_style:
                overrides["plan_style"] = personality_overrides.plan_style
            if personality_overrides.private_plan_style:
                overrides["private_plan_style"] = personality_overrides.private_plan_style
            if personality_overrides.visual_style:
                overrides["visual_style"] = personality_overrides.visual_style
            if personality_overrides.states:
                overrides["states"] = personality_overrides.states
            if personality_overrides.state_probability is not None:
                overrides["state_probability"] = personality_overrides.state_probability

        return self._merge_config_object(base_personality_config, overrides)

    def merge_chat_config(self, agent_config: AgentConfig) -> ChatConfig:
        """融合聊天配置"""
        if not self._base_global_config:
            self._load_base_configs()

        base_chat_config = self._base_global_config.chat

        # 准备覆盖配置
        overrides = {}
        if agent_config.config_overrides.chat:
            chat_overrides = agent_config.config_overrides.chat
            if chat_overrides.max_context_size is not None:
                overrides["max_context_size"] = chat_overrides.max_context_size
            if chat_overrides.interest_rate_mode:
                overrides["interest_rate_mode"] = chat_overrides.interest_rate_mode
            if chat_overrides.planner_size is not None:
                overrides["planner_size"] = chat_overrides.planner_size
            if chat_overrides.mentioned_bot_reply is not None:
                overrides["mentioned_bot_reply"] = chat_overrides.mentioned_bot_reply
            if chat_overrides.auto_chat_value is not None:
                overrides["auto_chat_value"] = chat_overrides.auto_chat_value
            if chat_overrides.enable_auto_chat_value_rules is not None:
                overrides["enable_auto_chat_value_rules"] = chat_overrides.enable_auto_chat_value_rules
            if chat_overrides.at_bot_inevitable_reply is not None:
                overrides["at_bot_inevitable_reply"] = chat_overrides.at_bot_inevitable_reply
            if chat_overrides.planner_smooth is not None:
                overrides["planner_smooth"] = chat_overrides.planner_smooth
            if chat_overrides.talk_value is not None:
                overrides["talk_value"] = chat_overrides.talk_value
            if chat_overrides.enable_talk_value_rules is not None:
                overrides["enable_talk_value_rules"] = chat_overrides.enable_talk_value_rules
            if chat_overrides.talk_value_rules is not None:
                overrides["talk_value_rules"] = chat_overrides.talk_value_rules
            if chat_overrides.auto_chat_value_rules is not None:
                overrides["auto_chat_value_rules"] = chat_overrides.auto_chat_value_rules
            if chat_overrides.include_planner_reasoning is not None:
                overrides["include_planner_reasoning"] = chat_overrides.include_planner_reasoning

        return self._merge_config_object(base_chat_config, overrides)

    def merge_relationship_config(self, agent_config: AgentConfig) -> RelationshipConfig:
        """融合关系配置"""
        if not self._base_global_config:
            self._load_base_configs()

        base_relationship_config = self._base_global_config.relationship

        overrides = {}
        if agent_config.config_overrides.relationship:
            if agent_config.config_overrides.relationship.enable_relationship is not None:
                overrides["enable_relationship"] = agent_config.config_overrides.relationship.enable_relationship

        return self._merge_config_object(base_relationship_config, overrides)

    def merge_expression_config(self, agent_config: AgentConfig) -> ExpressionConfig:
        """融合表达配置"""
        if not self._base_global_config:
            self._load_base_configs()

        base_expression_config = self._base_global_config.expression

        overrides = {}
        if agent_config.config_overrides.expression:
            expression_overrides = agent_config.config_overrides.expression
            if expression_overrides.mode:
                overrides["mode"] = expression_overrides.mode
            if expression_overrides.learning_list:
                overrides["learning_list"] = expression_overrides.learning_list
            if expression_overrides.expression_groups:
                overrides["expression_groups"] = expression_overrides.expression_groups

        return self._merge_config_object(base_expression_config, overrides)

    def merge_memory_config(self, agent_config: AgentConfig) -> MemoryConfig:
        """融合记忆配置"""
        if not self._base_global_config:
            self._load_base_configs()

        base_memory_config = self._base_global_config.memory

        overrides = {}
        if agent_config.config_overrides.memory:
            memory_overrides = agent_config.config_overrides.memory
            if memory_overrides.max_memory_number is not None:
                overrides["max_memory_number"] = memory_overrides.max_memory_number
            if memory_overrides.memory_build_frequency is not None:
                overrides["memory_build_frequency"] = memory_overrides.memory_build_frequency

        return self._merge_config_object(base_memory_config, overrides)

    def merge_mood_config(self, agent_config: AgentConfig) -> MoodConfig:
        """融合情绪配置"""
        if not self._base_global_config:
            self._load_base_configs()

        base_mood_config = self._base_global_config.mood

        overrides = {}
        if agent_config.config_overrides.mood:
            mood_overrides = agent_config.config_overrides.mood
            if mood_overrides.enable_mood is not None:
                overrides["enable_mood"] = mood_overrides.enable_mood
            if mood_overrides.mood_update_threshold is not None:
                overrides["mood_update_threshold"] = mood_overrides.mood_update_threshold
            if mood_overrides.emotion_style:
                overrides["emotion_style"] = mood_overrides.emotion_style

        return self._merge_config_object(base_mood_config, overrides)

    def merge_emoji_config(self, agent_config: AgentConfig) -> EmojiConfig:
        """融合表情包配置"""
        if not self._base_global_config:
            self._load_base_configs()

        base_emoji_config = self._base_global_config.emoji

        overrides = {}
        if agent_config.config_overrides.emoji:
            emoji_overrides = agent_config.config_overrides.emoji
            if emoji_overrides.emoji_chance is not None:
                overrides["emoji_chance"] = emoji_overrides.emoji_chance
            if emoji_overrides.max_reg_num is not None:
                overrides["max_reg_num"] = emoji_overrides.max_reg_num
            if emoji_overrides.do_replace is not None:
                overrides["do_replace"] = emoji_overrides.do_replace
            if emoji_overrides.check_interval is not None:
                overrides["check_interval"] = emoji_overrides.check_interval
            if emoji_overrides.steal_emoji is not None:
                overrides["steal_emoji"] = emoji_overrides.steal_emoji
            if emoji_overrides.content_filtration is not None:
                overrides["content_filtration"] = emoji_overrides.content_filtration
            if emoji_overrides.filtration_prompt:
                overrides["filtration_prompt"] = emoji_overrides.filtration_prompt

        return self._merge_config_object(base_emoji_config, overrides)

    def merge_tool_config(self, agent_config: AgentConfig) -> ToolConfig:
        """融合工具配置"""
        if not self._base_global_config:
            self._load_base_configs()

        base_tool_config = self._base_global_config.tool

        overrides = {}
        if agent_config.config_overrides.tool:
            tool_overrides = agent_config.config_overrides.tool
            if tool_overrides.enable_tool is not None:
                overrides["enable_tool"] = tool_overrides.enable_tool
            if tool_overrides.tool_cache_ttl is not None:
                overrides["tool_cache_ttl"] = tool_overrides.tool_cache_ttl
            if tool_overrides.max_tool_execution_time is not None:
                overrides["max_tool_execution_time"] = tool_overrides.max_tool_execution_time
            if tool_overrides.enable_tool_parallel is not None:
                overrides["enable_tool_parallel"] = tool_overrides.enable_tool_parallel

        return self._merge_config_object(base_tool_config, overrides)

    def merge_voice_config(self, agent_config: AgentConfig) -> VoiceConfig:
        """融合语音配置"""
        if not self._base_global_config:
            self._load_base_configs()

        base_voice_config = self._base_global_config.voice

        overrides = {}
        if agent_config.config_overrides.voice:
            if agent_config.config_overrides.voice.enable_asr is not None:
                overrides["enable_asr"] = agent_config.config_overrides.voice.enable_asr

        return self._merge_config_object(base_voice_config, overrides)

    # Plugin配置暂时不支持，因为MaiMBot中没有对应的PluginConfig类
    # def merge_plugin_config(self, agent_config: AgentConfig) -> Optional[Any]:
    #     """融合插件配置"""
    #     if not self._base_global_config:
    #         self._load_base_configs()
    #
    #     # 暂时返回None，跳过插件配置
    #     return None

    def merge_keyword_reaction_config(self, agent_config: AgentConfig) -> KeywordReactionConfig:
        """融合关键词反应配置"""
        if not self._base_global_config:
            self._load_base_configs()

        base_keyword_config = self._base_global_config.keyword_reaction

        overrides = {}
        if agent_config.config_overrides.keyword_reaction:
            keyword_overrides = agent_config.config_overrides.keyword_reaction
            if keyword_overrides.keyword_rules:
                overrides["keyword_rules"] = keyword_overrides.keyword_rules
            if keyword_overrides.regex_rules:
                overrides["regex_rules"] = keyword_overrides.regex_rules

        return self._merge_config_object(base_keyword_config, overrides)

    def create_merged_config(self, agent_config: AgentConfig) -> Dict[str, Any]:
        """创建完整的融合配置"""
        if not self._base_global_config:
            self._load_base_configs()

        try:
            merged_config = {
                "bot": self.merge_bot_config(agent_config),
                "personality": self.merge_personality_config(agent_config),
                "chat": self.merge_chat_config(agent_config),
                "relationship": self.merge_relationship_config(agent_config),
                "expression": self.merge_expression_config(agent_config),
                "memory": self.merge_memory_config(agent_config),
                "mood": self.merge_mood_config(agent_config),
                "emoji": self.merge_emoji_config(agent_config),
                "tool": self.merge_tool_config(agent_config),
                "voice": self.merge_voice_config(agent_config),
                # "plugin": self.merge_plugin_config(agent_config),  # 暂时跳过插件配置
                "keyword_reaction": self.merge_keyword_reaction_config(agent_config),
            }

            # 复制其他不需要修改的配置
            base_config_dict = asdict(self._base_global_config)
            for key, value in base_config_dict.items():
                if key not in merged_config:
                    merged_config[key] = value

            self.logger.info(f"Agent {agent_config.agent_id} 配置融合完成")
            return merged_config

        except Exception as e:
            self.logger.error(f"配置融合失败: {e}")
            raise


# 全局配置融合器实例
_config_merger = None


def get_config_merger() -> ConfigMerger:
    """获取配置融合器实例"""
    global _config_merger
    if _config_merger is None:
        _config_merger = ConfigMerger()
    return _config_merger


def create_agent_config(agent_config: AgentConfig) -> Dict[str, Any]:
    """创建Agent配置的便捷函数"""
    merger = get_config_merger()
    return merger.create_merged_config(agent_config)


async def create_agent_global_config(agent_id: str) -> Optional[Any]:
    """
    获取Agent专用的global_config

    Args:
        agent_id: Agent ID

    Returns:
        Agent专用的global_config对象或None
    """
    from .agent_config_loader import load_agent_config

    # 加载Agent配置
    agent_config = await load_agent_config(agent_id)
    if not agent_config:
        return None

    # 创建融合配置
    merger = get_config_merger()
    merged_dict = merger.create_merged_config(agent_config)
    if not merged_dict:
        return None

    # 重建global_config对象
    try:
        from src.config.config import GlobalConfig

        # 从基础配置获取不需要修改的部分
        if not merger._base_global_config:
            merger._load_base_configs()

        base_dict = asdict(merger._base_global_config)

        # 用融合后的配置替换对应部分
        for key, value in merged_dict.items():
            if key in base_dict:
                base_dict[key] = value

        # 创建新的GlobalConfig对象
        return GlobalConfig(**base_dict)

    except Exception as e:
        merger.logger.error(f"创建global_config失败: {e}")
        return merged_dict  # 返回字典形式作为降级


async def create_agent_model_config(agent_id: str) -> Optional[Any]:
    """
    获取Agent专用的model_config

    Args:
        agent_id: Agent ID

    Returns:
        Agent专用的model_config对象或None
    """
    from .agent_config_loader import load_agent_config

    # 加载Agent配置
    agent_config = await load_agent_config(agent_id)
    if not agent_config:
        return None

    try:
        # 尝试加载模型配置
        from src.config.config import model_config

        # 如果有Agent特定的模型配置覆盖，在这里处理
        # 目前直接返回基础模型配置
        # 未来可以从Agent配置中读取模型相关设置

        return model_config

    except Exception as e:
        merger = get_config_merger()
        merger.logger.error(f"获取model_config失败: {e}")
        return None
