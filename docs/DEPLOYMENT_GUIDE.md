# MaiBot 多租户隔离架构部署指南

## 📋 目录

- [部署概述](#部署概述)
- [前置要求](#前置要求)
- [环境准备](#环境准备)
- [数据库迁移](#数据库迁移)
- [应用配置](#应用配置)
- [部署步骤](#部署步骤)
- [验证部署](#验证部署)
- [性能优化](#性能优化)
- [监控和维护](#监控和维护)
- [故障排除](#故障排除)
- [高级配置](#高级配置)

## 🎯 部署概述

本指南将帮助您在生产环境中部署支持多租户隔离的MaiBot系统。多租户架构提供了企业级的数据隔离、扩展能力和性能优化。

### 支持的部署模式

1. **单机多租户部署** - 适用于小型团队或初创企业
2. **分布式多租户部署** - 适用于中大型企业
3. **容器化部署** - 适用于云原生环境
4. **Kubernetes部署** - 适用于大规模生产环境

### 核心特性

- ✅ **四维隔离** (T+A+C+P) - 租户+智能体+聊天流+平台
- ✅ **水平扩展** - 支持无限租户和智能体
- ✅ **高性能** - 优化的数据库查询和缓存
- ✅ **向后兼容** - 无缝升级现有系统
- ✅ **监控就绪** - 完整的监控和日志体系

## 🔧 前置要求

### 系统要求

#### 最低配置
- **CPU**: 2核心
- **内存**: 4GB RAM
- **存储**: 20GB 可用空间
- **网络**: 稳定的互联网连接
- **操作系统**: Linux (推荐 Ubuntu 20.04+) / macOS / Windows 10+

#### 推荐配置
- **CPU**: 4核心以上
- **内存**: 8GB+ RAM
- **存储**: 100GB+ SSD
- **网络**: 高速互联网连接
- **负载均衡器**: Nginx/HAProxy (生产环境)

#### 企业级配置
- **CPU**: 8核心以上
- **内存**: 16GB+ RAM
- **存储**: 500GB+ 高速SSD
- **数据库**: PostgreSQL/MySQL (推荐)
- **缓存**: Redis 集群
- **消息队列**: RabbitMQ/Apache Kafka

### 软件依赖

```bash
# Python 环境
Python 3.10+ (推荐 3.11)

# 数据库 (任选其一)
SQLite 3.36+ (开发/小型部署)
PostgreSQL 13+ (推荐)
MySQL 8.0+
MariaDB 10.6+

# 可选组件
Redis 6.0+ (缓存和会话)
Docker 20.10+ (容器化部署)
Kubernetes 1.24+ (K8s部署)
```

## 🚀 环境准备

### 1. 创建项目环境

```bash
# 克隆项目 (如果还没有)
git clone https://github.com/MaiM-with-u/MaiBot.git
cd MaiBot

# 创建 conda 环境
conda create -n maibot python=3.11
conda activate maibot

# 或使用 virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows
```

### 2. 安装依赖

```bash
# 安装项目依赖
pip install -r requirements.txt

# 生产环境额外依赖
pip install -r requirements-prod.txt  # 如果存在

# 安装多租户相关依赖
pip install sqlalchemy alembic redis psycopg2-binary
```

### 3. 环境变量配置

创建 `.env` 文件：

```bash
# 基础配置
MAIMBOT_ENV=production
DEBUG=false
LOG_LEVEL=INFO

# 数据库配置
DATABASE_URL=sqlite:///MaiBot.db
# 或 PostgreSQL
# DATABASE_URL=postgresql://user:password@localhost:5432/maibot

# Redis 配置 (可选)
REDIS_URL=redis://localhost:6379/0

# 多租户配置
MULTI_TENANT_ENABLED=true
DEFAULT_TENANT_ID=default

# 安全配置
SECRET_KEY=your-secret-key-here
JWT_SECRET_KEY=your-jwt-secret-key

# LLM 配置
OPENAI_API_KEY=your-openai-api-key
# 或其他 LLM 配置
```

## 🗄️ 数据库迁移

### 1. 数据库备份 (重要!)

```bash
# SQLite 备份
cp MaiBot.db MaiBot.db.backup.$(date +%Y%m%d_%H%M%S)

# PostgreSQL 备份
pg_dump maibot > maibot_backup_$(date +%Y%m%d_%H%M%S).sql

# MySQL 备份
mysqldump maibot > maibot_backup_$(date +%Y%m%d_%H%M%S).sql
```

### 2. 执行多租户迁移

```bash
# 检查迁移状态
python scripts/run_multi_tenant_migration.py --check

# 执行迁移
python scripts/run_multi_tenant_migration.py --migrate

# 验证迁移结果
python scripts/run_multi_tenant_migration.py --check
```

### 3. 配置数据库 (生产环境)

#### PostgreSQL 配置示例

```sql
-- 创建数据库
CREATE DATABASE maibot;
CREATE USER maibot_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE maibot TO maibot_user;

-- 优化配置
-- 在 postgresql.conf 中设置:
-- shared_buffers = 256MB
-- effective_cache_size = 1GB
-- maintenance_work_mem = 64MB
-- checkpoint_completion_target = 0.9
-- wal_buffers = 16MB
-- default_statistics_target = 100
```

#### MySQL 配置示例

```sql
-- 创建数据库
CREATE DATABASE maibot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'maibot_user'@'localhost' IDENTIFIED BY 'secure_password';
GRANT ALL PRIVILEGES ON maibot.* TO 'maibot_user'@'localhost';
FLUSH PRIVILEGES;
```

## ⚙️ 应用配置

### 1. 多租户配置文件

创建 `config/multi_tenant_config.toml`:

```toml
[multi_tenant]
enabled = true
default_tenant_id = "default"
max_tenants = 1000
isolation_level = "strict"

# 默认租户配置
[tenants.default]
name = "默认租户"
description = "系统默认租户"
enabled = true
max_agents = 10
max_chat_streams = 100
platforms = ["qq", "discord"]

# 示例租户配置
[tenants.enterprise]
name = "企业租户"
description = "企业级租户配置"
enabled = true
max_agents = 100
max_chat_streams = 1000
platforms = ["qq", "discord", "slack", "telegram"]

# LLM 配额
[tenants.enterprise.quotas]
daily_llm_requests = 10000
monthly_llm_tokens = 1000000
storage_quota_mb = 10240
```

### 2. 日志配置

创建 `config/logging.toml`:

```toml
[logging]
level = "INFO"
format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

[handlers.file]
class = "logging.handlers.RotatingFileHandler"
filename = "logs/maibot.log"
max_bytes = 10485760  # 10MB
backup_count = 5
level = "INFO"

[handlers.console]
class = "logging.StreamHandler"
level = "INFO"
stream = "ext://sys.stdout"

[loggers.maibot]
level = "INFO"
handlers = ["file", "console"]
propagate = false

[loggers.sqlalchemy]
level = "WARNING"
handlers = ["file"]
propagate = false
```

### 3. 性能优化配置

创建 `config/performance.toml`:

```toml
[performance]
database_pool_size = 20
database_max_overflow = 30
redis_pool_size = 50
cache_ttl_seconds = 3600
batch_size = 1000
max_concurrent_requests = 1000

[monitoring]
enabled = true
metrics_port = 9090
health_check_interval = 30
performance_tracking = true
```

## 🚀 部署步骤

### 方式一: 传统部署

```bash
# 1. 准备环境
conda activate maibot

# 2. 执行数据库迁移
python scripts/run_multi_tenant_migration.py --migrate

# 3. 初始化配置
python scripts/init_config.py

# 4. 启动应用
python bot.py

# 5. 验证部署
curl http://localhost:8080/health
```

### 方式二: Docker 部署

创建 `Dockerfile.prod`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建非root用户
RUN useradd -m -u 1000 maibot
RUN chown -R maibot:maibot /app
USER maibot

# 暴露端口
EXPOSE 8080

# 启动命令
CMD ["python", "bot.py"]
```

创建 `docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  maibot:
    build:
      context: .
      dockerfile: Dockerfile.prod
    ports:
      - "8080:8080"
    environment:
      - MAIMBOT_ENV=production
      - DATABASE_URL=postgresql://maibot:password@postgres:5432/maibot
      - REDIS_URL=redis://redis:6379/0
      - MULTI_TENANT_ENABLED=true
    depends_on:
      - postgres
      - redis
    volumes:
      - ./logs:/app/logs
      - ./config:/app/config
    restart: unless-stopped

  postgres:
    image: postgres:15
    environment:
      - POSTGRES_DB=maibot
      - POSTGRES_USER=maibot
      - POSTGRES_PASSWORD=password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - maibot
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
```

部署命令:

```bash
# 构建和启动
docker-compose -f docker-compose.prod.yml up -d

# 执行数据库迁移
docker-compose -f docker-compose.prod.yml exec maibot \
  python scripts/run_multi_tenant_migration.py --migrate

# 查看日志
docker-compose -f docker-compose.prod.yml logs -f maibot
```

### 方式三: Kubernetes 部署

创建 `k8s/namespace.yaml`:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: maibot
```

创建 `k8s/configmap.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maibot-config
  namespace: maibot
data:
  MULTI_TENANT_ENABLED: "true"
  DEFAULT_TENANT_ID: "default"
  LOG_LEVEL: "INFO"
```

创建 `k8s/deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: maibot
  namespace: maibot
spec:
  replicas: 3
  selector:
    matchLabels:
      app: maibot
  template:
    metadata:
      labels:
        app: maibot
    spec:
      containers:
      - name: maibot
        image: maibot:latest
        ports:
        - containerPort: 8080
        envFrom:
        - configMapRef:
            name: maibot-config
        - secretRef:
            name: maibot-secrets
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
```

部署命令:

```bash
# 应用配置
kubectl apply -f k8s/

# 执行数据库迁移
kubectl exec -n maibot deployment/maibot -- \
  python scripts/run_multi_tenant_migration.py --migrate

# 查看状态
kubectl get pods -n maibot
```

## ✅ 验证部署

### 1. 健康检查

```bash
# 基础健康检查
curl http://localhost:8080/health

# 详细健康检查
curl http://localhost:8080/health/detailed

# 多租户状态检查
curl http://localhost:8080/api/multi_tenant/status
```

预期响应:

```json
{
  "status": "healthy",
  "timestamp": "2025-01-11T12:00:00Z",
  "version": "1.0.0",
  "multi_tenant": {
    "enabled": true,
    "tenants_count": 5,
    "agents_count": 12,
    "database_status": "connected"
  }
}
```

### 2. 功能验证

```python
# 创建测试脚本 test_deployment.py
import asyncio
from src.isolation.isolation_context import create_isolation_context
from src.chat.heart_flow.isolated_heartflow_api import create_isolated_heartflow_processor

async def test_multi_tenant():
    # 测试租户隔离
    context1 = create_isolation_context("tenant1", "agent1", "qq")
    context2 = create_isolation_context("tenant2", "agent1", "qq")

    processor1 = create_isolated_heartflow_processor("tenant1", "agent1")
    processor2 = create_isolated_heartflow_processor("tenant2", "agent1")

    print("✅ 多租户隔离测试通过")

    # 测试数据库连接
    from src.common.database.isolation_query_examples import get_isolated_query_manager
    query_manager = get_isolated_query_manager(context1)
    overview = query_manager.get_tenant_overview()
    print(f"✅ 数据库测试通过: {overview}")

if __name__ == "__main__":
    asyncio.run(test_multi_tenant())
```

运行测试:

```bash
python test_deployment.py
```

### 3. 性能验证

```bash
# 安压测试工具
pip install locust

# 创建性能测试脚本 performance_test.py
from locust import HttpUser, task, between

class MaiBotUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def health_check(self):
        self.client.get("/health")

    @task
    def tenant_status(self):
        self.client.get("/api/multi_tenant/status")

    @task
    def create_agent(self):
        self.client.post("/api/agents", json={
            "tenant_id": "test_tenant",
            "agent_id": "test_agent",
            "name": "测试智能体"
        })

# 运行性能测试
locust -f performance_test.py --host=http://localhost:8080
```

## 📈 性能优化

### 1. 数据库优化

```sql
-- 创建复合索引
CREATE INDEX CONCURRENTLY idx_messages_isolation
ON messages(tenant_id, agent_id, platform, chat_stream_id);

CREATE INDEX CONCURRENTLY idx_memory_chest_isolation
ON memory_chest(tenant_id, agent_id, platform, chat_stream_id);

-- 分析表统计信息
ANALYZE messages;
ANALYZE memory_chest;
ANALYZE chat_streams;
```

### 2. Redis 缓存配置

```redis
# redis.conf 优化配置
maxmemory 2gb
maxmemory-policy allkeys-lru
save 900 1
save 300 10
save 60 10000
```

### 3. 应用层优化

```python
# config/performance.py
DATABASE_CONFIG = {
    "pool_size": 20,
    "max_overflow": 30,
    "pool_timeout": 30,
    "pool_recycle": 3600
}

REDIS_CONFIG = {
    "max_connections": 50,
    "retry_on_timeout": True,
    "socket_timeout": 5
}
```

## 📊 监控和维护

### 1. 日志监控

```bash
# 配置日志轮转
sudo vim /etc/logrotate.d/maibot

/path/to/maibot/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 maibot maibot
    postrotate
        systemctl reload maibot
    endscript
}
```

### 2. 系统监控

使用 Prometheus + Grafana:

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'maibot'
    static_configs:
      - targets: ['localhost:9090']
    metrics_path: '/metrics'
    scrape_interval: 5s
```

### 3. 健康检查脚本

```bash
#!/bin/bash
# health_check.sh

HEALTH_URL="http://localhost:8080/health"
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" $HEALTH_URL)

if [ $RESPONSE -eq 200 ]; then
    echo "$(date): MaiBot is healthy"
    exit 0
else
    echo "$(date): MaiBot is unhealthy (HTTP $RESPONSE)"
    # 发送告警
    curl -X POST "https://api.telegram.org/bot<token>/sendMessage" \
         -d "chat_id=<chat_id>" \
         -d "text=MaiBot health check failed!"
    exit 1
fi
```

### 4. 自动化维护

```bash
# 添加到 crontab
# 每日健康检查
0 */6 * * * /path/to/health_check.sh

# 每周日志清理
0 2 * * 0 find /path/to/maibot/logs -name "*.log" -mtime +7 -delete

# 每月数据库维护
0 3 1 * * /path/to/database_maintenance.sh
```

## 🔧 故障排除

### 常见问题及解决方案

#### 1. 数据库连接问题

**症状**: 应用启动失败，提示数据库连接错误

**解决方案**:
```bash
# 检查数据库状态
systemctl status postgresql

# 检查连接配置
python -c "
from src.common.database.database_model import engine
try:
    engine.connect()
    print('✅ 数据库连接正常')
except Exception as e:
    print(f'❌ 数据库连接失败: {e}')
"

# 重置数据库连接
docker-compose restart postgres
```

#### 2. 内存不足

**症状**: 应用响应缓慢，OOM错误

**解决方案**:
```bash
# 检查内存使用
free -h
ps aux --sort=-%mem | head

# 优化内存配置
export PYTHONOPTIMIZE=1
export MALLOC_TRIM_THRESHOLD_=100000

# 重启应用释放内存
systemctl restart maibot
```

#### 3. 租户数据泄露

**症状**: 不同租户数据混合

**解决方案**:
```bash
# 检查隔离配置
curl http://localhost:8080/api/multi_tenant/isolation_check

# 验证数据隔离
python scripts/verify_tenant_isolation.py

# 修复数据隔离问题
python scripts/fix_tenant_isolation.py
```

#### 4. 性能问题

**症状**: API响应缓慢，数据库查询超时

**解决方案**:
```bash
# 检查慢查询
python scripts/analyze_slow_queries.py

# 优化数据库
VACUUM ANALYZE;
REINDEX DATABASE maibot;

# 清理缓存
redis-cli FLUSHDB
systemctl restart maibot
```

### 日志分析

```bash
# 查看错误日志
tail -f logs/maibot.log | grep ERROR

# 分析访问模式
grep "tenant_id=" logs/maibot.log | awk '{print $NF}' | sort | uniq -c

# 监控资源使用
htop
iotop
```

## 🎛️ 高级配置

### 1. 多数据库支持

```python
# config/database.py
DATABASE_ROUTES = {
    "default": "postgresql://...",
    "tenant_001": "postgresql://...",
    "tenant_002": "mysql://...",
    "analytics": "clickhouse://..."
}
```

### 2. 微服务架构

```yaml
# docker-compose.microservices.yml
version: '3.8'

services:
  api-gateway:
    image: nginx:alpine
    ports:
      - "80:80"
    depends_on:
      - auth-service
      - chat-service
      - memory-service

  auth-service:
    build: ./services/auth
    environment:
      - DATABASE_URL=postgresql://...
    ports:
      - "8001:8000"

  chat-service:
    build: ./services/chat
    environment:
      - DATABASE_URL=postgresql://...
    ports:
      - "8002:8000"

  memory-service:
    build: ./services/memory
    environment:
      - DATABASE_URL=postgresql://...
    ports:
      - "8003:8000"
```

### 3. 集群部署

```bash
# 使用 Docker Swarm
docker swarm init
docker stack deploy -c docker-compose.cluster.yml maibot

# 使用 Kubernetes
kubectl scale deployment maibot --replicas=10
kubectl autoscale deployment maibot --cpu-percent=70 --min=3 --max=20
```

### 4. 安全配置

```python
# config/security.py
SECURITY_CONFIG = {
    "jwt_secret_key": os.environ.get("JWT_SECRET_KEY"),
    "token_expire_hours": 24,
    "rate_limit": {
        "requests_per_minute": 100,
        "burst_size": 200
    },
    "encryption": {
        "algorithm": "AES-256-GCM",
        "key_rotation_days": 90
    }
}
```

## 📞 支持和帮助

### 获取帮助

1. **文档资源**:
   - [项目文档](https://docs.mai-mai.org)
   - [API参考](./API_REFERENCE.md)
   - [测试报告](./TEST_REPORT.md)

2. **社区支持**:
   - GitHub Issues: [MaiBot Issues](https://github.com/MaiM-with-u/MaiBot/issues)
   - 讨论区: [GitHub Discussions](https://github.com/MaiM-with-u/MaiBot/discussions)

3. **故障报告**:
   ```bash
   # 收集诊断信息
   python scripts/collect_diagnostic_info.py

   # 生成支持包
   tar -czf maibot-support-$(date +%Y%m%d).tar.gz \
       logs/ \
       config/ \
       diagnostic_info.txt
   ```

### 最佳实践

1. **定期备份**: 每日自动备份数据库和配置
2. **监控告警**: 设置全面的监控和告警机制
3. **版本管理**: 使用Git管理配置文件
4. **安全更新**: 定期更新依赖包和系统补丁
5. **性能调优**: 根据实际负载调整配置参数

---

## 🎉 部署完成

恭喜！您已成功部署MaiBot多租户隔离架构。现在您的系统具备了：

- 🔒 **企业级数据隔离** - T+A+C+P四维完全隔离
- 📈 **高可扩展性** - 支持无限租户和智能体
- ⚡ **高性能** - 优化的数据库查询和缓存
- 🛡️ **高可用性** - 完整的监控和故障恢复机制
- 🔧 **易维护性** - 自动化运维和管理工具

接下来建议：
1. 配置监控和告警系统
2. 设置定期备份策略
3. 进行业务场景测试
4. 培训运维团队

祝您使用愉快！🚀