"""
记忆服务的Pydantic模式定义

定义所有API请求和响应的数据模式。
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from uuid import UUID

from pydantic import BaseModel, Field, validator


class MemoryLevel(str, Enum):
    """记忆级别枚举"""

    AGENT = "agent"  # 智能体级别
    PLATFORM = "platform"  # 平台级别
    CHAT = "chat"  # 聊天流级别


class MemoryStatus(str, Enum):
    """记忆状态枚举"""

    ACTIVE = "active"  # 活跃状态
    EXPIRED = "expired"  # 已过期
    ARCHIVED = "archived"  # 已归档


class ConflictStatus(str, Enum):
    """冲突状态枚举"""

    PENDING = "pending"  # 待处理
    FOLLOWING = "following"  # 跟踪中
    RESOLVED = "resolved"  # 已解决


# 基础模式
class BaseSchema(BaseModel):
    """基础模式类"""

    class Config:
        use_enum_values = True
        json_encoders = {datetime: lambda v: v.isoformat(), UUID: lambda v: str(v)}


# 隔离上下文模式
class IsolationContext(BaseSchema):
    """隔离上下文模式"""

    tenant_id: str = Field(..., description="租户ID", min_length=1, max_length=255)
    agent_id: str = Field(..., description="智能体ID", min_length=1, max_length=255)
    platform: Optional[str] = Field(None, description="平台标识", max_length=255)
    scope_id: Optional[str] = Field(None, description="作用域ID（聊天流ID）", max_length=255)

    @validator("platform")
    def validate_platform(cls, v):
        if v and not v.strip():
            return None
        return v

    @validator("scope_id")
    def validate_scope_id(cls, v):
        if v and not v.strip():
            return None
        return v


# 记忆相关模式
class MemoryCreate(BaseSchema):
    """创建记忆请求模式"""

    title: str = Field(..., description="记忆标题", min_length=1, max_length=500)
    content: str = Field(..., description="记忆内容", min_length=1)
    level: MemoryLevel = Field(..., description="记忆级别")
    platform: Optional[str] = Field(None, description="平台标识", max_length=255)
    scope_id: Optional[str] = Field(None, description="作用域ID", max_length=255)
    tags: List[str] = Field(default_factory=list, description="标签列表", max_items=10)
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    expires_at: Optional[datetime] = Field(None, description="过期时间")

    @validator("tags")
    def validate_tags(cls, v):
        if v:
            v = [tag.strip() for tag in v if tag.strip()]
            return v[:10]  # 限制最多10个标签
        return []

    @validator("metadata")
    def validate_metadata(cls, v):
        if v and len(str(v)) > 10000:  # 限制元数据大小
            raise ValueError("元数据过大，最大10KB")
        return v


class MemoryUpdate(BaseSchema):
    """更新记忆请求模式"""

    title: Optional[str] = Field(None, description="记忆标题", min_length=1, max_length=500)
    content: Optional[str] = Field(None, description="记忆内容", min_length=1)
    tags: Optional[List[str]] = Field(None, description="标签列表", max_items=10)
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")
    expires_at: Optional[datetime] = Field(None, description="过期时间")
    status: Optional[MemoryStatus] = Field(None, description="记忆状态")

    @validator("tags")
    def validate_tags(cls, v):
        if v:
            v = [tag.strip() for tag in v if tag.strip()]
            return v[:10]
        return v


class MemorySearch(BaseSchema):
    """记忆搜索请求模式"""

    query: str = Field(..., description="搜索查询", min_length=1, max_length=1000)
    limit: int = Field(default=10, ge=1, le=100, description="返回结果数量限制")
    offset: int = Field(default=0, ge=0, description="偏移量")
    level: Optional[MemoryLevel] = Field(None, description="记忆级别过滤")
    platform: Optional[str] = Field(None, description="平台过滤", max_length=255)
    scope_id: Optional[str] = Field(None, description="作用域过滤", max_length=255)
    tags: Optional[List[str]] = Field(None, description="标签过滤", max_items=10)
    date_from: Optional[datetime] = Field(None, description="开始日期")
    date_to: Optional[datetime] = Field(None, description="结束日期")
    similarity_threshold: float = Field(default=0.7, ge=0.0, le=1.0, description="相似度阈值")


class MemoryQuery(BaseSchema):
    """记忆复杂查询模式"""

    filters: Dict[str, Any] = Field(default_factory=dict, description="查询过滤器")
    sort_by: Optional[str] = Field("created_at", description="排序字段")
    sort_order: str = Field("desc", regex="^(asc|desc)$", description="排序顺序")
    limit: int = Field(default=10, ge=1, le=100, description="返回结果数量限制")
    offset: int = Field(default=0, ge=0, description="偏移量")


class MemoryAggregate(BaseSchema):
    """记忆聚合请求模式"""

    source_scopes: List[str] = Field(..., description="源作用域列表", min_items=1)
    target_level: MemoryLevel = Field(..., description="目标级别")
    target_platform: Optional[str] = Field(None, description="目标平台", max_length=255)
    target_scope_id: Optional[str] = Field(None, description="目标作用域ID", max_length=255)
    merge_strategy: str = Field("append", regex="^(append|merge|replace)$", description="合并策略")


class MemoryResponse(BaseSchema):
    """记忆响应模式"""

    id: UUID = Field(..., description="记忆ID")
    tenant_id: str = Field(..., description="租户ID")
    agent_id: str = Field(..., description="智能体ID")
    level: MemoryLevel = Field(..., description="记忆级别")
    platform: Optional[str] = Field(None, description="平台标识")
    scope_id: Optional[str] = Field(None, description="作用域ID")
    title: str = Field(..., description="记忆标题")
    content: str = Field(..., description="记忆内容")
    tags: List[str] = Field(default_factory=list, description="标签列表")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    status: MemoryStatus = Field(..., description="记忆状态")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    expires_at: Optional[datetime] = Field(None, description="过期时间")
    embedding: Optional[List[float]] = Field(None, description="向量嵌入")
    similarity_score: Optional[float] = Field(None, description="相似度分数")


class MemoryListResponse(BaseSchema):
    """记忆列表响应模式"""

    items: List[MemoryResponse] = Field(..., description="记忆列表")
    total: int = Field(..., description="总数量")
    limit: int = Field(..., description="返回数量限制")
    offset: int = Field(..., description="偏移量")
    has_more: bool = Field(..., description="是否有更多数据")


# 冲突跟踪相关模式
class ConflictCreate(BaseSchema):
    """创建冲突记录请求模式"""

    title: str = Field(..., description="冲突标题", min_length=1, max_length=500)
    context: Optional[str] = Field(None, description="冲突上下文", max_length=2000)
    start_following: bool = Field(default=False, description="是否开始跟踪")
    chat_id: Optional[str] = Field(None, description="聊天ID", max_length=255)


class ConflictUpdate(BaseSchema):
    """更新冲突记录请求模式"""

    title: Optional[str] = Field(None, description="冲突标题", min_length=1, max_length=500)
    context: Optional[str] = Field(None, description="冲突上下文", max_length=2000)
    start_following: Optional[bool] = Field(None, description="是否开始跟踪")
    resolved: Optional[bool] = Field(None, description="是否已解决")


class ConflictResponse(BaseSchema):
    """冲突记录响应模式"""

    id: UUID = Field(..., description="冲突ID")
    tenant_id: str = Field(..., description="租户ID")
    agent_id: str = Field(..., description="智能体ID")
    platform: Optional[str] = Field(None, description="平台标识")
    scope_id: Optional[str] = Field(None, description="作用域ID")
    title: str = Field(..., description="冲突标题")
    context: Optional[str] = Field(None, description="冲突上下文")
    start_following: bool = Field(..., description="是否开始跟踪")
    resolved: bool = Field(..., description="是否已解决")
    chat_id: Optional[str] = Field(None, description="聊天ID")
    created_at: datetime = Field(..., description="创建时间")
    resolved_at: Optional[datetime] = Field(None, description="解决时间")


# 系统管理相关模式
class HealthCheckResponse(BaseSchema):
    """健康检查响应模式"""

    status: str = Field(..., description="服务状态")
    version: str = Field(..., description="服务版本")
    database: Dict[str, Any] = Field(..., description="数据库状态")
    redis: Dict[str, Any] = Field(..., description="Redis状态")
    uptime: float = Field(..., description="运行时间(秒)")
    timestamp: datetime = Field(..., description="检查时间")


class SystemStatsResponse(BaseSchema):
    """系统统计响应模式"""

    total_memories: int = Field(..., description="总记忆数量")
    total_conflicts: int = Field(..., description="总冲突数量")
    active_tenants: int = Field(..., description="活跃租户数量")
    memory_by_level: Dict[str, int] = Field(..., description="按级别统计记忆数量")
    recent_activity: List[Dict[str, Any]] = Field(..., description="最近活动")
    storage_usage: Dict[str, Any] = Field(..., description="存储使用情况")


class MaintenanceRequest(BaseSchema):
    """维护任务请求模式"""

    task_type: str = Field(..., regex="^(cleanup|backup|optimize|reindex)$", description="任务类型")
    dry_run: bool = Field(default=False, description="是否试运行")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="任务参数")


class MaintenanceResponse(BaseSchema):
    """维护任务响应模式"""

    task_id: str = Field(..., description="任务ID")
    status: str = Field(..., description="任务状态")
    message: str = Field(..., description="任务消息")
    result: Optional[Dict[str, Any]] = Field(None, description="任务结果")
    started_at: datetime = Field(..., description="开始时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")


# 通用响应模式
class SuccessResponse(BaseSchema):
    """成功响应模式"""

    success: bool = Field(default=True, description="操作是否成功")
    message: str = Field(..., description="成功消息")
    data: Optional[Any] = Field(None, description="响应数据")


class ErrorResponse(BaseSchema):
    """错误响应模式"""

    success: bool = Field(default=False, description="操作是否成功")
    error: Dict[str, Any] = Field(..., description="错误信息")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="错误时间")


# 批量操作模式
class BatchMemoryCreate(BaseSchema):
    """批量创建记忆请求模式"""

    memories: List[MemoryCreate] = Field(..., min_items=1, max_items=50, description="记忆列表")


class BatchDeleteRequest(BaseSchema):
    """批量删除请求模式"""

    memory_ids: List[UUID] = Field(..., min_items=1, max_items=50, description="记忆ID列表")


class BatchOperationResponse(BaseSchema):
    """批量操作响应模式"""

    total: int = Field(..., description="总操作数量")
    successful: int = Field(..., description="成功数量")
    failed: int = Field(..., description="失败数量")
    errors: List[Dict[str, Any]] = Field(default_factory=list, description="错误列表")
