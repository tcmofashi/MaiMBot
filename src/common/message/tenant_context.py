"""Tenant/agent context helpers.

Provides ContextVar-backed getters/setters plus sync/async context managers.
Tenant is mandatory for DB/stream operations; agent is optional but preferred.
"""

from __future__ import annotations

from contextlib import contextmanager, asynccontextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class TenantContextState:
    tenant_id: Optional[str] = None
    agent_id: Optional[str] = None


_STATE: ContextVar[TenantContextState] = ContextVar("tenant_context_state", default=TenantContextState())


def set_current_tenant(tenant_id: Optional[str], agent_id: Optional[str] = None) -> Token:
    return _STATE.set(TenantContextState(tenant_id=tenant_id, agent_id=agent_id))


def reset_current_tenant(token: Token) -> None:
    _STATE.reset(token)


def get_current_tenant_id() -> Optional[str]:
    return _STATE.get().tenant_id


def get_current_agent_id() -> Optional[str]:
    return _STATE.get().agent_id


def get_current_context() -> TenantContextState:
    return _STATE.get()


@contextmanager
def tenant_context(tenant_id: str, agent_id: Optional[str] = None):
    token = set_current_tenant(tenant_id, agent_id)
    try:
        yield
    finally:
        reset_current_tenant(token)


@asynccontextmanager
async def tenant_context_async(tenant_id: str, agent_id: Optional[str] = None):
    token = set_current_tenant(tenant_id, agent_id)
    try:
        yield
    finally:
        reset_current_tenant(token)
