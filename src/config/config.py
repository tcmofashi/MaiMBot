import os
import tomlkit
import shutil
import sys
import asyncio
import threading

from collections import OrderedDict
from datetime import datetime
from tomlkit import TOMLDocument
from tomlkit.items import Table, KeyType
from dataclasses import field, dataclass
from rich.traceback import install
from typing import Any, Callable, List, Optional

from src.common.logger import get_logger
from src.common.env_loader import get_project_env
from src.common.toml_utils import format_toml_string
from src.common.message.tenant_context import get_current_agent_id, get_current_tenant_id
from src.config.config_base import ConfigBase
from src.config.official_configs import (
    BotConfig,
    PersonalityConfig,
    ExpressionConfig,
    ChatConfig,
    EmojiConfig,
    KeywordReactionConfig,
    ChineseTypoConfig,
    ResponsePostProcessConfig,
    ResponseSplitterConfig,
    TelemetryConfig,
    ExperimentalConfig,
    MessageReceiveConfig,
    MaimMessageConfig,
    LPMMKnowledgeConfig,
    RelationshipConfig,
    ToolConfig,
    VoiceConfig,
    MoodConfig,
    MemoryConfig,
    DebugConfig,
    JargonConfig,
    DreamConfig,
)

from .api_ada_configs import (
    ModelTaskConfig,
    ModelInfo,
    APIProvider,
)


install(extra_lines=3)


# 配置主程序日志格式
logger = get_logger("config")

# 获取当前文件所在目录的父目录的父目录（即MaiBot项目根目录）
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")
TEMPLATE_DIR = os.path.join(PROJECT_ROOT, "template")

# 考虑到，实际上配置文件中的mai_version是不会自动更新的,所以采用硬编码
# 对该字段的更新，请严格参照语义化版本规范：https://semver.org/lang/zh-CN/
MMC_VERSION = "0.11.7-snapshot.1"


def get_key_comment(toml_table, key):
    # 获取key的注释（如果有）
    if hasattr(toml_table, "trivia") and hasattr(toml_table.trivia, "comment"):
        return toml_table.trivia.comment
    if hasattr(toml_table, "value") and isinstance(toml_table.value, dict):
        item = toml_table.value.get(key)
        if item is not None and hasattr(item, "trivia"):
            return item.trivia.comment
    if hasattr(toml_table, "keys"):
        for k in toml_table.keys():
            if isinstance(k, KeyType) and k.key == key:  # type: ignore
                return k.trivia.comment  # type: ignore
    return None


def compare_dicts(new, old, path=None, logs=None):
    # 递归比较两个dict，找出新增和删减项，收集注释
    if path is None:
        path = []
    if logs is None:
        logs = []
    # 新增项
    for key in new:
        if key == "version":
            continue
        if key not in old:
            comment = get_key_comment(new, key)
            logs.append(f"新增: {'.'.join(path + [str(key)])}  注释: {comment or '无'}")
        elif isinstance(new[key], (dict, Table)) and isinstance(old.get(key), (dict, Table)):
            compare_dicts(new[key], old[key], path + [str(key)], logs)
    # 删减项
    for key in old:
        if key == "version":
            continue
        if key not in new:
            comment = get_key_comment(old, key)
            logs.append(f"删减: {'.'.join(path + [str(key)])}  注释: {comment or '无'}")
    return logs


def get_value_by_path(d, path):
    for k in path:
        if isinstance(d, dict) and k in d:
            d = d[k]
        else:
            return None
    return d


def set_value_by_path(d, path, value):
    """设置嵌套字典中指定路径的值"""
    for k in path[:-1]:
        if k not in d or not isinstance(d[k], dict):
            d[k] = {}
        d = d[k]

    # 使用 tomlkit.item 来保持 TOML 格式
    try:
        d[path[-1]] = tomlkit.item(value)
    except (TypeError, ValueError):
        # 如果转换失败，直接赋值
        d[path[-1]] = value


def compare_default_values(new, old, path=None, logs=None, changes=None):
    # 递归比较两个dict，找出默认值变化项
    if path is None:
        path = []
    if logs is None:
        logs = []
    if changes is None:
        changes = []
    for key in new:
        if key == "version":
            continue
        if key in old:
            if isinstance(new[key], (dict, Table)) and isinstance(old[key], (dict, Table)):
                compare_default_values(new[key], old[key], path + [str(key)], logs, changes)
            elif new[key] != old[key]:
                logs.append(f"默认值变化: {'.'.join(path + [str(key)])}  旧默认值: {old[key]}  新默认值: {new[key]}")
                changes.append((path + [str(key)], old[key], new[key]))
    return logs, changes


def _get_version_from_toml(toml_path) -> str | None:
    """从TOML文件中获取版本号"""
    if not os.path.exists(toml_path):
        return None
    with open(toml_path, "r", encoding="utf-8") as f:
        doc = tomlkit.load(f)
    if "inner" in doc and "version" in doc["inner"]:  # type: ignore
        return doc["inner"]["version"]  # type: ignore
    return None


def _version_tuple(v):
    """将版本字符串转换为元组以便比较"""
    if v is None:
        return (0,)
    return tuple(int(x) if x.isdigit() else 0 for x in str(v).replace("v", "").split("-")[0].split("."))


def _update_dict(target: TOMLDocument | dict | Table, source: TOMLDocument | dict):
    """
    将source字典的值更新到target字典中（如果target中存在相同的键）
    """
    for key, value in source.items():
        # 跳过version字段的更新
        if key == "version":
            continue
        if key in target:
            target_value = target[key]
            if isinstance(value, dict) and isinstance(target_value, (dict, Table)):
                _update_dict(target_value, value)
            else:
                try:
                    # 统一使用 tomlkit.item 来保持原生类型与转义，不对列表做字符串化处理
                    target[key] = tomlkit.item(value)
                except (TypeError, ValueError):
                    # 如果转换失败，直接赋值
                    target[key] = value


def _update_config_generic(config_name: str, template_name: str):
    """
    通用的配置文件更新函数

    Args:
        config_name: 配置文件名（不含扩展名），如 'bot_config' 或 'model_config'
        template_name: 模板文件名（不含扩展名），如 'bot_config_template' 或 'model_config_template'
    """
    # 获取根目录路径
    old_config_dir = os.path.join(CONFIG_DIR, "old")
    compare_dir = os.path.join(TEMPLATE_DIR, "compare")

    # 定义文件路径
    template_path = os.path.join(TEMPLATE_DIR, f"{template_name}.toml")
    old_config_path = os.path.join(CONFIG_DIR, f"{config_name}.toml")
    new_config_path = os.path.join(CONFIG_DIR, f"{config_name}.toml")
    compare_path = os.path.join(compare_dir, f"{template_name}.toml")

    # 创建compare目录（如果不存在）
    os.makedirs(compare_dir, exist_ok=True)

    template_version = _get_version_from_toml(template_path)
    compare_version = _get_version_from_toml(compare_path)

    # 检查配置文件是否存在
    if not os.path.exists(old_config_path):
        logger.info(f"{config_name}.toml配置文件不存在，从模板创建新配置")
        os.makedirs(CONFIG_DIR, exist_ok=True)  # 创建文件夹
        shutil.copy2(template_path, old_config_path)  # 复制模板文件
        logger.info(f"已创建新{config_name}配置文件，请填写后重新运行: {old_config_path}")
        # 新创建配置文件，退出
        sys.exit(0)

    compare_config = None
    new_config = None
    old_config = None

    # 先读取 compare 下的模板（如果有），用于默认值变动检测
    if os.path.exists(compare_path):
        with open(compare_path, "r", encoding="utf-8") as f:
            compare_config = tomlkit.load(f)

    # 读取当前模板
    with open(template_path, "r", encoding="utf-8") as f:
        new_config = tomlkit.load(f)

    # 检查默认值变化并处理（只有 compare_config 存在时才做）
    if compare_config:
        # 读取旧配置
        with open(old_config_path, "r", encoding="utf-8") as f:
            old_config = tomlkit.load(f)
        logs, changes = compare_default_values(new_config, compare_config)
        if logs:
            logger.info(f"检测到{config_name}模板默认值变动如下：")
            for log in logs:
                logger.info(log)
            # 检查旧配置是否等于旧默认值，如果是则更新为新默认值
            config_updated = False
            for path, old_default, new_default in changes:
                old_value = get_value_by_path(old_config, path)
                if old_value == old_default:
                    set_value_by_path(old_config, path, new_default)
                    logger.info(
                        f"已自动将{config_name}配置 {'.'.join(path)} 的值从旧默认值 {old_default} 更新为新默认值 {new_default}"
                    )
                    config_updated = True

            # 如果配置有更新，立即保存到文件
            if config_updated:
                with open(old_config_path, "w", encoding="utf-8") as f:
                    f.write(format_toml_string(old_config))
                logger.info(f"已保存更新后的{config_name}配置文件")
        else:
            logger.info(f"未检测到{config_name}模板默认值变动")

    # 检查 compare 下没有模板，或新模板版本更高，则复制
    if not os.path.exists(compare_path):
        shutil.copy2(template_path, compare_path)
        logger.info(f"已将{config_name}模板文件复制到: {compare_path}")
    elif _version_tuple(template_version) > _version_tuple(compare_version):
        shutil.copy2(template_path, compare_path)
        logger.info(f"{config_name}模板版本较新，已替换compare下的模板: {compare_path}")
    else:
        logger.debug(f"compare下的{config_name}模板版本不低于当前模板，无需替换: {compare_path}")

    # 读取旧配置文件和模板文件（如果前面没读过 old_config，这里再读一次）
    if old_config is None:
        with open(old_config_path, "r", encoding="utf-8") as f:
            old_config = tomlkit.load(f)
    # new_config 已经读取

    # 检查version是否相同
    if old_config and "inner" in old_config and "inner" in new_config:
        old_version = old_config["inner"].get("version")  # type: ignore
        new_version = new_config["inner"].get("version")  # type: ignore
        if old_version and new_version and old_version == new_version:
            logger.info(f"检测到{config_name}配置文件版本号相同 (v{old_version})，跳过更新")
            return
        else:
            logger.info(
                f"\n----------------------------------------\n检测到{config_name}版本号不同: 旧版本 v{old_version} -> 新版本 v{new_version}\n----------------------------------------"
            )
    else:
        logger.info(f"已有{config_name}配置文件未检测到版本号，可能是旧版本。将进行更新")

    # 创建old目录（如果不存在）
    os.makedirs(old_config_dir, exist_ok=True)  # 生成带时间戳的新文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    old_backup_path = os.path.join(old_config_dir, f"{config_name}_{timestamp}.toml")

    # 移动旧配置文件到old目录
    shutil.move(old_config_path, old_backup_path)
    logger.info(f"已备份旧{config_name}配置文件到: {old_backup_path}")

    # 复制模板文件到配置目录
    shutil.copy2(template_path, new_config_path)
    logger.info(f"已创建新{config_name}配置文件: {new_config_path}")

    # 输出新增和删减项及注释
    if old_config:
        logger.info(f"{config_name}配置项变动如下：\n----------------------------------------")
        if logs := compare_dicts(new_config, old_config):
            for log in logs:
                logger.info(log)
        else:
            logger.info("无新增或删减项")

    # 将旧配置的值更新到新配置中
    logger.info(f"开始合并{config_name}新旧配置...")
    _update_dict(new_config, old_config)

    # 保存更新后的配置（保留注释和格式，数组多行格式化）
    with open(new_config_path, "w", encoding="utf-8") as f:
        f.write(format_toml_string(new_config))
    logger.info(f"{config_name}配置文件更新完成，建议检查新配置文件中的内容，以免丢失重要信息")


def update_config():
    """更新bot_config.toml配置文件"""
    _update_config_generic("bot_config", "bot_config_template")


def update_model_config():
    """更新model_config.toml配置文件"""
    _update_config_generic("model_config", "model_config_template")


@dataclass
class Config(ConfigBase):
    """总配置类"""

    MMC_VERSION: str = field(default=MMC_VERSION, repr=False, init=False)  # 硬编码的版本信息

    bot: BotConfig
    personality: PersonalityConfig
    relationship: RelationshipConfig
    chat: ChatConfig
    message_receive: MessageReceiveConfig
    emoji: EmojiConfig
    expression: ExpressionConfig
    keyword_reaction: KeywordReactionConfig
    chinese_typo: ChineseTypoConfig
    response_post_process: ResponsePostProcessConfig
    response_splitter: ResponseSplitterConfig
    telemetry: TelemetryConfig
    experimental: ExperimentalConfig
    maim_message: MaimMessageConfig
    lpmm_knowledge: LPMMKnowledgeConfig
    tool: ToolConfig
    memory: MemoryConfig
    debug: DebugConfig
    mood: MoodConfig
    voice: VoiceConfig
    jargon: JargonConfig
    dream: DreamConfig


@dataclass
class APIAdapterConfig(ConfigBase):
    """API Adapter配置类"""

    models: List[ModelInfo]
    """模型列表"""

    model_task_config: ModelTaskConfig
    """模型任务配置"""

    api_providers: List[APIProvider] = field(default_factory=list)
    """API提供商列表"""

    def __post_init__(self):
        if not self.models:
            raise ValueError("模型列表不能为空，请在配置中设置有效的模型列表。")
        if not self.api_providers:
            raise ValueError("API提供商列表不能为空，请在配置中设置有效的API提供商列表。")

        # 检查API提供商名称是否重复
        provider_names = [provider.name for provider in self.api_providers]
        if len(provider_names) != len(set(provider_names)):
            raise ValueError("API提供商名称存在重复，请检查配置文件。")

        # 检查模型名称是否重复
        model_names = [model.name for model in self.models]
        if len(model_names) != len(set(model_names)):
            raise ValueError("模型名称存在重复，请检查配置文件。")

        self.api_providers_dict = {provider.name: provider for provider in self.api_providers}
        self.models_dict = {model.name: model for model in self.models}

        for model in self.models:
            if not model.model_identifier:
                raise ValueError(f"模型 '{model.name}' 的 model_identifier 不能为空")
            if not model.api_provider or model.api_provider not in self.api_providers_dict:
                raise ValueError(f"模型 '{model.name}' 的 api_provider '{model.api_provider}' 不存在")

    def get_model_info(self, model_name: str) -> ModelInfo:
        """根据模型名称获取模型信息"""
        if not model_name:
            raise ValueError("模型名称不能为空")
        if model_name not in self.models_dict:
            raise KeyError(f"模型 '{model_name}' 不存在")
        return self.models_dict[model_name]

    def get_provider(self, provider_name: str) -> APIProvider:
        """根据提供商名称获取API提供商信息"""
        if not provider_name:
            raise ValueError("API提供商名称不能为空")
        if provider_name not in self.api_providers_dict:
            raise KeyError(f"API提供商 '{provider_name}' 不存在")
        return self.api_providers_dict[provider_name]


GlobalConfig = Config
"""Alias retained for agent配置融合器."""


class _BackgroundAsyncRunner:
    """Runs async loaders inside a dedicated event-loop thread."""

    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop and self._thread and self._thread.is_alive():
                return self._loop

            loop = asyncio.new_event_loop()

            def _run() -> None:
                asyncio.set_event_loop(loop)
                loop.run_forever()

            thread = threading.Thread(target=_run, name="tenant-config-loop", daemon=True)
            thread.start()
            self._loop = loop
            self._thread = thread
            return loop

    def run(self, coro: "asyncio.Future[Any]") -> Any:
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result()


class _LRUCache:
    """Minimal thread-safe LRU cache for agent configs."""

    def __init__(self, maxsize: int = 64):
        self._maxsize = maxsize
        self._data: "OrderedDict[str, Any]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: Optional[str], loader: Callable[[], Any]) -> Any:
        if not key:
            return None
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
                return self._data[key]

        value = loader()
        if value is None:
            return None

        with self._lock:
            self._data[key] = value
            if len(self._data) > self._maxsize:
                self._data.popitem(last=False)
        return value

    def clear(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key:
                self._data.pop(key, None)
            else:
                self._data.clear()


class _TenantConfigProvider:
    """Fetches and caches agent-specific global/model configs."""

    def __init__(self, cache_size: int = 64):
        self._logger = get_logger("tenant_config_provider")
        self._runner = _BackgroundAsyncRunner()
        self._global_cache = _LRUCache(cache_size)
        self._model_cache = _LRUCache(cache_size)
        self._global_factory: Optional[Callable[[str], Any]] = None
        self._model_factory: Optional[Callable[[str], Any]] = None
        self._factory_error_reported = False

    def _build_route_key(self, tenant_id: Optional[str], agent_id: Optional[str]) -> Optional[str]:
        if not tenant_id or not agent_id:
            return None
        return f"{tenant_id}::{agent_id}"

    def _ensure_factories(self) -> bool:
        if self._global_factory and self._model_factory:
            return True
        try:
            from src.common.message.config_merger import create_agent_global_config, create_agent_model_config

            self._global_factory = create_agent_global_config
            self._model_factory = create_agent_model_config
            self._factory_error_reported = False
            return True
        except Exception as exc:  # pragma: no cover - optional dependency guard
            if not self._factory_error_reported:
                self._logger.warning("Tenant config loader unavailable: %s", exc)
                self._factory_error_reported = True
            return False

    def _load_global(self, agent_id: str) -> Any:
        if not self._ensure_factories() or not self._global_factory:
            return None
        try:
            return self._runner.run(self._global_factory(agent_id))
        except Exception as exc:  # pragma: no cover - defensive log
            self._logger.warning("Failed to load agent global_config (%s): %s", agent_id, exc)
            return None

    def _load_model(self, agent_id: str) -> Any:
        if not self._ensure_factories() or not self._model_factory:
            return None
        try:
            return self._runner.run(self._model_factory(agent_id))
        except Exception as exc:  # pragma: no cover - defensive log
            self._logger.warning("Failed to load agent model_config (%s): %s", agent_id, exc)
            return None

    def get_global_config(self, tenant_id: Optional[str], agent_id: Optional[str]) -> Any:
        # Require both tenant and agent context for tenant-aware lookup.
        if not tenant_id or not agent_id:
            raise RuntimeError("Missing tenant_id or agent_id: tenant-aware global config requires both context values")
        key = self._build_route_key(tenant_id, agent_id)
        return self._global_cache.get(key, lambda: self._load_global(agent_id or ""))

    def get_model_config(self, tenant_id: Optional[str], agent_id: Optional[str]) -> Any:
        # Require both tenant and agent context for tenant-aware lookup.
        if not tenant_id or not agent_id:
            raise RuntimeError("Missing tenant_id or agent_id: tenant-aware model config requires both context values")
        key = self._build_route_key(tenant_id, agent_id)
        return self._model_cache.get(key, lambda: self._load_model(agent_id or ""))

    def clear(
        self,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        *,
        config_type: Optional[str] = None,
    ) -> None:
        key = self._build_route_key(tenant_id, agent_id)
        if key is None and not (tenant_id is None and agent_id is None):
            self._logger.debug("skip cache clear due to missing tenant/agent context")
            return
        if config_type in (None, "global"):
            self._global_cache.clear(key)
        if config_type in (None, "model"):
            self._model_cache.clear(key)


_BASIC_VALUE_TYPES = (int, float, bool, str, bytes, type(None))


class _ConfigRuntimeAdapter:
    """Resolves tenant-specific overrides for proxied configs."""

    def __init__(
        self,
        source_label: str,
        fetcher: Callable[[Optional[str], Optional[str]], Any],
        *,
        require_context: bool = True,
    ):
        self._source_label = source_label
        self._fetcher = fetcher
        self._require_context = require_context
        self._logger = get_logger(f"{source_label}_config_proxy")

    def should_override(self, value: Any) -> bool:
        return not isinstance(value, _BASIC_VALUE_TYPES)

    def resolve(self, attr_name: str) -> Any:
        tenant_id = get_current_tenant_id()
        agent_id = get_current_agent_id()
        if not tenant_id or not agent_id:
            if self._require_context:
                raise RuntimeError(
                    "Missing tenant_id or agent_id in context: tenant-aware config access requires both values"
                )
            return None
        config_obj = self._fetcher(tenant_id, agent_id)
        if config_obj is None:
            return None
        try:
            return getattr(config_obj, attr_name)
        except AttributeError:
            self._logger.debug("Attribute %s missing on tenant config", attr_name)
            return None


class _RuntimeAwareConfig(Config):
    """`global_config` wrapper that hooks getattr for tenant overrides."""

    _runtime_proxy: Optional[_ConfigRuntimeAdapter] = None
    _RESERVED = {
        "__dict__",
        "__class__",
        "__annotations__",
        "__dataclass_fields__",
        "__dataclass_params__",
        "__module__",
    }

    def __getattribute__(self, item):  # noqa: D401
        if item.startswith("_") or item in self._RESERVED:
            return super().__getattribute__(item)

        base_value = super().__getattribute__(item)
        proxy = super().__getattribute__("_runtime_proxy")
        if proxy and proxy.should_override(base_value):
            override = proxy.resolve(item)
            if override is not None:
                return override
        return base_value


class _RuntimeAwareAPIAdapterConfig(APIAdapterConfig):
    """`model_config` wrapper with tenant-aware getattr hook."""

    _runtime_proxy: Optional[_ConfigRuntimeAdapter] = None

    def __getattribute__(self, item):  # noqa: D401
        if item.startswith("_"):
            return super().__getattribute__(item)

        base_value = super().__getattribute__(item)
        proxy = super().__getattribute__("_runtime_proxy")
        if proxy and proxy.should_override(base_value):
            override = proxy.resolve(item)
            if override is not None:
                return override
        return base_value


_TENANT_CONFIG_PROVIDER = _TenantConfigProvider()


def load_config(config_path: str) -> Config:
    """
    加载配置文件
    Args:
        config_path: 配置文件路径
    Returns:
        Config对象
    """
    # 读取配置文件
    with open(config_path, "r", encoding="utf-8") as f:
        config_data = tomlkit.load(f)

    # 创建Config对象
    try:
        return Config.from_dict(config_data)
    except Exception as e:
        logger.critical("配置文件解析失败")
        raise e


def api_ada_load_config(config_path: str) -> APIAdapterConfig:
    """
    加载API适配器配置文件
    Args:
        config_path: 配置文件路径
    Returns:
        APIAdapterConfig对象
    """
    # 读取配置文件
    with open(config_path, "r", encoding="utf-8") as f:
        config_data = tomlkit.load(f)

    # 创建APIAdapterConfig对象
    try:
        return APIAdapterConfig.from_dict(config_data)
    except Exception as e:
        logger.critical("API适配器配置文件解析失败")
        raise e


# 获取配置文件路径
logger.info(f"MaiCore当前版本: {MMC_VERSION}")
update_config()
update_model_config()

logger.info("正在品鉴配置文件...")
global_config = load_config(config_path=os.path.join(CONFIG_DIR, "bot_config.toml"))
model_config = api_ada_load_config(config_path=os.path.join(CONFIG_DIR, "model_config.toml"))

_env = get_project_env()
if _env.has("MAIM_MESSAGE_HOST") and _env.maim_message_host:
    global_config.maim_message.host = _env.maim_message_host

if _env.has("MAIM_MESSAGE_PORT") and _env.maim_message_port is not None:
    global_config.maim_message.port = _env.maim_message_port

if _env.has("MAIM_MESSAGE_MODE") and _env.maim_message_mode:
    global_config.maim_message.mode = _env.maim_message_mode

if _env.has("MAIM_MESSAGE_USE_WSS"):
    global_config.maim_message.use_wss = _env.maim_message_use_wss
logger.info("非常的新鲜，非常的美味！")

# 在注入运行时代理之前，保存一份纯净的基础配置副本
# 这份副本包含了环境变量的修改，但没有代理逻辑
# 专门提供给 ConfigMerger 使用，以避免递归死锁
import copy
base_global_config = copy.deepcopy(global_config)
base_model_config = copy.deepcopy(model_config)

try:
    global_config.__class__ = _RuntimeAwareConfig
    global_config._runtime_proxy = _ConfigRuntimeAdapter(
        "global",
        _TENANT_CONFIG_PROVIDER.get_global_config,
        require_context=False,
    )
except Exception as exc:  # pragma: no cover - defensive guard
    logger.warning("无法注入 global_config 运行时代理: %s", exc)

try:
    model_config.__class__ = _RuntimeAwareAPIAdapterConfig
    model_config._runtime_proxy = _ConfigRuntimeAdapter(
        "model",
        _TENANT_CONFIG_PROVIDER.get_model_config,
        require_context=False,
    )
except Exception as exc:  # pragma: no cover - defensive guard
    logger.warning("无法注入 model_config 运行时代理: %s", exc)


def clear_config_runtime_cache(
    agent_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    *,
    config_type: Optional[str] = None,
) -> None:
    """Clear cached tenant configs; useful for tests or manual refresh."""

    _TENANT_CONFIG_PROVIDER.clear(tenant_id, agent_id, config_type=config_type)
