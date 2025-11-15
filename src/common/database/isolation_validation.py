"""
数据库表隔离字段完整性验证工具
检查所有表是否包含必要的隔离字段

作者: Claude
创建时间: 2025-01-12
"""

from typing import Dict, List, Set
from src.common.logger import get_logger
from .database import db

logger = get_logger("isolation_validation")


class IsolationFieldValidator:
    """隔离字段验证器"""

    # 定义各表应有的隔离字段
    TABLE_ISOLATION_FIELDS = {
        "agents": ["tenant_id"],  # AgentRecord
        "chat_streams": ["tenant_id", "agent_id", "platform", "chat_stream_id"],
        "messages": ["tenant_id", "agent_id", "platform", "chat_stream_id"],
        "memory_chest": ["tenant_id", "agent_id", "platform", "chat_stream_id", "memory_level", "memory_scope"],
        "llm_usage": ["tenant_id", "agent_id", "platform"],
        "expression": ["tenant_id", "agent_id", "chat_stream_id"],
        "action_records": ["tenant_id", "agent_id", "chat_stream_id"],
        "jargon": ["tenant_id", "agent_id", "chat_stream_id"],
        "person_info": ["tenant_id"],
        "group_info": ["tenant_id"],
    }

    def __init__(self):
        self.validation_results = {}

    def validate_all_tables(self) -> Dict[str, Dict]:
        """
        验证所有表的隔离字段完整性

        Returns:
            Dict: 验证结果
        """
        logger.info("开始验证数据库表隔离字段完整性...")

        try:
            with db:
                for table_name, required_fields in self.TABLE_ISOLATION_FIELDS.items():
                    result = self._validate_table(table_name, required_fields)
                    self.validation_results[table_name] = result

                self._log_validation_summary()
                return self.validation_results

        except Exception as e:
            logger.exception(f"验证过程中发生错误: {e}")
            return {"error": str(e)}

    def _validate_table(self, table_name: str, required_fields: List[str]) -> Dict:
        """
        验证单个表的隔离字段

        Args:
            table_name: 表名
            required_fields: 必需的隔离字段列表

        Returns:
            Dict: 验证结果
        """
        try:
            # 检查表是否存在
            if not db.table_exists(table_name):
                return {
                    "status": "error",
                    "message": f"表 {table_name} 不存在",
                    "missing_fields": required_fields,
                    "has_all_fields": False,
                }

            # 获取表的现有字段
            cursor = db.execute_sql(f"PRAGMA table_info('{table_name}')")
            existing_fields = {row[1] for row in cursor.fetchall()}

            # 检查缺失的字段
            missing_fields = [field for field in required_fields if field not in existing_fields]

            # 检查索引（可选的详细验证）
            indexes = self._get_table_indexes(table_name)
            indexed_fields = self._extract_indexed_fields(indexes)

            result = {
                "status": "success",
                "exists": True,
                "total_fields": len(existing_fields),
                "required_fields": required_fields,
                "missing_fields": missing_fields,
                "has_all_fields": len(missing_fields) == 0,
                "existing_isolation_fields": list(existing_fields.intersection(required_fields)),
                "indexed_isolation_fields": list(set(required_fields).intersection(indexed_fields)),
            }

            if not result["has_all_fields"]:
                logger.warning(f"表 {table_name} 缺失隔离字段: {missing_fields}")
            else:
                logger.info(f"表 {table_name} 隔离字段完整")

            return result

        except Exception as e:
            logger.exception(f"验证表 {table_name} 时发生错误: {e}")
            return {"status": "error", "message": str(e), "missing_fields": required_fields, "has_all_fields": False}

    def _get_table_indexes(self, table_name: str) -> List[Dict]:
        """获取表的索引信息"""
        try:
            cursor = db.execute_sql(f"PRAGMA index_list('{table_name}')")
            indexes = []

            for row in cursor.fetchall():
                index_name = row[1]
                cursor2 = db.execute_sql(f"PRAGMA index_info('{index_name}')")
                index_columns = [col[2] for col in cursor2.fetchall()]
                indexes.append({"name": index_name, "columns": index_columns})

            return indexes
        except Exception as e:
            logger.warning(f"获取表 {table_name} 索引信息失败: {e}")
            return []

    def _extract_indexed_fields(self, indexes: List[Dict]) -> Set[str]:
        """从索引信息中提取被索引的字段"""
        indexed_fields = set()
        for index in indexes:
            indexed_fields.update(index["columns"])
        return indexed_fields

    def _log_validation_summary(self):
        """记录验证摘要"""
        total_tables = len(self.validation_results)
        valid_tables = sum(1 for result in self.validation_results.values() if result.get("has_all_fields", False))

        logger.info(f"隔离字段验证完成: {valid_tables}/{total_tables} 个表符合要求")

        # 列出有问题的表
        problematic_tables = [
            table for table, result in self.validation_results.items() if not result.get("has_all_fields", False)
        ]

        if problematic_tables:
            logger.warning(f"以下表需要修复隔离字段: {problematic_tables}")

            # 详细列出缺失字段
            for table in problematic_tables:
                result = self.validation_results[table]
                missing = result.get("missing_fields", [])
                if missing:
                    logger.warning(f"  {table}: 缺失字段 {missing}")

    def generate_migration_sql(self) -> Dict[str, List[str]]:
        """
        为缺失的隔离字段生成修复SQL

        Returns:
            Dict: 表名到SQL语句列表的映射
        """
        migration_sql = {}

        for table_name, result in self.validation_results.items():
            if not result.get("has_all_fields", False):
                missing_fields = result.get("missing_fields", [])
                sql_statements = []

                for field in missing_fields:
                    sql = f"ALTER TABLE {table_name} ADD COLUMN {field} TEXT"
                    sql_statements.append(sql)

                if sql_statements:
                    migration_sql[table_name] = sql_statements

        return migration_sql

    def validate_indexes(self) -> Dict[str, List[str]]:
        """
        验证隔离字段的索引

        Returns:
            Dict: 表名到缺失索引列表的映射
        """
        # 推荐的隔离字段索引
        RECOMMENDED_INDEXES = {
            "agents": ["CREATE INDEX IF NOT EXISTS idx_agents_tenant_agent ON agents(tenant_id, agent_id)"],
            "chat_streams": [
                "CREATE INDEX IF NOT EXISTS idx_chat_streams_isolation ON chat_streams(tenant_id, agent_id, platform)",
                "CREATE INDEX IF NOT EXISTS idx_chat_streams_tenant_agent ON chat_streams(tenant_id, agent_id)",
            ],
            "messages": [
                "CREATE INDEX IF NOT EXISTS idx_messages_isolation ON messages(tenant_id, agent_id, platform, chat_stream_id)",
                "CREATE INDEX IF NOT EXISTS idx_messages_tenant_agent ON messages(tenant_id, agent_id)",
            ],
            "memory_chest": [
                "CREATE INDEX IF NOT EXISTS idx_memory_chest_isolation ON memory_chest(tenant_id, agent_id, memory_level)",
                "CREATE INDEX IF NOT EXISTS idx_memory_chest_platform ON memory_chest(tenant_id, agent_id, platform, memory_level)",
                "CREATE INDEX IF NOT EXISTS idx_memory_chest_chat ON memory_chest(tenant_id, agent_id, chat_stream_id, memory_level)",
            ],
            "llm_usage": [
                "CREATE INDEX IF NOT EXISTS idx_llm_usage_isolation ON llm_usage(tenant_id, agent_id, platform)"
            ],
            "expression": [
                "CREATE INDEX IF NOT EXISTS idx_expression_isolation ON expression(tenant_id, agent_id, chat_stream_id)"
            ],
            "action_records": [
                "CREATE INDEX IF NOT EXISTS idx_action_records_isolation ON action_records(tenant_id, agent_id, chat_stream_id)"
            ],
            "jargon": [
                "CREATE INDEX IF NOT EXISTS idx_jargon_isolation ON jargon(tenant_id, agent_id, chat_stream_id)"
            ],
            "person_info": ["CREATE INDEX IF NOT EXISTS idx_person_info_tenant ON person_info(tenant_id)"],
            "group_info": ["CREATE INDEX IF NOT EXISTS idx_group_info_tenant ON group_info(tenant_id)"],
        }

        missing_indexes = {}

        for table_name, index_sqls in RECOMMENDED_INDEXES.items():
            table_missing = []

            for index_sql in index_sqls:
                # 提取索引名称
                index_name = index_sql.split("idx_")[1].split(" ")[0]

                # 检查索引是否已存在
                cursor = db.execute_sql(
                    "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (f"idx_{index_name}",)
                )

                if not cursor.fetchone():
                    table_missing.append(index_sql)

            if table_missing:
                missing_indexes[table_name] = table_missing

        return missing_indexes


def validate_isolation_fields() -> Dict:
    """
    便捷函数：验证所有表的隔离字段

    Returns:
        Dict: 验证结果
    """
    validator = IsolationFieldValidator()
    return validator.validate_all_tables()


def generate_isolation_fixes() -> Dict[str, Dict[str, List[str]]]:
    """
    便捷函数：生成隔离字段修复SQL

    Returns:
        Dict: 包含字段修复和索引创建SQL的字典
    """
    validator = IsolationFieldValidator()
    validator.validate_all_tables()

    return {"field_fixes": validator.generate_migration_sql(), "index_fixes": validator.validate_indexes()}


if __name__ == "__main__":
    # 执行验证
    results = validate_isolation_fields()

    # 生成修复SQL
    fixes = generate_isolation_fixes()

    print("=== 隔离字段验证结果 ===")
    for table, result in results.items():
        status = "✓" if result.get("has_all_fields", False) else "✗"
        print(f"{status} {table}")
        if not result.get("has_all_fields", False):
            print(f"  缺失字段: {result.get('missing_fields', [])}")

    print("\n=== 修复SQL ===")
    if fixes["field_fixes"]:
        print("字段修复:")
        for table, sqls in fixes["field_fixes"].items():
            print(f"  {table}:")
            for sql in sqls:
                print(f"    {sql}")

    if fixes["index_fixes"]:
        print("索引创建:")
        for table, sqls in fixes["index_fixes"].items():
            print(f"  {table}:")
            for sql in sqls:
                print(f"    {sql}")
