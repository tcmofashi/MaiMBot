# MaiBot 多租户迁移指南

## 概述

本文档提供了从单租户架构到多租户隔离架构的完整迁移指南。MaiBot的多租户架构基于四维隔离体系：租户(T) + 智能体(A) + 聊天流(C) + 平台(P)。

**迁移目标：**
- 实现不同租户间的数据完全隔离
- 支持同一租户下多个智能体的独立配置和记忆
- 基于聊天上下文和平台的细粒度隔离
- 保持向后兼容性，确保平滑迁移

**迁移原则：**
- 最小停机时间
- 数据完整性保证
- 向后兼容性
- 可回滚性

## 迁移架构概览

### 四维隔离体系

1. **租户隔离(T)** - 不同租户间的数据完全隔离
2. **智能体隔离(A)** - 同一租户不同智能体的配置、记忆隔离
3. **聊天流隔离(C)** - 基于sender和receiver区分的不同聊天上下文隔离
4. **平台隔离(P)** - 区分QQ、Discord等不同通信平台的隔离

### 迁移组件

迁移过程包含以下主要组件：

1. **数据迁移策略** - 数据库结构和数据的迁移
2. **代码迁移工具** - 代码自动迁移和重构
3. **API兼容性方案** - 新旧API并行运行和兼容性保证
4. **迁移管理系统** - 统一的迁移管理和监控
5. **验证工具** - 迁移结果验证和测试

## 迁移前准备

### 1. 环境检查

确保满足以下条件：

```bash
# 检查Python版本（需要3.10+）
python --version

# 检查项目依赖
pip install -r requirements.txt

# 检查数据库连接
python -c "from src.common.database.database import db; print('数据库连接正常')"

# 备份数据库
mysqldump -u username -p database_name > backup_before_migration.sql
```

### 2. 资源评估

**磁盘空间：**
- 数据备份：需要当前数据库大小的2-3倍空间
- 代码备份：约100MB
- 日志文件：约1GB（根据迁移规模）

**内存要求：**
- 数据迁移：至少4GB可用内存
- 代码迁移：至少2GB可用内存
- 验证测试：至少2GB可用内存

**时间估算：**
- 小规模项目（< 100MB数据）：2-4小时
- 中等规模项目（100MB-1GB数据）：4-8小时
- 大规模项目（> 1GB数据）：8-24小时

### 3. 依赖检查

确保以下依赖已安装：

```bash
# 核心依赖
pip install peewee asyncio aiofiles

# 开发工具
pip install ruff black pytest

# 数据库驱动（根据使用的数据库）
pip install pymysql psycopg2-binary
```

## 迁移步骤详解

### 阶段1：准备工作（30分钟）

#### 1.1 创建迁移工作空间

```python
from scripts.migration.migration_manager import MigrationManager

# 创建迁移管理器
manager = MigrationManager()

# 创建迁移计划
plan = manager.create_migration_plan(
    name="MaiBot多租户迁移",
    description="完整的多租户架构迁移",
    include_data=True,
    include_code=True,
    include_api=True
)

print(f"迁移计划ID: {plan.id}")
print(f"预计耗时: {plan.estimated_duration}")
print(f"风险级别: {plan.risk_level}")
```

#### 1.2 代码分析

```python
from scripts.migration.code_migration_tools import CodeMigrationTools

# 分析项目代码
tools = CodeMigrationTools()
analysis = tools.analyze_project()

print(f"需要迁移的文件数: {analysis['files_requiring_migration']}")
print(f"总变更数: {analysis['total_changes_required']}")
print(f"迁移复杂度: {analysis['migration_complexity']}")
```

#### 1.3 生成迁移计划

```python
# 生成详细的迁移计划
plan_file = tools.generate_migration_plan("my_migration_plan.json")
print(f"迁移计划已生成: {plan_file}")
```

### 阶段2：数据迁移（1-4小时）

#### 2.1 自动数据迁移

```python
from scripts.migration.data_migration_strategy import run_migration

# 运行数据迁移
success = await run_migration()
if success:
    print("数据迁移成功")
else:
    print("数据迁移失败")
```

#### 2.2 手动数据迁移（可选）

如果自动迁移失败，可以手动执行：

```python
from scripts.migration.data_migration_strategy import DataMigrationStrategy

strategy = DataMigrationStrategy()

# 分步执行
await strategy._create_data_backup()
await strategy._execute_migration_phases()
await strategy._validate_data_integrity()
```

#### 2.3 数据验证

```python
# 验证数据完整性
is_valid = await strategy._validate_data_integrity()
if is_valid:
    print("数据验证通过")
else:
    print("数据验证失败，需要检查")
```

### 阶段3：代码迁移（2-6小时）

#### 3.1 自动代码迁移

```python
from scripts.migration.code_migration_tools import apply_code_migration

# 迁移所有类型的代码
result = apply_code_migration(dry_run=False)
print(f"处理了 {result['total_files_processed']} 个文件")
print(f"修改了 {result['files_modified']} 个文件")
```

#### 3.2 分阶段代码迁移

```python
# 按阶段迁移代码
migration_types = ["isolation_context", "config_system"]
result = apply_code_migration(migration_types=migration_types, dry_run=False)
```

#### 3.3 代码验证

```python
# 检查代码质量
import subprocess
result = subprocess.run(["ruff", "check", "--fix", "src/"], capture_output=True, text=True)
print(result.stdout)
```

### 阶段4：API兼容性设置（1-2小时）

#### 4.1 启用双API模式

```python
from scripts.migration.api_compatibility_strategy import APICompatibilityStrategy

# 设置API兼容性
api_strategy = APICompatibilityStrategy()
api_strategy.compatibility_config["enable_dual_api"] = True
api_strategy.compatibility_config["legacy_api_warning"] = True
```

#### 4.2 创建迁移时间线

```python
# 创建API迁移时间线
timeline = api_strategy.create_migration_timeline()
print(f"迁移开始时间: {timeline['start_date']}")
print(f"迁移结束时间: {timeline['end_date']}")
```

#### 4.3 API使用监控

```python
# 生成兼容性报告
report = api_strategy.generate_migration_report()
print(f"旧API调用次数: {report['usage_statistics']['total_legacy_calls']}")
print(f"新API调用次数: {report['usage_statistics']['total_new_calls']}")
```

### 阶段5：验证和测试（1-3小时）

#### 5.1 运行迁移验证

```python
from scripts.migration.migration_validator import run_migration_validation

# 运行完整验证
validation_result = await run_migration_validation()
print(f"验证状态: {validation_result['overall_status']}")
print(f"通过测试: {validation_result['passed_tests']}/{validation_result['total_tests']}")
```

#### 5.2 功能测试

```python
# 测试关键功能
async def test_functionality():
    # 测试智能体配置加载
    # 测试聊天流创建
    # 测试记忆系统
    # 测试配置隔离
    pass

await test_functionality()
```

#### 5.3 性能测试

```python
# 性能对比测试
import time

start_time = time.time()
# 执行关键操作
end_time = time.time()
print(f"操作耗时: {end_time - start_time:.3f}秒")
```

### 阶段6：监控和优化（持续）

#### 6.1 监控系统状态

```python
from scripts.migration.migration_manager import create_migration_manager

manager = create_migration_manager()
status = manager.get_migration_status()
print(f"当前状态: {status['status']}")
print(f"进度: {status['metrics']['success_rate']:.1f}%")
```

#### 6.2 生成迁移报告

```python
# 生成最终报告
report = manager.generate_migration_report()
with open("migration_final_report.json", "w") as f:
    json.dump(report, f, indent=2, default=str)
```

## 常见问题和解决方案

### Q1: 数据迁移过程中断怎么办？

**解决方案：**
1. 检查迁移日志定位问题
2. 修复问题后从检查点恢复：
```python
from scripts.migration.data_migration_strategy import DataMigrationStrategy

strategy = DataMigrationStrategy()
await strategy.load_checkpoint("path_to_checkpoint.json")
success = await strategy.execute_full_migration()
```

### Q2: 代码迁移后出现语法错误

**解决方案：**
1. 使用ruff自动修复：
```bash
ruff check --fix src/
```

2. 手动修复剩余错误
3. 运行测试确保功能正常

### Q3: API兼容性问题

**解决方案：**
1. 检查API使用统计：
```python
from scripts.migration.api_compatibility_strategy import generate_compatibility_report
report = generate_compatibility_report()
print(report["deprecated_endpoints"])
```

2. 更新代码使用新API
3. 使用兼容性装饰器

### Q4: 性能下降

**解决方案：**
1. 检查性能指标
2. 优化数据库查询
3. 调整配置参数
4. 考虑缓存策略

### Q5: 迁移回滚

如果迁移失败需要回滚：

```python
from scripts.migration.migration_manager import MigrationManager

manager = MigrationManager()
# 迁移计划应该启用回滚功能
plan = manager.create_migration_plan(
    name="回滚迁移",
    description="回滚到迁移前状态",
    rollback_enabled=True
)
```

## 迁移检查清单

### 迁移前检查

- [ ] 数据库备份完成
- [ ] 代码备份完成
- [ ] 环境依赖检查完成
- [ ] 磁盘空间充足
- [ ] 迁移计划已创建
- [ ] 迁移时间窗口已确认

### 迁移中检查

- [ ] 数据迁移成功
- [ ] 代码迁移无错误
- [ ] API兼容性正常
- [ ] 基础功能测试通过
- [ ] 数据验证通过

### 迁移后检查

- [ ] 所有功能正常
- [ ] 性能测试通过
- [ ] 安全验证通过
- [ ] 监控系统正常
- [ ] 文档已更新
- [ ] 团队培训完成

## 最佳实践

### 1. 迁移策略

- **分阶段迁移**：将迁移过程分为多个阶段，逐步进行
- **测试先行**：在测试环境完整验证后再在生产环境执行
- **监控驱动**：建立完善的监控体系，及时发现问题
- **回滚准备**：始终准备回滚方案，确保可以快速恢复

### 2. 数据安全

- **多重备份**：在迁移前创建多个备份副本
- **完整性验证**：每次数据操作后进行完整性检查
- **权限控制**：严格控制迁移期间的数据库访问权限
- **审计日志**：记录所有数据操作，便于问题追踪

### 3. 代码质量

- **自动化工具**：充分利用自动化工具减少人为错误
- **代码审查**：重要变更需要进行代码审查
- **测试覆盖**：确保关键功能有足够的测试覆盖
- **文档同步**：及时更新技术文档和API文档

### 4. 性能优化

- **基准测试**：建立迁移前的性能基准
- **渐进优化**：在迁移过程中持续优化性能
- **资源监控**：实时监控系统资源使用情况
- **容量规划**：提前规划系统容量需求

## 监控和维护

### 1. 关键指标

- **系统性能**：响应时间、吞吐量、资源使用率
- **数据质量**：数据完整性、一致性、准确性
- **API使用**：新旧API使用比例、错误率
- **用户体验**：功能可用性、错误报告

### 2. 告警设置

```python
# 示例：设置关键指标告警
alerts = {
    "response_time": {"threshold": 1000, "unit": "ms"},
    "error_rate": {"threshold": 0.01, "unit": "ratio"},
    "disk_usage": {"threshold": 0.8, "unit": "ratio"},
    "memory_usage": {"threshold": 0.9, "unit": "ratio"}
}
```

### 3. 定期维护

- **每日检查**：系统状态和关键指标
- **每周审查**：性能趋势和问题分析
- **每月优化**：系统调优和性能改进
- **季度评估**：架构优化和技术升级

## 技术支持

### 文档资源

- [refactor.md](../refactor.md) - 架构设计文档
- [API文档](api_reference.md) - API参考文档
- [故障排除指南](troubleshooting.md) - 常见问题解决

### 工具脚本

- `scripts/migration/migration_manager.py` - 迁移管理工具
- `scripts/migration/data_migration_strategy.py` - 数据迁移工具
- `scripts/migration/code_migration_tools.py` - 代码迁移工具
- `scripts/migration/api_compatibility_strategy.py` - API兼容性工具
- `scripts/migration/migration_validator.py` - 验证工具

### 联系方式

如果遇到迁移过程中的问题，请：

1. 查看本文档和相关文档
2. 检查日志文件和错误信息
3. 在测试环境重现问题
4. 联系技术支持团队

---

**注意：** 本文档基于MaiBot项目的多租户隔离架构设计。在执行迁移前，请务必仔细阅读并理解所有步骤，建议在测试环境完整验证后再在生产环境执行。