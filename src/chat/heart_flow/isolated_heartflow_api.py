"""
隔离化心流处理系统便捷API
提供简单易用的接口来使用多租户隔离的心流处理功能
"""

from typing import Dict, Any, Optional
from src.chat.heart_flow.heartflow_message_processor import (
    IsolatedHeartFCMessageReceiver,
    get_isolated_heartfc_receiver,
    get_isolated_receiver_manager,
)
from src.chat.heart_flow.isolated_heartflow import (
    IsolatedHeartflow,
    get_isolated_heartflow,
    isolated_heartflow_health_check,
    get_isolated_heartflow_stats,
)
from src.chat.heart_flow.isolated_heartFC_chat import IsolatedHeartFChatting
from src.isolation.isolation_context import create_isolation_context, get_isolation_context_manager
from src.chat.message_receive.message import MessageRecv


class IsolatedHeartFlowAPI:
    """
    隔离化心流处理系统API
    提供高级封装的便捷接口
    """

    @staticmethod
    def create_heartflow_processor(tenant_id: str, agent_id: str) -> IsolatedHeartFCMessageReceiver:
        """
        创建隔离化的心流消息处理器

        Args:
            tenant_id: 租户标识
            agent_id: 智能体标识

        Returns:
            隔离化的心流消息处理器
        """
        return get_isolated_heartfc_receiver(tenant_id, agent_id)

    @staticmethod
    def create_heartflow_manager(tenant_id: str, agent_id: str) -> IsolatedHeartflow:
        """
        创建隔离化的心流管理器

        Args:
            tenant_id: 租户标识
            agent_id: 智能体标识

        Returns:
            隔离化的心流管理器
        """
        return get_isolated_heartflow(tenant_id, agent_id)

    @staticmethod
    def create_isolation_context(tenant_id: str, agent_id: str, platform: str = None, chat_stream_id: str = None):
        """
        创建隔离上下文

        Args:
            tenant_id: 租户标识
            agent_id: 智能体标识
            platform: 平台标识（可选）
            chat_stream_id: 聊天流标识（可选）

        Returns:
            隔离上下文
        """
        return create_isolation_context(tenant_id, agent_id, platform, chat_stream_id)

    @staticmethod
    async def process_message_with_isolation(message: MessageRecv, tenant_id: str, agent_id: str) -> bool:
        """
        使用隔离上下文处理消息

        Args:
            message: 消息对象
            tenant_id: 租户标识
            agent_id: 智能体标识

        Returns:
            是否处理成功
        """
        try:
            # 为消息添加隔离信息（如果支持的话）
            if hasattr(message, "tenant_id"):
                message.tenant_id = tenant_id
            if hasattr(message, "agent_id"):
                message.agent_id = agent_id

            # 获取隔离化处理器并处理消息
            receiver = get_isolated_heartfc_receiver(tenant_id, agent_id)
            await receiver.process_message(message)

            return True
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"隔离化消息处理失败: {e}")
            return False

    @staticmethod
    async def create_isolated_chat(
        chat_id: str, tenant_id: str, agent_id: str, platform: str = None
    ) -> Optional[IsolatedHeartFChatting]:
        """
        创建隔离化的心流聊天

        Args:
            chat_id: 聊天流ID
            tenant_id: 租户标识
            agent_id: 智能体标识
            platform: 平台标识

        Returns:
            隔离化的心流聊天实例或None
        """
        try:
            # 创建隔离上下文
            isolation_context = create_isolation_context(
                tenant_id=tenant_id, agent_id=agent_id, platform=platform, chat_stream_id=chat_id
            )

            # 创建隔离化聊天实例
            chat = IsolatedHeartFChatting(chat_id=chat_id, isolation_context=isolation_context)

            return chat
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"创建隔离化聊天失败: {e}")
            return None

    @staticmethod
    async def get_or_create_isolated_chat(
        chat_id: str, tenant_id: str, agent_id: str
    ) -> Optional[IsolatedHeartFChatting]:
        """
        获取或创建隔离化的心流聊天

        Args:
            chat_id: 聊天流ID
            tenant_id: 租户标识
            agent_id: 智能体标识

        Returns:
            隔离化的心流聊天实例或None
        """
        try:
            heartflow = get_isolated_heartflow(tenant_id, agent_id)
            chat = await heartflow.get_or_create_heartflow_chat(chat_id)
            return chat
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"获取或创建隔离化聊天失败: {e}")
            return None

    @staticmethod
    def get_system_stats() -> Dict[str, Any]:
        """
        获取系统统计信息

        Returns:
            统计信息字典
        """
        stats = get_isolated_heartflow_stats()

        # 添加更多统计信息
        receiver_manager = get_isolated_receiver_manager()
        context_manager = get_isolation_context_manager()

        stats.update(
            {
                "active_receivers": receiver_manager.get_receiver_count(),
                "active_contexts": context_manager.get_active_context_count(),
                "active_tenants_receivers": receiver_manager.list_active_tenants(),
            }
        )

        return stats

    @staticmethod
    async def system_health_check() -> Dict[str, Any]:
        """
        系统健康检查

        Returns:
            健康检查结果
        """
        return await isolated_heartflow_health_check()

    @staticmethod
    def cleanup_tenant_resources(tenant_id: str):
        """
        清理指定租户的资源

        Args:
            tenant_id: 租户标识
        """
        from src.chat.heart_flow.heartflow_message_processor import clear_isolated_heartfc_receivers
        from src.chat.heart_flow.isolated_heartflow import clear_isolated_heartflows

        clear_isolated_heartfc_receivers(tenant_id)
        clear_isolated_heartflows(tenant_id)

        # 清理上下文
        context_manager = get_isolation_context_manager()
        context_manager.clear_tenant_contexts(tenant_id)

    @staticmethod
    def cleanup_all_resources():
        """清理所有资源"""
        from src.chat.heart_flow.heartflow_message_processor import clear_isolated_heartfc_receivers
        from src.chat.heart_flow.isolated_heartflow import clear_isolated_heartflows

        clear_isolated_heartfc_receivers()
        clear_isolated_heartflows()

        # 清理所有上下文
        context_manager = get_isolation_context_manager()
        # 目前没有clear_all_contexts方法，但可以手动清理
        tenants = get_isolated_heartflow_stats().get("active_tenants", [])
        for tenant_id in tenants:
            context_manager.clear_tenant_contexts(tenant_id)

    @staticmethod
    def get_tenant_info(tenant_id: str, agent_id: str = None) -> Dict[str, Any]:
        """
        获取租户信息

        Args:
            tenant_id: 租户标识
            agent_id: 智能体标识（可选）

        Returns:
            租户信息字典
        """
        info = {
            "tenant_id": tenant_id,
        }

        if agent_id:
            # 获取特定智能体的信息
            try:
                receiver = get_isolated_heartfc_receiver(tenant_id, agent_id)
                heartflow = get_isolated_heartflow(tenant_id, agent_id)

                info.update(
                    {
                        "agent_id": agent_id,
                        "receiver_info": receiver.get_isolation_info(),
                        "heartflow_info": heartflow.get_isolation_info(),
                        "chat_count": heartflow.get_chat_count(),
                        "active_chat_ids": heartflow.get_active_chat_ids(),
                    }
                )
            except Exception as e:
                info["error"] = str(e)
        else:
            # 获取整个租户的信息
            try:
                receiver_manager = get_isolated_receiver_manager()
                stats = get_isolated_heartflow_stats()

                info.update(
                    {
                        "receiver_count": len(
                            [key for key in receiver_manager._receivers.keys() if key.startswith(f"{tenant_id}:")]
                        ),
                        "heartflows": [
                            key for key in stats.get("tenant_agent_pairs", []) if key.get("tenant_id") == tenant_id
                        ],
                    }
                )
            except Exception as e:
                info["error"] = str(e)

        return info


# 便捷函数，提供更简单的接口
def create_isolated_heartflow_processor(tenant_id: str, agent_id: str) -> IsolatedHeartFCMessageReceiver:
    """创建隔离化心流处理器的便捷函数"""
    return IsolatedHeartFlowAPI.create_heartflow_processor(tenant_id, agent_id)


async def process_isolated_message(message: MessageRecv, tenant_id: str, agent_id: str) -> bool:
    """处理隔离化消息的便捷函数"""
    return await IsolatedHeartFlowAPI.process_message_with_isolation(message, tenant_id, agent_id)


async def create_isolated_chat_instance(chat_id: str, tenant_id: str, agent_id: str, platform: str = None):
    """创建隔离化聊天实例的便捷函数"""
    return await IsolatedHeartFlowAPI.create_isolated_chat(chat_id, tenant_id, agent_id, platform)


def get_isolation_stats() -> Dict[str, Any]:
    """获取隔离系统统计的便捷函数"""
    return IsolatedHeartFlowAPI.get_system_stats()


async def isolation_health_check() -> Dict[str, Any]:
    """隔离系统健康检查的便捷函数"""
    return await IsolatedHeartFlowAPI.system_health_check()


def cleanup_tenant(tenant_id: str):
    """清理租户资源的便捷函数"""
    IsolatedHeartFlowAPI.cleanup_tenant_resources(tenant_id)


def cleanup_isolation_system():
    """清理整个隔离系统的便捷函数"""
    IsolatedHeartFlowAPI.cleanup_all_resources()


def get_tenant_isolation_info(tenant_id: str, agent_id: str = None) -> Dict[str, Any]:
    """获取租户隔离信息的便捷函数"""
    return IsolatedHeartFlowAPI.get_tenant_info(tenant_id, agent_id)
