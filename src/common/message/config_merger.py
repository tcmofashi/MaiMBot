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
            from src.config.config import base_global_config

            # 使用预先保存的、包含环境变量但无代理逻辑的基础配置副本
            self._base_global_config = base_global_config
            self.logger.info("基础配置加载成功")
        except Exception as e:
            self.logger.error(f"加载基础配置失败: {e}")
            raise

    def _deep_copy_sanitize(self, obj: Any) -> Any:
        """
        深拷贝并转换配置对象为标准Python类型
        主要用于处理 tomlkit 的 InlineTable 等特殊类型在 deepcopy 时的问题
        """
        from collections.abc import Mapping, Sequence
        
        # 基础类型直接返回
        if isinstance(obj, (str, int, float, bool, type(None))):
            return obj
            
        # 映射类型转换为标准字典
        # 增加对 hasattr("items") 的检查，以覆盖不继承 Mapping 但表现像 dict 的类型
        if isinstance(obj, Mapping) or hasattr(obj, "items"):
            try:
                return {k: self._deep_copy_sanitize(v) for k, v in obj.items()}
            except Exception:
                # 如果 items() 失败，尝试 fallback
                pass
            
        # 序列类型转换为标准列表 (注意排除字符串，已在上面处理)
        if isinstance(obj, Sequence):
            return [self._deep_copy_sanitize(v) for v in obj]
            
        # 其他类型尝试深拷贝
        try:
            return copy.deepcopy(obj)
        except Exception as e:
            # 如果深拷贝失败，记录日志并返回 str(obj) 或原对象，防止崩溃
            # 针对 InlineTable 错误，尝试转换
            if "InlineTable" in str(type(obj)) or "InlineTable" in str(e):
               self.logger.warning(f"Encountered InlineTable deepcopy error for {obj}, converting to dict forcefully")
               try:
                   return dict(obj)
               except:
                   pass
            
            self.logger.warning(f"Deepcopy failed for type {type(obj)}: {e}")
            return obj # 返回原对象，虽然可能不安全但比崩溃好


    def _merge_dict(self, base: Dict[str, Any], override: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """递归合并字典"""
        if not override:
            return self._deep_copy_sanitize(base)

        result = self._deep_copy_sanitize(base)
        for key, value in override.items():
            if isinstance(value, dict) and key in result and isinstance(result[key], dict):
                result[key] = self._merge_dict(result[key], value)
            else:
                result[key] = self._deep_copy_sanitize(value)
        return result

    def _sanitize_recursive_copy(self, obj: Any, seen: set = None) -> Any:
        """
        递归复制并净化对象。
        对于 Dataclass，创建新实例（DeepCopy）并净化字段。
        对于 列表/字典，创建新容器并净化元素。
        对于 tomlkit 类型，转换为标准 Python 类型。
        """
        import dataclasses
        if seen is None:
            seen = set()

        # 避免循环引用
        if id(obj) in seen:
            return obj
        seen.add(id(obj))

        if dataclasses.is_dataclass(obj):
            init_kwargs = {}
            non_init_fields = {}
            
            for f in dataclasses.fields(obj):
                if hasattr(obj, f.name):
                    val = getattr(obj, f.name)
                    clean_val = self._sanitize_recursive_copy(val, seen)
                    if f.init:
                        init_kwargs[f.name] = clean_val
                    else:
                        non_init_fields[f.name] = clean_val
            
            # 尝试重建对象
            try:
                new_obj = obj.__class__(**init_kwargs)
                # 设置 init=False 的字段 (如 MMC_VERSION)
                for k, v in non_init_fields.items():
                    setattr(new_obj, k, v)
                return new_obj
            except Exception as e:
                self.logger.warning(f"Recreating dataclass {type(obj)} failed: {e}, falling back to dict")
                # 合并所有字段作为降级字典
                return {**init_kwargs, **non_init_fields}
        
        if isinstance(obj, list):
            return [self._sanitize_recursive_copy(item, seen) for item in obj]
        
        if isinstance(obj, dict):
            return {k: self._sanitize_recursive_copy(v) for k, v in obj.items()}
            
        return self._deep_copy_sanitize(obj)

    def _apply_overrides_recursive(self, obj: Any, overrides: Dict[str, Any]) -> Any:
        """
        递归应用覆盖配置到对象上，保留原对象结构（不转换为字典）。
        支持 Dataclass 递归覆盖。
        """
        import dataclasses
        from collections.abc import Mapping
        
        if dataclasses.is_dataclass(obj):
            for key, value in overrides.items():
                if not hasattr(obj, key):
                    continue
                
                current_val = getattr(obj, key)
                
                # 情况1：子字段也是 Dataclass，且覆盖值是映射 -> 递归
                if isinstance(value, Mapping) and dataclasses.is_dataclass(current_val):
                    # 递归修改子对象 (current_val 已经是深拷贝的一部分，可以直接修改)
                    self._apply_overrides_recursive(current_val, value)
                
                # 情况2：当前值是字典，覆盖值也是映射 -> 字典合并
                elif isinstance(current_val, dict) and isinstance(value, Mapping):
                    # 先净化覆盖值
                    clean_val = self._deep_copy_sanitize(value)
                    # 合并字典
                    new_dict = self._merge_dict(current_val, clean_val)
                    setattr(obj, key, new_dict)
                    
                # 情况3：其他情况 (列表替换、基本类型替换) -> 直接替换
                else:
                    setattr(obj, key, self._deep_copy_sanitize(value))
            return obj
            
        elif isinstance(obj, dict):
            return self._merge_dict(obj, overrides)
        else:
            return self._deep_copy_sanitize(overrides)

    def _merge_config_object(self, base_config_obj: Any, overrides: Dict[str, Any]) -> Any:
        """
        合并单个配置对象（如 ChatConfig）
        """
        # 1. 获取基础配置的纯净深拷贝（保留对象结构）
        # 如果没有基础配置，返回空对象? 不，_sanitize_recursive_copy 处理 None
        clean_base = self._sanitize_recursive_copy(base_config_obj)
        
        if not overrides:
            return clean_base if clean_base else {}

        # 2. 如果基础配置是 None，无法应用 object-level overrides，
        # 只能尝试根据 overrides 创建对象? 
        # 但我们不知道类。所以如果 base 是 None，只能返回 overrides (字典)
        if clean_base is None:
            return self._deep_copy_sanitize(overrides)

        # 3. 递归应用覆盖
        return self._apply_overrides_recursive(clean_base, overrides)





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
        if not base_personality_config:
            self.logger.warning("基础配置中缺失 personality 配置，将使用默认空配置")
            from src.config.official_configs import PersonalityConfig as DefaultPersonalityConfig
            base_personality_config = DefaultPersonalityConfig(personality="")

        # 确保 agent_config.persona 存在
        agent_persona = agent_config.persona
        if not agent_persona:
             # 如果缺失，使用默认空配置
             from src.config.official_configs import PersonalityConfig as DefaultPersonalityConfig
             agent_persona = DefaultPersonalityConfig(personality="")
        
        # 优先使用Agent的persona配置
        overrides = {
            "personality": agent_persona.personality or base_personality_config.personality,
            "reply_style": agent_persona.reply_style or base_personality_config.reply_style,
            "interest": agent_persona.interest or base_personality_config.interest,
            "plan_style": agent_persona.plan_style or base_personality_config.plan_style,
            "private_plan_style": agent_persona.private_plan_style or base_personality_config.private_plan_style,
            "visual_style": agent_persona.visual_style or base_personality_config.visual_style,
            "states": agent_persona.states or base_personality_config.states,
            "state_probability": agent_persona.state_probability
            if agent_persona.state_probability > 0
            else base_personality_config.state_probability,
        }

        # 检查是否有额外的覆盖配置
        if agent_config.config_overrides and agent_config.config_overrides.personality:
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
            merged_config = {}
            
            try:
                merged_config["bot"] = self.merge_bot_config(agent_config)
            except Exception as e:
                self.logger.error(f"merge_bot_config 失败: {e}")
                raise

            try:
                merged_config["personality"] = self.merge_personality_config(agent_config)
            except Exception as e:
                self.logger.error(f"merge_personality_config 失败: {e}")
                raise

            try:
                merged_config["chat"] = self.merge_chat_config(agent_config)
            except Exception as e:
                self.logger.error(f"merge_chat_config 失败: {e}")
                raise

            try:
                merged_config["relationship"] = self.merge_relationship_config(agent_config)
            except Exception as e:
                self.logger.error(f"merge_relationship_config 失败: {e}")
                raise
            
            try:
                merged_config["expression"] = self.merge_expression_config(agent_config)
            except Exception as e:
                self.logger.error(f"merge_expression_config 失败: {e}")
                raise
            
            try:
                merged_config["memory"] = self.merge_memory_config(agent_config)
            except Exception as e:
                self.logger.error(f"merge_memory_config 失败: {e}")
                raise

            try:
                merged_config["mood"] = self.merge_mood_config(agent_config)
            except Exception as e:
                self.logger.error(f"merge_mood_config 失败: {e}")
                raise

            try:
                merged_config["emoji"] = self.merge_emoji_config(agent_config)
            except Exception as e:
                self.logger.error(f"merge_emoji_config 失败: {e}")
                raise

            try:
                merged_config["tool"] = self.merge_tool_config(agent_config)
            except Exception as e:
                self.logger.error(f"merge_tool_config 失败: {e}")
                raise

            try:
                merged_config["voice"] = self.merge_voice_config(agent_config)
            except Exception as e:
                self.logger.error(f"merge_voice_config 失败: {e}")
                raise

            # "plugin": self.merge_plugin_config(agent_config),  # 暂时跳过插件配置
            
            try:
                merged_config["keyword_reaction"] = self.merge_keyword_reaction_config(agent_config)
            except Exception as e:
                self.logger.error(f"merge_keyword_reaction_config 失败: {e}")
                raise

            # 复制其他不需要修改的配置
            # 务必进行 sanitization，防止 tomlkit 对象泄露
            # 使用 _sanitize_recursive_copy 替代 _conf_obj_to_dict，获取干净的对象实例
            import dataclasses
            base_config_obj = self._sanitize_recursive_copy(self._base_global_config)
            
            # 将未修改的字段（已净化为对象）复制到 merged_config
            if dataclasses.is_dataclass(base_config_obj):
                for f in dataclasses.fields(base_config_obj):
                    # 跳过 init=False 的字段（如 MMC_VERSION），否则会导致 GlobalConfig 初始化失败
                    if not f.init:
                        continue
                        
                    if f.name not in merged_config:
                        merged_config[f.name] = getattr(base_config_obj, f.name)
            else:
                # Fallback if base_config_obj is for some reason a dict (unlikely)
                base_dict = base_config_obj if isinstance(base_config_obj, dict) else {}
                for key, value in base_dict.items():
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

        # merged_dict 现在包含了完整配置的所有字段，并且值都是干净的对象实例
        # 直接使用它来创建 GlobalConfig
        return GlobalConfig(**merged_dict)

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
        from src.config.config import base_model_config

        # 如果有Agent特定的模型配置覆盖，在这里处理
        # 目前直接返回基础模型配置
        # 未来可以从Agent配置中读取模型相关设置

        # 使用预先保存的基础配置副本
        return base_model_config

    except Exception as e:
        merger = get_config_merger()
        merger.logger.error(f"获取model_config失败: {e}")
        return None
