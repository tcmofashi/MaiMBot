from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional

from src.config.config_base import ConfigBase
from src.config.official_configs import BotConfig, PersonalityConfig
from src.config.config import Config


def _deep_merge_dict(base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    """Return a deep-merged copy of *base* with *overrides* applied."""

    result = deepcopy(base)
    for key, value in overrides.items():
        if value is None:
            continue

        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge_dict(result[key], value)
        else:
            result[key] = value

    return result


@dataclass
class Agent(ConfigBase):
    """Represent a persona-aware agent configuration.

    每个 Agent 负责描述一个机器人的人格、身份以及覆盖配置项。
    该类的初衷是为未来的多角色扩展提供统一抽象。
    """

    agent_id: str
    """用于区分不同 Agent 的唯一标识。"""

    name: str
    """Agent 的显示名称，用于界面或日志展示。"""

    persona: PersonalityConfig
    """该 Agent 专属的人格配置。"""

    bot_overrides: Dict[str, Any] = field(default_factory=dict)
    """可选的 bot_config 覆盖项，key 与 ``BotConfig`` 字段保持一致。"""

    config_overrides: Dict[str, Any] = field(default_factory=dict)
    """可选的总配置覆盖项，结构需与 ``Config`` 对应字段一致。"""

    tags: list[str] = field(default_factory=list)
    """额外标签，帮助快速检索或分组。"""

    description: str = ""
    """对 Agent 的简要描述。"""

    _persona_override_fields: Optional[Dict[str, Any]] = field(default=None, init=False, repr=False)

    def build_bot_config(self, base_bot: BotConfig) -> BotConfig:
        """返回应用覆盖后的 ``BotConfig`` 副本。

        该方法不会修改传入的 ``base_bot``，而是返回一个新的 ``BotConfig`` 实例。
        """

        if not isinstance(base_bot, BotConfig):
            raise TypeError("base_bot 必须是 BotConfig 实例")

        merged_data: Dict[str, Any] = asdict(base_bot)
        bot_override_sources = []
        if self.bot_overrides:
            bot_override_sources.append(self.bot_overrides)

        bot_config_override = self.config_overrides.get("bot") if isinstance(self.config_overrides, dict) else None
        if isinstance(bot_config_override, dict):
            bot_override_sources.append(bot_config_override)

        for override in bot_override_sources:
            for key, value in override.items():
                if key not in merged_data or value is None:
                    continue
                merged_data[key] = value

        return BotConfig.from_dict(merged_data)

    def build_config(self, base_config: Config) -> Config:
        """返回应用覆盖后的完整 ``Config`` 副本。"""

        if not isinstance(base_config, Config):
            raise TypeError("base_config 必须是 Config 实例")

        base_dict: Dict[str, Any] = asdict(base_config)
        overrides = self.get_config_overrides()

        if overrides:
            merged_dict = _deep_merge_dict(base_dict, overrides)
        else:
            merged_dict = base_dict

        return Config.from_dict(merged_dict)

    def get_config_overrides(self) -> Dict[str, Any]:
        """获取该 Agent 生成的完整配置覆盖项。"""

        overrides: Dict[str, Any] = {}

        if isinstance(self.config_overrides, dict):
            overrides = deepcopy(self.config_overrides)

        if self.bot_overrides:
            bot_target = overrides.setdefault("bot", {})
            for key, value in self.bot_overrides.items():
                if value is None:
                    continue
                bot_target[key] = value

        persona_override_fields = asdict(self.persona)
        personality_target = overrides.get("personality")
        if not isinstance(personality_target, dict):
            personality_target = {}
        personality_target.update(persona_override_fields)
        overrides["personality"] = personality_target

        return overrides

    def has_override(self, field_name: str) -> bool:
        """检查是否对指定字段进行了覆盖。"""

        return field_name in self.bot_overrides and self.bot_overrides[field_name] is not None

    def get_override(self, field_name: str, default: Any = None) -> Any:
        """读取指定覆盖项。未配置时返回 ``default``。"""

        return self.bot_overrides.get(field_name, default)

    def to_metadata(self) -> Dict[str, Any]:
        """导出该 Agent 的轻量信息，便于记录或展示。"""

        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "tags": list(self.tags),
        }
