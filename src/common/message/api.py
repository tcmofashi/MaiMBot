import os
import asyncio
from maim_message.server import WebSocketServer, create_server_config
from src.common.logger import get_logger

global_api = None


# 全局变量存储消息处理器
_message_handler = None

# 默认值
DEFAULT_TENANT_ID = "default"
DEFAULT_AGENT_ID = "default"


def set_global_message_handler(handler):
    """设置全局消息处理器"""
    global _message_handler
    _message_handler = handler


def get_global_api() -> WebSocketServer:  # sourcery skip: extract-method
    """获取全局WebSocket服务器实例（使用最新API）"""
    global global_api, _message_handler
    if global_api is None:
        # 获取配置
        port = int(os.environ.get("PORT", "8095"))
        host = os.environ.get("HOST", "0.0.0.0")

        logger = get_logger(__name__)
        logger.info(f"正在初始化WebSocket服务器: {host}:{port}")

        async def default_message_handler(message, metadata):
            """默认消息处理器"""
            logger.info(f"收到消息: {message.message_segment.data if message.message_segment else 'None'}")

        async def async_auth_handler(metadata):
            """异步认证处理器"""
            # 从多个可能的来源获取API密钥
            api_key = metadata.get("api_key", "")
            if not api_key:
                # 尝试从headers中获取
                headers = metadata.get("headers", {})
                api_key = headers.get("x-apikey", "")

            logger = get_logger(__name__)
            logger.info(f"🔐 认证请求: api_key={api_key}, metadata={list(metadata.keys())}")

            # 基本的认证检查：只要有api_key就通过
            auth_result = bool(api_key)
            logger.info(f"🔐 认证结果: {auth_result}")
            return auth_result

        async def async_user_extractor(metadata):
            """异步用户提取处理器"""
            # 从多个可能的来源获取API密钥
            api_key = metadata.get("api_key", "")
            if not api_key:
                # 尝试从headers中获取
                headers = metadata.get("headers", {})
                api_key = headers.get("x-apikey", "")

            logger = get_logger(__name__)
            logger.info(f"👤 用户提取: api_key={api_key}")

            # 解析API密钥以提取tenant_id和agent_id
            # API密钥格式可能是: "tenant_id:agent_id" 或用户API key (mb_...)
            if ":" in api_key:
                parts = api_key.split(":", 1)
                # 检查第一部分是否是tenant_id格式（tenant_开头）
                if parts[0].startswith("tenant_"):
                    tenant_id = parts[0]
                    agent_id = parts[1] if len(parts) > 1 and parts[1] else DEFAULT_AGENT_ID
                    user_id = f"{tenant_id}:{agent_id}"
                    logger.info(f"👤 提取用户ID: tenant_id={tenant_id}, agent_id={agent_id}, user_id={user_id}")
                    return user_id
                else:
                    # 可能是其他格式，使用默认处理
                    tenant_id = parts[0] if parts[0] else DEFAULT_TENANT_ID
                    agent_id = parts[1] if len(parts) > 1 and parts[1] else DEFAULT_AGENT_ID
                    user_id = f"{tenant_id}:{agent_id}"
                    logger.info(f"👤 使用其他格式: tenant_id={tenant_id}, agent_id={agent_id}, user_id={user_id}")
                    return user_id
            else:
                # 如果没有分隔符，使用默认值
                user_id = f"{DEFAULT_TENANT_ID}:{DEFAULT_AGENT_ID}"
                logger.info(f"👤 使用默认值: user_id={user_id}")
                return user_id

        async def async_message_handler(message, metadata):
            """异步消息处理器"""
            # 从多个可能的来源获取API密钥
            api_key = metadata.get("api_key", "")
            if not api_key:
                # 尝试从headers中获取
                headers = metadata.get("headers", {})
                api_key = headers.get("x-apikey", "")

            # 优先从user_id中获取租户信息（如果经过认证处理）
            user_id = metadata.get("user_id", "")

            def extract_tenant_agent(key_string):
                """从key字符串中提取tenant_id和agent_id"""
                if ":" in key_string:
                    parts = key_string.split(":", 1)
                    tenant_id = parts[0] if parts[0] else DEFAULT_TENANT_ID
                    agent_id = parts[1] if len(parts) > 1 and parts[1] else DEFAULT_AGENT_ID
                    return tenant_id, agent_id
                return DEFAULT_TENANT_ID, DEFAULT_AGENT_ID

            # 尝试从不同来源提取租户信息
            if user_id:
                tenant_id, agent_id = extract_tenant_agent(user_id)
                # 如果user_id中的tenant_id不是标准格式，则从api_key尝试
                if not tenant_id.startswith("tenant_"):
                    tenant_id, agent_id = extract_tenant_agent(api_key)
            else:
                tenant_id, agent_id = extract_tenant_agent(api_key)

            # 如果提取的tenant_id不是标准格式，可能需要数据库查询
            # 暂时使用简单的映射逻辑
            if not tenant_id.startswith("tenant_") and ":" in api_key:
                # 这种情况说明可能是用户token，需要特殊处理
                # 暂时使用默认值，避免数据库错误
                logger = get_logger(__name__)
                logger.warning(f"无法提取有效的tenant_id，使用默认值: api_key={api_key}, user_id={user_id}")
                tenant_id = DEFAULT_TENANT_ID
                agent_id = DEFAULT_AGENT_ID

            metadata["tenant_id"] = tenant_id
            metadata["agent_id"] = agent_id

            handler = _message_handler or default_message_handler
            # 如果处理器是同步的，包装它
            if not asyncio.iscoroutinefunction(handler):
                result = handler(message, metadata)
                return result
            else:
                return await handler(message, metadata)

        # 创建最新的WebSocket服务器配置
        config = create_server_config(
            host=host,
            port=port,
            path="/ws",
            log_level="INFO",
            enable_connection_log=True,
            enable_message_log=True,
            on_auth=async_auth_handler,
            on_auth_extract_user=async_user_extractor,
            on_message=async_message_handler,
        )

        # 创建WebSocket服务器
        global_api = WebSocketServer(config)

        logger.info("WebSocket服务器初始化完成")
    return global_api
