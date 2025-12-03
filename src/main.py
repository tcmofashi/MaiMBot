import asyncio
import time

# 从maim_message导入最新的API-Server组件
from maim_message.server import WebSocketServer as MessageServer

from src.common.remote import TelemetryHeartBeatTask
from src.manager.async_task_manager import async_task_manager
from src.chat.utils.statistic import OnlineTimeRecordTask, StatisticOutputTask
from src.chat.emoji_system.emoji_manager import get_emoji_manager
from src.chat.message_receive.chat_stream import get_chat_manager
from src.config.config import global_config
from src.agent.manager import get_isolated_agent_manager
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
from src.common.message import get_global_api, set_global_message_handler

# 导入多租户隔离架构的核心组件
from src.core.instance_manager_api import get_instance_manager_api
from src.isolation.isolation_context import create_isolation_context
from src.chat.message_receive.isolated_message_api import process_isolated_message

# 插件系统现在使用统一的插件加载器

install(extra_lines=3)

logger = get_logger("main")


class MainSystem:
    def __init__(self):
        # 初始化多租户实例管理器API
        self.instance_manager = get_instance_manager_api()

        # 设置默认租户和智能体ID
        self.default_tenant_id = "default"
        self.default_agent_id = "default"

        # 延迟初始化WebSocket服务器，需要在设置消息处理器之后
        self.app: MessageServer = None
        self.server: Server = get_global_server()

        # 创建默认隔离上下文
        self.default_isolation_context = create_isolation_context(
            tenant_id=self.default_tenant_id, agent_id=self.default_agent_id, platform="unknown"
        )

    async def initialize(self):
        """初始化系统组件"""
        logger.info(f"正在唤醒{global_config.bot.nickname}......")

        # 初始化多租户隔离架构
        await self._initialize_isolation_architecture()

        # 使用隔离化的Agent管理器
        isolated_agent_manager = get_isolated_agent_manager(self.default_tenant_id)
        agent_count = await isolated_agent_manager.initialize()
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

        # 检查是否在租户模式下需要禁用插件
        should_load_plugins = True
        try:
            # 检查插件配置
            plugin_config = global_config.plugin

            # 检查是否启用了插件系统
            if not plugin_config.enable_plugins:
                logger.info("插件系统已禁用，跳过插件加载")
                should_load_plugins = False
            # 检查是否在租户模式下禁用插件
            elif plugin_config.tenant_mode_disable_plugins:
                # 检查是否处于租户模式（通过检查是否有隔离架构）
                if hasattr(self, "instance_manager") and self.instance_manager is not None:
                    logger.info("检测到租户模式，根据配置禁用插件加载")
                    should_load_plugins = False
        except Exception as e:
            logger.warning(f"检查插件配置时发生异常: {e}，继续加载插件")

        # 加载所有actions，包括默认的和插件的
        if should_load_plugins:
            plugin_manager.load_all_plugins()
            logger.info("插件加载完成")
        else:
            logger.info("已跳过插件加载")

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
        set_global_message_handler(self._isolated_message_process)

        # 现在获取WebSocket服务器（消息处理器已设置）
        self.app = get_global_api()

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

    def _convert_api_message_to_dict(self, message, metadata):
        """
        将APIMessageBase转换为字典格式，以便与现有系统兼容

        Args:
            message: APIMessageBase对象
            metadata: 消息元数据

        Returns:
            dict: 兼容旧格式的消息字典
        """
        # 从metadata中提取tenant_id和agent_id
        tenant_id = metadata.get("tenant_id", self.default_tenant_id) if metadata else self.default_tenant_id
        agent_id = metadata.get("agent_id", self.default_agent_id) if metadata else self.default_agent_id

        try:
            # 提取基本信息
            message_info = {}
            if hasattr(message, "message_info") and message.message_info:
                message_info = {
                    "message_id": message.message_info.message_id,
                    "time": message.message_info.time,
                    "platform": message.message_info.platform,
                }

                # 发送者信息
                if hasattr(message.message_info, "sender_info") and message.message_info.sender_info:
                    sender_info = message.message_info.sender_info
                    message_info["sender_info"] = {
                        "user_info": {
                            "platform": sender_info.user_info.platform if sender_info.user_info else "unknown",
                            "user_id": sender_info.user_info.user_id if sender_info.user_info else "unknown",
                            "user_nickname": getattr(sender_info.user_info, "user_nickname", "")
                            if sender_info.user_info
                            else "",
                        }
                    }

                    # 群组信息
                    if hasattr(sender_info, "group_info") and sender_info.group_info:
                        message_info["sender_info"]["group_info"] = {
                            "platform": sender_info.group_info.platform,
                            "group_id": sender_info.group_info.group_id,
                            "group_name": getattr(sender_info.group_info, "group_name", ""),
                        }

            # 提取消息内容
            message_segment = {}
            if hasattr(message, "message_segment") and message.message_segment:
                message_segment = {
                    "type": message.message_segment.type,
                    "data": message.message_segment.data,
                }

            # 维度信息
            message_dim = {}
            if hasattr(message, "message_dim") and message.message_dim:
                message_dim = {
                    "api_key": message.message_dim.api_key,
                    "platform": message.message_dim.platform,
                }

            # 构建兼容的消息格式
            converted_message = {
                "message_info": message_info,
                "message_segment": message_segment,
                "message_dim": message_dim,
                "raw_message": message_segment.get("data", ""),
                "processed_plain_text": message_segment.get("data", ""),
                "display_message": message_segment.get("data", ""),
                "tenant_id": tenant_id,  # 使用上面提取的值，确保不为None
                "agent_id": agent_id,  # 使用上面提取的值，确保不为None
                "platform": message_info.get("platform") or message_dim.get("platform"),
            }

            return converted_message

        except Exception as e:
            logger.error(f"转换消息格式失败: {e}")
            # 返回最小可用格式
            return {
                "message_info": {"message_id": "unknown", "platform": "unknown"},
                "message_segment": {"type": "text", "data": ""},
                "raw_message": "",
                "processed_plain_text": "",
                "display_message": "",
                "tenant_id": self.default_tenant_id,
                "agent_id": self.default_agent_id,
                "platform": "unknown",
            }

    async def _isolated_message_process(self, message, metadata):
        """
        多租户隔离消息处理器

        Args:
            message: 接收到的APIMessageBase消息对象
            metadata: 消息元数据
        """
        import time

        start_time = time.time()

        # 从APIMessageBase对象中提取信息
        try:
            # 处理APIMessageBase格式
            if hasattr(message, "message_info") and message.message_info:
                message_id = message.message_info.message_id or "unknown"
                platform = message.message_info.platform or "unknown"
            else:
                message_id = "unknown"
                platform = "unknown"

            # 从metadata中提取租户和用户信息
            # 确保tenant_id和agent_id不为None
            tenant_id = (
                metadata.get("tenant_id", self.default_tenant_id)
                if metadata and metadata.get("tenant_id")
                else self.default_tenant_id
            )
            agent_id = (
                metadata.get("agent_id", self.default_agent_id)
                if metadata and metadata.get("agent_id")
                else self.default_agent_id
            )
        except Exception as e:
            logger.error(f"解析消息信息失败: {e}")
            message_id = "unknown"
            platform = "unknown"
            tenant_id = self.default_tenant_id
            agent_id = self.default_agent_id

        logger.info(
            f"[消息处理] 开始处理消息 - ID: {message_id}, 租户: {tenant_id}, 智能体: {agent_id}, 平台: {platform}"
        )
        # 将APIMessageBase转换为旧格式，以便与process_isolated_message兼容
        message_data = self._convert_api_message_to_dict(message, metadata)

        logger.debug(f"[消息处理] 消息完整数据: {message_data}")

        try:
            # 使用隔离化消息处理
            process_start = time.time()
            logger.info(f"[消息处理] 开始隔离化消息处理 - 消息ID: {message_id}")

            isolated_message = await process_isolated_message(
                message_data,
                tenant_id=tenant_id,
                agent_id=agent_id,
                platform=platform,
                validate_before=True,
                validate_after=True,
            )

            process_duration = time.time() - process_start
            logger.info(f"[消息处理] 隔离化消息处理完成 - 消息ID: {message_id}, 耗时: {process_duration:.3f}秒")

            if isolated_message:
                total_duration = time.time() - start_time
                isolated_message_id = isolated_message.get_isolated_message_id()
                logger.info(
                    f"[消息处理] 消息处理成功 - 原始ID: {message_id}, 隔离化ID: {isolated_message_id}, 总耗时: {total_duration:.3f}秒"
                )

                # 检查消息是否正确设置了回复信息
                if hasattr(isolated_message, "chat_stream") and isolated_message.chat_stream:
                    logger.debug(
                        f"[消息处理] 聊天流信息 - Stream ID: {getattr(isolated_message.chat_stream, 'stream_id', 'unknown')}, 平台: {getattr(isolated_message.chat_stream, 'platform', 'unknown')}"
                    )
                else:
                    logger.warning(f"[消息处理] 警告: 消息缺少聊天流信息 - 消息ID: {message_id}")

                return None
            else:
                total_duration = time.time() - start_time
                logger.error(
                    f"[消息处理] 消息处理失败: 处理结果为空 - 消息ID: {message_id}, 耗时: {total_duration:.3f}秒"
                )
                return None

        except Exception as e:
            total_duration = time.time() - start_time
            logger.error(
                f"[消息处理] 消息处理异常 - 消息ID: {message_id}, 异常: {str(e)}, 耗时: {total_duration:.3f}秒",
                exc_info=True,
            )
            return None

    async def schedule_tasks(self):
        """调度定时任务"""
        # 启动租户消息服务器
        logger.info("正在启动租户消息服务器...")
        # 在新线程中运行WebSocket服务器，避免阻塞主事件循环
        import threading
        import asyncio

        def run_server_in_thread():
            """在新线程中运行WebSocket服务器"""
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                new_loop.run_until_complete(self._run_server())
            finally:
                new_loop.close()

        server_thread = threading.Thread(target=run_server_in_thread, daemon=True)
        server_thread.start()
        logger.info("WebSocket服务器线程已启动")

        # 返回一个完成的协程，避免await None报错
        return True

    async def _run_server(self):
        """运行WebSocket服务器"""
        if self.app is None:
            logger.error("WebSocket服务器未初始化")
            return

        try:
            # 启动WebSocket服务器
            await self.app.start()
            logger.info("WebSocket服务器已启动")

            # 保持服务器运行
            while self.app.is_running():
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"WebSocket服务器运行错误: {e}")
        finally:
            await self.app.stop()
            logger.info("WebSocket服务器已停止")

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
    await system.schedule_tasks()  # schedule_tasks 现在是异步函数

    # 让主程序保持运行，直到手动停止
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("收到停止信号，正在关闭系统...")
        # 这里可以添加清理逻辑
        logger.info("系统已关闭")


if __name__ == "__main__":
    asyncio.run(main())
