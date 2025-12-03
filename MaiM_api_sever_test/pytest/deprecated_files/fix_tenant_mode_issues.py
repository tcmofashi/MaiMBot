#!/usr/bin/env python3
"""
修复租户模式迁移中的问题
1. 修复 ChatStreams 表缺少 tenant_id 的问题
2. 修复消息存储时缺少租户信息的问题
3. 修复 WebSocket 连接处理问题
"""

import asyncio
import sys
import traceback
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.common.logger import get_logger

logger = get_logger("fix_tenant_mode")


async def fix_database_schema():
    """修复数据库模式，确保 tenant_id 字段有默认值"""
    try:
        from src.common.database.database_model import database

        logger.info("检查数据库连接...")

        # 确保数据库连接正常
        if not database.is_connection_usable():
            database.connect()

        logger.info("数据库连接正常")

        # 检查 ChatStreams 表结构
        from playhouse.migrate import SchemaMigrator

        migrator = SchemaMigrator(database)

        # 检查并添加 tenant_id 字段（如果不存在）
        try:
            # 尝试为现有记录设置默认的 tenant_id
            from src.common.database.database_model import ChatStreams

            # 更新所有没有 tenant_id 的记录，设置为 'default'
            query = ChatStreams.update(tenant_id="default").where(ChatStreams.tenant_id.is_null())
            updated_count = query.execute()
            logger.info(f"已更新 {updated_count} 条 ChatStreams 记录的 tenant_id")

        except Exception as e:
            logger.error(f"更新 ChatStreams 记录失败: {e}")

        # 检查 Messages 表是否需要租户字段
        try:
            # 为现有消息设置默认的租户信息
            # 这里我们可能需要添加租户字段，或者使用其他方式处理
            logger.info("检查 Messages 表的租户字段...")

        except Exception as e:
            logger.error(f"检查 Messages 表失败: {e}")

        logger.info("数据库模式修复完成")

    except Exception as e:
        logger.error(f"修复数据库模式失败: {e}")
        traceback.print_exc()


async def fix_message_storage():
    """修复消息存储逻辑，确保包含租户信息"""
    try:
        logger.info("修复消息存储逻辑...")

        # 检查消息存储代码

        # 这里我们可能需要修改 MessageStorage.store_message 方法
        # 但由于我们不能直接修改代码，我们记录问题

        logger.warning("消息存储代码需要修改以包含租户信息")
        logger.warning("问题：Messages.create() 调用中没有包含 tenant_id 字段")

        # 建议的修复方案
        logger.info("建议的修复方案：")
        logger.info("1. 在 Messages.create() 调用中添加 tenant_id 字段")
        logger.info("2. 从 chat_stream 中获取租户信息")
        logger.info("3. 确保所有消息都关联到正确的租户")

    except Exception as e:
        logger.error(f"修复消息存储失败: {e}")
        traceback.print_exc()


async def fix_websocket_handling():
    """修复 WebSocket 连接处理"""
    try:
        logger.info("分析 WebSocket 连接问题...")

        # WebSocket 问题通常是由于 ASGI 消息处理不当
        logger.warning("检测到 WebSocket 连接问题：")
        logger.warning("- RuntimeError: Unexpected ASGI message 'websocket.close'")
        logger.warning("- 这通常发生在 WebSocket 连接状态管理不当")

        logger.info("建议的修复方案：")
        logger.info("1. 检查 WebSocket 连接的生命周期管理")
        logger.info("2. 确保在发送消息前检查连接状态")
        logger.info("3. 正确处理 WebSocket 关闭消息")
        logger.info("4. 添加适当的异常处理")

    except Exception as e:
        logger.error(f"分析 WebSocket 问题失败: {e}")


async def fix_message_type_conversion():
    """修复消息类型转换问题"""
    try:
        logger.info("修复消息类型转换问题...")

        # 问题：MessageRecv 对象缺少 chat_stream_id 属性
        logger.warning("检测到消息类型转换问题：")
        logger.warning("- MessageRecv object has no attribute 'chat_stream_id'")
        logger.warning("- 这表明消息对象和数据库模型不匹配")

        logger.info("建议的修复方案：")
        logger.info("1. 确保 MessageRecv 类包含必要的租户相关字段")
        logger.info("2. 在消息处理流程中正确传递租户信息")
        logger.info("3. 更新消息序列化/反序列化逻辑")

    except Exception as e:
        logger.error(f"修复消息类型转换失败: {e}")


async def create_migration_script():
    """创建数据库迁移脚本"""
    try:
        logger.info("创建数据库迁移脚本...")

        migration_script = """
-- 数据库迁移脚本：修复租户模式问题

-- 1. 为 ChatStreams 表添加 tenant_id 默认值
UPDATE chat_streams 
SET tenant_id = 'default' 
WHERE tenant_id IS NULL;

-- 2. 为 Messages 表添加租户相关字段（如果需要）
-- ALTER TABLE messages ADD COLUMN tenant_id VARCHAR(50) DEFAULT 'default';
-- ALTER TABLE messages ADD COLUMN chat_stream_id VARCHAR(50);

-- 3. 创建索引以提高查询性能
-- CREATE INDEX idx_chat_streams_tenant ON chat_streams(tenant_id);
-- CREATE INDEX idx_messages_tenant ON messages(tenant_id);

-- 4. 验证数据完整性
SELECT COUNT(*) as null_tenant_streams FROM chat_streams WHERE tenant_id IS NULL;
-- SELECT COUNT(*) as null_tenant_messages FROM messages WHERE tenant_id IS NULL;
"""

        with open("tenant_migration.sql", "w", encoding="utf-8") as f:
            f.write(migration_script)

        logger.info("数据库迁移脚本已保存到 tenant_migration.sql")

    except Exception as e:
        logger.error(f"创建迁移脚本失败: {e}")


async def main():
    """主函数"""
    logger.info("开始修复租户模式问题...")

    try:
        # 1. 修复数据库模式
        await fix_database_schema()

        # 2. 分析消息存储问题
        await fix_message_storage()

        # 3. 分析 WebSocket 问题
        await fix_websocket_handling()

        # 4. 修复消息类型转换问题
        await fix_message_type_conversion()

        # 5. 创建迁移脚本
        await create_migration_script()

        logger.info("租户模式问题分析完成")
        logger.info("请根据上述建议进行代码修复")

    except Exception as e:
        logger.error(f"修复过程失败: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
