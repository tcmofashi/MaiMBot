import asyncio
from dataclasses import dataclass
from abc import ABC, abstractmethod
from typing import Callable, Any, Optional

from src.config.api_ada_configs import ModelInfo, APIProvider
from ..payload_content.message import Message
from ..payload_content.resp_format import RespFormat
from ..payload_content.tool_option import ToolOption, ToolCall


@dataclass
class UsageRecord:
    """
    使用记录类
    """

    model_name: str
    """模型名称"""

    provider_name: str
    """提供商名称"""

    prompt_tokens: int
    """提示token数"""

    completion_tokens: int
    """完成token数"""

    total_tokens: int
    """总token数"""


@dataclass
class APIResponse:
    """
    API响应类
    """

    content: str | None = None
    """响应内容"""

    reasoning_content: str | None = None
    """推理内容"""

    tool_calls: list[ToolCall] | None = None
    """工具调用 [(工具名称, 工具参数), ...]"""

    embedding: list[float] | None = None
    """嵌入向量"""

    usage: UsageRecord | None = None
    """使用情况 (prompt_tokens, completion_tokens, total_tokens)"""

    raw_data: Any = None
    """响应原始数据"""


class BaseClient(ABC):
    """
    基础客户端
    """

    api_provider: APIProvider

    def __init__(self, api_provider: APIProvider):
        self.api_provider = api_provider

    @abstractmethod
    async def get_response(
        self,
        model_info: ModelInfo,
        message_list: list[Message],
        tool_options: list[ToolOption] | None = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        response_format: RespFormat | None = None,
        stream_response_handler: Optional[
            Callable[[Any, asyncio.Event | None], tuple[APIResponse, tuple[int, int, int]]]
        ] = None,
        async_response_parser: Callable[[Any], tuple[APIResponse, tuple[int, int, int]]] | None = None,
        interrupt_flag: asyncio.Event | None = None,
        extra_params: dict[str, Any] | None = None,
    ) -> APIResponse:
        """
        获取对话响应
        :param model_info: 模型信息
        :param message_list: 对话体
        :param tool_options: 工具选项（可选，默认为None）
        :param max_tokens: 最大token数（可选，默认为1024）
        :param temperature: 温度（可选，默认为0.7）
        :param response_format: 响应格式（可选，默认为 NotGiven ）
        :param stream_response_handler: 流式响应处理函数（可选）
        :param async_response_parser: 响应解析函数（可选）
        :param interrupt_flag: 中断信号量（可选，默认为None）
        :return: (响应文本, 推理文本, 工具调用, 其他数据)
        """
        raise NotImplementedError("'get_response' method should be overridden in subclasses")

    @abstractmethod
    async def get_embedding(
        self,
        model_info: ModelInfo,
        embedding_input: str,
        extra_params: dict[str, Any] | None = None,
    ) -> APIResponse:
        """
        获取文本嵌入
        :param model_info: 模型信息
        :param embedding_input: 嵌入输入文本
        :return: 嵌入响应
        """
        raise NotImplementedError("'get_embedding' method should be overridden in subclasses")

    @abstractmethod
    async def get_audio_transcriptions(
        self,
        model_info: ModelInfo,
        audio_base64: str,
        max_tokens: Optional[int] = None,
        extra_params: dict[str, Any] | None = None,
    ) -> APIResponse:
        """
        获取音频转录
        :param model_info: 模型信息
        :param audio_base64: base64编码的音频数据
        :extra_params: 附加的请求参数
        :return: 音频转录响应
        """
        raise NotImplementedError("'get_audio_transcriptions' method should be overridden in subclasses")

    @abstractmethod
    def get_support_image_formats(self) -> list[str]:
        """
        获取支持的图片格式
        :return: 支持的图片格式列表
        """
        raise NotImplementedError("'get_support_image_formats' method should be overridden in subclasses")


class ClientRegistry:
    def __init__(self) -> None:
        self.client_registry: dict[str, type[BaseClient]] = {}
        """APIProvider.type -> BaseClient的映射表"""
        self.client_instance_cache: dict[str, BaseClient] = {}
        """APIProvider.name -> BaseClient的映射表"""

    def register_client_class(self, client_type: str):
        """
        注册API客户端类
        Args:
            client_class: API客户端类
        """

        def decorator(cls: type[BaseClient]) -> type[BaseClient]:
            if not issubclass(cls, BaseClient):
                raise TypeError(f"{cls.__name__} is not a subclass of BaseClient")
            self.client_registry[client_type] = cls
            return cls

        return decorator

    def get_client_class_instance(self, api_provider: APIProvider, force_new=False) -> BaseClient:
        """
        获取注册的API客户端实例
        Args:
            api_provider: APIProvider实例
            force_new: 是否强制创建新实例（用于解决事件循环问题）
        Returns:
            BaseClient: 注册的API客户端实例
        """
        # 如果强制创建新实例，直接创建不使用缓存
        if force_new:
            if client_class := self.client_registry.get(api_provider.client_type):
                return client_class(api_provider)
            else:
                raise KeyError(f"'{api_provider.client_type}' 类型的 Client 未注册")

        # 正常的缓存逻辑
        if api_provider.name not in self.client_instance_cache:
            if client_class := self.client_registry.get(api_provider.client_type):
                self.client_instance_cache[api_provider.name] = client_class(api_provider)
            else:
                raise KeyError(f"'{api_provider.client_type}' 类型的 Client 未注册")
        return self.client_instance_cache[api_provider.name]


client_registry = ClientRegistry()


class IsolatedClientRegistry:
    """隔离化客户端注册中心

    支持基于隔离上下文的客户端选择和管理。
    """

    def __init__(self):
        # 继承原有的客户端注册表
        self.client_registry: dict[str, type[BaseClient]] = {}
        """APIProvider.type -> BaseClient的映射表"""
        self.client_instance_cache: dict[str, BaseClient] = {}
        """APIProvider.name -> BaseClient的映射表"""

        # 隔离化客户端缓存（按租户+智能体隔离）
        self._isolated_client_cache: dict[str, BaseClient] = {}
        """tenant:agent -> BaseClient的映射表"""
        self._isolated_instance_cache: dict[str, dict[str, BaseClient]] = {}
        """tenant:agent -> {provider_name: BaseClient}的映射表"""

        # 客户端配置映射（支持隔离化配置）
        self._isolated_configs: dict[str, dict[str, APIProvider]] = {}
        """tenant:agent -> {model_name: APIProvider}的映射表"""

        # 线程安全锁
        import threading

        self._cache_lock = threading.RLock()
        self._config_lock = threading.RLock()

    def register_client_class(self, client_type: str):
        """注册API客户端类（兼容原有接口）"""

        def decorator(cls: type[BaseClient]) -> type[BaseClient]:
            if not issubclass(cls, BaseClient):
                raise TypeError(f"{cls.__name__} is not a subclass of BaseClient")
            self.client_registry[client_type] = cls
            return cls

        return decorator

    def get_client_class_instance(self, api_provider: APIProvider, force_new=False) -> BaseClient:
        """获取注册的API客户端实例（兼容原有接口）"""
        # 如果强制创建新实例，直接创建不使用缓存
        if force_new:
            if client_class := self.client_registry.get(api_provider.client_type):
                return client_class(api_provider)
            else:
                raise KeyError(f"'{api_provider.client_type}' 类型的 Client 未注册")

        # 正常的缓存逻辑
        if api_provider.name not in self.client_instance_cache:
            if client_class := self.client_registry.get(api_provider.client_type):
                self.client_instance_cache[api_provider.name] = client_class(api_provider)
            else:
                raise KeyError(f"'{api_provider.client_type}' 类型的 Client 未注册")
        return self.client_instance_cache[api_provider.name]

    def get_isolated_client_instance(
        self, api_provider: APIProvider, tenant_id: str, agent_id: str, force_new: bool = False
    ) -> BaseClient:
        """获取隔离化的API客户端实例"""
        isolation_key = f"{tenant_id}:{agent_id}"

        with self._cache_lock:
            # 初始化隔离缓存
            if isolation_key not in self._isolated_instance_cache:
                self._isolated_instance_cache[isolation_key] = {}

            cache = self._isolated_instance_cache[isolation_key]

            # 强制创建新实例
            if force_new:
                if client_class := self.client_registry.get(api_provider.client_type):
                    instance = client_class(api_provider)
                    cache[api_provider.name] = instance
                    return instance
                else:
                    raise KeyError(f"'{api_provider.client_type}' 类型的 Client 未注册")

            # 从缓存获取
            if api_provider.name not in cache:
                if client_class := self.client_registry.get(api_provider.client_type):
                    cache[api_provider.name] = client_class(api_provider)
                else:
                    raise KeyError(f"'{api_provider.client_type}' 类型的 Client 未注册")

            return cache[api_provider.name]

    def configure_isolated_client(self, tenant_id: str, agent_id: str, model_name: str, api_provider: APIProvider):
        """配置隔离化客户端"""
        isolation_key = f"{tenant_id}:{agent_id}"

        with self._config_lock:
            if isolation_key not in self._isolated_configs:
                self._isolated_configs[isolation_key] = {}

            self._isolated_configs[isolation_key][model_name] = api_provider

    def get_isolated_config(self, tenant_id: str, agent_id: str, model_name: str) -> Optional[APIProvider]:
        """获取隔离化配置"""
        isolation_key = f"{tenant_id}:{agent_id}"

        with self._config_lock:
            configs = self._isolated_configs.get(isolation_key, {})
            return configs.get(model_name)

    def clear_isolated_client_cache(self, tenant_id: str, agent_id: str = None):
        """清理隔离化客户端缓存"""
        with self._cache_lock:
            if agent_id:
                # 清理特定租户+智能体的缓存
                isolation_key = f"{tenant_id}:{agent_id}"
                if isolation_key in self._isolated_instance_cache:
                    del self._isolated_instance_cache[isolation_key]
            else:
                # 清理租户的所有缓存
                keys_to_remove = [
                    key for key in self._isolated_instance_cache.keys() if key.startswith(f"{tenant_id}:")
                ]

                for key in keys_to_remove:
                    del self._isolated_instance_cache[key]

    def clear_isolated_config(self, tenant_id: str, agent_id: str = None):
        """清理隔离化配置"""
        with self._config_lock:
            if agent_id:
                # 清理特定租户+智能体的配置
                isolation_key = f"{tenant_id}:{agent_id}"
                if isolation_key in self._isolated_configs:
                    del self._isolated_configs[isolation_key]
            else:
                # 清理租户的所有配置
                keys_to_remove = [key for key in self._isolated_configs.keys() if key.startswith(f"{tenant_id}:")]

                for key in keys_to_remove:
                    del self._isolated_configs[key]

    def get_isolated_cache_stats(self) -> dict:
        """获取隔离化缓存统计"""
        with self._cache_lock:
            total_clients = sum(len(cache) for cache in self._isolated_instance_cache.values())
            return {
                "total_isolation_groups": len(self._isolated_instance_cache),
                "total_cached_clients": total_clients,
                "cache_groups": {key: len(cache) for key, cache in self._isolated_instance_cache.items()},
            }

    def cleanup_expired_caches(self, max_age_hours: int = 24):
        """清理过期缓存"""
        # 这里可以添加基于时间的缓存清理逻辑
        # 目前仅提供接口，具体实现可以根据需要添加
        pass


# 全局隔离化客户端注册中心实例
isolated_client_registry = IsolatedClientRegistry()
