"""
MaiBot 多租户隔离数据库迁移脚本
支持T+A+C+P四维隔离的数据表结构升级

作者: Claude
创建时间: 2025-01-11
"""

import hashlib
from typing import Dict

from src.common.logger import get_logger
from .database import db

logger = get_logger("multi_tenant_migration")


class MultiTenantMigration:
    """多租户数据库迁移管理器"""

    def __init__(self):
        self.migration_version = "1.0.0"
        self.default_tenant_id = "default_tenant"
        self.default_agent_id = "default_agent"

    def execute_migration(self, force: bool = False) -> bool:
        """
        执行完整的多租户迁移

        Args:
            force: 是否强制执行迁移（跳过安全检查）

        Returns:
            bool: 迁移是否成功
        """
        try:
            logger.info("开始执行MaiBot多租户隔离迁移...")

            # 1. 安全检查
            if not force and not self._safety_check():
                logger.error("安全检查失败，终止迁移。使用 force=True 强制执行。")
                return False

            # 2. 创建迁移版本记录表
            self._create_migration_table()

            # 3. 检查是否已经迁移
            if self._is_already_migrated():
                logger.warning("数据库已经完成多租户迁移，跳过。")
                return True

            # 4. 执行表结构迁移
            migration_steps = [
                self._migrate_chat_streams,
                self._migrate_messages,
                self._migrate_memory_chest,
                self._migrate_agents,
                self._migrate_llm_usage,
                self._migrate_expressions,
                self._migrate_action_records,
                self._migrate_jargon,
                self._migrate_person_info,
                self._migrate_group_info,
            ]

            for step in migration_steps:
                try:
                    step()
                    logger.info(f"✓ {step.__name__} 完成")
                except Exception as e:
                    logger.error(f"✗ {step.__name__} 失败: {e}")
                    raise

            # 5. 创建复合索引
            self._create_composite_indexes()

            # 6. 记录迁移版本
            self._record_migration()

            logger.info("🎉 多租户隔离迁移完成！")
            return True

        except Exception as e:
            logger.exception(f"迁移过程中发生错误: {e}")
            return False

    def _safety_check(self) -> bool:
        """执行迁移前的安全检查"""
        try:
            with db:
                # 检查数据库连接
                cursor = db.execute_sql("SELECT 1")
                if not cursor.fetchone():
                    logger.error("数据库连接失败")
                    return False

                # 检查关键表是否存在
                critical_tables = ["chat_streams", "messages", "memory_chest"]
                for table in critical_tables:
                    if not db.table_exists(table):
                        logger.error(f"关键表 {table} 不存在")
                        return False

                # 检查数据量（警告）
                for table in critical_tables:
                    count = db.execute_sql(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    if count > 10000:
                        logger.warning(f"表 {table} 包含大量数据 ({count} 条)，迁移可能需要较长时间")

                logger.info("安全检查通过")
                return True

        except Exception as e:
            logger.exception(f"安全检查失败: {e}")
            return False

    def _create_migration_table(self):
        """创建迁移版本记录表"""
        with db:
            db.execute_sql("""
                CREATE TABLE IF NOT EXISTS migration_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    migration_name TEXT UNIQUE NOT NULL,
                    version TEXT NOT NULL,
                    executed_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def _is_already_migrated(self) -> bool:
        """检查是否已经完成迁移"""
        try:
            cursor = db.execute_sql(
                "SELECT COUNT(*) FROM migration_versions WHERE migration_name = 'multi_tenant_isolation'"
            )
            return cursor.fetchone()[0] > 0
        except Exception:
            return False

    def _record_migration(self):
        """记录迁移版本"""
        with db:
            db.execute_sql(
                """
                INSERT INTO migration_versions (migration_name, version)
                VALUES ('multi_tenant_isolation', ?)
                """,
                (self.migration_version,),
            )

    def _migrate_chat_streams(self):
        """迁移 ChatStreams 表"""
        with db:
            # 检查列是否已存在
            cursor = db.execute_sql("PRAGMA table_info(chat_streams)")
            existing_columns = {row[1] for row in cursor.fetchall()}

            # 添加隔离字段
            if "tenant_id" not in existing_columns:
                db.execute_sql("ALTER TABLE chat_streams ADD COLUMN tenant_id TEXT")
                logger.info("添加 chat_streams.tenant_id")

            if "chat_stream_id" not in existing_columns:
                db.execute_sql("ALTER TABLE chat_streams ADD COLUMN chat_stream_id TEXT")
                logger.info("添加 chat_streams.chat_stream_id")

            # 迁移现有数据
            self._migrate_chat_streams_data()

    def _migrate_chat_streams_data(self):
        """迁移 ChatStreams 数据"""
        # 为现有数据设置默认租户和生成新的 chat_stream_id
        with db:
            cursor = db.execute_sql("""
                SELECT stream_id, platform, user_id, group_id, agent_id
                FROM chat_streams
                WHERE tenant_id IS NULL OR tenant_id = ''
            """)

            for row in cursor.fetchall():
                old_stream_id, platform, user_id, group_id, agent_id = row
                if not old_stream_id:
                    continue

                # 生成新的隔离化 chat_stream_id
                new_chat_stream_id = self._generate_isolated_stream_id(
                    self.default_tenant_id,
                    agent_id or self.default_agent_id,
                    platform or "unknown",
                    user_id or group_id or "unknown",
                )

                # 更新记录
                db.execute_sql(
                    """
                    UPDATE chat_streams
                    SET tenant_id = ?,
                        chat_stream_id = ?,
                        agent_id = COALESCE(agent_id, ?)
                    WHERE stream_id = ?
                """,
                    (self.default_tenant_id, new_chat_stream_id, self.default_agent_id, old_stream_id),
                )

            logger.info(f"迁移了 {cursor.rowcount} 条 chat_streams 记录")

    def _migrate_messages(self):
        """迁移 Messages 表"""
        with db:
            cursor = db.execute_sql("PRAGMA table_info(messages)")
            existing_columns = {row[1] for row in cursor.fetchall()}

            # 添加隔离字段
            for field in ["tenant_id", "agent_id", "platform", "chat_stream_id"]:
                if field not in existing_columns:
                    db.execute_sql(f"ALTER TABLE messages ADD COLUMN {field} TEXT")
                    logger.info(f"添加 messages.{field}")

            # 迁移现有数据
            self._migrate_messages_data()

    def _migrate_messages_data(self):
        """迁移 Messages 数据"""
        with db:
            # 从 chat_streams 获取租户信息并更新 messages
            db.execute_sql(
                """
                UPDATE messages
                SET tenant_id = COALESCE(cs.tenant_id, ?),
                    agent_id = COALESCE(cs.agent_id, ?),
                    platform = COALESCE(cs.platform, platform),
                    chat_stream_id = COALESCE(cs.chat_stream_id, chat_id)
                FROM chat_streams cs
                WHERE messages.chat_id = cs.stream_id
                   AND (messages.tenant_id IS NULL OR messages.tenant_id = '')
            """,
                (self.default_tenant_id, self.default_agent_id),
            )

            # 对于没有对应 chat_stream 的消息，设置默认值
            db.execute_sql(
                """
                UPDATE messages
                SET tenant_id = ?, agent_id = ?, chat_stream_id = chat_id
                WHERE tenant_id IS NULL OR tenant_id = ''
            """,
                (self.default_tenant_id, self.default_agent_id),
            )

            logger.info("迁移了 messages 表数据")

    def _migrate_memory_chest(self):
        """迁移 MemoryChest 表"""
        with db:
            cursor = db.execute_sql("PRAGMA table_info(memory_chest)")
            existing_columns = {row[1] for row in cursor.fetchall()}

            # 添加隔离字段
            for field in ["tenant_id", "agent_id", "platform", "chat_stream_id", "memory_level", "memory_scope"]:
                if field not in existing_columns:
                    db.execute_sql(f"ALTER TABLE memory_chest ADD COLUMN {field} TEXT")
                    logger.info(f"添加 memory_chest.{field}")

            # 迁移现有数据
            self._migrate_memory_chest_data()

    def _migrate_memory_chest_data(self):
        """迁移 MemoryChest 数据"""
        with db:
            # 设置默认值
            db.execute_sql(
                """
                UPDATE memory_chest
                SET tenant_id = ?,
                    agent_id = ?,
                    memory_level = COALESCE(memory_level, 'agent'),
                    memory_scope = COALESCE(memory_scope, ? || ':' || ? || ':global')
                WHERE tenant_id IS NULL OR tenant_id = ''
            """,
                (self.default_tenant_id, self.default_agent_id, self.default_tenant_id, self.default_agent_id),
            )

            logger.info("迁移了 memory_chest 表数据")

    def _migrate_agents(self):
        """迁移 AgentRecord 表"""
        with db:
            cursor = db.execute_sql("PRAGMA table_info(agents)")
            existing_columns = {row[1] for row in cursor.fetchall()}

            if "tenant_id" not in existing_columns:
                db.execute_sql("ALTER TABLE agents ADD COLUMN tenant_id TEXT")
                logger.info("添加 agents.tenant_id")

            # 迁移数据
            db.execute_sql(
                """
                UPDATE agents
                SET tenant_id = ?
                WHERE tenant_id IS NULL OR tenant_id = ''
            """,
                (self.default_tenant_id,),
            )

            logger.info("迁移了 agents 表数据")

    def _migrate_llm_usage(self):
        """迁移 LLMUsage 表"""
        with db:
            cursor = db.execute_sql("PRAGMA table_info(llm_usage)")
            existing_columns = {row[1] for row in cursor.fetchall()}

            for field in ["tenant_id", "agent_id", "platform"]:
                if field not in existing_columns:
                    db.execute_sql(f"ALTER TABLE llm_usage ADD COLUMN {field} TEXT")
                    logger.info(f"添加 llm_usage.{field}")

            # 迁移数据
            db.execute_sql(
                """
                UPDATE llm_usage
                SET tenant_id = ?,
                    agent_id = COALESCE(agent_id, ?),
                    platform = COALESCE(platform, 'unknown')
                WHERE tenant_id IS NULL OR tenant_id = ''
            """,
                (self.default_tenant_id, self.default_agent_id),
            )

            logger.info("迁移了 llm_usage 表数据")

    def _migrate_expressions(self):
        """迁移 Expression 表"""
        with db:
            cursor = db.execute_sql("PRAGMA table_info(expression)")
            existing_columns = {row[1] for row in cursor.fetchall()}

            for field in ["tenant_id", "agent_id", "chat_stream_id"]:
                if field not in existing_columns:
                    db.execute_sql(f"ALTER TABLE expression ADD COLUMN {field} TEXT")
                    logger.info(f"添加 expression.{field}")

            # 迁移数据
            db.execute_sql(
                """
                UPDATE expression
                SET tenant_id = ?, agent_id = ?
                WHERE tenant_id IS NULL OR tenant_id = ''
            """,
                (self.default_tenant_id, self.default_agent_id),
            )

            logger.info("迁移了 expression 表数据")

    def _migrate_action_records(self):
        """迁移 ActionRecords 表"""
        with db:
            cursor = db.execute_sql("PRAGMA table_info(action_records)")
            existing_columns = {row[1] for row in cursor.fetchall()}

            for field in ["tenant_id", "agent_id", "chat_stream_id"]:
                if field not in existing_columns:
                    db.execute_sql(f"ALTER TABLE action_records ADD COLUMN {field} TEXT")
                    logger.info(f"添加 action_records.{field}")

            # 迁移数据
            db.execute_sql(
                """
                UPDATE action_records
                SET tenant_id = ?, agent_id = ?, chat_stream_id = chat_id
                WHERE tenant_id IS NULL OR tenant_id = ''
            """,
                (self.default_tenant_id, self.default_agent_id),
            )

            logger.info("迁移了 action_records 表数据")

    def _migrate_jargon(self):
        """迁移 Jargon 表"""
        with db:
            cursor = db.execute_sql("PRAGMA table_info(jargon)")
            existing_columns = {row[1] for row in cursor.fetchall()}

            for field in ["tenant_id", "agent_id", "chat_stream_id"]:
                if field not in existing_columns:
                    db.execute_sql(f"ALTER TABLE jargon ADD COLUMN {field} TEXT")
                    logger.info(f"添加 jargon.{field}")

            # 迁移数据
            db.execute_sql(
                """
                UPDATE jargon
                SET tenant_id = ?, agent_id = ?, chat_stream_id = chat_id
                WHERE tenant_id IS NULL OR tenant_id = ''
            """,
                (self.default_tenant_id, self.default_agent_id),
            )

            logger.info("迁移了 jargon 表数据")

    def _migrate_person_info(self):
        """迁移 PersonInfo 表"""
        with db:
            cursor = db.execute_sql("PRAGMA table_info(person_info)")
            existing_columns = {row[1] for row in cursor.fetchall()}

            if "tenant_id" not in existing_columns:
                db.execute_sql("ALTER TABLE person_info ADD COLUMN tenant_id TEXT")
                logger.info("添加 person_info.tenant_id")

            db.execute_sql(
                """
                UPDATE person_info
                SET tenant_id = ?
                WHERE tenant_id IS NULL OR tenant_id = ''
            """,
                (self.default_tenant_id,),
            )

            logger.info("迁移了 person_info 表数据")

    def _migrate_group_info(self):
        """迁移 GroupInfo 表"""
        with db:
            cursor = db.execute_sql("PRAGMA table_info(group_info)")
            existing_columns = {row[1] for row in cursor.fetchall()}

            if "tenant_id" not in existing_columns:
                db.execute_sql("ALTER TABLE group_info ADD COLUMN tenant_id TEXT")
                logger.info("添加 group_info.tenant_id")

            db.execute_sql(
                """
                UPDATE group_info
                SET tenant_id = ?
                WHERE tenant_id IS NULL OR tenant_id = ''
            """,
                (self.default_tenant_id,),
            )

            logger.info("迁移了 group_info 表数据")

    def _create_composite_indexes(self):
        """创建复合索引以优化查询性能"""
        indexes = [
            # ChatStreams 复合索引
            "CREATE INDEX IF NOT EXISTS idx_chat_streams_isolation ON chat_streams(tenant_id, agent_id, platform)",
            "CREATE INDEX IF NOT EXISTS idx_chat_streams_tenant_agent ON chat_streams(tenant_id, agent_id)",
            # Messages 复合索引
            "CREATE INDEX IF NOT EXISTS idx_messages_isolation ON messages(tenant_id, agent_id, platform, chat_stream_id)",
            "CREATE INDEX IF NOT EXISTS idx_messages_tenant_agent ON messages(tenant_id, agent_id)",
            "CREATE INDEX IF NOT EXISTS idx_messages_time_isolation ON messages(tenant_id, time DESC)",
            # MemoryChest 复合索引
            "CREATE INDEX IF NOT EXISTS idx_memory_chest_isolation ON memory_chest(tenant_id, agent_id, memory_level)",
            "CREATE INDEX IF NOT EXISTS idx_memory_chest_platform ON memory_chest(tenant_id, agent_id, platform, memory_level)",
            "CREATE INDEX IF NOT EXISTS idx_memory_chest_chat ON memory_chest(tenant_id, agent_id, chat_stream_id, memory_level)",
            # AgentRecord 复合索引
            "CREATE INDEX IF NOT EXISTS idx_agents_tenant_agent ON agents(tenant_id, agent_id)",
            # LLMUsage 复合索引
            "CREATE INDEX IF NOT EXISTS idx_llm_usage_isolation ON llm_usage(tenant_id, agent_id, platform)",
            "CREATE INDEX IF NOT EXISTS idx_llm_usage_tenant_time ON llm_usage(tenant_id, timestamp DESC)",
            # Expression 复合索引
            "CREATE INDEX IF NOT EXISTS idx_expression_isolation ON expression(tenant_id, agent_id, chat_stream_id)",
            # ActionRecords 复合索引
            "CREATE INDEX IF NOT EXISTS idx_action_records_isolation ON action_records(tenant_id, agent_id, chat_stream_id)",
            # Jargon 复合索引
            "CREATE INDEX IF NOT EXISTS idx_jargon_isolation ON jargon(tenant_id, agent_id, chat_stream_id)",
            # PersonInfo 复合索引
            "CREATE INDEX IF NOT EXISTS idx_person_info_tenant ON person_info(tenant_id)",
            # GroupInfo 复合索引
            "CREATE INDEX IF NOT EXISTS idx_group_info_tenant ON group_info(tenant_id)",
        ]

        with db:
            for index_sql in indexes:
                try:
                    db.execute_sql(index_sql)
                    logger.info(f"创建索引: {index_sql.split('idx_')[1].split(' ')[0]}")
                except Exception as e:
                    logger.warning(f"创建索引失败 (可能已存在): {e}")

    def _generate_isolated_stream_id(self, tenant_id: str, agent_id: str, platform: str, chat_identifier: str) -> str:
        """生成隔离化的 stream_id"""
        components = [tenant_id, agent_id, platform, chat_identifier]
        key = "|".join(components)
        return hashlib.sha256(key.encode()).hexdigest()

    def rollback(self) -> bool:
        """回滚多租户迁移 (危险操作，仅用于紧急情况)"""
        try:
            logger.warning("开始回滚多租户迁移...")

            # 删除隔离字段 (SQLite 不支持直接删除列，需要重建表)
            # 这里提供警告信息，实际回滚需要手动处理
            # 涉及的表: chat_streams, messages, memory_chest, agents,
            # llm_usage, expression, action_records, jargon, person_info, group_info

            logger.error("SQLite 不支持直接删除列，回滚需要手动重建表。")
            logger.error("请参考文档手动执行回滚操作。")

            return False

        except Exception as e:
            logger.exception(f"回滚失败: {e}")
            return False


def execute_multi_tenant_migration(force: bool = False) -> bool:
    """
    便捷函数：执行多租户迁移

    Args:
        force: 是否强制执行迁移

    Returns:
        bool: 迁移是否成功
    """
    migration = MultiTenantMigration()
    return migration.execute_migration(force)


def check_migration_status() -> Dict[str, any]:
    """
    检查迁移状态

    Returns:
        Dict: 迁移状态信息
    """
    try:
        with db:
            # 检查迁移表是否存在
            cursor = db.execute_sql("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='migration_versions'
            """)
            migration_table_exists = len(cursor.fetchall()) > 0

            if not migration_table_exists:
                return {"status": "not_started", "message": "迁移未开始，迁移版本表不存在"}

            # 检查迁移记录
            cursor = db.execute_sql("""
                SELECT migration_name, version, executed_at
                FROM migration_versions
                WHERE migration_name = 'multi_tenant_isolation'
            """)
            migration_record = cursor.fetchone()

            if not migration_record:
                return {"status": "not_migrated", "message": "数据库未完成多租户迁移"}

            # 检查表结构
            tables_status = {}
            tables_to_check = ["chat_streams", "messages", "memory_chest"]

            for table in tables_to_check:
                cursor = db.execute_sql(f"PRAGMA table_info({table})")
                columns = {row[1] for row in cursor.fetchall()}

                required_columns = ["tenant_id", "agent_id"]
                missing_columns = [col for col in required_columns if col not in columns]

                tables_status[table] = {"is_migrated": len(missing_columns) == 0, "missing_columns": missing_columns}

            all_migrated = all(status["is_migrated"] for status in tables_status.values())

            return {
                "status": "completed" if all_migrated else "partial",
                "migration_record": {
                    "name": migration_record[0],
                    "version": migration_record[1],
                    "executed_at": migration_record[2],
                },
                "tables_status": tables_status,
                "message": "迁移完成" if all_migrated else "部分表未完成迁移",
            }

    except Exception as e:
        logger.exception(f"检查迁移状态失败: {e}")
        return {"status": "error", "message": f"检查失败: {str(e)}"}
