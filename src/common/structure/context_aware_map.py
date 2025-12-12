from typing import TypeVar, Generic, Dict, Optional, Iterator, ValuesView, ItemsView, List, Any
import logging
from collections.abc import MutableMapping
from src.common.message.tenant_context import get_current_tenant_id, get_current_agent_id
from src.common.logger import get_logger

logger = get_logger("context_map")

KT = TypeVar("KT")
VT = TypeVar("VT")

class ContextAwareMap(MutableMapping[KT, VT]):
    """
    上下文感知的字典容器。
    内部按 (tenant_id, agent_id) 分区存储数据。
    
    行为：
    1. 读写操作 (get, set, __getitem__) 会根据当前租户上下文自动定位到对应分区。
    2. 如果当前无租户上下文：
       - 读取操作会降级为全局搜索，并记录警告。
       - 写入操作需要显式提供 tenant_id/agent_id，否则抛错(或根据实现策略)。
    3. 迭代操作 (keys, values, items) 会根据上下文返回子集，无上下文时返回全集并警告。
    """

    def __init__(self):
        # 结构: tenant_id -> agent_id -> key -> value
        self._data: Dict[str, Dict[str, Dict[KT, VT]]] = {}
        # 辅助索引：key -> (tenant_id, agent_id) 用于快速全局查找
        self._global_index: Dict[KT, tuple[str, str]] = {}

    def _get_context(self) -> tuple[Optional[str], Optional[str]]:
        return get_current_tenant_id(), get_current_agent_id()

    def set_with_context(self, key: KT, value: VT, tenant_id: str, agent_id: str = ""):
        """显式指定上下文进行存储"""
        if not tenant_id:
            raise ValueError("ContextAwareMap storage requires a tenant_id")
            
        if tenant_id not in self._data:
            self._data[tenant_id] = {}
        if agent_id not in self._data[tenant_id]:
            self._data[tenant_id][agent_id] = {}
            
        self._data[tenant_id][agent_id][key] = value
        self._global_index[key] = (tenant_id, agent_id)

    def __setitem__(self, key: KT, value: VT):
        """Standard setitem uses current context. Fallback or error if no context?"""
        tenant_id, agent_id = self._get_context()
        if not tenant_id:
             # 尝试从 value 中提取? (不通用)
             # 这里我们为了安全，如果无上下文且无法确定归属，应该报错
             # 但为了兼容旧代码初始化，可能需要特殊处理。
             # 建议使用 set_with_context 替代 explicit set
             # 暂时抛出警告并拒绝，或者寻找 fallback
             # 对于 ChatManager，大部分创建都在 context 下，或者 load_all_streams 时有保存的数据
             logger.warning(f"Writing to ContextAwareMap without context for key {key}. Use set_with_context instead.")
             # 这种情况下无法安全存储，抛出异常更合适
             raise RuntimeError(f"Cannot set item {key} without tenant context. Use set_with_context().")
        
        self.set_with_context(key, value, tenant_id, agent_id or "")

    def __getitem__(self, key: KT) -> VT:
        tenant_id, agent_id = self._get_context()
        
        # 1. 有上下文：严格匹配
        if tenant_id:
            agent_id = agent_id or ""
            # 尝试直接定位
            try:
                return self._data[tenant_id][agent_id][key]
            except KeyError:
                # 即使全局有这个key，但如果不在当前租户下，也应该视为不存在 (Isolation)
                # 检查是否存在于其他租户
                if key in self._global_index:
                    owner_tenant, owner_agent = self._global_index[key]
                    if owner_tenant != tenant_id or (agent_id and owner_agent != agent_id):
                        # logger.warning(f"Access denied: Key {key} belongs to {owner_tenant}:{owner_agent}, current {tenant_id}:{agent_id}")
                        raise KeyError(key)
                raise KeyError(key)

        # 2. 无上下文：全局搜索 + 警告
        if key in self._global_index:
            logger.info(f"Global access to key {key} without tenant context detected.")
            t_id, a_id = self._global_index[key]
            return self._data[t_id][a_id][key]
        
        raise KeyError(key)

    def __delitem__(self, key: KT):
        if key in self._global_index:
            t_id, a_id = self._global_index[key]
            # 校验权限？如果当前有上下文，必须匹配才能删除
            curr_tenant, curr_agent = self._get_context()
            if curr_tenant:
                if t_id != curr_tenant:
                     raise KeyError(f"Key {key} not found in current context")
                if curr_agent and a_id != curr_agent:
                     raise KeyError(f"Key {key} not found in current context")
            
            del self._data[t_id][a_id][key]
            del self._global_index[key]
            # Cleanup empty dicts?
        else:
            raise KeyError(key)

    def __iter__(self) -> Iterator[KT]:
        # 根据上下文返回 keys
        tenant_id, agent_id = self._get_context()
        if tenant_id:
            agent_id = agent_id or ""
            if tenant_id in self._data and agent_id in self._data[tenant_id]:
                yield from self._data[tenant_id][agent_id]
            return

        # 全局遍历 + 警告
        logger.info(f"Global iteration on ContextAwareMap without tenant context.")
        yield from self._global_index.keys()

    def __len__(self) -> int:
        tenant_id, agent_id = self._get_context()
        if tenant_id:
            agent_id = agent_id or ""
            return len(self._data.get(tenant_id, {}).get(agent_id, {}))
        
        return len(self._global_index)

    def values(self) -> ValuesView[VT]:
        tenant_id, agent_id = self._get_context()
        if tenant_id:
             agent_id = agent_id or ""
             return self._data.get(tenant_id, {}).get(agent_id, {}).values()
        
        logger.info(f"Global values() access on ContextAwareMap without tenant context.")
        # 构建所有 values
        all_values = []
        for t_data in self._data.values():
            for a_data in t_data.values():
                all_values.extend(a_data.values())
        return all_values # type: ignore (return list as view is acceptable enough for python duck typing usually, strictly ValuesView requires more) 

    def items(self) -> ItemsView[KT, VT]:
        tenant_id, agent_id = self._get_context()
        if tenant_id:
             agent_id = agent_id or ""
             return self._data.get(tenant_id, {}).get(agent_id, {}).items()

        logger.info(f"Global items() access on ContextAwareMap without tenant context.")
        all_items = []
        for t_data in self._data.values():
             for a_data in t_data.values():
                 all_items.extend(a_data.items())
        return all_items # type: ignore
    
    def clear(self):
        # 同样应该受限于 Context
        # 但如果是系统初始化，可能需要清空所有
        # 简单起见，如果无 Context，清空所有；有 Context，清空对应 Partition
        tenant_id, agent_id = self._get_context()
        if not tenant_id:
            logger.info("Global clear() on ContextAwareMap")
            self._data.clear()
            self._global_index.clear()
        else:
            agent_id = agent_id or ""
            if tenant_id in self._data and agent_id in self._data[tenant_id]:
                # 需要同步清理 global index，比较麻烦
                # 遍历删除
                keys_to_remove = list(self._data[tenant_id][agent_id].keys())
                for k in keys_to_remove:
                    del self[k] 
