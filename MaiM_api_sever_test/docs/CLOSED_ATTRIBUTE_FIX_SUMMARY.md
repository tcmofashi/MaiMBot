# 修复 maim_message 库中 ClientConnection 的 closed 属性问题

## 问题描述
在集成测试中发现消息发送失败，错误信息：
```
发送消息失败: 'ClientConnection' object has no attribute 'closed'
```

这个错误发生在 maim_message 库的 TenantMessageClient 类中，原因是新版本的 websockets 库（15.0.1）改变了 WebSocket 连接对象的属性接口。

## 根本原因
- **旧版本 websockets**: 使用 `websocket.closed` 属性（布尔值，True 表示已关闭）
- **新版本 websockets (15+)**: 使用 `websocket.state` 属性（枚举值：State.OPEN=1 表示连接打开）

## 修复方案
在 `/home/tcmofashi/proj/maim_message/src/maim_message/tenant_client.py` 文件中修复 `_is_connected()` 方法：

### 修复前
```python
def _is_connected(self) -> bool:
    """检查是否已连接"""
    return (
        self.state == ConnectionState.CONNECTED
        and self.websocket is not None
        and not self.websocket.closed  # 这里出错
    )
```

### 修复后
```python
def _is_connected(self) -> bool:
    """检查是否已连接"""
    if self.state != ConnectionState.CONNECTED or self.websocket is None:
        return False

    # 检查websockets库版本兼容性
    # 新版本(15+)使用state属性，旧版本使用closed属性
    if hasattr(self.websocket, "state"):
        # 新版本: state.OPEN (1) 表示连接打开
        from websockets.asyncio.connection import State

        return self.websocket.state == State.OPEN
    elif hasattr(self.websocket, "closed"):
        # 旧版本: closed=False 表示连接打开
        return not self.websocket.closed
    else:
        # 都没有属性时，假设连接正常
        return True
```

## 修复特点
1. **版本兼容性**: 支持新旧版本的 websockets 库
2. **渐进式检测**: 优先检测新版本的 `state` 属性，然后检查旧版本的 `closed` 属性
3. **保守策略**: 如果两种属性都不存在，假设连接正常（避免误判）

## 验证结果
1. ✅ 集成测试中不再出现 `'ClientConnection' object has no attribute 'closed'` 错误
2. ✅ 兼容性测试通过，支持新旧版本的 websockets 库
3. ✅ 代码通过 ruff 格式检查，无语法错误

## 相关文件
- 修复文件: `/home/tcmofashi/proj/maim_message/src/maim_message/tenant_client.py`
- 测试文件: `/home/tcmofashi/proj/MaiMBot/run_integration_tests.py`

## 注意事项
- ws_connection.py 文件中使用的是 aiohttp 库，其 ClientWebSocketResponse 类仍然有 `closed` 属性，无需修改
- 修复仅影响使用 websockets 库的 TenantMessageClient 类