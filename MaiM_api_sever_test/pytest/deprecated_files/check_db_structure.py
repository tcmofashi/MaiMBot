#!/usr/bin/env python3
"""
检查数据库结构的脚本
"""

import sqlite3
import os


def check_database(db_path):
    """检查指定数据库的表结构"""
    if not os.path.exists(db_path):
        print(f"数据库文件不存在: {db_path}")
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 获取所有表名
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()

        print(f"数据库: {db_path}")
        print(f"表数量: {len(tables)}")
        print("表列表:")

        for table in tables:
            table_name = table[0]
            print(f"  - {table_name}")

            # 检查是否包含租户相关字段
            if "stream" in table_name.lower() or "message" in table_name.lower():
                cursor.execute(f"PRAGMA table_info({table_name});")
                columns = cursor.fetchall()
                print("    列:")
                for col in columns:
                    col_name = col[1]
                    print(f"      - {col_name} ({col[2]})")

                    # 检查是否有租户相关字段
                    if "tenant" in col_name.lower():
                        print(f"        *** 发现租户相关字段: {col_name} ***")

        conn.close()
        print()

    except Exception as e:
        print(f"检查数据库时发生错误: {e}")


def main():
    """主函数"""
    print("=== 数据库结构检查 ===\n")

    # 检查所有数据库文件
    db_files = ["./data.db", "./config/bot.db", "./data/MaiBot.db", "../l2d_backend/data/l2d_backend.db"]

    for db_file in db_files:
        check_database(db_file)


if __name__ == "__main__":
    main()
