#!/usr/bin/env python3
"""
MaiBot 多租户隔离迁移执行脚本

使用方法:
    python scripts/run_multi_tenant_migration.py --check     # 检查迁移状态
    python scripts/run_multi_tenant_migration.py --migrate    # 执行迁移
    python scripts/run_multi_tenant_migration.py --force      # 强制执行迁移
"""

import argparse
import sys
import os

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.common.logger import get_logger
from src.common.database.multi_tenant_migration import execute_multi_tenant_migration, check_migration_status

logger = get_logger("migration_script")


def print_status(status):
    """打印迁移状态"""
    print("=" * 60)
    print("MaiBot 多租户隔离迁移状态")
    print("=" * 60)

    status_map = {
        "not_started": "❌ 未开始",
        "not_migrated": "⚠️ 未迁移",
        "partial": "🔄 部分完成",
        "completed": "✅ 已完成",
        "error": "❌ 错误",
    }

    print(f"状态: {status_map.get(status['status'], status['status'])}")
    print(f"信息: {status.get('message', '无')}")

    if status.get("migration_record"):
        record = status["migration_record"]
        print("\n迁移记录:")
        print(f"  - 名称: {record['name']}")
        print(f"  - 版本: {record['version']}")
        print(f"  - 执行时间: {record['executed_at']}")

    if status.get("tables_status"):
        print("\n表状态:")
        for table, table_status in status["tables_status"].items():
            icon = "✅" if table_status["is_migrated"] else "❌"
            print(f"  {icon} {table}")
            if table_status["missing_columns"]:
                print(f"    缺失字段: {', '.join(table_status['missing_columns'])}")

    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="MaiBot 多租户隔离迁移工具")
    parser.add_argument("--check", action="store_true", help="检查迁移状态")
    parser.add_argument("--migrate", action="store_true", help="执行迁移")
    parser.add_argument("--force", action="store_true", help="强制执行迁移（跳过安全检查）")

    args = parser.parse_args()

    if args.check:
        print("🔍 检查迁移状态...")
        status = check_migration_status()
        print_status(status)
        return

    if args.migrate or args.force:
        print("🚀 开始执行多租户迁移...")

        if args.force:
            print("⚠️ 强制模式：跳过安全检查")

        success = execute_multi_tenant_migration(force=args.force)

        if success:
            print("🎉 迁移成功完成！")

            # 再次检查状态
            print("\n📊 迁移后状态检查...")
            status = check_migration_status()
            print_status(status)

            print("\n✅ 多租户隔离架构已成功部署！")
            print("📝 下一步请参考 refactor.md 继续其他模块的改造")
        else:
            print("❌ 迁移失败，请查看日志了解详细信息")
            sys.exit(1)
        return

    # 默认显示帮助
    parser.print_help()


if __name__ == "__main__":
    main()
