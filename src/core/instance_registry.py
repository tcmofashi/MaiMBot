"""
实例注册和发现系统

实现实例的注册、发现和依赖注入。支持实例的动态配置和热更新，
提供实例间的依赖关系管理。

主要功能：
1. 实例注册和发现
2. 依赖注入和管理
3. 动态配置和热更新
4. 实例间依赖关系管理
5. 服务发现和负载均衡
"""

import asyncio
import threading
import inspect
from typing import Dict, Any, Optional, List, Set, Callable, Type, TypeVar
from dataclasses import dataclass, field
from collections import defaultdict
from abc import ABC, abstractmethod
from enum import Enum
import logging


logger = logging.getLogger(__name__)

T = TypeVar("T")


class InstanceScope(Enum):
    """实例作用域"""

    SINGLETON = "singleton"  # 单例
    PROTOTYPE = "prototype"  # 原型（每次创建新实例）
    REQUEST = "request"  # 请求级别
    SESSION = "session"  # 会话级别
    TENANT = "tenant"  # 租户级别
    AGENT = "agent"  # 智能体级别


class DependencyType(Enum):
    """依赖类型"""

    REQUIRED = "required"  # 必需依赖
    OPTIONAL = "optional"  # 可选依赖
    LAZY = "lazy"  # 懒加载依赖
    CONDITIONAL = "conditional"  # 条件依赖


@dataclass
class InstanceDefinition:
    """实例定义"""

    name: str
    instance_type: Type
    scope: InstanceScope = InstanceScope.SINGLETON
    factory: Optional[Callable] = None
    dependencies: Dict[str, str] = field(default_factory=dict)
    dependency_types: Dict[str, DependencyType] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_enabled: bool = True
    priority: int = 0
    tags: Set[str] = field(default_factory=set)


@dataclass
class DependencyDefinition:
    """依赖定义"""

    name: str
    dependency_type: DependencyType
    required: bool = True
    lazy: bool = False
    condition: Optional[Callable[[Dict[str, Any]], bool]] = None
    default_value: Any = None


@dataclass
class InstanceReference:
    """实例引用"""

    name: str
    instance: Any
    scope: InstanceScope
    context: Optional[str] = None  # 作用域上下文（如租户ID、会话ID等）
    created_at: float = field(default_factory=lambda: __import__("time").time())
    access_count: int = 0
    last_accessed: float = field(default_factory=lambda: __import__("time").time())


class InstanceFactory(ABC):
    """实例工厂抽象基类"""

    @abstractmethod
    async def create_instance(self, definition: InstanceDefinition, context: Dict[str, Any]) -> Any:
        """创建实例"""
        pass

    @abstractmethod
    def supports(self, instance_type: Type) -> bool:
        """检查是否支持指定类型"""
        pass


class DefaultInstanceFactory(InstanceFactory):
    """默认实例工厂"""

    async def create_instance(self, definition: InstanceDefinition, context: Dict[str, Any]) -> Any:
        """创建实例"""
        # 如果有自定义工厂函数，使用它
        if definition.factory:
            if inspect.iscoroutinefunction(definition.factory):
                return await definition.factory(context)
            else:
                return definition.factory(context)

        # 使用默认构造函数
        try:
            # 获取构造函数参数
            sig = inspect.signature(definition.instance_type.__init__)
            parameters = {}

            for param_name, param in sig.parameters.items():
                if param_name == "self":
                    continue

                # 检查是否有对应的依赖
                if param_name in definition.dependencies:
                    dependency_name = definition.dependencies[param_name]
                    dependency_instance = await self._get_dependency(dependency_name, context)
                    if dependency_instance is not None:
                        parameters[param_name] = dependency_instance

                # 检查配置中是否有对应的值
                elif param_name in definition.config:
                    parameters[param_name] = definition.config[param_name]

                # 检查是否有默认值
                elif param.default != inspect.Parameter.empty:
                    parameters[param_name] = param.default

            # 创建实例
            instance = definition.instance_type(**parameters)

            # 注入属性
            await self._inject_properties(instance, definition, context)

            return instance

        except Exception as e:
            logger.error(f"Failed to create instance {definition.name}: {e}")
            raise

    def supports(self, instance_type: Type) -> bool:
        """默认工厂支持所有类型"""
        return True

    async def _get_dependency(self, dependency_name: str, context: Dict[str, Any]) -> Any:
        """获取依赖实例"""
        registry = get_instance_registry()
        return await registry.get_instance(dependency_name, context)

    async def _inject_properties(self, instance: Any, definition: InstanceDefinition, context: Dict[str, Any]):
        """注入属性"""
        # 检查是否有需要注入的属性
        for attr_name, dependency_name in definition.dependencies.items():
            if hasattr(instance, attr_name):
                dependency_instance = await self._get_dependency(dependency_name, context)
                if dependency_instance is not None:
                    setattr(instance, attr_name, dependency_instance)


class InstanceRegistry:
    """
    实例注册中心

    负责实例的注册、发现、创建和依赖注入。
    支持多种作用域和依赖类型。
    """

    _instance: Optional["InstanceRegistry"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "InstanceRegistry":
        """单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return

        self._initialized = True
        self._lock = threading.RLock()

        # 实例定义存储
        self._definitions: Dict[str, InstanceDefinition] = {}

        # 实例存储（按作用域分类）
        self._singleton_instances: Dict[str, InstanceReference] = {}
        self._scoped_instances: Dict[InstanceScope, Dict[str, Dict[str, InstanceReference]]] = {
            scope: defaultdict(dict) for scope in InstanceScope if scope != InstanceScope.SINGLETON
        }

        # 工厂注册
        self._factories: List[InstanceFactory] = [DefaultInstanceFactory()]

        # 依赖关系图
        self._dependency_graph: Dict[str, Set[str]] = defaultdict(set)
        self._reverse_dependency_graph: Dict[str, Set[str]] = defaultdict(set)

        # 统计信息
        self._stats = {
            "registered_definitions": 0,
            "created_instances": 0,
            "active_instances": 0,
            "dependency_injections": 0,
            "cache_hits": 0,
            "cache_misses": 0,
        }

        logger.info("InstanceRegistry initialized")

    def register_instance(
        self,
        name: str,
        instance_type: Type,
        scope: InstanceScope = InstanceScope.SINGLETON,
        factory: Optional[Callable] = None,
        dependencies: Optional[Dict[str, str]] = None,
        config: Optional[Dict[str, Any]] = None,
        **metadata,
    ) -> bool:
        """
        注册实例定义

        Args:
            name: 实例名称
            instance_type: 实例类型
            scope: 作用域
            factory: 工厂函数
            dependencies: 依赖关系
            config: 配置参数
            **metadata: 元数据

        Returns:
            是否注册成功
        """
        with self._lock:
            if name in self._definitions:
                logger.warning(f"Instance {name} already registered, updating")
                # 清理现有实例
                self._cleanup_instance(name)

            # 创建实例定义
            definition = InstanceDefinition(
                name=name,
                instance_type=instance_type,
                scope=scope,
                factory=factory,
                dependencies=dependencies or {},
                config=config or {},
                metadata=metadata,
            )

            # 验证依赖关系
            if not self._validate_dependencies(definition):
                return False

            # 注册定义
            self._definitions[name] = definition

            # 更新依赖关系图
            self._update_dependency_graph(definition)

            self._stats["registered_definitions"] += 1

            logger.info(f"Registered instance: {name} ({scope.value})")
            return True

    def register_factory(self, factory: InstanceFactory):
        """注册实例工厂"""
        with self._lock:
            self._factories.insert(0, factory)  # 新工厂优先级更高
            logger.info(f"Registered factory: {factory.__class__.__name__}")

    async def get_instance(self, name: str, context: Optional[Dict[str, Any]] = None) -> Optional[T]:
        """
        获取实例

        Args:
            name: 实例名称
            context: 上下文信息

        Returns:
            实例对象或None
        """
        if context is None:
            context = {}

        with self._lock:
            definition = self._definitions.get(name)
            if not definition:
                logger.error(f"Instance definition not found: {name}")
                return None

            if not definition.is_enabled:
                logger.warning(f"Instance {name} is disabled")
                return None

            # 根据作用域获取实例
            if definition.scope == InstanceScope.SINGLETON:
                return await self._get_singleton_instance(definition, context)
            else:
                context_key = self._get_context_key(definition.scope, context)
                return await self._get_scoped_instance(definition, context, context_key)

    async def _get_singleton_instance(self, definition: InstanceDefinition, context: Dict[str, Any]) -> Optional[T]:
        """获取单例实例"""
        if definition.name in self._singleton_instances:
            ref = self._singleton_instances[definition.name]
            ref.access_count += 1
            ref.last_accessed = __import__("time").time()
            self._stats["cache_hits"] += 1
            return ref.instance

        # 创建新实例
        instance = await self._create_instance(definition, context)
        if instance is not None:
            ref = InstanceReference(name=definition.name, instance=instance, scope=definition.scope)
            self._singleton_instances[definition.name] = ref
            self._stats["created_instances"] += 1
            self._stats["active_instances"] += 1

        self._stats["cache_misses"] += 1
        return instance

    async def _get_scoped_instance(
        self, definition: InstanceDefinition, context: Dict[str, Any], context_key: str
    ) -> Optional[T]:
        """获取作用域实例"""
        scoped_instances = self._scoped_instances[definition.scope]

        if context_key in scoped_instances[definition.name]:
            ref = scoped_instances[definition.name][context_key]
            ref.access_count += 1
            ref.last_accessed = __import__("time").time()
            self._stats["cache_hits"] += 1
            return ref.instance

        # 创建新实例
        instance = await self._create_instance(definition, context)
        if instance is not None:
            ref = InstanceReference(
                name=definition.name, instance=instance, scope=definition.scope, context=context_key
            )
            scoped_instances[definition.name][context_key] = ref
            self._stats["created_instances"] += 1
            self._stats["active_instances"] += 1

        self._stats["cache_misses"] += 1
        return instance

    def _get_context_key(self, scope: InstanceScope, context: Dict[str, Any]) -> str:
        """获取上下文键"""
        if scope == InstanceScope.REQUEST:
            return context.get("request_id", "default")
        elif scope == InstanceScope.SESSION:
            return context.get("session_id", "default")
        elif scope == InstanceScope.TENANT:
            return context.get("tenant_id", "default")
        elif scope == InstanceScope.AGENT:
            return f"{context.get('tenant_id', 'default')}:{context.get('agent_id', 'default')}"
        else:
            return "default"

    async def _create_instance(self, definition: InstanceDefinition, context: Dict[str, Any]) -> Optional[T]:
        """创建实例"""
        try:
            # 检查循环依赖
            if self._has_circular_dependency(definition.name, set()):
                raise ValueError(f"Circular dependency detected for instance: {definition.name}")

            # 找到支持该类型的工厂
            factory = None
            for f in self._factories:
                if f.supports(definition.instance_type):
                    factory = f
                    break

            if not factory:
                raise ValueError(f"No factory found for instance type: {definition.instance_type}")

            # 创建实例
            instance = await factory.create_instance(definition, context)

            # 记录依赖注入
            if definition.dependencies:
                self._stats["dependency_injections"] += len(definition.dependencies)

            logger.debug(f"Created instance: {definition.name}")
            return instance

        except Exception as e:
            logger.error(f"Failed to create instance {definition.name}: {e}")
            return None

    def _validate_dependencies(self, definition: InstanceDefinition) -> bool:
        """验证依赖关系"""
        for _dep_name, dep_instance in definition.dependencies.items():
            if dep_instance not in self._definitions:
                logger.error(f"Dependency {dep_instance} not found for instance {definition.name}")
                return False
        return True

    def _update_dependency_graph(self, definition: InstanceDefinition):
        """更新依赖关系图"""
        # 清理旧的依赖关系
        if definition.name in self._dependency_graph:
            for dep in self._dependency_graph[definition.name]:
                self._reverse_dependency_graph[dep].discard(definition.name)

        # 添加新的依赖关系
        self._dependency_graph[definition.name] = set(definition.dependencies.values())
        for dep in definition.dependencies.values():
            self._reverse_dependency_graph[dep].add(definition.name)

    def _has_circular_dependency(self, instance_name: str, visited: Set[str]) -> bool:
        """检查循环依赖"""
        if instance_name in visited:
            return True

        visited.add(instance_name)
        dependencies = self._dependency_graph.get(instance_name, set())

        for dep in dependencies:
            if self._has_circular_dependency(dep, visited.copy()):
                return True

        return False

    def _cleanup_instance(self, name: str):
        """清理实例"""
        # 清理单例实例
        if name in self._singleton_instances:
            ref = self._singleton_instances[name]
            if hasattr(ref.instance, "cleanup"):
                try:
                    if inspect.iscoroutinefunction(ref.instance.cleanup):
                        asyncio.create_task(ref.instance.cleanup())
                    else:
                        ref.instance.cleanup()
                except Exception as e:
                    logger.error(f"Error during instance cleanup: {e}")
            del self._singleton_instances[name]
            self._stats["active_instances"] -= 1

        # 清理作用域实例
        for scope_instances in self._scoped_instances.values():
            if name in scope_instances:
                for _context_key, ref in scope_instances[name].items():
                    if hasattr(ref.instance, "cleanup"):
                        try:
                            if inspect.iscoroutinefunction(ref.instance.cleanup):
                                asyncio.create_task(ref.instance.cleanup())
                            else:
                                ref.instance.cleanup()
                        except Exception as e:
                            logger.error(f"Error during instance cleanup: {e}")
                del scope_instances[name]
                self._stats["active_instances"] -= len(scope_instances[name])

    def unregister_instance(self, name: str) -> bool:
        """注销实例"""
        with self._lock:
            if name not in self._definitions:
                logger.warning(f"Instance {name} not registered")
                return False

            # 清理实例
            self._cleanup_instance(name)

            # 更新依赖关系图
            if name in self._dependency_graph:
                for dep in self._dependency_graph[name]:
                    self._reverse_dependency_graph[dep].discard(name)
                del self._dependency_graph[name]

            if name in self._reverse_dependency_graph:
                del self._reverse_dependency_graph[name]

            # 删除定义
            del self._definitions[name]

            self._stats["registered_definitions"] -= 1

            logger.info(f"Unregistered instance: {name}")
            return True

    def get_instance_dependencies(self, name: str) -> List[str]:
        """获取实例依赖"""
        with self._lock:
            return list(self._dependency_graph.get(name, set()))

    def get_instance_dependents(self, name: str) -> List[str]:
        """获取依赖该实例的其他实例"""
        with self._lock:
            return list(self._reverse_dependency_graph.get(name, set()))

    def find_instances_by_tag(self, tag: str) -> List[str]:
        """根据标签查找实例"""
        with self._lock:
            return [name for name, definition in self._definitions.items() if tag in definition.tags]

    def find_instances_by_type(self, instance_type: Type) -> List[str]:
        """根据类型查找实例"""
        with self._lock:
            return [
                name
                for name, definition in self._definitions.items()
                if definition.instance_type == instance_type or issubclass(definition.instance_type, instance_type)
            ]

    def get_definition(self, name: str) -> Optional[InstanceDefinition]:
        """获取实例定义"""
        with self._lock:
            return self._definitions.get(name)

    def list_instances(self) -> List[str]:
        """列出所有注册的实例"""
        with self._lock:
            return list(self._definitions.keys())

    def update_instance_config(self, name: str, config: Dict[str, Any]) -> bool:
        """更新实例配置"""
        with self._lock:
            if name not in self._definitions:
                logger.error(f"Instance {name} not found")
                return False

            self._definitions[name].config.update(config)

            # 如果是单例实例，可能需要重新创建
            if name in self._singleton_instances:
                logger.info(f"Config updated for singleton instance {name}, consider recreating")

            return True

    def enable_instance(self, name: str) -> bool:
        """启用实例"""
        with self._lock:
            if name in self._definitions:
                self._definitions[name].is_enabled = True
                return True
            return False

    def disable_instance(self, name: str) -> bool:
        """禁用实例"""
        with self._lock:
            if name in self._definitions:
                self._definitions[name].is_enabled = False
                # 清理现有实例
                self._cleanup_instance(name)
                return True
            return False

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return self._stats.copy()

    def clear_cache(self, scope: Optional[InstanceScope] = None):
        """清理缓存"""
        with self._lock:
            if scope is None or scope == InstanceScope.SINGLETON:
                count = len(self._singleton_instances)
                for name in list(self._singleton_instances.keys()):
                    self._cleanup_instance(name)
                logger.info(f"Cleared {count} singleton instances")

            if scope is None:
                for scoped_scope in self._scoped_instances:
                    count = sum(len(instances) for instances in self._scoped_instances[scoped_scope].values())
                    for name in list(self._scoped_instances[scoped_scope].keys()):
                        self._cleanup_instance(name)
                    logger.info(f"Cleared {count} {scoped_scope.value} instances")
            elif scope in self._scoped_instances:
                count = sum(len(instances) for instances in self._scoped_instances[scope].values())
                for name in list(self._scoped_instances[scope].keys()):
                    self._cleanup_instance(name)
                logger.info(f"Cleared {count} {scope.value} instances")

    def shutdown(self):
        """关闭注册中心"""
        logger.info("Shutting down InstanceRegistry")

        # 清理所有实例
        with self._lock:
            all_names = list(self._definitions.keys())
            for name in all_names:
                self._cleanup_instance(name)

            self._definitions.clear()
            self._dependency_graph.clear()
            self._reverse_dependency_graph.clear()
            self._factories.clear()

        logger.info("InstanceRegistry shutdown complete")


# 全局实例注册中心单例
global_instance_registry = InstanceRegistry()


def get_instance_registry() -> InstanceRegistry:
    """获取全局实例注册中心单例"""
    return global_instance_registry


# 便捷函数
def register_instance(name: str, instance_type: Type, **kwargs) -> bool:
    """便捷函数：注册实例"""
    return global_instance_registry.register_instance(name, instance_type, **kwargs)


async def get_instance(name: str, context: Optional[Dict[str, Any]] = None) -> Optional[T]:
    """便捷函数：获取实例"""
    return await global_instance_registry.get_instance(name, context)


def inject(name: str, dependency_type: DependencyType = DependencyType.REQUIRED):
    """依赖注入装饰器"""

    def decorator(func):
        def wrapper(*args, **kwargs):
            # 这里可以实现自动依赖注入逻辑
            return func(*args, **kwargs)

        return wrapper

    return decorator
