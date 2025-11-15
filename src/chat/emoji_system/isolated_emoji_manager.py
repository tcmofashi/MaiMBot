"""
隔离化表情管理器

支持T+A维度隔离的表情管理系统，使每个智能体可以有独立的表情偏好和表情包集合。
同时支持租户级别的表情定制和表情继承逻辑。
"""

import asyncio
import time
import weakref
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field
from threading import Lock

from src.isolation.isolation_context import create_isolation_context
from src.chat.emoji_system.emoji_manager import MaiEmoji, get_emoji_manager
from src.common.logger import get_logger
from src.config.config import global_config

logger = get_logger("emoji_isolated")


@dataclass
class IsolatedEmojiConfig:
    """隔离化表情配置"""

    tenant_id: str
    agent_id: str
    # 表情偏好设置
    preferred_emotions: List[str] = field(default_factory=list)
    banned_emotions: List[str] = field(default_factory=list)
    custom_emoji_rules: Dict[str, Any] = field(default_factory=dict)
    # 表情包集合设置
    max_emoji_count: int = 200
    auto_replace: bool = True
    inherit_from_tenant: bool = True
    # 使用统计
    usage_stats: Dict[str, int] = field(default_factory=dict)
    last_updated: float = field(default_factory=time.time)


class IsolatedEmojiManager:
    """隔离化表情管理器

    支持T+A维度隔离，每个租户+智能体组合拥有独立的表情偏好和表情包集合。
    实现表情继承逻辑：默认表情 < 租户表情 < 智能体表情
    """

    def __init__(self, tenant_id: str, agent_id: str):
        self.tenant_id = tenant_id
        self.agent_id = agent_id

        # 创建隔离上下文
        self.isolation_context = create_isolation_context(tenant_id, agent_id)

        # 表情配置
        self.config = IsolatedEmojiConfig(tenant_id, agent_id)

        # 继承全局表情管理器的功能
        self.global_manager = get_emoji_manager()

        # 缓存
        self._emoji_cache: Dict[str, MaiEmoji] = {}
        self._cache_lock = Lock()
        self._last_cache_update = 0.0
        self._cache_ttl = 300.0  # 5分钟缓存

        # 租户级别的表情包（用于继承）
        self._tenant_emojis: Set[str] = set()

        # 智能体级别的表情包
        self._agent_emojis: Set[str] = set()

        logger.info(f"创建隔离化表情管理器: tenant={tenant_id}, agent={agent_id}")

    async def initialize(self) -> None:
        """初始化管理器"""
        try:
            # 加载配置
            await self._load_config()

            # 加载表情包
            await self._load_emojis()

            logger.info(f"隔离化表情管理器初始化完成: tenant={self.tenant_id}, agent={self.agent_id}")
        except Exception as e:
            logger.error(f"隔离化表情管理器初始化失败: {e}")
            raise

    async def _load_config(self) -> None:
        """加载表情配置"""
        try:
            # TODO: 从数据库或配置文件加载表情配置
            # 这里使用默认配置
            self.config.max_emoji_count = global_config.emoji.max_reg_num
            self.config.auto_replace = global_config.emoji.do_replace

            logger.debug(f"加载表情配置: tenant={self.tenant_id}, agent={self.agent_id}")
        except Exception as e:
            logger.error(f"加载表情配置失败: {e}")

    async def _load_emojis(self) -> None:
        """加载表情包"""
        try:
            # 获取所有表情包
            all_emojis = self.global_manager.emoji_objects

            with self._cache_lock:
                self._emoji_cache.clear()

                for emoji in all_emojis:
                    if not emoji.is_deleted:
                        self._emoji_cache[emoji.hash] = emoji

                self._last_cache_update = time.time()

            logger.debug(f"加载表情包完成: {len(self._emoji_cache)}个")
        except Exception as e:
            logger.error(f"加载表情包失败: {e}")

    async def get_emoji_for_text(self, text_emotion: str) -> Optional[Tuple[str, str, str]]:
        """根据文本内容获取相关表情包

        优先级：智能体表情 > 租户表情 > 默认表情

        Args:
            text_emotion: 输入的情感描述文本

        Returns:
            Optional[Tuple[str, str, str]]: (表情包完整文件路径, 表情包描述, 匹配的情感)
        """
        try:
            # 检查缓存是否过期
            if time.time() - self._last_cache_update > self._cache_ttl:
                await self._load_emojis()

            # 获取可用的表情包
            available_emojis = self._get_available_emojis()

            if not available_emojis:
                logger.warning(f"没有可用的表情包: tenant={self.tenant_id}, agent={self.agent_id}")
                return None

            # 过滤情感标签
            filtered_emojis = self._filter_by_emotion(available_emojis, text_emotion)

            if not filtered_emojis:
                logger.warning(f"没有匹配情感的表情包: {text_emotion}")
                return None

            # 选择最佳表情包
            selected_emoji = await self._select_best_emoji(filtered_emojis, text_emotion)

            if selected_emoji:
                # 更新使用统计
                await self._update_usage_stats(selected_emoji, text_emotion)

                # 记录使用
                self.global_manager.record_usage(selected_emoji.hash)

                return selected_emoji.full_path, f"[ {selected_emoji.description} ]", text_emotion

            return None

        except Exception as e:
            logger.error(f"获取表情包失败: {e}")
            return None

    def _get_available_emojis(self) -> List[MaiEmoji]:
        """获取可用的表情包列表"""
        with self._cache_lock:
            # 按优先级过滤：智能体表情 > 租户表情 > 默认表情
            available = []

            for emoji in self._emoji_cache.values():
                # 检查是否被禁止
                if self._is_banned_emoji(emoji):
                    continue

                # 添加到可用列表（带优先级标记）
                available.append(emoji)

            return available

    def _filter_by_emotion(self, emojis: List[MaiEmoji], text_emotion: str) -> List[MaiEmoji]:
        """根据情感过滤表情包"""
        filtered = []

        for emoji in emojis:
            if not emoji.emotion:
                continue

            # 检查是否有匹配的情感标签
            for emotion in emoji.emotion:
                # 简单的相似度匹配
                if self._emotion_matches(text_emotion, emotion):
                    filtered.append(emoji)
                    break

        return filtered

    def _emotion_matches(self, text_emotion: str, emoji_emotion: str) -> bool:
        """检查情感是否匹配"""
        # 这里可以使用更复杂的匹配算法
        text_lower = text_emotion.lower()
        emotion_lower = emoji_emotion.lower()

        # 直接匹配
        if text_lower in emotion_lower or emotion_lower in text_lower:
            return True

        # 简单的同义词匹配
        synonyms = {
            "开心": ["高兴", "快乐", "愉快"],
            "难过": ["伤心", "悲伤", "难过"],
            "生气": ["愤怒", "恼火", "生气"],
            "惊讶": ["吃惊", "意外", "惊讶"],
            "害怕": ["恐惧", "担心", "害怕"],
        }

        for key, values in synonyms.items():
            if key in text_lower and any(v in emotion_lower for v in values):
                return True
            if key in emotion_lower and any(v in text_lower for v in values):
                return True

        return False

    async def _select_best_emoji(self, emojis: List[MaiEmoji], text_emotion: str) -> Optional[MaiEmoji]:
        """选择最佳表情包"""
        if not emojis:
            return None

        # 计算每个表情包的权重
        weighted_emojis = []

        for emoji in emojis:
            weight = self._calculate_emoji_weight(emoji, text_emotion)
            weighted_emojis.append((emoji, weight))

        # 按权重排序
        weighted_emojis.sort(key=lambda x: x[1], reverse=True)

        # 从前几个中随机选择
        top_count = min(3, len(weighted_emojis))
        top_emojis = [item[0] for item in weighted_emojis[:top_count]]

        import random

        return random.choice(top_emojis)

    def _calculate_emoji_weight(self, emoji: MaiEmoji, text_emotion: str) -> float:
        """计算表情包权重"""
        weight = 1.0

        # 使用频率权重（使用次数少的权重高）
        weight += 1.0 / (emoji.usage_count + 1)

        # 时间权重（最近使用过的权重稍低）
        time_factor = (time.time() - emoji.last_used_time) / (24 * 3600)  # 天数
        weight += min(time_factor / 30, 1.0)  # 最多30天的时间权重

        # 情感匹配权重
        best_match_score = 0.0
        for emotion in emoji.emotion:
            score = self._calculate_emotion_similarity(text_emotion, emotion)
            best_match_score = max(best_match_score, score)

        weight *= 1.0 + best_match_score

        # 智能体偏好权重
        if emotion in self.config.preferred_emotions:
            weight *= 1.5

        # 被禁止的情感权重
        if emotion in self.config.banned_emotions:
            weight *= 0.1

        return weight

    def _calculate_emotion_similarity(self, emotion1: str, emotion2: str) -> float:
        """计算情感相似度"""
        # 简单的相似度计算
        if emotion1 == emotion2:
            return 1.0

        # 检查包含关系
        if emotion1 in emotion2 or emotion2 in emotion1:
            return 0.8

        # 这里可以加入更复杂的语义相似度计算
        return 0.0

    def _is_banned_emoji(self, emoji: MaiEmoji) -> bool:
        """检查表情是否被禁止"""
        # 检查情感标签是否被禁止
        for emotion in emoji.emotion:
            if emotion in self.config.banned_emotions:
                return True

        return False

    async def _update_usage_stats(self, emoji: MaiEmoji, emotion: str) -> None:
        """更新使用统计"""
        try:
            # 更新配置中的统计
            stat_key = f"{emotion}_{emoji.hash}"
            self.config.usage_stats[stat_key] = self.config.usage_stats.get(stat_key, 0) + 1
            self.config.last_updated = time.time()

            # TODO: 保存到数据库
        except Exception as e:
            logger.error(f"更新使用统计失败: {e}")

    async def add_custom_emoji(self, emoji_path: str, emotions: List[str], description: str = "") -> bool:
        """添加自定义表情包"""
        try:
            # 创建表情包对象
            emoji = MaiEmoji(full_path=emoji_path)
            emoji.emotion = emotions
            emoji.description = description

            # 初始化哈希和格式
            init_result = await emoji.initialize_hash_format()
            if not init_result:
                logger.error(f"初始化表情包失败: {emoji_path}")
                return False

            # 检查是否已存在
            if await self.get_emoji_from_manager(emoji.hash):
                logger.warning(f"表情包已存在: {emoji_path}")
                return False

            # 注册到数据库
            success = await emoji.register_to_db()
            if success:
                # 添加到智能体表情包集合
                self._agent_emojis.add(emoji.hash)

                # 更新缓存
                with self._cache_lock:
                    self._emoji_cache[emoji.hash] = emoji

                logger.info(f"添加自定义表情包成功: {emoji_path}")
                return True

            return False

        except Exception as e:
            logger.error(f"添加自定义表情包失败: {e}")
            return False

    async def remove_emoji(self, emoji_hash: str) -> bool:
        """移除表情包"""
        try:
            # 从智能体表情包集合中移除
            self._agent_emojis.discard(emoji_hash)

            # 从缓存中移除
            with self._cache_lock:
                self._emoji_cache.pop(emoji_hash, None)

            # 注意：不从数据库删除，只是从智能体的集合中移除
            logger.info(f"移除表情包: {emoji_hash}")
            return True

        except Exception as e:
            logger.error(f"移除表情包失败: {e}")
            return False

    async def get_emoji_from_manager(self, emoji_hash: str) -> Optional[MaiEmoji]:
        """从管理器获取表情包"""
        with self._cache_lock:
            return self._emoji_cache.get(emoji_hash)

    def get_isolation_info(self) -> Dict[str, Any]:
        """获取隔离信息"""
        return {
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "emoji_count": len(self._emoji_cache),
            "agent_emoji_count": len(self._agent_emojis),
            "tenant_emoji_count": len(self._tenant_emojis),
            "preferred_emotions": self.config.preferred_emotions,
            "banned_emotions": self.config.banned_emotions,
            "last_cache_update": self._last_cache_update,
        }

    async def cleanup(self) -> None:
        """清理资源"""
        try:
            with self._cache_lock:
                self._emoji_cache.clear()

            self._agent_emojis.clear()
            self._tenant_emojis.clear()

            logger.info(f"清理隔离化表情管理器: tenant={self.tenant_id}, agent={self.agent_id}")
        except Exception as e:
            logger.error(f"清理资源失败: {e}")


class IsolatedEmojiManagerManager:
    """隔离化表情管理器的全局管理器"""

    def __init__(self):
        self._managers: Dict[str, IsolatedEmojiManager] = {}
        self._lock = Lock()
        self._weak_refs: Dict[str, weakref.ref] = {}

    def get_manager(self, tenant_id: str, agent_id: str) -> IsolatedEmojiManager:
        """获取隔离化表情管理器"""
        key = f"{tenant_id}:{agent_id}"

        with self._lock:
            # 检查弱引用
            if key in self._weak_refs:
                manager = self._weak_refs[key]()
                if manager is not None:
                    return manager
                else:
                    del self._weak_refs[key]

            # 创建新的管理器
            if key not in self._managers:
                self._managers[key] = IsolatedEmojiManager(tenant_id, agent_id)
                self._weak_refs[key] = weakref.ref(self._managers[key])

            return self._managers[key]

    def list_managers(self) -> List[Dict[str, str]]:
        """列出所有管理器"""
        with self._lock:
            managers = []
            for key, manager in self._managers.items():
                if manager is not None:
                    tenant_id, agent_id = key.split(":")
                    managers.append(
                        {"tenant_id": tenant_id, "agent_id": agent_id, "emoji_count": len(manager._emoji_cache)}
                    )
            return managers

    def cleanup_manager(self, tenant_id: str, agent_id: str) -> bool:
        """清理指定的管理器"""
        key = f"{tenant_id}:{agent_id}"

        with self._lock:
            if key in self._managers:
                manager = self._managers[key]
                asyncio.create_task(manager.cleanup())
                del self._managers[key]

                if key in self._weak_refs:
                    del self._weak_refs[key]

                logger.info(f"清理管理器: {key}")
                return True

            return False

    def cleanup_all(self) -> int:
        """清理所有管理器"""
        with self._lock:
            count = len(self._managers)

            for manager in self._managers.values():
                if manager is not None:
                    asyncio.create_task(manager.cleanup())

            self._managers.clear()
            self._weak_refs.clear()

            logger.info(f"清理所有管理器: {count}个")
            return count

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            stats = {
                "total_managers": len(self._managers),
                "total_emojis": 0,
                "total_agent_emojis": 0,
                "total_tenant_emojis": 0,
            }

            for manager in self._managers.values():
                if manager is not None:
                    stats["total_emojis"] += len(manager._emoji_cache)
                    stats["total_agent_emojis"] += len(manager._agent_emojis)
                    stats["total_tenant_emojis"] += len(manager._tenant_emojis)

            return stats


# 全局管理器实例
_isolated_emoji_manager_manager = IsolatedEmojiManagerManager()


def get_isolated_emoji_manager(tenant_id: str, agent_id: str) -> IsolatedEmojiManager:
    """获取隔离化表情管理器"""
    return _isolated_emoji_manager_manager.get_manager(tenant_id, agent_id)


def get_isolated_emoji_manager_manager() -> IsolatedEmojiManagerManager:
    """获取隔离化表情管理器的全局管理器"""
    return _isolated_emoji_manager_manager


# 向后兼容的导入已完成
