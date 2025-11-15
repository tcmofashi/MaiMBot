"""
表情包管理器

支持隔离化的表情包管理，包括表情包的创建、分享和订阅功能，
提供表情包的权限控制和版本管理。
"""

import time
import json
import hashlib
import zipfile
import tempfile
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from pathlib import Path
import threading
from enum import Enum

from src.common.logger import get_logger
from src.common.database.database_model import Emoji
from src.chat.emoji_system.emoji_config import get_emoji_config_manager

logger = get_logger("emoji_pack")


class PackPermission(Enum):
    """表情包权限类型"""

    PUBLIC = "public"  # 公开
    PRIVATE = "private"  # 私有
    TENANT_SHARED = "tenant_shared"  # 租户内共享
    SHARED = "shared"  # 已分享


@dataclass
class EmojiPack:
    """表情包数据结构"""

    pack_id: str
    name: str
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    tags: List[str] = field(default_factory=list)
    emoji_list: List[Dict[str, Any]] = field(default_factory=list)  # 表情包列表
    permission: PackPermission = PackPermission.PRIVATE
    tenant_id: str = ""
    created_time: float = field(default_factory=time.time)
    updated_time: float = field(default_factory=time.time)
    download_count: int = 0
    rating: float = 0.0
    rating_count: int = 0
    file_size: int = 0
    checksum: str = ""


@dataclass
class EmojiPackSubscription:
    """表情包订阅"""

    tenant_id: str
    agent_id: Optional[str]
    pack_id: str
    subscription_time: float = field(default_factory=time.time)
    is_active: bool = True
    auto_update: bool = True
    local_version: str = "1.0.0"


class EmojiPackManager:
    """表情包管理器"""

    def __init__(self, pack_dir: str = "data/emoji_packs"):
        self.pack_dir = Path(pack_dir)
        self.pack_dir.mkdir(parents=True, exist_ok=True)

        # 子目录
        self.public_dir = self.pack_dir / "public"
        self.private_dir = self.pack_dir / "private"
        self.temp_dir = self.pack_dir / "temp"

        for dir_path in [self.public_dir, self.private_dir, self.temp_dir]:
            dir_path.mkdir(exist_ok=True)

        # 内存缓存
        self._packs: Dict[str, EmojiPack] = {}
        self._subscriptions: Dict[str, EmojiPackSubscription] = {}
        self._lock = threading.RLock()

        # 数据文件
        self.packs_file = self.pack_dir / "packs.json"
        self.subscriptions_file = self.pack_dir / "subscriptions.json"

        logger.info(f"初始化表情包管理器: {pack_dir}")

    def initialize(self) -> None:
        """初始化管理器"""
        try:
            self._load_packs()
            self._load_subscriptions()
            self._verify_packs()
            logger.info("表情包管理器初始化完成")
        except Exception as e:
            logger.error(f"表情包管理器初始化失败: {e}")
            raise

    def _load_packs(self) -> None:
        """加载表情包元数据"""
        try:
            if self.packs_file.exists():
                with open(self.packs_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for pack_id, pack_data in data.items():
                        permission = pack_data.get("permission", "private")
                        pack_data["permission"] = PackPermission(permission)
                        self._packs[pack_id] = EmojiPack(**pack_data)
                logger.info(f"加载表情包元数据: {len(self._packs)}个")
        except Exception as e:
            logger.error(f"加载表情包元数据失败: {e}")

    def _load_subscriptions(self) -> None:
        """加载订阅信息"""
        try:
            if self.subscriptions_file.exists():
                with open(self.subscriptions_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for key, sub_data in data.items():
                        self._subscriptions[key] = EmojiPackSubscription(**sub_data)
                logger.info(f"加载订阅信息: {len(self._subscriptions)}个")
        except Exception as e:
            logger.error(f"加载订阅信息失败: {e}")

    def _save_packs(self) -> None:
        """保存表情包元数据"""
        try:
            data = {}
            for pack_id, pack in self._packs.items():
                pack_dict = asdict(pack)
                pack_dict["permission"] = pack.permission.value
                data[pack_id] = pack_dict

            with open(self.packs_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.debug("表情包元数据保存成功")
        except Exception as e:
            logger.error(f"保存表情包元数据失败: {e}")

    def _save_subscriptions(self) -> None:
        """保存订阅信息"""
        try:
            data = {key: asdict(sub) for key, sub in self._subscriptions.items()}

            with open(self.subscriptions_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.debug("订阅信息保存成功")
        except Exception as e:
            logger.error(f"保存订阅信息失败: {e}")

    def _verify_packs(self) -> None:
        """验证表情包文件完整性"""
        try:
            invalid_packs = []

            for pack_id, pack in self._packs.items():
                pack_path = self._get_pack_path(pack)
                if not pack_path.exists():
                    logger.warning(f"表情包文件不存在: {pack_id}")
                    invalid_packs.append(pack_id)
                    continue

                # 验证校验和
                if pack.checksum:
                    calculated_checksum = self._calculate_file_checksum(pack_path)
                    if calculated_checksum != pack.checksum:
                        logger.warning(f"表情包文件校验和不匹配: {pack_id}")
                        invalid_packs.append(pack_id)

            # 移除无效的表情包
            if invalid_packs:
                for pack_id in invalid_packs:
                    del self._packs[pack_id]
                    self._save_packs()
                logger.warning(f"移除无效表情包: {len(invalid_packs)}个")

        except Exception as e:
            logger.error(f"验证表情包失败: {e}")

    def _get_pack_path(self, pack: EmojiPack) -> Path:
        """获取表情包文件路径"""
        if pack.permission == PackPermission.PUBLIC:
            return self.public_dir / f"{pack.pack_id}.zip"
        else:
            return self.private_dir / pack.tenant_id / f"{pack.pack_id}.zip"

    def _calculate_file_checksum(self, file_path: Path) -> str:
        """计算文件校验和"""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def _generate_pack_id(self, name: str, tenant_id: str) -> str:
        """生成表情包ID"""
        timestamp = str(int(time.time()))
        content = f"{name}_{tenant_id}_{timestamp}"
        return hashlib.md5(content.encode()).hexdigest()[:16]

    # ==================== 表情包创建 ====================

    def create_pack(
        self,
        tenant_id: str,
        name: str,
        emoji_hashes: List[str],
        description: str = "",
        tags: List[str] = None,
        permission: PackPermission = PackPermission.PRIVATE,
        author: str = "",
    ) -> Optional[str]:
        """创建表情包"""
        try:
            pack_id = self._generate_pack_id(name, tenant_id)

            # 检查是否已存在
            if pack_id in self._packs:
                logger.warning(f"表情包ID已存在: {pack_id}")
                return None

            # 获取表情包详细信息
            emoji_list = []
            for emoji_hash in emoji_hashes:
                try:
                    # 从数据库获取表情信息
                    emoji_record = Emoji.get_or_none(Emoji.emoji_hash == emoji_hash)
                    if emoji_record:
                        emoji_info = {
                            "hash": emoji_hash,
                            "description": emoji_record.description,
                            "emotion": emoji_record.emotion,
                            "format": emoji_record.format,
                        }
                        emoji_list.append(emoji_info)
                except Exception as e:
                    logger.error(f"获取表情信息失败: {emoji_hash}, {e}")

            if not emoji_list:
                logger.error("没有有效的表情包数据")
                return None

            # 创建表情包对象
            pack = EmojiPack(
                pack_id=pack_id,
                name=name,
                description=description,
                tags=tags or [],
                emoji_list=emoji_list,
                permission=permission,
                tenant_id=tenant_id,
                author=author,
            )

            # 创建表情包文件
            pack_file = self._create_pack_file(pack, emoji_hashes)
            if not pack_file:
                logger.error("创建表情包文件失败")
                return None

            # 更新文件信息
            pack.file_size = pack_file.stat().st_size
            pack.checksum = self._calculate_file_checksum(pack_file)

            # 保存到缓存
            with self._lock:
                self._packs[pack_id] = pack
                self._save_packs()

            logger.info(f"创建表情包成功: {pack_id}")
            return pack_id

        except Exception as e:
            logger.error(f"创建表情包失败: {e}")
            return None

    def _create_pack_file(self, pack: EmojiPack, emoji_hashes: List[str]) -> Optional[Path]:
        """创建表情包文件"""
        try:
            pack_path = self._get_pack_path(pack)

            # 确保目录存在
            pack_path.parent.mkdir(parents=True, exist_ok=True)

            # 创建临时文件
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp_file:
                temp_path = Path(temp_file.name)

            # 创建ZIP文件
            with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as zf:
                # 添加元数据
                metadata = {
                    "pack_id": pack.pack_id,
                    "name": pack.name,
                    "description": pack.description,
                    "version": pack.version,
                    "author": pack.author,
                    "tags": pack.tags,
                    "created_time": pack.created_time,
                    "emoji_list": pack.emoji_list,
                }

                zf.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))

                # 添加表情文件
                for emoji_hash in emoji_hashes:
                    try:
                        emoji_record = Emoji.get_or_none(Emoji.emoji_hash == emoji_hash)
                        if emoji_record and emoji_record.full_path:
                            emoji_path = Path(emoji_record.full_path)
                            if emoji_path.exists():
                                # 在ZIP中使用哈希作为文件名
                                zip_name = f"{emoji_hash}.{emoji_record.format}"
                                zf.write(emoji_path, zip_name)
                                logger.debug(f"添加表情文件: {zip_name}")
                    except Exception as e:
                        logger.error(f"添加表情文件失败: {emoji_hash}, {e}")

            # 移动到目标位置
            temp_path.replace(pack_path)

            logger.info(f"表情包文件创建成功: {pack_path}")
            return pack_path

        except Exception as e:
            logger.error(f"创建表情包文件失败: {e}")
            return None

    # ==================== 表情包管理 ====================

    def get_pack(self, pack_id: str, tenant_id: str = None) -> Optional[EmojiPack]:
        """获取表情包"""
        pack = self._packs.get(pack_id)
        if pack:
            # 权限检查
            if not self._can_access_pack(pack, tenant_id):
                logger.warning(f"无权访问表情包: {pack_id}")
                return None
        return pack

    def list_packs(
        self, tenant_id: str = None, permission: PackPermission = None, tags: List[str] = None, limit: int = 50
    ) -> List[EmojiPack]:
        """列出表情包"""
        packs = []

        for pack in self._packs.values():
            # 权限过滤
            if not self._can_access_pack(pack, tenant_id):
                continue

            # 权限类型过滤
            if permission and pack.permission != permission:
                continue

            # 标签过滤
            if tags and not any(tag in pack.tags for tag in tags):
                continue

            packs.append(pack)

        # 按时间排序并限制数量
        packs.sort(key=lambda p: p.updated_time, reverse=True)
        return packs[:limit]

    def delete_pack(self, pack_id: str, tenant_id: str) -> bool:
        """删除表情包"""
        try:
            pack = self._packs.get(pack_id)
            if not pack:
                logger.warning(f"表情包不存在: {pack_id}")
                return False

            # 权限检查
            if pack.permission != PackPermission.PUBLIC and pack.tenant_id != tenant_id:
                logger.warning(f"无权删除表情包: {pack_id}")
                return False

            # 删除文件
            pack_path = self._get_pack_path(pack)
            if pack_path.exists():
                pack_path.unlink()

            # 从缓存中移除
            with self._lock:
                del self._packs[pack_id]
                self._save_packs()

            logger.info(f"删除表情包成功: {pack_id}")
            return True

        except Exception as e:
            logger.error(f"删除表情包失败: {e}")
            return False

    def _can_access_pack(self, pack: EmojiPack, tenant_id: str = None) -> bool:
        """检查是否可以访问表情包"""
        if pack.permission == PackPermission.PUBLIC:
            return True
        if pack.permission == PackPermission.PRIVATE and pack.tenant_id == tenant_id:
            return True
        if pack.permission == PackPermission.TENANT_SHARED and pack.tenant_id == tenant_id:
            return True
        return False

    # ==================== 表情包分享 ====================

    def share_pack(
        self, pack_id: str, tenant_id: str, target_permission: PackPermission = PackPermission.PUBLIC
    ) -> bool:
        """分享表情包"""
        try:
            pack = self._packs.get(pack_id)
            if not pack:
                logger.warning(f"表情包不存在: {pack_id}")
                return False

            # 权限检查
            if pack.tenant_id != tenant_id:
                logger.warning(f"无权分享表情包: {pack_id}")
                return False

            # 移动文件
            if pack.permission != target_permission:
                old_path = self._get_pack_path(pack)
                pack.permission = target_permission
                new_path = self._get_pack_path(pack)

                if old_path != new_path:
                    new_path.parent.mkdir(parents=True, exist_ok=True)
                    old_path.rename(new_path)

            # 保存更改
            with self._lock:
                self._save_packs()

            logger.info(f"分享表情包成功: {pack_id} -> {target_permission.value}")
            return True

        except Exception as e:
            logger.error(f"分享表情包失败: {e}")
            return False

    # ==================== 表情包订阅 ====================

    def subscribe_pack(self, tenant_id: str, agent_id: Optional[str], pack_id: str, auto_update: bool = True) -> bool:
        """订阅表情包"""
        try:
            pack = self._packs.get(pack_id)
            if not pack:
                logger.warning(f"表情包不存在: {pack_id}")
                return False

            # 权限检查
            if not self._can_access_pack(pack, tenant_id):
                logger.warning(f"无权订阅表情包: {pack_id}")
                return False

            key = f"{tenant_id}:{agent_id or 'system'}:{pack_id}"

            subscription = EmojiPackSubscription(
                tenant_id=tenant_id, agent_id=agent_id, pack_id=pack_id, auto_update=auto_update
            )

            with self._lock:
                self._subscriptions[key] = subscription
                self._save_subscriptions()

            logger.info(f"订阅表情包成功: {key}")
            return True

        except Exception as e:
            logger.error(f"订阅表情包失败: {e}")
            return False

    def unsubscribe_pack(self, tenant_id: str, agent_id: Optional[str], pack_id: str) -> bool:
        """取消订阅表情包"""
        try:
            key = f"{tenant_id}:{agent_id or 'system'}:{pack_id}"

            with self._lock:
                if key in self._subscriptions:
                    del self._subscriptions[key]
                    self._save_subscriptions()
                    logger.info(f"取消订阅表情包成功: {key}")
                    return True
                else:
                    logger.warning(f"订阅记录不存在: {key}")
                    return False

        except Exception as e:
            logger.error(f"取消订阅表情包失败: {e}")
            return False

    def get_subscriptions(self, tenant_id: str, agent_id: Optional[str] = None) -> List[EmojiPackSubscription]:
        """获取订阅列表"""
        subscriptions = []

        for _key, subscription in self._subscriptions.items():
            if subscription.tenant_id == tenant_id:
                if agent_id is None or subscription.agent_id == agent_id:
                    subscriptions.append(subscription)

        return subscriptions

    # ==================== 表情包安装 ====================

    def install_pack_to_collection(
        self, tenant_id: str, agent_id: Optional[str], pack_id: str, collection_name: str = None
    ) -> bool:
        """将表情包安装到集合"""
        try:
            pack = self._packs.get(pack_id)
            if not pack:
                logger.warning(f"表情包不存在: {pack_id}")
                return False

            # 权限检查
            if not self._can_access_pack(pack, tenant_id):
                logger.warning(f"无权安装表情包: {pack_id}")
                return False

            # 解压表情包
            emoji_hashes = self._extract_pack_hashes(pack)
            if not emoji_hashes:
                logger.error("解压表情包失败")
                return False

            # 添加到配置
            config_manager = get_emoji_config_manager()

            if not collection_name:
                collection_name = f"pack_{pack.name}_{pack_id[:8]}"

            success = config_manager.add_emoji_collection(
                tenant_id=tenant_id,
                agent_id=agent_id,
                collection_name=collection_name,
                emoji_hashes=emoji_hashes,
                description=f"从表情包安装: {pack.description}",
                tags=pack.tags,
            )

            if success:
                logger.info(f"安装表情包到集合成功: {collection_name}")
                return True
            else:
                logger.error(f"安装表情包到集合失败: {collection_name}")
                return False

        except Exception as e:
            logger.error(f"安装表情包到集合失败: {e}")
            return False

    def _extract_pack_hashes(self, pack: EmojiPack) -> List[str]:
        """从表情包中提取哈希列表"""
        try:
            pack_path = self._get_pack_path(pack)
            if not pack_path.exists():
                return []

            emoji_hashes = []
            with zipfile.ZipFile(pack_path, "r") as zf:
                # 从元数据中读取
                if "metadata.json" in zf.namelist():
                    with zf.open("metadata.json") as f:
                        metadata = json.load(f)
                        emoji_list = metadata.get("emoji_list", [])
                        emoji_hashes = [emoji["hash"] for emoji in emoji_list]

            return emoji_hashes

        except Exception as e:
            logger.error(f"提取表情包哈希失败: {e}")
            return []

    # ==================== 统计和监控 ====================

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            stats = {
                "total_packs": len(self._packs),
                "public_packs": sum(1 for p in self._packs.values() if p.permission == PackPermission.PUBLIC),
                "private_packs": sum(1 for p in self._packs.values() if p.permission == PackPermission.PRIVATE),
                "total_subscriptions": len(self._subscriptions),
                "total_downloads": sum(p.download_count for p in self._packs.values()),
                "pack_dir": str(self.pack_dir),
            }

            # 按租户统计
            tenant_stats = {}
            for pack in self._packs.values():
                tenant = pack.tenant_id
                if tenant not in tenant_stats:
                    tenant_stats[tenant] = {"packs": 0, "downloads": 0}
                tenant_stats[tenant]["packs"] += 1
                tenant_stats[tenant]["downloads"] += pack.download_count

            stats["tenant_stats"] = tenant_stats
            return stats

    def cleanup_temp_files(self) -> int:
        """清理临时文件"""
        try:
            count = 0
            for temp_file in self.temp_dir.glob("*"):
                if temp_file.is_file():
                    temp_file.unlink()
                    count += 1
            logger.info(f"清理临时文件: {count}个")
            return count
        except Exception as e:
            logger.error(f"清理临时文件失败: {e}")
            return 0


# 全局管理器实例
_emoji_pack_manager: Optional[EmojiPackManager] = None
_pack_lock = threading.Lock()


def get_emoji_pack_manager() -> EmojiPackManager:
    """获取表情包管理器"""
    global _emoji_pack_manager

    if _emoji_pack_manager is None:
        with _pack_lock:
            if _emoji_pack_manager is None:
                _emoji_pack_manager = EmojiPackManager()
                _emoji_pack_manager.initialize()

    return _emoji_pack_manager


# 便捷函数
def create_emoji_pack(
    tenant_id: str,
    name: str,
    emoji_hashes: List[str],
    description: str = "",
    tags: List[str] = None,
    permission: PackPermission = PackPermission.PRIVATE,
) -> Optional[str]:
    """创建表情包"""
    return get_emoji_pack_manager().create_pack(
        tenant_id=tenant_id,
        name=name,
        emoji_hashes=emoji_hashes,
        description=description,
        tags=tags,
        permission=permission,
    )


def subscribe_emoji_pack(tenant_id: str, agent_id: Optional[str], pack_id: str, auto_update: bool = True) -> bool:
    """订阅表情包"""
    return get_emoji_pack_manager().subscribe_pack(
        tenant_id=tenant_id, agent_id=agent_id, pack_id=pack_id, auto_update=auto_update
    )
