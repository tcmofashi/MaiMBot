"""
多租户集成测试配置模块

定义租户、智能体、平台等测试场景的配置
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import logging
import toml

logger = logging.getLogger(__name__)


@dataclass
class TenantConfig:
    """租户配置"""

    tenant_id: str
    tenant_name: str
    description: Optional[str] = None
    settings: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentConfig:
    """智能体配置"""

    agent_id: str
    agent_name: str
    personality: str
    tenant_id: str
    description: Optional[str] = None
    settings: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlatformConfig:
    """平台配置"""

    platform: str
    name: str
    description: Optional[str] = None
    settings: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UserIdentity:
    """用户身份"""

    user_id: str
    nickname: str
    platform: str
    tenant_id: str
    cardname: Optional[str] = None


@dataclass
class GroupIdentity:
    """群组身份"""

    group_id: str
    group_name: str
    platform: str
    tenant_id: str
    description: Optional[str] = None


@dataclass
class TestScenario:
    """测试场景配置"""

    name: str
    description: str
    tenant_id: str
    agent_id: str
    platform: str
    user_id: str
    group_id: Optional[str] = None
    message_count: int = 10
    conversation_topics: List[str] = field(default_factory=list)
    settings: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMConfig:
    """LLM配置"""

    model_name: str = "gpt-3.5-turbo"
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    temperature: float = 0.8
    max_tokens: int = 200
    timeout: float = 30.0


@dataclass
class TestConfig:
    """测试配置"""

    tenants: List[TenantConfig] = field(default_factory=list)
    agents: List[AgentConfig] = field(default_factory=list)
    platforms: List[PlatformConfig] = field(default_factory=list)
    scenarios: List[TestScenario] = field(default_factory=list)
    llm: LLMConfig = field(default_factory=LLMConfig)

    # 全局设置
    concurrent_users: int = 5
    message_delay_min: float = 1.0
    message_delay_max: float = 3.0
    test_duration: int = 300  # 秒
    log_level: str = "INFO"

    @classmethod
    def from_toml(cls, config_path: str) -> "TestConfig":
        """从TOML文件加载配置"""
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"配置文件不存在: {config_path}")

        logger.info(f"加载测试配置: {config_path}")
        raw = toml.load(config_path)

        # 解析租户配置
        tenants = []
        for tenant_data in raw.get("tenants", []):
            tenants.append(TenantConfig(**tenant_data))

        # 解析智能体配置
        agents = []
        for agent_data in raw.get("agents", []):
            agents.append(AgentConfig(**agent_data))

        # 解析平台配置
        platforms = []
        for platform_data in raw.get("platforms", []):
            platforms.append(PlatformConfig(**platform_data))

        # 解析测试场景
        scenarios = []
        for scenario_data in raw.get("scenarios", []):
            scenarios.append(TestScenario(**scenario_data))

        # 解析LLM配置
        llm_data = raw.get("llm", {})
        llm = LLMConfig(**llm_data)

        # 解析全局设置
        global_settings = raw.get("settings", {})

        return cls(
            tenants=tenants,
            agents=agents,
            platforms=platforms,
            scenarios=scenarios,
            llm=llm,
            concurrent_users=global_settings.get("concurrent_users", 5),
            message_delay_min=global_settings.get("message_delay_min", 1.0),
            message_delay_max=global_settings.get("message_delay_max", 3.0),
            test_duration=global_settings.get("test_duration", 300),
            log_level=global_settings.get("log_level", "INFO"),
        )

    def get_tenant(self, tenant_id: str) -> Optional[TenantConfig]:
        """获取租户配置"""
        for tenant in self.tenants:
            if tenant.tenant_id == tenant_id:
                return tenant
        return None

    def get_agent(self, agent_id: str) -> Optional[AgentConfig]:
        """获取智能体配置"""
        for agent in self.agents:
            if agent.agent_id == agent_id:
                return agent
        return None

    def get_platform(self, platform: str) -> Optional[PlatformConfig]:
        """获取平台配置"""
        for platform_config in self.platforms:
            if platform_config.platform == platform:
                return platform_config
        return None


# 默认测试配置
def create_default_config() -> TestConfig:
    """创建默认的多租户测试配置"""

    tenants = [
        TenantConfig(
            tenant_id="tenant_a",
            tenant_name="科技公司A",
            description="专注于AI技术研发的科技公司",
            settings={"industry": "technology", "size": "medium"},
        ),
        TenantConfig(
            tenant_id="tenant_b",
            tenant_name="教育机构B",
            description="在线教育平台",
            settings={"industry": "education", "size": "large"},
        ),
        TenantConfig(
            tenant_id="tenant_c",
            tenant_name="个人用户C",
            description="个人开发者",
            settings={"industry": "individual", "size": "small"},
        ),
    ]

    agents = [
        AgentConfig(
            agent_id="assistant_tech",
            agent_name="技术助手",
            personality="专业、严谨、善于技术解答",
            tenant_id="tenant_a",
            description="专注于技术问题的AI助手",
        ),
        AgentConfig(
            agent_id="tutor_edu",
            agent_name="教育导师",
            personality="耐心、亲切、善于教学",
            tenant_id="tenant_b",
            description="专注于教育辅导的AI助手",
        ),
        AgentConfig(
            agent_id="companion_general",
            agent_name="通用伙伴",
            personality="友善、幽默、健谈",
            tenant_id="tenant_c",
            description="日常聊天的AI伙伴",
        ),
    ]

    platforms = [
        PlatformConfig(platform="qq", name="QQ", description="腾讯QQ平台"),
        PlatformConfig(platform="wechat", name="微信", description="微信平台"),
        PlatformConfig(platform="discord", name="Discord", description="Discord平台"),
    ]

    scenarios = [
        TestScenario(
            name="技术讨论群",
            description="公司内部技术讨论群聊",
            tenant_id="tenant_a",
            agent_id="assistant_tech",
            platform="qq",
            user_id="dev_001",
            group_id="tech_group_001",
            message_count=15,
            conversation_topics=["Python编程", "算法优化", "系统架构", "Bug调试"],
        ),
        TestScenario(
            name="一对一教学",
            description="学生与教育导师的一对一交流",
            tenant_id="tenant_b",
            agent_id="tutor_edu",
            platform="wechat",
            user_id="student_001",
            message_count=20,
            conversation_topics=["数学问题", "学习方法", "作业辅导", "考试准备"],
        ),
        TestScenario(
            name="日常聊天",
            description="个人用户的日常闲聊",
            tenant_id="tenant_c",
            agent_id="companion_general",
            platform="discord",
            user_id="user_001",
            message_count=12,
            conversation_topics=["电影推荐", "兴趣爱好", "日常生活", "游戏讨论"],
        ),
    ]

    return TestConfig(
        tenants=tenants,
        agents=agents,
        platforms=platforms,
        scenarios=scenarios,
        concurrent_users=3,
        message_delay_min=0.5,
        message_delay_max=2.0,
        test_duration=600,
    )
