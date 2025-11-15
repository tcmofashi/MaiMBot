"""
记忆服务的数据库迁移管理

提供数据库版本管理和迁移功能。
"""

import logging
from typing import List, Dict, Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .connection import get_session

logger = logging.getLogger(__name__)


class MigrationManager:
    """数据库迁移管理器"""

    def __init__(self):
        self.migrations = [
            {
                "version": "001_initial_schema",
                "description": "创建初始数据库架构",
                "up": self._create_initial_schema,
                "down": self._drop_initial_schema,
            },
            {
                "version": "002_add_indexes",
                "description": "添加性能优化索引",
                "up": self._add_performance_indexes,
                "down": self._drop_performance_indexes,
            },
            {
                "version": "003_add_stats_tables",
                "description": "添加统计和监控表",
                "up": self._create_stats_tables,
                "down": self._drop_stats_tables,
            },
        ]

    async def initialize_migration_table(self):
        """初始化迁移表"""
        async for session in get_session():
            try:
                # 创建迁移表
                await session.execute(
                    text("""
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version VARCHAR(50) PRIMARY KEY,
                        description TEXT,
                        applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        checksum VARCHAR(64)
                    )
                """)
                )
                await session.commit()
                logger.info("迁移表初始化完成")

            except Exception as e:
                await session.rollback()
                logger.error(f"初始化迁移表失败: {e}")
                raise

    async def get_applied_migrations(self) -> List[str]:
        """获取已应用的迁移"""
        async for session in get_session():
            try:
                result = await session.execute(text("SELECT version FROM schema_migrations ORDER BY version"))
                return [row[0] for row in result.fetchall()]

            except Exception as e:
                logger.error(f"获取已应用迁移失败: {e}")
                return []

    async def apply_pending_migrations(self):
        """应用所有待执行的迁移"""
        await self.initialize_migration_table()

        applied = await self.get_applied_migrations()
        pending = [m for m in self.migrations if m["version"] not in applied]

        if not pending:
            logger.info("没有待执行的迁移")
            return

        logger.info(f"发现 {len(pending)} 个待执行的迁移")

        for migration in pending:
            try:
                logger.info(f"应用迁移: {migration['version']} - {migration['description']}")
                await migration["up"]()

                # 记录迁移
                async for session in get_session():
                    await session.execute(
                        text("""
                        INSERT INTO schema_migrations (version, description)
                        VALUES (:version, :description)
                    """),
                        {"version": migration["version"], "description": migration["description"]},
                    )
                    await session.commit()

                logger.info(f"迁移 {migration['version']} 应用成功")

            except Exception as e:
                logger.error(f"应用迁移 {migration['version']} 失败: {e}")
                raise

    async def rollback_migration(self, version: str):
        """回滚指定版本的迁移"""
        migration = next((m for m in self.migrations if m["version"] == version), None)
        if not migration:
            raise ValueError(f"未找到迁移版本: {version}")

        try:
            logger.info(f"回滚迁移: {migration['version']}")
            await migration["down"]()

            # 删除迁移记录
            async for session in get_session():
                await session.execute(
                    text("DELETE FROM schema_migrations WHERE version = :version"), {"version": version}
                )
                await session.commit()

            logger.info(f"迁移 {version} 回滚成功")

        except Exception as e:
            logger.error(f"回滚迁移 {version} 失败: {e}")
            raise

    async def _create_initial_schema(self):
        """创建初始数据库架构"""
        # 这个方法实际不会被调用，因为表创建已经在 models.py 中处理
        logger.info("初始架构已通过ORM创建")

    async def _drop_initial_schema(self):
        """删除初始数据库架构"""
        async for session in get_session():
            try:
                # 删除表（按依赖关系倒序）
                tables = ["system_metrics", "operation_logs", "memory_stats", "conflicts", "memories"]

                for table in tables:
                    await session.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))

                await session.commit()
                logger.info("初始架构已删除")

            except Exception:
                await session.rollback()
                raise

    async def _add_performance_indexes(self):
        """添加性能优化索引"""
        async for session in get_session():
            try:
                # 添加复合索引
                indexes = [
                    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_memories_tenant_level_status "
                    "ON memories(tenant_id, level, status) WHERE status = 'active'",
                    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_memories_platform_scope_active "
                    "ON memories(platform, scope_id, created_at) WHERE status = 'active' AND platform IS NOT NULL",
                    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_conflicts_tenant_resolved "
                    "ON conflicts(tenant_id, resolved, created_at) WHERE resolved = false",
                    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_conflicts_agent_platform "
                    "ON conflicts(agent_id, platform, start_following) WHERE start_following = true",
                ]

                for index_sql in indexes:
                    await session.execute(text(index_sql))

                await session.commit()
                logger.info("性能优化索引添加完成")

            except Exception:
                await session.rollback()
                raise

    async def _drop_performance_indexes(self):
        """删除性能优化索引"""
        async for session in get_session():
            try:
                # 删除索引
                indexes = [
                    "idx_memories_tenant_level_status",
                    "idx_memories_platform_scope_active",
                    "idx_conflicts_tenant_resolved",
                    "idx_conflicts_agent_platform",
                ]

                for index_name in indexes:
                    await session.execute(text(f"DROP INDEX IF EXISTS {index_name}"))

                await session.commit()
                logger.info("性能优化索引删除完成")

            except Exception:
                await session.rollback()
                raise

    async def _create_stats_tables(self):
        """创建统计和监控表"""
        async for session in get_session():
            try:
                # 统计表已在 models.py 中定义，这里只是确保它们存在
                await session.execute(
                    text("""
                    SELECT 1 FROM memory_stats LIMIT 1
                """)
                )
                await session.execute(
                    text("""
                    SELECT 1 FROM operation_logs LIMIT 1
                """)
                )
                await session.execute(
                    text("""
                    SELECT 1 FROM system_metrics LIMIT 1
                """)
                )

                await session.commit()
                logger.info("统计和监控表创建完成")

            except Exception:
                await session.rollback()
                raise


# 全局迁移管理器实例
migration_manager = MigrationManager()


async def run_migrations():
    """运行所有迁移"""
    await migration_manager.apply_pending_migrations()


async def get_migration_status() -> Dict[str, Any]:
    """获取迁移状态"""
    applied = await migration_manager.get_applied_migrations()
    pending = [m["version"] for m in migration_manager.migrations if m["version"] not in applied]

    return {
        "total_migrations": len(migration_manager.migrations),
        "applied_migrations": len(applied),
        "pending_migrations": len(pending),
        "applied_versions": applied,
        "pending_versions": pending,
        "last_migration": applied[-1] if applied else None,
    }


async def validate_database_schema() -> Dict[str, Any]:
    """验证数据库架构完整性"""
    validation_result = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "tables": {},
    }

    try:
        # 检查必需的表是否存在
        required_tables = ["memories", "conflicts", "memory_stats", "operation_logs", "system_metrics"]
        async for session in get_session():
            for table in required_tables:
                try:
                    result = await session.execute(
                        text(f"SELECT COUNT(*) FROM information_schema.tables WHERE table_name = '{table}'")
                    )
                    exists = result.fetchone()[0] > 0
                    validation_result["tables"][table] = {"exists": exists}

                    if not exists:
                        validation_result["valid"] = False
                        validation_result["errors"].append(f"必需的表 {table} 不存在")

                    # 检查表结构
                    if exists:
                        # 检查关键列
                        if table == "memories":
                            required_columns = ["id", "tenant_id", "agent_id", "title", "content"]
                            await _check_table_columns(session, table, required_columns, validation_result)

                except Exception as e:
                    validation_result["errors"].append(f"检查表 {table} 时出错: {str(e)}")

    except Exception as e:
        validation_result["valid"] = False
        validation_result["errors"].append(f"数据库验证失败: {str(e)}")

    return validation_result


async def _check_table_columns(session: AsyncSession, table: str, required_columns: List[str], result: Dict[str, Any]):
    """检查表的必需列"""
    try:
        columns_query = """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = :table_name
        """
        db_result = await session.execute(text(columns_query), {"table_name": table})
        existing_columns = {row[0] for row in db_result.fetchall()}

        missing_columns = set(required_columns) - existing_columns
        if missing_columns:
            result["valid"] = False
            result["errors"].append(f"表 {table} 缺少必需的列: {list(missing_columns)}")

        result["tables"][table]["columns"] = list(existing_columns)

    except Exception as e:
        result["errors"].append(f"检查表 {table} 列时出错: {str(e)}")


# 便捷函数
async def ensure_database_ready() -> bool:
    """确保数据库准备就绪"""
    try:
        # 运行迁移
        await run_migrations()

        # 验证架构
        validation = await validate_database_schema()
        if not validation["valid"]:
            logger.error(f"数据库架构验证失败: {validation['errors']}")
            return False

        return True

    except Exception as e:
        logger.error(f"确保数据库准备就绪失败: {e}")
        return False
