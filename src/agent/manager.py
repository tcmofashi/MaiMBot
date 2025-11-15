"""Agent manager responsible for synchronising agents between storage and runtime."""

from __future__ import annotations

import json
import os
import datetime
import threading
import weakref
from dataclasses import asdict
from threading import RLock
from typing import Dict, List, Optional

from peewee import DoesNotExist

from src.agent.agent import Agent
from src.agent.loader import load_agents_from_directory
from src.agent.registry import clear_agents, register_agent, get_isolated_registry
from src.common.database.database_model import AgentRecord
from src.common.logger import get_logger
from src.config.official_configs import PersonalityConfig
from src.isolation.isolation_context import create_isolation_context

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
        # 安全解析persona字段，提供默认值以防止JSON解析错误
        # persona字段存储的是纯文本描述，直接构建persona_data对象
        try:
            if not record.persona or record.persona.strip() == "":
                raise ValueError("persona字段为空")

            persona_data = {
                "personality": record.persona.strip(),
                "reply_style": "轻松自然，偶尔会使用一些可爱的表情符号",
                "interest": "音乐、游戏、动漫、日常闲聊",
                "plan_style": "主动参与对话，根据上下文给出合适的回应",
                "visual_style": "",
                "private_plan_style": "私聊中更加亲密和随意",
                "states": ["开心", "平静", "兴奋", "思考"],
                "state_probability": 0.1,
            }
        except (ValueError) as e:
            LOGGER.warning(f"Agent '{record.agent_id}' (租户: {record.tenant_id}) 的persona字段无效，使用默认配置: {e}")
            # 使用默认的persona配置
            persona_data = {
                "personality": f"一个名为{record.name or record.agent_id}的友好AI助手",
                "reply_style": "轻松自然，偶尔会使用一些可爱的表情符号",
                "interest": "音乐、游戏、动漫、日常闲聊",
                "plan_style": "主动参与对话，根据上下文给出合适的回应",
                "visual_style": "",
                "private_plan_style": "私聊中更加亲密和随意",
                "states": ["开心", "平静", "兴奋", "思考"],
                "state_probability": 0.1,
            }

        try:
            persona = PersonalityConfig.from_dict(persona_data)
        except Exception as e:
            LOGGER.error(f"从persona数据创建PersonalityConfig失败，使用默认配置: {e}")
            # 创建基本的PersonalityConfig
            persona = PersonalityConfig(
                personality=persona_data.get("personality", "一个友好的AI助手"),
                reply_style=persona_data.get("reply_style", "自然友好"),
                interest=persona_data.get("interest", "日常闲聊"),
                plan_style=persona_data.get("plan_style", "参与对话"),
            )

        # 安全解析其他JSON字段
        try:
            bot_overrides = json.loads(record.bot_overrides) if record.bot_overrides else {}
        except (json.JSONDecodeError, ValueError) as e:
            LOGGER.warning(f"Agent '{record.agent_id}' 的bot_overrides字段无效，使用空字典: {e}")
            bot_overrides = {}

        try:
            config_overrides = json.loads(record.config_overrides) if record.config_overrides else {}
        except (json.JSONDecodeError, ValueError) as e:
            LOGGER.warning(f"Agent '{record.agent_id}' 的config_overrides字段无效，使用空字典: {e}")
            config_overrides = {}

        try:
            tags = json.loads(record.tags) if record.tags else []
        except (json.JSONDecodeError, ValueError) as e:
            LOGGER.warning(f"Agent '{record.agent_id}' 的tags字段无效，使用空列表: {e}")
            tags = []

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


# ----------------------------------------------------------------------
# 多租户隔离化智能体管理器
# ----------------------------------------------------------------------


class IsolatedAgentManager:
    """支持T+A隔离的智能体管理器。

    负责管理特定租户的智能体定义的持久化和运行时同步。
    """

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self._cache: Dict[str, Agent] = {}
        self._lock = RLock()

        # 集成隔离上下文
        self.isolation_context = create_isolation_context(tenant_id, "system")

        # 获取隔离化的注册中心
        self.registry = get_isolated_registry(tenant_id)

    # ------------------------------------------------------------------
    # Persistence helpers（支持租户隔离）
    # ------------------------------------------------------------------

    def _agent_from_record(self, record: AgentRecord) -> Agent:
        """从数据库记录构建Agent实例（支持多租户）"""
        # 使用persona字段构建persona_data，如果为空则使用默认值
        try:
            if not record.persona or record.persona.strip() == "":
                raise ValueError("persona字段为空")

            # persona字段存储的是纯文本描述，直接构建persona_data对象
            persona_data = {
                "personality": record.persona.strip(),
                "reply_style": "轻松自然，偶尔会使用一些可爱的表情符号",
                "interest": "音乐、游戏、动漫、日常闲聊",
                "plan_style": "主动参与对话，根据上下文给出合适的回应",
                "visual_style": "",
                "private_plan_style": "私聊中更加亲密和随意",
                "states": ["开心", "平静", "兴奋", "思考"],
                "state_probability": 0.1,
            }
        except (ValueError) as e:
            LOGGER.warning(f"租户 '{self.tenant_id}' 的Agent '{record.agent_id}' 的persona字段无效，使用默认配置: {e}")
            # 使用默认的persona配置
            persona_data = {
                "personality": f"一个名为{record.name or record.agent_id}的友好AI助手",
                "reply_style": "轻松自然，偶尔会使用一些可爱的表情符号",
                "interest": "音乐、游戏、动漫、日常闲聊",
                "plan_style": "主动参与对话，根据上下文给出合适的回应",
                "visual_style": "",
                "private_plan_style": "私聊中更加亲密和随意",
                "states": ["开心", "平静", "兴奋", "思考"],
                "state_probability": 0.1,
            }

        try:
            persona = PersonalityConfig.from_dict(persona_data)
        except Exception as e:
            LOGGER.error(f"租户 '{self.tenant_id}' 从persona数据创建PersonalityConfig失败，使用默认配置: {e}")
            # 创建基本的PersonalityConfig
            persona = PersonalityConfig(
                personality=persona_data.get("personality", "一个友好的AI助手"),
                reply_style=persona_data.get("reply_style", "自然友好"),
                interest=persona_data.get("interest", "日常闲聊"),
                plan_style=persona_data.get("plan_style", "参与对话"),
            )

        # 安全解析其他JSON字段
        try:
            bot_overrides = json.loads(record.bot_overrides) if record.bot_overrides else {}
        except (json.JSONDecodeError, ValueError) as e:
            LOGGER.warning(
                f"租户 '{self.tenant_id}' 的Agent '{record.agent_id}' 的bot_overrides字段无效，使用空字典: {e}"
            )
            bot_overrides = {}

        try:
            config_overrides = json.loads(record.config_overrides) if record.config_overrides else {}
        except (json.JSONDecodeError, ValueError) as e:
            LOGGER.warning(
                f"租户 '{self.tenant_id}' 的Agent '{record.agent_id}' 的config_overrides字段无效，使用空字典: {e}"
            )
            config_overrides = {}

        try:
            tags = json.loads(record.tags) if record.tags else []
        except (json.JSONDecodeError, ValueError) as e:
            LOGGER.warning(f"租户 '{self.tenant_id}' 的Agent '{record.agent_id}' 的tags字段无效，使用空列表: {e}")
            tags = []

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
        """将Agent实例转换为数据库记录（支持多租户）"""
        persona_dict = asdict(agent.persona)
        tags_list = list(agent.tags) if agent.tags else []

        return {
            "tenant_id": self.tenant_id,  # 添加租户隔离字段
            "agent_id": agent.agent_id,
            "name": agent.name,
            "description": agent.description,
            "tags": json.dumps(tags_list),
            "persona": json.dumps(persona_dict),
            "bot_overrides": json.dumps(agent.bot_overrides) if agent.bot_overrides else None,
            "config_overrides": json.dumps(agent.config_overrides) if agent.config_overrides else None,
        }

    # ------------------------------------------------------------------
    # Public API（支持租户隔离）
    # ------------------------------------------------------------------

    def sync_from_directory(
        self,
        directory: Optional[str | os.PathLike[str]] = None,
    ) -> List[str]:
        """从配置目录加载智能体定义并持久化（租户隔离）"""

        agents = load_agents_from_directory(directory=directory, auto_register=False)
        stored_ids: List[str] = []

        for agent in agents:
            stored_ids.append(agent.agent_id)
            self.upsert_agent(agent, register=False)

        if stored_ids:
            LOGGER.info(f"租户 '{self.tenant_id}' 已从目录同步 {len(stored_ids)} 个 Agent")

        return stored_ids

    def upsert_agent(self, agent: Agent, *, register: bool = True) -> None:
        """插入或更新智能体定义到数据库（租户隔离）"""

        payload = self._record_from_agent(agent)
        now = datetime.datetime.utcnow()

        # 使用租户隔离的查询条件
        record, created = AgentRecord.get_or_create(
            tenant_id=self.tenant_id,
            agent_id=agent.agent_id,
            defaults={**payload, "created_at": now, "updated_at": now},
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
            self.registry.register(agent)

    def get_agent(self, agent_id: str) -> Optional[Agent]:
        """根据ID获取智能体（租户隔离）"""

        if not agent_id:
            agent_id = "default"

        with self._lock:
            cached = self._cache.get(agent_id)
        if cached is not None:
            return cached

        try:
            # 租户隔离的查询
            record = AgentRecord.get((AgentRecord.tenant_id == self.tenant_id) & (AgentRecord.agent_id == agent_id))
        except DoesNotExist:
            LOGGER.debug(f"租户 '{self.tenant_id}' 数据库中不存在 Agent '{agent_id}'")
            return None

        agent = self._agent_from_record(record)

        with self._lock:
            self._cache[agent_id] = agent

        self.registry.register(agent)
        return agent

    def list_agents(self) -> List[Agent]:
        """返回租户所有智能体"""

        agents: List[Agent] = []
        for record in AgentRecord.select().where(AgentRecord.tenant_id == self.tenant_id):
            agents.append(self._agent_from_record(record))
        return agents

    def refresh_registry(self, *, clear: bool = True) -> int:
        """从数据库注册所有智能体到运行时（租户隔离）"""

        if clear:
            self.registry.clear()

        count = 0
        for agent in self.list_agents():
            self.registry.register(agent)
            with self._lock:
                self._cache[agent.agent_id] = agent
            count += 1
        return count

    def agent_exists(self, agent_id: str) -> bool:
        """检查智能体是否存在于缓存或数据库中（租户隔离）"""

        if not agent_id:
            agent_id = "default"

        with self._lock:
            if agent_id in self._cache:
                return True

        return (
            AgentRecord.select()
            .where((AgentRecord.tenant_id == self.tenant_id) & (AgentRecord.agent_id == agent_id))
            .exists()
        )

    async def initialize(self, directory: Optional[str | os.PathLike[str]] = None) -> int:
        """同步智能体并刷新注册表（租户隔离）"""

        self.sync_from_directory(directory)
        count = self.refresh_registry(clear=True)
        if count == 0:
            LOGGER.warning(f"租户 '{self.tenant_id}' 数据库中未找到任何 Agent，已保持默认配置")
        return count

    # ------------------------------------------------------------------
    # 租户特定方法
    # ------------------------------------------------------------------

    def _load_tenant_agents(self) -> int:
        """加载属于当前租户的智能体"""

        try:
            agent_count = 0
            records = AgentRecord.select().where(AgentRecord.tenant_id == self.tenant_id)

            for record in records:
                agent = self._agent_from_record(record)
                self.registry.register(agent)

                with self._lock:
                    self._cache[agent.agent_id] = agent

                agent_count += 1

            LOGGER.info(f"已为租户 '{self.tenant_id}' 加载 {agent_count} 个智能体")
            return agent_count

        except Exception as e:
            LOGGER.error(f"加载租户 '{self.tenant_id}' 智能体时出错: {e}")
            return 0

    def get_tenant_agent(self, agent_id: str) -> Optional[Agent]:
        """只返回当前租户的智能体"""
        return self.get_agent(agent_id)

    def delete_agent(self, agent_id: str) -> bool:
        """删除租户的智能体"""
        try:
            # 从数据库删除
            deleted_count = (
                AgentRecord.delete()
                .where((AgentRecord.tenant_id == self.tenant_id) & (AgentRecord.agent_id == agent_id))
                .execute()
            )

            if deleted_count > 0:
                # 从缓存删除
                with self._lock:
                    if agent_id in self._cache:
                        del self._cache[agent_id]

                # 从注册表删除
                self.registry.unregister(agent_id)

                LOGGER.info(f"已删除租户 '{self.tenant_id}' 的智能体 '{agent_id}'")
                return True

            return False

        except Exception as e:
            LOGGER.error(f"删除租户 '{self.tenant_id}' 智能体 '{agent_id}' 时出错: {e}")
            return False

    def get_tenant_stats(self) -> Dict[str, any]:
        """获取租户统计信息"""

        try:
            db_count = AgentRecord.select().where(AgentRecord.tenant_id == self.tenant_id).count()
        except Exception:
            db_count = 0

        with self._lock:
            cache_count = len(self._cache)

        registry_count = self.registry.get_agent_count()

        return {
            "tenant_id": self.tenant_id,
            "database_agent_count": db_count,
            "cache_agent_count": cache_count,
            "registry_agent_count": registry_count,
            "isolation_scope": str(self.isolation_context.scope),
        }

    def clear_cache(self):
        """清理缓存"""
        with self._lock:
            self._cache.clear()
        self.registry.clear()
        LOGGER.info(f"已清理租户 '{self.tenant_id}' 的智能体缓存")


class IsolatedAgentManagerManager:
    """隔离化智能体管理器管理器，管理多个租户的管理器实例"""

    def __init__(self):
        self._managers: Dict[str, IsolatedAgentManager] = {}
        self._lock = threading.RLock()
        self._weak_refs: Dict[str, weakref.ref] = {}

    def get_manager(self, tenant_id: str) -> IsolatedAgentManager:
        """获取租户的管理器实例"""

        with self._lock:
            # 检查弱引用是否仍然有效
            if tenant_id in self._weak_refs:
                manager_ref = self._weak_refs[tenant_id]
                manager = manager_ref()
                if manager is not None:
                    return manager

            # 创建新的管理器实例
            manager = IsolatedAgentManager(tenant_id)

            # 使用弱引用存储，避免内存泄漏
            self._managers[tenant_id] = manager
            self._weak_refs[tenant_id] = weakref.ref(manager)

            return manager

    def list_tenant_managers(self) -> List[str]:
        """列出所有租户ID"""

        with self._lock:
            return list(self._managers.keys())

    def clear_tenant_manager(self, tenant_id: str) -> bool:
        """清理指定租户的管理器"""

        with self._lock:
            if tenant_id in self._managers:
                manager = self._managers.get(tenant_id)
                if manager:
                    manager.clear_cache()
                del self._managers[tenant_id]
                if tenant_id in self._weak_refs:
                    del self._weak_refs[tenant_id]
                return True
            return False

    def clear_all_managers(self):
        """清理所有管理器"""

        with self._lock:
            for manager in self._managers.values():
                if manager:
                    manager.clear_cache()
            self._managers.clear()
            self._weak_refs.clear()

    def cleanup_expired_managers(self):
        """清理已过期的管理器引用"""

        with self._lock:
            expired_tenants = []
            for tenant_id, ref in self._weak_refs.items():
                if ref() is None:
                    expired_tenants.append(tenant_id)

            for tenant_id in expired_tenants:
                if tenant_id in self._managers:
                    del self._managers[tenant_id]
                del self._weak_refs[tenant_id]

    def get_manager_stats(self) -> Dict[str, any]:
        """获取管理器统计信息"""

        self.cleanup_expired_managers()

        stats = {"total_tenants": len(self._managers), "managers": {}}

        with self._lock:
            for tenant_id, manager in self._managers.items():
                if manager:
                    stats["managers"][tenant_id] = manager.get_tenant_stats()

        return stats


# 全局隔离化智能体管理器管理器
_isolated_manager_manager = IsolatedAgentManagerManager()


def get_isolated_agent_manager_manager() -> IsolatedAgentManagerManager:
    """获取全局隔离化智能体管理器管理器"""
    return _isolated_manager_manager


def get_isolated_agent_manager(tenant_id: str) -> IsolatedAgentManager:
    """获取指定租户的隔离化智能体管理器"""
    return _isolated_manager_manager.get_manager(tenant_id)


async def initialize_isolated_agent_manager(tenant_id: str, directory: Optional[str | os.PathLike[str]] = None) -> int:
    """初始化指定租户的智能体管理器"""
    manager = get_isolated_agent_manager(tenant_id)
    return await manager.initialize(directory)


def get_isolated_tenant_agent(agent_id: str, tenant_id: str) -> Optional[Agent]:
    """从指定租户获取智能体的便捷函数"""
    manager = get_isolated_agent_manager(tenant_id)
    return manager.get_tenant_agent(agent_id)


def list_isolated_tenant_agents(tenant_id: str) -> List[Agent]:
    """列出指定租户所有智能体的便捷函数"""
    manager = get_isolated_agent_manager(tenant_id)
    return manager.list_agents()


def clear_isolated_agent_manager(tenant_id: str) -> bool:
    """清理指定租户管理器的便捷函数"""
    return _isolated_manager_manager.clear_tenant_manager(tenant_id)


def get_isolated_manager_stats() -> Dict[str, any]:
    """获取隔离化管理器统计信息的便捷函数"""
    return _isolated_manager_manager.get_manager_stats()
