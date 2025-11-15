"""
实例工厂注册模块

为多租户隔离架构注册各种实例类型的工厂函数。
解决"No factory registered for instance type"错误。
"""

from src.common.logger import get_logger
from src.core.global_instance_manager import get_global_instance_manager
from src.config.isolated_config_manager import get_isolated_config_manager
from src.chat.message_receive.chat_stream import get_chat_manager

logger = get_logger(__name__)


def register_config_manager_factory():
    """注册配置管理器工厂函数"""
    global_manager = get_global_instance_manager()

    def config_manager_factory(tenant_id: str, agent_id: str, chat_stream_id: str = None, **kwargs):
        """配置管理器工厂函数"""
        # 忽略未使用的参数
        _ = chat_stream_id, kwargs
        return get_isolated_config_manager(tenant_id, agent_id)

    global_manager.register_factory("config_manager", config_manager_factory)
    logger.info("注册配置管理器工厂函数成功")


def register_chat_manager_factory():
    """注册聊天管理器工厂函数"""
    global_manager = get_global_instance_manager()

    def chat_manager_factory(tenant_id: str, agent_id: str, chat_stream_id: str = None, **kwargs):
        """聊天管理器工厂函数"""
        # 忽略未使用的参数
        _ = tenant_id, agent_id, chat_stream_id, kwargs
        # 获取全局聊天管理器实例
        return get_chat_manager()

    global_manager.register_factory("chat_manager", chat_manager_factory)
    logger.info("注册聊天管理器工厂函数成功")


def register_all_instance_factories():
    """注册所有实例工厂函数"""
    try:
        register_config_manager_factory()
        register_chat_manager_factory()
        logger.info("所有实例工厂函数注册完成")
        return True
    except Exception as e:
        logger.error(f"注册实例工厂函数失败: {e}")
        return False


def register_instance_factory(instance_type: str, factory_func):
    """通用实例工厂注册函数"""
    try:
        global_manager = get_global_instance_manager()
        global_manager.register_factory(instance_type, factory_func)
        logger.info(f"注册实例工厂函数成功: {instance_type}")
        return True
    except Exception as e:
        logger.error(f"注册实例工厂函数失败 {instance_type}: {e}")
        return False


# 自动注册所有工厂函数
def auto_register_factories():
    """自动注册所有必要的工厂函数"""
    logger.info("开始自动注册实例工厂函数...")
    success = register_all_instance_factories()
    if success:
        logger.info("实例工厂函数自动注册成功")
    else:
        logger.error("实例工厂函数自动注册失败")
    return success
