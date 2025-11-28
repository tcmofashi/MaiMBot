# MaiMBot 一键测试脚本使用指南

## 概述

MaiMBot提供了完整的一键测试解决方案，可以自动启动配置器后端和回复后端，并运行各种类型的测试。

## 脚本文件

### 1. `start_maimbot_test.py` - 主要测试脚本 🎯

**功能最全面的一键测试脚本，推荐使用**

#### 基本用法

```bash
# 基础连接测试（默认）
python start_maimbot_test.py

# 完整集成测试（包含用户注册、Agent创建、WebSocket对话等）
python start_maimbot_test.py --integration

# 自定义参数测试
python start_maimbot_test.py --users 3 --agents 2

# 只启动服务，不运行测试
python start_maimbot_test.py --start-only

# 测试后不清理服务（保持服务运行）
python start_maimbot_test.py --no-cleanup
```

#### 参数说明

- `--users`: 用户数量（默认: 2）
- `--agents`: 每个用户的Agent数量（默认: 1）
- `--integration`: 运行完整集成测试
- `--no-cleanup`: 测试后不清理服务
- `--start-only`: 只启动服务，不运行测试

### 2. `simple_test.py` - 简化测试脚本 ⚡

**轻量级测试脚本，启动速度快**

```bash
python simple_test.py
```

### 3. `run_full_test.py` - 完整功能脚本 🔧

**功能最完整的脚本，包含所有高级功能**

```bash
# 基础测试
python run_full_test.py

# 自定义参数
python run_full_test.py --users 5 --agents 3

# 只启动服务
python run_full_test.py --start-only
```

## 测试内容

### 基础连接测试
- ✅ 配置器后端启动（端口8000）
- ✅ 回复后端启动（端口8095）
- ✅ API健康检查
- ✅ WebSocket连接测试

### 完整集成测试（--integration）
- 🔹 用户注册和认证
- 🔹 多个Agent创建
- 🔹 WebSocket多路连接对话
- 🔹 消息发送和响应
- 🔹 数据库清理

## 服务架构

```
┌─────────────────┐    ┌─────────────────┐
│   配置器后端     │    │   回复后端       │
│  (端口: 8000)   │    │  (端口: 8095)   │
│                │    │                │
│ • 用户注册      │    │ • WebSocket     │
│ • Agent管理     │    │ • 消息处理      │
│ • API认证       │    │ • 聊天功能      │
└─────────────────┘    └─────────────────┘
```

## 常见问题

### Q: 配置器后端启动很慢？
A: 这是正常现象，系统需要初始化数据库、插件等组件，通常需要20-30秒。

### Q: API健康检查失败？
A: 可能是启动时间不够，脚本会给足够时间启动。如果仍有问题，可以检查端口是否被占用。

### Q: 集成测试失败？
A: 检查依赖是否完整安装：
```bash
pip install PyJWT "pydantic[email]" aiohttp
```

### Q: 如何停止服务？
A: 按 `Ctrl+C` 即可优雅停止所有服务。

## 日志文件

测试运行时会生成以下日志文件：
- `maimbot_test.log` - 主测试日志
- `full_test.log` - 完整测试日志

## 示例输出

```
🤖 MaiMBot 一键测试脚本
==================================================
2025-11-12 15:00:20 [INFO] 🎯 MaiMBot 完整测试开始
2025-11-12 15:00:20 [INFO] 🚀 启动配置器后端...
2025-11-12 15:00:45 [INFO] ✅ 配置器后端启动成功!
2025-11-12 15:01:20 [INFO] ✅ 回复后端启动成功!
2025-11-12 15:01:25 [INFO] ✅ 回复后端WebSocket连接成功
2025-11-12 15:01:36 [INFO] 🎉 完整测试成功完成!
==================================================
```

## 快速开始

1. **确保环境就绪**：
   ```bash
   conda activate maibot
   pip install PyJWT "pydantic[email]" aiohttp
   ```

2. **运行基础测试**：
   ```bash
   python start_maimbot_test.py
   ```

3. **运行完整测试**：
   ```bash
   python start_maimbot_test.py --integration --users 3 --agents 2
   ```

4. **查看结果**：
   检查控制台输出和日志文件，确认所有测试都通过。

## 技术支持

如遇到问题，请检查：
1. Python环境和依赖包
2. 端口8000和8095是否可用
3. 数据库连接是否正常
4. 日志文件中的详细错误信息