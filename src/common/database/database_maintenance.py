"""
MaiBot 多租户数据库维护工具
提供数据库健康检查、数据一致性验证、清理和优化功能

作者: Claude
创建时间: 2025-01-12
"""

import datetime
from typing import Dict, Any

from src.common.logger import get_logger
from .database import db

logger = get_logger("database_maintenance")


class DatabaseMaintenance:
    """数据库维护工具"""

    def __init__(self):
        self.maintenance_log = []

    def run_full_maintenance(self) -> Dict[str, Any]:
        """
        运行完整的数据库维护流程

        Returns:
            Dict: 维护结果报告
        """
        logger.info("开始数据库完整维护...")
        start_time = datetime.datetime.now()

        results = {
            "start_time": start_time.isoformat(),
            "health_check": self.health_check(),
            "consistency_check": self.check_data_consistency(),
            "cleanup": self.cleanup_orphaned_data(),
            "optimization": self.optimize_database(),
            "statistics": self.generate_statistics(),
        }

        end_time = datetime.datetime.now()
        results["end_time"] = end_time.isoformat()
        results["duration"] = (end_time - start_time).total_seconds()

        logger.info(f"数据库维护完成，耗时: {results['duration']:.2f}秒")
        return results

    def health_check(self) -> Dict[str, Any]:
        """
        数据库健康检查

        Returns:
            Dict: 健康检查结果
        """
        logger.info("执行数据库健康检查...")

        health_status = {
            "overall_health": "healthy",
            "issues": [],
            "warnings": [],
            "table_status": {},
            "index_status": {},
            "connection_info": {},
        }

        try:
            with db:
                # 1. 检查数据库连接
                cursor = db.execute_sql("SELECT sqlite_version()")
                db_version = cursor.fetchone()[0]
                health_status["connection_info"]["database_version"] = db_version

                # 2. 检查表完整性
                tables_to_check = [
                    "agents",
                    "chat_streams",
                    "messages",
                    "memory_chest",
                    "llm_usage",
                    "expression",
                    "action_records",
                    "jargon",
                    "person_info",
                    "group_info",
                ]

                for table_name in tables_to_check:
                    table_info = self._check_table_health(table_name)
                    health_status["table_status"][table_name] = table_info

                    if not table_info["healthy"]:
                        health_status["overall_health"] = "degraded"
                        health_status["issues"].append(f"表 {table_name} 健康状态异常")

                # 3. 检查索引状态
                index_status = self._check_index_health()
                health_status["index_status"] = index_status

                if index_status["missing_indexes"]:
                    health_status["overall_health"] = "degraded"
                    health_status["warnings"].append("存在缺失的索引")

                # 4. 检查数据库大小
                size_info = self._get_database_size_info()
                health_status["database_size"] = size_info

                if size_info["total_size_mb"] > 1000:  # 超过1GB
                    health_status["warnings"].append("数据库大小超过1GB，建议清理")

        except Exception as e:
            logger.exception(f"健康检查失败: {e}")
            health_status["overall_health"] = "error"
            health_status["issues"].append(f"健康检查异常: {str(e)}")

        return health_status

    def _check_table_health(self, table_name: str) -> Dict[str, Any]:
        """检查单个表的健康状态"""
        try:
            if not db.table_exists(table_name):
                return {"healthy": False, "error": "表不存在", "row_count": 0, "size_bytes": 0}

            # 检查行数
            cursor = db.execute_sql(f"SELECT COUNT(*) FROM {table_name}")
            row_count = cursor.fetchone()[0]

            # 检查表大小（SQLite特有）
            try:
                cursor = db.execute_sql(f"SELECT COUNT(*) * 1024 FROM {table_name}")
                estimated_size = cursor.fetchone()[0]
            except Exception:
                estimated_size = 0

            # 检查隔离字段（如果适用）
            isolation_issues = []
            if table_name in [
                "chat_streams",
                "messages",
                "memory_chest",
                "llm_usage",
                "expression",
                "action_records",
                "jargon",
            ]:
                cursor = db.execute_sql(f"PRAGMA table_info({table_name})")
                columns = {row[1] for row in cursor.fetchall()}

                required_fields = ["tenant_id", "agent_id"]
                if table_name in ["chat_streams", "messages"]:
                    required_fields.extend(["platform", "chat_stream_id"])
                elif table_name == "memory_chest":
                    required_fields.extend(["memory_level", "memory_scope"])

                missing_fields = [field for field in required_fields if field not in columns]
                if missing_fields:
                    isolation_issues = missing_fields

            return {
                "healthy": len(isolation_issues) == 0,
                "row_count": row_count,
                "estimated_size_bytes": estimated_size,
                "isolation_issues": isolation_issues,
            }

        except Exception as e:
            return {"healthy": False, "error": str(e), "row_count": 0, "size_bytes": 0}

    def _check_index_health(self) -> Dict[str, Any]:
        """检查索引健康状态"""
        required_indexes = [
            "idx_agents_tenant_agent",
            "idx_chat_streams_isolation",
            "idx_messages_isolation",
            "idx_memory_chest_isolation",
            "idx_llm_usage_isolation",
            "idx_expression_isolation",
            "idx_action_records_isolation",
            "idx_jargon_isolation",
            "idx_person_info_tenant",
            "idx_group_info_tenant",
        ]

        existing_indexes = []
        missing_indexes = []

        for index_name in required_indexes:
            try:
                cursor = db.execute_sql("SELECT name FROM sqlite_master WHERE type='index' AND name=?", (index_name,))
                if cursor.fetchone():
                    existing_indexes.append(index_name)
                else:
                    missing_indexes.append(index_name)
            except Exception as e:
                logger.warning(f"检查索引 {index_name} 失败: {e}")
                missing_indexes.append(index_name)

        return {
            "required_indexes": required_indexes,
            "existing_indexes": existing_indexes,
            "missing_indexes": missing_indexes,
            "coverage_ratio": len(existing_indexes) / len(required_indexes),
        }

    def _get_database_size_info(self) -> Dict[str, Any]:
        """获取数据库大小信息"""
        try:
            # 获取主数据库文件大小
            cursor = db.execute_sql("SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()")
            total_size = cursor.fetchone()[0] if cursor.fetchone() else 0

            return {
                "total_size_bytes": total_size,
                "total_size_mb": total_size / (1024 * 1024),
                "total_pages": db.execute_sql("SELECT page_count FROM pragma_page_count()").fetchone()[0],
                "page_size": db.execute_sql("SELECT page_size FROM pragma_page_size()").fetchone()[0],
            }
        except Exception as e:
            logger.warning(f"获取数据库大小信息失败: {e}")
            return {"total_size_bytes": 0, "total_size_mb": 0}

    def check_data_consistency(self) -> Dict[str, Any]:
        """
        检查数据一致性

        Returns:
            Dict: 一致性检查结果
        """
        logger.info("执行数据一致性检查...")

        consistency_results = {
            "overall_consistency": "consistent",
            "issues": [],
            "warnings": [],
            "checks_performed": [],
        }

        try:
            with db:
                # 1. 检查ChatStreams和Messages的一致性
                chat_message_consistency = self._check_chat_message_consistency()
                consistency_results["checks_performed"].append(
                    {"name": "chat_message_consistency", "result": chat_message_consistency}
                )

                if not chat_message_consistency["consistent"]:
                    consistency_results["overall_consistency"] = "inconsistent"
                    consistency_results["issues"].extend(chat_message_consistency["issues"])

                # 2. 检查隔离字段一致性
                isolation_consistency = self._check_isolation_field_consistency()
                consistency_results["checks_performed"].append(
                    {"name": "isolation_field_consistency", "result": isolation_consistency}
                )

                if not isolation_consistency["consistent"]:
                    consistency_results["overall_consistency"] = "inconsistent"
                    consistency_results["issues"].extend(isolation_consistency["issues"])

                # 3. 检查外键一致性
                fk_consistency = self._check_foreign_key_consistency()
                consistency_results["checks_performed"].append(
                    {"name": "foreign_key_consistency", "result": fk_consistency}
                )

                if fk_consistency["warnings"]:
                    consistency_results["warnings"].extend(fk_consistency["warnings"])

        except Exception as e:
            logger.exception(f"一致性检查失败: {e}")
            consistency_results["overall_consistency"] = "error"
            consistency_results["issues"].append(f"一致性检查异常: {str(e)}")

        return consistency_results

    def _check_chat_message_consistency(self) -> Dict[str, Any]:
        """检查ChatStreams和Messages表的一致性"""
        issues = []

        try:
            # 检查消息是否都有对应的聊天流
            cursor = db.execute_sql("""
                SELECT COUNT(*) FROM messages m
                LEFT JOIN chat_streams cs ON m.chat_stream_id = cs.chat_stream_id
                WHERE m.chat_stream_id IS NOT NULL AND cs.chat_stream_id IS NULL
            """)
            orphaned_messages = cursor.fetchone()[0]

            if orphaned_messages > 0:
                issues.append(f"发现 {orphaned_messages} 条孤立消息（没有对应的聊天流）")

            # 检查隔离字段一致性
            cursor = db.execute_sql("""
                SELECT COUNT(*) FROM messages m
                LEFT JOIN chat_streams cs ON m.chat_stream_id = cs.chat_stream_id
                WHERE m.chat_stream_id IS NOT NULL
                  AND cs.chat_stream_id IS NOT NULL
                  AND (m.tenant_id != cs.tenant_id
                       OR m.agent_id != cs.agent_id
                       OR (m.platform != cs.platform AND m.platform IS NOT NULL AND cs.platform IS NOT NULL))
            """)
            inconsistent_isolation = cursor.fetchone()[0]

            if inconsistent_isolation > 0:
                issues.append(f"发现 {inconsistent_isolation} 条隔离字段不一致的消息")

        except Exception as e:
            logger.exception(f"聊天消息一致性检查失败: {e}")
            issues.append(f"检查异常: {str(e)}")

        return {"consistent": len(issues) == 0, "issues": issues}

    def _check_isolation_field_consistency(self) -> Dict[str, Any]:
        """检查隔离字段一致性"""
        issues = []

        try:
            # 检查各表的空隔离字段
            tables_to_check = [
                ("chat_streams", ["tenant_id", "agent_id", "platform", "chat_stream_id"]),
                ("messages", ["tenant_id", "agent_id", "platform", "chat_stream_id"]),
                ("memory_chest", ["tenant_id", "agent_id", "memory_level", "memory_scope"]),
            ]

            for table_name, required_fields in tables_to_check:
                for field in required_fields:
                    cursor = db.execute_sql(f"SELECT COUNT(*) FROM {table_name} WHERE {field} IS NULL OR {field} = ''")
                    null_count = cursor.fetchone()[0]

                    if null_count > 0:
                        issues.append(f"表 {table_name} 有 {null_count} 条记录的 {field} 字段为空")

        except Exception as e:
            logger.exception(f"隔离字段一致性检查失败: {e}")
            issues.append(f"检查异常: {str(e)}")

        return {"consistent": len(issues) == 0, "issues": issues}

    def _check_foreign_key_consistency(self) -> Dict[str, Any]:
        """检查外键一致性（警告级别）"""
        warnings = []

        try:
            # 检查是否有引用不存在agent的记录
            for table_name in ["chat_streams", "messages", "memory_chest"]:
                cursor = db.execute_sql(f"""
                    SELECT COUNT(*) FROM {table_name} t
                    LEFT JOIN agents a ON t.tenant_id = a.tenant_id AND t.agent_id = a.agent_id
                    WHERE t.agent_id IS NOT NULL AND t.agent_id != '' AND a.agent_id IS NULL
                """)
                orphaned_count = cursor.fetchone()[0]

                if orphaned_count > 0:
                    warnings.append(f"表 {table_name} 有 {orphaned_count} 条记录引用了不存在的智能体")

        except Exception as e:
            logger.exception(f"外键一致性检查失败: {e}")
            warnings.append(f"检查异常: {str(e)}")

        return {"warnings": warnings}

    def cleanup_orphaned_data(self) -> Dict[str, Any]:
        """
        清理孤立数据

        Returns:
            Dict: 清理结果
        """
        logger.info("开始清理孤立数据...")

        cleanup_results = {"items_cleaned": 0, "cleanup_operations": [], "errors": []}

        try:
            with db:
                # 1. 清理孤立的消息记录
                try:
                    cursor = db.execute_sql("""
                        DELETE FROM messages
                        WHERE chat_stream_id IN (
                            SELECT m.chat_stream_id FROM messages m
                            LEFT JOIN chat_streams cs ON m.chat_stream_id = cs.chat_stream_id
                            WHERE m.chat_stream_id IS NOT NULL AND cs.chat_stream_id IS NULL
                        )
                    """)
                    messages_cleaned = cursor.rowcount
                    cleanup_results["items_cleaned"] += messages_cleaned
                    cleanup_results["cleanup_operations"].append(
                        {"operation": "删除孤立消息", "count": messages_cleaned}
                    )
                    logger.info(f"清理了 {messages_cleaned} 条孤立消息")
                except Exception as e:
                    cleanup_results["errors"].append(f"清理孤立消息失败: {e}")

                # 2. 清理空字符串的隔离字段（设置为默认值）
                default_tenant = "default_tenant"
                default_agent = "default_agent"

                for table_name in ["chat_streams", "messages", "memory_chest"]:
                    try:
                        # 清理空的tenant_id
                        cursor = db.execute_sql(
                            f"""
                            UPDATE {table_name}
                            SET tenant_id = ?
                            WHERE tenant_id IS NULL OR tenant_id = ''
                        """,
                            (default_tenant,),
                        )
                        tenant_fixed = cursor.rowcount

                        # 清理空的agent_id
                        cursor = db.execute_sql(
                            f"""
                            UPDATE {table_name}
                            SET agent_id = ?
                            WHERE agent_id IS NULL OR agent_id = ''
                        """,
                            (default_agent,),
                        )
                        agent_fixed = cursor.rowcount

                        if tenant_fixed > 0 or agent_fixed > 0:
                            cleanup_results["items_cleaned"] += tenant_fixed + agent_fixed
                            cleanup_results["cleanup_operations"].append(
                                {
                                    "operation": f"修复{table_name}表隔离字段",
                                    "tenant_fixed": tenant_fixed,
                                    "agent_fixed": agent_fixed,
                                }
                            )

                    except Exception as e:
                        cleanup_results["errors"].append(f"修复{table_name}表隔离字段失败: {e}")

                # 3. 清理重复的记忆记录
                try:
                    cursor = db.execute_sql("""
                        DELETE FROM memory_chest
                        WHERE id NOT IN (
                            SELECT MIN(id) FROM memory_chest
                            GROUP BY tenant_id, agent_id, COALESCE(platform, ''),
                                   COALESCE(chat_stream_id, ''), title, content
                        )
                    """)
                    duplicates_cleaned = cursor.rowcount
                    cleanup_results["items_cleaned"] += duplicates_cleaned
                    if duplicates_cleaned > 0:
                        cleanup_results["cleanup_operations"].append(
                            {"operation": "删除重复记忆", "count": duplicates_cleaned}
                        )
                        logger.info(f"清理了 {duplicates_cleaned} 条重复记忆")
                except Exception as e:
                    cleanup_results["errors"].append(f"清理重复记忆失败: {e}")

        except Exception as e:
            logger.exception(f"数据清理失败: {e}")
            cleanup_results["errors"].append(f"清理过程异常: {str(e)}")

        logger.info(f"数据清理完成，共清理 {cleanup_results['items_cleaned']} 项")
        return cleanup_results

    def optimize_database(self) -> Dict[str, Any]:
        """
        优化数据库性能

        Returns:
            Dict: 优化结果
        """
        logger.info("开始数据库优化...")

        optimization_results = {"optimizations_performed": [], "errors": [], "space_freed_mb": 0}

        try:
            with db:
                # 1. 分析表统计信息
                try:
                    tables = [
                        "agents",
                        "chat_streams",
                        "messages",
                        "memory_chest",
                        "llm_usage",
                        "expression",
                        "action_records",
                        "jargon",
                        "person_info",
                        "group_info",
                    ]

                    for table_name in tables:
                        if db.table_exists(table_name):
                            db.execute_sql(f"ANALYZE {table_name}")

                    optimization_results["optimizations_performed"].append(
                        {"operation": "更新表统计信息", "tables_analyzed": len(tables)}
                    )
                except Exception as e:
                    optimization_results["errors"].append(f"分析表统计信息失败: {e}")

                # 2. 清理数据库碎片
                try:
                    start_size = self._get_database_size_info()["total_size_bytes"]

                    db.execute_sql("VACUUM")

                    end_size = self._get_database_size_info()["total_size_bytes"]
                    space_freed = (start_size - end_size) / (1024 * 1024)

                    optimization_results["space_freed_mb"] = space_freed
                    optimization_results["optimizations_performed"].append(
                        {"operation": "数据库碎片整理", "space_freed_mb": space_freed}
                    )

                    logger.info(f"数据库优化完成，释放空间: {space_freed:.2f} MB")

                except Exception as e:
                    optimization_results["errors"].append(f"数据库碎片整理失败: {e}")

                # 3. 重建索引
                try:
                    db.execute_sql("REINDEX")
                    optimization_results["optimizations_performed"].append({"operation": "重建索引"})
                except Exception as e:
                    optimization_results["errors"].append(f"重建索引失败: {e}")

        except Exception as e:
            logger.exception(f"数据库优化失败: {e}")
            optimization_results["errors"].append(f"优化过程异常: {str(e)}")

        return optimization_results

    def generate_statistics(self) -> Dict[str, Any]:
        """
        生成数据库统计信息

        Returns:
            Dict: 统计信息
        """
        logger.info("生成数据库统计信息...")

        statistics = {
            "generation_time": datetime.datetime.now().isoformat(),
            "table_statistics": {},
            "isolation_statistics": {},
            "usage_statistics": {},
        }

        try:
            with db:
                # 1. 表统计
                tables_to_analyze = [
                    "agents",
                    "chat_streams",
                    "messages",
                    "memory_chest",
                    "llm_usage",
                    "expression",
                    "action_records",
                    "jargon",
                    "person_info",
                    "group_info",
                ]

                for table_name in tables_to_analyze:
                    if db.table_exists(table_name):
                        cursor = db.execute_sql(f"SELECT COUNT(*) FROM {table_name}")
                        row_count = cursor.fetchone()[0]

                        statistics["table_statistics"][table_name] = {"row_count": row_count}

                # 2. 租户隔离统计
                try:
                    cursor = db.execute_sql("SELECT COUNT(DISTINCT tenant_id) FROM agents")
                    tenant_count = cursor.fetchone()[0] or 0

                    cursor = db.execute_sql("SELECT COUNT(DISTINCT agent_id) FROM agents")
                    agent_count = cursor.fetchone()[0] or 0

                    statistics["isolation_statistics"] = {"total_tenants": tenant_count, "total_agents": agent_count}
                except Exception as e:
                    logger.warning(f"获取隔离统计信息失败: {e}")

                # 3. 使用量统计
                try:
                    # 最近30天的LLM使用量
                    cursor = db.execute_sql("""
                        SELECT COUNT(*), SUM(total_tokens), SUM(cost)
                        FROM llm_usage
                        WHERE timestamp >= datetime('now', '-30 days')
                    """)
                    usage_stats = cursor.fetchone()

                    statistics["usage_statistics"] = {
                        "last_30_days": {
                            "requests": usage_stats[0] or 0,
                            "tokens": usage_stats[1] or 0,
                            "cost": usage_stats[2] or 0.0,
                        }
                    }
                except Exception as e:
                    logger.warning(f"获取使用量统计失败: {e}")

        except Exception as e:
            logger.exception(f"生成统计信息失败: {e}")

        return statistics


def run_database_maintenance() -> Dict[str, Any]:
    """
    便捷函数：运行完整的数据库维护

    Returns:
        Dict: 维护结果报告
    """
    maintenance = DatabaseMaintenance()
    return maintenance.run_full_maintenance()


def health_check() -> Dict[str, Any]:
    """
    便捷函数：仅执行健康检查

    Returns:
        Dict: 健康检查结果
    """
    maintenance = DatabaseMaintenance()
    return maintenance.health_check()


if __name__ == "__main__":
    # 运行完整维护
    results = run_database_maintenance()

    print("=== 数据库维护报告 ===")
    print(f"开始时间: {results['start_time']}")
    print(f"结束时间: {results['end_time']}")
    print(f"耗时: {results['duration']:.2f} 秒")

    print("\n=== 健康检查 ===")
    health = results["health_check"]
    print(f"整体健康状态: {health['overall_health']}")

    if health["issues"]:
        print("问题:")
        for issue in health["issues"]:
            print(f"  - {issue}")

    if health["warnings"]:
        print("警告:")
        for warning in health["warnings"]:
            print(f"  - {warning}")

    print("\n=== 数据一致性 ===")
    consistency = results["consistency_check"]
    print(f"一致性状态: {consistency['overall_consistency']}")

    print("\n=== 清理结果 ===")
    cleanup = results["cleanup"]
    print(f"清理项目数: {cleanup['items_cleaned']}")

    print("\n=== 优化结果 ===")
    optimization = results["optimization"]
    print(f"释放空间: {optimization['space_freed_mb']:.2f} MB")

    print("\n=== 统计信息 ===")
    stats = results["statistics"]
    print(f"表统计: {len(stats['table_statistics'])} 个表")
    if "isolation_statistics" in stats:
        print(f"租户数: {stats['isolation_statistics'].get('total_tenants', 0)}")
        print(f"智能体数: {stats['isolation_statistics'].get('total_agents', 0)}")
