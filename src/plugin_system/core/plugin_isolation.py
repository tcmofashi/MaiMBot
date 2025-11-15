"""
插件权限和隔离验证
实现插件权限验证机制，确保插件执行时的资源隔离
支持插件沙箱环境
"""

import os
import time
import threading
import psutil
import resource
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from enum import Enum
from contextlib import contextmanager

from src.common.logger import get_logger
from src.isolation.isolation_context import IsolationContext
from src.plugin_system.base.plugin_base import PluginBase

logger = get_logger("plugin_isolation")


class ViolationType(Enum):
    """违规类型"""

    MEMORY_LIMIT = "memory_limit"
    CPU_TIME = "cpu_time"
    FILE_ACCESS = "file_access"
    NETWORK_ACCESS = "network_access"
    SYSTEM_CALL = "system_call"
    MODULE_IMPORT = "module_import"
    RESOURCE_LIMIT = "resource_limit"
    PERMISSION_DENIED = "permission_denied"
    ISOLATION_BREACH = "isolation_breach"


class SecurityLevel(Enum):
    """安全级别"""

    LOW = "low"  # 低安全级别，基础限制
    MEDIUM = "medium"  # 中安全级别，资源限制
    HIGH = "high"  # 高安全级别，严格沙箱
    MAXIMUM = "maximum"  # 最高安全级别，完全隔离


@dataclass
class SecurityPolicy:
    """安全策略"""

    security_level: SecurityLevel
    max_memory_mb: int = 512
    max_cpu_time: float = 10.0
    max_execution_time: float = 30.0
    allow_network_access: bool = False
    allow_file_access: bool = False
    allowed_file_paths: List[str] = field(default_factory=list)
    denied_file_paths: List[str] = field(default_factory=list)
    allowed_modules: Set[str] = field(default_factory=set)
    denied_modules: Set[str] = field(default_factory=set)
    allowed_system_calls: Set[str] = field(default_factory=set)
    denied_system_calls: Set[str] = field(default_factory=set)
    max_processes: int = 1
    max_files: int = 100
    custom_restrictions: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ViolationRecord:
    """违规记录"""

    plugin_name: str
    tenant_id: str
    agent_id: str
    violation_type: ViolationType
    description: str
    timestamp: float
    stack_trace: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)


class ResourceMonitor:
    """资源监控器"""

    def __init__(self, policy: SecurityPolicy):
        self.policy = policy
        self.start_time = None
        self.start_memory = None
        self.process = None
        self.monitoring = False
        self.violations: List[ViolationRecord] = []

    def start_monitoring(self, plugin_name: str, tenant_id: str, agent_id: str):
        """开始监控"""
        self.start_time = time.time()
        self.process = psutil.Process()
        self.start_memory = self.process.memory_info().rss
        self.monitoring = True
        self.plugin_name = plugin_name
        self.tenant_id = tenant_id
        self.agent_id = agent_id

        logger.debug(f"开始监控插件 {plugin_name} 资源使用")

    def stop_monitoring(self):
        """停止监控"""
        self.monitoring = False
        logger.debug(f"停止监控插件 {getattr(self, 'plugin_name', 'unknown')} 资源使用")

    def check_violations(self) -> List[ViolationRecord]:
        """检查违规"""
        if not self.monitoring:
            return []

        violations = []
        current_time = time.time()

        # 检查执行时间
        if current_time - self.start_time > self.policy.max_execution_time:
            violations.append(
                ViolationRecord(
                    plugin_name=getattr(self, "plugin_name", "unknown"),
                    tenant_id=getattr(self, "tenant_id", "unknown"),
                    agent_id=getattr(self, "agent_id", "unknown"),
                    violation_type=ViolationType.RESOURCE_LIMIT,
                    description=f"执行时间超限: {current_time - self.start_time:.2f}s > {self.policy.max_execution_time}s",
                    timestamp=current_time,
                )
            )

        # 检查内存使用
        if self.process:
            current_memory = self.process.memory_info().rss
            memory_mb = (current_memory - self.start_memory) / (1024 * 1024)

            if memory_mb > self.policy.max_memory_mb:
                violations.append(
                    ViolationRecord(
                        plugin_name=getattr(self, "plugin_name", "unknown"),
                        tenant_id=getattr(self, "tenant_id", "unknown"),
                        agent_id=getattr(self, "agent_id", "unknown"),
                        violation_type=ViolationType.MEMORY_LIMIT,
                        description=f"内存使用超限: {memory_mb:.2f}MB > {self.policy.max_memory_mb}MB",
                        timestamp=current_time,
                    )
                )

        # 检查进程数
        if self.process:
            try:
                children = self.process.children(recursive=True)
                if len(children) + 1 > self.policy.max_processes:
                    violations.append(
                        ViolationRecord(
                            plugin_name=getattr(self, "plugin_name", "unknown"),
                            tenant_id=getattr(self, "tenant_id", "unknown"),
                            agent_id=getattr(self, "agent_id", "unknown"),
                            violation_type=ViolationType.RESOURCE_LIMIT,
                            description=f"进程数超限: {len(children) + 1} > {self.policy.max_processes}",
                            timestamp=current_time,
                        )
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        self.violations.extend(violations)
        return violations


class ModuleValidator:
    """模块验证器"""

    def __init__(self, policy: SecurityPolicy):
        self.policy = policy
        self.import_hook = None
        self.original_import = None

    def install_hook(self):
        """安装导入钩子"""
        self.original_import = __builtins__["__import__"]
        self.import_hook = self._create_import_hook()
        __builtins__["__import__"] = self.import_hook

    def remove_hook(self):
        """移除导入钩子"""
        if self.original_import and "__import__" in __builtins__:
            __builtins__["__import__"] = self.original_import

    def _create_import_hook(self):
        """创建导入钩子"""

        def restricted_import(name, globals=None, locals=None, fromlist=(), level=0):
            # 检查是否在允许列表中
            if self.policy.allowed_modules and name not in self.policy.allowed_modules:
                raise ImportError(f"模块 '{name}' 不在允许列表中")

            # 检查是否在禁止列表中
            if name in self.policy.denied_modules:
                raise ImportError(f"模块 '{name}' 被禁止导入")

            # 对于高安全级别，限制更多模块
            if self.policy.security_level in [SecurityLevel.HIGH, SecurityLevel.MAXIMUM]:
                dangerous_modules = {
                    "os",
                    "sys",
                    "subprocess",
                    "shutil",
                    "tempfile",
                    "glob",
                    "socket",
                    "urllib",
                    "http",
                    "ftplib",
                    "smtplib",
                    "ctypes",
                    "threading",
                    "multiprocessing",
                    "asyncio",
                    "pickle",
                    "marshal",
                    "importlib",
                    "imp",
                }
                if name in dangerous_modules:
                    raise ImportError(f"模块 '{name}' 在高安全级别下被禁止")

            return self.original_import(name, globals, locals, fromlist, level)

        return restricted_import


class FileSystemValidator:
    """文件系统验证器"""

    def __init__(self, policy: SecurityPolicy):
        self.policy = policy
        self.original_open = None
        self.original_os_functions = {}

    def install_hooks(self):
        """安装文件系统钩子"""
        # 替换 open 函数
        self.original_open = open

        def restricted_open(
            file, mode="r", buffering=-1, encoding=None, errors=None, newline=None, closefd=True, opener=None
        ):
            if not self._validate_file_access(file, mode):
                raise PermissionError(f"文件访问被拒绝: {file}")
            return self.original_open(file, mode, buffering, encoding, errors, newline, closefd, opener)

        __builtins__["open"] = restricted_open

        # 替换 os 模块中的危险函数
        if not self.policy.allow_file_access or self.policy.security_level in [
            SecurityLevel.HIGH,
            SecurityLevel.MAXIMUM,
        ]:
            dangerous_functions = [
                "remove",
                "rmdir",
                "removedirs",
                "rename",
                "renames",
                "replace",
                "mkdir",
                "makedirs",
                "link",
                "symlink",
                "chmod",
                "chown",
                "stat",
                "lstat",
                "walk",
                "scandir",
                "listdir",
            ]

            for func_name in dangerous_functions:
                if hasattr(os, func_name):
                    self.original_os_functions[func_name] = getattr(os, func_name)
                    setattr(os, func_name, self._create_restricted_function(func_name))

    def remove_hooks(self):
        """移除文件系统钩子"""
        if self.original_open:
            __builtins__["open"] = self.original_open

        for func_name, original_func in self.original_os_functions.items():
            setattr(os, func_name, original_func)

    def _validate_file_access(self, file_path: str, mode: str) -> bool:
        """验证文件访问权限"""
        if not self.policy.allow_file_access and self.policy.security_level in [
            SecurityLevel.HIGH,
            SecurityLevel.MAXIMUM,
        ]:
            return False

        # 检查是否在允许路径中
        if self.policy.allowed_file_paths:
            for allowed_path in self.policy.allowed_file_paths:
                if file_path.startswith(allowed_path):
                    return True
            return False

        # 检查是否在禁止路径中
        for denied_path in self.policy.denied_file_paths:
            if file_path.startswith(denied_path):
                return False

        return True

    def _create_restricted_function(self, func_name: str):
        """创建受限制的函数"""

        def restricted_function(*args, **kwargs):
            raise PermissionError(f"文件系统操作 '{func_name}' 被安全策略禁止")

        return restricted_function


class PluginSandbox:
    """插件沙箱"""

    def __init__(self, policy: SecurityPolicy):
        self.policy = policy
        self.resource_monitor = ResourceMonitor(policy)
        self.module_validator = ModuleValidator(policy)
        self.fs_validator = FileSystemValidator(policy)
        self.active = False
        self.violations: List[ViolationRecord] = []

    @contextmanager
    def execute(self, plugin_name: str, tenant_id: str, agent_id: str):
        """在沙箱中执行插件"""
        try:
            self._enter_sandbox(plugin_name, tenant_id, agent_id)
            yield
        finally:
            self._exit_sandbox()

    def _enter_sandbox(self, plugin_name: str, tenant_id: str, agent_id: str):
        """进入沙箱"""
        if self.active:
            return

        logger.debug(f"插件 {plugin_name} 进入沙箱环境")

        # 开始资源监控
        self.resource_monitor.start_monitoring(plugin_name, tenant_id, agent_id)

        # 安安全验证钩子
        if self.policy.security_level in [SecurityLevel.HIGH, SecurityLevel.MAXIMUM]:
            self.module_validator.install_hook()
            self.fs_validator.install_hooks()

        # 设置资源限制
        if self.policy.security_level in [SecurityLevel.HIGH, SecurityLevel.MAXIMUM]:
            self._set_resource_limits()

        self.active = True

    def _exit_sandbox(self):
        """退出沙箱"""
        if not self.active:
            return

        # 检查违规
        violations = self.resource_monitor.check_violations()
        self.violations.extend(violations)

        # 移除钩子
        self.module_validator.remove_hook()
        self.fs_validator.remove_hooks()

        # 停止监控
        self.resource_monitor.stop_monitoring()

        self.active = False

        if violations:
            logger.warning(f"插件沙箱检测到 {len(violations)} 个违规")

    def _set_resource_limits(self):
        """设置资源限制"""
        try:
            # 设置内存限制
            memory_limit = self.policy.max_memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))

            # 设置CPU时间限制
            cpu_limit = int(self.policy.max_cpu_time)
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit))

            # 设置文件大小限制
            resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))  # 1MB

        except (ValueError, OSError) as e:
            logger.warning(f"设置资源限制失败: {e}")

    def get_violations(self) -> List[ViolationRecord]:
        """获取违规记录"""
        violations = self.violations.copy()
        violations.extend(self.resource_monitor.violations)
        return violations


class PluginIsolationValidator:
    """插件隔离验证器"""

    def __init__(self):
        self.default_policies = self._create_default_policies()
        self.custom_policies: Dict[str, SecurityPolicy] = {}
        self.violation_history: List[ViolationRecord] = []
        self._lock = threading.RLock()

    def _create_default_policies(self) -> Dict[SecurityLevel, SecurityPolicy]:
        """创建默认安全策略"""
        return {
            SecurityLevel.LOW: SecurityPolicy(
                security_level=SecurityLevel.LOW,
                max_memory_mb=1024,
                max_cpu_time=30.0,
                max_execution_time=120.0,
                allow_network_access=True,
                allow_file_access=True,
                allowed_modules=set(),
                denied_modules=set(),
                max_processes=5,
            ),
            SecurityLevel.MEDIUM: SecurityPolicy(
                security_level=SecurityLevel.MEDIUM,
                max_memory_mb=512,
                max_cpu_time=10.0,
                max_execution_time=30.0,
                allow_network_access=False,
                allow_file_access=False,
                denied_modules={"os", "sys", "subprocess", "socket"},
                max_processes=1,
            ),
            SecurityLevel.HIGH: SecurityPolicy(
                security_level=SecurityLevel.HIGH,
                max_memory_mb=256,
                max_cpu_time=5.0,
                max_execution_time=15.0,
                allow_network_access=False,
                allow_file_access=False,
                denied_modules={"os", "sys", "subprocess", "socket", "urllib", "http", "ftplib"},
                max_processes=1,
                max_files=50,
            ),
            SecurityLevel.MAXIMUM: SecurityPolicy(
                security_level=SecurityLevel.MAXIMUM,
                max_memory_mb=128,
                max_cpu_time=2.0,
                max_execution_time=10.0,
                allow_network_access=False,
                allow_file_access=False,
                allowed_modules={"math", "random", "datetime", "json", "re"},
                denied_modules={"os", "sys", "subprocess", "socket", "urllib", "http", "ftplib", "pickle"},
                max_processes=1,
                max_files=10,
            ),
        }

    def get_policy(self, security_level: SecurityLevel, custom_policy_name: str = None) -> SecurityPolicy:
        """获取安全策略"""
        if custom_policy_name and custom_policy_name in self.custom_policies:
            return self.custom_policies[custom_policy_name]

        return self.default_policies.get(security_level, self.default_policies[SecurityLevel.MEDIUM])

    def register_custom_policy(self, name: str, policy: SecurityPolicy):
        """注册自定义策略"""
        with self._lock:
            self.custom_policies[name] = policy
            logger.info(f"注册自定义安全策略: {name}")

    def validate_plugin_execution(
        self,
        plugin: PluginBase,
        isolation_context: IsolationContext,
        security_level: SecurityLevel = SecurityLevel.MEDIUM,
        custom_policy_name: str = None,
    ) -> PluginSandbox:
        """验证插件执行权限"""
        # 检查租户隔离
        if not self._validate_tenant_isolation(plugin, isolation_context):
            raise PermissionError("插件违反租户隔离规则")

        # 检查智能体隔离
        if not self._validate_agent_isolation(plugin, isolation_context):
            raise PermissionError("插件违反智能体隔离规则")

        # 检查平台隔离
        if not self._validate_platform_isolation(plugin, isolation_context):
            raise PermissionError("插件违反平台隔离规则")

        # 创建沙箱
        policy = self.get_policy(security_level, custom_policy_name)
        sandbox = PluginSandbox(policy)

        logger.debug(f"插件 {plugin.plugin_name} 通过隔离验证，使用安全级别: {security_level.value}")
        return sandbox

    def _validate_tenant_isolation(self, plugin: PluginBase, isolation_context: IsolationContext) -> bool:
        """验证租户隔离"""
        if hasattr(plugin, "allowed_tenants"):
            allowed_tenants = getattr(plugin, "allowed_tenants", [])
            if allowed_tenants and isolation_context.tenant_id not in allowed_tenants:
                return False

        if hasattr(plugin, "denied_tenants"):
            denied_tenants = getattr(plugin, "denied_tenants", [])
            if isolation_context.tenant_id in denied_tenants:
                return False

        return True

    def _validate_agent_isolation(self, plugin: PluginBase, isolation_context: IsolationContext) -> bool:
        """验证智能体隔离"""
        if hasattr(plugin, "allowed_agents"):
            allowed_agents = getattr(plugin, "allowed_agents", [])
            if allowed_agents and isolation_context.agent_id not in allowed_agents:
                return False

        if hasattr(plugin, "denied_agents"):
            denied_agents = getattr(plugin, "denied_agents", [])
            if isolation_context.agent_id in denied_agents:
                return False

        return True

    def _validate_platform_isolation(self, plugin: PluginBase, isolation_context: IsolationContext) -> bool:
        """验证平台隔离"""
        if hasattr(plugin, "allowed_platforms"):
            allowed_platforms = getattr(plugin, "allowed_platforms", [])
            if allowed_platforms and isolation_context.platform and isolation_context.platform not in allowed_platforms:
                return False

        if hasattr(plugin, "denied_platforms"):
            denied_platforms = getattr(plugin, "denied_platforms", [])
            if isolation_context.platform and isolation_context.platform in denied_platforms:
                return False

        return True

    def record_violation(self, violation: ViolationRecord):
        """记录违规"""
        with self._lock:
            self.violation_history.append(violation)
            logger.warning(f"记录插件违规: {violation.plugin_name} - {violation.violation_type.value}")

    def get_violation_history(
        self, plugin_name: str = None, tenant_id: str = None, violation_type: ViolationType = None, limit: int = 100
    ) -> List[ViolationRecord]:
        """获取违规历史"""
        with self._lock:
            violations = self.violation_history

            # 应用过滤器
            if plugin_name:
                violations = [v for v in violations if v.plugin_name == plugin_name]
            if tenant_id:
                violations = [v for v in violations if v.tenant_id == tenant_id]
            if violation_type:
                violations = [v for v in violations if v.violation_type == violation_type]

            # 按时间倒序排列
            violations.sort(key=lambda v: v.timestamp, reverse=True)

            return violations[:limit]

    def get_violation_stats(self, days: int = 7) -> Dict[str, Any]:
        """获取违规统计"""
        with self._lock:
            cutoff_time = time.time() - (days * 24 * 60 * 60)
            recent_violations = [v for v in self.violation_history if v.timestamp >= cutoff_time]

            stats = {
                "total_violations": len(recent_violations),
                "by_type": {},
                "by_plugin": {},
                "by_tenant": {},
                "time_range_days": days,
            }

            for violation in recent_violations:
                # 按类型统计
                vtype = violation.violation_type.value
                stats["by_type"][vtype] = stats["by_type"].get(vtype, 0) + 1

                # 按插件统计
                stats["by_plugin"][violation.plugin_name] = stats["by_plugin"].get(violation.plugin_name, 0) + 1

                # 按租户统计
                stats["by_tenant"][violation.tenant_id] = stats["by_tenant"].get(violation.tenant_id, 0) + 1

            return stats

    def cleanup_old_violations(self, days: int = 30):
        """清理旧的违规记录"""
        with self._lock:
            cutoff_time = time.time() - (days * 24 * 60 * 60)
            original_count = len(self.violation_history)
            self.violation_history = [v for v in self.violation_history if v.timestamp >= cutoff_time]
            removed_count = original_count - len(self.violation_history)

            if removed_count > 0:
                logger.info(f"清理了 {removed_count} 条旧的违规记录")


# 全局验证器实例
_global_isolation_validator = PluginIsolationValidator()


def get_isolation_validator() -> PluginIsolationValidator:
    """获取全局隔离验证器"""
    return _global_isolation_validator


# 便捷函数
def validate_plugin_isolation(
    plugin: PluginBase,
    isolation_context: IsolationContext,
    security_level: SecurityLevel = SecurityLevel.MEDIUM,
    custom_policy_name: str = None,
) -> PluginSandbox:
    """验证插件隔离的便捷函数"""
    validator = get_isolation_validator()
    return validator.validate_plugin_execution(plugin, isolation_context, security_level, custom_policy_name)


def register_plugin_security_policy(name: str, policy: SecurityPolicy):
    """注册插件安全策略的便捷函数"""
    validator = get_isolation_validator()
    validator.register_custom_policy(name, policy)


def get_plugin_violation_stats(days: int = 7) -> Dict[str, Any]:
    """获取插件违规统计的便捷函数"""
    validator = get_isolation_validator()
    return validator.get_violation_stats(days)


def cleanup_plugin_violations(days: int = 30):
    """清理插件违规记录的便捷函数"""
    validator = get_isolation_validator()
    validator.cleanup_old_violations(days)
