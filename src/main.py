import asyncio
import time
from maim_message import TenantMessageServer as MessageServer

from src.common.remote import TelemetryHeartBeatTask
from src.manager.async_task_manager import async_task_manager
from src.chat.utils.statistic import OnlineTimeRecordTask, StatisticOutputTask
from src.chat.emoji_system.emoji_manager import get_emoji_manager
from src.chat.message_receive.chat_stream import get_chat_manager
from src.config.config import global_config
from src.agent.manager import get_agent_manager
from src.common.logger import get_logger
from src.common.server import get_global_server, Server
from src.mood.mood_manager import mood_manager
from src.chat.knowledge import lpmm_start_up
from src.memory_system.memory_management_task import MemoryManagementTask
from rich.traceback import install
# from src.api.main import start_api_server

# 导入新的插件管理器
from src.plugin_system.core.plugin_manager import plugin_manager

# 导入消息API和traceback模块
from src.common.message import get_global_api

# 导入多租户隔离架构的核心组件
from src.core.instance_manager_api import get_instance_manager_api
from src.isolation.isolation_context import create_isolation_context
from src.chat.message_receive.isolated_message_api import process_isolated_message

# 插件系统现在使用统一的插件加载器

install(extra_lines=3)

logger = get_logger("main")


class MainSystem:
    def __init__(self):
        # 使用消息API替代直接的FastAPI实例
        self.app: MessageServer = get_global_api()
        self.server: Server = get_global_server()

        # 初始化多租户实例管理器API
        self.instance_manager = get_instance_manager_api()

        # 设置默认租户和智能体ID
        self.default_tenant_id = "default"
        self.default_agent_id = "default"

        # 创建默认隔离上下文
        self.default_isolation_context = create_isolation_context(
            tenant_id=self.default_tenant_id, agent_id=self.default_agent_id, platform="unknown"
        )

    async def initialize(self):
        """初始化系统组件"""
        logger.info(f"正在唤醒{global_config.bot.nickname}......")

        # 初始化多租户隔离架构
        await self._initialize_isolation_architecture()

        agent_manager = get_agent_manager()
        agent_count = agent_manager.initialize()
        if agent_count:
            logger.info("已加载 %d 个 Agent 配置", agent_count)

        # 其他初始化任务
        await asyncio.gather(self._init_components())

        logger.info(f"""
--------------------------------
全部系统初始化完成，{global_config.bot.nickname}已成功唤醒
--------------------------------
如果想要自定义{global_config.bot.nickname}的功能,请查阅：https://docs.mai-mai.org/manual/usage/
或者遇到了问题，请访问我们的文档:https://docs.mai-mai.org/
--------------------------------
如果你想要编写或了解插件相关内容，请访问开发文档https://docs.mai-mai.org/develop/
--------------------------------
如果你需要查阅模型的消耗以及麦麦的统计数据，请访问根目录的maibot_statistics.html文件
""")

    async def _initialize_isolation_architecture(self):
        """初始化多租户隔离架构"""
        logger.info("正在初始化多租户隔离架构...")

        # 初始化默认租户的实例管理器
        await self.instance_manager.get_isolated_instance(
            instance_type="config_manager", tenant_id=self.default_tenant_id, agent_id=self.default_agent_id
        )

        # 初始化默认租户的聊天管理器
        await self.instance_manager.get_isolated_instance(
            instance_type="chat_manager", tenant_id=self.default_tenant_id, agent_id=self.default_agent_id
        )

        # 执行系统健康检查
        health_status = await self.instance_manager.batch_health_check()
        if health_status.total_count > 0:
            success_rate = health_status.success_rate
            if success_rate > 0.5:  # 成功率超过50%认为成功
                logger.info("多租户隔离架构初始化成功")
            else:
                logger.warning(f"多租户隔离架构初始化警告: 成功率 {success_rate:.2%}")
        else:
            logger.info("多租户隔离架构初始化完成，未发现实例（这是正常的）")

    async def _init_components(self):
        """初始化其他组件"""
        init_start_time = time.time()

        # 添加在线时间统计任务
        await async_task_manager.add_task(OnlineTimeRecordTask())

        # 添加统计信息输出任务
        await async_task_manager.add_task(StatisticOutputTask())

        # 添加遥测心跳任务
        await async_task_manager.add_task(TelemetryHeartBeatTask())

        # 启动API服务器
        # start_api_server()
        # logger.info("API服务器启动成功")

        # 启动LPMM
        lpmm_start_up()

        # 加载所有actions，包括默认的和插件的
        plugin_manager.load_all_plugins()

        # 初始化表情管理器
        get_emoji_manager().initialize()
        logger.info("表情包管理器初始化成功")

        # 启动情绪管理器
        if global_config.mood.enable_mood:
            await mood_manager.start()
            logger.info("情绪管理器初始化成功")

        # 初始化聊天管理器
        await get_chat_manager()._initialize()
        asyncio.create_task(get_chat_manager()._auto_save_task())

        logger.info("聊天管理器初始化成功")

        # 添加记忆管理任务
        await async_task_manager.add_task(MemoryManagementTask())
        logger.info("记忆管理任务已启动")

        # await asyncio.sleep(0.5) #防止logger输出飞了

        # 注册消息处理器 - 多租户隔离的消息处理
        self.app.register_message_handler(self._isolated_message_process)

        # 触发 ON_START 事件
        from src.plugin_system.core.events_manager import events_manager
        from src.plugin_system.base.component_types import EventType

        await events_manager.handle_mai_events(event_type=EventType.ON_START)
        # logger.info("已触发 ON_START 事件")
        try:
            init_time = int(1000 * (time.time() - init_start_time))
            logger.info(f"初始化完成，神经元放电{init_time}次")
        except Exception as e:
            logger.error(f"启动大脑和外部世界失败: {e}")
            raise

    async def _isolated_message_process(self, message_data):
        """
        多租户隔离消息处理器

        Args:
            message_data: 接收到的消息数据
        """
        # 使用隔离化消息处理
        result = await process_isolated_message(
            message_data,
            default_tenant_id=self.default_tenant_id,
            default_agent_id=self.default_agent_id,
            instance_manager=self.instance_manager,
        )

        if result.success:
            logger.debug(f"消息处理成功: {result.message}")
            return result.response
        else:
            logger.error(f"消息处理失败: {result.error}")
            raise Exception(f"消息处理失败: {result.error}")

    def schedule_tasks(self):
        """调度定时任务"""
        # 启动租户消息服务器（这会阻塞）
        logger.info("正在启动租户消息服务器...")
        self.app.run()

    async def _instance_management_task(self):
        """实例管理任务 - 定期清理和维护实例"""
        try:
            # 每小时执行一次实例清理
            while True:
                await asyncio.sleep(3600)  # 1小时

                try:
                    # 执行实例健康检查
                    health_result = await self.instance_manager.batch_health_check(tenant_id=self.default_tenant_id)

                    if not health_result.success_rate > 0.8:
                        logger.warning(f"实例健康检查警告: 成功率 {health_result.success_rate:.2%}")

                    # 清理过期实例（如果需要）
                    # await self.instance_manager.clear_expired_instances()

                except Exception as e:
                    logger.error(f"实例管理任务异常: {e}")

        except Exception as e:
            logger.error(f"实例管理任务启动失败: {e}")

    # async def forget_memory_task(self):
    #     """记忆遗忘任务"""
    #     while True:
    #         await asyncio.sleep(global_config.memory.forget_memory_interval)
    #         logger.info("[记忆遗忘] 开始遗忘记忆...")
    #         await self.hippocampus_manager.forget_memory(percentage=global_config.memory.memory_forget_percentage)  # type: ignore
    #         logger.info("[记忆遗忘] 记忆遗忘完成")


async def main():
    """主函数"""
    system = MainSystem()
    await system.initialize()
    system.schedule_tasks()


if __name__ == "__main__":
    asyncio.run(main())
