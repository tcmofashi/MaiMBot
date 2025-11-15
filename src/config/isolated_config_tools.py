"""
多租户隔离配置系统工具集
提供配置管理、迁移、验证等工具
"""

import json
import tomlkit
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass

from src.common.logger import get_logger
from src.config.isolated_config_manager import get_isolated_config_manager, clear_isolated_config_manager
from src.config.isolated_config_models import TenantConfig, AgentConfig, PlatformConfig
from src.config.config import global_config

logger = get_logger(__name__)


@dataclass
class ConfigExportItem:
    """配置导出项"""

    tenant_id: str
    agent_id: str
    platform: Optional[str]
    category: str
    key: str
    value: Any
    level: str
    description: Optional[str]
    created_at: datetime


class ConfigMigrationTool:
    """配置迁移工具"""

    @staticmethod
    def migrate_from_global_config(tenant_id: str, agent_id: str, overwrite: bool = False) -> Dict[str, Any]:
        """从全局配置迁移到租户配置"""
        try:
            logger.info(f"Starting migration from global config to {tenant_id}:{agent_id}")

            # 获取隔离配置管理器
            config_manager = get_isolated_config_manager(tenant_id, agent_id)
            migration_stats = {"migrated": 0, "skipped": 0, "errors": 0, "details": []}

            # 遍历全局配置的所有字段
            for field_name in global_config.__dataclass_fields__:
                if field_name.startswith("_"):
                    continue

                try:
                    category_obj = getattr(global_config, field_name)
                    if hasattr(category_obj, "__dataclass_fields__"):
                        # 这是一个配置分类
                        for key in category_obj.__dataclass_fields__:
                            value = getattr(category_obj, key)

                            # 检查是否已存在
                            existing_value = config_manager.get_config(field_name, key)
                            if existing_value is not None and not overwrite:
                                migration_stats["skipped"] += 1
                                migration_stats["details"].append(f"Skipped {field_name}.{key} (already exists)")
                                continue

                            # 迁移配置
                            config_manager.set_config(
                                field_name,
                                key,
                                value,
                                level="agent",
                                description=f"Migrated from global config at {datetime.now()}",
                            )
                            migration_stats["migrated"] += 1
                            migration_stats["details"].append(f"Migrated {field_name}.{key} = {value}")

                except Exception as e:
                    migration_stats["errors"] += 1
                    migration_stats["details"].append(f"Error migrating {field_name}: {str(e)}")
                    logger.error(f"Error migrating config field {field_name}: {e}")

            logger.info(f"Migration completed: {migration_stats}")
            return migration_stats

        except Exception as e:
            logger.error(f"Failed to migrate global config: {e}")
            raise

    @staticmethod
    def migrate_from_file(
        tenant_id: str,
        agent_id: str,
        config_file: str,
        level: str = "agent",
        platform: str = None,
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        """从配置文件迁移"""
        try:
            logger.info(f"Migrating config from file {config_file} to {tenant_id}:{agent_id}")

            config_path = Path(config_file)
            if not config_path.exists():
                raise FileNotFoundError(f"Config file not found: {config_file}")

            # 读取配置文件
            with open(config_path, "r", encoding="utf-8") as f:
                if config_path.suffix == ".toml":
                    config_data = tomlkit.load(f)
                elif config_path.suffix == ".json":
                    config_data = json.load(f)
                else:
                    raise ValueError(f"Unsupported config file format: {config_path.suffix}")

            # 获取配置管理器
            config_manager = get_isolated_config_manager(tenant_id, agent_id)

            migration_stats = {"migrated": 0, "skipped": 0, "errors": 0, "details": []}

            # 迁移配置
            for category, category_data in config_data.items():
                if category in ["inner", "version"]:
                    continue

                if isinstance(category_data, dict):
                    for key, value in category_data.items():
                        try:
                            # 检查是否已存在
                            existing_value = config_manager.get_config(category, key)
                            if existing_value is not None and not overwrite:
                                migration_stats["skipped"] += 1
                                migration_stats["details"].append(f"Skipped {category}.{key} (already exists)")
                                continue

                            # 迁移配置
                            config_manager.set_config(
                                category,
                                key,
                                value,
                                level=level,
                                platform=platform,
                                description=f"Migrated from file {config_file} at {datetime.now()}",
                            )
                            migration_stats["migrated"] += 1
                            migration_stats["details"].append(f"Migrated {category}.{key} = {value}")

                        except Exception as e:
                            migration_stats["errors"] += 1
                            migration_stats["details"].append(f"Error migrating {category}.{key}: {str(e)}")

            logger.info(f"File migration completed: {migration_stats}")
            return migration_stats

        except Exception as e:
            logger.error(f"Failed to migrate from file {config_file}: {e}")
            raise


class ConfigExportImportTool:
    """配置导入导出工具"""

    @staticmethod
    def export_configs(
        tenant_id: str,
        agent_id: str = None,
        platform: str = None,
        categories: List[str] = None,
        include_history: bool = False,
    ) -> Dict[str, Any]:
        """导出配置"""
        try:
            logger.info(f"Exporting configs for {tenant_id}:{agent_id or 'all_agents'}:{platform or 'all_platforms'}")

            export_data = {
                "export_info": {
                    "tenant_id": tenant_id,
                    "agent_id": agent_id,
                    "platform": platform,
                    "categories": categories,
                    "export_time": datetime.now().isoformat(),
                    "version": "1.0",
                },
                "configs": {},
                "history": [] if include_history else None,
            }

            # 获取配置管理器
            config_managers = []
            if agent_id:
                config_managers.append(get_isolated_config_manager(tenant_id, agent_id))
            else:
                # 获取该租户的所有智能体管理器
                # 这里需要遍历数据库获取所有agent_id
                agent_ids = (
                    AgentConfig.select(AgentConfig.agent_id).where(AgentConfig.tenant_id == tenant_id).distinct()
                )

                for agent_record in agent_ids:
                    config_managers.append(get_isolated_config_manager(tenant_id, agent_record.agent_id))

            # 导出配置
            for config_manager in config_managers:
                effective_config = config_manager.get_effective_config(platform)

                # 过滤分类
                if categories:
                    effective_config = {k: v for k, v in effective_config.items() if k in categories}

                # 组织到导出数据中
                agent_key = config_manager.agent_id
                export_data["configs"][agent_key] = effective_config

                # 导出历史记录
                if include_history:
                    history = config_manager.get_config_history(limit=1000)
                    export_data["history"].extend(history)

            logger.info(f"Export completed, {len(export_data['configs'])} agents exported")
            return export_data

        except Exception as e:
            logger.error(f"Failed to export configs: {e}")
            raise

    @staticmethod
    def import_configs(
        export_data: Dict[str, Any], target_tenant_id: str, overwrite: bool = False, create_agents: bool = True
    ) -> Dict[str, Any]:
        """导入配置"""
        try:
            logger.info(f"Importing configs to {target_tenant_id}")

            import_stats = {"imported": 0, "skipped": 0, "errors": 0, "details": []}

            export_info = export_data.get("export_info", {})
            configs = export_data.get("configs", {})

            for agent_id, agent_configs in configs.items():
                try:
                    # 检查智能体是否存在（如果不允许创建）
                    if not create_agents:
                        existing_agents = (
                            AgentConfig.select()
                            .where((AgentConfig.tenant_id == target_tenant_id) & (AgentConfig.agent_id == agent_id))
                            .count()
                        )
                        if existing_agents == 0:
                            import_stats["skipped"] += 1
                            import_stats["details"].append(
                                f"Skipped agent {agent_id} (doesn't exist and create_agents=False)"
                            )
                            continue

                    # 获取配置管理器
                    config_manager = get_isolated_config_manager(target_tenant_id, agent_id)

                    # 导入配置
                    for category, category_configs in agent_configs.items():
                        for key, value in category_configs.items():
                            try:
                                # 检查是否已存在
                                existing_value = config_manager.get_config(category, key)
                                if existing_value is not None and not overwrite:
                                    import_stats["skipped"] += 1
                                    import_stats["details"].append(
                                        f"Skipped {agent_id}:{category}.{key} (already exists)"
                                    )
                                    continue

                                # 导入配置
                                config_manager.set_config(
                                    category,
                                    key,
                                    value,
                                    level="agent",
                                    description=f"Imported from {export_info.get('tenant_id', 'unknown')} at {datetime.now()}",
                                )
                                import_stats["imported"] += 1

                            except Exception as e:
                                import_stats["errors"] += 1
                                import_stats["details"].append(f"Error importing {agent_id}:{category}.{key}: {str(e)}")

                except Exception as e:
                    import_stats["errors"] += 1
                    import_stats["details"].append(f"Error importing agent {agent_id}: {str(e)}")

            logger.info(f"Import completed: {import_stats}")
            return import_stats

        except Exception as e:
            logger.error(f"Failed to import configs: {e}")
            raise


class ConfigValidationTool:
    """配置验证工具"""

    @staticmethod
    def validate_tenant_config(tenant_id: str, agent_id: str = None) -> Dict[str, Any]:
        """验证租户配置完整性"""
        try:
            validation_result = {
                "valid": True,
                "errors": [],
                "warnings": [],
                "missing_configs": [],
                "invalid_configs": [],
            }

            # 定义必需的配置项
            required_configs = {
                "bot": ["platform", "nickname"],
                "personality": ["personality", "reply_style"],
                "chat": ["max_response_length"],
                "message_receive": ["platform"],
            }

            # 定义配置验证规则
            config_validators = {
                "bot.platform": lambda x: isinstance(x, str) and x.strip(),
                "bot.nickname": lambda x: isinstance(x, str) and x.strip(),
                "personality.personality": lambda x: isinstance(x, str) and len(x.strip()) > 10,
                "personality.reply_style": lambda x: isinstance(x, str) and len(x.strip()) > 10,
                "chat.max_response_length": lambda x: isinstance(x, int) and x > 0,
            }

            # 验证每个智能体
            agents_to_check = (
                [agent_id]
                if agent_id
                else [
                    record.agent_id
                    for record in AgentConfig.select(AgentConfig.agent_id)
                    .where(AgentConfig.tenant_id == tenant_id)
                    .distinct()
                ]
            )

            for check_agent_id in agents_to_check:
                config_manager = get_isolated_config_manager(tenant_id, check_agent_id)

                # 检查必需配置
                for category, keys in required_configs.items():
                    for key in keys:
                        value = config_manager.get_config(category, key)
                        if value is None:
                            validation_result["missing_configs"].append(f"{check_agent_id}:{category}.{key}")
                            validation_result["valid"] = False
                        else:
                            # 验证配置值
                            config_key = f"{category}.{key}"
                            if config_key in config_validators:
                                try:
                                    is_valid = config_validators[config_key](value)
                                    if not is_valid:
                                        validation_result["invalid_configs"].append(
                                            f"{check_agent_id}:{config_key} = {value}"
                                        )
                                        validation_result["valid"] = False
                                except Exception as e:
                                    validation_result["errors"].append(
                                        f"Error validating {check_agent_id}:{config_key}: {str(e)}"
                                    )
                                    validation_result["valid"] = False

            return validation_result

        except Exception as e:
            logger.error(f"Failed to validate tenant config: {e}")
            return {"valid": False, "errors": [str(e)], "warnings": [], "missing_configs": [], "invalid_configs": []}

    @staticmethod
    def check_config_consistency(tenant_id: str) -> Dict[str, Any]:
        """检查配置一致性"""
        try:
            consistency_result = {"consistent": True, "issues": [], "recommendations": []}

            # 获取该租户的所有智能体
            agent_ids = [
                record.agent_id
                for record in AgentConfig.select(AgentConfig.agent_id)
                .where(AgentConfig.tenant_id == tenant_id)
                .distinct()
            ]

            if len(agent_ids) <= 1:
                consistency_result["recommendations"].append("Only one agent found, consistency check not applicable")
                return consistency_result

            # 比较关键配置项
            key_configs = ["bot.platform", "message_receive.platform", "chat.max_response_length"]

            config_values = {}

            for agent_id in agent_ids:
                config_manager = get_isolated_config_manager(tenant_id, agent_id)
                config_values[agent_id] = {}

                for config_key in key_configs:
                    category, key = config_key.split(".")
                    value = config_manager.get_config(category, key)
                    config_values[agent_id][config_key] = value

            # 检查一致性
            for config_key in key_configs:
                values = [config_values[agent_id].get(config_key) for agent_id in agent_ids]
                unique_values = set(v for v in values if v is not None)

                if len(unique_values) > 1:
                    consistency_result["consistent"] = False
                    consistency_result["issues"].append(
                        f"Inconsistent {config_key} values: {dict(zip(agent_ids, values, strict=False))}"
                    )

            return consistency_result

        except Exception as e:
            logger.error(f"Failed to check config consistency: {e}")
            return {"consistent": False, "issues": [str(e)], "recommendations": []}


class ConfigManagementTool:
    """配置管理工具"""

    @staticmethod
    def cleanup_expired_configs(tenant_id: str = None, days: int = 30) -> Dict[str, Any]:
        """清理过期配置"""
        try:
            from datetime import timedelta

            cleanup_result = {"cleaned": 0, "errors": 0, "details": []}

            cutoff_date = datetime.now() - timedelta(days=days)

            # 清理过期的配置历史
            history_query = ConfigHistory.delete().where(ConfigHistory.operated_at < cutoff_date)
            if tenant_id:
                history_query = history_query.where(ConfigHistory.tenant_id == tenant_id)

            cleaned_count = history_query.execute()
            cleanup_result["cleaned"] = cleaned_count
            cleanup_result["details"].append(f"Cleaned {cleaned_count} expired history records")

            logger.info(f"Cleanup completed: {cleanup_result}")
            return cleanup_result

        except Exception as e:
            logger.error(f"Failed to cleanup expired configs: {e}")
            return {"cleaned": 0, "errors": 1, "details": [str(e)]}

    @staticmethod
    def get_config_statistics(tenant_id: str = None) -> Dict[str, Any]:
        """获取配置统计信息"""
        try:
            stats = {
                "tenant_configs": 0,
                "agent_configs": 0,
                "platform_configs": 0,
                "tenants": 0,
                "agents": 0,
                "platforms": set(),
                "categories": set(),
            }

            # 统计租户配置
            tenant_query = TenantConfig.select()
            if tenant_id:
                tenant_query = tenant_query.where(TenantConfig.tenant_id == tenant_id)

            stats["tenant_configs"] = tenant_query.count()
            stats["tenants"] = len(set(t.tenant_id for t in tenant_query))

            # 统计智能体配置
            agent_query = AgentConfig.select()
            if tenant_id:
                agent_query = agent_query.where(AgentConfig.tenant_id == tenant_id)

            stats["agent_configs"] = agent_query.count()
            agent_tenants = set()
            for agent in agent_query:
                agent_tenants.add(agent.tenant_id)
                stats["categories"].add(agent.config_category)

            stats["agents"] = len(set(f"{a.tenant_id}:{a.agent_id}" for a in agent_query))

            # 统计平台配置
            platform_query = PlatformConfig.select()
            if tenant_id:
                platform_query = platform_query.where(PlatformConfig.tenant_id == tenant_id)

            stats["platform_configs"] = platform_query.count()
            for platform in platform_query:
                stats["platforms"].add(platform.platform)
                stats["categories"].add(platform.config_category)

            stats["platforms"] = list(stats["platforms"])
            stats["categories"] = list(stats["categories"])

            return stats

        except Exception as e:
            logger.error(f"Failed to get config statistics: {e}")
            return {}

    @staticmethod
    def reset_agent_config(tenant_id: str, agent_id: str, confirm: bool = False) -> Dict[str, Any]:
        """重置智能体配置"""
        if not confirm:
            raise ValueError("Must confirm reset operation by setting confirm=True")

        try:
            reset_result = {"deleted": 0, "errors": 0, "details": []}

            # 删除智能体配置
            agent_deleted = (
                AgentConfig.delete()
                .where((AgentConfig.tenant_id == tenant_id) & (AgentConfig.agent_id == agent_id))
                .execute()
            )

            # 删除平台配置
            platform_deleted = (
                PlatformConfig.delete()
                .where((PlatformConfig.tenant_id == tenant_id) & (PlatformConfig.agent_id == agent_id))
                .execute()
            )

            reset_result["deleted"] = agent_deleted + platform_deleted
            reset_result["details"].append(
                f"Deleted {agent_deleted} agent configs and {platform_deleted} platform configs"
            )

            # 清理配置管理器缓存
            clear_isolated_config_manager(tenant_id, agent_id)

            logger.info(f"Reset completed for {tenant_id}:{agent_id}: {reset_result}")
            return reset_result

        except Exception as e:
            logger.error(f"Failed to reset agent config: {e}")
            return {"deleted": 0, "errors": 1, "details": [str(e)]}


# 便捷函数
def migrate_global_to_tenant(tenant_id: str, agent_id: str, overwrite: bool = False):
    """便捷函数：迁移全局配置到租户"""
    return ConfigMigrationTool.migrate_from_global_config(tenant_id, agent_id, overwrite)


def validate_tenant_configs(tenant_id: str, agent_id: str = None):
    """便捷函数：验证租户配置"""
    return ConfigValidationTool.validate_tenant_config(tenant_id, agent_id)


def export_tenant_configs(tenant_id: str, agent_id: str = None, file_path: str = None):
    """便捷函数：导出租户配置"""
    export_data = ConfigExportImportTool.export_configs(tenant_id, agent_id)

    if file_path:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        logger.info(f"Exported configs to {file_path}")

    return export_data
