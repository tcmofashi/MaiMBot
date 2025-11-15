"""
消息路由和分发系统
实现基于租户、智能体、平台的消息过滤和路由规则
"""

import asyncio
import re
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import fnmatch

from .multi_tenant_adapter import MessagePriority
from ..common.logger import get_logger

logger = get_logger("message_router")


class RouteTarget(Enum):
    """路由目标类型"""

    TENANT = "tenant"
    AGENT = "agent"
    PLATFORM = "platform"
    CHAT_STREAM = "chat_stream"
    BROADCAST = "broadcast"


@dataclass
class RouteRule:
    """路由规则"""

    rule_id: str
    name: str
    target_type: RouteTarget
    target_pattern: str  # 支持通配符模式
    conditions: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    hit_count: int = 0
    last_hit: Optional[datetime] = None

    def matches(self, context: Dict[str, Any]) -> bool:
        """检查规则是否匹配"""
        try:
            # 检查目标模式匹配
            if not self._match_target(context):
                return False

            # 检查条件匹配
            return self._match_conditions(context)

        except Exception as e:
            logger.warning(f"规则匹配检查失败 {self.rule_id}: {e}")
            return False

    def _match_target(self, context: Dict[str, Any]) -> bool:
        """检查目标匹配"""
        if self.target_type == RouteTarget.TENANT:
            tenant_id = context.get("tenant_id", "")
            return fnmatch.fnmatch(tenant_id, self.target_pattern)

        elif self.target_type == RouteTarget.AGENT:
            agent_id = context.get("agent_id", "")
            return fnmatch.fnmatch(agent_id, self.target_pattern)

        elif self.target_type == RouteTarget.PLATFORM:
            platform = context.get("platform", "")
            return fnmatch.fnmatch(platform, self.target_pattern)

        elif self.target_type == RouteTarget.CHAT_STREAM:
            chat_stream_id = context.get("chat_stream_id", "")
            return fnmatch.fnmatch(chat_stream_id, self.target_pattern)

        elif self.target_type == RouteTarget.BROADCAST:
            return True  # 广播规则总是匹配

        return False

    def _match_conditions(self, context: Dict[str, Any]) -> bool:
        """检查条件匹配"""
        for key, expected_value in self.conditions.items():
            actual_value = context.get(key)

            if isinstance(expected_value, dict):
                # 复杂条件
                if not self._match_complex_condition(actual_value, expected_value):
                    return False
            elif isinstance(expected_value, (list, tuple)):
                # 列表条件（包含检查）
                if actual_value not in expected_value:
                    return False
            elif isinstance(expected_value, str):
                # 字符串条件（支持正则）
                if "*" in expected_value or "?" in expected_value:
                    if not fnmatch.fnmatch(str(actual_value), expected_value):
                        return False
                else:
                    if str(actual_value) != expected_value:
                        return False
            else:
                # 直接比较
                if actual_value != expected_value:
                    return False

        return True

    def _match_complex_condition(self, actual: Any, condition: Dict[str, Any]) -> bool:
        """匹配复杂条件"""
        op = condition.get("op", "eq")
        value = condition.get("value")

        if op == "eq":
            return actual == value
        elif op == "ne":
            return actual != value
        elif op == "gt":
            return actual > value
        elif op == "gte":
            return actual >= value
        elif op == "lt":
            return actual < value
        elif op == "lte":
            return actual <= value
        elif op == "in":
            return actual in value
        elif op == "not_in":
            return actual not in value
        elif op == "contains":
            return value in str(actual)
        elif op == "regex":
            return bool(re.search(value, str(actual)))
        elif op == "exists":
            return actual is not None
        elif op == "not_exists":
            return actual is None

        return False

    def update_hit_stats(self):
        """更新命中统计"""
        self.hit_count += 1
        self.last_hit = datetime.now()


@dataclass
class RouteAction:
    """路由动作"""

    action_id: str
    name: str
    action_type: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


@dataclass
class QueuedMessage:
    """队列消息"""

    message_id: str
    message_data: Dict[str, Any]
    context: Dict[str, Any]
    priority: MessagePriority
    timestamp: datetime
    retry_count: int = 0
    max_retries: int = 3
    expires_at: Optional[datetime] = None


class MessageRouter:
    """消息路由器"""

    def __init__(self):
        # 路由规则管理
        self.rules: Dict[str, RouteRule] = {}
        self.rule_priorities: List[str] = []  # 按优先级排序的规则ID

        # 路由动作
        self.actions: Dict[str, RouteAction] = {}

        # 消息队列
        self.queues: Dict[str, asyncio.Queue] = {
            "high": asyncio.Queue(maxsize=1000),
            "normal": asyncio.Queue(maxsize=5000),
            "low": asyncio.Queue(maxsize=10000),
        }

        # 路由表缓存
        self.route_cache: Dict[str, List[str]] = {}
        self.cache_enabled = True
        self.cache_max_size = 1000

        # 统计信息
        self.stats = {
            "messages_routed": 0,
            "rules_matched": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "queues_full": 0,
            "actions_executed": 0,
            "errors": 0,
        }

        # 任务管理
        self._processor_tasks: List[asyncio.Task] = []
        self._running = False

        # 默认动作
        self._setup_default_actions()

    def _setup_default_actions(self):
        """设置默认动作"""
        # 转发到租户
        self.actions["forward_to_tenant"] = RouteAction(
            action_id="forward_to_tenant", name="转发到租户", action_type="forward", parameters={"target": "tenant"}
        )

        # 转发到智能体
        self.actions["forward_to_agent"] = RouteAction(
            action_id="forward_to_agent", name="转发到智能体", action_type="forward", parameters={"target": "agent"}
        )

        # 广播到平台
        self.actions["broadcast_to_platform"] = RouteAction(
            action_id="broadcast_to_platform",
            name="广播到平台",
            action_type="broadcast",
            parameters={"target": "platform"},
        )

        # 丢弃消息
        self.actions["drop_message"] = RouteAction(action_id="drop_message", name="丢弃消息", action_type="drop")

        # 记录日志
        self.actions["log_message"] = RouteAction(action_id="log_message", name="记录日志", action_type="log")

    def add_rule(self, rule: RouteRule):
        """添加路由规则"""
        self.rules[rule.rule_id] = rule

        # 重新排序规则优先级
        self._reorder_rules()

        # 清理缓存
        self._clear_cache()

        logger.info(f"添加路由规则: {rule.name} ({rule.rule_id})")

    def remove_rule(self, rule_id: str):
        """移除路由规则"""
        if rule_id in self.rules:
            del self.rules[rule_id]
            self._reorder_rules()
            self._clear_cache()
            logger.info(f"移除路由规则: {rule_id}")

    def update_rule(self, rule_id: str, **kwargs):
        """更新路由规则"""
        if rule_id in self.rules:
            rule = self.rules[rule_id]
            for key, value in kwargs.items():
                if hasattr(rule, key):
                    setattr(rule, key, value)
            self._reorder_rules()
            self._clear_cache()
            logger.info(f"更新路由规则: {rule_id}")

    def _reorder_rules(self):
        """重新排序规则优先级"""
        sorted_rules = sorted(self.rules.values(), key=lambda r: (-r.priority, r.created_at))
        self.rule_priorities = [rule.rule_id for rule in sorted_rules]

    def add_action(self, action: RouteAction):
        """添加路由动作"""
        self.actions[action.action_id] = action
        logger.info(f"添加路由动作: {action.name} ({action.action_id})")

    def remove_action(self, action_id: str):
        """移除路由动作"""
        if action_id in self.actions:
            del self.actions[action_id]
            logger.info(f"移除路由动作: {action_id}")

    def route_message(
        self, message_data: Dict[str, Any], context: Dict[str, Any], priority: MessagePriority = MessagePriority.NORMAL
    ) -> List[str]:
        """路由消息，返回匹配的动作ID列表"""
        try:
            self.stats["messages_routed"] += 1

            # 生成缓存键
            cache_key = self._generate_cache_key(context)

            # 检查缓存
            if self.cache_enabled and cache_key in self.route_cache:
                self.stats["cache_hits"] += 1
                matched_rule_ids = self.route_cache[cache_key]
            else:
                self.stats["cache_misses"] += 1
                matched_rule_ids = self._find_matching_rules(context)

                # 更新缓存
                if self.cache_enabled:
                    self._update_cache(cache_key, matched_rule_ids)

            # 获取动作列表
            action_ids = []
            for rule_id in matched_rule_ids:
                rule = self.rules[rule_id]
                rule.update_hit_stats()
                self.stats["rules_matched"] += 1

                # 获取规则关联的动作
                rule_actions = context.get("rule_actions", {}).get(rule_id, [])
                action_ids.extend(rule_actions)

            # 如果没有匹配的规则，使用默认动作
            if not action_ids:
                action_ids = self._get_default_actions(context)

            # 将消息加入队列
            self._queue_message(message_data, context, priority, action_ids)

            return action_ids

        except Exception as e:
            logger.error(f"消息路由失败: {e}")
            self.stats["errors"] += 1
            return []

    def _find_matching_rules(self, context: Dict[str, Any]) -> List[str]:
        """查找匹配的规则"""
        matched_rules = []
        for rule_id in self.rule_priorities:
            rule = self.rules[rule_id]
            if rule.enabled and rule.matches(context):
                matched_rules.append(rule_id)
        return matched_rules

    def _generate_cache_key(self, context: Dict[str, Any]) -> str:
        """生成缓存键"""
        key_parts = [
            context.get("tenant_id", ""),
            context.get("agent_id", ""),
            context.get("platform", ""),
            context.get("chat_stream_id", ""),
            str(context.get("message_type", "")),
        ]
        return "|".join(key_parts)

    def _update_cache(self, cache_key: str, rule_ids: List[str]):
        """更新缓存"""
        if len(self.route_cache) >= self.cache_max_size:
            # 简单的LRU：清理一半缓存
            keys_to_remove = list(self.route_cache.keys())[: self.cache_max_size // 2]
            for key in keys_to_remove:
                del self.route_cache[key]

        self.route_cache[cache_key] = rule_ids

    def _clear_cache(self):
        """清理缓存"""
        self.route_cache.clear()

    def _get_default_actions(self, context: Dict[str, Any]) -> List[str]:
        """获取默认动作"""
        tenant_id = context.get("tenant_id")
        agent_id = context.get("agent_id")

        if tenant_id:
            return ["forward_to_tenant"]
        elif agent_id:
            return ["forward_to_agent"]
        else:
            return ["drop_message"]

    def _queue_message(
        self, message_data: Dict[str, Any], context: Dict[str, Any], priority: MessagePriority, action_ids: List[str]
    ):
        """将消息加入队列"""
        try:
            message_id = f"{datetime.now().timestamp()}-{id(message_data)}"
            queued_message = QueuedMessage(
                message_id=message_id,
                message_data=message_data,
                context=context,
                priority=priority,
                timestamp=datetime.now(),
                expires_at=datetime.now() + timedelta(minutes=30),  # 30分钟过期
            )

            # 选择队列
            queue_name = "normal"
            if priority == MessagePriority.HIGH or priority == MessagePriority.URGENT:
                queue_name = "high"
            elif priority == MessagePriority.LOW:
                queue_name = "low"

            queue = self.queues[queue_name]
            try:
                queue.put_nowait((queued_message, action_ids))
            except asyncio.QueueFull:
                logger.warning(f"消息队列已满: {queue_name}")
                self.stats["queues_full"] += 1

        except Exception as e:
            logger.error(f"消息入队失败: {e}")
            self.stats["errors"] += 1

    async def start_processors(self, num_workers: int = 3):
        """启动消息处理器"""
        self._running = True

        # 为每个优先级队列启动处理器
        for queue_name in ["high", "normal", "low"]:
            for i in range(num_workers):
                task = asyncio.create_task(self._message_processor(queue_name, f"{queue_name}-worker-{i}"))
                self._processor_tasks.append(task)

        logger.info(f"启动消息处理器: {len(self._processor_tasks)} 个任务")

    async def stop_processors(self):
        """停止消息处理器"""
        self._running = False

        # 等待所有任务完成
        for task in self._processor_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._processor_tasks.clear()
        logger.info("消息处理器已停止")

    async def _message_processor(self, queue_name: str, worker_name: str):
        """消息处理器"""
        queue = self.queues[queue_name]
        logger.info(f"消息处理器启动: {worker_name}")

        while self._running:
            try:
                # 获取消息
                try:
                    queued_message, action_ids = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                # 检查消息是否过期
                if queued_message.expires_at and datetime.now() > queued_message.expires_at:
                    logger.warning(f"消息已过期，丢弃: {queued_message.message_id}")
                    queue.task_done()
                    continue

                # 执行动作
                await self._execute_actions(queued_message, action_ids)
                queue.task_done()

            except Exception as e:
                logger.error(f"消息处理器异常 {worker_name}: {e}")
                self.stats["errors"] += 1

        logger.info(f"消息处理器停止: {worker_name}")

    async def _execute_actions(self, queued_message: QueuedMessage, action_ids: List[str]):
        """执行路由动作"""
        for action_id in action_ids:
            if action_id not in self.actions:
                logger.warning(f"未找到动作: {action_id}")
                continue

            action = self.actions[action_id]
            if not action.enabled:
                continue

            try:
                await self._execute_single_action(queued_message, action)
                self.stats["actions_executed"] += 1

            except Exception as e:
                logger.error(f"执行动作失败 {action_id}: {e}")
                self.stats["errors"] += 1

                # 检查是否需要重试
                if queued_message.retry_count < queued_message.max_retries:
                    queued_message.retry_count += 1
                    # 重新加入队列
                    self._queue_message(
                        queued_message.message_data, queued_message.context, queued_message.priority, [action_id]
                    )
                    logger.info(f"消息重试: {queued_message.message_id} (第{queued_message.retry_count}次)")

    async def _execute_single_action(self, queued_message: QueuedMessage, action: RouteAction):
        """执行单个动作"""
        action_type = action.action_type
        message_data = queued_message.message_data
        context = queued_message.context

        if action_type == "forward":
            target = action.parameters.get("target")
            if target == "tenant":
                await self._forward_to_tenant(message_data, context)
            elif target == "agent":
                await self._forward_to_agent(message_data, context)
            elif target == "platform":
                await self._forward_to_platform(message_data, context)

        elif action_type == "broadcast":
            await self._broadcast_message(message_data, context)

        elif action_type == "drop":
            # 丢弃消息，无需额外操作
            pass

        elif action_type == "log":
            logger.info(f"路由日志: {message_data}")

        elif action_type == "custom":
            # 自定义动作
            custom_handler = action.parameters.get("handler")
            if custom_handler and callable(custom_handler):
                await custom_handler(queued_message)

    async def _forward_to_tenant(self, message_data: Dict[str, Any], context: Dict[str, Any]):
        """转发到租户"""
        # 这里需要集成到实际的多租户系统
        tenant_id = context.get("tenant_id")
        logger.debug(f"转发消息到租户: {tenant_id}")

    async def _forward_to_agent(self, message_data: Dict[str, Any], context: Dict[str, Any]):
        """转发到智能体"""
        agent_id = context.get("agent_id")
        logger.debug(f"转发消息到智能体: {agent_id}")

    async def _forward_to_platform(self, message_data: Dict[str, Any], context: Dict[str, Any]):
        """转发到平台"""
        platform = context.get("platform")
        logger.debug(f"转发消息到平台: {platform}")

    async def _broadcast_message(self, message_data: Dict[str, Any], context: Dict[str, Any]):
        """广播消息"""
        platform = context.get("platform")
        logger.debug(f"广播消息到平台: {platform}")

    def get_stats(self) -> Dict[str, Any]:
        """获取路由器统计信息"""
        return self.stats.copy()

    def get_rule_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取规则统计信息"""
        return {
            rule_id: {
                "name": rule.name,
                "hit_count": rule.hit_count,
                "last_hit": rule.last_hit.isoformat() if rule.last_hit else None,
                "enabled": rule.enabled,
            }
            for rule_id, rule in self.rules.items()
        }

    def export_rules(self) -> List[Dict[str, Any]]:
        """导出路由规则"""
        return [
            {
                "rule_id": rule.rule_id,
                "name": rule.name,
                "target_type": rule.target_type.value,
                "target_pattern": rule.target_pattern,
                "conditions": rule.conditions,
                "priority": rule.priority,
                "enabled": rule.enabled,
            }
            for rule in self.rules.values()
        ]

    def import_rules(self, rules_data: List[Dict[str, Any]]):
        """导入路由规则"""
        for rule_data in rules_data:
            try:
                rule = RouteRule(
                    rule_id=rule_data["rule_id"],
                    name=rule_data["name"],
                    target_type=RouteTarget(rule_data["target_type"]),
                    target_pattern=rule_data["target_pattern"],
                    conditions=rule_data.get("conditions", {}),
                    priority=rule_data.get("priority", 0),
                    enabled=rule_data.get("enabled", True),
                )
                self.add_rule(rule)
            except Exception as e:
                logger.error(f"导入路由规则失败: {e}")


# 全局消息路由器实例
_global_message_router: Optional[MessageRouter] = None


def get_message_router() -> MessageRouter:
    """获取全局消息路由器"""
    global _global_message_router
    if _global_message_router is None:
        _global_message_router = MessageRouter()
    return _global_message_router


async def start_message_router(num_workers: int = 3):
    """启动消息路由器"""
    router = get_message_router()
    await router.start_processors(num_workers)


async def stop_message_router():
    """停止消息路由器"""
    router = get_message_router()
    await router.stop_processors()
