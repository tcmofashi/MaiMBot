#!/usr/bin/env python3
"""
修复 tenant_id 字段的数据库迁移脚本

这个脚本用于修复现有数据库记录中缺失的 tenant_id 字段，
为所有现有记录设置默认的租户ID值。
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.common.database.database import db
from src.common.logger import get_logger

logger = get_logger("tenant_id_migration")


def backup_database():
    """备份数据库"""
    db_path = db.database
    backup_path = f"{db_path}.backup_{int(time.time())}"

    try:
        import shutil

        shutil.copy2(db_path, backup_path)
        logger.info(f"数据库已备份到: {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"备份数据库失败: {e}")
        return None


def check_tenant_id_columns():
    """检查哪些表有 tenant_id 字段"""
    tables_with_tenant_id = []

    # 获取所有表
    cursor = db.execute_sql("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]

    for table in tables:
        try:
            cursor = db.execute_sql(f"PRAGMA table_info('{table}')")
            columns = [row[1] for row in cursor.fetchall()]
            if "tenant_id" in columns:
                tables_with_tenant_id.append(table)
        except Exception as e:
            logger.warning(f"检查表 {table} 时出错: {e}")

    return tables_with_tenant_id


def fix_agent_records():
    """修复 AgentRecord 表中的 tenant_id"""
    try:
        # 检查是否有 NULL 的 tenant_id
        cursor = db.execute_sql("SELECT COUNT(*) FROM agents WHERE tenant_id IS NULL")
        null_count = cursor.fetchone()[0]

        if null_count == 0:
            logger.info("AgentRecord 表中没有 NULL 的 tenant_id 记录")
            return True

        logger.info(f"发现 {null_count} 条 AgentRecord 记录需要修复 tenant_id")

        # 更新 NULL 记录为默认值
        cursor = db.execute_sql("UPDATE agents SET tenant_id = 'default' WHERE tenant_id IS NULL")
        updated_count = cursor.rowcount

        logger.info(f"已更新 {updated_count} 条 AgentRecord 记录的 tenant_id 为 'default'")
        return True

    except Exception as e:
        logger.error(f"修复 AgentRecord tenant_id 失败: {e}")
        return False


def fix_other_tables(tables_with_tenant_id):
    """修复其他表中的 tenant_id"""
    success = True

    for table in tables_with_tenant_id:
        if table == "agents":  # 已经处理过了
            continue

        try:
            # 检查是否有 NULL 的 tenant_id
            cursor = db.execute_sql(f"SELECT COUNT(*) FROM {table} WHERE tenant_id IS NULL")
            null_count = cursor.fetchone()[0]

            if null_count == 0:
                logger.info(f"表 {table} 中没有 NULL 的 tenant_id 记录")
                continue

            logger.info(f"发现 {null_count} 条 {table} 记录需要修复 tenant_id")

            # 更新 NULL 记录为默认值
            cursor = db.execute_sql(f"UPDATE {table} SET tenant_id = 'default' WHERE tenant_id IS NULL")
            updated_count = cursor.rowcount

            logger.info(f"已更新 {updated_count} 条 {table} 记录的 tenant_id 为 'default'")

        except Exception as e:
            logger.error(f"修复表 {table} tenant_id 失败: {e}")
            success = False

    return success


def verify_fix():
    """验证修复结果"""
    try:
        # 检查所有有 tenant_id 的表
        tables_with_tenant_id = check_tenant_id_columns()

        all_fixed = True
        for table in tables_with_tenant_id:
            cursor = db.execute_sql(f"SELECT COUNT(*) FROM {table} WHERE tenant_id IS NULL")
            null_count = cursor.fetchone()[0]

            if null_count > 0:
                logger.error(f"表 {table} 仍有 {null_count} 条记录的 tenant_id 为 NULL")
                all_fixed = False
            else:
                logger.info(f"✓ 表 {table} 的 tenant_id 已全部修复")

        return all_fixed

    except Exception as e:
        logger.error(f"验证修复结果失败: {e}")
        return False


def main():
    """主函数"""
    logger.info("开始修复 tenant_id 字段...")

    # 备份数据库
    backup_path = backup_database()
    if not backup_path:
        logger.error("数据库备份失败，中止修复")
        return False

    try:
        # 检查哪些表有 tenant_id 字段
        tables_with_tenant_id = check_tenant_id_columns()
        logger.info(f"发现以下表有 tenant_id 字段: {tables_with_tenant_id}")

        # 修复 AgentRecord 表（优先处理，因为这是最关键的）
        if not fix_agent_records():
            logger.error("修复 AgentRecord 失败")
            return False

        # 修复其他表
        if not fix_other_tables(tables_with_tenant_id):
            logger.error("修复其他表失败")
            return False

        # 验证修复结果
        if not verify_fix():
            logger.error("验证修复结果失败")
            return False

        logger.info("✓ tenant_id 字段修复完成")
        logger.info(f"数据库备份保存在: {backup_path}")
        return True

    except Exception as e:
        logger.error(f"修复过程中发生异常: {e}")
        return False


if __name__ == "__main__":
    import time

    try:
        success = main()
        if success:
            logger.info("tenant_id 修复成功完成")
            sys.exit(0)
        else:
            logger.error("tenant_id 修复失败")
            sys.exit(1)
    except KeyboardInterrupt:
        logger.info("用户中断修复过程")
        sys.exit(1)
    except Exception as e:
        logger.error(f"修复脚本执行失败: {e}")
        sys.exit(1)
