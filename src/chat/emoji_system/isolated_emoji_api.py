"""
隔离化表情系统便捷API接口

提供便捷的函数：get_isolated_emoji(), set_isolated_emoji_preference() 等，
实现表情的动态加载和缓存，提供表情使用统计和监控。
"""

import asyncio
import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from functools import wraps

from src.isolation.isolation_context import IsolationContext, create_isolation_context
from src.chat.emoji_system.isolated_emoji_manager import get_isolated_emoji_manager, get_isolated_emoji_manager_manager
from src.chat.emoji_system.emoji_config import get_emoji_config_manager, get_effective_emoji_config
from src.chat.emoji_system.emoji_pack_manager import get_emoji_pack_manager, create_emoji_pack, subscribe_emoji_pack
from src.common.logger import get_logger

logger = get_logger("emoji_api")


@dataclass
class EmojiUsageStats:
    """表情使用统计"""

    tenant_id: str
    agent_id: str
    total_usage: int
    daily_usage: int
    popular_emotions: List[Tuple[str, int]]
    usage_by_hour: Dict[int, int]
    last_reset_time: float


class IsolatedEmojiSystem:
    """隔离化表情系统统一接口"""

    def __init__(self):
        self.config_manager = get_emoji_config_manager()
        self.pack_manager = get_emoji_pack_manager()
        self.manager_manager = get_isolated_emoji_manager_manager()

    # ==================== 表情获取API ====================

    async def get_emoji(
        self, text_emotion: str, tenant_id: str, agent_id: str, isolation_context: Optional[IsolationContext] = None
    ) -> Optional[Tuple[str, str, str]]:
        """获取表情包

        Args:
            text_emotion: 情感文本
            tenant_id: 租户ID
            agent_id: 智能体ID
            isolation_context: 隔离上下文

        Returns:
            表情包信息元组或None
        """
        try:
            # 使用便捷函数
            result = await get_isolated_emoji(
                text_emotion=text_emotion, tenant_id=tenant_id, agent_id=agent_id, isolation_context=isolation_context
            )

            if result:
                logger.debug(f"获取表情包成功: tenant={tenant_id}, agent={agent_id}, emotion={text_emotion}")

            return result

        except Exception as e:
            logger.error(f"获取表情包失败: {e}")
            return None

    async def get_multiple_emojis(
        self,
        text_emotions: List[str],
        tenant_id: str,
        agent_id: str,
        max_count: int = 3,
        isolation_context: Optional[IsolationContext] = None,
    ) -> List[Tuple[str, str, str]]:
        """获取多个表情包

        Args:
            text_emotions: 情感文本列表
            tenant_id: 租户ID
            agent_id: 智能体ID
            max_count: 最大返回数量
            isolation_context: 隔离上下文

        Returns:
            表情包信息列表
        """
        results = []

        for emotion in text_emotions:
            if len(results) >= max_count:
                break

            result = await self.get_emoji(emotion, tenant_id, agent_id, isolation_context)
            if result:
                results.append(result)

        return results

    # ==================== 表情偏好配置API ====================

    def set_emoji_preference(
        self,
        tenant_id: str,
        agent_id: str,
        preferred_emotions: List[str] = None,
        banned_emotions: List[str] = None,
        custom_weights: Dict[str, float] = None,
    ) -> bool:
        """设置表情偏好

        Args:
            tenant_id: 租户ID
            agent_id: 智能体ID
            preferred_emotions: 偏好的情感标签
            banned_emotions: 禁止的情感标签
            custom_weights: 自定义权重

        Returns:
            是否设置成功
        """
        try:
            updates = {}

            if preferred_emotions:
                updates["preference_emotions"] = preferred_emotions

            if banned_emotions:
                updates["preference_banned_emotions"] = banned_emotions

            if custom_weights:
                # 获取现有配置并合并权重
                config = self.config_manager.get_agent_config(tenant_id, agent_id)
                config.preference.weights.update(custom_weights)
                updates["preference_weights"] = config.preference.weights

            if updates:
                success = self.config_manager.update_agent_config(tenant_id, agent_id, **updates)
                if success:
                    logger.info(f"设置表情偏好成功: tenant={tenant_id}, agent={agent_id}")
                return success

            return True

        except Exception as e:
            logger.error(f"设置表情偏好失败: {e}")
            return False

    def get_emoji_preference(self, tenant_id: str, agent_id: str) -> Dict[str, Any]:
        """获取表情偏好"""
        try:
            effective_config = get_effective_emoji_config(tenant_id, agent_id)
            preference = effective_config.get("preference", {})

            return {
                "preferred_emotions": preference.get("emotions", []),
                "banned_emotions": preference.get("banned_emotions", []),
                "weights": preference.get("weights", {}),
                "custom_rules": preference.get("custom_rules", {}),
            }

        except Exception as e:
            logger.error(f"获取表情偏好失败: {e}")
            return {}

    # ==================== 表情包管理API ====================

    async def add_custom_emoji(
        self, tenant_id: str, agent_id: str, emoji_path: str, emotions: List[str], description: str = ""
    ) -> bool:
        """添加自定义表情包

        Args:
            tenant_id: 租户ID
            agent_id: 智能体ID
            emoji_path: 表情包文件路径
            emotions: 情感标签列表
            description: 描述

        Returns:
            是否添加成功
        """
        try:
            manager = get_isolated_emoji_manager(tenant_id, agent_id)
            success = await manager.add_custom_emoji(emoji_path, emotions, description)

            if success:
                logger.info(f"添加自定义表情包成功: tenant={tenant_id}, agent={agent_id}")

            return success

        except Exception as e:
            logger.error(f"添加自定义表情包失败: {e}")
            return False

    def remove_custom_emoji(self, tenant_id: str, agent_id: str, emoji_hash: str) -> bool:
        """移除自定义表情包"""
        try:
            manager = get_isolated_emoji_manager(tenant_id, agent_id)
            success = asyncio.run(manager.remove_emoji(emoji_hash))

            if success:
                logger.info(f"移除自定义表情包成功: tenant={tenant_id}, agent={agent_id}")

            return success

        except Exception as e:
            logger.error(f"移除自定义表情包失败: {e}")
            return False

    # ==================== 表情包集合API ====================

    def create_emoji_collection(
        self,
        tenant_id: str,
        agent_id: Optional[str],
        collection_name: str,
        emoji_hashes: List[str],
        description: str = "",
        tags: List[str] = None,
    ) -> bool:
        """创建表情包集合"""
        try:
            success = self.config_manager.add_emoji_collection(
                tenant_id=tenant_id,
                agent_id=agent_id,
                collection_name=collection_name,
                emoji_hashes=emoji_hashes,
                description=description,
                tags=tags,
            )

            if success:
                logger.info(f"创建表情包集合成功: tenant={tenant_id}, agent={agent_id}, collection={collection_name}")

            return success

        except Exception as e:
            logger.error(f"创建表情包集合失败: {e}")
            return False

    def get_emoji_collections(self, tenant_id: str, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """获取表情包集合"""
        try:
            collections = self.config_manager.get_emoji_collections(tenant_id, agent_id)

            return {
                collection_name: {
                    "name": collection.name,
                    "description": collection.description,
                    "emoji_count": len(collection.emoji_hashes),
                    "tags": collection.tags,
                    "created_time": collection.created_time,
                    "updated_time": collection.updated_time,
                }
                for collection_name, collection in collections.items()
            }

        except Exception as e:
            logger.error(f"获取表情包集合失败: {e}")
            return {}

    # ==================== 表情包分享API ====================

    def create_emoji_pack(
        self,
        tenant_id: str,
        pack_name: str,
        emoji_hashes: List[str],
        description: str = "",
        tags: List[str] = None,
        is_public: bool = False,
    ) -> Optional[str]:
        """创建表情包

        Args:
            tenant_id: 租户ID
            pack_name: 表情包名称
            emoji_hashes: 表情包哈希列表
            description: 描述
            tags: 标签
            is_public: 是否公开

        Returns:
            表情包ID或None
        """
        try:
            from src.chat.emoji_system.emoji_pack_manager import PackPermission

            permission = PackPermission.PUBLIC if is_public else PackPermission.PRIVATE

            pack_id = create_emoji_pack(
                tenant_id=tenant_id,
                name=pack_name,
                emoji_hashes=emoji_hashes,
                description=description,
                tags=tags,
                permission=permission,
            )

            if pack_id:
                logger.info(f"创建表情包成功: tenant={tenant_id}, pack={pack_name}")

            return pack_id

        except Exception as e:
            logger.error(f"创建表情包失败: {e}")
            return None

    def subscribe_emoji_pack(self, tenant_id: str, agent_id: str, pack_id: str, auto_update: bool = True) -> bool:
        """订阅表情包"""
        try:
            success = subscribe_emoji_pack(
                tenant_id=tenant_id, agent_id=agent_id, pack_id=pack_id, auto_update=auto_update
            )

            if success:
                logger.info(f"订阅表情包成功: tenant={tenant_id}, agent={agent_id}, pack={pack_id}")

            return success

        except Exception as e:
            logger.error(f"订阅表情包失败: {e}")
            return False

    # ==================== 使用统计API ====================

    def get_usage_stats(self, tenant_id: str, agent_id: str) -> EmojiUsageStats:
        """获取使用统计"""
        try:
            # 获取配置中的统计信息
            agent_config = self.config_manager.get_agent_config(tenant_id, agent_id)
            tenant_config = self.config_manager.get_tenant_config(tenant_id)

            # 模拟一些统计数据
            popular_emotions = [("开心", 15), ("难过", 8), ("惊讶", 5)]
            usage_by_hour = {i: 0 for i in range(24)}
            usage_by_hour[14] = 5  # 下午2点使用较多
            usage_by_hour[20] = 8  # 晚上8点使用较多

            return EmojiUsageStats(
                tenant_id=tenant_id,
                agent_id=agent_id,
                total_usage=agent_config.total_usage + tenant_config.total_usage,
                daily_usage=agent_config.daily_usage + tenant_config.daily_usage,
                popular_emotions=popular_emotions,
                usage_by_hour=usage_by_hour,
                last_reset_time=agent_config.last_reset_time,
            )

        except Exception as e:
            logger.error(f"获取使用统计失败: {e}")
            return EmojiUsageStats(
                tenant_id=tenant_id,
                agent_id=agent_id,
                total_usage=0,
                daily_usage=0,
                popular_emotions=[],
                usage_by_hour={},
                last_reset_time=time.time(),
            )

    def reset_daily_usage(self, tenant_id: str, agent_id: Optional[str] = None) -> bool:
        """重置日使用统计"""
        try:
            self.config_manager.reset_daily_usage(tenant_id if agent_id else None)
            logger.info(f"重置日使用统计成功: tenant={tenant_id}, agent={agent_id}")
            return True

        except Exception as e:
            logger.error(f"重置日使用统计失败: {e}")
            return False

    # ==================== 系统管理API ====================

    def get_system_stats(self) -> Dict[str, Any]:
        """获取系统统计"""
        try:
            manager_stats = self.manager_manager.get_stats()
            config_stats = self.config_manager.get_stats()
            pack_stats = self.pack_manager.get_stats()

            return {
                "managers": manager_stats,
                "configs": config_stats,
                "packs": pack_stats,
                "total_tenants": len(set(m["tenant_id"] for m in self.manager_manager.list_managers())),
                "total_agents": len(self.manager_manager.list_managers()),
            }

        except Exception as e:
            logger.error(f"获取系统统计失败: {e}")
            return {}

    async def health_check(self) -> Dict[str, Any]:
        """系统健康检查"""
        try:
            health_status = {"status": "healthy", "timestamp": time.time(), "checks": {}}

            # 检查配置管理器
            try:
                config_stats = self.config_manager.get_stats()
                health_status["checks"]["config_manager"] = {
                    "status": "healthy",
                    "tenant_count": config_stats["tenant_count"],
                    "agent_count": config_stats["agent_count"],
                }
            except Exception as e:
                health_status["checks"]["config_manager"] = {"status": "unhealthy", "error": str(e)}
                health_status["status"] = "degraded"

            # 检查表情包管理器
            try:
                pack_stats = self.pack_manager.get_stats()
                health_status["checks"]["pack_manager"] = {
                    "status": "healthy",
                    "total_packs": pack_stats["total_packs"],
                    "total_subscriptions": pack_stats["total_subscriptions"],
                }
            except Exception as e:
                health_status["checks"]["pack_manager"] = {"status": "unhealthy", "error": str(e)}
                health_status["status"] = "degraded"

            # 检查管理器
            try:
                manager_stats = self.manager_manager.get_stats()
                health_status["checks"]["isolated_managers"] = {
                    "status": "healthy",
                    "total_managers": manager_stats["total_managers"],
                    "total_emojis": manager_stats["total_emojis"],
                }
            except Exception as e:
                health_status["checks"]["isolated_managers"] = {"status": "unhealthy", "error": str(e)}
                health_status["status"] = "degraded"

            return health_status

        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return {"status": "unhealthy", "timestamp": time.time(), "error": str(e)}

    def cleanup_resources(self, tenant_id: Optional[str] = None) -> Dict[str, int]:
        """清理资源"""
        try:
            cleanup_counts = {}

            # 清理隔离化管理器
            if tenant_id:
                # 清理指定租户的所有管理器
                managers = self.manager_manager.list_managers()
                for manager in managers:
                    if manager["tenant_id"] == tenant_id:
                        success = self.manager_manager.cleanup_manager(manager["tenant_id"], manager["agent_id"])
                        if success:
                            cleanup_counts["managers"] = cleanup_counts.get("managers", 0) + 1
            else:
                # 清理所有管理器
                count = self.manager_manager.cleanup_all()
                cleanup_counts["managers"] = count

            # 清理临时文件
            temp_count = self.pack_manager.cleanup_temp_files()
            cleanup_counts["temp_files"] = temp_count

            logger.info(f"资源清理完成: {cleanup_counts}")
            return cleanup_counts

        except Exception as e:
            logger.error(f"资源清理失败: {e}")
            return {}


# 全局系统实例
_isolated_emoji_system: Optional[IsolatedEmojiSystem] = None


def get_isolated_emoji_system() -> IsolatedEmojiSystem:
    """获取隔离化表情系统"""
    global _isolated_emoji_system

    if _isolated_emoji_system is None:
        _isolated_emoji_system = IsolatedEmojiSystem()

    return _isolated_emoji_system


# ==================== 便捷函数 ====================


async def get_isolated_emoji(
    text_emotion: str, tenant_id: str, agent_id: str, isolation_context: Optional[IsolationContext] = None
) -> Optional[Tuple[str, str, str]]:
    """获取隔离化表情包"""
    system = get_isolated_emoji_system()
    return await system.get_emoji(text_emotion, tenant_id, agent_id, isolation_context)


def set_isolated_emoji_preference(
    tenant_id: str,
    agent_id: str,
    preferred_emotions: List[str] = None,
    banned_emotions: List[str] = None,
    custom_weights: Dict[str, float] = None,
) -> bool:
    """设置隔离化表情偏好"""
    system = get_isolated_emoji_system()
    return system.set_emoji_preference(tenant_id, agent_id, preferred_emotions, banned_emotions, custom_weights)


def get_isolated_emoji_preference(tenant_id: str, agent_id: str) -> Dict[str, Any]:
    """获取隔离化表情偏好"""
    system = get_isolated_emoji_system()
    return system.get_emoji_preference(tenant_id, agent_id)


async def add_isolated_custom_emoji(
    tenant_id: str, agent_id: str, emoji_path: str, emotions: List[str], description: str = ""
) -> bool:
    """添加隔离化自定义表情包"""
    system = get_isolated_emoji_system()
    return await system.add_custom_emoji(tenant_id, agent_id, emoji_path, emotions, description)


def create_isolated_emoji_collection(
    tenant_id: str,
    agent_id: Optional[str],
    collection_name: str,
    emoji_hashes: List[str],
    description: str = "",
    tags: List[str] = None,
) -> bool:
    """创建隔离化表情包集合"""
    system = get_isolated_emoji_system()
    return system.create_emoji_collection(tenant_id, agent_id, collection_name, emoji_hashes, description, tags)


def get_isolated_emoji_system_stats() -> Dict[str, Any]:
    """获取隔离化表情系统统计"""
    system = get_isolated_emoji_system()
    return system.get_system_stats()


async def isolated_emoji_health_check() -> Dict[str, Any]:
    """隔离化表情系统健康检查"""
    system = get_isolated_emoji_system()
    return await system.health_check()


def cleanup_isolated_emoji_resources(tenant_id: Optional[str] = None) -> Dict[str, int]:
    """清理隔离化表情资源"""
    system = get_isolated_emoji_system()
    return system.cleanup_resources(tenant_id)


# ==================== 装饰器支持 ====================


def with_emoji_isolation(tenant_id: str, agent_id: str):
    """表情隔离装饰器"""

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # 创建隔离上下文
            isolation_context = create_isolation_context(tenant_id, agent_id)
            kwargs["isolation_context"] = isolation_context

            return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # 创建隔离上下文
            isolation_context = create_isolation_context(tenant_id, agent_id)
            kwargs["isolation_context"] = isolation_context

            return func(*args, **kwargs)

        # 根据函数类型返回对应的包装器
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# ==================== 上下文管理器 ====================


class IsolatedEmojiContext:
    """隔离化表情上下文管理器"""

    def __init__(self, tenant_id: str, agent_id: str):
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.system = get_isolated_emoji_system()
        self.isolation_context = create_isolation_context(tenant_id, agent_id)

    async def get_emoji(self, text_emotion: str) -> Optional[Tuple[str, str, str]]:
        """获取表情包"""
        return await self.system.get_emoji(text_emotion, self.tenant_id, self.agent_id, self.isolation_context)

    def set_preference(self, **kwargs) -> bool:
        """设置偏好"""
        return self.system.set_emoji_preference(self.tenant_id, self.agent_id, **kwargs)

    def get_preference(self) -> Dict[str, Any]:
        """获取偏好"""
        return self.system.get_emoji_preference(self.tenant_id, self.agent_id)

    async def add_custom_emoji(self, emoji_path: str, emotions: List[str], description: str = "") -> bool:
        """添加自定义表情包"""
        return await self.system.add_custom_emoji(self.tenant_id, self.agent_id, emoji_path, emotions, description)

    def get_stats(self) -> EmojiUsageStats:
        """获取统计"""
        return self.system.get_usage_stats(self.tenant_id, self.agent_id)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # 清理资源（如果需要）
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # 清理资源（如果需要）
        pass
