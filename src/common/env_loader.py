"""Project-wide environment loader.

Centralizes .env handling so every entry point (bot runtime, tests, CLI tools)
shares the same behavior when resolving project-level configuration such as the
maim_db connection, logging verbosity, or maim_message server endpoints.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"
TEMPLATE_ENV_FILE = PROJECT_ROOT / "template" / "template.env"


def _read_env(key: str, fallback: Optional[str] = None) -> tuple[Optional[str], bool]:
    """Return the raw env value and whether it was explicitly provided."""

    if key in os.environ:
        return os.environ[key], True
    return fallback, False


def _to_int(value: Optional[str]) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"Invalid integer value for environment variable: {value}") from None


def _to_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ProjectEnvConfig:
    """Typed view over the project-level environment variables."""

    database_url: Optional[str]
    database_host: Optional[str]
    database_port: Optional[int]
    database_name: Optional[str]
    database_user: Optional[str]
    database_password: Optional[str]
    log_level: Optional[str]
    console_log_level: Optional[str]
    file_log_level: Optional[str]
    maim_message_host: Optional[str]
    maim_message_port: Optional[int]
    maim_message_mode: Optional[str]
    maim_message_use_wss: bool
    defined_keys: set[str]

    def has(self, key: str) -> bool:
        """Whether the given environment key was explicitly provided."""

        return key in self.defined_keys


_PROJECT_ENV: Optional[ProjectEnvConfig] = None


def load_project_env(*, force_reload: bool = False) -> ProjectEnvConfig:
    """Load (and cache) the .env file, copying from template when missing."""

    global _PROJECT_ENV

    if _PROJECT_ENV is not None and not force_reload:
        return _PROJECT_ENV

    _ensure_env_file()
    load_dotenv(ENV_FILE, override=False)

    defined_keys: set[str] = set()

    db_url, db_url_defined = _read_env("DATABASE_URL", "sqlite:///data/MaiBot.db")
    if db_url_defined:
        defined_keys.add("DATABASE_URL")

    db_host, db_host_defined = _read_env("DATABASE_HOST", "localhost")
    if db_host_defined:
        defined_keys.add("DATABASE_HOST")

    db_port_raw, db_port_defined = _read_env("DATABASE_PORT", "5432")
    if db_port_defined:
        defined_keys.add("DATABASE_PORT")
    db_port = _to_int(db_port_raw)

    db_name, db_name_defined = _read_env("DATABASE_NAME", "maimbot")
    if db_name_defined:
        defined_keys.add("DATABASE_NAME")

    db_user, db_user_defined = _read_env("DATABASE_USER", "postgres")
    if db_user_defined:
        defined_keys.add("DATABASE_USER")

    db_password, db_password_defined = _read_env("DATABASE_PASSWORD", "")
    if db_password_defined:
        defined_keys.add("DATABASE_PASSWORD")

    log_level, log_level_defined = _read_env("MAIMBOT_LOG_LEVEL")
    if log_level_defined:
        defined_keys.add("MAIMBOT_LOG_LEVEL")

    console_log_level, console_defined = _read_env("MAIMBOT_CONSOLE_LOG_LEVEL")
    if console_defined:
        defined_keys.add("MAIMBOT_CONSOLE_LOG_LEVEL")

    file_log_level, file_defined = _read_env("MAIMBOT_FILE_LOG_LEVEL")
    if file_defined:
        defined_keys.add("MAIMBOT_FILE_LOG_LEVEL")

    mm_host, mm_host_defined = _read_env("MAIM_MESSAGE_HOST", "127.0.0.1")
    if mm_host_defined:
        defined_keys.add("MAIM_MESSAGE_HOST")

    mm_port_raw, mm_port_defined = _read_env("MAIM_MESSAGE_PORT", "8090")
    if mm_port_defined:
        defined_keys.add("MAIM_MESSAGE_PORT")
    mm_port = _to_int(mm_port_raw)

    mm_mode, mm_mode_defined = _read_env("MAIM_MESSAGE_MODE", "ws")
    if mm_mode_defined:
        defined_keys.add("MAIM_MESSAGE_MODE")

    mm_wss_raw, mm_wss_defined = _read_env("MAIM_MESSAGE_USE_WSS")
    if mm_wss_defined:
        defined_keys.add("MAIM_MESSAGE_USE_WSS")
    mm_use_wss = _to_bool(mm_wss_raw, default=False)

    _PROJECT_ENV = ProjectEnvConfig(
        database_url=db_url,
        database_host=db_host,
        database_port=db_port,
        database_name=db_name,
        database_user=db_user,
        database_password=db_password,
        log_level=_normalize_level(log_level),
        console_log_level=_normalize_level(console_log_level),
        file_log_level=_normalize_level(file_log_level),
        maim_message_host=mm_host,
        maim_message_port=mm_port,
        maim_message_mode=mm_mode,
        maim_message_use_wss=mm_use_wss,
        defined_keys=defined_keys,
    )

    _set_default_env("DATABASE_URL", _PROJECT_ENV.database_url)
    _set_default_env("DATABASE_HOST", _PROJECT_ENV.database_host)
    _set_default_env("DATABASE_PORT", _PROJECT_ENV.database_port)
    _set_default_env("DATABASE_NAME", _PROJECT_ENV.database_name)
    _set_default_env("DATABASE_USER", _PROJECT_ENV.database_user)
    _set_default_env("DATABASE_PASSWORD", _PROJECT_ENV.database_password)
    _set_default_env("MAIM_MESSAGE_HOST", _PROJECT_ENV.maim_message_host)
    _set_default_env("MAIM_MESSAGE_PORT", _PROJECT_ENV.maim_message_port)
    _set_default_env("MAIM_MESSAGE_MODE", _PROJECT_ENV.maim_message_mode)
    _set_default_env("MAIM_MESSAGE_USE_WSS", str(_PROJECT_ENV.maim_message_use_wss).lower())

    return _PROJECT_ENV


def get_project_env() -> ProjectEnvConfig:
    """Convenience wrapper for callers that only need the cached object."""

    return load_project_env()


def _normalize_level(value: Optional[str]) -> Optional[str]:
    return value.upper() if value else None


def _ensure_env_file() -> None:
    if ENV_FILE.exists():
        return

    if TEMPLATE_ENV_FILE.exists():
        shutil.copyfile(TEMPLATE_ENV_FILE, ENV_FILE)
        print("[env] 未找到 .env，已根据 template.env 自动创建。")
        return

    raise FileNotFoundError(".env 文件不存在，请先创建或提供 template/template.env")


def _set_default_env(key: str, value: Optional[object]) -> None:
    if value is None:
        return
    if key not in os.environ:
        os.environ[key] = str(value)
