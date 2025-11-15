"""
测试数据清理功能
删除测试创建的用户、Agent和相关聊天历史
"""

import logging
import sqlite3
from typing import List, Dict
from datetime import datetime

from src.common.database.database import db
from src.common.database.database_model import UserSessions, AgentRecord, Messages, ChatStreams, TenantUsers
from .api_client import TestUser, TestAgent

logger = logging.getLogger(__name__)


class TestDataCleaner:
    """测试数据清理器"""

    def __init__(self, db_path: str = None):
        """
        初始化清理器

        Args:
            db_path: 数据库路径，如果为None则使用默认配置
        """
        self.db_path = db_path
        self.cleanup_log: List[Dict] = []

    def _get_connection(self):
        """获取数据库连接"""
        if self.db_path:
            return sqlite3.connect(self.db_path)
        else:
            # 使用项目默认数据库连接
            return db.connection()

    def _log_cleanup(self, table: str, operation: str, count: int, details: str = ""):
        """记录清理日志"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "table": table,
            "operation": operation,
            "count": count,
            "details": details,
        }
        self.cleanup_log.append(log_entry)
        logger.info(f"清理 {table}: {operation} - {count} 条记录 {details}")

    async def cleanup_test_users(self, users: List[TestUser]) -> Dict:
        """清理测试用户数据"""
        result = {"users_cleaned": 0, "agents_cleaned": 0, "sessions_cleaned": 0, "errors": []}

        if self.db_path:
            # 使用原生SQL方式（自定义数据库路径）
            conn = self._get_connection()
            cursor = conn.cursor()

            try:
                for user in users:
                    try:
                        # 清理用户会话
                        cursor.execute(
                            "DELETE FROM user_sessions WHERE user_id = ? OR tenant_id = ?",
                            (user.user_id, user.tenant_id),
                        )
                        sessions_deleted = cursor.rowcount
                        if sessions_deleted > 0:
                            self._log_cleanup("user_sessions", "DELETE", sessions_deleted, f"用户 {user.username}")
                        result["sessions_cleaned"] += sessions_deleted

                        # 清理Agent记录
                        cursor.execute("DELETE FROM agents WHERE tenant_id = ?", (user.tenant_id,))
                        agents_deleted = cursor.rowcount
                        if agents_deleted > 0:
                            self._log_cleanup("agents", "DELETE", agents_deleted, f"租户 {user.tenant_id} 的所有Agent")
                        result["agents_cleaned"] += agents_deleted

                        # 清理用户记录
                        cursor.execute(
                            "DELETE FROM tenant_users WHERE user_id = ? OR tenant_id = ?",
                            (user.user_id, user.tenant_id),
                        )
                        users_deleted = cursor.rowcount
                        if users_deleted > 0:
                            self._log_cleanup("tenant_users", "DELETE", users_deleted, f"用户 {user.username}")
                        result["users_cleaned"] += users_deleted

                        conn.commit()

                    except Exception as e:
                        conn.rollback()
                        error_msg = f"清理用户 {user.username} 失败: {e}"
                        result["errors"].append(error_msg)
                        logger.error(error_msg)

            finally:
                conn.close()
        else:
            # 使用Peewee ORM方式（默认数据库）
            try:
                with db:
                    for user in users:
                        try:
                            # 清理用户会话
                            sessions_deleted = (
                                UserSessions.delete()
                                .where(
                                    (UserSessions.user_id == user.user_id) | (UserSessions.tenant_id == user.tenant_id)
                                )
                                .execute()
                            )
                            if sessions_deleted > 0:
                                self._log_cleanup("user_sessions", "DELETE", sessions_deleted, f"用户 {user.username}")
                            result["sessions_cleaned"] += sessions_deleted

                            # 清理Agent记录
                            agents_deleted = (
                                AgentRecord.delete().where(AgentRecord.tenant_id == user.tenant_id).execute()
                            )
                            if agents_deleted > 0:
                                self._log_cleanup(
                                    "agents", "DELETE", agents_deleted, f"租户 {user.tenant_id} 的所有Agent"
                                )
                            result["agents_cleaned"] += agents_deleted

                            # 清理用户记录
                            users_deleted = (
                                TenantUsers.delete()
                                .where(
                                    (TenantUsers.user_id == user.user_id) | (TenantUsers.tenant_id == user.tenant_id)
                                )
                                .execute()
                            )
                            if users_deleted > 0:
                                self._log_cleanup("tenant_users", "DELETE", users_deleted, f"用户 {user.username}")
                            result["users_cleaned"] += users_deleted

                        except Exception as e:
                            error_msg = f"清理用户 {user.username} 失败: {e}"
                            result["errors"].append(error_msg)
                            logger.error(error_msg)

            except Exception as e:
                error_msg = f"数据库操作失败: {e}"
                result["errors"].append(error_msg)
                logger.error(error_msg)

        logger.info(
            f"用户清理完成: {result['users_cleaned']} 用户, "
            f"{result['agents_cleaned']} Agent, {result['sessions_cleaned']} 会话"
        )
        return result

    async def cleanup_chat_history(self, users: List[TestUser], agents: List[TestAgent]) -> Dict:
        """清理聊天历史数据"""
        result = {"messages_cleaned": 0, "chat_streams_cleaned": 0, "errors": []}

        # 获取需要清理的聊天流ID
        tenant_ids = [user.tenant_id for user in users]

        if not tenant_ids:
            return result

        if self.db_path:
            # 使用原生SQL方式（自定义数据库路径）
            conn = self._get_connection()
            cursor = conn.cursor()

            try:
                placeholders = ",".join(["?" for _ in tenant_ids])

                # 清理消息记录
                cursor.execute(f"DELETE FROM messages WHERE tenant_id IN ({placeholders})", tenant_ids)
                messages_deleted = cursor.rowcount
                if messages_deleted > 0:
                    self._log_cleanup("messages", "DELETE", messages_deleted, f"租户 {tenant_ids}")
                result["messages_cleaned"] += messages_deleted

                # 清理聊天流记录
                cursor.execute(f"DELETE FROM chat_streams WHERE tenant_id IN ({placeholders})", tenant_ids)
                streams_deleted = cursor.rowcount
                if streams_deleted > 0:
                    self._log_cleanup("chat_streams", "DELETE", streams_deleted, f"租户 {tenant_ids}")
                result["chat_streams_cleaned"] += streams_deleted

                conn.commit()

            except Exception as e:
                conn.rollback()
                error_msg = f"清理聊天历史失败: {e}"
                result["errors"].append(error_msg)
                logger.error(error_msg)

            finally:
                conn.close()
        else:
            # 使用Peewee ORM方式（默认数据库）
            try:
                with db:
                    # 清理消息记录
                    messages_deleted = Messages.delete().where(Messages.tenant_id.in_(tenant_ids)).execute()
                    if messages_deleted > 0:
                        self._log_cleanup("messages", "DELETE", messages_deleted, f"租户 {tenant_ids}")
                    result["messages_cleaned"] += messages_deleted

                    # 清理聊天流记录
                    streams_deleted = ChatStreams.delete().where(ChatStreams.tenant_id.in_(tenant_ids)).execute()
                    if streams_deleted > 0:
                        self._log_cleanup("chat_streams", "DELETE", streams_deleted, f"租户 {tenant_ids}")
                    result["chat_streams_cleaned"] += streams_deleted

            except Exception as e:
                error_msg = f"清理聊天历史失败: {e}"
                result["errors"].append(error_msg)
                logger.error(error_msg)

        logger.info(f"聊天历史清理完成: {result['messages_cleaned']} 消息, {result['chat_streams_cleaned']} 聊天流")
        return result

    async def cleanup_by_tenant_ids(self, tenant_ids: List[str]) -> Dict:
        """根据租户ID清理数据"""
        result = {
            "tenants_processed": len(tenant_ids),
            "users_cleaned": 0,
            "agents_cleaned": 0,
            "sessions_cleaned": 0,
            "messages_cleaned": 0,
            "chat_streams_cleaned": 0,
            "errors": [],
        }

        if self.db_path:
            # 使用原生SQL方式（自定义数据库路径）
            conn = self._get_connection()
            cursor = conn.cursor()

            try:
                for tenant_id in tenant_ids:
                    try:
                        # 清理各个表
                        tables_to_clean = [
                            ("user_sessions", "tenant_id"),
                            ("messages", "tenant_id"),
                            ("chat_streams", "tenant_id"),
                            ("agents", "tenant_id"),
                            ("tenant_users", "tenant_id"),
                        ]

                        for table_name, id_field in tables_to_clean:
                            cursor.execute(f"DELETE FROM {table_name} WHERE {id_field} = ?", (tenant_id,))
                            deleted_count = cursor.rowcount
                            if deleted_count > 0:
                                self._log_cleanup(table_name, "DELETE", deleted_count, f"租户 {tenant_id}")

                                # 更新结果统计
                                if "user" in table_name:
                                    result["users_cleaned"] += deleted_count
                                elif "agent" in table_name:
                                    result["agents_cleaned"] += deleted_count
                                elif "session" in table_name:
                                    result["sessions_cleaned"] += deleted_count
                                elif "message" in table_name:
                                    result["messages_cleaned"] += deleted_count
                                elif "stream" in table_name:
                                    result["chat_streams_cleaned"] += deleted_count

                        conn.commit()

                    except Exception as e:
                        conn.rollback()
                        error_msg = f"清理租户 {tenant_id} 失败: {e}"
                        result["errors"].append(error_msg)
                        logger.error(error_msg)

            finally:
                conn.close()
        else:
            # 使用Peewee ORM方式（默认数据库）
            try:
                with db:
                    for tenant_id in tenant_ids:
                        try:
                            # 清理用户会话
                            sessions_deleted = (
                                UserSessions.delete().where(UserSessions.tenant_id == tenant_id).execute()
                            )
                            if sessions_deleted > 0:
                                self._log_cleanup("user_sessions", "DELETE", sessions_deleted, f"租户 {tenant_id}")
                            result["sessions_cleaned"] += sessions_deleted

                            # 清理消息记录
                            messages_deleted = Messages.delete().where(Messages.tenant_id == tenant_id).execute()
                            if messages_deleted > 0:
                                self._log_cleanup("messages", "DELETE", messages_deleted, f"租户 {tenant_id}")
                            result["messages_cleaned"] += messages_deleted

                            # 清理聊天流记录
                            streams_deleted = ChatStreams.delete().where(ChatStreams.tenant_id == tenant_id).execute()
                            if streams_deleted > 0:
                                self._log_cleanup("chat_streams", "DELETE", streams_deleted, f"租户 {tenant_id}")
                            result["chat_streams_cleaned"] += streams_deleted

                            # 清理Agent记录
                            agents_deleted = AgentRecord.delete().where(AgentRecord.tenant_id == tenant_id).execute()
                            if agents_deleted > 0:
                                self._log_cleanup("agents", "DELETE", agents_deleted, f"租户 {tenant_id}")
                            result["agents_cleaned"] += agents_deleted

                            # 清理用户记录
                            users_deleted = TenantUsers.delete().where(TenantUsers.tenant_id == tenant_id).execute()
                            if users_deleted > 0:
                                self._log_cleanup("tenant_users", "DELETE", users_deleted, f"租户 {tenant_id}")
                            result["users_cleaned"] += users_deleted

                        except Exception as e:
                            error_msg = f"清理租户 {tenant_id} 失败: {e}"
                            result["errors"].append(error_msg)
                            logger.error(error_msg)

            except Exception as e:
                error_msg = f"数据库操作失败: {e}"
                result["errors"].append(error_msg)
                logger.error(error_msg)

        return result

    async def cleanup_all_test_data(self, users: List[TestUser], agents: List[TestAgent]) -> Dict:
        """清理所有测试数据"""
        logger.info("开始清理所有测试数据...")

        # 清理聊天历史
        chat_result = await self.cleanup_chat_history(users, agents)

        # 清理用户和Agent
        user_result = await self.cleanup_test_users(users)

        # 合并结果
        final_result = {
            "cleanup_completed": True,
            "timestamp": datetime.now().isoformat(),
            "users": user_result,
            "chat_history": chat_result,
            "total_errors": len(user_result["errors"]) + len(chat_result["errors"]),
            "cleanup_log": self.cleanup_log,
        }

        if final_result["total_errors"] > 0:
            logger.error(f"清理过程中发生 {final_result['total_errors']} 个错误")
        else:
            logger.info("所有测试数据清理完成")

        return final_result

    def get_cleanup_report(self) -> Dict:
        """获取清理报告"""
        return {
            "cleanup_operations": len(self.cleanup_log),
            "cleanup_log": self.cleanup_log,
            "summary": {
                "total_records_deleted": sum(log["count"] for log in self.cleanup_log),
                "tables_affected": list(set(log["table"] for log in self.cleanup_log)),
            },
        }

    def save_cleanup_report(self, filepath: str):
        """保存清理报告到文件"""
        import json

        report = self.get_cleanup_report()
        report["generated_at"] = datetime.now().isoformat()

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)

        logger.info(f"清理报告已保存到: {filepath}")


# 便捷函数
async def cleanup_test_scenario(users: List[TestUser], agents: List[TestAgent], save_report: bool = True) -> Dict:
    """清理测试场景"""
    cleaner = TestDataCleaner()

    result = await cleaner.cleanup_all_test_data(users, agents)

    if save_report:
        report_path = f"cleanup_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        cleaner.save_cleanup_report(report_path)

    return result


async def cleanup_by_prefix(prefix: str = "testuser", save_report: bool = True) -> Dict:
    """根据前缀清理测试数据"""
    cleaner = TestDataCleaner()

    try:
        if cleaner.db_path:
            # 使用原生SQL方式（自定义数据库路径）
            conn = cleaner._get_connection()
            cursor = conn.cursor()

            try:
                # 查找匹配前缀的租户ID
                cursor.execute("SELECT DISTINCT tenant_id FROM tenant_users WHERE username LIKE ?", (f"{prefix}%",))
                tenant_ids = [row[0] for row in cursor.fetchall()]

            finally:
                conn.close()
        else:
            # 使用Peewee ORM方式（默认数据库）
            with db:
                tenant_ids = list(
                    TenantUsers.select(TenantUsers.tenant_id)
                    .where(TenantUsers.username.startswith(f"{prefix}%"))
                    .distinct()
                    .scalars()
                )

        if tenant_ids:
            result = await cleaner.cleanup_by_tenant_ids(tenant_ids)

            if save_report:
                report_path = f"cleanup_report_{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                cleaner.save_cleanup_report(report_path)

            logger.info(f"根据前缀 '{prefix}' 清理了 {len(tenant_ids)} 个租户的数据")
            return result
        else:
            logger.info(f"未找到前缀为 '{prefix}' 的测试数据")
            return {"tenants_processed": 0, "errors": []}

    except Exception as e:
        logger.error(f"根据前缀清理失败: {e}")
        return {"tenants_processed": 0, "errors": [str(e)]}
