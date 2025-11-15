"""
MaiBot API兼容性策略
提供API版本管理、兼容性保证和并行运行支持

作者: Claude
创建时间: 2025-01-12
"""

import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from collections import defaultdict

from src.common.logger import get_logger

logger = get_logger("api_compatibility_strategy")


class APIVersion(Enum):
    """API版本枚举"""

    V1_LEGACY = "v1_legacy"  # 原有API
    V2_TRANSITION = "v2_transition"  # 过渡期API
    V3_ISOLATED = "v3_isolated"  # 隔离架构API


class CompatibilityLevel(Enum):
    """兼容性级别"""

    FULL = "full"  # 完全兼容
    PARTIAL = "partial"  # 部分兼容
    DEPRECATED = "deprecated"  # 已弃用
    BREAKING = "breaking"  # 破坏性变更


@dataclass
class APIEndpoint:
    """API端点定义"""

    name: str
    path: str
    method: str
    version: APIVersion
    compatibility_level: CompatibilityLevel
    deprecated_date: Optional[datetime] = None
    removal_date: Optional[datetime] = None
    migration_guide: Optional[str] = None
    alternatives: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class APIUsage:
    """API使用统计"""

    endpoint_name: str
    version: APIVersion
    usage_count: int
    last_used: datetime
    error_count: int = 0
    average_response_time: float = 0.0
    users: List[str] = field(default_factory=list)


@dataclass
class CompatibilityRule:
    """兼容性规则"""

    name: str
    description: str
    old_signature: str
    new_signature: str
    transformation_function: Optional[Callable] = None
    auto_apply: bool = True
    test_cases: List[Dict[str, Any]] = field(default_factory=list)


class APICompatibilityStrategy:
    """API兼容性策略管理器"""

    def __init__(self):
        self.endpoints: Dict[str, APIEndpoint] = {}
        self.usage_stats: Dict[str, APIUsage] = defaultdict(APIUsage)
        self.compatibility_rules: List[CompatibilityRule] = []
        self.migration_metrics = {
            "total_api_calls": 0,
            "legacy_api_calls": 0,
            "new_api_calls": 0,
            "errors": 0,
            "migrations_triggered": 0,
        }

        # 兼容性配置
        self.compatibility_config = {
            "enable_dual_api": True,  # 启用双API并行
            "auto_migration": False,  # 自动迁移（默认关闭）
            "legacy_api_warning": True,  # 旧API警告
            "usage_tracking": True,  # 使用统计
            "compatibility_checks": True,  # 兼容性检查
            "grace_period_days": 90,  # 优雅期天数
            "max_warning_count": 10,  # 最大警告次数
        }

        self._initialize_endpoints()
        self._initialize_compatibility_rules()

    def _initialize_endpoints(self):
        """初始化API端点定义"""
        # ChatStream API
        self.register_endpoint(
            APIEndpoint(
                name="chat_stream_create",
                path="/api/chat/stream",
                method="POST",
                version=APIVersion.V1_LEGACY,
                compatibility_level=CompatibilityLevel.DEPRECATED,
                description="创建聊天流 - 旧版本API",
                alternatives=["/api/v3/chat/stream"],
                migration_guide="使用新的IsolationContext参数",
            )
        )

        self.register_endpoint(
            APIEndpoint(
                name="chat_stream_create_v3",
                path="/api/v3/chat/stream",
                method="POST",
                version=APIVersion.V3_ISOLATED,
                compatibility_level=CompatibilityLevel.FULL,
                description="创建聊天流 - 支持多租户隔离",
            )
        )

        # 配置API
        self.register_endpoint(
            APIEndpoint(
                name="config_get",
                path="/api/config",
                method="GET",
                version=APIVersion.V1_LEGACY,
                compatibility_level=CompatibilityLevel.PARTIAL,
                description="获取配置 - 旧版本API",
                alternatives=["/api/v3/config"],
                migration_guide="需要提供租户和智能体上下文",
            )
        )

        self.register_endpoint(
            APIEndpoint(
                name="config_get_v3",
                path="/api/v3/config",
                method="GET",
                version=APIVersion.V3_ISOLATED,
                compatibility_level=CompatibilityLevel.FULL,
                description="获取配置 - 支持多租户隔离",
            )
        )

        # 记忆系统API
        self.register_endpoint(
            APIEndpoint(
                name="memory_store",
                path="/api/memory",
                method="POST",
                version=APIVersion.V1_LEGACY,
                compatibility_level=CompatibilityLevel.DEPRECATED,
                description="存储记忆 - 旧版本API",
                alternatives=["/api/v3/memory"],
                migration_guide="需要提供隔离上下文信息",
            )
        )

        self.register_endpoint(
            APIEndpoint(
                name="memory_store_v3",
                path="/api/v3/memory",
                method="POST",
                version=APIVersion.V3_ISOLATED,
                compatibility_level=CompatibilityLevel.FULL,
                description="存储记忆 - 支持多租户隔离",
            )
        )

    def _initialize_compatibility_rules(self):
        """初始化兼容性规则"""
        self.compatibility_rules = [
            CompatibilityRule(
                name="chat_stream_param_mapping",
                description="ChatStream创建参数映射",
                old_signature="ChatStream(chat_id, platform, user_id)",
                new_signature="ChatStream(isolation_context, chat_id, platform, user_id)",
                transformation_function=self._transform_chat_stream_params,
                auto_apply=True,
                test_cases=[
                    {
                        "old_params": {"chat_id": "123", "platform": "qq", "user_id": "456"},
                        "expected": "isolation_context_added",
                    }
                ],
            ),
            CompatibilityRule(
                name="config_context_injection",
                description="配置获取时注入隔离上下文",
                old_signature="get_config(key)",
                new_signature="get_config(isolation_context, key)",
                transformation_function=self._transform_config_call,
                auto_apply=True,
                test_cases=[{"old_params": {"key": "bot_name"}, "expected": "context_injected"}],
            ),
            CompatibilityRule(
                name="memory_context_addition",
                description="记忆API添加上下文参数",
                old_signature="store_memory(key, value)",
                new_signature="store_memory(isolation_context, key, value)",
                transformation_function=self._transform_memory_call,
                auto_apply=True,
                test_cases=[{"old_params": {"key": "user_pref", "value": "test"}, "expected": "context_added"}],
            ),
        ]

    def register_endpoint(self, endpoint: APIEndpoint):
        """注册API端点"""
        self.endpoints[endpoint.name] = endpoint
        logger.debug(f"注册API端点: {endpoint.name} ({endpoint.version.value})")

    def track_api_usage(
        self,
        endpoint_name: str,
        version: APIVersion,
        user_id: str = None,
        response_time: float = 0.0,
        error: bool = False,
    ):
        """跟踪API使用情况"""
        if not self.compatibility_config["usage_tracking"]:
            return

        key = f"{endpoint_name}_{version.value}"
        usage = self.usage_stats[key]

        usage.endpoint_name = endpoint_name
        usage.version = version
        usage.usage_count += 1
        usage.last_used = datetime.now()

        if error:
            usage.error_count += 1
            self.migration_metrics["errors"] += 1

        if response_time > 0:
            # 计算平均响应时间
            total_time = usage.average_response_time * (usage.usage_count - 1) + response_time
            usage.average_response_time = total_time / usage.usage_count

        if user_id and user_id not in usage.users:
            usage.users.append(user_id)

        self.migration_metrics["total_api_calls"] += 1

        if version == APIVersion.V1_LEGACY:
            self.migration_metrics["legacy_api_calls"] += 1
        elif version == APIVersion.V3_ISOLATED:
            self.migration_metrics["new_api_calls"] += 1

        # 发出迁移警告
        if version == APIVersion.V1_LEGACY and self.compatibility_config["legacy_api_warning"]:
            self._emit_migration_warning(endpoint_name, user_id)

    def _emit_migration_warning(self, endpoint_name: str, user_id: str = None):
        """发出迁移警告"""
        endpoint = self.endpoints.get(endpoint_name)
        if not endpoint or endpoint.compatibility_level != CompatibilityLevel.DEPRECATED:
            return

        key = f"{endpoint_name}_{endpoint.version.value}"
        usage = self.usage_stats[key]

        if usage.usage_count <= self.compatibility_config["max_warning_count"]:
            logger.warning(f"API迁移警告: {endpoint_name} 已弃用，请使用 {endpoint.alternatives}")

    def legacy_api_decorator(self, new_endpoint_name: str):
        """旧API装饰器，提供自动迁移"""

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # 跟踪使用情况
                self.track_api_usage(func.__name__, APIVersion.V1_LEGACY)

                # 如果启用自动迁移
                if self.compatibility_config["auto_migration"]:
                    try:
                        # 尝试转换参数并调用新API
                        return self._migrate_to_new_api(new_endpoint_name, args, kwargs)
                    except Exception as e:
                        logger.error(f"自动迁移失败: {e}，回退到旧API")
                        self.migration_metrics["errors"] += 1

                # 调用旧API
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    response_time = time.time() - start_time
                    self.track_api_usage(func.__name__, APIVersion.V1_LEGACY, response_time=response_time)
                    return result
                except Exception:
                    response_time = time.time() - start_time
                    self.track_api_usage(func.__name__, APIVersion.V1_LEGACY, response_time=response_time, error=True)
                    raise

            return wrapper

        return decorator

    def new_api_decorator(self, endpoint_name: str):
        """新API装饰器"""

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    response_time = time.time() - start_time
                    self.track_api_usage(endpoint_name, APIVersion.V3_ISOLATED, response_time=response_time)
                    return result
                except Exception:
                    response_time = time.time() - start_time
                    self.track_api_usage(endpoint_name, APIVersion.V3_ISOLATED, response_time=response_time, error=True)
                    raise

            return wrapper

        return decorator

    def _migrate_to_new_api(self, new_endpoint_name: str, old_args: Tuple, old_kwargs: Dict) -> Any:
        """迁移到新API"""
        # 查找兼容性规则
        for rule in self.compatibility_rules:
            if rule.auto_apply and rule.transformation_function:
                try:
                    # 应用转换函数
                    transformed_args, transformed_kwargs = rule.transformation_function(old_args, old_kwargs)
                    self.migration_metrics["migrations_triggered"] += 1

                    # 调用新API
                    new_func = self._get_new_api_function(new_endpoint_name)
                    if new_func:
                        return new_func(*transformed_args, **transformed_kwargs)
                except Exception as e:
                    logger.error(f"应用兼容性规则失败 {rule.name}: {e}")

        raise Exception("无法自动迁移到新API")

    def _get_new_api_function(self, endpoint_name: str) -> Optional[Callable]:
        """获取新API函数"""
        # 这里应该根据endpoint_name查找对应的新API函数
        # 在实际实现中，这需要与具体的API框架集成
        return None

    def _transform_chat_stream_params(self, args: Tuple, kwargs: Dict) -> Tuple[Tuple, Dict]:
        """转换ChatStream参数"""
        # 模拟参数转换
        isolation_context = self._create_default_isolation_context()
        new_args = (isolation_context,) + args
        return new_args, kwargs

    def _transform_config_call(self, args: Tuple, kwargs: Dict) -> Tuple[Tuple, Dict]:
        """转换配置调用参数"""
        isolation_context = self._create_default_isolation_context()
        new_args = (isolation_context,) + args
        return new_args, kwargs

    def _transform_memory_call(self, args: Tuple, kwargs: Dict) -> Tuple[Tuple, Dict]:
        """转换记忆API调用参数"""
        isolation_context = self._create_default_isolation_context()
        new_args = (isolation_context,) + args
        return new_args, kwargs

    def _create_default_isolation_context(self):
        """创建默认隔离上下文"""
        # 这里应该返回一个实际的IsolationContext实例
        # 模拟实现
        return {"tenant_id": "default_tenant", "agent_id": "default_agent", "chat_stream_id": None, "platform": "qq"}

    def generate_migration_report(self) -> Dict[str, Any]:
        """生成迁移报告"""
        total_legacy_calls = sum(
            usage.usage_count for usage in self.usage_stats.values() if usage.version == APIVersion.V1_LEGACY
        )
        total_new_calls = sum(
            usage.usage_count for usage in self.usage_stats.values() if usage.version == APIVersion.V3_ISOLATED
        )

        # 计算迁移进度
        total_calls = total_legacy_calls + total_new_calls
        migration_progress = (total_new_calls / total_calls * 100) if total_calls > 0 else 0

        # 识别需要迁移的端点
        deprecated_endpoints = []
        for endpoint in self.endpoints.values():
            if endpoint.compatibility_level == CompatibilityLevel.DEPRECATED:
                usage_key = f"{endpoint.name}_{endpoint.version.value}"
                usage = self.usage_stats.get(usage_key)
                if usage and usage.usage_count > 0:
                    deprecated_endpoints.append(
                        {
                            "endpoint": endpoint.name,
                            "usage_count": usage.usage_count,
                            "last_used": usage.last_used.isoformat(),
                            "users_count": len(usage.users),
                            "alternatives": endpoint.alternatives,
                        }
                    )

        # 生成迁移建议
        recommendations = self._generate_migration_recommendations(
            total_legacy_calls, total_new_calls, deprecated_endpoints
        )

        return {
            "generated_at": datetime.now().isoformat(),
            "migration_metrics": self.migration_metrics,
            "usage_statistics": {
                "total_legacy_calls": total_legacy_calls,
                "total_new_calls": total_new_calls,
                "migration_progress": round(migration_progress, 2),
                "total_errors": self.migration_metrics["errors"],
            },
            "deprecated_endpoints": deprecated_endpoints,
            "recommendations": recommendations,
            "next_steps": self._generate_next_steps(migration_progress),
        }

    def _generate_migration_recommendations(
        self, legacy_calls: int, new_calls: int, deprecated_endpoints: List[Dict]
    ) -> List[str]:
        """生成迁移建议"""
        recommendations = []

        if legacy_calls > 0:
            recommendations.append(f"发现 {legacy_calls} 次旧API调用，需要迁移到新版本")

        if deprecated_endpoints:
            recommendations.append(f"有 {len(deprecated_endpoints)} 个已弃用的端点仍在使用")

        if legacy_calls > new_calls:
            recommendations.append("旧API使用率仍然较高，建议加强迁移推广")

        if self.migration_metrics["errors"] > 0:
            recommendations.append("存在API调用错误，需要检查兼容性问题")

        recommendations.append("建议在迁移完成后禁用旧API以提高性能")
        recommendations.append("持续监控API使用情况，确保迁移顺利进行")

        return recommendations

    def _generate_next_steps(self, migration_progress: float) -> List[str]:
        """生成下一步行动计划"""
        if migration_progress < 30:
            return ["加强开发者培训和文档宣导", "提供更多的迁移工具和示例", "设置迁移期限和提醒机制"]
        elif migration_progress < 70:
            return ["逐步启用更严格的迁移策略", "开始禁用部分非关键旧API", "加强测试和验证"]
        elif migration_progress < 95:
            return ["准备完全禁用旧API", "进行全面的兼容性测试", "制定回滚计划"]
        else:
            return ["完成旧API的禁用", "清理遗留代码和文档", "总结迁移经验"]

    def create_migration_timeline(self) -> Dict[str, Any]:
        """创建迁移时间线"""
        grace_period_days = self.compatibility_config["grace_period_days"]
        start_date = datetime.now()
        end_date = start_date + timedelta(days=grace_period_days)

        phases = [
            {
                "phase": 1,
                "name": "并行运行期",
                "start_date": start_date.isoformat(),
                "end_date": (start_date + timedelta(days=30)).isoformat(),
                "description": "新旧API并行运行，提供警告和迁移建议",
                "actions": ["启用双API模式", "开始使用统计", "发出迁移警告"],
            },
            {
                "phase": 2,
                "name": "迁移推广期",
                "start_date": (start_date + timedelta(days=30)).isoformat(),
                "end_date": (start_date + timedelta(days=60)).isoformat(),
                "description": "加强迁移推广，提供更多支持",
                "actions": ["提供迁移工具", "加强文档", "技术支持"],
            },
            {
                "phase": 3,
                "name": "逐步禁用期",
                "start_date": (start_date + timedelta(days=60)).isoformat(),
                "end_date": (start_date + timedelta(days=grace_period_days - 10)).isoformat(),
                "description": "逐步禁用非关键的旧API",
                "actions": ["禁用部分旧API", "加强监控", "准备完全切换"],
            },
            {
                "phase": 4,
                "name": "完全切换期",
                "start_date": (start_date + timedelta(days=grace_period_days - 10)).isoformat(),
                "end_date": end_date.isoformat(),
                "description": "完全切换到新API",
                "actions": ["完全禁用旧API", "清理遗留代码", "完成迁移"],
            },
        ]

        return {
            "grace_period_days": grace_period_days,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "phases": phases,
            "current_phase": self._get_current_phase(phases),
        }

    def _get_current_phase(self, phases: List[Dict]) -> Dict[str, Any]:
        """获取当前阶段"""
        now = datetime.now()
        for phase in phases:
            start = datetime.fromisoformat(phase["start_date"])
            end = datetime.fromisoformat(phase["end_date"])
            if start <= now <= end:
                return phase
        return phases[0]  # 默认返回第一阶段

    def test_api_compatibility(self, endpoint_name: str, test_cases: List[Dict[str, Any]]) -> Dict[str, Any]:
        """测试API兼容性"""
        results = {
            "endpoint": endpoint_name,
            "total_tests": len(test_cases),
            "passed_tests": 0,
            "failed_tests": 0,
            "test_details": [],
        }

        for i, test_case in enumerate(test_cases):
            test_result = {
                "test_id": i + 1,
                "description": test_case.get("description", f"测试用例 {i + 1}"),
                "input": test_case.get("input", {}),
                "expected": test_case.get("expected", {}),
                "actual": None,
                "passed": False,
                "error": None,
            }

            try:
                # 执行测试
                actual_result = self._execute_compatibility_test(endpoint_name, test_case)
                test_result["actual"] = actual_result

                # 验证结果
                expected_result = test_case.get("expected")
                if self._compare_results(expected_result, actual_result):
                    test_result["passed"] = True
                    results["passed_tests"] += 1
                else:
                    results["failed_tests"] += 1
                    test_result["error"] = "结果不匹配"

            except Exception as e:
                results["failed_tests"] += 1
                test_result["error"] = str(e)

            results["test_details"].append(test_result)

        results["success_rate"] = (
            (results["passed_tests"] / results["total_tests"] * 100) if results["total_tests"] > 0 else 0
        )

        return results

    def _execute_compatibility_test(self, endpoint_name: str, test_case: Dict[str, Any]) -> Any:
        """执行兼容性测试"""
        # 这里应该实现具体的测试逻辑
        # 模拟实现
        return {"status": "success", "migrated": True}

    def _compare_results(self, expected: Any, actual: Any) -> bool:
        """比较测试结果"""
        # 简化的结果比较
        return str(expected) == str(actual)


# 便捷函数和装饰器
def legacy_api(new_endpoint_name: str):
    """旧API装饰器的便捷函数"""
    strategy = APICompatibilityStrategy()
    return strategy.legacy_api_decorator(new_endpoint_name)


def new_api(endpoint_name: str):
    """新API装饰器的便捷函数"""
    strategy = APICompatibilityStrategy()
    return strategy.new_api_decorator(endpoint_name)


def track_api_usage(endpoint_name: str, version: str, **kwargs):
    """跟踪API使用的便捷函数"""
    strategy = APICompatibilityStrategy()
    api_version = APIVersion(version)
    strategy.track_api_usage(endpoint_name, api_version, **kwargs)


def generate_compatibility_report() -> Dict[str, Any]:
    """生成兼容性报告的便捷函数"""
    strategy = APICompatibilityStrategy()
    return strategy.generate_migration_report()


def create_migration_timeline() -> Dict[str, Any]:
    """创建迁移时间线的便捷函数"""
    strategy = APICompatibilityStrategy()
    return strategy.create_migration_timeline()
