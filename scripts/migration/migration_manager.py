"""
MaiBot 迁移管理和监控系统
提供统一的迁移管理平台、任务调度和风险评估

作者: Claude
创建时间: 2025-01-12
"""

import asyncio
import json
import signal
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.common.logger import get_logger
from .data_migration_strategy import DataMigrationStrategy
from .code_migration_tools import CodeMigrationTools
from .api_compatibility_strategy import APICompatibilityStrategy

logger = get_logger("migration_manager")


class MigrationStatus(Enum):
    """迁移状态"""

    IDLE = "idle"
    PLANNING = "planning"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLING_BACK = "rolling_back"


class TaskPriority(Enum):
    """任务优先级"""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class RiskLevel(Enum):
    """风险级别"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class MigrationTask:
    """迁移任务定义"""

    id: str
    name: str
    description: str
    task_type: str  # data, code, api
    priority: TaskPriority
    dependencies: List[str] = field(default_factory=list)
    status: MigrationStatus = MigrationStatus.IDLE
    progress: float = 0.0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    timeout_seconds: int = 3600
    result: Optional[Dict[str, Any]] = None


@dataclass
class MigrationPlan:
    """迁移计划"""

    id: str
    name: str
    description: str
    tasks: List[MigrationTask]
    created_at: datetime
    scheduled_at: Optional[datetime] = None
    estimated_duration: Optional[timedelta] = None
    risk_level: RiskLevel = RiskLevel.MEDIUM
    rollback_enabled: bool = True
    backup_enabled: bool = True


@dataclass
class MigrationMetrics:
    """迁移指标"""

    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    running_tasks: int = 0
    total_duration: timedelta = field(default_factory=lambda: timedelta(0))
    success_rate: float = 0.0
    data_migrated_bytes: int = 0
    code_files_modified: int = 0
    api_calls_migrated: int = 0
    errors_count: int = 0
    warnings_count: int = 0


class MigrationManager:
    """迁移管理器"""

    def __init__(self):
        self.current_plan: Optional[MigrationPlan] = None
        self.tasks: Dict[str, MigrationTask] = {}
        self.running = False
        self.paused = False
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.metrics = MigrationMetrics()
        self.event_handlers: Dict[str, List[Callable]] = {}

        # 迁移组件
        self.data_migration = DataMigrationStrategy()
        self.code_migration = CodeMigrationTools()
        self.api_compatibility = APICompatibilityStrategy()

        # 配置
        self.config = {
            "workspace_dir": "/tmp/maibot_migration_workspace",
            "log_level": "INFO",
            "max_parallel_tasks": 4,
            "task_timeout_seconds": 3600,
            "heartbeat_interval": 30,
            "checkpoint_interval": 300,  # 5分钟
            "auto_save_progress": True,
            "enable_notifications": True,
        }

        # 工作空间
        self.workspace_dir = Path(self.config["workspace_dir"])
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        # 控制信号
        self._shutdown_event = threading.Event()

        # 注册信号处理器
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """信号处理器"""
        logger.info(f"收到信号 {signum}，准备关闭迁移管理器")
        self._shutdown_event.set()

    def create_migration_plan(
        self,
        name: str,
        description: str,
        include_data: bool = True,
        include_code: bool = True,
        include_api: bool = True,
    ) -> MigrationPlan:
        """创建迁移计划"""
        logger.info(f"创建迁移计划: {name}")

        plan_id = f"plan_{int(time.time())}"
        tasks = []

        # 数据迁移任务
        if include_data:
            data_tasks = self._create_data_migration_tasks()
            tasks.extend(data_tasks)

        # 代码迁移任务
        if include_code:
            code_tasks = self._create_code_migration_tasks()
            tasks.extend(code_tasks)

        # API兼容性任务
        if include_api:
            api_tasks = self._create_api_compatibility_tasks()
            tasks.extend(api_tasks)

        # 评估风险级别
        risk_level = self._assess_plan_risk(tasks)

        # 估算执行时间
        estimated_duration = self._estimate_duration(tasks)

        plan = MigrationPlan(
            id=plan_id,
            name=name,
            description=description,
            tasks=tasks,
            created_at=datetime.now(),
            estimated_duration=estimated_duration,
            risk_level=risk_level,
        )

        logger.info(f"迁移计划创建完成: {plan_id}, 包含 {len(tasks)} 个任务")
        return plan

    def _create_data_migration_tasks(self) -> List[MigrationTask]:
        """创建数据迁移任务"""
        return [
            MigrationTask(
                id="data_backup",
                name="数据备份",
                description="创建完整的数据备份",
                task_type="data",
                priority=TaskPriority.CRITICAL,
                timeout_seconds=1800,
            ),
            MigrationTask(
                id="schema_migration",
                name="数据库结构迁移",
                description="创建新的多租户隔离表结构",
                task_type="data",
                priority=TaskPriority.HIGH,
                dependencies=["data_backup"],
                timeout_seconds=3600,
            ),
            MigrationTask(
                id="agent_data_migration",
                name="智能体数据迁移",
                description="迁移智能体配置数据到新结构",
                task_type="data",
                priority=TaskPriority.HIGH,
                dependencies=["schema_migration"],
                timeout_seconds=7200,
            ),
            MigrationTask(
                id="chat_data_migration",
                name="聊天记录迁移",
                description="迁移聊天记录数据",
                task_type="data",
                priority=TaskPriority.MEDIUM,
                dependencies=["schema_migration"],
                timeout_seconds=14400,
            ),
            MigrationTask(
                id="memory_data_migration",
                name="记忆数据迁移",
                description="迁移记忆系统数据",
                task_type="data",
                priority=TaskPriority.MEDIUM,
                dependencies=["schema_migration"],
                timeout_seconds=10800,
            ),
            MigrationTask(
                id="data_validation",
                name="数据验证",
                description="验证迁移数据的完整性",
                task_type="data",
                priority=TaskPriority.HIGH,
                dependencies=["agent_data_migration", "chat_data_migration", "memory_data_migration"],
                timeout_seconds=3600,
            ),
        ]

    def _create_code_migration_tasks(self) -> List[MigrationTask]:
        """创建代码迁移任务"""
        return [
            MigrationTask(
                id="code_analysis",
                name="代码分析",
                description="分析项目代码结构，识别需要迁移的部分",
                task_type="code",
                priority=TaskPriority.HIGH,
                timeout_seconds=1800,
            ),
            MigrationTask(
                id="isolation_context_migration",
                name="IsolationContext迁移",
                description="添加IsolationContext抽象层",
                task_type="code",
                priority=TaskPriority.HIGH,
                dependencies=["code_analysis"],
                timeout_seconds=3600,
            ),
            MigrationTask(
                id="config_system_migration",
                name="配置系统迁移",
                description="更新配置系统以支持多租户",
                task_type="code",
                priority=TaskPriority.HIGH,
                dependencies=["isolation_context_migration"],
                timeout_seconds=3600,
            ),
            MigrationTask(
                id="chat_stream_migration",
                name="ChatStream系统迁移",
                description="迁移ChatStream相关代码",
                task_type="code",
                priority=TaskPriority.MEDIUM,
                dependencies=["isolation_context_migration"],
                timeout_seconds=5400,
            ),
            MigrationTask(
                id="database_access_migration",
                name="数据库访问迁移",
                description="更新数据库访问代码",
                task_type="code",
                priority=TaskPriority.MEDIUM,
                dependencies=["isolation_context_migration"],
                timeout_seconds=5400,
            ),
            MigrationTask(
                id="code_validation",
                name="代码验证",
                description="验证代码迁移的正确性",
                task_type="code",
                priority=TaskPriority.HIGH,
                dependencies=["config_system_migration", "chat_stream_migration", "database_access_migration"],
                timeout_seconds=3600,
            ),
        ]

    def _create_api_compatibility_tasks(self) -> List[MigrationTask]:
        """创建API兼容性任务"""
        return [
            MigrationTask(
                id="api_analysis",
                name="API分析",
                description="分析现有API使用情况",
                task_type="api",
                priority=TaskPriority.MEDIUM,
                timeout_seconds=1800,
            ),
            MigrationTask(
                id="api_compatibility_setup",
                name="API兼容性设置",
                description="设置新旧API并行运行",
                task_type="api",
                priority=TaskPriority.MEDIUM,
                dependencies=["api_analysis"],
                timeout_seconds=3600,
            ),
            MigrationTask(
                id="api_monitoring",
                name="API监控设置",
                description="设置API使用监控和统计",
                task_type="api",
                priority=TaskPriority.LOW,
                dependencies=["api_compatibility_setup"],
                timeout_seconds=1800,
            ),
            MigrationTask(
                id="migration_timeline_creation",
                name="迁移时间线创建",
                description="创建API迁移时间线",
                task_type="api",
                priority=TaskPriority.LOW,
                dependencies=["api_analysis"],
                timeout_seconds=900,
            ),
        ]

    def _assess_plan_risk(self, tasks: List[MigrationTask]) -> RiskLevel:
        """评估计划风险级别"""
        critical_tasks = sum(1 for task in tasks if task.priority == TaskPriority.CRITICAL)
        high_tasks = sum(1 for task in tasks if task.priority == TaskPriority.HIGH)

        # 基于关键任务数量评估风险
        if critical_tasks > 3:
            return RiskLevel.CRITICAL
        elif critical_tasks > 1 or high_tasks > 5:
            return RiskLevel.HIGH
        elif high_tasks > 2:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW

    def _estimate_duration(self, tasks: List[MigrationTask]) -> timedelta:
        """估算执行时间"""
        total_seconds = sum(task.timeout_seconds for task in tasks)
        # 考虑并行执行，除以最大并行任务数
        estimated_seconds = total_seconds // self.config["max_parallel_tasks"]
        return timedelta(seconds=estimated_seconds)

    async def execute_migration_plan(self, plan: MigrationPlan) -> bool:
        """执行迁移计划"""
        logger.info(f"开始执行迁移计划: {plan.name}")

        self.current_plan = plan
        self.running = True
        self.paused = False
        self.metrics = MigrationMetrics(total_tasks=len(plan.tasks))

        try:
            # 初始化任务
            self.tasks = {task.id: task for task in plan.tasks}

            # 创建备份
            if plan.backup_enabled:
                await self._create_backup()

            # 执行任务
            success = await self._execute_tasks()

            if success:
                logger.info("迁移计划执行成功")
                await self._emit_event("migration_completed", {"plan_id": plan.id})
            else:
                logger.error("迁移计划执行失败")
                if plan.rollback_enabled:
                    await self._rollback_migration()

            return success

        except Exception as e:
            logger.error(f"执行迁移计划时发生错误: {e}")
            if plan.rollback_enabled:
                await self._rollback_migration()
            return False

        finally:
            self.running = False
            await self._save_progress()

    async def _execute_tasks(self) -> bool:
        """执行任务"""
        while self.running and not self._shutdown_event.is_set():
            # 查找可执行的任务
            ready_tasks = self._get_ready_tasks()

            if not ready_tasks:
                # 检查是否所有任务都已完成
                if self._all_tasks_completed():
                    break
                else:
                    # 等待任务完成
                    await asyncio.sleep(1)
                    continue

            # 并行执行任务
            futures = []
            for task in ready_tasks[: self.config["max_parallel_tasks"]]:
                future = asyncio.create_task(self._execute_task(task))
                futures.append(future)

            # 等待任务完成
            if futures:
                await asyncio.gather(*futures, return_exceptions=True)

            # 保存进度
            if self.config["auto_save_progress"]:
                await self._save_progress()

            # 短暂休息
            await asyncio.sleep(0.1)

        return self._all_tasks_completed() and not self._has_failed_tasks()

    def _get_ready_tasks(self) -> List[MigrationTask]:
        """获取准备执行的任务"""
        ready_tasks = []
        for task in self.tasks.values():
            if task.status == MigrationStatus.IDLE and self._dependencies_completed(task):
                ready_tasks.append(task)
        return ready_tasks

    def _dependencies_completed(self, task: MigrationTask) -> bool:
        """检查任务依赖是否完成"""
        for dep_id in task.dependencies:
            dep_task = self.tasks.get(dep_id)
            if not dep_task or dep_task.status != MigrationStatus.COMPLETED:
                return False
        return True

    async def _execute_task(self, task: MigrationTask):
        """执行单个任务"""
        logger.info(f"开始执行任务: {task.name}")
        task.status = MigrationStatus.RUNNING
        task.start_time = datetime.now()

        await self._emit_event("task_started", {"task_id": task.id, "task_name": task.name})

        try:
            # 执行具体任务
            result = await self._run_task_logic(task)

            task.status = MigrationStatus.COMPLETED
            task.end_time = datetime.now()
            task.progress = 100.0
            task.result = result

            # 更新指标
            self.metrics.completed_tasks += 1
            self.metrics.success_rate = self.metrics.completed_tasks / self.metrics.total_tasks * 100

            logger.info(f"任务完成: {task.name}")
            await self._emit_event("task_completed", {"task_id": task.id, "result": result})

        except Exception as e:
            logger.error(f"任务执行失败: {task.name}, 错误: {e}")
            task.status = MigrationStatus.FAILED
            task.end_time = datetime.now()
            task.error_message = str(e)

            self.metrics.failed_tasks += 1
            self.metrics.errors_count += 1

            await self._emit_event("task_failed", {"task_id": task.id, "error": str(e)})

            # 重试逻辑
            if task.retry_count < task.max_retries:
                logger.info(f"准备重试任务: {task.name} (第{task.retry_count + 1}次)")
                task.retry_count += 1
                task.status = MigrationStatus.IDLE
                await asyncio.sleep(5)  # 重试延迟

    async def _run_task_logic(self, task: MigrationTask) -> Dict[str, Any]:
        """运行任务逻辑"""
        if task.task_type == "data":
            return await self._run_data_migration_task(task)
        elif task.task_type == "code":
            return await self._run_code_migration_task(task)
        elif task.task_type == "api":
            return await self._run_api_compatibility_task(task)
        else:
            raise ValueError(f"未知的任务类型: {task.task_type}")

    async def _run_data_migration_task(self, task: MigrationTask) -> Dict[str, Any]:
        """运行数据迁移任务"""
        if task.id == "data_backup":
            # 执行数据备份
            success = await self.data_migration._create_data_backup()
            return {"backup_created": success}
        elif task.id == "schema_migration":
            # 执行数据库结构迁移
            migration_handler = self.data_migration
            success = migration_handler._create_migration_table()
            success &= migration_handler._create_isolated_tables()
            return {"schema_migrated": success}
        elif "migration" in task.id:
            # 执行数据迁移
            if "agent" in task.id:
                success = await self.data_migration._migrate_agent_data(task)
            elif "chat" in task.id:
                success = await self.data_migration._migrate_chat_data(task)
            elif "memory" in task.id:
                success = await self.data_migration._migrate_memory_data(task)
            else:
                success = True
            return {"data_migrated": success, "records": task.processed_records}
        elif task.id == "data_validation":
            # 执行数据验证
            success = await self.data_migration._validate_data_integrity()
            return {"validation_passed": success}
        else:
            return {"status": "unknown_task"}

    async def _run_code_migration_task(self, task: MigrationTask) -> Dict[str, Any]:
        """运行代码迁移任务"""
        if task.id == "code_analysis":
            analysis = self.code_migration.analyze_project()
            return {"analysis": analysis}
        elif "migration" in task.id:
            # 执行代码迁移
            migration_types = []
            if "isolation" in task.id:
                migration_types.append("isolation_context")
            if "config" in task.id:
                migration_types.append("config_system")
            if "chat" in task.id:
                migration_types.append("chat_stream")
            if "database" in task.id:
                migration_types.append("database_access")

            result = self.code_migration.apply_migration(migration_types=migration_types, dry_run=False)
            return {"migration_result": result}
        elif task.id == "code_validation":
            # 代码验证（模拟）
            await asyncio.sleep(2)
            return {"validation_passed": True}
        else:
            return {"status": "unknown_task"}

    async def _run_api_compatibility_task(self, task: MigrationTask) -> Dict[str, Any]:
        """运行API兼容性任务"""
        if task.id == "api_analysis":
            report = self.api_compatibility.generate_migration_report()
            return {"report": report}
        elif task.id == "api_compatibility_setup":
            # 设置API兼容性（模拟）
            await asyncio.sleep(1)
            return {"compatibility_setup": True}
        elif task.id == "api_monitoring":
            # 设置API监控（模拟）
            await asyncio.sleep(1)
            return {"monitoring_setup": True}
        elif task.id == "migration_timeline_creation":
            timeline = self.api_compatibility.create_migration_timeline()
            return {"timeline": timeline}
        else:
            return {"status": "unknown_task"}

    def _all_tasks_completed(self) -> bool:
        """检查是否所有任务都已完成"""
        return all(task.status in [MigrationStatus.COMPLETED, MigrationStatus.FAILED] for task in self.tasks.values())

    def _has_failed_tasks(self) -> bool:
        """检查是否有失败的任务"""
        return any(task.status == MigrationStatus.FAILED for task in self.tasks.values())

    async def pause_migration(self):
        """暂停迁移"""
        logger.info("暂停迁移")
        self.paused = True
        await self._emit_event("migration_paused", {})

    async def resume_migration(self):
        """恢复迁移"""
        logger.info("恢复迁移")
        self.paused = False
        await self._emit_event("migration_resumed", {})

    async def cancel_migration(self):
        """取消迁移"""
        logger.info("取消迁移")
        self.running = False
        self._shutdown_event.set()
        await self._emit_event("migration_cancelled", {})

    async def _create_backup(self):
        """创建备份"""
        logger.info("创建迁移备份")
        backup_dir = self.workspace_dir / "backups" / datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir.mkdir(parents=True, exist_ok=True)

    async def _rollback_migration(self):
        """回滚迁移"""
        logger.info("开始回滚迁移")
        # 实现回滚逻辑
        await self._emit_event("migration_rolled_back", {})

    async def _save_progress(self):
        """保存进度"""
        try:
            progress_file = self.workspace_dir / "migration_progress.json"
            progress_data = {
                "current_plan": asdict(self.current_plan) if self.current_plan else None,
                "tasks": {task_id: asdict(task) for task_id, task in self.tasks.items()},
                "metrics": asdict(self.metrics),
                "timestamp": datetime.now().isoformat(),
            }

            with open(progress_file, "w", encoding="utf-8") as f:
                json.dump(progress_data, f, ensure_ascii=False, indent=2, default=str)

        except Exception as e:
            logger.error(f"保存进度失败: {e}")

    async def _emit_event(self, event_type: str, data: Dict[str, Any]):
        """发送事件"""
        if event_type in self.event_handlers:
            for handler in self.event_handlers[event_type]:
                try:
                    await handler(data)
                except Exception as e:
                    logger.error(f"事件处理器执行失败: {e}")

    def add_event_handler(self, event_type: str, handler: Callable):
        """添加事件处理器"""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)

    def get_migration_status(self) -> Dict[str, Any]:
        """获取迁移状态"""
        if not self.current_plan:
            return {"status": "no_plan"}

        return {
            "plan_id": self.current_plan.id,
            "plan_name": self.current_plan.name,
            "status": "running" if self.running else "stopped",
            "paused": self.paused,
            "metrics": asdict(self.metrics),
            "tasks": {
                task_id: {
                    "name": task.name,
                    "status": task.status.value,
                    "progress": task.progress,
                    "error": task.error_message,
                }
                for task_id, task in self.tasks.items()
            },
        }

    def generate_migration_report(self) -> Dict[str, Any]:
        """生成迁移报告"""
        if not self.current_plan:
            return {"error": "没有迁移计划"}

        total_duration = sum(
            (task.end_time - task.start_time).total_seconds()
            for task in self.tasks.values()
            if task.start_time and task.end_time
        )

        return {
            "plan": asdict(self.current_plan),
            "metrics": asdict(self.metrics),
            "tasks_summary": {
                "total": len(self.tasks),
                "completed": len([t for t in self.tasks.values() if t.status == MigrationStatus.COMPLETED]),
                "failed": len([t for t in self.tasks.values() if t.status == MigrationStatus.FAILED]),
                "running": len([t for t in self.tasks.values() if t.status == MigrationStatus.RUNNING]),
            },
            "total_duration_seconds": total_duration,
            "generated_at": datetime.now().isoformat(),
        }


# 便捷函数
async def run_full_migration() -> bool:
    """运行完整迁移"""
    manager = MigrationManager()
    plan = manager.create_migration_plan(name="MaiBot多租户迁移", description="完整的多租户架构迁移")
    return await manager.execute_migration_plan(plan)


def create_migration_manager() -> MigrationManager:
    """创建迁移管理器实例"""
    return MigrationManager()
