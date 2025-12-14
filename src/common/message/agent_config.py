"""
Agent配置数据类
用于从MaimConfig数据库读取JSON配置并反序列化
与MaimConfig的Agent配置字段完全一致
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from src.config.api_ada_configs import ModelInfo, APIProvider


@dataclass
class PersonalityConfig:
    """人格配置"""

    personality: str
    """人格核心描述，定义AI的基本性格特征和行为准则"""

    reply_style: str = ""
    """回复风格，如"轻松自然"、"正式礼貌"、"幽默风趣"等"""

    interest: str = ""
    """兴趣领域，影响对话内容的偏好和话题选择"""

    plan_style: str = ""
    """群聊行为风格，定义在群聊中的说话规则和行为模式"""

    private_plan_style: str = ""
    """私聊行为风格，定义在私聊中的说话规则和行为模式"""

    visual_style: str = ""
    """视觉风格，生成图片时的提示词风格和美学偏好"""

    states: List[str] = field(default_factory=list)
    """状态列表，多种人格状态用于随机切换，增加对话多样性"""

    state_probability: float = 0.0
    """状态切换概率，0.0-1.0之间，控制人格状态随机切换的频率"""


@dataclass
class BotOverrides:
    """Bot基础配置覆盖"""

    platform: Optional[str] = None
    """运行平台，如"qq"、"telegram"、"discord"等"""

    qq_account: Optional[str] = None
    """QQ账号，数字字符串格式"""

    nickname: Optional[str] = None
    """机器人昵称，在聊天中显示的名称"""

    platforms: List[str] = field(default_factory=list)
    """其他支持平台列表"""

    alias_names: List[str] = field(default_factory=list)
    """别名列表，用于识别机器人的多种称呼方式"""


# 聊天配置覆盖字段
@dataclass
class ChatConfigOverrides:
    """聊天配置覆盖"""

    max_context_size: Optional[int] = None
    """上下文长度，保留的历史消息数量"""

    interest_rate_mode: Optional[str] = None
    """兴趣计算模式，"fast"快速或"accurate"精确"""

    planner_size: Optional[float] = None
    """规划器大小，控制AI执行能力，1.0-3.0"""

    mentioned_bot_reply: Optional[bool] = None
    """提及回复，被@时是否必须回复"""

    auto_chat_value: Optional[float] = None
    """主动聊天频率，数值越低，主动聊天概率越低"""

    enable_auto_chat_value_rules: Optional[bool] = None
    """动态聊天频率，是否启用基于时间的自动频率调整"""

    at_bot_inevitable_reply: Optional[float] = None
    """@回复必然性，1.0为100%回复，0.0为不额外增幅"""

    planner_smooth: Optional[float] = None
    """规划器平滑，减小规划器负荷，推荐2-5"""

    talk_value: Optional[float] = None
    """思考频率，AI主动思考和回复的频率"""

    enable_talk_value_rules: Optional[bool] = None
    """动态思考频率，是否启用基于时间的思考频率调整"""

    talk_value_rules: Optional[List[Dict[str, Any]]] = None
    """思考频率规则，基于时间的动态规则列表"""

    auto_chat_value_rules: Optional[List[Dict[str, Any]]] = None
    """聊天频率规则，基于时间的动态规则列表"""

    include_planner_reasoning: Optional[bool] = None
    """是否将planner推理加入replyer"""


@dataclass
class RelationshipConfigOverrides:
    """关系配置覆盖"""

    enable_relationship: Optional[bool] = None
    """启用关系系统，是否开启用户关系管理功能"""


@dataclass
class ExpressionConfigOverrides:
    """表达配置覆盖"""

    mode: Optional[str] = None
    """表达模式，"classic"经典或"exp_model"表达模型模式"""

    learning_list: Optional[List[List[str]]] = None
    """表达学习配置列表，定义学习模式"""

    expression_groups: Optional[List[Dict[str, Any]]] = None
    """表达学习互通组，定义表达学习的分组规则"""


@dataclass
class MemoryConfigOverrides:
    """记忆配置覆盖"""

    max_memory_number: Optional[int] = None
    """记忆最大数量，保留的长期记忆条数"""

    memory_build_frequency: Optional[int] = None
    """记忆构建频率，每N条消息构建一次记忆"""


@dataclass
class MoodConfigOverrides:
    """情绪配置覆盖"""

    enable_mood: Optional[bool] = None
    """启用情绪系统，是否开启情绪状态管理"""

    mood_update_threshold: Optional[float] = None
    """情绪更新阈值，数值越高，情绪变化越缓慢"""

    emotion_style: Optional[str] = None
    """情感特征，描述情绪变化的模式和特征"""


@dataclass
class EmojiConfigOverrides:
    """表情包配置覆盖"""

    emoji_chance: Optional[float] = None
    """表情包概率，发送表情包的基础概率，0.0-1.0"""

    max_reg_num: Optional[int] = None
    """最大注册数量，表情包缓存的最大数量"""

    do_replace: Optional[bool] = None
    """是否替换，达到最大数量时是否替换旧表情包"""

    check_interval: Optional[int] = None
    """检查间隔，表情包检查间隔时间（分钟）"""

    steal_emoji: Optional[bool] = None
    """偷取表情包，是否从聊天中学习新表情包"""

    content_filtration: Optional[bool] = None
    """内容过滤，是否开启表情包内容过滤"""

    filtration_prompt: Optional[str] = None
    """过滤要求，表情包内容过滤的标准描述"""


@dataclass
class ToolConfigOverrides:
    """工具配置覆盖"""

    enable_tool: Optional[bool] = None
    """启用工具，是否在聊天中启用外部工具调用"""

    tool_cache_ttl: Optional[int] = None
    """工具缓存TTL（秒）"""

    max_tool_execution_time: Optional[int] = None
    """最大工具执行时间（秒）"""

    enable_tool_parallel: Optional[bool] = None
    """是否启用工具并行执行"""


@dataclass
class VoiceConfigOverrides:
    """语音配置覆盖"""

    enable_asr: Optional[bool] = None
    """语音识别，是否启用语音转文字功能"""


@dataclass
class PluginConfigOverrides:
    """插件配置覆盖"""

    enable_plugins: Optional[bool] = None
    """启用插件，是否启用插件系统"""

    tenant_mode_disable_plugins: Optional[bool] = None
    """租户模式禁用，多租户模式下是否禁用所有插件"""

    allowed_plugins: Optional[List[str]] = None
    """允许插件，白名单插件列表"""

    blocked_plugins: Optional[List[str]] = None
    """禁止插件，黑名单插件列表"""


@dataclass
class KeywordReactionConfigOverrides:
    """关键词反应配置覆盖"""

    keyword_rules: Optional[List[Dict[str, Any]]] = None
    """关键词规则，基于关键词匹配的反应规则"""

    regex_rules: Optional[List[Dict[str, Any]]] = None
    """正则规则，基于正则表达式匹配的反应规则"""



@dataclass
class PersonalityConfigOverrides:
    """人格配置覆盖"""
    personality: Optional[str] = None
    reply_style: Optional[str] = None
    interest: Optional[str] = None
    plan_style: Optional[str] = None
    private_plan_style: Optional[str] = None
    visual_style: Optional[str] = None
    states: Optional[List[str]] = None
    state_probability: Optional[float] = None


@dataclass
class LPMMKnowledgeConfigOverrides:
    """LPMM知识库配置覆盖"""
    enable: Optional[bool] = None
    lpmm_mode: Optional[str] = None
    rag_synonym_search_top_k: Optional[int] = None
    rag_synonym_threshold: Optional[float] = None
    info_extraction_workers: Optional[int] = None
    qa_relation_search_top_k: Optional[int] = None
    qa_relation_threshold: Optional[float] = None
    qa_paragraph_search_top_k: Optional[int] = None
    qa_paragraph_node_weight: Optional[float] = None
    qa_ent_filter_top_k: Optional[int] = None
    qa_ppr_damping: Optional[float] = None
    qa_res_top_k: Optional[int] = None
    embedding_dimension: Optional[int] = None


@dataclass
class DreamConfigOverrides:
    """Dream配置覆盖"""
    interval_minutes: Optional[int] = None
    max_iterations: Optional[int] = None


@dataclass
class JargonConfigOverrides:
    """Jargon配置覆盖"""
    all_global: Optional[bool] = None


@dataclass
class ResponsePostProcessConfigOverrides:
    """回复后处理配置覆盖"""
    enable_response_post_process: Optional[bool] = None


@dataclass
class ChineseTypoConfigOverrides:
    """中文错别字配置覆盖"""
    enable: Optional[bool] = None
    error_rate: Optional[float] = None
    min_freq: Optional[int] = None
    tone_error_rate: Optional[float] = None
    word_replace_rate: Optional[float] = None


@dataclass
class ResponseSplitterConfigOverrides:
    """回复分割器配置覆盖"""
    enable: Optional[bool] = None
    max_length: Optional[int] = None
    max_sentence_num: Optional[int] = None
    enable_kaomoji_protection: Optional[bool] = None
    enable_overflow_return_all: Optional[bool] = None


@dataclass
class DebugConfigOverrides:
    """调试配置覆盖"""
    show_prompt: Optional[bool] = None
    show_replyer_prompt: Optional[bool] = None
    show_replyer_reasoning: Optional[bool] = None
    show_jargon_prompt: Optional[bool] = None
    show_memory_prompt: Optional[bool] = None
    show_planner_prompt: Optional[bool] = None
    show_lpmm_paragraph: Optional[bool] = None


@dataclass
class ExperimentalConfigOverrides:
    """实验功能配置覆盖"""
    enable_friend_chat: Optional[bool] = None
    chat_prompts: Optional[List[str]] = None


@dataclass
class MaimMessageConfigOverrides:
    """maim_message配置覆盖"""
    use_custom: Optional[bool] = None
    host: Optional[str] = None
    port: Optional[int] = None
    mode: Optional[str] = None
    use_wss: Optional[bool] = None
    cert_file: Optional[str] = None
    key_file: Optional[str] = None
    auth_token: Optional[List[str]] = None


@dataclass
class TelemetryConfigOverrides:
    """遥测配置覆盖"""
    enable: Optional[bool] = None



@dataclass
class TaskConfigOverrides:
    """任务配置覆盖"""
    model_list: Optional[List[str]] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    slow_threshold: Optional[float] = None


@dataclass
class ModelTaskConfigOverrides:
    """模型任务配置覆盖"""
    utils: Optional[TaskConfigOverrides] = None
    utils_small: Optional[TaskConfigOverrides] = None
    replyer: Optional[TaskConfigOverrides] = None
    vlm: Optional[TaskConfigOverrides] = None
    voice: Optional[TaskConfigOverrides] = None
    tool_use: Optional[TaskConfigOverrides] = None
    planner: Optional[TaskConfigOverrides] = None
    embedding: Optional[TaskConfigOverrides] = None
    lpmm_entity_extract: Optional[TaskConfigOverrides] = None
    lpmm_rdf_build: Optional[TaskConfigOverrides] = None
    lpmm_qa: Optional[TaskConfigOverrides] = None


@dataclass
class ModelConfigOverrides:
    """模型配置覆盖"""
    models: Optional[List[ModelInfo]] = None
    """模型列表覆盖（同名覆盖，不同名追加）"""
    
    api_providers: Optional[List[APIProvider]] = None
    """API提供商列表覆盖（同名覆盖，不同名追加）"""
    
    model_task_config: Optional[ModelTaskConfigOverrides] = None
    """任务模型分配覆盖"""

@dataclass
class ConfigOverrides:
    """整体配置覆盖"""

    chat: Optional[ChatConfigOverrides] = None
    """聊天配置覆盖"""

    relationship: Optional[RelationshipConfigOverrides] = None
    """关系配置覆盖"""

    expression: Optional[ExpressionConfigOverrides] = None
    """表达配置覆盖"""

    memory: Optional[MemoryConfigOverrides] = None
    """记忆配置覆盖"""

    mood: Optional[MoodConfigOverrides] = None
    """情绪配置覆盖"""

    emoji: Optional[EmojiConfigOverrides] = None
    """表情包配置覆盖"""

    tool: Optional[ToolConfigOverrides] = None
    """工具配置覆盖"""

    voice: Optional[VoiceConfigOverrides] = None
    """语音配置覆盖"""

    plugin: Optional[PluginConfigOverrides] = None
    """插件配置覆盖"""

    keyword_reaction: Optional[KeywordReactionConfigOverrides] = None
    """关键词反应配置覆盖"""

    personality: Optional[PersonalityConfigOverrides] = None
    """人格配置覆盖"""

    lpmm_knowledge: Optional[LPMMKnowledgeConfigOverrides] = None
    """LPMM知识库配置覆盖"""

    dream: Optional[DreamConfigOverrides] = None
    """Dream配置覆盖"""
    
    model: Optional[ModelConfigOverrides] = None
    """模型配置覆盖"""

    jargon: Optional[JargonConfigOverrides] = None
    """Jargon配置覆盖"""

    response_post_process: Optional[ResponsePostProcessConfigOverrides] = None
    """回复后处理配置覆盖"""

    chinese_typo: Optional[ChineseTypoConfigOverrides] = None
    """中文错别字配置覆盖"""

    response_splitter: Optional[ResponseSplitterConfigOverrides] = None
    """回复分割器配置覆盖"""

    debug: Optional[DebugConfigOverrides] = None
    """调试配置覆盖"""

    experimental: Optional[ExperimentalConfigOverrides] = None
    """实验功能配置覆盖"""

    maim_message: Optional[MaimMessageConfigOverrides] = None
    """maim_message配置覆盖"""

    telemetry: Optional[TelemetryConfigOverrides] = None
    """遥测配置覆盖"""



@dataclass
class AgentConfig:
    """Agent配置主类 - 与MaimConfig的Agent配置字段完全一致"""

    # 核心字段
    agent_id: str
    """Agent的唯一标识符，通常格式为`tenant_id:agent_id`"""

    name: str
    """Agent的显示名称，用于界面展示"""

    description: str = ""
    """Agent的简要描述信息"""

    tags: List[str] = field(default_factory=list)
    """标签列表，用于分类和检索"""

    # 配置覆盖字段
    persona: PersonalityConfig = field(default_factory=PersonalityConfig)
    """Agent专属的人格配置对象"""

    bot_overrides: BotOverrides = field(default_factory=BotOverrides)
    """Bot基础配置的覆盖项"""

    config_overrides: ConfigOverrides = field(default_factory=ConfigOverrides)
    """整体配置系统的覆盖项"""


def parse_agent_config_from_json(json_data: Dict[str, Any]) -> AgentConfig:
    """从JSON数据解析Agent配置"""

    # 解析人格配置
    persona_data = json_data.get("persona", {})
    persona = PersonalityConfig(
        personality=persona_data.get("personality", ""),
        reply_style=persona_data.get("reply_style", ""),
        interest=persona_data.get("interest", ""),
        plan_style=persona_data.get("plan_style", ""),
        private_plan_style=persona_data.get("private_plan_style", ""),
        visual_style=persona_data.get("visual_style", ""),
        states=persona_data.get("states", []),
        state_probability=persona_data.get("state_probability", 0.0),
    )

    # 解析Bot配置覆盖
    bot_data = json_data.get("bot_overrides", {})
    bot_overrides = BotOverrides(
        platform=bot_data.get("platform"),
        qq_account=bot_data.get("qq_account"),
        nickname=bot_data.get("nickname"),
        platforms=bot_data.get("platforms", []),
        alias_names=bot_data.get("alias_names", []),
    )

    # 解析配置覆盖
    config_data = json_data.get("config_overrides", {})

    # 聊天配置覆盖
    chat_data = config_data.get("chat", {})
    chat_config = ChatConfigOverrides(
        max_context_size=chat_data.get("max_context_size"),
        interest_rate_mode=chat_data.get("interest_rate_mode"),
        planner_size=chat_data.get("planner_size"),
        mentioned_bot_reply=chat_data.get("mentioned_bot_reply"),
        auto_chat_value=chat_data.get("auto_chat_value"),
        enable_auto_chat_value_rules=chat_data.get("enable_auto_chat_value_rules"),
        at_bot_inevitable_reply=chat_data.get("at_bot_inevitable_reply"),
        planner_smooth=chat_data.get("planner_smooth"),
        talk_value=chat_data.get("talk_value"),
        enable_talk_value_rules=chat_data.get("enable_talk_value_rules"),
        talk_value_rules=chat_data.get("talk_value_rules"),
        auto_chat_value_rules=chat_data.get("auto_chat_value_rules"),
        include_planner_reasoning=chat_data.get("include_planner_reasoning"),
    )

    # 其他配置覆盖...
    relationship_config = RelationshipConfigOverrides(
        enable_relationship=config_data.get("relationship", {}).get("enable_relationship")
    )

    expression_config = ExpressionConfigOverrides(
        mode=config_data.get("expression", {}).get("mode"),
        learning_list=config_data.get("expression", {}).get("learning_list"),
        expression_groups=config_data.get("expression", {}).get("expression_groups"),
    )

    memory_config = MemoryConfigOverrides(
        max_memory_number=config_data.get("memory", {}).get("max_memory_number"),
        memory_build_frequency=config_data.get("memory", {}).get("memory_build_frequency"),
    )

    mood_config = MoodConfigOverrides(
        enable_mood=config_data.get("mood", {}).get("enable_mood"),
        mood_update_threshold=config_data.get("mood", {}).get("mood_update_threshold"),
        emotion_style=config_data.get("mood", {}).get("emotion_style"),
    )

    emoji_data = config_data.get("emoji", {})
    emoji_config = EmojiConfigOverrides(
        emoji_chance=emoji_data.get("emoji_chance"),
        max_reg_num=emoji_data.get("max_reg_num"),
        do_replace=emoji_data.get("do_replace"),
        check_interval=emoji_data.get("check_interval"),
        steal_emoji=emoji_data.get("steal_emoji"),
        content_filtration=emoji_data.get("content_filtration"),
        filtration_prompt=emoji_data.get("filtration_prompt"),
    )

    tool_data = config_data.get("tool", {})
    tool_config = ToolConfigOverrides(
        enable_tool=tool_data.get("enable_tool"),
        tool_cache_ttl=tool_data.get("tool_cache_ttl"),
        max_tool_execution_time=tool_data.get("max_tool_execution_time"),
        enable_tool_parallel=tool_data.get("enable_tool_parallel"),
    )

    voice_config = VoiceConfigOverrides(enable_asr=config_data.get("voice", {}).get("enable_asr"))

    plugin_data = config_data.get("plugin", {})
    plugin_config = PluginConfigOverrides(
        enable_plugins=plugin_data.get("enable_plugins"),
        tenant_mode_disable_plugins=plugin_data.get("tenant_mode_disable_plugins"),
        allowed_plugins=plugin_data.get("allowed_plugins"),
        blocked_plugins=plugin_data.get("blocked_plugins"),
    )

    keyword_data = config_data.get("keyword_reaction", {})
    keyword_config = KeywordReactionConfigOverrides(
        keyword_rules=keyword_data.get("keyword_rules"), regex_rules=keyword_data.get("regex_rules")
    )

    personality_data = config_data.get("personality", {})
    personality_config = PersonalityConfigOverrides(
        personality=personality_data.get("personality"),
        reply_style=personality_data.get("reply_style"),
        interest=personality_data.get("interest"),
        plan_style=personality_data.get("plan_style"),
        private_plan_style=personality_data.get("private_plan_style"),
        visual_style=personality_data.get("visual_style"),
        states=personality_data.get("states"),
        state_probability=personality_data.get("state_probability"),
    )

    lpmm_data = config_data.get("lpmm_knowledge", {})
    lpmm_config = LPMMKnowledgeConfigOverrides(
        enable=lpmm_data.get("enable"),
        lpmm_mode=lpmm_data.get("lpmm_mode"),
        rag_synonym_search_top_k=lpmm_data.get("rag_synonym_search_top_k"),
        rag_synonym_threshold=lpmm_data.get("rag_synonym_threshold"),
        info_extraction_workers=lpmm_data.get("info_extraction_workers"),
        qa_relation_search_top_k=lpmm_data.get("qa_relation_search_top_k"),
        qa_relation_threshold=lpmm_data.get("qa_relation_threshold"),
        qa_paragraph_search_top_k=lpmm_data.get("qa_paragraph_search_top_k"),
        qa_paragraph_node_weight=lpmm_data.get("qa_paragraph_node_weight"),
        qa_ent_filter_top_k=lpmm_data.get("qa_ent_filter_top_k"),
        qa_ppr_damping=lpmm_data.get("qa_ppr_damping"),
        qa_res_top_k=lpmm_data.get("qa_res_top_k"),
        embedding_dimension=lpmm_data.get("embedding_dimension"),
    )

    dream_config = DreamConfigOverrides(
        interval_minutes=config_data.get("dream", {}).get("interval_minutes"),
        max_iterations=config_data.get("dream", {}).get("max_iterations"),
    )

    jargon_config = JargonConfigOverrides(
        all_global=config_data.get("jargon", {}).get("all_global")
    )

    resp_pp_config = ResponsePostProcessConfigOverrides(
        enable_response_post_process=config_data.get("response_post_process", {}).get("enable_response_post_process")
    )

    typo_data = config_data.get("chinese_typo", {})
    typo_config = ChineseTypoConfigOverrides(
        enable=typo_data.get("enable"),
        error_rate=typo_data.get("error_rate"),
        min_freq=typo_data.get("min_freq"),
        tone_error_rate=typo_data.get("tone_error_rate"),
        word_replace_rate=typo_data.get("word_replace_rate"),
    )

    splitter_data = config_data.get("response_splitter", {})
    splitter_config = ResponseSplitterConfigOverrides(
        enable=splitter_data.get("enable"),
        max_length=splitter_data.get("max_length"),
        max_sentence_num=splitter_data.get("max_sentence_num"),
        enable_kaomoji_protection=splitter_data.get("enable_kaomoji_protection"),
        enable_overflow_return_all=splitter_data.get("enable_overflow_return_all"),
    )

    debug_data = config_data.get("debug", {})
    debug_config = DebugConfigOverrides(
        show_prompt=debug_data.get("show_prompt"),
        show_replyer_prompt=debug_data.get("show_replyer_prompt"),
        show_replyer_reasoning=debug_data.get("show_replyer_reasoning"),
        show_jargon_prompt=debug_data.get("show_jargon_prompt"),
        show_memory_prompt=debug_data.get("show_memory_prompt"),
        show_planner_prompt=debug_data.get("show_planner_prompt"),
        show_lpmm_paragraph=debug_data.get("show_lpmm_paragraph"),
    )

    exp_data = config_data.get("experimental", {})
    experimental_config = ExperimentalConfigOverrides(
        enable_friend_chat=exp_data.get("enable_friend_chat"),
        chat_prompts=exp_data.get("chat_prompts"),
    )

    msg_data = config_data.get("maim_message", {})
    message_config = MaimMessageConfigOverrides(
        use_custom=msg_data.get("use_custom"),
        host=msg_data.get("host"),
        port=msg_data.get("port"),
        mode=msg_data.get("mode"),
        use_wss=msg_data.get("use_wss"),
        cert_file=msg_data.get("cert_file"),
        key_file=msg_data.get("key_file"),
        auth_token=msg_data.get("auth_token"),
    )

    telemetry_config = TelemetryConfigOverrides(
        enable=config_data.get("telemetry", {}).get("enable")
    )


    config_overrides = ConfigOverrides(
        chat=chat_config,
        relationship=relationship_config,
        expression=expression_config,
        memory=memory_config,
        mood=mood_config,
        emoji=emoji_config,
        tool=tool_config,
        voice=voice_config,
        plugin=plugin_config,
        keyword_reaction=keyword_config,
        personality=personality_config,
        lpmm_knowledge=lpmm_config,
        dream=dream_config,
        jargon=jargon_config,
        response_post_process=resp_pp_config,
        chinese_typo=typo_config,
        response_splitter=splitter_config,
        debug=debug_config,
        experimental=experimental_config,
        maim_message=message_config,
        telemetry=telemetry_config,

    )

    return AgentConfig(
        agent_id=json_data.get("agent_id", ""),
        name=json_data.get("name", ""),
        description=json_data.get("description", ""),
        tags=json_data.get("tags", []),
        persona=persona,
        bot_overrides=bot_overrides,
        config_overrides=config_overrides,
    )


def agent_config_to_dict(agent_config: AgentConfig) -> Dict[str, Any]:
    """将Agent配置转换为字典格式"""
    return {
        "agent_id": agent_config.agent_id,
        "name": agent_config.name,
        "description": agent_config.description,
        "tags": agent_config.tags,
        "persona": {
            "personality": agent_config.persona.personality,
            "reply_style": agent_config.persona.reply_style,
            "interest": agent_config.persona.interest,
            "plan_style": agent_config.persona.plan_style,
            "private_plan_style": agent_config.persona.private_plan_style,
            "visual_style": agent_config.persona.visual_style,
            "states": agent_config.persona.states,
            "state_probability": agent_config.persona.state_probability,
        },
        "bot_overrides": {
            "platform": agent_config.bot_overrides.platform,
            "qq_account": agent_config.bot_overrides.qq_account,
            "nickname": agent_config.bot_overrides.nickname,
            "platforms": agent_config.bot_overrides.platforms,
            "alias_names": agent_config.bot_overrides.alias_names,
        },
        "config_overrides": {
            # 这里只包含非None的配置项
            **{
                k: v.__dict__
                for k, v in [
                    ("chat", agent_config.config_overrides.chat),
                    ("relationship", agent_config.config_overrides.relationship),
                    ("expression", agent_config.config_overrides.expression),
                    ("memory", agent_config.config_overrides.memory),
                    ("mood", agent_config.config_overrides.mood),
                    ("emoji", agent_config.config_overrides.emoji),
                    ("tool", agent_config.config_overrides.tool),
                    ("voice", agent_config.config_overrides.voice),
                    ("plugin", agent_config.config_overrides.plugin),
                    ("keyword_reaction", agent_config.config_overrides.keyword_reaction),
                    ("personality", agent_config.config_overrides.personality),
                    ("lpmm_knowledge", agent_config.config_overrides.lpmm_knowledge),
                    ("dream", agent_config.config_overrides.dream),
                    ("jargon", agent_config.config_overrides.jargon),
                    ("response_post_process", agent_config.config_overrides.response_post_process),
                    ("chinese_typo", agent_config.config_overrides.chinese_typo),
                    ("response_splitter", agent_config.config_overrides.response_splitter),
                    ("debug", agent_config.config_overrides.debug),
                    ("experimental", agent_config.config_overrides.experimental),
                    ("maim_message", agent_config.config_overrides.maim_message),
                    ("telemetry", agent_config.config_overrides.telemetry),
                ]
                if v is not None and hasattr(v, "__dict__")
            }
        },
    }
