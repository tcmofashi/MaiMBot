#!/usr/bin/env python3
"""
MaiMBot 数据库结构分析

创建时间: 2025-11-27 23:24:00
最后修改: 2025-11-27 23:24:00
AI生成标识: Cline
测试类型: 数据库结构分析
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import Dict, List, Any


class DatabaseAnalyzer:
    """数据库结构分析器"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.connection = None
        self.cursor = None

    def connect(self):
        """连接到数据库"""
        try:
            self.connection = sqlite3.connect(self.db_path)
            self.cursor = self.connection.cursor()
            print(f"成功连接到数据库: {self.db_path}")
        except Exception as e:
            print(f"连接数据库失败: {e}")
            raise

    def disconnect(self):
        """断开数据库连接"""
        if self.connection:
            self.connection.close()
            print("数据库连接已关闭")

    def get_table_list(self) -> List[str]:
        """获取所有表名"""
        self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in self.cursor.fetchall()]
        return tables

    def get_table_schema(self, table_name: str) -> str:
        """获取表的完整SQL定义"""
        self.cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table_name}';")
        result = self.cursor.fetchone()
        return result[0] if result else ""

    def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """获取表的列信息"""
        self.cursor.execute(f"PRAGMA table_info({table_name});")
        columns = []
        for row in self.cursor.fetchall():
            columns.append(
                {
                    "cid": row[0],
                    "name": row[1],
                    "type": row[2],
                    "notnull": bool(row[3]),
                    "default_value": row[4],
                    "pk": bool(row[5]),
                }
            )
        return columns

    def get_foreign_keys(self, table_name: str) -> List[Dict[str, Any]]:
        """获取表的外键信息"""
        self.cursor.execute(f"PRAGMA foreign_key_list({table_name});")
        foreign_keys = []
        for row in self.cursor.fetchall():
            foreign_keys.append(
                {
                    "id": row[0],
                    "seq": row[1],
                    "table": row[2],
                    "from": row[3],
                    "to": row[4],
                    "on_update": row[5],
                    "on_delete": row[6],
                    "match": row[7],
                }
            )
        return foreign_keys

    def get_indexes(self, table_name: str) -> List[Dict[str, Any]]:
        """获取表的索引信息"""
        self.cursor.execute(f"PRAGMA index_list({table_name});")
        indexes = []
        for row in self.cursor.fetchall():
            index_info = {
                "seq": row[0],
                "name": row[1],
                "unique": bool(row[2]),
                "origin": row[3],
                "partial": bool(row[4]),
            }

            # 获取索引列信息
            self.cursor.execute(f"PRAGMA index_info({index_info['name']});")
            index_columns = []
            for col_row in self.cursor.fetchall():
                index_columns.append({"seqno": col_row[0], "cid": col_row[1], "name": col_row[2]})
            index_info["columns"] = index_columns
            indexes.append(index_info)

        return indexes

    def analyze_database(self) -> Dict[str, Any]:
        """完整分析数据库结构"""
        print("开始分析数据库结构...")

        tables = self.get_table_list()
        print(f"发现 {len(tables)} 个表: {tables}")

        database_info = {
            "database_name": os.path.basename(self.db_path),
            "analysis_time": datetime.now().isoformat(),
            "tables": {},
        }

        for table_name in tables:
            print(f"分析表: {table_name}")

            table_info = {
                "schema": self.get_table_schema(table_name),
                "columns": self.get_table_info(table_name),
                "foreign_keys": self.get_foreign_keys(table_name),
                "indexes": self.get_indexes(table_name),
            }

            # 识别主键
            primary_keys = [col["name"] for col in table_info["columns"] if col["pk"]]
            table_info["primary_keys"] = primary_keys

            # 识别唯一约束
            unique_constraints = []
            for index in table_info["indexes"]:
                if index["unique"] and not index["name"].startswith("sqlite_"):
                    unique_constraints.append(
                        {"name": index["name"], "columns": [col["name"] for col in index["columns"]]}
                    )
            table_info["unique_constraints"] = unique_constraints

            database_info["tables"][table_name] = table_info

        return database_info

    def generate_report(self, database_info: Dict[str, Any]) -> str:
        """生成详细的数据库结构报告"""
        report = []
        report.append("# MaiMBot 数据库结构分析报告")
        report.append(f"**创建时间**: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}  ")
        report.append(f"**数据库文件**: {database_info['database_name']}  ")
        report.append(f"**分析时间**: {database_info['analysis_time']}  ")
        report.append("**AI生成标识**: Cline  ")
        report.append("**文档类型**: 数据库结构分析报告")
        report.append("")

        report.append("## 概述")
        report.append(f"本报告详细分析了 MaiMBot 项目中的数据库结构，共发现 {len(database_info['tables'])} 个数据表。")
        report.append("")

        report.append("## 数据库表列表")
        for table_name in database_info["tables"].keys():
            report.append(f"- `{table_name}`")
        report.append("")

        report.append("## 详细表结构分析")

        for table_name, table_info in database_info["tables"].items():
            report.append(f"### 表: `{table_name}`")
            report.append("")

            # 表定义
            report.append("#### 表定义")
            report.append("```sql")
            report.append(table_info["schema"])
            report.append("```")
            report.append("")

            # 列信息
            report.append("#### 列信息")
            report.append("| 列名 | 数据类型 | 是否主键 | 是否非空 | 默认值 |")
            report.append("|------|----------|----------|----------|--------|")
            for column in table_info["columns"]:
                pk_mark = "✅" if column["pk"] else ""
                notnull_mark = "✅" if column["notnull"] else ""
                default_value = column["default_value"] if column["default_value"] is not None else "NULL"
                report.append(
                    f"| `{column['name']}` | `{column['type']}` | {pk_mark} | {notnull_mark} | `{default_value}` |"
                )
            report.append("")

            # 主键
            if table_info["primary_keys"]:
                report.append("#### 主键")
                report.append(f"- {', '.join([f'`{pk}`' for pk in table_info['primary_keys']])}")
                report.append("")

            # 外键
            if table_info["foreign_keys"]:
                report.append("#### 外键约束")
                for fk in table_info["foreign_keys"]:
                    report.append(f"- `{fk['from']}` → `{fk['table']}.{fk['to']}`")
                    if fk["on_update"] or fk["on_delete"]:
                        actions = []
                        if fk["on_update"]:
                            actions.append(f"ON UPDATE {fk['on_update']}")
                        if fk["on_delete"]:
                            actions.append(f"ON DELETE {fk['on_delete']}")
                        report.append(f"  - 引用操作: {' '.join(actions)}")
                report.append("")

            # 唯一约束
            if table_info["unique_constraints"]:
                report.append("#### 唯一约束")
                for constraint in table_info["unique_constraints"]:
                    columns_str = ", ".join([f"`{col}`" for col in constraint["columns"]])
                    report.append(f"- `{constraint['name']}`: {columns_str}")
                report.append("")

            # 索引
            if table_info["indexes"]:
                non_system_indexes = [idx for idx in table_info["indexes"] if not idx["name"].startswith("sqlite_")]
                if non_system_indexes:
                    report.append("#### 索引")
                    for index in non_system_indexes:
                        index_type = "唯一索引" if index["unique"] else "普通索引"
                        columns_str = ", ".join([f"`{col['name']}`" for col in index["columns"]])
                        report.append(f"- `{index['name']}` ({index_type}): {columns_str}")
                    report.append("")

            report.append("---")
            report.append("")

        return "\n".join(report)


def main():
    """主函数"""
    db_path = "data/MaiBot.db"

    if not os.path.exists(db_path):
        print(f"数据库文件不存在: {db_path}")
        return

    analyzer = DatabaseAnalyzer(db_path)

    try:
        analyzer.connect()
        database_info = analyzer.analyze_database()

        # 生成报告
        report = analyzer.generate_report(database_info)

        # 保存报告
        report_dir = "MaiM_api_sever_test/test_data/database_tests"
        os.makedirs(report_dir, exist_ok=True)

        report_filename = f"database_structure_analysis_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        report_path = os.path.join(report_dir, report_filename)

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)

        print(f"数据库结构分析报告已保存到: {report_path}")

        # 同时保存JSON格式的详细数据
        json_filename = f"database_structure_details_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        json_path = os.path.join(report_dir, json_filename)

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(database_info, f, indent=2, ensure_ascii=False)

        print(f"详细数据库结构数据已保存到: {json_path}")

        # 在控制台输出简要信息
        print("\n" + "=" * 50)
        print("数据库结构分析摘要:")
        print("=" * 50)
        for table_name, table_info in database_info["tables"].items():
            print(f"\n表: {table_name}")
            print(f"  列数: {len(table_info['columns'])}")
            print(f"  主键: {table_info['primary_keys']}")
            print(f"  外键: {len(table_info['foreign_keys'])}")
            print(f"  索引: {len([idx for idx in table_info['indexes'] if not idx['name'].startswith('sqlite_')])}")

    except Exception as e:
        print(f"分析过程中出现错误: {e}")
    finally:
        analyzer.disconnect()


if __name__ == "__main__":
    main()
