# -*- coding: utf-8 -*-
"""
隔离化记忆系统API
提供便捷的高级接口和使用示例
"""

from typing import Dict, Any, List
from dataclasses import dataclass

from src.isolation.isolation_context import create_isolation_context
from src.memory_system.isolated_memory_chest import (
    get_isolated_memory_chest,
    get_isolated_memory_chest_simple,
    clear_isolated_memory_chest,
    get_memory_system_stats,
)
from src.memory_system.isolated_questions import (
    get_isolated_conflict_tracker,
    get_isolated_conflict_tracker_simple,
    clear_isolated_conflict_tracker,
    get_conflict_system_stats,
)
from src.common.logger import get_logger

logger = get_logger("isolated_memory_api")


@dataclass
class MemorySystemConfig:
    """记忆系统配置"""

    enable_aggregation: bool = True
    enable_conflict_tracking: bool = True
    cache_ttl: int = 300
    max_memories_per_level: int = 1000
    auto_cleanup_days: int = 30


class IsolatedMemorySystem:
    """隔离化记忆系统高级API"""

    def __init__(self, tenant_id: str, agent_id: str, platform: str = None, config: MemorySystemConfig = None):
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.platform = platform
        self.config = config or MemorySystemConfig()

        # 创建隔离上下文
        self.isolation_context = create_isolation_context(tenant_id=tenant_id, agent_id=agent_id, platform=platform)

        # 获取隔离化组件
        self.memory_chest = get_isolated_memory_chest(self.isolation_context)
        self.conflict_tracker = get_isolated_conflict_tracker(self.isolation_context)

        logger.info(f"创建隔离化记忆系统: {tenant_id}:{agent_id}:{platform or 'default'}")

    async def add_memory(
        self, title: str, content: str, level: str = "agent", scope_id: str = None, locked: bool = False
    ) -> str:
        """
        添加记忆

        Args:
            title: 记忆标题
            content: 记忆内容
            level: 记忆级别 ("agent", "platform", "chat")
            scope_id: 范围ID (平台名称或聊天流ID)
            locked: 是否锁定

        Returns:
            str: 记忆ID
        """
        try:
            memory_context = level
            if level == "platform" and scope_id:
                memory_context = f"platform:{scope_id}"
            elif level == "chat" and scope_id:
                memory_context = f"chat:{scope_id}"

            memory_id = await self.memory_chest.add_memory(
                title=title, content=content, memory_context=memory_context, scope_id=scope_id, locked=locked
            )

            logger.info(f"添加记忆: {title} (级别: {level}, ID: {memory_id})")
            return memory_id

        except Exception as e:
            logger.error(f"添加记忆时出错: {e}")
            return ""

    def query_memories(self, level: str = "agent", scope_id: str = None, limit: int = 10) -> List[Dict[str, Any]]:
        """
        查询记忆

        Args:
            level: 记忆级别 ("agent", "platform", "chat")
            scope_id: 范围ID
            limit: 返回数量限制

        Returns:
            List[Dict]: 记忆列表
        """
        try:
            memories = self.memory_chest.query_memories(query_scope=level, scope_id=scope_id, limit=limit)

            logger.info(f"查询记忆: {level} 范围，找到 {len(memories)} 条记录")
            return memories

        except Exception as e:
            logger.error(f"查询记忆时出错: {e}")
            return []

    async def search_memories(self, question: str, chat_id: str = "") -> str:
        """
        根据问题搜索记忆答案

        Args:
            question: 问题
            chat_id: 聊天ID

        Returns:
            str: 答案
        """
        try:
            answer = await self.memory_chest.get_answer_by_question(chat_id, question)
            logger.info(f"搜索记忆答案: {question} -> {len(answer) if answer else 0} 字符")
            return answer

        except Exception as e:
            logger.error(f"搜索记忆答案时出错: {e}")
            return ""

    async def track_conflict(
        self, question: str, chat_id: str = "", context: str = "", start_following: bool = True
    ) -> bool:
        """
        跟踪冲突问题

        Args:
            question: 问题
            chat_id: 聊天ID
            context: 上下文
            start_following: 是否开始跟踪

        Returns:
            bool: 是否成功
        """
        try:
            success = await self.conflict_tracker.track_conflict(
                question=question, context=context, start_following=start_following, chat_id=chat_id
            )

            if success:
                logger.info(f"开始跟踪冲突: {question}")
            else:
                logger.warning(f"跟踪冲突失败: {question}")

            return success

        except Exception as e:
            logger.error(f"跟踪冲突时出错: {e}")
            return False

    async def aggregate_memories(self, from_levels: List[str], to_level: str, scope_ids: List[str] = None) -> bool:
        """
        聚合记忆

        Args:
            from_levels: 源级别列表
            to_level: 目标级别
            scope_ids: 范围ID列表

        Returns:
            bool: 是否成功
        """
        if not self.config.enable_aggregation:
            logger.warning("记忆聚合功能未启用")
            return False

        try:
            from_scopes = []
            for level in from_levels:
                if scope_ids:
                    for scope_id in scope_ids:
                        from_scopes.append({"level": level, "scope_id": scope_id})
                else:
                    from_scopes.append({"level": level})

            to_scope = {"level": to_level}
            if scope_ids:
                to_scope["scope_id"] = scope_ids[0]

            success = self.memory_chest.aggregate_memories(from_scopes, to_scope)

            if success:
                logger.info(f"聚合记忆: {from_levels} -> {to_level}")
            else:
                logger.warning(f"聚合记忆失败: {from_levels} -> {to_level}")

            return success

        except Exception as e:
            logger.error(f"聚合记忆时出错: {e}")
            return False

    def get_statistics(self) -> Dict[str, Any]:
        """获取记忆系统统计信息"""
        try:
            memory_stats = self.memory_chest.get_memory_statistics()
            conflict_stats = self.conflict_tracker.get_conflict_statistics()

            combined_stats = {
                "system_info": {
                    "tenant_id": self.tenant_id,
                    "agent_id": self.agent_id,
                    "platform": self.platform or "",
                    "isolation_scope": str(self.isolation_context.scope),
                },
                "memory_stats": memory_stats,
                "conflict_stats": conflict_stats,
                "config": {
                    "enable_aggregation": self.config.enable_aggregation,
                    "enable_conflict_tracking": self.config.enable_conflict_tracking,
                    "cache_ttl": self.config.cache_ttl,
                    "max_memories_per_level": self.config.max_memories_per_level,
                    "auto_cleanup_days": self.config.auto_cleanup_days,
                },
            }

            return combined_stats

        except Exception as e:
            logger.error(f"获取统计信息时出错: {e}")
            return {}

    async def cleanup_expired_memories(self) -> int:
        """清理过期记忆"""
        try:
            count = await self.memory_chest.cleanup_expired_memories(self.config.auto_cleanup_days)
            logger.info(f"清理过期记忆: {count} 条")
            return count

        except Exception as e:
            logger.error(f"清理过期记忆时出错: {e}")
            return 0

    def get_isolation_info(self) -> Dict[str, str]:
        """获取隔离信息"""
        return self.memory_chest.get_isolation_info()


# 便捷函数
async def create_isolated_memory_system(
    tenant_id: str, agent_id: str, platform: str = None, config: MemorySystemConfig = None
) -> IsolatedMemorySystem:
    """创建隔离化记忆系统"""
    return IsolatedMemorySystem(tenant_id, agent_id, platform, config)


async def process_isolated_memory(
    title: str,
    content: str,
    tenant_id: str,
    agent_id: str,
    level: str = "agent",
    scope_id: str = None,
    platform: str = None,
) -> str:
    """处理隔离化记忆（便捷函数）"""
    memory_system = await create_isolated_memory_system(tenant_id, agent_id, platform)
    return await memory_system.add_memory(title, content, level, scope_id)


async def search_isolated_memory(
    question: str, tenant_id: str, agent_id: str, chat_id: str = "", platform: str = None
) -> str:
    """搜索隔离化记忆（便捷函数）"""
    memory_system = await create_isolated_memory_system(tenant_id, agent_id, platform)
    return await memory_system.search_memories(question, chat_id)


def query_isolated_memories(
    tenant_id: str, agent_id: str, level: str = "agent", scope_id: str = None, limit: int = 10, platform: str = None
) -> List[Dict[str, Any]]:
    """查询隔离化记忆（便捷函数）"""
    memory_chest = get_isolated_memory_chest_simple(tenant_id, agent_id, platform)
    return memory_chest.query_memories(level, scope_id, limit)


async def track_isolated_conflict(
    question: str,
    tenant_id: str,
    agent_id: str,
    chat_id: str = "",
    context: str = "",
    start_following: bool = True,
    platform: str = None,
) -> bool:
    """跟踪隔离化冲突（便捷函数）"""
    conflict_tracker = get_isolated_conflict_tracker_simple(tenant_id, agent_id, platform)
    return await conflict_tracker.track_conflict(question, context, start_following, chat_id)


def get_isolation_stats(tenant_id: str = None, agent_id: str = None) -> Dict[str, Any]:
    """获取隔离系统统计信息"""
    memory_stats = get_memory_system_stats()
    conflict_stats = get_conflict_system_stats()

    combined_stats = {"memory_system": memory_stats, "conflict_system": conflict_stats}

    if tenant_id and agent_id:
        # 获取特定租户的统计信息
        tenant_memory_stats = {}
        tenant_conflict_stats = {}

        # 从全局统计中提取特定租户的信息
        for scope_key, stats in memory_stats.get("memory_chests", {}).items():
            if scope_key.startswith(f"{tenant_id}:{agent_id}"):
                tenant_memory_stats[scope_key] = stats

        for scope_key, stats in conflict_stats.get("conflict_trackers", {}).items():
            if scope_key.startswith(f"{tenant_id}:{agent_id}"):
                tenant_conflict_stats[scope_key] = stats

        combined_stats["tenant_specific"] = {
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "memory_chests": tenant_memory_stats,
            "conflict_trackers": tenant_conflict_stats,
        }

    return combined_stats


def cleanup_tenant_resources(tenant_id: str) -> bool:
    """清理租户资源"""
    try:
        clear_isolated_memory_chest(tenant_id)
        clear_isolated_conflict_tracker(tenant_id)
        logger.info(f"已清理租户 {tenant_id} 的所有记忆系统资源")
        return True

    except Exception as e:
        logger.error(f"清理租户资源时出错: {e}")
        return False


def get_tenant_memory_info(tenant_id: str, agent_id: str) -> Dict[str, Any]:
    """获取租户记忆信息"""
    try:
        memory_chest = get_isolated_memory_chest_simple(tenant_id, agent_id)
        conflict_tracker = get_isolated_conflict_tracker_simple(tenant_id, agent_id)

        memory_info = memory_chest.get_memory_statistics()
        conflict_info = conflict_tracker.get_conflict_statistics()
        isolation_info = memory_chest.get_isolation_info()

        return {
            "isolation_info": isolation_info,
            "memory_statistics": memory_info,
            "conflict_statistics": conflict_info,
        }

    except Exception as e:
        logger.error(f"获取租户记忆信息时出错: {e}")
        return {}


# 系统管理函数
async def system_health_check() -> Dict[str, Any]:
    """系统健康检查"""
    try:
        memory_stats = get_memory_system_stats()
        conflict_stats = get_conflict_system_stats()

        health_status = {
            "overall_health": "healthy",
            "memory_system": {
                "active_instances": memory_stats.get("active_instances", 0),
                "status": "healthy" if memory_stats.get("active_instances", 0) < 100 else "warning",
            },
            "conflict_system": {
                "active_instances": conflict_stats.get("active_instances", 0),
                "status": "healthy" if conflict_stats.get("active_instances", 0) < 100 else "warning",
            },
            "recommendations": [],
        }

        # 生成建议
        if memory_stats.get("active_instances", 0) > 50:
            health_status["recommendations"].append("记忆系统实例较多，考虑清理非活跃租户")

        if conflict_stats.get("active_instances", 0) > 50:
            health_status["recommendations"].append("冲突跟踪器实例较多，考虑清理非活跃租户")

        # 更新整体健康状态
        if (
            health_status["memory_system"]["status"] == "warning"
            or health_status["conflict_system"]["status"] == "warning"
        ):
            health_status["overall_health"] = "warning"

        return health_status

    except Exception as e:
        logger.error(f"系统健康检查时出错: {e}")
        return {"overall_health": "error", "error": str(e), "recommendations": ["检查系统日志以了解详情"]}


async def cleanup_all_expired_memories(max_age_days: int = 30) -> Dict[str, int]:
    """清理所有过期记忆"""
    try:
        memory_stats = get_memory_system_stats()
        cleanup_results = {}

        for scope_key, _stats in memory_stats.get("memory_chests", {}).items():
            try:
                # 解析scope_key以获取租户和智能体信息
                parts = scope_key.split(":")
                if len(parts) >= 2:
                    tenant_id, agent_id = parts[0], parts[1]
                    platform = parts[2] if len(parts) > 2 else None

                    memory_chest = get_isolated_memory_chest_simple(tenant_id, agent_id, platform)
                    count = await memory_chest.cleanup_expired_memories(max_age_days)
                    cleanup_results[scope_key] = count

            except Exception as e:
                logger.warning(f"清理租户 {scope_key} 的过期记忆时出错: {e}")
                cleanup_results[scope_key] = 0

        total_cleaned = sum(cleanup_results.values())
        logger.info(f"全局清理过期记忆完成: {total_cleaned} 条")

        return {"total_cleaned": total_cleaned, "tenant_results": cleanup_results}

    except Exception as e:
        logger.error(f"全局清理过期记忆时出错: {e}")
        return {"total_cleaned": 0, "error": str(e)}
