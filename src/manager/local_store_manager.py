import datetime
import json
from threading import Lock
from typing import Any, Dict, Tuple

from src.common.database.database_model import RuntimeState
from src.common.logger import get_logger
from src.common.message.tenant_context import get_current_agent_id, get_current_tenant_id

logger = get_logger("local_storage")


class LocalStoreManager:
    """基于数据库的运行时状态存储，取代本地 JSON 记事本。"""

    def __init__(self):
        self._cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._lock = Lock()

    def __getitem__(self, item: str) -> Any:
        """获取本地存储数据"""
        return self.store.get(item)

    def __setitem__(self, key: str, value: Any):
        """设置本地存储数据"""
        self.store[key] = value
        self._write_key(key, value)

    def __delitem__(self, key: str):
        """删除本地存储数据"""
        if key in self.store:
            del self.store[key]
            self._delete_key(key)
        else:
            logger.warning(f"尝试删除不存在的键: {key}")

    def __contains__(self, item: str) -> bool:
        """检查本地存储数据是否存在"""
        return item in self.store

    @property
    def store(self) -> Dict[str, Any]:
        """返回当前上下文的缓存副本，必要时从数据库加载。"""
        scope = self._current_scope()
        with self._lock:
            if scope not in self._cache:
                self._cache[scope] = self._load_scope_from_db()
            return self._cache[scope]

    def load_local_store(self):
        """主动加载当前上下文缓存。"""
        _ = self.store

    def save_local_store(self):
        """将当前缓存写回数据库。"""
        for key, value in self.store.items():
            self._write_key(key, value)

    def _current_scope(self) -> Tuple[str, str]:
        tenant_id = get_current_tenant_id()
        agent_id = get_current_agent_id()
        if not tenant_id or not agent_id:
            raise RuntimeError("local_storage 需要 tenant_id 和 agent_id 上下文")
        return tenant_id, agent_id

    def _load_scope_from_db(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        for row in RuntimeState.select():
            data[row.state_key] = self._deserialize_value(row.state_value)
        if data:
            logger.info("已从数据库加载运行时状态缓存")
        return data

    def _write_key(self, key: str, value: Any):
        serialized = self._serialize_value(value)
        now = datetime.datetime.utcnow()
        record = RuntimeState.get_or_none(RuntimeState.state_key == key)
        if record:
            record.state_value = serialized
            record.updated_at = now
            record.save()
        else:
            RuntimeState.create(state_key=key, state_value=serialized, updated_at=now)

    def _delete_key(self, key: str):
        RuntimeState.delete().where(RuntimeState.state_key == key).execute()

    @staticmethod
    def _serialize_value(value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False)
        except TypeError:
            logger.warning("值无法直接序列化，已使用字符串形式存储")
            return json.dumps(str(value), ensure_ascii=False)

    @staticmethod
    def _deserialize_value(raw_value: str | None) -> Any:
        if raw_value is None:
            return None
        try:
            return json.loads(raw_value)
        except json.JSONDecodeError:
            return raw_value


local_storage = LocalStoreManager()  # 全局单例化
