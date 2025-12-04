"""
数据库Agent配置加载器
从maim_db数据库中加载结构化的Agent配置并与基础配置融合
"""

from typing import Dict, Any, Optional, List

from .agent_config import AgentConfig, PersonalityConfig, BotOverrides, ConfigOverrides
from src.common.logger import get_logger

try:
    from maim_db.src.core.models.agent_config import (
        PersonalityConfig as DBPersonalityConfig,
        BotConfigOverrides as DBBotConfigOverrides,
        ChatConfigOverrides as DBChatConfigOverrides,
        ExpressionConfigOverrides as DBExpressionConfigOverrides,
        MemoryConfigOverrides as DBMemoryConfigOverrides,
        MoodConfigOverrides as DBMoodConfigOverrides,
        EmojiConfigOverrides as DBEmojiConfigOverrides,
        ToolConfigOverrides as DBToolConfigOverrides,
        VoiceConfigOverrides as DBVoiceConfigOverrides,
        PluginConfigOverrides as DBPluginConfigOverrides,
        KeywordReactionConfigOverrides as DBKeywordReactionConfigOverrides,
        RelationshipConfigOverrides as DBRelationshipConfigOverrides,
        parse_json_field,
    )

    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False
    DBPersonalityConfig = None
    DBBotConfigOverrides = None
    DBChatConfigOverrides = None
    DBExpressionConfigOverrides = None
    DBMemoryConfigOverrides = None
    DBMoodConfigOverrides = None
    DBEmojiConfigOverrides = None
    DBToolConfigOverrides = None
    DBVoiceConfigOverrides = None
    DBPluginConfigOverrides = None
    DBKeywordReactionConfigOverrides = None
    DBRelationshipConfigOverrides = None


class DatabaseAgentConfigLoader:
    """数据库Agent配置加载器"""

    def __init__(self):
        self.logger = get_logger("db_agent_config_loader")
        if not DATABASE_AVAILABLE:
            self.logger.warning("maim_db数据库模块不可用，数据库加载器将被禁用")

    def is_available(self) -> bool:
        """检查数据库模块是否可用"""
        return DATABASE_AVAILABLE

    def _convert_db_personality_to_agent_config(self, db_config: DBPersonalityConfig) -> PersonalityConfig:
        """转换数据库人格配置到Agent人格配置"""
        return PersonalityConfig(
            personality=db_config.personality,
            reply_style=db_config.reply_style or "",
            interest=db_config.interest or "",
            plan_style=db_config.plan_style or "",
            private_plan_style=db_config.private_plan_style or "",
            visual_style=db_config.visual_style or "",
            states=parse_json_field(db_config.states, []),
            state_probability=db_config.state_probability,
        )

    def _convert_db_bot_overrides_to_agent_config(self, db_config: DBBotConfigOverrides) -> BotOverrides:
        """转换数据库Bot配置覆盖到Agent Bot配置覆盖"""
        return BotOverrides(
            platform=db_config.platform or None,
            qq_account=db_config.qq_account or None,
            nickname=db_config.nickname or None,
            platforms=parse_json_field(db_config.platforms, []),
            alias_names=parse_json_field(db_config.alias_names, []),
        )

    def _convert_db_chat_overrides_to_agent_config(self, db_config: DBChatConfigOverrides):
        """转换数据库聊天配置覆盖到Agent配置覆盖"""
        from .agent_config import ChatConfigOverrides

        return ChatConfigOverrides(
            max_context_size=db_config.max_context_size,
            interest_rate_mode=db_config.interest_rate_mode,
            planner_size=db_config.planner_size,
            mentioned_bot_reply=db_config.mentioned_bot_reply,
            auto_chat_value=db_config.auto_chat_value,
            enable_auto_chat_value_rules=db_config.enable_auto_chat_value_rules,
            at_bot_inevitable_reply=db_config.at_bot_inevitable_reply,
            planner_smooth=db_config.planner_smooth,
            talk_value=db_config.talk_value,
            enable_talk_value_rules=db_config.enable_talk_value_rules,
            talk_value_rules=parse_json_field(db_config.talk_value_rules, []),
            auto_chat_value_rules=parse_json_field(db_config.auto_chat_value_rules, []),
        )

    def _convert_db_expression_overrides_to_agent_config(self, db_config: DBExpressionConfigOverrides):
        """转换数据库表达配置覆盖到Agent配置覆盖"""
        from .agent_config import ExpressionConfigOverrides

        return ExpressionConfigOverrides(
            mode=db_config.mode,
            learning_list=parse_json_field(db_config.learning_list, []),
            expression_groups=parse_json_field(db_config.expression_groups, []),
        )

    def _convert_db_memory_overrides_to_agent_config(self, db_config: DBMemoryConfigOverrides):
        """转换数据库记忆配置覆盖到Agent配置覆盖"""
        from .agent_config import MemoryConfigOverrides

        return MemoryConfigOverrides(
            max_memory_number=db_config.max_memory_number, memory_build_frequency=db_config.memory_build_frequency
        )

    def _convert_db_mood_overrides_to_agent_config(self, db_config: DBMoodConfigOverrides):
        """转换数据库情绪配置覆盖到Agent配置覆盖"""
        from .agent_config import MoodConfigOverrides

        return MoodConfigOverrides(
            enable_mood=db_config.enable_mood,
            mood_update_threshold=db_config.mood_update_threshold,
            emotion_style=db_config.emotion_style or "",
        )

    def _convert_db_emoji_overrides_to_agent_config(self, db_config: DBEmojiConfigOverrides):
        """转换数据库表情包配置覆盖到Agent配置覆盖"""
        from .agent_config import EmojiConfigOverrides

        return EmojiConfigOverrides(
            emoji_chance=db_config.emoji_chance,
            max_reg_num=db_config.max_reg_num,
            do_replace=db_config.do_replace,
            check_interval=db_config.check_interval,
            steal_emoji=db_config.steal_emoji,
            content_filtration=db_config.content_filtration,
            filtration_prompt=db_config.filtration_prompt or "",
        )

    def _convert_db_tool_overrides_to_agent_config(self, db_config: DBToolConfigOverrides):
        """转换数据库工具配置覆盖到Agent配置覆盖"""
        from .agent_config import ToolConfigOverrides

        return ToolConfigOverrides(enable_tool=db_config.enable_tool)

    def _convert_db_voice_overrides_to_agent_config(self, db_config: DBVoiceConfigOverrides):
        """转换数据库语音配置覆盖到Agent配置覆盖"""
        from .agent_config import VoiceConfigOverrides

        return VoiceConfigOverrides(enable_asr=db_config.enable_asr)

    def _convert_db_plugin_overrides_to_agent_config(self, db_config: DBPluginConfigOverrides):
        """转换数据库插件配置覆盖到Agent配置覆盖"""
        from .agent_config import PluginConfigOverrides

        return PluginConfigOverrides(
            enable_plugins=db_config.enable_plugins,
            tenant_mode_disable_plugins=db_config.tenant_mode_disable_plugins,
            allowed_plugins=parse_json_field(db_config.allowed_plugins, []),
            blocked_plugins=parse_json_field(db_config.blocked_plugins, []),
        )

    def _convert_db_keyword_overrides_to_agent_config(self, db_config: DBKeywordReactionConfigOverrides):
        """转换数据库关键词反应配置覆盖到Agent配置覆盖"""
        from .agent_config import KeywordReactionConfigOverrides

        return KeywordReactionConfigOverrides(
            keyword_rules=parse_json_field(db_config.keyword_rules, []),
            regex_rules=parse_json_field(db_config.regex_rules, []),
        )

    def _convert_db_relationship_overrides_to_agent_config(self, db_config: DBRelationshipConfigOverrides):
        """转换数据库关系配置覆盖到Agent配置覆盖"""
        from .agent_config import RelationshipConfigOverrides

        return RelationshipConfigOverrides(enable_relationship=db_config.enable_relationship)

    def _convert_db_personality_overrides_to_agent_config(self, db_config: DBPersonalityConfig):
        """转换数据库人格配置覆盖到Agent配置覆盖"""
        from .agent_config import PersonalityConfigOverrides

        return PersonalityConfigOverrides(
            personality=db_config.personality,
            reply_style=db_config.reply_style,
            interest=db_config.interest,
            plan_style=db_config.plan_style,
            private_plan_style=db_config.private_plan_style,
            visual_style=db_config.visual_style,
            states=parse_json_field(db_config.states, []),
            state_probability=db_config.state_probability,
        )

    async def load_agent_config_from_database(self, agent_id: str) -> Optional[AgentConfig]:
        """从数据库加载Agent配置"""
        if not self.is_available():
            self.logger.error("数据库模块不可用，无法加载Agent配置")
            return None

        try:
            # 加载基础Agent信息（需要根据实际的Agent表结构调整）
            # 这里假设有Agent表，如果没有，需要从其他地方获取
            agent_name = f"Agent_{agent_id}"
            agent_description = ""
            agent_tags = []

            # 加载人格配置
            personality_config = None
            try:
                db_personality = DBPersonalityConfig.get_or_none(DBPersonalityConfig.agent_id == agent_id)
                if db_personality:
                    personality_config = self._convert_db_personality_to_agent_config(db_personality)
            except Exception as e:
                self.logger.error(f"加载人格配置失败: {e}")
                personality_config = PersonalityConfig(personality="")

            # 加载Bot配置覆盖
            bot_overrides = BotOverrides()
            try:
                db_bot_config = DBBotConfigOverrides.get_or_none(DBBotConfigOverrides.agent_id == agent_id)
                if db_bot_config:
                    bot_overrides = self._convert_db_bot_overrides_to_agent_config(db_bot_config)
            except Exception as e:
                self.logger.error(f"加载Bot配置覆盖失败: {e}")

            # 加载各种配置覆盖
            chat_overrides = None
            expression_overrides = None
            memory_overrides = None
            mood_overrides = None
            emoji_overrides = None
            tool_overrides = None
            voice_overrides = None
            plugin_overrides = None
            keyword_overrides = None
            relationship_overrides = None
            personality_overrides = None

            try:
                db_chat_config = DBChatConfigOverrides.get_or_none(DBChatConfigOverrides.agent_id == agent_id)
                if db_chat_config:
                    chat_overrides = self._convert_db_chat_overrides_to_agent_config(db_chat_config)

                db_expression_config = DBExpressionConfigOverrides.get_or_none(
                    DBExpressionConfigOverrides.agent_id == agent_id
                )
                if db_expression_config:
                    expression_overrides = self._convert_db_expression_overrides_to_agent_config(db_expression_config)

                db_memory_config = DBMemoryConfigOverrides.get_or_none(DBMemoryConfigOverrides.agent_id == agent_id)
                if db_memory_config:
                    memory_overrides = self._convert_db_memory_overrides_to_agent_config(db_memory_config)

                db_mood_config = DBMoodConfigOverrides.get_or_none(DBMoodConfigOverrides.agent_id == agent_id)
                if db_mood_config:
                    mood_overrides = self._convert_db_mood_overrides_to_agent_config(db_mood_config)

                db_emoji_config = DBEmojiConfigOverrides.get_or_none(DBEmojiConfigOverrides.agent_id == agent_id)
                if db_emoji_config:
                    emoji_overrides = self._convert_db_emoji_overrides_to_agent_config(db_emoji_config)

                db_tool_config = DBToolConfigOverrides.get_or_none(DBToolConfigOverrides.agent_id == agent_id)
                if db_tool_config:
                    tool_overrides = self._convert_db_tool_overrides_to_agent_config(db_tool_config)

                db_voice_config = DBVoiceConfigOverrides.get_or_none(DBVoiceConfigOverrides.agent_id == agent_id)
                if db_voice_config:
                    voice_overrides = self._convert_db_voice_overrides_to_agent_config(db_voice_config)

                db_plugin_config = DBPluginConfigOverrides.get_or_none(DBPluginConfigOverrides.agent_id == agent_id)
                if db_plugin_config:
                    plugin_overrides = self._convert_db_plugin_overrides_to_agent_config(db_plugin_config)

                db_keyword_config = DBKeywordReactionConfigOverrides.get_or_none(
                    DBKeywordReactionConfigOverrides.agent_id == agent_id
                )
                if db_keyword_config:
                    keyword_overrides = self._convert_db_keyword_overrides_to_agent_config(db_keyword_config)

                db_relationship_config = DBRelationshipConfigOverrides.get_or_none(
                    DBRelationshipConfigOverrides.agent_id == agent_id
                )
                if db_relationship_config:
                    relationship_overrides = self._convert_db_relationship_overrides_to_agent_config(
                        db_relationship_config
                    )

                # 人格覆盖与基础人格配置相同
                personality_overrides = personality_overrides

            except Exception as e:
                self.logger.error(f"加载配置覆盖失败: {e}")

            # 创建配置覆盖对象
            config_overrides = ConfigOverrides(
                chat=chat_overrides,
                expression=expression_overrides,
                memory=memory_overrides,
                mood=mood_overrides,
                emoji=emoji_overrides,
                tool=tool_overrides,
                voice=voice_overrides,
                plugin=plugin_overrides,
                keyword_reaction=keyword_overrides,
                relationship=relationship_overrides,
                personality=personality_overrides,
            )

            # 创建AgentConfig对象
            agent_config = AgentConfig(
                agent_id=agent_id,
                name=agent_name,
                description=agent_description,
                tags=agent_tags,
                persona=personality_config,
                bot_overrides=bot_overrides,
                config_overrides=config_overrides,
            )

            self.logger.info(f"成功从数据库加载Agent配置: {agent_id}")
            return agent_config

        except Exception as e:
            self.logger.error(f"从数据库加载Agent配置失败: {e}")
            return None

    async def create_merged_config_from_database(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """从数据库创建融合后的全局配置"""
        agent_config = await self.load_agent_config_from_database(agent_id)
        if not agent_config:
            self.logger.error(f"无法从数据库加载Agent配置: {agent_id}")
            return None

        try:
            # 创建融合配置
            from .config_merger import create_agent_config

            merged_config = create_agent_config(agent_config)
            self.logger.info(f"成功从数据库创建Agent {agent_id} 的融合配置")
            return merged_config

        except Exception as e:
            self.logger.error(f"从数据库创建融合配置失败: {e}")
            return None

    async def get_available_agents_from_database(self) -> List[str]:
        """从数据库获取可用的Agent ID列表"""
        if not self.is_available():
            self.logger.error("数据库模块不可用")
            return []

        try:
            # 从人格配置表中获取所有agent_id
            agent_ids = list(DBPersonalityConfig.select(DBPersonalityConfig.agent_id).distinct().scalars())
            self.logger.info(f"从数据库获取到 {len(agent_ids)} 个Agent")
            return agent_ids

        except Exception as e:
            self.logger.error(f"从数据库获取Agent列表失败: {e}")
            return []

    async def save_agent_config_to_database(self, agent_config: AgentConfig) -> bool:
        """将Agent配置保存到数据库"""
        if not self.is_available():
            self.logger.error("数据库模块不可用，无法保存Agent配置")
            return False

        try:
            # 这里需要实现将AgentConfig对象保存到数据库的逻辑
            # 由于涉及多个表，需要使用事务来保证一致性
            self.logger.info(f"保存Agent配置到数据库: {agent_config.agent_id}")
            # TODO: 实现保存逻辑
            return True

        except Exception as e:
            self.logger.error(f"保存Agent配置到数据库失败: {e}")
            return False


# 全局数据库Agent配置加载器实例
_db_agent_config_loader = None


def get_db_agent_config_loader() -> DatabaseAgentConfigLoader:
    """获取数据库Agent配置加载器实例"""
    global _db_agent_config_loader
    if _db_agent_config_loader is None:
        _db_agent_config_loader = DatabaseAgentConfigLoader()
    return _db_agent_config_loader


# 便捷函数
async def load_agent_config_from_database(agent_id: str) -> Optional[AgentConfig]:
    """从数据库加载Agent配置的便捷函数"""
    loader = get_db_agent_config_loader()
    return await loader.load_agent_config_from_database(agent_id)


async def create_merged_config_from_database(agent_id: str) -> Optional[Dict[str, Any]]:
    """从数据库创建融合Agent配置的便捷函数"""
    loader = get_db_agent_config_loader()
    return await loader.create_merged_config_from_database(agent_id)


async def get_available_agents_from_database() -> List[str]:
    """从数据库获取可用Agent列表的便捷函数"""
    loader = get_db_agent_config_loader()
    return await loader.get_available_agents_from_database()
