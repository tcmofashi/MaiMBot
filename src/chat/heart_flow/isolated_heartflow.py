"""
隔离化的心流管理系统
支持T+A维度的多租户心流隔离，每个租户+智能体组合有独立的心流实例
"""

import traceback
from typing import Any, Optional, Dict
import threading

from src.chat.heart_flow.heartFC_chat import HeartFChatting
from src.chat.brain_chat.brain_chat import BrainChatting
from src.chat.heart_flow.isolated_heartFC_chat import IsolatedHeartFChatting
from src.chat.message_receive.chat_stream import get_isolated_chat_manager
from src.common.logger import get_logger
from src.isolation.isolation_context import create_isolation_context, get_isolation_context_manager

logger = get_logger("isolated_heartflow")


class IsolatedHeartflow:
    """
    隔离化的心流协调器，负责管理特定租户+智能体组合的心流实例
    """

    def __init__(self, tenant_id: str, agent_id: str):
        """
        初始化隔离化的心流管理器

        Args:
            tenant_id: 租户标识
            agent_id: 智能体标识
        """
        self.tenant_id = tenant_id
        self.agent_id = agent_id

        # 创建隔离上下文
        self.isolation_context = create_isolation_context(tenant_id=tenant_id, agent_id=agent_id)

        # 心流聊天实例缓存，按chat_id存储
        self.heartflow_chat_list: Dict[str, HeartFChatting | BrainChatting | IsolatedHeartFChatting] = {}

        # 线程安全锁
        self._lock = threading.RLock()

    async def get_or_create_heartflow_chat(
        self, chat_id: str
    ) -> Optional[HeartFChatting | BrainChatting | IsolatedHeartFChatting]:
        """
        获取或创建一个新的隔离化心流聊天实例

        Args:
            chat_id: 聊天流唯一标识符

        Returns:
            心流聊天实例或None
        """
        try:
            with self._lock:
                # 检查是否已存在实例
                if chat_id in self.heartflow_chat_list:
                    chat_instance = self.heartflow_chat_list.get(chat_id)
                    if chat_instance:
                        return chat_instance

                # 获取隔离化的聊天管理器
                chat_manager = get_isolated_chat_manager(self.tenant_id, self.agent_id)
                chat_stream = chat_manager.get_stream(chat_id)

                if not chat_stream:
                    raise ValueError(f"未找到 chat_id={chat_id} 的聊天流")

                # 创建带隔离上下文的心流聊天实例
                isolated_context = self.isolation_context.create_sub_context(
                    platform=chat_stream.platform, chat_stream_id=chat_id
                )

                if chat_stream.group_info:
                    # 群聊使用隔离化的HeartFChatting
                    new_chat = IsolatedHeartFChatting(chat_id=chat_id, isolation_context=isolated_context)
                else:
                    # 私聊仍使用原有的BrainChatting（后续可以隔离化）
                    new_chat = BrainChatting(chat_id=chat_id)

                # 启动聊天实例
                await new_chat.start()

                # 缓存实例
                self.heartflow_chat_list[chat_id] = new_chat

                logger.info(f"[隔离心流] 创建心流聊天成功: {self.tenant_id}:{self.agent_id}:{chat_id}")
                return new_chat

        except Exception as e:
            logger.error(f"[隔离心流] 创建心流聊天 {chat_id} 失败: {e}", exc_info=True)
            traceback.print_exc()
            return None

    def remove_heartflow_chat(self, chat_id: str) -> bool:
        """
        移除指定的心流聊天实例

        Args:
            chat_id: 聊天流ID

        Returns:
            是否成功移除
        """
        try:
            with self._lock:
                if chat_id in self.heartflow_chat_list:
                    chat_instance = self.heartflow_chat_list.pop(chat_id)
                    # 如果聊天实例有清理方法，调用清理
                    if hasattr(chat_instance, "cleanup"):
                        try:
                            if hasattr(chat_instance.cleanup, "__await__"):
                                # 异步方法
                                import asyncio

                                asyncio.create_task(chat_instance.cleanup())
                            else:
                                # 同步方法
                                chat_instance.cleanup()
                        except Exception as e:
                            logger.warning(f"[隔离心流] 清理聊天实例失败: {e}")

                    logger.info(f"[隔离心流] 移除心流聊天: {self.tenant_id}:{self.agent_id}:{chat_id}")
                    return True
                return False
        except Exception as e:
            logger.error(f"[隔离心流] 移除心流聊天失败: {e}")
            return False

    def get_chat_count(self) -> int:
        """获取当前管理的心流聊天数量"""
        with self._lock:
            return len(self.heartflow_chat_list)

    def get_active_chat_ids(self) -> list:
        """获取活跃的聊天ID列表"""
        with self._lock:
            return list(self.heartflow_chat_list.keys())

    def clear_all_chats(self):
        """清理所有心流聊天实例"""
        try:
            with self._lock:
                chat_ids = list(self.heartflow_chat_list.keys())
                for chat_id in chat_ids:
                    self.remove_heartflow_chat(chat_id)

                logger.info(f"[隔离心流] 清理所有心流聊天: {self.tenant_id}:{self.agent_id}")
        except Exception as e:
            logger.error(f"[隔离心流] 清理所有心流聊天失败: {e}")

    def get_isolation_info(self) -> Dict[str, Any]:
        """获取隔离信息"""
        return {
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "chat_count": self.get_chat_count(),
            "active_chat_ids": self.get_active_chat_ids(),
            "isolation_level": self.isolation_context.get_isolation_level().value,
            "scope": str(self.isolation_context.scope),
        }

    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        health_info = {"status": "healthy", "isolation_info": self.get_isolation_info(), "chat_instances": []}

        with self._lock:
            for chat_id, chat_instance in self.heartflow_chat_list.items():
                chat_info = {"chat_id": chat_id, "running": getattr(chat_instance, "running", "unknown")}
                health_info["chat_instances"].append(chat_info)

        return health_info


class IsolatedHeartflowManager:
    """隔离化心流管理器，管理多个租户+智能体的心流实例"""

    def __init__(self):
        self._heartflows: Dict[str, IsolatedHeartflow] = {}
        self._context_manager = get_isolation_context_manager()
        self._lock = threading.RLock()

    def get_heartflow(self, tenant_id: str, agent_id: str) -> IsolatedHeartflow:
        """获取或创建隔离化的心流管理器"""
        key = f"{tenant_id}:{agent_id}"

        with self._lock:
            if key not in self._heartflows:
                self._heartflows[key] = IsolatedHeartflow(tenant_id, agent_id)

            return self._heartflows[key]

    def clear_tenant_heartflows(self, tenant_id: str):
        """清理指定租户的所有心流管理器"""
        with self._lock:
            keys_to_remove = []
            for key in self._heartflows:
                if key.startswith(f"{tenant_id}:"):
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                heartflow = self._heartflows.pop(key)
                heartflow.clear_all_chats()

            logger.info(f"[隔离心流] 清理租户心流: {tenant_id}")

    def clear_all_heartflows(self):
        """清理所有心流管理器"""
        with self._lock:
            for heartflow in self._heartflows.values():
                heartflow.clear_all_chats()

            self._heartflows.clear()
            logger.info("[隔离心流] 清理所有心流管理器")

    def get_heartflow_count(self) -> int:
        """获取心流管理器数量"""
        with self._lock:
            return len(self._heartflows)

    def list_active_tenants(self) -> list:
        """列出活跃的租户"""
        with self._lock:
            tenants = set()
            for key in self._heartflows:
                tenant_id = key.split(":")[0]
                tenants.add(tenant_id)
            return list(tenants)

    async def global_health_check(self) -> Dict[str, Any]:
        """全局健康检查"""
        health_info = {
            "status": "healthy",
            "heartflow_count": self.get_heartflow_count(),
            "active_tenants": self.list_active_tenants(),
            "heartflows": {},
        }

        with self._lock:
            for key, heartflow in self._heartflows.items():
                try:
                    heartflow_health = await heartflow.health_check()
                    health_info["heartflows"][key] = heartflow_health
                except Exception as e:
                    health_info["heartflows"][key] = {"status": "error", "error": str(e)}

        return health_info

    def get_manager_stats(self) -> Dict[str, Any]:
        """获取管理器统计信息"""
        with self._lock:
            stats = {
                "heartflow_count": len(self._heartflows),
                "total_chat_count": 0,
                "active_tenants": set(),
                "tenant_agent_pairs": [],
            }

            for key, heartflow in self._heartflows.items():
                tenant_id, agent_id = key.split(":")
                stats["total_chat_count"] += heartflow.get_chat_count()
                stats["active_tenants"].add(tenant_id)
                stats["tenant_agent_pairs"].append(
                    {"tenant_id": tenant_id, "agent_id": agent_id, "chat_count": heartflow.get_chat_count()}
                )

            stats["active_tenants"] = list(stats["active_tenants"])
            return stats


# 全局隔离化心流管理器实例
_isolated_heartflow_manager = IsolatedHeartflowManager()


def get_isolated_heartflow(tenant_id: str, agent_id: str) -> IsolatedHeartflow:
    """获取隔离化心流管理器的便捷函数"""
    return _isolated_heartflow_manager.get_heartflow(tenant_id, agent_id)


def get_isolated_heartflow_manager() -> IsolatedHeartflowManager:
    """获取隔离化心流管理器"""
    return _isolated_heartflow_manager


def clear_isolated_heartflows(tenant_id: str = None):
    """清理隔离化心流管理器"""
    if tenant_id:
        _isolated_heartflow_manager.clear_tenant_heartflows(tenant_id)
    else:
        _isolated_heartflow_manager.clear_all_heartflows()


async def isolated_heartflow_health_check() -> Dict[str, Any]:
    """隔离化心流全局健康检查"""
    return await _isolated_heartflow_manager.global_health_check()


def get_isolated_heartflow_stats() -> Dict[str, Any]:
    """获取隔离化心流统计信息"""
    return _isolated_heartflow_manager.get_manager_stats()


async def get_or_create_heartflow_chat(
    tenant_id: str, agent_id: str, chat_id: str
) -> Optional[HeartFChatting | BrainChatting | IsolatedHeartFChatting]:
    """
    获取或创建隔离化心流聊天的便捷函数

    Args:
        tenant_id: 租户标识
        agent_id: 智能体标识
        chat_id: 聊天流唯一标识符

    Returns:
        心流聊天实例或None
    """
    heartflow = get_isolated_heartflow(tenant_id, agent_id)
    return await heartflow.get_or_create_heartflow_chat(chat_id)
