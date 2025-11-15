"""
MaiBot 多租户隔离查询最佳实践代码示例
提供T+A+C+P四维隔离的查询模式和方法

作者: Claude
创建时间: 2025-01-11
"""

from typing import List, Optional, Dict, Any
from datetime import datetime

from src.common.logger import get_logger
from src.isolation.isolation_context import IsolationContext, get_isolation_context
from .database_model import ChatStreams, Messages, MemoryChest, LLMUsage

logger = get_logger("isolation_query_examples")


class IsolationQueryBuilder:
    """多租户隔离查询构建器"""

    def __init__(self, isolation_context: IsolationContext = None):
        """
        初始化查询构建器

        Args:
            isolation_context: 隔离上下文，如果为None则尝试从上下文获取
        """
        self.isolation_context = isolation_context or get_isolation_context()
        if not self.isolation_context:
            raise ValueError("隔离上下文不能为空")

    def get_base_filter(self, include_platform: bool = True, include_chat: bool = False) -> Dict[str, str]:
        """
        获取基础隔离过滤条件

        Args:
            include_platform: 是否包含平台过滤
            include_chat: 是否包含聊天流过滤

        Returns:
            Dict[str, str]: 过滤条件字典
        """
        filters = {"tenant_id": self.isolation_context.tenant_id, "agent_id": self.isolation_context.agent_id}

        if include_platform and self.isolation_context.platform:
            filters["platform"] = self.isolation_context.platform

        if include_chat and self.isolation_context.chat_stream_id:
            filters["chat_stream_id"] = self.isolation_context.chat_stream_id

        return filters


class ChatStreamQueries:
    """聊天流隔离查询示例"""

    def __init__(self, isolation_context: IsolationContext = None):
        self.builder = IsolationQueryBuilder(isolation_context)

    def get_chat_stream_by_id(self, chat_stream_id: str) -> Optional[ChatStreams]:
        """根据聊天流ID获取聊天流（隔离）"""
        try:
            filters = self.builder.get_base_filter()
            filters["chat_stream_id"] = chat_stream_id

            return ChatStreams.get_or_none(**filters)
        except Exception as e:
            logger.exception(f"获取聊天流失败: {e}")
            return None

    def get_chat_streams_by_platform(self, platform: str) -> List[ChatStreams]:
        """获取指定平台的所有聊天流（租户+智能体隔离）"""
        try:
            filters = self.builder.get_base_filter(include_platform=True)
            filters["platform"] = platform

            return list(ChatStreams.select().where(**filters))
        except Exception as e:
            logger.exception(f"获取平台聊天流失败: {e}")
            return []

    def get_all_chat_streams(self) -> List[ChatStreams]:
        """获取租户下的所有聊天流（智能体隔离）"""
        try:
            filters = self.builder.get_base_filter(include_platform=False)

            return list(ChatStreams.select().where(**filters))
        except Exception as e:
            logger.exception(f"获取所有聊天流失败: {e}")
            return []

    def get_active_chat_streams(self, hours: int = 24) -> List[ChatStreams]:
        """获取最近活跃的聊天流"""
        try:
            filters = self.builder.get_base_filter(include_platform=False)
            cutoff_time = datetime.now().timestamp() - (hours * 3600)

            return list(
                ChatStreams.select()
                .where(ChatStreams.last_active_time > cutoff_time, **filters)
                .order_by(ChatStreams.last_active_time.desc())
            )
        except Exception as e:
            logger.exception(f"获取活跃聊天流失败: {e}")
            return []

    def search_chat_streams_by_user(self, user_id: str, platform: Optional[str] = None) -> List[ChatStreams]:
        """根据用户ID搜索聊天流"""
        try:
            filters = self.builder.get_base_filter(include_platform=True)
            filters["user_id"] = user_id

            if platform:
                filters["platform"] = platform

            return list(ChatStreams.select().where(**filters))
        except Exception as e:
            logger.exception(f"根据用户搜索聊天流失败: {e}")
            return []


class MessageQueries:
    """消息隔离查询示例"""

    def __init__(self, isolation_context: IsolationContext = None):
        self.builder = IsolationQueryBuilder(isolation_context)

    def get_messages_by_chat_stream(self, chat_stream_id: str, limit: int = 50, offset: int = 0) -> List[Messages]:
        """获取指定聊天流的消息（完全隔离）"""
        try:
            filters = self.builder.get_base_filter(include_platform=True, include_chat=True)
            filters["chat_stream_id"] = chat_stream_id

            return list(Messages.select().where(**filters).order_by(Messages.time.desc()).limit(limit).offset(offset))
        except Exception as e:
            logger.exception(f"获取聊天流消息失败: {e}")
            return []

    def get_messages_by_platform(self, platform: str, limit: int = 100) -> List[Messages]:
        """获取指定平台的消息（租户+智能体+平台隔离）"""
        try:
            filters = self.builder.get_base_filter(include_platform=True)
            filters["platform"] = platform

            return list(Messages.select().where(**filters).order_by(Messages.time.desc()).limit(limit))
        except Exception as e:
            logger.exception(f"获取平台消息失败: {e}")
            return []

    def get_recent_messages(self, hours: int = 24, limit: int = 200) -> List[Messages]:
        """获取最近的消息（租户+智能体隔离）"""
        try:
            filters = self.builder.get_base_filter(include_platform=False)
            cutoff_time = datetime.now().timestamp() - (hours * 3600)

            return list(
                Messages.select()
                .where(Messages.time > cutoff_time, **filters)
                .order_by(Messages.time.desc())
                .limit(limit)
            )
        except Exception as e:
            logger.exception(f"获取最近消息失败: {e}")
            return []

    def search_messages(self, keyword: str, limit: int = 50) -> List[Messages]:
        """搜索消息内容（隔离）"""
        try:
            filters = self.builder.get_base_filter(include_platform=True)

            return list(
                Messages.select()
                .where(Messages.processed_plain_text.contains(keyword), **filters)
                .order_by(Messages.time.desc())
                .limit(limit)
            )
        except Exception as e:
            logger.exception(f"搜索消息失败: {e}")
            return []

    def get_message_statistics(self) -> Dict[str, Any]:
        """获取消息统计信息（隔离）"""
        try:
            filters = self.builder.get_base_filter(include_platform=False)

            total_count = Messages.select().where(**filters).count()

            # 按平台统计
            platform_stats = {}
            if self.isolation_context.platform:
                platform_filters = filters.copy()
                platform_filters["platform"] = self.isolation_context.platform
                platform_stats[self.isolation_context.platform] = Messages.select().where(**platform_filters).count()
            else:
                # 获取所有平台统计
                query = (
                    Messages.select(Messages.platform, Messages.id.count().alias("count"))
                    .where(**filters)
                    .group_by(Messages.platform)
                )

                for row in query:
                    platform_stats[row.platform] = row.count

            return {
                "total_messages": total_count,
                "platform_statistics": platform_stats,
                "tenant_id": self.isolation_context.tenant_id,
                "agent_id": self.isolation_context.agent_id,
            }
        except Exception as e:
            logger.exception(f"获取消息统计失败: {e}")
            return {}


class MemoryQueries:
    """记忆隔离查询示例，支持多层次记忆管理"""

    def __init__(self, isolation_context: IsolationContext = None):
        self.builder = IsolationQueryBuilder(isolation_context)

    def query_memories(self, memory_scope: str = "agent", scope_id: str = None, limit: int = 20) -> List[MemoryChest]:
        """
        查询记忆，支持不同隔离级别

        Args:
            memory_scope: 记忆级别 ("agent", "platform", "chat")
            scope_id: 范围ID (platform名称或chat_stream_id)
            limit: 返回数量限制
        """
        try:
            filters = {"tenant_id": self.isolation_context.tenant_id, "agent_id": self.isolation_context.agent_id}

            if memory_scope == "agent":
                filters["memory_level"] = "agent"
            elif memory_scope == "platform" and scope_id:
                filters.update({"memory_level": "platform", "platform": scope_id})
            elif memory_scope == "chat" and scope_id:
                filters.update({"memory_level": "chat", "chat_stream_id": scope_id})
            else:
                raise ValueError(f"无效的记忆级别或缺少scope_id: {memory_scope}")

            return list(MemoryChest.select().where(**filters).order_by(MemoryChest.id.desc()).limit(limit))
        except Exception as e:
            logger.exception(f"查询记忆失败: {e}")
            return []

    def get_agent_memories(self, limit: int = 50) -> List[MemoryChest]:
        """获取智能体级别的所有记忆"""
        return self.query_memories("agent", limit=limit)

    def get_platform_memories(self, platform: str, limit: int = 30) -> List[MemoryChest]:
        """获取特定平台的记忆"""
        return self.query_memories("platform", platform, limit)

    def get_chat_memories(self, chat_stream_id: str, limit: int = 20) -> List[MemoryChest]:
        """获取特定聊天流的记忆"""
        return self.query_memories("chat", chat_stream_id, limit)

    def search_memories(self, keyword: str, memory_scope: str = "agent", scope_id: str = None) -> List[MemoryChest]:
        """搜索记忆内容"""
        try:
            filters = {"tenant_id": self.isolation_context.tenant_id, "agent_id": self.isolation_context.agent_id}

            if memory_scope == "agent":
                filters["memory_level"] = "agent"
            elif memory_scope == "platform" and scope_id:
                filters.update({"memory_level": "platform", "platform": scope_id})
            elif memory_scope == "chat" and scope_id:
                filters.update({"memory_level": "chat", "chat_stream_id": scope_id})

            return list(
                MemoryChest.select()
                .where(MemoryChest.content.contains(keyword) | MemoryChest.title.contains(keyword), **filters)
                .order_by(MemoryChest.id.desc())
            )
        except Exception as e:
            logger.exception(f"搜索记忆失败: {e}")
            return []

    def get_memory_summary(self) -> Dict[str, Any]:
        """获取记忆统计摘要"""
        try:
            agent_memories = self.get_agent_memories(limit=1000)
            platform_memories = {}
            chat_memories = {}

            # 如果有平台信息，获取平台记忆
            if self.isolation_context.platform:
                platform_memories[self.isolation_context.platform] = self.get_platform_memories(
                    self.isolation_context.platform, limit=1000
                )

            # 如果有聊天流信息，获取聊天记忆
            if self.isolation_context.chat_stream_id:
                chat_memories[self.isolation_context.chat_stream_id] = self.get_chat_memories(
                    self.isolation_context.chat_stream_id, limit=1000
                )

            return {
                "agent_memory_count": len(agent_memories),
                "platform_memory_counts": {k: len(v) for k, v in platform_memories.items()},
                "chat_memory_counts": {k: len(v) for k, v in chat_memories.items()},
                "tenant_id": self.isolation_context.tenant_id,
                "agent_id": self.isolation_context.agent_id,
            }
        except Exception as e:
            logger.exception(f"获取记忆摘要失败: {e}")
            return {}


class UsageQueries:
    """LLM使用量隔离查询示例"""

    def __init__(self, isolation_context: IsolationContext = None):
        self.builder = IsolationQueryBuilder(isolation_context)

    def get_usage_statistics(self, days: int = 30) -> Dict[str, Any]:
        """获取使用量统计（租户隔离）"""
        try:
            filters = {"tenant_id": self.isolation_context.tenant_id, "agent_id": self.isolation_context.agent_id}

            cutoff_date = datetime.now() - datetime.timedelta(days=days)

            # 总使用量
            total_usage = LLMUsage.select().where(LLMUsage.timestamp >= cutoff_date, **filters)

            total_tokens = sum(u.total_tokens for u in total_usage)
            total_cost = sum(u.cost for u in total_usage)

            # 按平台统计
            platform_stats = {}
            if self.isolation_context.platform:
                platform_filters = filters.copy()
                platform_filters["platform"] = self.isolation_context.platform
                platform_usage = LLMUsage.select().where(LLMUsage.timestamp >= cutoff_date, **platform_filters)

                platform_stats[self.isolation_context.platform] = {
                    "tokens": sum(u.total_tokens for u in platform_usage),
                    "cost": sum(u.cost for u in platform_usage),
                    "requests": len(platform_usage),
                }

            return {
                "period_days": days,
                "total_tokens": total_tokens,
                "total_cost": total_cost,
                "total_requests": len(total_usage),
                "platform_statistics": platform_stats,
                "tenant_id": self.isolation_context.tenant_id,
                "agent_id": self.isolation_context.agent_id,
            }
        except Exception as e:
            logger.exception(f"获取使用量统计失败: {e}")
            return {}


class IsolationQueryManager:
    """隔离查询管理器 - 统一入口"""

    def __init__(self, isolation_context: IsolationContext = None):
        self.isolation_context = isolation_context
        self.chat_streams = ChatStreamQueries(isolation_context)
        self.messages = MessageQueries(isolation_context)
        self.memories = MemoryQueries(isolation_context)
        self.usage = UsageQueries(isolation_context)

    def validate_isolation_context(self) -> bool:
        """验证隔离上下文是否有效"""
        if not self.isolation_context:
            logger.error("隔离上下文为空")
            return False

        if not self.isolation_context.tenant_id:
            logger.error("租户ID为空")
            return False

        if not self.isolation_context.agent_id:
            logger.error("智能体ID为空")
            return False

        return True

    def get_tenant_overview(self) -> Dict[str, Any]:
        """获取租户概览信息"""
        if not self.validate_isolation_context():
            return {}

        try:
            return {
                "tenant_id": self.isolation_context.tenant_id,
                "agent_id": self.isolation_context.agent_id,
                "platform": self.isolation_context.platform,
                "chat_stream_count": len(self.chat_streams.get_all_chat_streams()),
                "recent_message_count": len(self.messages.get_recent_messages(hours=24)),
                "agent_memory_count": len(self.memories.get_agent_memories(limit=1000)),
                "usage_stats": self.usage.get_usage_statistics(days=7),
            }
        except Exception as e:
            logger.exception(f"获取租户概览失败: {e}")
            return {}


# 便捷函数
def get_isolated_query_manager(isolation_context: IsolationContext = None) -> IsolationQueryManager:
    """获取隔离查询管理器实例"""
    return IsolationQueryManager(isolation_context)


# 使用示例
if __name__ == "__main__":
    # 示例1: 创建隔离查询管理器
    from src.isolation.isolation_context import create_isolation_context

    # 创建隔离上下文
    context = create_isolation_context(tenant_id="tenant1", agent_id="agent1", platform="qq", chat_stream_id="chat123")

    # 获取查询管理器
    query_manager = get_isolated_query_manager(context)

    # 示例2: 查询聊天流
    chat_streams = query_manager.chat_streams.get_all_chat_streams()
    print(f"找到 {len(chat_streams)} 个聊天流")

    # 示例3: 查询消息
    messages = query_manager.messages.get_recent_messages(hours=1)
    print(f"最近1小时有 {len(messages)} 条消息")

    # 示例4: 查询记忆
    agent_memories = query_manager.memories.get_agent_memories(limit=10)
    print(f"智能体有 {len(agent_memories)} 条记忆")

    # 示例5: 获取租户概览
    overview = query_manager.get_tenant_overview()
    print("租户概览:", overview)
