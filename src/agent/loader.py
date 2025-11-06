"""Utilities for loading Agent definitions from configuration files."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Iterable, List, Optional

import tomlkit

from src.agent.agent import Agent
from src.agent.registry import clear_agents, register_agents
from src.common.logger import get_logger

LOGGER = get_logger("agent_loader")


def _default_agent_config_dir() -> Path:
    """Return the default directory that stores agent configuration files."""

    return Path(__file__).resolve().parent.parent.parent / "config" / "agents"


def _iter_agent_files(directory: Path) -> Iterable[Path]:
    """Yield agent configuration files under *directory* in alphabetical order."""

    if not directory.exists():
        return []

    files = [p for p in directory.glob("*.toml") if p.is_file()]
    files.sort()
    return files


def _extract_persona_overrides(raw_persona: object, agent: Agent) -> None:
    """Populate selective persona overrides based on user-provided fields."""

    if not isinstance(raw_persona, Mapping):
        agent._persona_override_fields = None
        return

    override_fields: dict[str, object] = {}
    for key in raw_persona.keys():
        if not hasattr(agent.persona, key):
            continue
        override_fields[key] = getattr(agent.persona, key)

    agent._persona_override_fields = override_fields or {}


def _load_agent_file(path: Path) -> Agent:
    """Parse a single agent configuration file and return an :class:`Agent`."""

    try:
        with path.open("r", encoding="utf-8") as fp:
            document = tomlkit.load(fp)
            data = document.unwrap() if hasattr(document, "unwrap") else document
    except Exception as exc:  # pragma: no cover - IO failure
        raise RuntimeError(f"读取 Agent 配置失败: {path}") from exc

    try:
        agent = Agent.from_dict(data)
        _extract_persona_overrides(data.get("persona"), agent)
    except Exception as exc:
        raise ValueError(f"解析 Agent 配置失败: {path} ({exc})") from exc

    if not agent.agent_id:
        raise ValueError(f"Agent 配置缺少 agent_id 字段: {path}")

    if not agent.name:
        raise ValueError(f"Agent 配置缺少 name 字段: {path}")

    return agent


def load_agents_from_directory(
    directory: Optional[str | os.PathLike[str]] = None,
    *,
    auto_register: bool = True,
    clear_existing: bool = False,
) -> List[Agent]:
    """Load all agent configurations under *directory*.

    Args:
        directory: Directory path that contains ``.toml`` agent files. If not
            provided, the default ``config/agents`` directory under the project
            root will be used.
        auto_register: Whether to automatically register loaded agents into the
            global registry.
        clear_existing: Clear existing registered agents before registering the
            newly loaded ones. Only applies when ``auto_register`` is ``True``.

    Returns:
        List[Agent]: Loaded agents. Invalid files are skipped with an error log.
    """

    target_dir = Path(directory) if directory is not None else _default_agent_config_dir()

    if not target_dir.exists():
        LOGGER.warning("Agent 配置目录不存在: %s", target_dir)
        return []

    loaded_agents: List[Agent] = []
    for file_path in _iter_agent_files(target_dir):
        try:
            agent = _load_agent_file(file_path)
        except Exception as exc:
            LOGGER.error("加载 Agent 配置失败 (%s): %s", file_path, exc)
            continue

        loaded_agents.append(agent)
        LOGGER.debug("已加载 Agent 配置: %s (%s)", agent.name, agent.agent_id)

    if auto_register and loaded_agents:
        if clear_existing:
            clear_agents()
        register_agents(loaded_agents)
        LOGGER.info("已注册 %d 个 Agent 配置", len(loaded_agents))

    return loaded_agents


__all__ = ["load_agents_from_directory"]
