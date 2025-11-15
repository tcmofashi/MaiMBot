"""
配置器API客户端
用于用户注册、Agent创建等配置操作
"""

import logging
from typing import Dict, List, Optional, Tuple
import aiohttp
from dataclasses import dataclass
import time
import random

logger = logging.getLogger(__name__)


@dataclass
class TestUser:
    """测试用户数据"""

    username: str
    password: str
    email: str
    tenant_name: str
    tenant_id: str
    user_id: str
    access_token: str
    api_key: str
    agents: List[Dict] = None

    def __post_init__(self):
        if self.agents is None:
            self.agents = []


@dataclass
class TestAgent:
    """测试Agent数据"""

    agent_id: str
    name: str
    tenant_id: str
    template_id: str
    persona: str


class ConfigAPIClient:
    """配置器API客户端"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        # 确保base_url是字符串类型
        if isinstance(base_url, int):
            # 如果传入的是整数，假设是端口号
            self.base_url = f"http://localhost:{base_url}"
            logger.warning(f"ConfigAPIClient接收到整数端口号 {base_url}，已转换为URL: {self.base_url}")
        elif isinstance(base_url, str):
            self.base_url = base_url
        else:
            # 其他类型转换为字符串
            self.base_url = str(base_url)
            logger.warning(
                f"ConfigAPIClient接收到非字符串URL {base_url} (类型: {type(base_url)})，已转换为: {self.base_url}"
            )

        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def _request(self, method: str, path: str, **kwargs) -> Dict:
        """发送HTTP请求"""
        # 确保path以/开头
        if not path.startswith("/"):
            path = "/" + path

        # 构建完整URL
        url = f"{self.base_url.rstrip('/')}{path}"

        if not self.session:
            raise RuntimeError("Session not initialized. Use async with context.")

        try:
            async with self.session.request(method, url, **kwargs) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    logger.error(f"HTTP {response.status}: {error_text} - URL: {url}")
                    raise Exception(f"HTTP {response.status}: {error_text}")

                return await response.json()
        except aiohttp.ClientError as e:
            logger.error(f"Request failed: {e} - URL: {url}")
            raise Exception(f"Request failed: {e}") from e

    async def register_user(self, username: str, password: str, email: str, tenant_name: str = None) -> TestUser:
        """注册用户"""
        if not tenant_name:
            tenant_name = f"{username}的租户"

        data = {
            "username": username,
            "password": password,
            "email": email,
            "tenant_name": tenant_name,
            "tenant_type": "personal",
        }

        result = await self._request("POST", "/api/v1/auth/register", json=data)

        return TestUser(
            username=username,
            password=password,
            email=email,
            tenant_name=tenant_name,
            tenant_id=result["user_info"]["tenant_id"],
            user_id=result["user_info"]["user_id"],
            access_token=result["access_token"],
            api_key=result["user_info"]["api_key"],
        )

    async def login_user(self, username: str, password: str) -> TestUser:
        """登录用户"""
        data = {"username": username, "password": password}

        result = await self._request("POST", "/api/v1/auth/login", json=data)

        return TestUser(
            username=username,
            password=password,
            email=result["user_info"]["email"],
            tenant_name=result["user_info"]["tenant_name"],
            tenant_id=result["user_info"]["tenant_id"],
            user_id=result["user_info"]["user_id"],
            access_token=result["access_token"],
            api_key=result["user_info"]["api_key"],
        )

    async def get_agent_templates(self) -> List[Dict]:
        """获取Agent模板列表"""
        result = await self._request("GET", "/api/v1/agents/templates")
        return result

    async def create_agent(
        self, user: TestUser, name: str, template_id: str = None, description: str = None
    ) -> TestAgent:
        """为用户创建Agent"""
        headers = {"Authorization": f"Bearer {user.access_token}"}

        data = {
            "name": name,
            "description": description or f"{name} - 测试Agent",
            "template_id": template_id or "friendly_assistant",
        }

        result = await self._request("POST", "/api/v1/agents/", json=data, headers=headers)

        return TestAgent(
            agent_id=result["agent_id"],
            name=result["name"],
            tenant_id=result["tenant_id"],
            template_id=template_id or "friendly_assistant",
            persona=result.get("persona", "默认人格"),
        )

    async def get_user_agents(self, user: TestUser) -> List[Dict]:
        """获取用户的Agent列表"""
        headers = {"Authorization": f"Bearer {user.access_token}"}

        result = await self._request("GET", "/api/v1/agents/", headers=headers)
        return result

    async def get_tenant_stats(self, user: TestUser) -> Dict:
        """获取租户统计信息"""
        headers = {"Authorization": f"Bearer {user.access_token}"}

        result = await self._request("GET", "/api/v1/tenant/stats", headers=headers)
        return result


class MultiTenantTestManager:
    """多租户测试管理器"""

    def __init__(self, config_api_url: str = "http://localhost:8000"):
        # 确保config_api_url是字符串类型
        if isinstance(config_api_url, int):
            # 如果传入的是整数，假设是端口号
            self.config_api_url = f"http://localhost:{config_api_url}"
            logger.warning(
                f"MultiTenantTestManager接收到整数端口号 {config_api_url}，已转换为URL: {self.config_api_url}"
            )
        elif isinstance(config_api_url, str):
            self.config_api_url = config_api_url
        else:
            # 其他类型转换为字符串
            self.config_api_url = str(config_api_url)
            logger.warning(
                f"MultiTenantTestManager接收到非字符串URL {config_api_url} (类型: {type(config_api_url)})，已转换为: {self.config_api_url}"
            )

        self.users: List[TestUser] = []
        self.agents: List[TestAgent] = []

    async def create_test_users(
        self, count: int = 3, agents_per_user: int = 2
    ) -> Tuple[List[TestUser], List[TestAgent]]:
        """创建测试用户和Agent"""
        async with ConfigAPIClient(self.config_api_url) as client:
            users = []
            all_agents = []

            for i in range(count):
                # 创建用户
                # 生成唯一用户名，避免冲突
                timestamp = int(time.time() * 1000)  # 毫秒时间戳
                random_suffix = random.randint(1000, 9999)
                username = f"testuser_{timestamp}_{random_suffix}_{i + 1:03d}"
                password = "testpass123"
                email = f"testuser_{timestamp}_{random_suffix}_{i + 1:03d}@example.com"
                tenant_name = f"测试租户_{timestamp}_{random_suffix}_{i + 1:03d}"

                try:
                    user = await client.register_user(username, password, email, tenant_name)
                    users.append(user)
                    logger.info(f"创建用户成功: {username} (tenant: {user.tenant_id})")

                    # 获取可用模板
                    templates = await client.get_agent_templates()
                    if templates and "data" in templates:
                        template_list = templates["data"]
                    else:
                        template_list = []

                    # 为用户创建多个Agent
                    for j in range(agents_per_user):
                        agent_name = f"{username}_agent_{j + 1}"

                        # 选择模板
                        template_id = "friendly_assistant"
                        if template_list and len(template_list) > j:
                            template_id = template_list[j]["template_id"]

                        try:
                            agent = await client.create_agent(user, agent_name, template_id)
                            all_agents.append(agent)
                            user.agents.append(
                                {"agent_id": agent.agent_id, "name": agent.name, "template_id": template_id}
                            )
                            logger.info(f"创建Agent成功: {agent_name} (id: {agent.agent_id})")
                        except Exception as e:
                            logger.error(f"创建Agent失败 {agent_name}: {e}")

                except Exception as e:
                    logger.error(f"创建用户失败 {username}: {e}")

            self.users = users
            self.agents = all_agents

            logger.info(f"总共创建 {len(users)} 个用户, {len(all_agents)} 个Agent")
            return users, all_agents

    def get_test_data(self) -> Dict:
        """获取测试数据摘要"""
        return {
            "users": [
                {
                    "username": user.username,
                    "tenant_id": user.tenant_id,
                    "user_id": user.user_id,
                    "api_key": user.api_key,
                    "agents": user.agents,
                }
                for user in self.users
            ],
            "total_users": len(self.users),
            "total_agents": len(self.agents),
        }

    async def cleanup_test_data(self):
        """清理测试数据（这里需要实现数据库清理逻辑）"""
        # 注意：这个方法需要在cleanup_test.py中实现
        pass


# 便捷函数
async def create_test_scenario(
    config_api_url: str = "http://localhost:8000", user_count: int = 3, agents_per_user: int = 2
) -> MultiTenantTestManager:
    """创建测试场景"""
    manager = MultiTenantTestManager(config_api_url)
    await manager.create_test_users(user_count, agents_per_user)
    return manager
