"""
Message-related helpers for tenant/agent active reporting.

提供一个统一的入口 `upsert_active_from_message`：从 `MessageRecv` 中
读取 `message_info.additional_config` 的 `tenant_id`/`agent_id`，若缺失
则回退到 `tenant_context` 获取当前上下文；再调用 `maim_db` 的
`AsyncAgentActiveState.upsert` 上报活跃（默认 12 小时）。
"""

from __future__ import annotations

import os
import sys
from typing import Optional

from src.common.logger import get_logger
from src.common.message.tenant_context import get_current_tenant_id, get_current_agent_id, tenant_context_async

logger = get_logger(__name__)


async def _import_maimdb_active():
    """尝试延迟导入 maim_db 的 AsyncAgentActiveState，失败返回 None"""
    try:
        maim_db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "maim_db"))
        if maim_db_path not in sys.path:
            sys.path.insert(0, maim_db_path)
        from maim_db.src.core import AsyncAgentActiveState  # type: ignore

        return AsyncAgentActiveState
    except Exception as e:
        logger.debug(f"无法导入 maim_db 活跃接口: {e}")
        return None


async def upsert_active_from_message(message, ttl_seconds: int = 12 * 3600) -> Optional[bool]:
    """从消息中提取 tenant_id/agent_id 并上报活跃。

    优先级：`message.message_info.additional_config` -> contextvar 上下文

    返回 True 表示成功上报，False 表示未找到 tenant/agent，None 表示上报失败（导入或执行异常）。
    """
    try:
        add_cfg = getattr(message.message_info, "additional_config", None) or {}
        tenant_id = add_cfg.get("tenant_id")
        agent_id = add_cfg.get("agent_id")

        # 回退到上下文获取
        if not tenant_id:
            tenant_id = get_current_tenant_id()
        if not agent_id:
            agent_id = get_current_agent_id()

        if not tenant_id or not agent_id:
            logger.debug("没有找到 tenant_id 或 agent_id，跳过活跃上报")
            return False

        AsyncAgentActiveState = await _import_maimdb_active()
        if not AsyncAgentActiveState:
            logger.debug("maim_db AsyncAgentActiveState 不可用，无法上报活跃")
            return None

        await AsyncAgentActiveState.upsert(tenant_id=tenant_id, agent_id=agent_id, ttl_seconds=ttl_seconds)
        logger.debug(f"已上报活跃: tenant={tenant_id} agent={agent_id} ttl={ttl_seconds}")
        return True
    except Exception as e:
        logger.exception(f"上报活跃时发生异常: {e}")
        return None


__all__ = [
    "upsert_active_from_message",
    "convert_message_sending_to_api_message",
]
import asyncio
import aiohttp
import json
import toml
from typing import Dict, Any, Optional, Tuple, TYPE_CHECKING

# API-Server Version 导入
from maim_message.server import WebSocketServer, create_server_config
from maim_message.message import (
    APIMessageBase,
    MessageDim,
    BaseMessageInfo as APIBaseMessageInfo,
    Seg as APISeg,
    SenderInfo as APISenderInfo,
    ReceiverInfo as APIReceiverInfo,
    GroupInfo as APIGroupInfo,
    UserInfo as APIUserInfo,
    FormatInfo as APIFormatInfo,
    TemplateInfo as APITemplateInfo,
)

from src.common.logger import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from src.chat.message_receive.message import MessageSending

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
        tenant_id: Optional[str] = None
        agent_id: Optional[str] = None
        # 第一层：尝试从 API Key 提前解析 tenant/agent 并上报活跃
        try:
            api_key = metadata.get("api_key") or getattr(message.message_dim, "api_key", None)
            if api_key:
                parsed = await parse_api_key(api_key)
            else:
                parsed = None

            if parsed:
                tenant_id = parsed.get("tenant_id")
                agent_id = parsed.get("agent_id")

            if tenant_id and agent_id:
                # 使用一个最小的消息对象包装，交给统一上报函数处理
                from types import SimpleNamespace

                stub = SimpleNamespace()
                stub.message_info = SimpleNamespace()
                stub.message_info.additional_config = {"tenant_id": tenant_id, "agent_id": agent_id}
                try:
                    await upsert_active_from_message(stub, ttl_seconds=12 * 3600)
                except Exception:
                    logger.debug("第一层上报活跃失败（upsert_active_from_message）")
        except Exception:
            logger.debug("在第一层尝试解析 API Key 并上报活跃时出错，继续后续处理")

        # 转换消息格式
        legacy_message = convert_api_message_to_legacy(message)

        # 将租户上下文信息注入 legacy message，供下游依赖 additional_config 的模块读取
        additional_cfg = legacy_message.setdefault("message_info", {}).setdefault("additional_config", {})
        if tenant_id and "tenant_id" not in additional_cfg:
            additional_cfg["tenant_id"] = tenant_id
        if agent_id and "agent_id" not in additional_cfg:
            additional_cfg["agent_id"] = agent_id

        # 调用原有的消息处理逻辑
        from src.chat.message_receive.bot import get_message_handler

        handler = get_message_handler()
        if tenant_id and agent_id:
            async with tenant_context_async(tenant_id, agent_id):
                await handler.message_process(legacy_message)
        else:
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

    raw_additional_cfg = getattr(api_message.message_info, "additional_config", None)
    additional_cfg: Dict[str, Any] = {}
    if isinstance(raw_additional_cfg, dict):
        additional_cfg = dict(raw_additional_cfg)

    message_dim_dict = {
        "api_key": api_message.message_dim.api_key,
        "platform": api_message.message_dim.platform,
    }

    additional_cfg.setdefault("api_key", api_message.message_dim.api_key)
    additional_cfg.setdefault("api_platform", api_message.message_dim.platform)

    existing_dim = additional_cfg.get("message_dim")
    if isinstance(existing_dim, dict):
        existing_dim.setdefault("api_key", api_message.message_dim.api_key)
        existing_dim.setdefault("platform", api_message.message_dim.platform)
    else:
        additional_cfg["message_dim"] = message_dim_dict

    if additional_cfg:
        legacy_data["message_info"]["additional_config"] = additional_cfg

    return legacy_data


def _normalize_additional_config(additional_config: Any) -> Dict[str, Any]:
    if not additional_config:
        return {}
    if isinstance(additional_config, dict):
        return additional_config
    if isinstance(additional_config, str):
        try:
            parsed = json.loads(additional_config)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _extract_route_from_additional(additional_config: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    if not additional_config:
        return None, None

    message_dim_cfg = additional_config.get("message_dim")
    if not isinstance(message_dim_cfg, dict):
        message_dim_cfg = {}

    api_key = additional_config.get("api_key") or message_dim_cfg.get("api_key")
    platform = additional_config.get("api_platform") or message_dim_cfg.get("platform")
    return api_key, platform


def _iter_route_candidates(message: "MessageSending"):
    candidates = [message]
    candidates.append(getattr(message, "reply", None))

    stream = getattr(message, "chat_stream", None)
    if stream:
        context = getattr(stream, "context", None)
        if context is not None:
            # ChatMessageContext 提供 message 属性与 get_last_message 方法
            context_message = getattr(context, "message", None)
            if context_message:
                candidates.append(context_message)
            getter = getattr(context, "get_last_message", None)
            if callable(getter):
                try:
                    last_msg = getter()
                    if last_msg:
                        candidates.append(last_msg)
                except Exception:
                    pass

    seen = set()
    for candidate in candidates:
        if candidate is None:
            continue
        ident = id(candidate)
        if ident in seen:
            continue
        seen.add(ident)
        yield candidate


def _resolve_api_route(message: "MessageSending") -> Tuple[str, str]:
    last_platform: Optional[str] = None
    for candidate in _iter_route_candidates(message):
        add_cfg = _normalize_additional_config(getattr(candidate.message_info, "additional_config", None))
        api_key, platform = _extract_route_from_additional(add_cfg)
        if api_key:
            resolved_platform = platform or getattr(candidate.message_info, "platform", None)
            if not resolved_platform:
                resolved_platform = getattr(message.message_info, "platform", None)
            if not resolved_platform:
                resolved_platform = last_platform
            if not resolved_platform:
                raise ValueError("无法确定消息路由的平台信息")
            return api_key, resolved_platform
        if platform:
            last_platform = platform

    raise ValueError("无法在消息上下文中找到 API Key，请确保 additional_config 包含 api_key/api_platform 信息")


def convert_message_sending_to_api_message(message: "MessageSending") -> APIMessageBase:
    api_key, target_platform = _resolve_api_route(message)

    chat_stream = getattr(message, "chat_stream", None)
    group_context = getattr(message.message_info, "group_info", None) or (
        chat_stream.group_info if chat_stream else None
    )

    bot_user_info = getattr(message.message_info, "user_info", None)
    sender_info = None
    if bot_user_info:
        sender_group_info = None
        if group_context:
            sender_group_info = APIGroupInfo.from_dict(group_context.to_dict())  # type: ignore[arg-type]

        sender_info = APISenderInfo(
            user_info=APIUserInfo.from_dict(bot_user_info.to_dict()),  # type: ignore[arg-type]
            group_info=sender_group_info,
        )

    receiver_user = None
    receiver_group = None
    if chat_stream and getattr(chat_stream, "user_info", None):
        receiver_user = APIUserInfo.from_dict(chat_stream.user_info.to_dict())  # type: ignore[arg-type]
    target_group = group_context
    if target_group:
        receiver_group = APIGroupInfo.from_dict(target_group.to_dict())  # type: ignore[arg-type]

    receiver_info = None
    if receiver_user or receiver_group:
        receiver_info = APIReceiverInfo(user_info=receiver_user, group_info=receiver_group)

    format_info = None
    if getattr(message.message_info, "format_info", None):
        format_info = APIFormatInfo.from_dict(message.message_info.format_info.to_dict())  # type: ignore[arg-type]

    template_info = None
    if getattr(message.message_info, "template_info", None):
        template_info = APITemplateInfo.from_dict(message.message_info.template_info.to_dict())  # type: ignore[arg-type]

    additional_config = getattr(message.message_info, "additional_config", None)

    api_message_info = APIBaseMessageInfo(
        platform=message.message_info.platform,
        message_id=message.message_info.message_id,
        time=message.message_info.time,
        format_info=format_info,
        template_info=template_info,
        additional_config=additional_config,
        sender_info=sender_info,
        receiver_info=receiver_info,
    )

    api_segment = APISeg.from_dict(message.message_segment.to_dict())

    platform = target_platform or api_message_info.platform or message.message_info.platform
    if not platform:
        raise ValueError("缺少 message_dim 平台信息，无法发送消息")

    message_dim = MessageDim(api_key=api_key, platform=platform)

    return APIMessageBase(
        message_info=api_message_info,
        message_segment=api_segment,
        message_dim=message_dim,
    )


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
