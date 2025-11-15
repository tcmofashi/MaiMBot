"""
隔离化插件API
为插件提供隔离的API接口，确保插件只能访问其授权范围内的数据和功能
"""

import asyncio
from typing import Dict, List, Any, Callable
from dataclasses import dataclass
from enum import Enum

from src.common.logger import get_logger
from src.isolation.isolation_context import IsolationContext
from src.chat.message_receive.chat_stream import get_isolated_chat_manager

logger = get_logger("isolated_plugin_api")


class APIPermission(Enum):
    """API权限枚举"""

    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    ADMIN = "admin"


class APIResourceType(Enum):
    """API资源类型"""

    MESSAGE = "message"
    CHAT = "chat"
    CONFIG = "config"
    MEMORY = "memory"
    EVENT = "event"
    PLUGIN = "plugin"
    SYSTEM = "system"


@dataclass
class APIResourcePermission:
    """API资源权限"""

    resource_type: APIResourceType
    permissions: List[APIPermission]
    allowed_paths: List[str] = None  # 允许访问的路径
    denied_paths: List[str] = None  # 禁止访问的路径
    custom_rules: Dict[str, Any] = None  # 自定义规则


class IsolatedPluginAPI:
    """
    隔离化插件API类

    为插件提供隔离的API接口，确保插件只能访问其授权范围内的数据和功能
    """

    def __init__(self, isolation_context: IsolationContext):
        self.isolation_context = isolation_context
        self.tenant_id = isolation_context.tenant_id  # T: 租户隔离
        self.agent_id = isolation_context.agent_id  # A: 智能体隔离
        self.platform = isolation_context.platform  # P: 平台隔离
        self.chat_stream_id = isolation_context.chat_stream_id  # C: 聊天流隔离

        # 权限管理
        self._permissions: Dict[APIResourceType, APIResourcePermission] = {}
        self._setup_default_permissions()

        # API客户端
        self._api_clients = {}
        self._initialize_api_clients()

        # 缓存
        self._cache: Dict[str, Any] = {}
        self._cache_ttl = 300  # 5分钟缓存

        logger.debug(f"隔离化插件API初始化完成: {self.tenant_id}:{self.agent_id}:{self.platform}")

    def _setup_default_permissions(self):
        """设置默认权限"""
        # 默认权限配置
        default_permissions = {
            APIResourceType.MESSAGE: APIResourcePermission(
                resource_type=APIResourceType.MESSAGE,
                permissions=[APIPermission.READ, APIPermission.WRITE],
                allowed_paths=[f"/{self.tenant_id}/{self.agent_id}/*"],
                denied_paths=["/system/*", "/admin/*"],
            ),
            APIResourceType.CHAT: APIResourcePermission(
                resource_type=APIResourceType.CHAT,
                permissions=[APIPermission.READ, APIPermission.WRITE],
                allowed_paths=[f"/{self.tenant_id}/{self.agent_id}/*"],
                denied_paths=["/system/*"],
            ),
            APIResourceType.CONFIG: APIResourcePermission(
                resource_type=APIResourceType.CONFIG,
                permissions=[APIPermission.READ],
                allowed_paths=[f"/{self.tenant_id}/{self.agent_id}/*"],
                denied_paths=["/system/*", "/security/*"],
            ),
            APIResourceType.MEMORY: APIResourcePermission(
                resource_type=APIResourceType.MEMORY,
                permissions=[APIPermission.READ, APIPermission.WRITE],
                allowed_paths=[f"/{self.tenant_id}/{self.agent_id}/*"],
                denied_paths=["/system/*", "/other_tenants/*"],
            ),
            APIResourceType.EVENT: APIResourcePermission(
                resource_type=APIResourceType.EVENT,
                permissions=[APIPermission.READ, APIPermission.WRITE],
                allowed_paths=[f"/{self.tenant_id}/{self.agent_id}/*"],
                denied_paths=["/system/*"],
            ),
            APIResourceType.PLUGIN: APIResourcePermission(
                resource_type=APIResourceType.PLUGIN,
                permissions=[APIPermission.READ],
                allowed_paths=[f"/{self.tenant_id}/*"],
                denied_paths=["/system/*", "/other_tenants/*"],
            ),
            APIResourceType.SYSTEM: APIResourcePermission(
                resource_type=APIResourceType.SYSTEM,
                permissions=[],  # 默认无系统权限
                allowed_paths=[],
                denied_paths=["*"],
            ),
        }

        self._permissions = default_permissions

    def _initialize_api_clients(self):
        """初始化API客户端"""
        try:
            # 延迟导入避免循环依赖
            from src.config.isolated_config_manager import get_isolated_config_manager
            from src.memory_system.isolated_memory_chest import get_isolated_memory_chest
            from src.plugin_system.core.isolated_events_manager import get_isolated_events_manager

            # 配置API客户端
            self._api_clients["config"] = get_isolated_config_manager(self.tenant_id, self.agent_id)

            # 记忆API客户端
            self._api_clients["memory"] = get_isolated_memory_chest(
                self.tenant_id, self.agent_id, self.platform, self.chat_stream_id
            )

            # 事件API客户端
            self._api_clients["events"] = get_isolated_events_manager(self.tenant_id, self.agent_id)

            logger.debug("API客户端初始化完成")

        except Exception as e:
            logger.warning(f"API客户端初始化失败，部分功能可能不可用: {e}")

    def check_permission(self, resource_type: APIResourceType, permission: APIPermission, path: str = None) -> bool:
        """检查权限"""
        if resource_type not in self._permissions:
            return False

        resource_perm = self._permissions[resource_type]
        if permission not in resource_perm.permissions:
            return False

        # 检查路径权限
        if path:
            # 检查是否在禁止列表中
            if resource_perm.denied_paths:
                for denied_path in resource_perm.denied_paths:
                    if self._path_matches(path, denied_path):
                        return False

            # 检查是否在允许列表中
            if resource_perm.allowed_paths:
                for allowed_path in resource_perm.allowed_paths:
                    if self._path_matches(path, allowed_path):
                        return True
                return False

        return True

    def _path_matches(self, path: str, pattern: str) -> bool:
        """检查路径是否匹配模式"""
        # 简单的通配符匹配
        if pattern.endswith("*"):
            return path.startswith(pattern[:-1])
        return path == pattern

    # === 消息API ===

    async def send_message(self, content: str, message_type: str = "text") -> bool:
        """发送消息"""
        if not self.check_permission(APIResourceType.MESSAGE, APIPermission.WRITE):
            raise PermissionError("插件没有发送消息的权限")

        try:
            # 获取隔离化的聊天管理器
            chat_manager = get_isolated_chat_manager(self.tenant_id, self.agent_id)

            if self.chat_stream_id:
                chat_stream = chat_manager.get_stream(self.chat_stream_id)
                if chat_stream:
                    # 这里应该调用隔离化的消息发送接口
                    # 暂时返回成功，实际实现需要调用消息发送API
                    logger.debug(f"插件发送消息到 {self.chat_stream_id}: {content[:50]}...")
                    return True
            return False

        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            return False

    async def get_chat_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取聊天历史"""
        if not self.check_permission(APIResourceType.MESSAGE, APIPermission.READ):
            raise PermissionError("插件没有读取消息的权限")

        try:
            # 获取隔离化的聊天管理器
            chat_manager = get_isolated_chat_manager(self.tenant_id, self.agent_id)

            if self.chat_stream_id:
                chat_stream = chat_manager.get_stream(self.chat_stream_id)
                if chat_stream:
                    # 获取聊天历史
                    history = []
                    # 这里需要从chat_stream中获取历史消息
                    # 暂时返回空列表，实际实现需要提取消息历史
                    return history
            return []

        except Exception as e:
            logger.error(f"获取聊天历史失败: {e}")
            return []

    # === 配置API ===

    def get_config(self, key: str, default: Any = None) -> Any:
        """获取配置"""
        if not self.check_permission(APIResourceType.CONFIG, APIPermission.READ, f"/config/{key}"):
            raise PermissionError("插件没有读取配置的权限")

        try:
            config_client = self._api_clients.get("config")
            if config_client:
                return config_client.get_config(key, default)
            return default

        except Exception as e:
            logger.error(f"获取配置失败: {e}")
            return default

    def set_config(self, key: str, value: Any) -> bool:
        """设置配置"""
        if not self.check_permission(APIResourceType.CONFIG, APIPermission.WRITE, f"/config/{key}"):
            raise PermissionError("插件没有写入配置的权限")

        try:
            config_client = self._api_clients.get("config")
            if config_client:
                return config_client.set_config(key, value)
            return False

        except Exception as e:
            logger.error(f"设置配置失败: {e}")
            return False

    # === 记忆API ===

    async def add_memory(self, title: str, content: str, **kwargs) -> bool:
        """添加记忆"""
        if not self.check_permission(APIResourceType.MEMORY, APIPermission.WRITE):
            raise PermissionError("插件没有写入记忆的权限")

        try:
            memory_client = self._api_clients.get("memory")
            if memory_client:
                # 添加租户和智能体信息
                memory_kwargs = {
                    "tenant_id": self.tenant_id,
                    "agent_id": self.agent_id,
                    "platform": self.platform,
                    "scope_id": self.chat_stream_id,
                    **kwargs,
                }
                return await memory_client.add_memory(title, content, **memory_kwargs)
            return False

        except Exception as e:
            logger.error(f"添加记忆失败: {e}")
            return False

    async def search_memories(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """搜索记忆"""
        if not self.check_permission(APIResourceType.MEMORY, APIPermission.READ):
            raise PermissionError("插件没有读取记忆的权限")

        try:
            memory_client = self._api_clients.get("memory")
            if memory_client:
                # 在租户和智能体范围内搜索
                return await memory_client.search_memories(
                    query, tenant_id=self.tenant_id, agent_id=self.agent_id, platform=self.platform, limit=limit
                )
            return []

        except Exception as e:
            logger.error(f"搜索记忆失败: {e}")
            return []

    # === 事件API ===

    async def publish_event(self, event_type: str, data: Dict[str, Any]) -> bool:
        """发布事件"""
        if not self.check_permission(APIResourceType.EVENT, APIPermission.WRITE):
            raise PermissionError("插件没有发布事件的权限")

        try:
            events_client = self._api_clients.get("events")
            if events_client:
                # 添加隔离上下文到事件数据
                isolated_data = {
                    "tenant_id": self.tenant_id,
                    "agent_id": self.agent_id,
                    "platform": self.platform,
                    "chat_stream_id": self.chat_stream_id,
                    **data,
                }
                return await events_client.publish_event(event_type, isolated_data)
            return False

        except Exception as e:
            logger.error(f"发布事件失败: {e}")
            return False

    async def subscribe_event(self, event_type: str, handler: Callable) -> str:
        """订阅事件"""
        if not self.check_permission(APIResourceType.EVENT, APIPermission.READ):
            raise PermissionError("插件没有订阅事件的权限")

        try:
            events_client = self._api_clients.get("events")
            if events_client:
                return await events_client.subscribe_event(event_type, handler, self.isolation_context)
            return ""

        except Exception as e:
            logger.error(f"订阅事件失败: {e}")
            return ""

    # === 插件API ===

    def get_plugin_list(self) -> List[str]:
        """获取插件列表"""
        if not self.check_permission(APIResourceType.PLUGIN, APIPermission.READ):
            raise PermissionError("插件没有读取插件信息的权限")

        try:
            # 获取租户可用的插件列表
            from src.plugin_system.core.plugin_manager import get_isolated_plugin_manager

            plugin_manager = get_isolated_plugin_manager(self.tenant_id)
            return plugin_manager.get_enabled_plugins()

        except Exception as e:
            logger.error(f"获取插件列表失败: {e}")
            return []

    def call_plugin(self, plugin_name: str, method: str, *args, **kwargs) -> Any:
        """调用其他插件"""
        if not self.check_permission(APIResourceType.PLUGIN, APIPermission.EXECUTE):
            raise PermissionError("插件没有调用其他插件的权限")

        try:
            # 检查是否有权限调用目标插件
            from src.plugin_system.core.plugin_manager import can_tenant_execute_plugin

            if not can_tenant_execute_plugin(self.tenant_id, plugin_name, self.agent_id, self.platform):
                raise PermissionError(f"没有权限调用插件: {plugin_name}")

            # 执行插件调用
            from src.plugin_system.core.isolated_plugin_executor import execute_isolated_plugin
            from src.plugin_system.core.plugin_manager import plugin_manager

            plugin_instance = plugin_manager.get_plugin_instance(plugin_name)
            if plugin_instance:
                # 异步执行
                task = asyncio.create_task(
                    execute_isolated_plugin(
                        plugin_instance, method, self.tenant_id, self.agent_id, self.platform, *args, **kwargs
                    )
                )
                return task
            else:
                raise ValueError(f"插件实例不存在: {plugin_name}")

        except Exception as e:
            logger.error(f"调用插件失败: {e}")
            raise

    # === 缓存API ===

    def cache_get(self, key: str) -> Any:
        """获取缓存"""
        cache_key = f"{self.tenant_id}:{self.agent_id}:{key}"
        return self._cache.get(cache_key)

    def cache_set(self, key: str, value: Any, ttl: int = None) -> bool:
        """设置缓存"""
        try:
            cache_key = f"{self.tenant_id}:{self.agent_id}:{key}"
            self._cache[cache_key] = value

            # 设置TTL（简单实现，实际应该使用更复杂的缓存机制）
            if ttl:
                asyncio.create_task(self._cache_expire(cache_key, ttl))

            return True
        except Exception as e:
            logger.error(f"设置缓存失败: {e}")
            return False

    async def _cache_expire(self, key: str, ttl: int):
        """缓存过期"""
        await asyncio.sleep(ttl)
        if key in self._cache:
            del self._cache[key]

    def cache_delete(self, key: str) -> bool:
        """删除缓存"""
        try:
            cache_key = f"{self.tenant_id}:{self.agent_id}:{key}"
            if cache_key in self._cache:
                del self._cache[cache_key]
                return True
            return False
        except Exception as e:
            logger.error(f"删除缓存失败: {e}")
            return False

    def cache_clear(self) -> bool:
        """清空缓存"""
        try:
            # 只清空当前租户和智能体的缓存
            prefix = f"{self.tenant_id}:{self.agent_id}:"
            keys_to_delete = [k for k in self._cache.keys() if k.startswith(prefix)]
            for key in keys_to_delete:
                del self._cache[key]
            return True
        except Exception as e:
            logger.error(f"清空缓存失败: {e}")
            return False

    # === 系统API ===

    def get_system_info(self) -> Dict[str, Any]:
        """获取系统信息"""
        if not self.check_permission(APIResourceType.SYSTEM, APIPermission.READ):
            raise PermissionError("插件没有读取系统信息的权限")

        return {
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "platform": self.platform,
            "chat_stream_id": self.chat_stream_id,
            "isolation_level": self.isolation_context.get_isolation_level().value,
            "api_version": "1.0.0",
        }

    def get_permissions_summary(self) -> Dict[str, Any]:
        """获取权限摘要"""
        permissions_summary = {}
        for resource_type, permission in self._permissions.items():
            permissions_summary[resource_type.value] = {
                "permissions": [p.value for p in permission.permissions],
                "allowed_paths": permission.allowed_paths,
                "denied_paths": permission.denied_paths,
            }
        return permissions_summary

    # === 工具方法 ===

    def set_permissions(self, resource_type: APIResourceType, permissions: APIResourcePermission):
        """设置权限"""
        self._permissions[resource_type] = permissions

    def add_permission(self, resource_type: APIResourceType, permission: APIPermission):
        """添加权限"""
        if resource_type in self._permissions:
            if permission not in self._permissions[resource_type].permissions:
                self._permissions[resource_type].permissions.append(permission)

    def remove_permission(self, resource_type: APIResourceType, permission: APIPermission):
        """移除权限"""
        if resource_type in self._permissions:
            if permission in self._permissions[resource_type].permissions:
                self._permissions[resource_type].permissions.remove(permission)

    async def cleanup(self):
        """清理资源"""
        try:
            # 清空缓存
            self.cache_clear()

            # 清理API客户端
            self._api_clients.clear()

            logger.debug(f"隔离化插件API已清理: {self.tenant_id}:{self.agent_id}:{self.platform}")

        except Exception as e:
            logger.error(f"清理API资源失败: {e}")


class PluginAPIFactory:
    """插件API工厂"""

    @staticmethod
    def create_isolated_api(isolation_context: IsolationContext) -> IsolatedPluginAPI:
        """创建隔离化API"""
        return IsolatedPluginAPI(isolation_context)

    @staticmethod
    def create_limited_api(
        isolation_context: IsolationContext, allowed_permissions: Dict[APIResourceType, List[APIPermission]]
    ) -> IsolatedPluginAPI:
        """创建有限权限的API"""
        api = IsolatedPluginAPI(isolation_context)

        # 设置有限权限
        for resource_type, permissions in allowed_permissions.items():
            resource_permission = APIResourcePermission(resource_type=resource_type, permissions=permissions)
            api.set_permissions(resource_type, resource_permission)

        return api


# 便捷函数
def create_isolated_plugin_api(
    tenant_id: str, agent_id: str, platform: str = None, chat_stream_id: str = None
) -> IsolatedPluginAPI:
    """创建隔离化插件API的便捷函数"""
    from src.isolation.isolation_context import create_isolation_context

    isolation_context = create_isolation_context(
        tenant_id=tenant_id, agent_id=agent_id, platform=platform, chat_stream_id=chat_stream_id
    )

    return PluginAPIFactory.create_isolated_api(isolation_context)


def create_limited_plugin_api(
    tenant_id: str,
    agent_id: str,
    allowed_permissions: Dict[APIResourceType, List[APIPermission]],
    platform: str = None,
    chat_stream_id: str = None,
) -> IsolatedPluginAPI:
    """创建有限权限插件API的便捷函数"""
    from src.isolation.isolation_context import create_isolation_context

    isolation_context = create_isolation_context(
        tenant_id=tenant_id, agent_id=agent_id, platform=platform, chat_stream_id=chat_stream_id
    )

    return PluginAPIFactory.create_limited_api(isolation_context, allowed_permissions)
