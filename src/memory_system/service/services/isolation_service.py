"""
记忆服务的隔离服务

提供T+A+P+C四维隔离的验证和管理功能。
"""

import logging
from typing import Dict, Any, Optional, List
from fastapi import Request

from ..utils.isolation import IsolationContext, get_isolation_context_from_request, isolation_validator

logger = logging.getLogger(__name__)


class IsolationService:
    """隔离服务类"""

    def __init__(self):
        self.validator = isolation_validator

    async def validate_memory_access(
        self,
        isolation_context: IsolationContext,
        level: Optional[str] = None,
        platform: Optional[str] = None,
        scope_id: Optional[str] = None,
        memory_id: Optional[str] = None,
    ) -> bool:
        """
        验证记忆访问权限

        Args:
            isolation_context: 当前隔离上下文
            level: 记忆级别
            platform: 平台标识
            scope_id: 作用域ID
            memory_id: 记忆ID

        Returns:
            是否有访问权限
        """
        try:
            # 验证租户权限
            if not await self.validator.validate_tenant(isolation_context.tenant_id):
                logger.warning(f"租户权限验证失败: {isolation_context.tenant_id}")
                return False

            # 验证智能体权限
            if not await self.validator.validate_agent(isolation_context.tenant_id, isolation_context.agent_id):
                logger.warning(f"智能体权限验证失败: {isolation_context.tenant_id}:{isolation_context.agent_id}")
                return False

            # 验证平台权限（如果指定）
            if platform and not await self.validator.validate_platform(platform):
                logger.warning(f"平台权限验证失败: {platform}")
                return False

            # 检查级别兼容性
            if level and not self._is_level_compatible(isolation_context, level):
                logger.warning(f"记忆级别不兼容: {level}")
                return False

            # 检查平台兼容性
            if platform and isolation_context.platform and platform != isolation_context.platform:
                logger.warning(f"平台不兼容: {platform} vs {isolation_context.platform}")
                return False

            # 检查作用域兼容性
            if scope_id and isolation_context.scope_id and scope_id != isolation_context.scope_id:
                # 只有高级别访问低级别时才允许
                if not self._can_access_cross_scope(isolation_context, scope_id):
                    logger.warning(f"作用域访问被拒绝: {scope_id}")
                    return False

            logger.debug(f"记忆访问权限验证通过: {isolation_context}")
            return True

        except Exception as e:
            logger.error(f"验证记忆访问权限失败: {e}")
            return False

    async def validate_conflict_access(
        self,
        isolation_context: IsolationContext,
        platform: Optional[str] = None,
        chat_id: Optional[str] = None,
        conflict_id: Optional[str] = None,
    ) -> bool:
        """
        验证冲突访问权限

        Args:
            isolation_context: 当前隔离上下文
            platform: 平台标识
            chat_id: 聊天ID
            conflict_id: 冲突ID

        Returns:
            是否有访问权限
        """
        try:
            # 验证租户权限
            if not await self.validator.validate_tenant(isolation_context.tenant_id):
                return False

            # 验证智能体权限
            if not await self.validator.validate_agent(isolation_context.tenant_id, isolation_context.agent_id):
                return False

            # 验证平台权限
            if platform and not await self.validator.validate_platform(platform):
                return False

            # 冲突通常需要更严格的访问控制
            # 同一智能体内的冲突可以相互访问
            if chat_id and isolation_context.scope_id:
                if chat_id != isolation_context.scope_id:
                    # 只有同租户内可以跨作用域访问冲突
                    logger.debug(f"跨作用域冲突访问: {chat_id} vs {isolation_context.scope_id}")

            logger.debug(f"冲突访问权限验证通过: {isolation_context}")
            return True

        except Exception as e:
            logger.error(f"验证冲突访问权限失败: {e}")
            return False

    async def validate_tenant_access(self, current_context: IsolationContext, target_tenant_id: str) -> bool:
        """
        验证租户间访问权限

        Args:
            current_context: 当前隔离上下文
            target_tenant_id: 目标租户ID

        Returns:
            是否有访问权限
        """
        try:
            # 只有同租户用户可以访问
            if current_context.tenant_id != target_tenant_id:
                logger.warning(f"租户间访问被拒绝: {current_context.tenant_id} -> {target_tenant_id}")
                return False

            return True

        except Exception as e:
            logger.error(f"验证租户访问权限失败: {e}")
            return False

    async def validate_memory_aggregation(
        self, isolation_context: IsolationContext, source_scopes: List[str], target_level: str
    ) -> bool:
        """
        验证记忆聚合权限

        Args:
            isolation_context: 当前隔离上下文
            source_scopes: 源作用域列表
            target_level: 目标级别

        Returns:
            是否有聚合权限
        """
        try:
            # 验证基本权限
            if not await self.validator.validate_tenant(isolation_context.tenant_id):
                return False

            if not await self.validator.validate_agent(isolation_context.tenant_id, isolation_context.agent_id):
                return False

            # 验证目标级别
            if target_level not in ["agent", "platform", "chat"]:
                logger.warning(f"无效的目标级别: {target_level}")
                return False

            # 检查聚合权限
            # 同一智能体内的记忆可以聚合
            if not source_scopes:
                logger.warning("源作用域列表为空")
                return False

            # 聚合到更高级别需要相应权限
            if target_level == "platform" and not isolation_context.platform:
                logger.warning("聚合到平台级别需要平台标识")
                return False

            logger.debug(f"记忆聚合权限验证通过: {isolation_context}, 目标级别: {target_level}")
            return True

        except Exception as e:
            logger.error(f"验证记忆聚合权限失败: {e}")
            return False

    async def validate_batch_operation(self, isolation_context: IsolationContext, operation_count: int) -> bool:
        """
        验证批量操作权限

        Args:
            isolation_context: 当前隔离上下文
            operation_count: 操作数量

        Returns:
            是否有批量操作权限
        """
        try:
            # 验证基本权限
            if not await self.validator.validate_tenant(isolation_context.tenant_id):
                return False

            if not await self.validator.validate_agent(isolation_context.tenant_id, isolation_context.agent_id):
                return False

            # 检查批量操作数量限制
            max_batch_size = 100  # 可配置
            if operation_count > max_batch_size:
                logger.warning(f"批量操作数量超限: {operation_count} > {max_batch_size}")
                return False

            logger.debug(f"批量操作权限验证通过: {operation_count}项")
            return True

        except Exception as e:
            logger.error(f"验证批量操作权限失败: {e}")
            return False

    async def validate_admin_access(self, isolation_context: IsolationContext) -> bool:
        """
        验证管理员权限

        Args:
            isolation_context: 当前隔离上下文

        Returns:
            是否有管理员权限
        """
        try:
            # 验证基本权限
            if not await self.validator.validate_tenant(isolation_context.tenant_id):
                return False

            if not await self.validator.validate_agent(isolation_context.tenant_id, isolation_context.agent_id):
                return False

            # 这里可以添加更复杂的管理员权限检查逻辑
            # 例如检查智能体是否具有管理员角色

            # 暂时允许所有通过基本验证的用户执行管理员操作
            # 在生产环境中应该有更严格的权限控制

            logger.debug(f"管理员权限验证通过: {isolation_context}")
            return True

        except Exception as e:
            logger.error(f"验证管理员权限失败: {e}")
            return False

    def _is_level_compatible(self, context: IsolationContext, level: str) -> bool:
        """检查级别兼容性"""
        # 智能体可以访问所有级别的记忆
        # 平台级别只能访问平台和聊天级别
        # 聊天级别只能访问聊天级别

        context_level = context.get_isolation_level()

        if context_level >= 2:  # 智能体级别及以上
            return True
        elif context_level == 3:  # 平台级别
            return level in ["platform", "chat"]
        elif context_level == 4:  # 聊天级别
            return level == "chat"
        else:
            return False

    def _can_access_cross_scope(self, context: IsolationContext, target_scope_id: str) -> bool:
        """检查是否可以跨作用域访问"""
        # 高级别可以访问低级别
        # 同级别只能访问相同作用域
        context_level = context.get_isolation_level()

        if context_level >= 3:  # 平台级别及以上可以跨作用域访问
            return True
        elif context_level == 2:  # 智能体级别可以跨作用域访问
            return True
        else:
            return context.scope_id == target_scope_id

    async def create_isolated_context(
        self,
        tenant_id: str,
        agent_id: str,
        platform: Optional[str] = None,
        scope_id: Optional[str] = None,
        request: Optional[Request] = None,
    ) -> IsolationContext:
        """
        创建隔离上下文

        Args:
            tenant_id: 租户ID
            agent_id: 智能体ID
            platform: 平台标识
            scope_id: 作用域ID
            request: HTTP请求对象

        Returns:
            隔离上下文
        """
        try:
            if request:
                # 优先从请求中提取上下文
                return await get_isolation_context_from_request(request)
            else:
                # 直接创建上下文
                from ..utils.isolation import validate_isolation_context

                return await validate_isolation_context(tenant_id, agent_id, platform, scope_id)

        except Exception as e:
            logger.error(f"创建隔离上下文失败: {e}")
            raise

    async def check_isolation_compatibility(
        self, context1: IsolationContext, context2: IsolationContext, operation: str = "access"
    ) -> Dict[str, Any]:
        """
        检查两个隔离上下文的兼容性

        Args:
            context1: 第一个隔离上下文
            context2: 第二个隔离上下文
            operation: 操作类型

        Returns:
            兼容性检查结果
        """
        try:
            compatibility = {
                "compatible": True,
                "same_tenant": context1.is_same_tenant(context2),
                "same_agent": context1.is_same_agent(context2),
                "same_platform": context1.is_same_platform(context2),
                "same_scope": context1.is_same_scope(context2),
                "access_level": self._get_access_level(context1, context2),
                "restrictions": [],
            }

            # 检查基本兼容性
            if not compatibility["same_tenant"]:
                compatibility["compatible"] = False
                compatibility["restrictions"].append("不同租户无法访问")

            # 根据操作类型检查具体限制
            if operation == "write":
                if not compatibility["same_agent"]:
                    compatibility["compatible"] = False
                    compatibility["restrictions"].append("写操作需要同一智能体")
            elif operation == "read":
                if compatibility["same_tenant"]:
                    # 同租户内可以读取，但可能有其他限制
                    pass
                else:
                    compatibility["compatible"] = False
                    compatibility["restrictions"].append("跨租户读取被禁止")

            return compatibility

        except Exception as e:
            logger.error(f"检查隔离兼容性失败: {e}")
            return {"compatible": False, "error": str(e)}

    def _get_access_level(self, context1: IsolationContext, context2: IsolationContext) -> str:
        """获取访问级别"""
        if context1.is_same_scope(context2):
            return "full"
        elif context1.is_same_platform(context2):
            return "platform"
        elif context1.is_same_agent(context2):
            return "agent"
        elif context1.is_same_tenant(context2):
            return "tenant"
        else:
            return "none"

    async def get_isolation_hierarchy(self) -> Dict[str, Any]:
        """
        获取隔离层级信息

        Returns:
            隔离层级结构
        """
        return {
            "levels": {
                1: {
                    "name": "tenant",
                    "description": "租户级别",
                    "isolation": "完全隔离",
                    "access": "只能访问同租户数据",
                },
                2: {
                    "name": "agent",
                    "description": "智能体级别",
                    "isolation": "租户内智能体间隔离",
                    "access": "可访问同租户内所有数据",
                },
                3: {
                    "name": "platform",
                    "description": "平台级别",
                    "isolation": "智能体内平台间隔离",
                    "access": "可访问同智能体内所有数据",
                },
                4: {
                    "name": "scope",
                    "description": "作用域级别",
                    "isolation": "聊天流级别隔离",
                    "access": "可访问同平台内所有数据",
                },
            },
            "access_rules": {
                "tenant_to_tenant": "禁止",
                "tenant_to_agent": "禁止",
                "agent_to_agent": "限制访问",
                "agent_to_platform": "允许",
                "platform_to_chat": "允许",
                "chat_to_platform": "限制",
            },
        }

    async def health_check(self) -> Dict[str, Any]:
        """
        健康检查

        Returns:
            隔离服务健康状态
        """
        try:
            # 检查验证器状态
            validator_status = {
                "tenants_loaded": len(self.validator.allowed_tenants),
                "agents_loaded": sum(len(agents) for agents in self.validator.allowed_agents.values()),
                "platforms_loaded": len(self.validator.allowed_platforms),
            }

            return {
                "status": "healthy",
                "validator": validator_status,
                "isolation_levels": 4,
                "timestamp": "2024-01-01T00:00:00Z",  # 使用实际时间戳
            }

        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
