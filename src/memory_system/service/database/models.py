"""
记忆服务的数据库模型定义

使用SQLAlchemy ORM定义记忆和冲突跟踪的数据模型。
"""

from typing import Dict, Any
from uuid import uuid4

from sqlalchemy import Column, String, Text, DateTime, Boolean, Integer, Float, Index, JSON, ARRAY, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, VECTOR
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class Memory(Base):
    """记忆表 - 支持T+A+P+C四维隔离"""

    __tablename__ = "memories"

    # 主键和基础字段
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(String(255), nullable=False, comment="租户ID")
    agent_id = Column(String(255), nullable=False, comment="智能体ID")
    platform = Column(String(255), nullable=True, comment="平台标识")
    scope_id = Column(String(255), nullable=True, comment="作用域ID（聊天流ID）")
    level = Column(String(50), nullable=False, comment="记忆级别: agent/platform/chat")

    # 记忆内容
    title = Column(Text, nullable=False, comment="记忆标题")
    content = Column(Text, nullable=False, comment="记忆内容")
    embedding = Column(VECTOR(1536), nullable=True, comment="向量嵌入（1536维）")

    # 元数据
    tags = Column(ARRAY(String), default=[], comment="标签列表")
    metadata = Column(JSON, default={}, comment="元数据（JSON格式）")

    # 状态和时间
    status = Column(String(20), default="active", comment="记忆状态: active/expired/archived")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")
    expires_at = Column(DateTime(timezone=True), nullable=True, comment="过期时间")

    # 统计字段
    access_count = Column(Integer, default=0, comment="访问次数")
    last_accessed = Column(DateTime(timezone=True), nullable=True, comment="最后访问时间")

    # 约束
    __table_args__ = (
        CheckConstraint("level IN ('agent', 'platform', 'chat')", name="check_memory_level"),
        CheckConstraint("status IN ('active', 'expired', 'archived')", name="check_memory_status"),
        # 复合索引 - 优化隔离查询
        Index("idx_tenant_agent", "tenant_id", "agent_id"),
        Index("idx_platform_scope", "platform", "scope_id"),
        Index("idx_level_status", "level", "status"),
        Index("idx_tenant_isolation", "tenant_id", "agent_id", "platform", "scope_id"),
        # 时间索引
        Index("idx_created_at", "created_at"),
        Index("idx_expires_at", "expires_at"),
        Index("idx_updated_at", "updated_at"),
        # 向量相似度搜索索引
        Index("idx_embedding_gin", "embedding", postgresql_using="gin"),
        # 标签索引
        Index("idx_tags", "tags", postgresql_using="gin"),
        # 状态和时间复合索引
        Index("idx_status_created", "status", "created_at"),
        Index("idx_tenant_level_status", "tenant_id", "level", "status"),
    )

    def __repr__(self):
        return f"<Memory(id={self.id}, tenant_id={self.tenant_id}, title={self.title[:50]})>"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": str(self.id),
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "platform": self.platform,
            "scope_id": self.scope_id,
            "level": self.level,
            "title": self.title,
            "content": self.content,
            "tags": self.tags or [],
            "metadata": self.metadata or {},
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
        }


class Conflict(Base):
    """冲突跟踪表 - 支持T+A+P+C四维隔离"""

    __tablename__ = "conflicts"

    # 主键和隔离字段
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(String(255), nullable=False, comment="租户ID")
    agent_id = Column(String(255), nullable=False, comment="智能体ID")
    platform = Column(String(255), nullable=True, comment="平台标识")
    scope_id = Column(String(255), nullable=True, comment="作用域ID（聊天流ID）")

    # 冲突内容
    title = Column(String(500), nullable=False, comment="冲突标题")
    context = Column(Text, nullable=True, comment="冲突上下文")
    chat_id = Column(String(255), nullable=True, comment="聊天ID")

    # 跟踪状态
    start_following = Column(Boolean, default=False, comment="是否开始跟踪")
    resolved = Column(Boolean, default=False, comment="是否已解决")

    # 时间字段
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")
    resolved_at = Column(DateTime(timezone=True), nullable=True, comment="解决时间")

    # 关联的记忆ID
    related_memory_ids = Column(ARRAY(UUID(as_uuid=True)), default=[], comment="相关记忆ID列表")

    # 约束
    __table_args__ = (
        Index("idx_tenant_conflict", "tenant_id", "agent_id", "platform", "scope_id"),
        Index("idx_following_status", "start_following", "resolved"),
        Index("idx_tenant_resolved", "tenant_id", "resolved"),
        Index("idx_created_at", "created_at"),
        Index("idx_resolved_at", "resolved_at"),
        Index("idx_chat_id", "chat_id"),
    )

    def __repr__(self):
        return f"<Conflict(id={self.id}, tenant_id={self.tenant_id}, title={self.title[:50]})>"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": str(self.id),
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "platform": self.platform,
            "scope_id": self.scope_id,
            "title": self.title,
            "context": self.context,
            "chat_id": self.chat_id,
            "start_following": self.start_following,
            "resolved": self.resolved,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "related_memory_ids": [str(mid) for mid in (self.related_memory_ids or [])],
        }


class MemoryStats(Base):
    """记忆统计表 - 用于存储各种统计数据"""

    __tablename__ = "memory_stats"

    # 主键和分组字段
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(String(255), nullable=False, comment="租户ID")
    agent_id = Column(String(255), nullable=False, comment="智能体ID")
    platform = Column(String(255), nullable=True, comment="平台标识")
    level = Column(String(50), nullable=False, comment="记忆级别")

    # 统计数据
    total_count = Column(Integer, default=0, comment="总记忆数量")
    active_count = Column(Integer, default=0, comment="活跃记忆数量")
    expired_count = Column(Integer, default=0, comment="过期记忆数量")
    archived_count = Column(Integer, default=0, comment="归档记忆数量")
    total_access_count = Column(Integer, default=0, comment="总访问次数")

    # 存储统计
    total_size_bytes = Column(Integer, default=0, comment="总存储大小(字节)")
    avg_embedding_size = Column(Float, default=0.0, comment="平均嵌入大小")

    # 时间统计
    oldest_memory_at = Column(DateTime(timezone=True), nullable=True, comment="最早记忆时间")
    newest_memory_at = Column(DateTime(timezone=True), nullable=True, comment="最新记忆时间")
    last_calculated_at = Column(DateTime(timezone=True), server_default=func.now(), comment="最后计算时间")

    # 约束
    __table_args__ = (
        CheckConstraint("level IN ('agent', 'platform', 'chat')", name="check_stats_level"),
        Index("idx_stats_grouping", "tenant_id", "agent_id", "platform", "level"),
        Index("idx_stats_calculated", "last_calculated_at"),
    )

    def __repr__(self):
        return f"<MemoryStats(tenant_id={self.tenant_id}, level={self.level}, total={self.total_count})>"


class OperationLog(Base):
    """操作日志表 - 记录所有重要操作"""

    __tablename__ = "operation_logs"

    # 主键
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # 操作信息和隔离上下文
    operation_type = Column(String(50), nullable=False, comment="操作类型")
    resource_type = Column(String(50), nullable=False, comment="资源类型: memory/conflict")
    resource_id = Column(UUID(as_uuid=True), nullable=True, comment="资源ID")
    tenant_id = Column(String(255), nullable=False, comment="租户ID")
    agent_id = Column(String(255), nullable=False, comment="智能体ID")
    platform = Column(String(255), nullable=True, comment="平台标识")
    scope_id = Column(String(255), nullable=True, comment="作用域ID")

    # 操作详情
    operation_details = Column(JSON, default={}, comment="操作详情")
    old_values = Column(JSON, nullable=True, comment="旧值（用于更新操作）")
    new_values = Column(JSON, nullable=True, comment="新值")

    # 执行信息
    user_id = Column(String(255), nullable=True, comment="执行用户ID")
    session_id = Column(String(255), nullable=True, comment="会话ID")
    ip_address = Column(String(45), nullable=True, comment="IP地址")
    user_agent = Column(Text, nullable=True, comment="用户代理")

    # 结果信息
    success = Column(Boolean, default=True, comment="操作是否成功")
    error_message = Column(Text, nullable=True, comment="错误信息")
    execution_time_ms = Column(Integer, nullable=True, comment="执行时间(毫秒)")

    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")

    # 约束
    __table_args__ = (
        Index("idx_operation_tenant", "tenant_id", "created_at"),
        Index("idx_operation_resource", "resource_type", "resource_id"),
        Index("idx_operation_type", "operation_type", "created_at"),
        Index("idx_operation_success", "success", "created_at"),
    )

    def __repr__(self):
        return f"<OperationLog(type={self.operation_type}, resource={self.resource_type}, success={self.success})>"


class SystemMetrics(Base):
    """系统指标表 - 存储系统性能和使用指标"""

    __tablename__ = "system_metrics"

    # 主键
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # 指标信息
    metric_name = Column(String(100), nullable=False, comment="指标名称")
    metric_value = Column(Float, nullable=False, comment="指标值")
    metric_unit = Column(String(20), nullable=True, comment="指标单位")

    # 维度信息
    tenant_id = Column(String(255), nullable=True, comment="租户维度")
    agent_id = Column(String(255), nullable=True, comment="智能体维度")
    platform = Column(String(255), nullable=True, comment="平台维度")
    additional_dimensions = Column(JSON, default={}, comment="额外维度")

    # 时间信息
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), comment="记录时间")
    period_start = Column(DateTime(timezone=True), nullable=True, comment="周期开始时间")
    period_end = Column(DateTime(timezone=True), nullable=True, comment="周期结束时间")

    # 约束
    __table_args__ = (
        Index("idx_metric_name_time", "metric_name", "recorded_at"),
        Index("idx_metric_tenant", "tenant_id", "metric_name", "recorded_at"),
        Index("idx_metric_period", "period_start", "period_end"),
    )

    def __repr__(self):
        return f"<SystemMetrics(name={self.metric_name}, value={self.metric_value})>"
