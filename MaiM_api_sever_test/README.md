# MaiM API Server 测试文件归档

## 概述
此目录包含了所有AI创建的测试文件，已按照pytest结构进行归档整理，并遵循AI编程指导规范。

## 目录结构
```
MaiM_api_sever_test/
├── pytest/                    # 所有测试文件归档目录
│   ├── test_api_auto_tester.py     # API自动测试器
│   ├── test_maimbot_full_integration.py # MaiMBot完整集成测试
│   ├── deprecated_files/      # 过期文件归档目录
│   │   ├── api_auto_tester.py     # 原API自动测试器（已重命名）
│   │   ├── api_test.py            # API测试
│   │   ├── api_tester.py          # API测试器
│   │   ├── extract_api_endpoints.py # API端点提取器
│   │   └── start_maimbot_test.py  # 原MaiMBot启动测试（已重命名）
│   └── test_*.py              # 各种功能测试文件
├── docs/                      # API服务器相关文档归档目录
│   ├── ALL_ENDPOINTS.md       # 所有API端点文档
│   ├── API_SERVER.md          # API服务器架构设计文档
│   ├── API_REFERENCE.md       # API参考文档
│   ├── API_USAGE_EXAMPLES.md  # API使用示例
│   ├── api_tester_template.json # API测试器模板
│   └── deprecated_files/      # 过期文档归档目录
│       ├── POST_agents_Internal_Server_Error_问题分析_20251126_0214.md
│       └── POST_agents_Internal_Server_Error_问题分析_20251126_0220.md
├── test_data/                 # 测试数据存储目录
│   ├── api_tests/            # API测试数据
│   ├── database_tests/       # 数据库测试数据
│   ├── performance_tests/    # 性能测试数据
│   └── integration_tests/    # 集成测试数据
├── AI_PROGRAMMING_GUIDE.md   # AI编程指导规范
└── README.md                  # 本说明文件
```

## 测试文件分类

### API测试
- `test_api_auto_tester.py` - API自动测试器（已规范命名）
- `test_maimbot_full_integration.py` - MaiMBot完整集成测试（已规范命名）

### 过期文件归档
- `deprecated_files/` - 包含所有已重命名或过期的测试文件
  - `api_auto_tester.py` - 原API自动测试器（已重命名为test_api_auto_tester.py）
  - `api_test.py` - API测试
  - `api_tester.py` - API测试器
  - `extract_api_endpoints.py` - API端点提取器
  - `start_maimbot_test.py` - 原MaiMBot启动测试（已重命名为test_maimbot_full_integration.py）

### 文档归档
- `docs/` - API服务器相关文档
  - `ALL_ENDPOINTS.md` - 所有API端点文档
  - `API_SERVER.md` - API服务器架构设计文档
  - `API_REFERENCE.md` - API参考文档
  - `API_USAGE_EXAMPLES.md` - API使用示例
  - `api_tester_template.json` - API测试器模板
  - `deprecated_files/` - 过期文档归档目录

## 使用说明
所有测试文件已从根目录移动到此处，保持原有的功能不变。如需运行特定测试，请进入相应目录执行。

## 归档时间
2025年11月27日
