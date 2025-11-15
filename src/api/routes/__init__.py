"""
API路由模块

提供隔离化的API路由，包括聊天、智能体管理、统计等功能。
"""

from .isolated_chat_api import router as isolated_chat_router

__all__ = ["isolated_chat_router"]
