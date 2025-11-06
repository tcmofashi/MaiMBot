"""Agent manager responsible for synchronising agents between storage and runtime."""

from __future__ import annotations

import json
import os
import datetime
from dataclasses import asdict
from threading import RLock
from typing import Dict, List, Optional

from peewee import DoesNotExist

from src.agent.agent import Agent
from src.agent.loader import load_agents_from_directory
from src.agent.registry import clear_agents, register_agent
from src.common.database.database_model import AgentRecord
from src.common.logger import get_logger
from src.config.official_configs import PersonalityConfig

LOGGER = get_logger("agent_manager")


class AgentManager:
    """Manage persisted Agent definitions and runtime registry synchronisation."""

    def __init__(self) -> None:
        self._cache: Dict[str, Agent] = {}
        self._lock = RLock()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _agent_from_record(self, record: AgentRecord) -> Agent:
        persona_data = json.loads(record.persona)
        persona = PersonalityConfig.from_dict(persona_data)

        bot_overrides = json.loads(record.bot_overrides) if record.bot_overrides else {}
        config_overrides = json.loads(record.config_overrides) if record.config_overrides else {}
        tags = json.loads(record.tags) if record.tags else []

        agent = Agent(
            agent_id=record.agent_id,
            name=record.name,
            persona=persona,
            bot_overrides=bot_overrides,
            config_overrides=config_overrides,
            tags=tags,
            description=record.description or "",
        )
        try:
            agent._persona_override_fields = persona_data if isinstance(persona_data, dict) else None
        except AttributeError:
            pass

        return agent

    def _record_from_agent(self, agent: Agent) -> dict:
        persona_dict = asdict(agent.persona)

        tags_list = list(agent.tags) if agent.tags else []

        return {
            "agent_id": agent.agent_id,
            "name": agent.name,
            "description": agent.description,
            "tags": json.dumps(tags_list),
            "persona": json.dumps(persona_dict),
            "bot_overrides": json.dumps(agent.bot_overrides) if agent.bot_overrides else None,
            "config_overrides": json.dumps(agent.config_overrides) if agent.config_overrides else None,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def sync_from_directory(
        self,
        directory: Optional[str | os.PathLike[str]] = None,
    ) -> List[str]:
        """Load agent definitions from config directory and persist them."""

        agents = load_agents_from_directory(directory=directory, auto_register=False)
        stored_ids: List[str] = []

        for agent in agents:
            stored_ids.append(agent.agent_id)
            self.upsert_agent(agent, register=False)

        if stored_ids:
            LOGGER.info("已从目录同步 %d 个 Agent", len(stored_ids))

        return stored_ids

    def upsert_agent(self, agent: Agent, *, register: bool = True) -> None:
        """Insert or update an Agent definition in the database."""

        payload = self._record_from_agent(agent)
        now = datetime.datetime.utcnow()

        record, created = AgentRecord.get_or_create(
            agent_id=agent.agent_id, defaults={**payload, "created_at": now, "updated_at": now}
        )
        if not created:
            for field, value in payload.items():
                setattr(record, field, value)
            record.updated_at = now
            record.save()
        else:
            record.updated_at = now
            record.save()

        with self._lock:
            self._cache[agent.agent_id] = agent

        if register:
            register_agent(agent)

    def get_agent(self, agent_id: str) -> Optional[Agent]:
        """Fetch an Agent by id, loading from cache or database if necessary."""

        if not agent_id:
            agent_id = "default"

        with self._lock:
            cached = self._cache.get(agent_id)
        if cached is not None:
            return cached

        try:
            record = AgentRecord.get(AgentRecord.agent_id == agent_id)
        except DoesNotExist:
            LOGGER.debug("数据库中不存在 Agent '%s'", agent_id)
            return None

        agent = self._agent_from_record(record)

        with self._lock:
            self._cache[agent_id] = agent

        register_agent(agent)
        return agent

    def list_agents(self) -> List[Agent]:
        """Return all Agents stored in the database."""

        agents: List[Agent] = []
        for record in AgentRecord.select():
            agents.append(self._agent_from_record(record))
        return agents

    def refresh_registry(self, *, clear: bool = True) -> int:
        """Register all agents from the database into runtime registry."""

        if clear:
            clear_agents()

        count = 0
        for agent in self.list_agents():
            register_agent(agent)
            with self._lock:
                self._cache[agent.agent_id] = agent
            count += 1
        return count

    def agent_exists(self, agent_id: str) -> bool:
        """Check whether an Agent exists in cache or database without loading it."""

        if not agent_id:
            agent_id = "default"

        with self._lock:
            if agent_id in self._cache:
                return True

        return AgentRecord.select().where(AgentRecord.agent_id == agent_id).exists()

    def initialize(self, directory: Optional[str | os.PathLike[str]] = None) -> int:
        """Sync agents from directory and refresh registry."""

        self.sync_from_directory(directory)
        count = self.refresh_registry(clear=True)
        if count == 0:
            LOGGER.warning("数据库中未找到任何 Agent，已保持默认配置")
        return count


_manager = AgentManager()


def get_agent_manager() -> AgentManager:
    return _manager
