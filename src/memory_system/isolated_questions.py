# -*- coding: utf-8 -*-
"""
隔离化问题记录系统
支持T+A+P+C四维隔离的问题和冲突跟踪
"""

import time
import asyncio
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from threading import RLock
import weakref

from src.common.logger import get_logger
from src.common.database.database_model import MemoryConflict
from src.chat.utils.chat_message_builder import (
    get_raw_msg_by_timestamp_with_chat,
    build_readable_messages,
)
from src.llm_models.utils_model import LLMRequest
from src.config.config import model_config
from src.isolation.isolation_context import IsolationContext
from src.memory_system.memory_utils import parse_md_json

from .questions import QuestionTracker

logger = get_logger("isolated_conflict_tracker")


@dataclass
class IsolationScope:
    """隔离范围标识"""

    tenant_id: str
    agent_id: str
    platform: Optional[str] = None
    chat_stream_id: Optional[str] = None

    def __str__(self) -> str:
        """生成隔离范围的字符串表示"""
        components = [self.tenant_id, self.agent_id]
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
        if not isinstance(other, IsolationScope):
            return False
        return str(self) == str(other)


class IsolatedQuestionTracker(QuestionTracker):
    """隔离化问题跟踪器"""

    def __init__(self, question: str, chat_id: str, isolation_context: IsolationContext, context: str = "") -> None:
        # 调用父类初始化
        super().__init__(question, chat_id, context)

        # 扩展隔离上下文
        self.isolation_context = isolation_context
        self.tenant_id = isolation_context.tenant_id
        self.agent_id = isolation_context.agent_id
        self.platform = isolation_context.platform

        # 隔离范围
        self.isolation_scope = IsolationScope(
            tenant_id=self.tenant_id, agent_id=self.agent_id, platform=self.platform, chat_stream_id=chat_id
        )

    def __eq__(self, other) -> bool:
        """比较两个隔离化追踪器是否相等"""
        if not isinstance(other, IsolatedQuestionTracker):
            return False
        return (
            self.question == other.question
            and self.chat_id == other.chat_id
            and self.tenant_id == other.tenant_id
            and self.agent_id == other.agent_id
        )

    def __hash__(self) -> int:
        """为对象提供哈希值，支持集合操作"""
        return hash((self.question, self.chat_id, self.tenant_id, self.agent_id))

    def get_isolation_info(self) -> Dict[str, str]:
        """获取隔离信息"""
        return {
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "platform": self.platform or "",
            "chat_id": self.chat_id,
            "isolation_scope": str(self.isolation_scope),
        }


class IsolatedConflictTracker:
    """
    隔离化记忆整合冲突追踪器

    支持T+A+P+C四维隔离的冲突记录和跟踪
    """

    def __init__(self, isolation_context: IsolationContext):
        self.isolation_context = isolation_context
        self.tenant_id = isolation_context.tenant_id
        self.agent_id = isolation_context.agent_id
        self.platform = isolation_context.platform

        # 隔离范围
        self.isolation_scope = IsolationScope(tenant_id=self.tenant_id, agent_id=self.agent_id, platform=self.platform)

        self.question_tracker_list: List[IsolatedQuestionTracker] = []

        self.LLMRequest_tracker = LLMRequest(
            model_set=model_config.model_task_config.utils,
            request_type="isolated_conflict_tracker",
        )

        logger.info(f"创建隔离化冲突追踪器: {str(self.isolation_scope)}")

    def get_questions_by_chat_id(self, chat_id: str) -> List[IsolatedQuestionTracker]:
        """获取指定聊天ID的问题跟踪器列表"""
        return [
            tracker
            for tracker in self.question_tracker_list
            if tracker.chat_id == chat_id and tracker.tenant_id == self.tenant_id and tracker.agent_id == self.agent_id
        ]

    async def track_conflict(
        self, question: str, context: str = "", start_following: bool = False, chat_id: str = ""
    ) -> bool:
        """
        跟踪冲突内容（隔离化版本）
        """
        try:
            tracker = IsolatedQuestionTracker(question.strip(), chat_id, self.isolation_context, context)
            self.question_tracker_list.append(tracker)

            if start_following and chat_id:
                asyncio.create_task(self._follow_and_record(tracker, question.strip()))
                logger.info(f"开始隔离化冲突跟踪: {question} (范围: {str(self.isolation_scope)})")

            return True

        except Exception as e:
            logger.error(f"隔离化跟踪冲突时出错: {e}")
            return False

    async def record_conflict(
        self, conflict_content: str, context: str = "", start_following: bool = False, chat_id: str = ""
    ) -> bool:
        """
        记录冲突内容（隔离化版本）
        """
        try:
            if not conflict_content or conflict_content.strip() == "":
                return False

            # 若需要跟随后续消息以判断是否得到解答，则进入跟踪流程
            if start_following and chat_id:
                tracker = IsolatedQuestionTracker(conflict_content.strip(), chat_id, self.isolation_context, context)
                self.question_tracker_list.append(tracker)
                # 后台启动跟踪任务，避免阻塞
                asyncio.create_task(self._follow_and_record(tracker, conflict_content.strip()))
                return True

            # 默认：直接记录，不进行跟踪（添加隔离过滤）
            MemoryConflict.create(
                conflict_content=conflict_content,
                create_time=time.time(),
                update_time=time.time(),
                answer="",
                chat_id=chat_id,
                tenant_id=self.tenant_id,  # 添加租户隔离
                agent_id=self.agent_id,  # 添加智能体隔离
                platform=self.platform,  # 添加平台隔离
            )

            logger.info(f"记录隔离冲突内容: {len(conflict_content)} 字符 (范围: {str(self.isolation_scope)})")
            return True

        except Exception as e:
            logger.error(f"记录隔离冲突内容时出错: {e}")
            return False

    async def _follow_and_record(self, tracker: IsolatedQuestionTracker, original_question: str) -> None:
        """
        后台任务：跟踪问题是否被解答，并写入数据库（隔离化版本）
        """
        try:
            max_duration = 10 * 60  # 10 分钟
            max_messages = 50  # 最多 50 条消息
            poll_interval = 2.0  # 秒

            logger.info(f"开始隔离化问题跟踪: {original_question} (范围: {str(self.isolation_scope)})")

            while tracker.active:
                now_ts = time.time()
                # 终止条件：时长达到上限
                if now_ts - tracker.start_time >= max_duration:
                    logger.info("问题跟踪达到10分钟上限，判定为未解答")
                    break

                # 统计最近一段是否有新消息（添加租户过滤）
                recent_msgs = get_raw_msg_by_timestamp_with_chat(
                    chat_id=tracker.chat_id,
                    timestamp_start=tracker.last_read_time,
                    timestamp_end=now_ts,
                    limit=30,
                    limit_mode="latest",
                    filter_bot=False,
                    filter_command=True,
                )

                # 过滤消息以确保属于当前租户和智能体
                filtered_msgs = self._filter_messages_by_isolation(recent_msgs)

                if len(filtered_msgs) > 0:
                    tracker.last_read_time = now_ts

                    # 统计从开始到现在的总消息数
                    all_msgs = get_raw_msg_by_timestamp_with_chat(
                        chat_id=tracker.chat_id,
                        timestamp_start=tracker.start_time,
                        timestamp_end=now_ts,
                        limit=0,
                        limit_mode="latest",
                        filter_bot=False,
                        filter_command=True,
                    )

                    # 过滤所有消息
                    all_filtered_msgs = self._filter_messages_by_isolation(all_msgs)

                    # 检查是否应该进行判定（防抖检查）
                    if not tracker.should_judge_now():
                        logger.debug(f"判定防抖中，跳过本次判定: {tracker.question}")
                        await asyncio.sleep(poll_interval)
                        continue

                    # 构建可读聊天文本
                    chat_text = build_readable_messages(
                        all_filtered_msgs,
                        replace_bot_name=True,
                        timestamp_mode="relative",
                        read_mark=0.0,
                        truncate=False,
                        show_actions=False,
                        show_pic=False,
                        remove_emoji_stickers=True,
                    )
                    chat_len = len(all_filtered_msgs)

                    # 让小模型判断是否有答案
                    answered, answer_text, judge_type = await tracker.judge_answer(chat_text, chat_len)

                    if judge_type == "ANSWERED":
                        # 问题已解答，直接结束跟踪
                        logger.info("问题已得到解答，结束跟踪并写入答案")
                        await self.add_or_update_conflict(
                            conflict_content=tracker.question,
                            create_time=tracker.start_time,
                            update_time=time.time(),
                            answer=answer_text or "",
                            chat_id=tracker.chat_id,
                        )
                        return
                    elif judge_type == "END":
                        # 话题转向，增加END计数
                        tracker.consecutive_end_count += 1
                        logger.info(f"话题已转向，连续END次数: {tracker.consecutive_end_count}")

                        if tracker.consecutive_end_count >= 2:
                            # 连续两次END，结束跟踪
                            logger.info("连续两次END，结束跟踪")
                            break
                        else:
                            # 第一次END，重置计数器并继续跟踪
                            logger.info("第一次END，继续跟踪")
                            continue
                    elif judge_type == "CONTINUE":
                        # 继续跟踪，重置END计数器
                        tracker.consecutive_end_count = 0
                        continue

                    if len(all_filtered_msgs) >= max_messages:
                        logger.info("问题跟踪达到50条消息上限，判定为未解答")
                        logger.info(f"追踪结束：{tracker.question}")
                        break

                # 无新消息时稍作等待
                await asyncio.sleep(poll_interval)

            # 未获取到答案，记录未解答状态
            await self._record_unanswered_question(tracker, original_question)

            logger.info(f"隔离化问题跟踪结束：{original_question}")

        except Exception as e:
            logger.error(f"后台隔离化问题跟踪任务异常: {e}")
        finally:
            # 无论任务成功还是失败，都要从追踪列表中移除
            tracker.stop()
            self.remove_tracker(tracker)

    def _filter_messages_by_isolation(self, messages: List[Any]) -> List[Any]:
        """过滤消息以确保属于当前隔离范围"""
        filtered_messages = []

        for msg in messages:
            try:
                # 这里需要根据实际的消息结构进行过滤
                # 假设消息有tenant_id和agent_id属性，或者可以通过其他方式识别
                # 如果无法识别，则保留消息以确保兼容性

                # 检查消息是否属于当前租户和智能体
                # 这里的实现需要根据实际的消息结构调整
                msg_tenant_id = getattr(msg, "tenant_id", None)
                msg_agent_id = getattr(msg, "agent_id", None)

                # 如果消息有租户和智能体信息，则进行过滤
                if msg_tenant_id and msg_agent_id:
                    if msg_tenant_id == self.tenant_id and msg_agent_id == self.agent_id:
                        filtered_messages.append(msg)
                else:
                    # 如果没有隔离信息，则保留消息（向后兼容）
                    filtered_messages.append(msg)

            except Exception as e:
                logger.warning(f"过滤消息时出错，保留消息: {e}")
                filtered_messages.append(msg)

        return filtered_messages

    async def _record_unanswered_question(self, tracker: IsolatedQuestionTracker, original_question: str):
        """记录未解答的问题"""
        try:
            # 查找现有的冲突记录（添加隔离条件）
            existing_conflict = MemoryConflict.get_or_none(
                (MemoryConflict.conflict_content == original_question)
                & (MemoryConflict.chat_id == tracker.chat_id)
                & (MemoryConflict.tenant_id == self.tenant_id)
                & (MemoryConflict.agent_id == self.agent_id)
            )

            if existing_conflict:
                # 检查raise_time是否大于3且没有答案
                current_raise_time = getattr(existing_conflict, "raise_time", 0) or 0
                if current_raise_time > 0 and not existing_conflict.answer:
                    # 删除该条目
                    await self.delete_conflict(original_question, tracker.chat_id)
                    logger.info(f"追踪结束后删除条目(raise_time={current_raise_time}且无答案): {original_question}")
                else:
                    # 更新记录但不删除
                    await self.add_or_update_conflict(
                        conflict_content=original_question,
                        create_time=existing_conflict.create_time,
                        update_time=time.time(),
                        answer="",
                        chat_id=tracker.chat_id,
                    )
                    logger.info(f"记录隔离冲突内容(未解答): {len(original_question)} 字符")
            else:
                # 如果没有现有记录，创建新记录
                await self.add_or_update_conflict(
                    conflict_content=original_question,
                    create_time=time.time(),
                    update_time=time.time(),
                    answer="",
                    chat_id=tracker.chat_id,
                )
                logger.info(f"记录隔离冲突内容(未解答): {len(original_question)} 字符")

        except Exception as e:
            logger.error(f"记录未解答问题时出错: {e}")

    def remove_tracker(self, tracker: IsolatedQuestionTracker) -> None:
        """从追踪列表中移除指定的追踪器"""
        try:
            if tracker in self.question_tracker_list:
                self.question_tracker_list.remove(tracker)
                logger.info(f"已从隔离追踪列表中移除追踪器: {tracker.question}")
            else:
                logger.warning(f"尝试移除不存在的追踪器: {tracker.question}")
        except Exception as e:
            logger.error(f"移除追踪器时出错: {e}")

    async def add_or_update_conflict(
        self,
        conflict_content: str,
        create_time: float,
        update_time: float,
        answer: str = "",
        context: str = "",
        chat_id: str = None,
    ) -> bool:
        """
        根据conflict_content匹配数据库内容，如果找到相同的就更新update_time和answer，
        如果没有相同的，就新建一条保存全部内容（隔离化版本）
        """
        try:
            # 尝试根据conflict_content查找现有记录（添加隔离条件）
            existing_conflict = MemoryConflict.get_or_none(
                (MemoryConflict.conflict_content == conflict_content)
                & (MemoryConflict.chat_id == chat_id)
                & (MemoryConflict.tenant_id == self.tenant_id)
                & (MemoryConflict.agent_id == self.agent_id)
            )

            if existing_conflict:
                # 如果找到相同的conflict_content，更新update_time和answer
                existing_conflict.update_time = update_time
                existing_conflict.answer = answer
                existing_conflict.save()
                return True
            else:
                # 如果没有找到相同的，创建新记录
                MemoryConflict.create(
                    conflict_content=conflict_content,
                    create_time=create_time,
                    update_time=update_time,
                    answer=answer,
                    context=context,
                    chat_id=chat_id,
                    tenant_id=self.tenant_id,  # 添加租户隔离
                    agent_id=self.agent_id,  # 添加智能体隔离
                    platform=self.platform,  # 添加平台隔离
                )
                return True
        except Exception as e:
            # 记录错误并返回False
            logger.error(f"添加或更新隔离冲突记录时出错: {e}")
            return False

    async def record_memory_merge_conflict(self, part2_content: str, chat_id: str = None) -> bool:
        """
        记录记忆整合过程中的冲突内容（part2）（隔离化版本）
        """
        if not part2_content or part2_content.strip() == "":
            return False

        prompt = f"""以下是一段有冲突的信息，请你根据这些信息总结出几个具体的提问:
冲突信息：
{part2_content}

要求：
1.提问必须具体，明确
2.提问最好涉及指向明确的事物，而不是代称
3.如果缺少上下文，不要强行提问，可以忽略
4.请忽略涉及违法，暴力，色情，政治等敏感话题的内容

请用json格式输出，不要输出其他内容，仅输出提问理由和具体提的提问:
**示例**
// 理由文本
```json
{{
    "question":"提问",
}}
```
```json
{{
    "question":"提问"
}}
```
...提问数量在1-3个之间，不要重复，现在请输出："""

        (
            question_response,
            (reasoning_content, model_name, tool_calls),
        ) = await self.LLMRequest_tracker.generate_response_async(prompt)

        # 解析JSON响应
        questions, reasoning_content = parse_md_json(question_response)

        logger.debug(f"隔离化冲突分析结果: {len(questions)} 个问题")

        for question in questions:
            await self.record_conflict(
                conflict_content=question["question"],
                context=reasoning_content,
                start_following=False,
                chat_id=chat_id,
            )
        return True

    async def get_conflict_count(self) -> int:
        """
        获取隔离范围内的冲突记录数量
        """
        try:
            return (
                MemoryConflict.select()
                .where((MemoryConflict.tenant_id == self.tenant_id) & (MemoryConflict.agent_id == self.agent_id))
                .count()
            )
        except Exception as e:
            logger.error(f"获取隔离冲突记录数量时出错: {e}")
            return 0

    async def delete_conflict(self, conflict_content: str, chat_id: str) -> bool:
        """
        删除指定的冲突记录（隔离化版本）
        """
        try:
            conflict = MemoryConflict.get_or_none(
                (MemoryConflict.conflict_content == conflict_content)
                & (MemoryConflict.chat_id == chat_id)
                & (MemoryConflict.tenant_id == self.tenant_id)
                & (MemoryConflict.agent_id == self.agent_id)
            )

            if conflict:
                conflict.delete_instance()
                logger.info(f"已删除隔离冲突记录: {conflict_content}")
                return True
            else:
                logger.warning(f"未找到要删除的隔离冲突记录: {conflict_content}")
                return False
        except Exception as e:
            logger.error(f"删除隔离冲突记录时出错: {e}")
            return False

    def get_conflict_statistics(self) -> Dict[str, Any]:
        """获取冲突统计信息"""
        try:
            stats = {
                "tenant_id": self.tenant_id,
                "agent_id": self.agent_id,
                "platform": self.platform or "",
                "total_conflicts": 0,
                "active_trackers": len(self.question_tracker_list),
                "answered_conflicts": 0,
                "unanswered_conflicts": 0,
                "chat_streams": set(),
            }

            # 统计冲突记录
            conflicts = MemoryConflict.select().where(
                (MemoryConflict.tenant_id == self.tenant_id) & (MemoryConflict.agent_id == self.agent_id)
            )

            for conflict in conflicts:
                stats["total_conflicts"] += 1

                if conflict.answer:
                    stats["answered_conflicts"] += 1
                else:
                    stats["unanswered_conflicts"] += 1

                if conflict.chat_id:
                    stats["chat_streams"].add(conflict.chat_id)

            # 转换set为list以便JSON序列化
            stats["chat_streams"] = list(stats["chat_streams"])

            return stats

        except Exception as e:
            logger.error(f"获取冲突统计信息时出错: {e}")
            return {}

    def get_isolation_info(self) -> Dict[str, str]:
        """获取隔离信息"""
        return {
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "platform": self.platform or "",
            "isolation_scope": str(self.isolation_scope),
        }


class IsolatedConflictTrackerManager:
    """隔离化冲突追踪器管理器"""

    def __init__(self):
        self._trackers: Dict[str, IsolatedConflictTracker] = {}
        self._lock = RLock()
        self._weak_refs: Dict[str, weakref.ref] = {}

    def get_isolated_conflict_tracker(self, isolation_context: IsolationContext) -> IsolatedConflictTracker:
        """获取隔离化的冲突追踪器实例"""
        scope_key = str(isolation_context.scope)

        with self._lock:
            # 检查弱引用是否仍然有效
            if scope_key in self._weak_refs:
                tracker_ref = self._weak_refs[scope_key]
                tracker = tracker_ref()
                if tracker is not None:
                    return tracker

            # 创建新的实例
            tracker = IsolatedConflictTracker(isolation_context)

            # 使用弱引用存储，避免内存泄漏
            self._weak_refs[scope_key] = weakref.ref(tracker)

            return tracker

    def clear_tenant_trackers(self, tenant_id: str):
        """清理指定租户的冲突追踪器实例"""
        with self._lock:
            keys_to_remove = []
            for key, _ref in self._weak_refs.items():
                if key.startswith(f"{tenant_id}:"):
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                del self._weak_refs[key]

            logger.info(f"已清理租户 {tenant_id} 的所有冲突追踪器实例")

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
        stats = {"active_instances": self.get_active_instance_count(), "conflict_trackers": {}}

        with self._lock:
            for key, ref in self._weak_refs.items():
                tracker = ref()
                if tracker is not None:
                    tracker_stats = tracker.get_conflict_statistics()
                    stats["conflict_trackers"][key] = tracker_stats

        return stats


# 全局隔离化冲突追踪器管理器实例
_global_conflict_manager = IsolatedConflictTrackerManager()


def get_isolated_conflict_tracker(isolation_context: IsolationContext) -> IsolatedConflictTracker:
    """获取隔离化冲突追踪器的便捷函数"""
    return _global_conflict_manager.get_isolated_conflict_tracker(isolation_context)


def get_isolated_conflict_tracker_simple(
    tenant_id: str, agent_id: str, platform: str = None
) -> IsolatedConflictTracker:
    """通过参数创建隔离化冲突追踪器的便捷函数"""
    from src.isolation.isolation_context import create_isolation_context

    context = create_isolation_context(tenant_id, agent_id, platform)
    return get_isolated_conflict_tracker(context)


def clear_isolated_conflict_tracker(tenant_id: str):
    """清理指定租户的冲突追踪器实例"""
    _global_conflict_manager.clear_tenant_trackers(tenant_id)


def get_conflict_system_stats() -> Dict[str, Any]:
    """获取冲突系统统计信息"""
    return _global_conflict_manager.get_system_statistics()
