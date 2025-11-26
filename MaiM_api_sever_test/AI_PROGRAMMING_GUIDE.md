# AI 编程指导规范

## 概述
本文档为AI编程提供标准化的指导规范，确保生成的代码和文档具有良好的可维护性和可追溯性。

## 文件命名规范

### 1. 临时测试文件
- **命名格式**: `{功能描述}_temp_{日期}.py`
- **示例**: 
  - `api_auth_test_temp_251127.py`
  - `database_connection_temp_251127.py`
- **说明**: 临时文件在文件名中只显示日期，具体时间放在文件内部注释中

### 2. 正式测试文件
- **命名格式**: `test_{功能模块}_{具体测试}.py`
- **示例**:
  - `test_api_key_management.py`
  - `test_database_connection.py`
- **说明**: 正式测试文件应使用描述性名称，便于理解功能

### 3. 项目报告文档
- **命名格式**: `{项目名称}_{问题描述}_{日期}.md`
- **示例**:
  - `MaiMBot_API_Authentication_Issue_251127.md`
  - `MaiMBot_Database_Performance_Analysis_251127.md`
- **说明**: 项目报告文档在文件名中只显示日期，具体时间放在文档内部

## 输出结果管理

### 1. 重要输出数据
- **存储位置**: `MaiM_api_sever_test/test_data/`
- **文件格式**: JSON、CSV 或 TXT
- **命名规范**: `{测试名称}_results_{日期_时分秒}.{格式}`
- **示例**:
  - `api_performance_results_20251127_143025.json`
  - `database_query_results_20251127_090015.csv`

### 2. 测试数据目录结构
```
MaiM_api_sever_test/
├── test_data/
│   ├── api_tests/           # API测试数据
│   ├── database_tests/      # 数据库测试数据
│   ├── performance_tests/   # 性能测试数据
│   └── integration_tests/   # 集成测试数据
```

## 时间标记规范

### 1. 文件头部时间标记
所有AI生成的文件必须在文件头部包含创建时间信息：

**Python文件示例**:
```python
#!/usr/bin/env python3
"""
[文件功能描述]

创建时间: 2025-11-27 14:30:25
最后修改: 2025-11-27 14:30:25
AI生成标识: [AI模型名称]
"""

# 文件内容...
```

**Markdown文档示例**:
```markdown
# [文档标题]

**创建时间**: 2025年11月27日 14:30:25  
**最后修改**: 2025年11月27日 14:30:25  
**AI生成标识**: [AI模型名称]

## 概述
[文档内容...]
```

### 2. 时间格式标准
- **完整格式**: YYYY-MM-DD HH:MM:SS
- **简化格式**: YYYYMMDD
- **中文格式**: YYYY年MM月DD日

## 代码结构规范

### 1. 测试文件结构模板
```python
#!/usr/bin/env python3
"""
[测试功能描述]

创建时间: YYYY-MM-DD HH:MM:SS
最后修改: YYYY-MM-DD HH:MM:SS
AI生成标识: [AI模型名称]
测试类型: [单元测试/集成测试/性能测试]
"""

import os
import sys
import asyncio
import json
from datetime import datetime

# 配置常量
TEST_CONFIG = {
    "api_base_url": "http://localhost:8000",
    "timeout": 30,
    "max_retries": 3
}

class TestReporter:
    """测试结果报告器"""
    
    def __init__(self, test_name):
        self.test_name = test_name
        self.start_time = datetime.now()
        self.results = []
        
    def log_result(self, test_case, status, details=None):
        """记录测试结果"""
        result = {
            "test_case": test_case,
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "details": details
        }
        self.results.append(result)
        
    def save_results(self):
        """保存测试结果到文件"""
        results_dir = "MaiM_api_sever_test/test_data"
        os.makedirs(results_dir, exist_ok=True)
        
        filename = f"{self.test_name}_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(results_dir, filename)
        
        report = {
            "test_name": self.test_name,
            "start_time": self.start_time.isoformat(),
            "end_time": datetime.now().isoformat(),
            "total_cases": len(self.results),
            "passed_cases": len([r for r in self.results if r["status"] == "PASS"]),
            "results": self.results
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"测试结果已保存到: {filepath}")

async def main_test_function():
    """主测试函数"""
    reporter = TestReporter("示例测试")
    
    try:
        # 测试用例1
        reporter.log_result("测试用例1", "PASS", "测试通过")
        
        # 测试用例2
        reporter.log_result("测试用例2", "FAIL", "预期结果不匹配")
        
    except Exception as e:
        reporter.log_result("全局异常", "ERROR", str(e))
    
    finally:
        reporter.save_results()

if __name__ == "__main__":
    asyncio.run(main_test_function())
```

### 1. 文档结构模板
```markdown
# [文档标题]

**创建时间**: YYYY年MM月DD日 HH:MM:SS  
**最后修改**: YYYY年MM月DD日 HH:MM:SS  
**AI生成标识**: [AI模型名称]  
**文档类型**: [问题分析/测试报告/架构设计]

## 概述
[简要描述文档目的和内容]

## 问题描述
[详细描述遇到的问题或分析的目标]

## 分析与解决方案
[提供详细的分析过程和解决方案]

## 测试结果
[如有测试，提供测试结果和数据]

## 总结与建议
[总结分析结果，提供后续建议]

## 相关文件
- [关联文件1]
- [关联文件2]
```

## 测试文件可用性规范

### 1. 测试文件位置要求
- **正式测试文件**: 应该在任何目录下都可执行，不依赖于根目录的特定环境
- **路径引用**: 使用相对路径或环境变量，避免硬编码绝对路径
- **依赖管理**: 明确声明所有依赖，确保测试环境一致性

### 2. 长期可用性保证
- **API稳定性**: 正式测试文件应该针对稳定的API接口
- **向后兼容**: 确保测试在系统升级后仍能正常工作
- **文档同步**: 测试文件与对应功能文档保持同步更新

### 3. 环境独立性
```python
# 正确的路径引用方式
import os
import sys

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# 使用环境变量配置
api_base_url = os.getenv('API_BASE_URL', 'http://localhost:8000')
database_url = os.getenv('DATABASE_URL', 'sqlite:///test.db')
```

## 文件分类规范

### 1. 测试文件分类标准
- **单元测试**: 针对单个函数或类的测试
- **集成测试**: 测试多个模块的协作
- **功能测试**: 验证特定功能的完整性
- **性能测试**: 测试系统性能和响应时间
- **回归测试**: 确保修改不会破坏现有功能

### 2. 文档分类标准
- **架构设计**: 系统架构和设计决策
- **API文档**: 接口说明和使用方法
- **问题分析**: 故障排查和问题解决过程
- **测试报告**: 测试结果和性能分析
- **使用指南**: 用户操作和配置说明

### 3. 正确分类实践
```python
# 在文件头部明确分类
"""
文件类型: 单元测试
测试模块: src/api/auth.py
测试功能: 用户认证流程
分类标签: [auth, unit_test, api]
"""
```

## 最佳实践

### 1. 代码质量
- 遵循PEP 8编码规范
- 添加适当的注释和文档字符串
- 使用类型注解
- 包含错误处理机制

### 2. 测试覆盖
- 为重要功能编写单元测试
- 包含边界条件测试
- 提供测试数据生成脚本

### 3. 文档完整性
- 每个功能模块应有对应的文档
- 包含使用示例和API说明
- 提供故障排除指南

### 4. 版本控制
- 使用有意义的提交信息
- 关联Issue或任务编号
- 保持文件分类的准确性

## 自动化工具

### 1. 文件验证脚本
```python
# scripts/validate_ai_files.py
# 验证AI生成文件是否符合规范
```

### 2. 报告生成器
```python
# scripts/generate_test_report.py
# 生成统一的测试报告
```

通过遵循这些规范，可以确保AI生成的代码和文档具有良好的质量和可维护性。
