import os
import re
from typing import Tuple

from src.common.message.tenant_context import get_current_agent_id, get_current_tenant_id

_BASE_STORAGE_DIR = os.path.join("data", "tenant_storage")
_SANITIZE_PATTERN = re.compile(r"[^a-zA-Z0-9_.-]")


def _sanitize_segment(value: str) -> str:
    return _SANITIZE_PATTERN.sub("_", value)


def _require_scope() -> Tuple[str, str]:
    tenant_id = get_current_tenant_id()
    agent_id = get_current_agent_id()
    if not tenant_id or not agent_id:
        raise RuntimeError("Tenant-aware storage requires tenant_id and agent_id context")
    return tenant_id, agent_id


def tenant_storage_root() -> str:
    tenant_id, agent_id = _require_scope()
    return os.path.join(_BASE_STORAGE_DIR, _sanitize_segment(tenant_id), _sanitize_segment(agent_id))


def tenant_storage_path(*segments: str) -> str:
    return os.path.join(tenant_storage_root(), *segments)


def ensure_storage_subdir(*segments: str) -> str:
    path = tenant_storage_path(*segments)
    os.makedirs(path, exist_ok=True)
    return path
