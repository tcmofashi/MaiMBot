import os
import asyncio
import aiohttp
import toml
from typing import Dict, Any, Optional

# API-Server Version 导入
from maim_message.server import WebSocketServer, create_server_config
from maim_message.message import APIMessageBase

from src.common.logger import get_logger

global_api = None
_config_cache = None


def load_message_config() -> Dict[str, Any]:
    """加载消息服务器配置"""
    global _config_cache
    if _config_cache is None:
        config_path = os.path.join(os.path.dirname(__file__), "config.toml")
        with open(config_path, "r", encoding="utf-8") as f:
            _config_cache = toml.load(f)
    return _config_cache


class MaimConfigClient:
    """MaimConfig API客户端"""

    def __init__(self, url: str, timeout: int = 30, retry_count: int = 3):
        self.url = url.rstrip("/")
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.retry_count = retry_count
        self.session = None
        self.logger = get_logger("maim_config")

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def get_api_key(self, api_key_id: str) -> Optional[str]:
        """从MaimConfig获取API密钥"""
        if not self.session:
            raise RuntimeError("MaimConfigClient must be used as async context manager")

        url = f"{self.url}/api/v1/auth/api-key/{api_key_id}"

        for attempt in range(self.retry_count):
            try:
                async with self.session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("api_key")
                    elif response.status == 404:
                        # 用户不存在
                        self.logger.warning(f"用户不存在: {api_key_id}")
                        return None
                    else:
                        self.logger.warning(f"获取API密钥失败，状态码: {response.status}")
            except Exception as e:
                self.logger.error(f"获取API密钥异常 (尝试 {attempt + 1}): {e}")
                if attempt < self.retry_count - 1:
                    await asyncio.sleep(1)

        return None

    async def parse_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        """解析API Key获取租户和Agent信息"""
        if not self.session:
            raise RuntimeError("MaimConfigClient must be used as async context manager")

        # 调用MaimConfig的API Key解析端点
        url = f"{self.url}/auth/parse-api-key"
        data = {"api_key": api_key}

        try:
            async with self.session.post(url, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("success"):
                        return result.get("data")
                    return None
                return None
        except Exception:
            return None

    async def get_user_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户详细信息"""
        if not self.session:
            raise RuntimeError("MaimConfigClient must be used as async context manager")

        url = f"{self.url}/api/v1/users/{user_id}"

        for attempt in range(self.retry_count):
            try:
                async with self.session.get(url) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 404:
                        self.logger.warning(f"用户不存在: {user_id}")
                        return None
                    else:
                        self.logger.warning(f"获取用户信息失败，状态码: {response.status}")
            except Exception as e:
                self.logger.error(f"获取用户信息异常 (尝试 {attempt + 1}): {e}")
                if attempt < self.retry_count - 1:
                    await asyncio.sleep(1)

        return None

    async def log_api_usage(self, user_id: str, platform: str, action: str = "auth") -> None:
        """记录API使用情况（可选功能）"""
        if not self.session:
            raise RuntimeError("MaimConfigClient must be used as async context manager")

        url = f"{self.url}/api/v1/usage/log"
        data = {
            "user_id": user_id,
            "platform": platform,
            "action": action,
            "timestamp": asyncio.get_event_loop().time(),
        }

        try:
            async with self.session.post(url, json=data) as response:
                if response.status == 200:
                    self.logger.debug(f"API使用记录成功: {user_id} - {action}")
        except Exception as e:
            # 记录失败不影响主要功能
            self.logger.debug(f"记录API使用失败: {e}")


async def parse_api_key(api_key: str) -> Optional[Dict[str, Any]]:
    """使用MaimConfig API解析API Key获取租户和Agent信息"""
    config = load_message_config()
    maim_config_config = config["maimconfig"]

    try:
        async with MaimConfigClient(
            url=maim_config_config["url"],
            timeout=maim_config_config["timeout"],
            retry_count=maim_config_config["retry_count"],
        ) as client:
            # 调用MaimConfig的API Key解析端点
            url = f"{client.url}/auth/parse-api-key"
            data = {"api_key": api_key}

            async with client.session.post(url, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("success"):
                        logger = get_logger("api_key_parser")
                        logger.info(f"API Key解析成功: {api_key[:10]}...")
                        return result.get("data")
                    else:
                        logger = get_logger("api_key_parser")
                        logger.warning(f"API Key解析失败: {result.get('message', '未知错误')}")
                        return None
                else:
                    logger = get_logger("api_key_parser")
                    logger.warning(f"API Key解析端点响应异常，状态码: {response.status}")
                    return None

    except Exception as e:
        logger = get_logger("api_key_parser")
        logger.error(f"API Key解析异常: {e}")
        return None


async def auth_handler(metadata: Dict[str, Any]) -> bool:
    """API Key认证回调函数 - 使用MaimConfig解析API Key"""
    api_key = metadata.get("api_key", "")
    if not api_key:
        return False

    # 使用MaimConfig解析API Key来验证其有效性
    parsed_data = await parse_api_key(api_key)
    return parsed_data is not None and parsed_data.get("format_valid", False)


async def extract_user_handler(metadata: Dict[str, Any]) -> str:
    """用户标识提取回调函数 - 使用MaimConfig解析API Key获取租户和Agent信息"""
    api_key = metadata.get("api_key", "")
    platform = metadata.get("platform", "unknown")

    if not api_key:
        return "unknown_user"

    try:
        # 解析API Key获取租户和Agent信息
        parsed_data = await parse_api_key(api_key)
        if not parsed_data or not parsed_data.get("format_valid"):
            # 如果API Key无效，使用hash作为临时标识
            logger = get_logger("extract_user_handler")
            logger.warning(f"API Key解析失败，使用临时标识: {api_key[:10]}...")
            return f"temp_user_{hash(api_key) % 10000}"

        # 提取租户ID和Agent ID
        tenant_id = parsed_data.get("tenant_id")
        agent_id = parsed_data.get("agent_id")
        version = parsed_data.get("version")

        # 生成用户标识：tenant_agent的联合标识（不包含platform）
        if tenant_id and agent_id:
            user_id = f"{tenant_id}_{agent_id}"
            # 如果有版本信息，也包含在内
            if version:
                user_id = f"{user_id}_{version}"
        else:
            # 如果解析出的信息不完整，使用降级策略
            logger = get_logger("extract_user_handler")
            logger.warning(f"API Key解析信息不完整: tenant_id={tenant_id}, agent_id={agent_id}")
            user_id = f"partial_user_{hash(api_key) % 10000}"

        # 记录API使用情况
        config = load_message_config()
        maim_config_config = config["maimconfig"]

        async with MaimConfigClient(
            url=maim_config_config["url"],
            timeout=maim_config_config["timeout"],
            retry_count=maim_config_config["retry_count"],
        ) as client:
            # 记录API使用情况
            if tenant_id:
                await client.log_api_usage(tenant_id, platform, "auth")

        logger = get_logger("extract_user_handler")
        logger.info(f"用户标识提取成功: {api_key[:10]}... -> {user_id}")
        return user_id

    except Exception as e:
        logger = get_logger("extract_user_handler")
        logger.error(f"用户标识提取异常: {e}")
        # 降级使用API Key的hash作为标识
        return f"fallback_user_{hash(api_key) % 10000}"


async def message_handler(message: APIMessageBase, metadata: Dict[str, Any]) -> None:
    """消息处理回调函数 - 将APIMessageBase转换为MessageBase并调用原有处理流程"""
    logger = get_logger("message_handler")
    try:
        # 转换消息格式
        legacy_message = convert_api_message_to_legacy(message)

        # 调用原有的消息处理逻辑
        from src.chat.message_receive.bot import get_message_handler

        handler = get_message_handler()
        await handler.message_process(legacy_message)

        logger.info(f"消息处理完成: {message.message_info.message_id}")

    except Exception as e:
        logger.error(f"消息处理失败: {e}")


def convert_api_message_to_legacy(api_message: APIMessageBase) -> Dict[str, Any]:
    """将APIMessageBase转换为兼容的MessageBase格式"""
    # 提取用户信息
    user_info = None
    group_info = None

    if api_message.message_info.sender_info:
        if api_message.message_info.sender_info.user_info:
            user_info = api_message.message_info.sender_info.user_info

        if api_message.message_info.sender_info.group_info:
            group_info = api_message.message_info.sender_info.group_info

    # 构建兼容的消息格式
    legacy_data = {
        "message_info": {
            "platform": api_message.message_info.platform,
            "message_id": api_message.message_info.message_id,
            "time": api_message.message_info.time,
        },
        "message_segment": {"type": api_message.message_segment.type, "data": api_message.message_segment.data},
        "user_info": user_info,
        "group_info": group_info,
        "message_dim": {"api_key": api_message.message_dim.api_key, "platform": api_message.message_dim.platform},
    }

    # 添加格式信息（如果有）
    if api_message.message_info.format_info:
        legacy_data["message_info"]["format_info"] = {
            "content_format": api_message.message_info.format_info.content_format,
            "accept_format": api_message.message_info.format_info.accept_format,
        }

    return legacy_data


def get_global_api() -> WebSocketServer:  # sourcery skip: extract-method
    """获取全局WebSocketServer实例"""
    global global_api
    if global_api is None:
        config = load_message_config()
        api_server_config = config["api_server"]

        # 创建API-Server版本配置
        server_config = create_server_config(
            host=api_server_config["host"],
            port=api_server_config["port"],
            path=api_server_config["path"],
            on_auth=auth_handler,
            on_auth_extract_user=extract_user_handler,
            on_message=message_handler,
            log_level=config["logging"]["log_level"],
            enable_connection_log=config["logging"]["enable_connection_log"],
            enable_message_log=config["logging"]["enable_message_log"],
        )

        # 如果启用SSL
        if config.get("ssl", {}).get("enabled", False):
            ssl_config = config["ssl"]
            server_config.ssl_enabled = True
            if ssl_config.get("cert_file"):
                server_config.ssl_certfile = ssl_config["cert_file"]
            if ssl_config.get("key_file"):
                server_config.ssl_keyfile = ssl_config["key_file"]
            if ssl_config.get("ca_certs"):
                server_config.ssl_ca_certs = ssl_config["ca_certs"]
            server_config.ssl_verify = ssl_config.get("verify", True)

        global_api = WebSocketServer(server_config)

        logger = get_logger("global_api")
        logger.info(f"API-Server WebSocket服务器已配置: {api_server_config['host']}:{api_server_config['port']}")

    return global_api
