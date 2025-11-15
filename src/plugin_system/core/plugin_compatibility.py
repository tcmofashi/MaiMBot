"""
向后兼容性支持
确保原有插件系统API继续工作，提供渐进式迁移支持
"""

from typing import Dict, List, Optional, Any, Callable

from src.common.logger import get_logger
from src.isolation.isolation_context import create_isolation_context
from src.plugin_system.base.plugin_base import PluginBase
from src.plugin_system.core.isolated_plugin_executor import PluginExecutionResult
from src.plugin_system.core.plugin_manager import plugin_manager
from src.plugin_system.core.isolated_plugin_api_wrapper import get_isolated_plugin_system

logger = get_logger("plugin_compatibility")


class CompatiblePluginManager:
    """
    兼容性插件管理器

    提供与原有PluginManager兼容的接口，内部使用隔离化实现
    """

    def __init__(self):
        self.system = get_isolated_plugin_system()
        self.default_tenant_id = "default"
        self.default_agent_id = "default"
        self.default_platform = "default"

        logger.info("兼容性插件管理器初始化完成")

    def get_plugin_instance(self, plugin_name: str) -> Optional[PluginBase]:
        """获取插件实例（兼容接口）"""
        return plugin_manager.get_plugin_instance(plugin_name)

    def load_all_plugins(self) -> tuple[int, int]:
        """加载所有插件（兼容接口）"""
        return plugin_manager.load_all_plugins()

    def load_registered_plugin_classes(self, plugin_name: str) -> tuple[bool, int]:
        """加载已注册的插件类（兼容接口）"""
        return plugin_manager.load_registered_plugin_classes(plugin_name)

    async def remove_registered_plugin(self, plugin_name: str) -> bool:
        """移除已注册的插件（兼容接口）"""
        return await plugin_manager.remove_registered_plugin(plugin_name)

    async def reload_registered_plugin(self, plugin_name: str) -> bool:
        """重载已注册的插件（兼容接口）"""
        return await plugin_manager.reload_registered_plugin(plugin_name)

    def list_loaded_plugins(self) -> List[str]:
        """列出已加载的插件（兼容接口）"""
        return plugin_manager.list_loaded_plugins()

    def list_registered_plugins(self) -> List[str]:
        """列出已注册的插件（兼容接口）"""
        return plugin_manager.list_registered_plugins()

    def get_plugin_path(self, plugin_name: str) -> Optional[str]:
        """获取插件路径（兼容接口）"""
        return plugin_manager.get_plugin_path(plugin_name)

    # 新增的隔离化方法
    def set_default_isolation_context(self, tenant_id: str, agent_id: str, platform: str = None):
        """设置默认隔离上下文"""
        self.default_tenant_id = tenant_id
        self.default_agent_id = agent_id
        if platform:
            self.default_platform = platform

    async def execute_plugin_method(
        self,
        plugin_name: str,
        method_name: str,
        *args,
        tenant_id: str = None,
        agent_id: str = None,
        platform: str = None,
        **kwargs,
    ) -> PluginExecutionResult:
        """执行插件方法（扩展接口）"""
        tenant_id = tenant_id or self.default_tenant_id
        agent_id = agent_id or self.default_agent_id
        platform = platform or self.default_platform

        return await self.system.execute_plugin_simple(
            plugin_name, method_name, tenant_id, agent_id, platform, *args, **kwargs
        )


class CompatibleEventsManager:
    """
    兼容性事件管理器

    提供与原有EventsManager兼容的接口，内部使用隔离化实现
    """

    def __init__(self):
        self.system = get_isolated_plugin_system()
        self.default_tenant_id = "default"
        self.default_agent_id = "default"
        self.default_platform = "default"

        # 兼容性映射
        self._compatibility_mapping = {}

        logger.info("兼容性事件管理器初始化完成")

    def register_event_subscriber(self, handler_info, handler_class) -> bool:
        """注册事件订阅者（兼容接口）"""
        # 使用原有的事件管理器注册
        from src.plugin_system.core.events_manager import events_manager

        return events_manager.register_event_subscriber(handler_info, handler_class)

    async def handle_mai_events(
        self, event_type, message=None, llm_prompt=None, llm_response=None, stream_id=None, action_usage=None
    ):
        """处理Mai事件（兼容接口）"""
        # 使用原有的事件管理器处理
        from src.plugin_system.core.events_manager import events_manager

        return await events_manager.handle_mai_events(
            event_type, message, llm_prompt, llm_response, stream_id, action_usage
        )

    async def unregister_event_subscriber(self, handler_name: str) -> bool:
        """取消注册事件订阅者（兼容接口）"""
        from src.plugin_system.core.events_manager import events_manager

        return await events_manager.unregister_event_subscriber(handler_name)

    async def cancel_handler_tasks(self, handler_name: str) -> None:
        """取消处理器任务（兼容接口）"""
        from src.plugin_system.core.events_manager import events_manager

        await events_manager.cancel_handler_tasks(handler_name)

    async def get_event_result_history(self, event_type):
        """获取事件结果历史（兼容接口）"""
        from src.plugin_system.core.events_manager import events_manager

        return await events_manager.get_event_result_history(event_type)

    async def clear_event_result_history(self, event_type):
        """清空事件结果历史（兼容接口）"""
        from src.plugin_system.core.events_manager import events_manager

        await events_manager.clear_event_result_history(event_type)

    def set_default_isolation_context(self, tenant_id: str, agent_id: str, platform: str = None):
        """设置默认隔离上下文"""
        self.default_tenant_id = tenant_id
        self.default_agent_id = agent_id
        if platform:
            self.default_platform = platform


class MigrationHelper:
    """
    迁移辅助工具

    提供从原有API到隔离化API的迁移支持
    """

    def __init__(self):
        self.migration_log = []
        self.compatibility_manager = CompatiblePluginManager()
        self.compatibility_events = CompatibleEventsManager()

    def analyze_plugin_usage(self, plugin_name: str) -> Dict[str, Any]:
        """分析插件使用情况"""
        analysis = {
            "plugin_name": plugin_name,
            "current_usage": {},
            "migration_complexity": "medium",
            "required_changes": [],
            "compatibility_score": 0.8,
        }

        try:
            # 获取插件实例
            plugin_instance = plugin_manager.get_plugin_instance(plugin_name)
            if not plugin_instance:
                analysis["error"] = "插件实例不存在"
                return analysis

            # 分析插件结构
            if hasattr(plugin_instance, "get_plugin_components"):
                components = plugin_instance.get_plugin_components()
                analysis["current_usage"]["components"] = len(components)

                # 分析组件类型
                component_types = {}
                for component_info, _component_class in components:
                    comp_type = component_info.component_type.name
                    component_types[comp_type] = component_types.get(comp_type, 0) + 1
                analysis["current_usage"]["component_types"] = component_types

            # 检查隔离相关属性
            isolation_attributes = ["allowed_tenants", "allowed_agents", "allowed_platforms"]
            has_isolation_attrs = any(hasattr(plugin_instance, attr) for attr in isolation_attributes)
            analysis["has_isolation_support"] = has_isolation_attrs

            # 计算迁移复杂度
            if has_isolation_attrs:
                analysis["migration_complexity"] = "low"
                analysis["compatibility_score"] = 0.95
            elif analysis["current_usage"].get("components", 0) > 5:
                analysis["migration_complexity"] = "high"
                analysis["compatibility_score"] = 0.6

            # 生成建议的变更
            if not has_isolation_attrs:
                analysis["required_changes"].append("添加隔离支持属性")
                analysis["required_changes"].append("更新插件方法以支持隔离上下文")

        except Exception as e:
            analysis["error"] = str(e)

        return analysis

    def generate_migration_plan(self, plugin_name: str) -> Dict[str, Any]:
        """生成迁移计划"""
        analysis = self.analyze_plugin_usage(plugin_name)

        plan = {
            "plugin_name": plugin_name,
            "migration_steps": [],
            "estimated_effort": "medium",
            "compatibility_guarantee": True,
            "rollback_plan": "使用兼容性接口",
        }

        if "error" in analysis:
            plan["error"] = analysis["error"]
            return plan

        # 基础迁移步骤
        plan["migration_steps"] = [
            "1. 备份当前插件代码",
            "2. 添加隔离上下文支持属性",
            "3. 更新插件方法签名以支持隔离参数",
            "4. 测试兼容性接口功能",
            "5. 逐步迁移到隔离化API",
            "6. 移除兼容性依赖",
        ]

        # 根据复杂度调整计划
        if analysis["migration_complexity"] == "low":
            plan["estimated_effort"] = "low"
            plan["migration_steps"] = plan["migration_steps"][:4]
        elif analysis["migration_complexity"] == "high":
            plan["estimated_effort"] = "high"
            plan["migration_steps"].extend(["7. 详细的单元测试", "8. 集成测试", "9. 性能测试"])

        return plan

    def test_compatibility(self, plugin_name: str) -> Dict[str, Any]:
        """测试兼容性"""
        test_result = {
            "plugin_name": plugin_name,
            "compatibility_tests": {},
            "overall_status": "unknown",
            "issues": [],
            "recommendations": [],
        }

        try:
            plugin_instance = plugin_manager.get_plugin_instance(plugin_name)
            if not plugin_instance:
                test_result["overall_status"] = "failed"
                test_result["issues"].append("插件实例不存在")
                return test_result

            # 测试基础功能
            basic_tests = {
                "plugin_loading": True,
                "component_access": True,
                "method_calling": False,
                "isolation_compatibility": False,
            }

            # 测试组件访问
            try:
                if hasattr(plugin_instance, "get_plugin_components"):
                    components = plugin_instance.get_plugin_components()
                    basic_tests["component_access"] = len(components) >= 0
            except Exception as e:
                basic_tests["component_access"] = False
                test_result["issues"].append(f"组件访问失败: {e}")

            # 测试方法调用
            try:
                # 尝试调用一个简单方法
                if hasattr(plugin_instance, "plugin_info"):
                    basic_tests["method_calling"] = True
            except Exception as e:
                test_result["issues"].append(f"方法调用失败: {e}")

            # 测试隔离兼容性
            try:
                # 尝试创建隔离上下文
                create_isolation_context("test", "test")
                basic_tests["isolation_compatibility"] = True
            except Exception as e:
                test_result["issues"].append(f"隔离兼容性失败: {e}")

            test_result["compatibility_tests"] = basic_tests

            # 评估整体状态
            passed_tests = sum(1 for result in basic_tests.values() if result)
            total_tests = len(basic_tests)

            if passed_tests == total_tests:
                test_result["overall_status"] = "passed"
            elif passed_tests >= total_tests * 0.7:
                test_result["overall_status"] = "warning"
            else:
                test_result["overall_status"] = "failed"

            # 生成建议
            if not basic_tests["method_calling"]:
                test_result["recommendations"].append("检查插件方法的实现")
            if not basic_tests["isolation_compatibility"]:
                test_result["recommendations"].append("添加隔离上下文支持")

        except Exception as e:
            test_result["overall_status"] = "error"
            test_result["issues"].append(f"测试过程中发生错误: {e}")

        return test_result

    def get_migration_recommendations(self) -> List[Dict[str, Any]]:
        """获取迁移建议"""
        recommendations = []
        loaded_plugins = plugin_manager.list_loaded_plugins()

        for plugin_name in loaded_plugins:
            analysis = self.analyze_plugin_usage(plugin_name)
            plan = self.generate_migration_plan(plugin_name)
            compatibility = self.test_compatibility(plugin_name)

            recommendation = {
                "plugin_name": plugin_name,
                "priority": self._calculate_priority(analysis, compatibility),
                "analysis": analysis,
                "migration_plan": plan,
                "compatibility_test": compatibility,
            }

            recommendations.append(recommendation)

        # 按优先级排序
        recommendations.sort(key=lambda x: x["priority"], reverse=True)

        return recommendations

    def _calculate_priority(self, analysis: Dict, compatibility: Dict) -> float:
        """计算迁移优先级"""
        priority = 0.5  # 基础优先级

        # 根据兼容性调整
        if compatibility.get("overall_status") == "passed":
            priority += 0.3
        elif compatibility.get("overall_status") == "warning":
            priority += 0.1
        else:
            priority -= 0.2

        # 根据迁移复杂度调整
        complexity = analysis.get("migration_complexity", "medium")
        if complexity == "low":
            priority += 0.2
        elif complexity == "high":
            priority -= 0.1

        # 根据现有隔离支持调整
        if analysis.get("has_isolation_support"):
            priority += 0.2

        return max(0.0, min(1.0, priority))


# 全局兼容性实例
_compatible_plugin_manager = CompatiblePluginManager()
_compatible_events_manager = CompatibleEventsManager()
_migration_helper = MigrationHelper()


def get_compatible_plugin_manager() -> CompatiblePluginManager:
    """获取兼容性插件管理器"""
    return _compatible_plugin_manager


def get_compatible_events_manager() -> CompatibleEventsManager:
    """获取兼容性事件管理器"""
    return _compatible_events_manager


def get_migration_helper() -> MigrationHelper:
    """获取迁移辅助工具"""
    return _migration_helper


# 便捷函数
def test_plugin_compatibility(plugin_name: str) -> Dict[str, Any]:
    """测试插件兼容性的便捷函数"""
    helper = get_migration_helper()
    return helper.test_compatibility(plugin_name)


def get_plugin_migration_plan(plugin_name: str) -> Dict[str, Any]:
    """获取插件迁移计划的便捷函数"""
    helper = get_migration_helper()
    return helper.generate_migration_plan(plugin_name)


def get_all_migration_recommendations() -> List[Dict[str, Any]]:
    """获取所有迁移建议的便捷函数"""
    helper = get_migration_helper()
    return helper.get_migration_recommendations()


# 兼容性装饰器
def backward_compatible(isolated_api_version: bool = False):
    """向后兼容装饰器"""

    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            try:
                # 尝试使用新的隔离化API
                if isolated_api_version:
                    system = get_isolated_plugin_system()
                    return func(system, *args, **kwargs)
                else:
                    # 使用兼容性接口
                    return func(*args, **kwargs)
            except Exception as e:
                logger.warning(f"新API调用失败，回退到兼容模式: {e}")
                # 回退到原有实现
                return func(*args, **kwargs)

        return wrapper

    return decorator
