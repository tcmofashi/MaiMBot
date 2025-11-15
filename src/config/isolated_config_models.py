"""
多租户隔离配置系统的数据库模型
支持T+A+P三维隔离的配置存储和继承
"""

from datetime import datetime
from peewee import *
from src.common.database.database_model import db


class IsolatedConfigBase(Model):
    """隔离配置基类"""

    class Meta:
        database = db
        indexes = (
            # 复合索引，优化配置查询性能
            (("tenant_id", "agent_id", "platform", "config_level"), False),
        )

    # 基础隔离字段
    tenant_id = TextField(index=True)  # T: 租户隔离
    agent_id = TextField(index=True)  # A: 智能体隔离
    platform = TextField(null=True, index=True)  # P: 平台隔离（可为空，表示通用配置）

    # 配置层级和内容
    config_level = TextField(index=True)  # 配置层级: "global", "tenant", "agent", "platform"
    config_category = TextField(index=True)  # 配置分类: "bot", "personality", "chat" 等
    config_key = TextField(index=True)  # 配置键名
    config_value = TextField()  # 配置值（JSON格式）
    config_type = TextField(default="string")  # 配置类型: "string", "int", "float", "bool", "json"

    # 元数据
    description = TextField(null=True)  # 配置描述
    is_active = BooleanField(default=True)  # 是否启用
    priority = IntegerField(default=0)  # 优先级（用于覆盖逻辑）

    # 审计字段
    created_at = DateTimeField(default=datetime.now)
    updated_at = DateTimeField(default=datetime.now)
    created_by = TextField(null=True)
    updated_by = TextField(null=True)

    def __str__(self):
        return f"{self.config_level}:{self.tenant_id}:{self.agent_id}:{self.platform}:{self.config_key}"

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        return super().save(*args, **kwargs)


class TenantConfig(IsolatedConfigBase):
    """租户级别配置"""

    class Meta:
        table_name = "tenant_configs"
        indexes = (
            (("tenant_id", "config_category", "config_key"), True),  # 唯一索引
        )

    def __init__(self, **kwargs):
        kwargs["config_level"] = "tenant"
        super().__init__(**kwargs)


class AgentConfig(IsolatedConfigBase):
    """智能体级别配置"""

    class Meta:
        table_name = "agent_configs"
        indexes = (
            (("tenant_id", "agent_id", "config_category", "config_key"), True),  # 唯一索引
        )

    def __init__(self, **kwargs):
        kwargs["config_level"] = "agent"
        super().__init__(**kwargs)


class PlatformConfig(IsolatedConfigBase):
    """平台级别配置"""

    class Meta:
        table_name = "platform_configs"
        indexes = (
            (("tenant_id", "agent_id", "platform", "config_category", "config_key"), True),  # 唯一索引
        )

    def __init__(self, **kwargs):
        kwargs["config_level"] = "platform"
        super().__init__(**kwargs)


class ConfigTemplate(Model):
    """配置模板"""

    class Meta:
        database = db

    name = TextField(unique=True, index=True)  # 模板名称
    description = TextField(null=True)  # 模板描述
    config_category = TextField(index=True)  # 配置分类
    template_content = TextField()  # 模板内容（JSON格式）
    is_system = BooleanField(default=False)  # 是否系统模板
    is_active = BooleanField(default=True)  # 是否启用

    created_at = DateTimeField(default=datetime.now)
    updated_at = DateTimeField(default=datetime.now)
    created_by = TextField(null=True)
    updated_by = TextField(null=True)

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        return super().save(*args, **kwargs)


class ConfigHistory(Model):
    """配置变更历史"""

    class Meta:
        database = db
        indexes = ((("tenant_id", "agent_id", "platform"), False),)

    # 关联的配置信息
    tenant_id = TextField(index=True)
    agent_id = TextField(index=True)
    platform = TextField(null=True, index=True)
    config_category = TextField(index=True)
    config_key = TextField(index=True)

    # 变更信息
    old_value = TextField(null=True)  # 旧值
    new_value = TextField(null=True)  # 新值
    change_type = TextField(index=True)  # 变更类型: "create", "update", "delete"
    change_reason = TextField(null=True)  # 变更原因

    # 操作信息
    operated_by = TextField(null=True)  # 操作者
    operated_at = DateTimeField(default=datetime.now)

    # 审计信息
    ip_address = TextField(null=True)
    user_agent = TextField(null=True)


# 创建数据库表函数
def create_isolated_config_tables():
    """创建隔离配置相关的数据库表"""
    tables = [IsolatedConfigBase, TenantConfig, AgentConfig, PlatformConfig, ConfigTemplate, ConfigHistory]

    with db:
        for table in tables:
            if not table.table_exists():
                db.create_tables([table])
                print(f"Created table: {table._meta.table_name}")
            else:
                print(f"Table already exists: {table._meta.table_name}")


# 配置查询辅助类
class ConfigQueryBuilder:
    """配置查询构建器"""

    @staticmethod
    def get_tenant_configs(tenant_id: str, category: str = None):
        """获取租户配置"""
        query = TenantConfig.select().where((TenantConfig.tenant_id == tenant_id) & (TenantConfig.is_active))

        if category:
            query = query.where(TenantConfig.config_category == category)

        return query.order_by(TenantConfig.priority.desc(), TenantConfig.config_key)

    @staticmethod
    def get_agent_configs(tenant_id: str, agent_id: str, category: str = None):
        """获取智能体配置"""
        query = AgentConfig.select().where(
            (AgentConfig.tenant_id == tenant_id) & (AgentConfig.agent_id == agent_id) & (AgentConfig.is_active)
        )

        if category:
            query = query.where(AgentConfig.config_category == category)

        return query.order_by(AgentConfig.priority.desc(), AgentConfig.config_key)

    @staticmethod
    def get_platform_configs(tenant_id: str, agent_id: str, platform: str, category: str = None):
        """获取平台配置"""
        query = PlatformConfig.select().where(
            (PlatformConfig.tenant_id == tenant_id)
            & (PlatformConfig.agent_id == agent_id)
            & (PlatformConfig.platform == platform)
            & (PlatformConfig.is_active)
        )

        if category:
            query = query.where(PlatformConfig.config_category == category)

        return query.order_by(PlatformConfig.priority.desc(), PlatformConfig.config_key)

    @staticmethod
    def get_effective_configs(tenant_id: str, agent_id: str, platform: str = None, category: str = None):
        """获取有效配置（按继承优先级合并）"""
        # 获取各级别配置
        tenant_configs = ConfigQueryBuilder.get_tenant_configs(tenant_id, category)
        agent_configs = ConfigQueryBuilder.get_agent_configs(tenant_id, agent_id, category)

        platform_configs = None
        if platform:
            platform_configs = ConfigQueryBuilder.get_platform_configs(tenant_id, agent_id, platform, category)

        # 合并配置（优先级：platform > agent > tenant）
        merged_configs = {}

        # 1. 租户配置（基础层）
        for config in tenant_configs:
            merged_configs[config.config_key] = {
                "value": config.config_value,
                "type": config.config_type,
                "level": "tenant",
                "source": config,
            }

        # 2. 智能体配置（覆盖层）
        for config in agent_configs:
            merged_configs[config.config_key] = {
                "value": config.config_value,
                "type": config.config_type,
                "level": "agent",
                "source": config,
            }

        # 3. 平台配置（最上层）
        if platform_configs:
            for config in platform_configs:
                merged_configs[config.config_key] = {
                    "value": config.config_value,
                    "type": config.config_type,
                    "level": "platform",
                    "source": config,
                }

        return merged_configs
