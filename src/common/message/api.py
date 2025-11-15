import os
from maim_message import MessageServer, TenantMessageServer
from src.common.logger import get_logger

global_api = None


def get_global_api() -> MessageServer:  # sourcery skip: extract-method
    """获取全局MessageServer实例（使用租户模式）"""
    global global_api
    if global_api is None:
        # 强制使用租户模式
        port = int(os.environ.get("PORT", "8095"))
        host = os.environ.get("HOST", "0.0.0.0")

        logger = get_logger(__name__)
        logger.info(f"正在初始化租户模式消息服务器: {host}:{port}")

        # 创建租户消息服务器
        global_api = TenantMessageServer(host=host, port=port)

        logger.info("租户模式消息服务器初始化完成")
    return global_api
