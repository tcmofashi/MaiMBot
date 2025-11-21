
-- 数据库迁移脚本：修复租户模式问题

-- 1. 为 chat_streams 表添加 tenant_id 默认值
UPDATE chat_streams 
SET tenant_id = 'default' 
WHERE tenant_id IS NULL;

-- 2. 为 messages 表添加租户相关字段（如果需要）
-- ALTER TABLE messages ADD COLUMN tenant_id VARCHAR(50) DEFAULT 'default';
-- ALTER TABLE messages ADD COLUMN chat_stream_id VARCHAR(50);

-- 3. 创建索引以提高查询性能
-- CREATE INDEX idx_chat_streams_tenant ON chat_streams(tenant_id);
-- CREATE INDEX idx_messages_tenant ON messages(tenant_id);

-- 4. 验证数据完整性
SELECT COUNT(*) as null_tenant_streams FROM chat_streams WHERE tenant_id IS NULL;
-- SELECT COUNT(*) as null_tenant_messages FROM messages WHERE tenant_id IS NULL;
