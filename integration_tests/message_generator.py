"""
LLM消息生成器

使用LLM生成真实场景的多租户多agent测试消息
"""

import json
import random
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import logging

from .config import TestScenario, AgentConfig, TenantConfig, LLMConfig

logger = logging.getLogger(__name__)


@dataclass
class GeneratedMessage:
    """生成的消息"""

    content: str
    user_id: str
    agent_id: str
    tenant_id: str
    platform: str
    group_id: Optional[str] = None
    timestamp: float = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()
        if self.metadata is None:
            self.metadata = {}


class LLMMessageGenerator:
    """基于LLM的消息生成器"""

    def __init__(self, llm_config: LLMConfig):
        self.llm_config = llm_config
        self._setup_llm_client()

    def _setup_llm_client(self):
        """设置LLM客户端"""
        try:
            # 尝试导入OpenAI客户端
            import openai

            self.client = openai.AsyncOpenAI(api_key=self.llm_config.api_key, base_url=self.llm_config.api_base)
            logger.info(f"LLM客户端初始化成功，模型: {self.llm_config.model_name}")
        except ImportError:
            logger.warning("OpenAI库未安装，将使用模拟消息生成器")
            self.client = None
        except Exception as e:
            logger.error(f"LLM客户端初始化失败: {e}")
            self.client = None

    async def generate_conversation_messages(
        self, scenario: TestScenario, agent_config: AgentConfig, tenant_config: TenantConfig, message_count: int = None
    ) -> List[GeneratedMessage]:
        """生成对话消息"""

        if message_count is None:
            message_count = scenario.message_count

        if self.client:
            return await self._generate_with_llm(scenario, agent_config, tenant_config, message_count)
        else:
            return self._generate_mock_messages(scenario, agent_config, tenant_config, message_count)

    async def _generate_with_llm(
        self, scenario: TestScenario, agent_config: AgentConfig, tenant_config: TenantConfig, message_count: int
    ) -> List[GeneratedMessage]:
        """使用LLM生成消息"""

        messages = []

        # 构建系统提示词
        system_prompt = self._build_system_prompt(agent_config, tenant_config, scenario)

        # 构建用户请求
        user_prompt = self._build_user_prompt(scenario, agent_config, message_count)

        try:
            response = await self.client.chat.completions.create(
                model=self.llm_config.model_name,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                temperature=self.llm_config.temperature,
                max_tokens=self.llm_config.max_tokens * message_count,
                timeout=self.llm_config.timeout,
            )

            content = response.choices[0].message.content

            # 解析生成的消息
            messages = self._parse_generated_messages(content, scenario, agent_config, tenant_config)

            logger.info(f"LLM生成了 {len(messages)} 条消息，场景: {scenario.name}")

        except Exception as e:
            logger.error(f"LLM消息生成失败: {e}，使用模拟消息")
            return self._generate_mock_messages(scenario, agent_config, tenant_config, message_count)

        return messages

    def _build_system_prompt(
        self, agent_config: AgentConfig, tenant_config: TenantConfig, scenario: TestScenario
    ) -> str:
        """构建系统提示词"""

        return f"""你是一个专业的测试消息生成器。请根据以下配置生成真实的用户消息：

租户信息：
- 租户ID: {tenant_config.tenant_id}
- 租户名称: {tenant_config.tenant_name}
- 租户描述: {tenant_config.description}

智能体信息：
- 智能体ID: {agent_config.agent_id}
- 智能体名称: {agent_config.agent_name}
- 智能体性格: {agent_config.personality}
- 智能体描述: {agent_config.description}

测试场景：
- 场景名称: {scenario.name}
- 场景描述: {scenario.description}
- 对话主题: {", ".join(scenario.conversation_topics)}
- 平台: {scenario.platform}
- 用户ID: {scenario.user_id}
- 群组ID: {scenario.group_id or "私聊"}

请生成自然的用户消息，符合该场景下的真实对话风格。消息应该：
1. 语言自然，符合中文表达习惯
2. 内容与场景和主题相关
3. 包含适当的语气和情感
4. 长度适中（通常10-100字）

请以JSON格式返回消息列表，格式如下：
[
  {{"content": "消息内容1", "type": "question"}},
  {{"content": "消息内容2", "type": "statement"}},
  {{"content": "消息内容3", "type": "emotion"}}
]

消息类型可以是：question(问题), statement(陈述), emotion(情感表达), greeting(问候), farewell(告别)
"""

    def _build_user_prompt(self, scenario: TestScenario, agent_config: AgentConfig, message_count: int) -> str:
        """构建用户请求"""

        topics_str = "、".join(scenario.conversation_topics)

        return f"""请为场景"{scenario.name}"生成 {message_count} 条用户消息。

要求：
1. 消息主题围绕：{topics_str}
2. 适合与{agent_config.agent_name}（{agent_config.personality}）对话
3. 混合不同类型的消息：提问、陈述、情感表达等
4. 语言风格要自然真实

请确保消息多样性，避免重复和模板化。"""

    def _parse_generated_messages(
        self, content: str, scenario: TestScenario, agent_config: AgentConfig, tenant_config: TenantConfig
    ) -> List[GeneratedMessage]:
        """解析LLM生成的消息"""

        try:
            # 尝试解析JSON
            if "```json" in content:
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                json_content = content[json_start:json_end].strip()
            elif "[" in content:
                json_start = content.find("[")
                json_end = content.rfind("]") + 1
                json_content = content[json_start:json_end]
            else:
                json_content = content

            message_data = json.loads(json_content)

            messages = []
            for i, msg_data in enumerate(message_data):
                if isinstance(msg_data, dict) and "content" in msg_data:
                    msg = GeneratedMessage(
                        content=msg_data["content"],
                        user_id=scenario.user_id,
                        agent_id=scenario.agent_id,
                        tenant_id=scenario.tenant_id,
                        platform=scenario.platform,
                        group_id=scenario.group_id,
                        timestamp=time.time() + i * 0.1,
                        metadata={
                            "scenario": scenario.name,
                            "message_type": msg_data.get("type", "statement"),
                            "agent_name": agent_config.agent_name,
                            "tenant_name": tenant_config.tenant_name,
                        },
                    )
                    messages.append(msg)

            return messages

        except Exception as e:
            logger.error(f"解析LLM生成的消息失败: {e}")
            # 将整个内容作为一条消息
            return [
                GeneratedMessage(
                    content=content.strip(),
                    user_id=scenario.user_id,
                    agent_id=scenario.agent_id,
                    tenant_id=scenario.tenant_id,
                    platform=scenario.platform,
                    group_id=scenario.group_id,
                    metadata={
                        "scenario": scenario.name,
                        "message_type": "statement",
                        "agent_name": agent_config.agent_name,
                        "tenant_name": tenant_config.tenant_name,
                    },
                )
            ]

    def _generate_mock_messages(
        self, scenario: TestScenario, agent_config: AgentConfig, tenant_config: TenantConfig, message_count: int
    ) -> List[GeneratedMessage]:
        """生成模拟消息（不使用LLM）"""

        # 预定义的消息模板
        message_templates = {
            "技术讨论": [
                "关于Python的性能优化，有什么建议吗？",
                "我最近在学机器学习，有什么好的资源推荐？",
                "这个bug调试了好久，还是没找到原因",
                "大家对微服务架构怎么看？",
                "有没有人用过Docker容器化部署？",
                "异步编程的优势是什么？",
                "如何提高代码的可维护性？",
                "最近在看设计模式，感觉很有用",
                "数据库索引优化的最佳实践是什么？",
                "API设计有什么好的原则吗？",
            ],
            "教育辅导": [
                "这道数学题我不太会，能帮我看看吗？",
                "英语单词总是记不住，有什么好方法？",
                "考试前应该如何高效复习？",
                "老师，这个概念我还是不太理解",
                "怎么提高写作能力？",
                "科学实验的步骤有哪些？",
                "历史事件的时间线总是记混",
                "化学方程式怎么配平？",
                "物理公式的推导过程是怎样的？",
                "如何制定学习计划？",
            ],
            "日常聊天": [
                "今天天气真好，出去玩了",
                "最近看了什么好电影吗？",
                "周末有什么安排？",
                "这个游戏太难了，卡关了",
                "晚饭吃什么好呢？",
                "最近工作好累啊",
                "有什么好看的小说推荐吗？",
                "周末去爬山怎么样？",
                "学了一道新菜，很有成就感",
                "最近在追一部剧，很不错",
            ],
        }

        # 选择合适的消息模板
        templates = []
        if "技术" in scenario.name or "编程" in scenario.conversation_topics:
            templates.extend(message_templates["技术讨论"])
        if "教育" in scenario.name or "学习" in scenario.conversation_topics:
            templates.extend(message_templates["教育辅导"])
        if "日常" in scenario.name or "聊天" in scenario.name:
            templates.extend(message_templates["日常聊天"])

        # 如果没有匹配的模板，使用默认模板
        if not templates:
            templates = [
                "你好，请问有什么可以帮助你的吗？",
                "今天过得怎么样？",
                "最近在忙什么呢？",
                "有什么新鲜事分享吗？",
                "周末有什么计划？",
            ]

        # 生成消息
        messages = []
        for i in range(message_count):
            content = random.choice(templates)
            # 添加一些随机变化
            if random.random() < 0.3:
                content += f"（来自{agent_config.agent_name}的测试）"

            msg = GeneratedMessage(
                content=content,
                user_id=scenario.user_id,
                agent_id=scenario.agent_id,
                tenant_id=scenario.tenant_id,
                platform=scenario.platform,
                group_id=scenario.group_id,
                timestamp=time.time() + i * random.uniform(0.1, 1.0),
                metadata={
                    "scenario": scenario.name,
                    "message_type": "mock",
                    "agent_name": agent_config.agent_name,
                    "tenant_name": tenant_config.tenant_name,
                    "generated_by": "mock_generator",
                },
            )
            messages.append(msg)

        logger.info(f"模拟生成了 {len(messages)} 条消息，场景: {scenario.name}")
        return messages


# 消息类型定义
class MessageType:
    QUESTION = "question"
    STATEMENT = "statement"
    EMOTION = "emotion"
    GREETING = "greeting"
    FAREWELL = "farewell"


# 预定义的测试场景
def get_test_scenarios() -> List[TestScenario]:
    """获取预定义的测试场景"""

    return [
        TestScenario(
            name="技术问答",
            description="技术讨论场景",
            tenant_id="tenant_a",
            agent_id="assistant_tech",
            platform="qq",
            user_id="developer_001",
            group_id="tech_group_001",
            message_count=15,
            conversation_topics=["Python", "机器学习", "系统架构", "调试"],
        ),
        TestScenario(
            name="学习辅导",
            description="教育辅导场景",
            tenant_id="tenant_b",
            agent_id="tutor_edu",
            platform="wechat",
            user_id="student_001",
            message_count=20,
            conversation_topics=["数学", "学习方法", "考试准备"],
        ),
        TestScenario(
            name="日常聊天",
            description="日常对话场景",
            tenant_id="tenant_c",
            agent_id="companion_general",
            platform="discord",
            user_id="user_001",
            message_count=12,
            conversation_topics=["电影", "音乐", "日常生活"],
        ),
    ]
