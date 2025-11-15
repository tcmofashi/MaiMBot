-- 记忆服务数据库初始化脚本

-- 启用向量扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_memories_tenant_agent ON memories(tenant_id, agent_id);
CREATE INDEX IF NOT EXISTS idx_memories_embedding_gin ON memories USING gin(embedding);
CREATE INDEX IF NOT EXISTS idx_conflicts_tenant_agent ON conflicts(tenant_id, agent_id);

-- 创建用户权限
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO memory_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO memory_user;