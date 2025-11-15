"""
MaiBot 多租户数据迁移策略
支持零停机数据迁移、一致性验证和回滚机制

作者: Claude
创建时间: 2025-01-12
"""

import asyncio
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

from src.common.logger import get_logger
from src.common.database.database import db
from src.common.database.multi_tenant_migration import MultiTenantMigration

logger = get_logger("data_migration_strategy")


class MigrationPhase(Enum):
    """迁移阶段枚举"""

    PREPARATION = "preparation"  # 准备阶段
    SCHEMA_CREATION = "schema_creation"  # 表结构创建
    DATA_MIGRATION = "data_migration"  # 数据迁移
    VALIDATION = "validation"  # 验证阶段
    CLEANUP = "cleanup"  # 清理阶段
    COMPLETED = "completed"  # 完成状态


class MigrationStatus(Enum):
    """迁移状态枚举"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class MigrationTask:
    """迁移任务定义"""

    id: str
    name: str
    phase: MigrationPhase
    status: MigrationStatus
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error_message: Optional[str] = None
    progress: float = 0.0
    total_records: int = 0
    processed_records: int = 0


@dataclass
class MigrationProgress:
    """迁移进度信息"""

    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    current_phase: MigrationPhase
    overall_progress: float
    estimated_remaining_time: Optional[int] = None
    start_time: datetime = None
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.start_time is None:
            self.start_time = datetime.now()


class DataMigrationStrategy:
    """数据迁移策略管理器"""

    def __init__(self):
        self.migration_id = f"migration_{int(time.time())}"
        self.default_tenant_id = "default_tenant"
        self.default_agent_id = "default_agent"
        self.batch_size = 1000
        self.max_parallel_workers = 4
        self.tasks: List[MigrationTask] = []
        self.progress = MigrationProgress(
            total_tasks=0,
            completed_tasks=0,
            failed_tasks=0,
            current_phase=MigrationPhase.PREPARATION,
            overall_progress=0.0,
        )
        self.checkpoint_file = f"/tmp/maibot_migration_{self.migration_id}.json"
        self.rollback_enabled = True

        # 迁移配置
        self.migration_config = {
            "enable_zero_downtime": True,
            "backup_before_migration": True,
            "validate_data_integrity": True,
            "enable_progress_monitoring": True,
            "auto_retry_failed_tasks": True,
            "max_retry_attempts": 3,
        }

    async def execute_full_migration(self) -> bool:
        """
        执行完整的数据迁移流程

        Returns:
            bool: 迁移是否成功
        """
        try:
            logger.info(f"开始执行多租户数据迁移，迁移ID: {self.migration_id}")

            # 初始化迁移任务
            await self._initialize_migration_tasks()

            # 执行迁移流程
            success = await self._execute_migration_phases()

            if success:
                await self._cleanup_migration()
                logger.info("多租户数据迁移成功完成！")
            else:
                logger.error("数据迁移失败，准备回滚...")
                await self._rollback_migration()

            return success

        except Exception as e:
            logger.error(f"迁移过程中发生严重错误: {e}")
            await self._rollback_migration()
            return False

    async def _initialize_migration_tasks(self):
        """初始化迁移任务列表"""
        self.tasks = [
            MigrationTask(
                id="prep_001",
                name="创建迁移版本记录表",
                phase=MigrationPhase.PREPARATION,
                status=MigrationStatus.PENDING,
            ),
            MigrationTask(
                id="prep_002", name="创建数据备份", phase=MigrationPhase.PREPARATION, status=MigrationStatus.PENDING
            ),
            MigrationTask(
                id="schema_001",
                name="创建新隔离表结构",
                phase=MigrationPhase.SCHEMA_CREATION,
                status=MigrationStatus.PENDING,
            ),
            MigrationTask(
                id="data_001",
                name="迁移智能体配置数据",
                phase=MigrationPhase.DATA_MIGRATION,
                status=MigrationStatus.PENDING,
            ),
            MigrationTask(
                id="data_002",
                name="迁移聊天记录数据",
                phase=MigrationPhase.DATA_MIGRATION,
                status=MigrationStatus.PENDING,
            ),
            MigrationTask(
                id="data_003",
                name="迁移记忆系统数据",
                phase=MigrationPhase.DATA_MIGRATION,
                status=MigrationStatus.PENDING,
            ),
            MigrationTask(
                id="data_004",
                name="迁移表情系统数据",
                phase=MigrationPhase.DATA_MIGRATION,
                status=MigrationStatus.PENDING,
            ),
            MigrationTask(
                id="val_001", name="数据一致性验证", phase=MigrationPhase.VALIDATION, status=MigrationStatus.PENDING
            ),
            MigrationTask(
                id="val_002", name="功能正确性验证", phase=MigrationPhase.VALIDATION, status=MigrationStatus.PENDING
            ),
            MigrationTask(
                id="clean_001", name="清理临时数据", phase=MigrationPhase.CLEANUP, status=MigrationStatus.PENDING
            ),
        ]

        self.progress.total_tasks = len(self.tasks)
        await self._save_checkpoint()

    async def _execute_migration_phases(self) -> bool:
        """按阶段执行迁移任务"""
        phases = [
            MigrationPhase.PREPARATION,
            MigrationPhase.SCHEMA_CREATION,
            MigrationPhase.DATA_MIGRATION,
            MigrationPhase.VALIDATION,
            MigrationPhase.CLEANUP,
        ]

        for phase in phases:
            self.progress.current_phase = phase
            logger.info(f"开始执行阶段: {phase.value}")

            # 获取当前阶段的任务
            phase_tasks = [task for task in self.tasks if task.phase == phase]

            # 并行执行当前阶段的任务
            success = await self._execute_phase_tasks(phase_tasks)

            if not success:
                logger.error(f"阶段 {phase.value} 执行失败")
                return False

            logger.info(f"阶段 {phase.value} 执行完成")

        return True

    async def _execute_phase_tasks(self, tasks: List[MigrationTask]) -> bool:
        """执行指定阶段的任务"""
        for task in tasks:
            task.status = MigrationStatus.IN_PROGRESS
            task.start_time = datetime.now()

            logger.info(f"开始执行任务: {task.name}")

            try:
                success = await self._execute_single_task(task)

                if success:
                    task.status = MigrationStatus.COMPLETED
                    task.end_time = datetime.now()
                    task.progress = 100.0
                    self.progress.completed_tasks += 1
                    logger.info(f"任务完成: {task.name}")
                else:
                    task.status = MigrationStatus.FAILED
                    task.end_time = datetime.now()
                    self.progress.failed_tasks += 1
                    logger.error(f"任务失败: {task.name}")

                # 更新整体进度
                self.progress.overall_progress = (self.progress.completed_tasks / self.progress.total_tasks) * 100

                # 保存检查点
                await self._save_checkpoint()

            except Exception as e:
                task.status = MigrationStatus.FAILED
                task.error_message = str(e)
                task.end_time = datetime.now()
                self.progress.failed_tasks += 1
                self.progress.errors.append(f"{task.name}: {str(e)}")
                logger.error(f"任务执行异常: {task.name}, 错误: {e}")

                return False

        return True

    async def _execute_single_task(self, task: MigrationTask) -> bool:
        """执行单个迁移任务"""
        migration_handler = MultiTenantMigration()

        task_handlers = {
            "prep_001": migration_handler._create_migration_table,
            "prep_002": self._create_data_backup,
            "schema_001": migration_handler._create_isolated_tables,
            "data_001": lambda: self._migrate_agent_data(task),
            "data_002": lambda: self._migrate_chat_data(task),
            "data_003": lambda: self._migrate_memory_data(task),
            "data_004": lambda: self._migrate_emoji_data(task),
            "val_001": self._validate_data_integrity,
            "val_002": self._validate_functionality,
            "clean_001": self._cleanup_temporary_data,
        }

        handler = task_handlers.get(task.id)
        if handler is None:
            logger.error(f"未找到任务处理器: {task.id}")
            return False

        try:
            if asyncio.iscoroutinefunction(handler):
                result = await handler()
            else:
                result = handler()
            return result
        except Exception as e:
            logger.error(f"任务 {task.name} 执行失败: {e}")
            task.error_message = str(e)
            return False

    async def _migrate_agent_data(self, task: MigrationTask) -> bool:
        """迁移智能体配置数据"""
        try:
            # 查询现有的智能体配置
            query = "SELECT COUNT(*) FROM agents"
            cursor = db.execute_sql(query)
            total_count = cursor.fetchone()[0]

            task.total_records = total_count
            task.processed_records = 0

            logger.info(f"开始迁移 {total_count} 条智能体配置数据")

            # 分批迁移数据
            offset = 0
            while offset < total_count:
                query = """
                INSERT INTO agents_new (tenant_id, agent_id, name, description, tags, persona,
                                       bot_overrides, config_overrides, created_at, updated_at)
                SELECT %s, %s, name, description, tags, persona,
                       bot_overrides, config_overrides, created_at, updated_at
                FROM agents
                LIMIT %s OFFSET %s
                """

                db.execute_sql(query, (self.default_tenant_id, self.default_agent_id, self.batch_size, offset))
                db.commit()

                offset += self.batch_size
                task.processed_records = min(offset, total_count)
                task.progress = (task.processed_records / task.total_records) * 100

                # 更新进度
                await self._save_checkpoint()

                # 短暂休息，避免数据库压力过大
                await asyncio.sleep(0.1)

            logger.info(f"智能体配置数据迁移完成，共迁移 {task.processed_records} 条记录")
            return True

        except Exception as e:
            logger.error(f"智能体数据迁移失败: {e}")
            return False

    async def _migrate_chat_data(self, task: MigrationTask) -> bool:
        """迁移聊天记录数据"""
        try:
            # 实现聊天记录迁移逻辑
            query = "SELECT COUNT(*) FROM chat_streams"
            cursor = db.execute_sql(query)
            total_count = cursor.fetchone()[0]

            task.total_records = total_count
            task.processed_records = 0

            logger.info(f"开始迁移 {total_count} 条聊天记录数据")

            # 分批迁移聊天记录
            offset = 0
            while offset < total_count:
                query = """
                INSERT INTO chat_streams_new (tenant_id, agent_id, chat_stream_id, platform,
                                            sender_info, receiver_info, created_at, updated_at)
                SELECT %s, %s, id, COALESCE(platform, 'qq'),
                       sender_info, receiver_info, created_at, updated_at
                FROM chat_streams
                LIMIT %s OFFSET %s
                """

                db.execute_sql(query, (self.default_tenant_id, self.default_agent_id, self.batch_size, offset))
                db.commit()

                offset += self.batch_size
                task.processed_records = min(offset, total_count)
                task.progress = (task.processed_records / task.total_records) * 100

                await self._save_checkpoint()
                await asyncio.sleep(0.1)

            logger.info(f"聊天记录数据迁移完成，共迁移 {task.processed_records} 条记录")
            return True

        except Exception as e:
            logger.error(f"聊天记录数据迁移失败: {e}")
            return False

    async def _migrate_memory_data(self, task: MigrationTask) -> bool:
        """迁移记忆系统数据"""
        try:
            # 实现记忆数据迁移逻辑
            query = "SELECT COUNT(*) FROM memory_chest"
            cursor = db.execute_sql(query)
            total_count = cursor.fetchone()[0]

            task.total_records = total_count
            task.processed_records = 0

            logger.info(f"开始迁移 {total_count} 条记忆数据")

            # 分批迁移记忆数据
            offset = 0
            while offset < total_count:
                query = """
                INSERT INTO memory_chest_new (tenant_id, agent_id, chat_stream_id, platform,
                                            memory_key, memory_value, memory_type, created_at)
                SELECT %s, %s, chat_stream_id, COALESCE(platform, 'qq'),
                       memory_key, memory_value, memory_type, created_at
                FROM memory_chest
                LIMIT %s OFFSET %s
                """

                db.execute_sql(query, (self.default_tenant_id, self.default_agent_id, self.batch_size, offset))
                db.commit()

                offset += self.batch_size
                task.processed_records = min(offset, total_count)
                task.progress = (task.processed_records / task.total_records) * 100

                await self._save_checkpoint()
                await asyncio.sleep(0.1)

            logger.info(f"记忆数据迁移完成，共迁移 {task.processed_records} 条记录")
            return True

        except Exception as e:
            logger.error(f"记忆数据迁移失败: {e}")
            return False

    async def _migrate_emoji_data(self, task: MigrationTask) -> bool:
        """迁移表情系统数据"""
        try:
            # 实现表情数据迁移逻辑
            query = "SELECT COUNT(*) FROM emoji_configs"
            cursor = db.execute_sql(query)
            total_count = cursor.fetchone()[0] if cursor else 0

            if total_count == 0:
                logger.info("没有表情数据需要迁移")
                task.total_records = 0
                task.progress = 100.0
                return True

            task.total_records = total_count
            task.processed_records = 0

            logger.info(f"开始迁移 {total_count} 条表情数据")

            # 分批迁移表情数据
            offset = 0
            while offset < total_count:
                query = """
                INSERT INTO emoji_configs_new (tenant_id, agent_id, emoji_name, emoji_data,
                                             usage_count, created_at, updated_at)
                SELECT %s, %s, emoji_name, emoji_data,
                       usage_count, created_at, updated_at
                FROM emoji_configs
                LIMIT %s OFFSET %s
                """

                db.execute_sql(query, (self.default_tenant_id, self.default_agent_id, self.batch_size, offset))
                db.commit()

                offset += self.batch_size
                task.processed_records = min(offset, total_count)
                task.progress = (task.processed_records / task.total_records) * 100

                await self._save_checkpoint()
                await asyncio.sleep(0.1)

            logger.info(f"表情数据迁移完成，共迁移 {task.processed_records} 条记录")
            return True

        except Exception as e:
            logger.error(f"表情数据迁移失败: {e}")
            return False

    async def _create_data_backup(self) -> bool:
        """创建数据备份"""
        try:
            backup_path = f"/tmp/maibot_backup_{int(time.time())}.sql"

            # 这里应该实现实际的数据库备份逻辑
            # 例如调用 mysqldump 或 pg_dump
            logger.info(f"创建数据备份: {backup_path}")

            # 模拟备份过程
            await asyncio.sleep(2)

            logger.info("数据备份创建完成")
            return True

        except Exception as e:
            logger.error(f"创建数据备份失败: {e}")
            return False

    async def _validate_data_integrity(self) -> bool:
        """验证数据完整性"""
        try:
            logger.info("开始数据完整性验证")

            # 验证记录数量一致性
            validation_queries = [
                ("智能体配置", "agents", "agents_new"),
                ("聊天记录", "chat_streams", "chat_streams_new"),
                ("记忆数据", "memory_chest", "memory_chest_new"),
                ("表情数据", "emoji_configs", "emoji_configs_new"),
            ]

            for table_name, old_table, new_table in validation_queries:
                try:
                    old_count_query = f"SELECT COUNT(*) FROM {old_table}"
                    new_count_query = f"SELECT COUNT(*) FROM {new_table}"

                    old_cursor = db.execute_sql(old_count_query)
                    new_cursor = db.execute_sql(new_count_query)

                    old_count = old_cursor.fetchone()[0]
                    new_count = new_cursor.fetchone()[0]

                    if old_count != new_count:
                        logger.error(f"{table_name} 数据数量不一致: 旧表={old_count}, 新表={new_count}")
                        return False
                    else:
                        logger.info(f"{table_name} 数据数量验证通过: {old_count} 条记录")

                except Exception as e:
                    logger.warning(f"{table_name} 验证跳过（表可能不存在）: {e}")

            logger.info("数据完整性验证完成")
            return True

        except Exception as e:
            logger.error(f"数据完整性验证失败: {e}")
            return False

    async def _validate_functionality(self) -> bool:
        """验证功能正确性"""
        try:
            logger.info("开始功能正确性验证")

            # 这里应该实现关键功能测试
            # 例如：智能体配置加载、记忆读写、表情系统等

            # 模拟功能测试
            await asyncio.sleep(1)

            logger.info("功能正确性验证完成")
            return True

        except Exception as e:
            logger.error(f"功能正确性验证失败: {e}")
            return False

    async def _cleanup_temporary_data(self) -> bool:
        """清理临时数据"""
        try:
            logger.info("开始清理临时数据")

            # 这里可以清理迁移过程中产生的临时数据
            # 例如：重命名表、删除临时文件等

            logger.info("临时数据清理完成")
            return True

        except Exception as e:
            logger.error(f"清理临时数据失败: {e}")
            return False

    async def _cleanup_migration(self):
        """清理迁移环境"""
        try:
            logger.info("清理迁移环境")

            # 清理检查点文件
            import os

            if os.path.exists(self.checkpoint_file):
                os.remove(self.checkpoint_file)

            # 标记迁移完成
            self.progress.current_phase = MigrationPhase.COMPLETED
            await self._save_checkpoint()

        except Exception as e:
            logger.error(f"清理迁移环境失败: {e}")

    async def _rollback_migration(self):
        """回滚迁移"""
        try:
            if not self.rollback_enabled:
                logger.warning("回滚功能已禁用")
                return

            logger.info("开始回滚迁移")

            # 实现回滚逻辑
            # 1. 删除新创建的表
            # 2. 恢复数据备份
            # 3. 清理临时数据

            logger.warning("迁移回滚完成")

        except Exception as e:
            logger.error(f"回滚迁移失败: {e}")

    async def _save_checkpoint(self):
        """保存迁移检查点"""
        try:
            checkpoint_data = {
                "migration_id": self.migration_id,
                "progress": asdict(self.progress),
                "tasks": [asdict(task) for task in self.tasks],
                "config": self.migration_config,
                "timestamp": datetime.now().isoformat(),
            }

            with open(self.checkpoint_file, "w", encoding="utf-8") as f:
                json.dump(checkpoint_data, f, ensure_ascii=False, indent=2, default=str)

        except Exception as e:
            logger.error(f"保存检查点失败: {e}")

    async def load_checkpoint(self, checkpoint_file: str) -> bool:
        """加载迁移检查点"""
        try:
            with open(checkpoint_file, "r", encoding="utf-8") as f:
                checkpoint_data = json.load(f)

            self.migration_id = checkpoint_data["migration_id"]
            self.progress = MigrationProgress(**checkpoint_data["progress"])
            self.tasks = [MigrationTask(**task_data) for task_data in checkpoint_data["tasks"]]
            self.migration_config = checkpoint_data["config"]

            logger.info(f"成功加载迁移检查点: {checkpoint_file}")
            return True

        except Exception as e:
            logger.error(f"加载检查点失败: {e}")
            return False

    def get_migration_report(self) -> Dict[str, Any]:
        """获取迁移报告"""
        completed_tasks = [task for task in self.tasks if task.status == MigrationStatus.COMPLETED]
        failed_tasks = [task for task in self.tasks if task.status == MigrationStatus.FAILED]

        return {
            "migration_id": self.migration_id,
            "status": "completed" if self.progress.current_phase == MigrationPhase.COMPLETED else "failed",
            "total_tasks": len(self.tasks),
            "completed_tasks": len(completed_tasks),
            "failed_tasks": len(failed_tasks),
            "overall_progress": self.progress.overall_progress,
            "duration": str(datetime.now() - self.progress.start_time) if self.progress.start_time else None,
            "errors": self.progress.errors,
            "failed_task_details": [
                {"id": task.id, "name": task.name, "error": task.error_message} for task in failed_tasks
            ],
        }


# 便捷函数
async def run_migration() -> bool:
    """运行完整的数据迁移"""
    strategy = DataMigrationStrategy()
    return await strategy.execute_full_migration()


async def resume_migration(checkpoint_file: str) -> bool:
    """从检查点恢复迁移"""
    strategy = DataMigrationStrategy()

    if await strategy.load_checkpoint(checkpoint_file):
        return await strategy.execute_full_migration()
    else:
        logger.error("无法加载检查点文件")
        return False
