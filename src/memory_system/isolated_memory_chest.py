# -*- coding: utf-8 -*-
"""
隔离化记忆系统
支持T+A+P+C四维隔离的记忆存储和管理
"""

import time
import random
import hashlib
from typing import List, Dict, Optional, Tuple, Any
from enum import Enum
from dataclasses import dataclass
from threading import RLock
import weakref

from src.llm_models.utils_model import LLMRequest
from src.config.config import model_config
from src.common.database.database_model import MemoryChest as MemoryChestModel
from src.common.logger import get_logger
from src.config.config import global_config
from src.isolation.isolation_context import IsolationContext

from .memory_utils import (
    find_best_matching_memory,
)

logger = get_logger("isolated_memory")


class MemoryLevel(Enum):
    """记忆级别枚举"""

    AGENT = "agent"  # 智能体级别（基础隔离）
    PLATFORM = "platform"  # 平台级别（可聚合）
    CHAT = "chat"  # 聊天流级别（可分离）


@dataclass
class MemoryScope:
    """记忆范围标识"""

    tenant_id: str
    agent_id: str
    platform: Optional[str] = None
    chat_stream_id: Optional[str] = None
    memory_level: MemoryLevel = MemoryLevel.AGENT

    def __str__(self) -> str:
        """生成记忆范围的字符串表示"""
        components = [self.tenant_id, self.agent_id, self.memory_level.value]
        if self.platform:
            components.append(self.platform)
        if self.chat_stream_id:
            components.append(self.chat_stream_id)
        return ":".join(components)

    def __hash__(self) -> int:
        """支持作为字典键"""
        return hash(str(self))

    def __eq__(self, other) -> bool:
        """支持比较"""
        if not isinstance(other, MemoryScope):
            return False
        return str(self) == str(other)


class MemoryAggregator:
    """记忆聚合器，处理记忆的动态组合和分离"""

    @staticmethod
    async def aggregate_chat_to_platform(
        tenant_id: str, agent_id: str, chat_stream_ids: List[str], platform: str
    ) -> bool:
        """将聊天流记忆聚合到平台级别"""
        try:
            # 查找聊天流级别的记忆
            chat_memories = MemoryChestModel.select().where(
                (MemoryChestModel.tenant_id == tenant_id)
                & (MemoryChestModel.agent_id == agent_id)
                & (MemoryChestModel.platform == platform)
                & (MemoryChestModel.chat_stream_id.in_(chat_stream_ids))
                & (MemoryChestModel.memory_level == MemoryLevel.CHAT.value)
            )

            # 聚合记忆并创建平台级记忆
            aggregated_content = []
            for memory in chat_memories:
                if memory.content and not memory.locked:
                    aggregated_content.append(memory.content)

            if aggregated_content:
                # 创建平台级记忆
                combined_content = "\n".join(aggregated_content)
                MemoryChestModel.create(
                    title=f"平台记忆聚合_{platform}_{int(time.time())}",
                    content=combined_content,
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    platform=platform,
                    chat_stream_id=None,
                    memory_level=MemoryLevel.PLATFORM.value,
                )
                logger.info(f"将 {len(chat_memories)} 条聊天流记忆聚合到平台: {platform}")
                return True

            return False

        except Exception as e:
            logger.error(f"聚合聊天流记忆到平台时出错: {e}")
            return False

    @staticmethod
    async def separate_platform_to_chat(
        tenant_id: str, agent_id: str, platform: str, chat_stream_ids: List[str]
    ) -> bool:
        """将平台记忆分离到聊天流级别"""
        try:
            # 查找平台级别的记忆
            platform_memories = MemoryChestModel.select().where(
                (MemoryChestModel.tenant_id == tenant_id)
                & (MemoryChestModel.agent_id == agent_id)
                & (MemoryChestModel.platform == platform)
                & (MemoryChestModel.chat_stream_id.is_null())
                & (MemoryChestModel.memory_level == MemoryLevel.PLATFORM.value)
            )

            # 为每个聊天流创建记忆副本
            for memory in platform_memories:
                if memory.content and not memory.locked:
                    for chat_id in chat_stream_ids:
                        MemoryChestModel.create(
                            title=f"{memory.title}_{chat_id}",
                            content=memory.content,
                            tenant_id=tenant_id,
                            agent_id=agent_id,
                            platform=platform,
                            chat_stream_id=chat_id,
                            memory_level=MemoryLevel.CHAT.value,
                        )

            if platform_memories.count() > 0:
                logger.info(f"将 {platform_memories.count()} 条平台记忆分离到 {len(chat_stream_ids)} 个聊天流")
                return True

            return False

        except Exception as e:
            logger.error(f"分离平台记忆到聊天流时出错: {e}")
            return False

    @staticmethod
    async def aggregate_platform_to_agent(tenant_id: str, agent_id: str, platforms: List[str]) -> bool:
        """将平台记忆聚合到智能体级别"""
        try:
            # 查找平台级别的记忆
            platform_memories = MemoryChestModel.select().where(
                (MemoryChestModel.tenant_id == tenant_id)
                & (MemoryChestModel.agent_id == agent_id)
                & (MemoryChestModel.platform.in_(platforms))
                & (MemoryChestModel.memory_level == MemoryLevel.PLATFORM.value)
            )

            # 聚合记忆并创建智能体级记忆
            aggregated_content = []
            for memory in platform_memories:
                if memory.content and not memory.locked:
                    aggregated_content.append(memory.content)

            if aggregated_content:
                # 创建智能体级记忆
                combined_content = "\n".join(aggregated_content)
                MemoryChestModel.create(
                    title=f"智能体记忆聚合_{agent_id}_{int(time.time())}",
                    content=combined_content,
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    platform=None,
                    chat_stream_id=None,
                    memory_level=MemoryLevel.AGENT.value,
                )
                logger.info(f"将 {len(platform_memories)} 条平台记忆聚合到智能体: {agent_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"聚合平台记忆到智能体时出错: {e}")
            return False

    @staticmethod
    async def separate_agent_to_platform(tenant_id: str, agent_id: str, platforms: List[str]) -> bool:
        """将智能体记忆分离到平台级别"""
        try:
            # 查找智能体级别的记忆
            agent_memories = MemoryChestModel.select().where(
                (MemoryChestModel.tenant_id == tenant_id)
                & (MemoryChestModel.agent_id == agent_id)
                & (MemoryChestModel.platform.is_null())
                & (MemoryChestModel.chat_stream_id.is_null())
                & (MemoryChestModel.memory_level == MemoryLevel.AGENT.value)
            )

            # 为每个平台创建记忆副本
            for memory in agent_memories:
                if memory.content and not memory.locked:
                    for platform in platforms:
                        MemoryChestModel.create(
                            title=f"{memory.title}_{platform}",
                            content=memory.content,
                            tenant_id=tenant_id,
                            agent_id=agent_id,
                            platform=platform,
                            chat_stream_id=None,
                            memory_level=MemoryLevel.PLATFORM.value,
                        )

            if agent_memories.count() > 0:
                logger.info(f"将 {agent_memories.count()} 条智能体记忆分离到 {len(platforms)} 个平台")
                return True

            return False

        except Exception as e:
            logger.error(f"分离智能体记忆到平台时出错: {e}")
            return False


class IsolatedMemoryChest:
    """隔离化记忆存储系统，支持T+A+P+C四维隔离"""

    def __init__(self, isolation_context: IsolationContext):
        self.isolation_context = isolation_context
        self.tenant_id = isolation_context.tenant_id
        self.agent_id = isolation_context.agent_id
        self.platform = isolation_context.platform
        self.chat_stream_id = isolation_context.chat_stream_id

        # 基础记忆范围（智能体级别）
        self.base_memory_scope = MemoryScope(
            tenant_id=self.tenant_id, agent_id=self.agent_id, memory_level=MemoryLevel.AGENT
        )

        # 创建LLM请求实例
        self.LLMRequest = LLMRequest(
            model_set=model_config.model_task_config.utils_small,
            request_type="isolated_memory_chest",
        )

        self.LLMRequest_build = LLMRequest(
            model_set=model_config.model_task_config.utils,
            request_type="isolated_memory_chest_build",
        )

        # 运行时缓存
        self.running_content_list: Dict[str, Dict[str, Any]] = {}
        self.fetched_memory_list: List[Tuple[str, Tuple[str, str, float]]] = []

        # 记忆缓存
        self._memory_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._cache_lock = RLock()
        self._cache_ttl = 300  # 5分钟缓存

        logger.info(f"创建隔离化记忆系统: {str(self.base_memory_scope)}")

    def get_memory_scope(self, level: MemoryLevel, scope_id: str = None) -> MemoryScope:
        """获取指定级别的记忆范围"""
        if level == MemoryLevel.AGENT:
            return MemoryScope(tenant_id=self.tenant_id, agent_id=self.agent_id, memory_level=level)
        elif level == MemoryLevel.PLATFORM:
            return MemoryScope(
                tenant_id=self.tenant_id, agent_id=self.agent_id, platform=scope_id or self.platform, memory_level=level
            )
        elif level == MemoryLevel.CHAT:
            return MemoryScope(
                tenant_id=self.tenant_id,
                agent_id=self.agent_id,
                platform=self.platform,
                chat_stream_id=scope_id or self.chat_stream_id,
                memory_level=level,
            )
        else:
            raise ValueError(f"不支持的记忆级别: {level}")

    def query_memories(
        self, query_scope: str = "agent", scope_id: str = None, limit: int = 10, exclude_locked: bool = True
    ) -> List[Dict[str, Any]]:
        """查询记忆，支持不同隔离级别"""
        try:
            # 检查缓存
            cache_key = f"{query_scope}:{scope_id}:{limit}:{exclude_locked}"
            cache_time = time.time()

            with self._cache_lock:
                if cache_key in self._memory_cache:
                    cached_data, cached_time = self._memory_cache[cache_key]
                    if cache_time - cached_time < self._cache_ttl:
                        logger.debug(f"使用记忆缓存: {cache_key}")
                        return cached_data

            # 构建查询条件
            level = MemoryLevel(query_scope)
            # memory_scope = self.get_memory_scope(level, scope_id)  # 暂时未使用

            # 构建基本查询条件
            base_conditions = [
                MemoryChestModel.tenant_id == self.tenant_id,
                MemoryChestModel.agent_id == self.agent_id,
                MemoryChestModel.memory_level == level.value,
            ]

            # 添加级别特定的条件
            if level == MemoryLevel.PLATFORM:
                platform_name = scope_id or self.platform
                if platform_name:
                    base_conditions.append(MemoryChestModel.platform == platform_name)
            elif level == MemoryLevel.CHAT:
                chat_id = scope_id or self.chat_stream_id
                if chat_id:
                    base_conditions.append(MemoryChestModel.chat_stream_id == chat_id)

            # 添加锁定过滤条件
            if exclude_locked:
                base_conditions.append(not MemoryChestModel.locked)

            # 执行查询
            query = MemoryChestModel.select().where(*base_conditions).limit(limit)

            memories = []
            for memory in query:
                memories.append(
                    {
                        "id": memory.id,
                        "title": memory.title,
                        "content": memory.content,
                        "chat_stream_id": memory.chat_stream_id,
                        "platform": memory.platform,
                        "memory_level": memory.memory_level,
                        "tenant_id": memory.tenant_id,
                        "agent_id": memory.agent_id,
                        "locked": memory.locked,
                        "create_time": getattr(memory, "create_time", time.time()),
                    }
                )

            # 缓存结果
            with self._cache_lock:
                self._memory_cache[cache_key] = (memories, cache_time)

            logger.debug(f"查询记忆: {query_scope} 范围，找到 {len(memories)} 条记录")
            return memories

        except Exception as e:
            logger.error(f"查询记忆时出错: {e}")
            return []

    def aggregate_memories(self, from_scopes: List[Dict[str, str]], to_scope: Dict[str, str]) -> bool:
        """记忆聚合：从多个子范围聚合到父范围"""
        try:
            to_level = MemoryLevel(to_scope["level"])

            # 收集需要聚合的记忆
            all_memories = []
            for scope_info in from_scopes:
                level = MemoryLevel(scope_info["level"])
                scope_id = scope_info.get("scope_id")
                memories = self.query_memories(level.value, scope_id, limit=100)
                all_memories.extend(memories)

            if not all_memories:
                logger.warning("没有找到需要聚合的记忆")
                return False

            # 聚合记忆内容
            aggregated_content = []
            for memory in all_memories:
                if memory["content"]:
                    aggregated_content.append(memory["content"])

            if not aggregated_content:
                logger.warning("没有有效的记忆内容可以聚合")
                return False

            combined_content = "\n".join(aggregated_content)

            # 创建聚合后的记忆
            to_memory_scope = self.get_memory_scope(to_level, to_scope.get("scope_id"))
            title = f"聚合记忆_{str(to_memory_scope)}_{int(time.time())}"

            MemoryChestModel.create(
                title=title,
                content=combined_content,
                tenant_id=self.tenant_id,
                agent_id=self.agent_id,
                platform=to_scope.get("scope_id") if to_level == MemoryLevel.PLATFORM else None,
                chat_stream_id=to_scope.get("scope_id") if to_level == MemoryLevel.CHAT else None,
                memory_level=to_level.value,
            )

            # 清理缓存
            self._clear_cache()

            logger.info(f"成功聚合 {len(all_memories)} 条记忆到: {str(to_memory_scope)}")
            return True

        except Exception as e:
            logger.error(f"聚合记忆时出错: {e}")
            return False

    def separate_memories(self, from_scope: Dict[str, str], to_scopes: List[Dict[str, str]]) -> bool:
        """记忆分离：从父范围分离到多个子范围"""
        try:
            from_level = MemoryLevel(from_scope["level"])
            scope_id = from_scope.get("scope_id")

            # 获取父范围的记忆
            parent_memories = self.query_memories(from_level.value, scope_id, limit=50)

            if not parent_memories:
                logger.warning("没有找到需要分离的记忆")
                return False

            # 为每个子范围创建记忆副本
            for scope_info in to_scopes:
                to_level = MemoryLevel(scope_info["level"])
                to_scope_id = scope_info.get("scope_id")

                for memory in parent_memories:
                    if memory["content"] and not memory["locked"]:
                        title = f"{memory['title']}_{to_scope_id or 'separated'}"

                        MemoryChestModel.create(
                            title=title,
                            content=memory["content"],
                            tenant_id=self.tenant_id,
                            agent_id=self.agent_id,
                            platform=to_scope_id if to_level == MemoryLevel.PLATFORM else self.platform,
                            chat_stream_id=to_scope_id if to_level == MemoryLevel.CHAT else self.chat_stream_id,
                            memory_level=to_level.value,
                        )

            # 清理缓存
            self._clear_cache()

            logger.info(f"成功分离 {len(parent_memories)} 条记忆到 {len(to_scopes)} 个子范围")
            return True

        except Exception as e:
            logger.error(f"分离记忆时出错: {e}")
            return False

    async def add_memory(
        self, title: str, content: str, memory_context: str = "agent", scope_id: str = None, locked: bool = False
    ) -> str:
        """添加记忆，支持不同上下文级别"""
        try:
            # 生成记忆ID
            if memory_context == "agent":
                memory_level = MemoryLevel.AGENT
                platform = None
                chat_stream_id = None
                # memory_id = self._generate_memory_id(title, memory_level.value)  # 暂时未使用
            elif memory_context.startswith("platform:"):
                memory_level = MemoryLevel.PLATFORM
                platform = scope_id or memory_context.split(":")[1] or self.platform
                chat_stream_id = None
                # memory_id = self._generate_memory_id(title, memory_level.value, platform)  # 暂时未使用
            elif memory_context.startswith("chat:"):
                memory_level = MemoryLevel.CHAT
                platform = self.platform
                chat_stream_id = scope_id or memory_context.split(":")[1] or self.chat_stream_id
                # memory_id = self._generate_memory_id(title, memory_level.value, platform, chat_stream_id)  # 暂时未使用
            else:
                raise ValueError(f"不支持的记忆上下文: {memory_context}")

            # 创建记忆记录
            memory = MemoryChestModel.create(
                title=title,
                content=content,
                tenant_id=self.tenant_id,
                agent_id=self.agent_id,
                platform=platform,
                chat_stream_id=chat_stream_id,
                memory_level=memory_level.value,
                locked=locked,
            )

            # 清理缓存
            self._clear_cache()

            logger.info(f"添加记忆: {title} (级别: {memory_level.value}, ID: {memory.id})")
            return str(memory.id)

        except Exception as e:
            logger.error(f"添加记忆时出错: {e}")
            return ""

    def _generate_memory_id(self, title: str, *components) -> str:
        """生成带隔离上下文的记忆ID"""
        base_components = [self.tenant_id, self.agent_id] + list(components) + [title]
        key = ":".join(base_components)
        return hashlib.sha256(key.encode()).hexdigest()

    def remove_one_memory_by_age_weight(self) -> bool:
        """删除一条记忆：按"越老/越新更易被删"的权重随机选择"""
        try:
            # 在当前智能体的记忆范围内删除
            # filter_dict = {  # 暂时未使用
            #     "tenant_id": self.tenant_id,
            #     "agent_id": self.agent_id
            # }

            memories = list(
                MemoryChestModel.select().where(
                    (MemoryChestModel.tenant_id == self.tenant_id) & (MemoryChestModel.agent_id == self.agent_id)
                )
            )

            if not memories:
                return False

            # 排除锁定项
            candidates = [m for m in memories if not getattr(m, "locked", False)]
            if not candidates:
                return False

            # 按 id 排序，使用 id 近似时间顺序（小 -> 老，大 -> 新）
            candidates.sort(key=lambda m: m.id)
            n = len(candidates)
            if n == 1:
                candidates[0].delete_instance()
                logger.info(f"[隔离记忆管理] 已删除一条记忆(权重抽样)：{candidates[0].title}")
                return True

            # 计算U型权重：中间最低，两端最高
            weights = []
            for idx, _m in enumerate(candidates):
                r = idx / (n - 1)
                w = 0.1 + 0.9 * (abs(r - 0.5) * 2) ** 1.5
                weights.append(w)

            selected = random.choices(candidates, weights=weights, k=1)[0]
            selected.delete_instance()

            # 清理缓存
            self._clear_cache()

            logger.info(f"[隔离记忆管理] 已删除一条记忆(权重抽样)：{selected.title}")
            return True

        except Exception as e:
            logger.error(f"[隔离记忆管理] 按年龄权重删除记忆时出错: {e}")
            return False

    def _clear_cache(self):
        """清理记忆缓存"""
        with self._cache_lock:
            self._memory_cache.clear()

    async def get_answer_by_question(self, chat_id: str = "", question: str = "") -> str:
        """根据问题获取答案"""
        try:
            logger.info(f"正在回忆问题答案: {question}")

            # 使用隔离化的标题选择
            title = await self.select_title_by_question(question)

            if not title:
                return ""

            # 查找匹配的记忆记录
            try:
                memory = (
                    MemoryChestModel.select()
                    .where(
                        (MemoryChestModel.title == title)
                        & (MemoryChestModel.tenant_id == self.tenant_id)
                        & (MemoryChestModel.agent_id == self.agent_id)
                    )
                    .first()
                )

                if not memory:
                    logger.warning(f"未找到记忆: {title}")
                    return ""

                content = memory.content

            except Exception as e:
                logger.error(f"查找记忆时出错: {e}")
                return ""

            if random.random() < 0.5:
                type_desc = "要求原文能够较为全面的回答问题"
            else:
                type_desc = "要求提取简短的内容"

            prompt = f"""
目标文段：
{content}

你现在需要从目标文段中找出合适的信息来回答问题：{question}
请务必从目标文段中提取相关信息的**原文**并输出，{type_desc}
如果没有原文能够回答问题，输出"无有效信息"即可，不要输出其他内容：
"""

            if global_config.debug.show_prompt:
                logger.info(f"隔离记忆仓库获取答案 prompt: {prompt}")
            else:
                logger.debug(f"隔离记忆仓库获取答案 prompt: {prompt}")

            answer, (reasoning_content, model_name, tool_calls) = await self.LLMRequest.generate_response_async(prompt)

            if "无有效" in answer or "无有效信息" in answer or "无信息" in answer:
                logger.info(f"没有能够回答{question}的记忆")
                return ""

            logger.info(f"隔离记忆仓库对问题 '{question}' 获取答案: {answer}")

            # 将问题和答案存到fetched_memory_list
            if chat_id and answer:
                self.fetched_memory_list.append((chat_id, (question, answer, time.time())))

                # 清理fetched_memory_list
                self._cleanup_fetched_memory_list()

            return answer

        except Exception as e:
            logger.error(f"隔离记忆仓库获取答案时出错: {e}")
            return ""

    async def select_title_by_question(self, question: str) -> str:
        """根据问题选择最匹配的标题"""
        try:
            # 获取隔离范围内的所有标题
            titles = self._get_isolated_titles(exclude_locked=True)
            formatted_titles = ""
            for title in titles:
                formatted_titles += f"{title}\n"

            prompt = f"""
所有主题：
{formatted_titles}

请根据以下问题，选择一个能够回答问题的主题：
问题：{question}
请你输出主题，不要输出其他内容，完整输出主题名：
"""

            if global_config.debug.show_prompt:
                logger.info(f"隔离记忆仓库选择标题 prompt: {prompt}")
            else:
                logger.debug(f"隔离记忆仓库选择标题 prompt: {prompt}")

            title, (reasoning_content, model_name, tool_calls) = await self.LLMRequest.generate_response_async(prompt)

            # 使用模糊查找匹配标题
            best_match = find_best_matching_memory(title, similarity_threshold=0.8)
            if best_match:
                selected_title = best_match[0]
                logger.info(f"隔离记忆仓库选择标题: {selected_title} (相似度: {best_match[2]:.3f})")
                return selected_title
            else:
                logger.warning(f"未找到相似度 >= 0.8 的标题匹配: {title}")
                return None

        except Exception as e:
            logger.error(f"隔离记忆仓库选择标题时出错: {e}")
            return ""

    def _get_isolated_titles(self, exclude_locked: bool = False) -> List[str]:
        """获取隔离范围内的所有标题"""
        try:
            titles = []
            memories = MemoryChestModel.select().where(
                (MemoryChestModel.tenant_id == self.tenant_id) & (MemoryChestModel.agent_id == self.agent_id)
            )

            for memory in memories:
                if memory.title:
                    if exclude_locked and memory.locked:
                        continue
                    titles.append(memory.title)
            return titles

        except Exception as e:
            logger.error(f"获取隔离范围内的标题时出错: {e}")
            return []

    def _cleanup_fetched_memory_list(self):
        """清理fetched_memory_list，移除超过10分钟的记忆和超过10条的最旧记忆"""
        try:
            current_time = time.time()
            ten_minutes_ago = current_time - 600  # 10分钟 = 600秒

            # 移除超过10分钟的记忆
            self.fetched_memory_list = [
                (chat_id, (question, answer, timestamp))
                for chat_id, (question, answer, timestamp) in self.fetched_memory_list
                if timestamp > ten_minutes_ago
            ]

            # 如果记忆条数超过10条，移除最旧的5条
            if len(self.fetched_memory_list) > 10:
                # 按时间戳排序，移除最旧的5条
                self.fetched_memory_list.sort(key=lambda x: x[1][2])  # 按timestamp排序
                self.fetched_memory_list = self.fetched_memory_list[5:]  # 保留最新的5条

            logger.debug(f"fetched_memory_list清理后，当前有 {len(self.fetched_memory_list)} 条记忆")

        except Exception as e:
            logger.error(f"清理fetched_memory_list时出错: {e}")

    def get_memory_statistics(self) -> Dict[str, Any]:
        """获取记忆统计信息"""
        try:
            stats = {
                "tenant_id": self.tenant_id,
                "agent_id": self.agent_id,
                "total_count": 0,
                "agent_count": 0,
                "platform_count": 0,
                "chat_count": 0,
                "locked_count": 0,
                "platforms": set(),
                "chat_streams": set(),
            }

            memories = MemoryChestModel.select().where(
                (MemoryChestModel.tenant_id == self.tenant_id) & (MemoryChestModel.agent_id == self.agent_id)
            )

            for memory in memories:
                stats["total_count"] += 1

                if memory.memory_level == MemoryLevel.AGENT.value:
                    stats["agent_count"] += 1
                elif memory.memory_level == MemoryLevel.PLATFORM.value:
                    stats["platform_count"] += 1
                    if memory.platform:
                        stats["platforms"].add(memory.platform)
                elif memory.memory_level == MemoryLevel.CHAT.value:
                    stats["chat_count"] += 1
                    if memory.chat_stream_id:
                        stats["chat_streams"].add(memory.chat_stream_id)

                if memory.locked:
                    stats["locked_count"] += 1

            # 转换set为list以便JSON序列化
            stats["platforms"] = list(stats["platforms"])
            stats["chat_streams"] = list(stats["chat_streams"])

            return stats

        except Exception as e:
            logger.error(f"获取记忆统计信息时出错: {e}")
            return {}

    async def cleanup_expired_memories(self, max_age_days: int = 30) -> int:
        """清理过期记忆"""
        try:
            cutoff_time = time.time() - (max_age_days * 24 * 3600)

            # 查找过期且未锁定的记忆
            expired_memories = (
                MemoryChestModel.select()
                .where(
                    (MemoryChestModel.tenant_id == self.tenant_id)
                    & (MemoryChestModel.agent_id == self.agent_id)
                    & (not MemoryChestModel.locked)
                )
                .where(getattr(MemoryChestModel, "create_time", time.time()) < cutoff_time)
            )

            count = 0
            for memory in expired_memories:
                logger.info(f"清理过期记忆: {memory.title} (ID: {memory.id})")
                memory.delete_instance()
                count += 1

            if count > 0:
                self._clear_cache()
                logger.info(f"已清理 {count} 条过期记忆")

            return count

        except Exception as e:
            logger.error(f"清理过期记忆时出错: {e}")
            return 0

    def get_isolation_info(self) -> Dict[str, str]:
        """获取隔离信息"""
        return {
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "platform": self.platform or "",
            "chat_stream_id": self.chat_stream_id or "",
            "memory_scope": str(self.base_memory_scope),
        }


class IsolatedMemoryChestManager:
    """隔离化记忆系统管理器"""

    def __init__(self):
        self._chests: Dict[str, IsolatedMemoryChest] = {}
        self._lock = RLock()
        self._weak_refs: Dict[str, weakref.ref] = {}

    def get_isolated_memory_chest(self, isolation_context: IsolationContext) -> IsolatedMemoryChest:
        """获取隔离化的记忆系统实例"""
        scope_key = str(isolation_context.scope)

        with self._lock:
            # 检查弱引用是否仍然有效
            if scope_key in self._weak_refs:
                chest_ref = self._weak_refs[scope_key]
                chest = chest_ref()
                if chest is not None:
                    return chest

            # 创建新的实例
            chest = IsolatedMemoryChest(isolation_context)

            # 使用弱引用存储，避免内存泄漏
            self._weak_refs[scope_key] = weakref.ref(chest)

            return chest

    def clear_tenant_memory_chests(self, tenant_id: str):
        """清理指定租户的记忆系统实例"""
        with self._lock:
            keys_to_remove = []
            for key, _ref in self._weak_refs.items():
                if key.startswith(f"{tenant_id}:"):
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                del self._weak_refs[key]

            logger.info(f"已清理租户 {tenant_id} 的所有记忆系统实例")

    def cleanup_expired_instances(self):
        """清理已过期的实例引用"""
        with self._lock:
            expired_keys = []
            for key, ref in self._weak_refs.items():
                if ref() is None:
                    expired_keys.append(key)

            for key in expired_keys:
                del self._weak_refs[key]

    def get_active_instance_count(self) -> int:
        """获取活跃的实例数量"""
        self.cleanup_expired_instances()
        with self._lock:
            return len(self._weak_refs)

    def get_system_statistics(self) -> Dict[str, Any]:
        """获取系统统计信息"""
        stats = {"active_instances": self.get_active_instance_count(), "memory_chests": {}}

        with self._lock:
            for key, ref in self._weak_refs.items():
                chest = ref()
                if chest is not None:
                    chest_stats = chest.get_memory_statistics()
                    stats["memory_chests"][key] = chest_stats

        return stats


# 全局隔离化记忆系统管理器实例
_global_memory_manager = IsolatedMemoryChestManager()


def get_isolated_memory_chest(isolation_context: IsolationContext) -> IsolatedMemoryChest:
    """获取隔离化记忆系统的便捷函数"""
    return _global_memory_manager.get_isolated_memory_chest(isolation_context)


def get_isolated_memory_chest_simple(
    tenant_id: str, agent_id: str, platform: str = None, chat_stream_id: str = None
) -> IsolatedMemoryChest:
    """通过参数创建隔离化记忆系统的便捷函数"""
    from src.isolation.isolation_context import create_isolation_context

    context = create_isolation_context(tenant_id, agent_id, platform, chat_stream_id)
    return get_isolated_memory_chest(context)


def clear_isolated_memory_chest(tenant_id: str):
    """清理指定租户的记忆系统实例"""
    _global_memory_manager.clear_tenant_memory_chests(tenant_id)


def get_memory_system_stats() -> Dict[str, Any]:
    """获取记忆系统统计信息"""
    return _global_memory_manager.get_system_statistics()
