"""
Agent配置系统使用示例
展示如何使用不同的数据源加载Agent配置并创建融合配置
"""

import asyncio
from typing import Dict, Any, Optional


# 示例1：从数据库加载Agent配置
async def example_load_from_database(agent_id: str) -> Optional[Dict[str, Any]]:
    """
    示例：从数据库加载Agent配置
    """
    from src.common.message import (
        load_agent_config_from_database,
        create_merged_config_from_database,
        get_db_agent_config_loader,
    )

    # 检查数据库是否可用
    db_loader = get_db_agent_config_loader()
    if not db_loader.is_available():
        print("❌ 数据库模块不可用，无法从数据库加载配置")
        return None

    try:
        # 方法1：直接使用便捷函数
        agent_config = await load_agent_config_from_database(agent_id)
        if agent_config:
            print(f"✅ 成功加载Agent配置: {agent_config.name}")
            print(f"   - 人格: {agent_config.persona.personality[:50]}...")
            print(f"   - 平台: {agent_config.bot_overrides.platform}")

        # 方法2：创建融合配置
        merged_config = await create_merged_config_from_database(agent_id)
        if merged_config:
            print(f"✅ 成功创建融合配置，包含 {len(merged_config)} 个配置模块")

        return merged_config

    except Exception as e:
        print(f"❌ 数据库加载失败: {e}")
        return None


# 示例2：创建融合配置的统一接口
async def example_create_merged_config(agent_id: str) -> Optional[Dict[str, Any]]:
    """
    示例：使用统一接口创建融合配置
    """
    from src.common.message import create_merged_agent_config

    try:
        # 创建融合配置
        merged_config = await create_merged_agent_config(agent_id)
        if not merged_config:
            print(f"❌ 无法创建融合配置: {agent_id}")
            return None

        print("✅ 成功创建融合配置，包含以下模块:")
        for module_name, module_config in merged_config.items():
            if hasattr(module_config, "__class__"):
                print(f"   - {module_name}: {module_config.__class__.__name__}")

        return merged_config

    except Exception as e:
        print(f"❌ 创建融合配置失败: {e}")
        return None


# 示例3：获取可用Agent列表
async def example_get_available_agents():
    """
    示例：获取可用Agent列表
    """
    from src.common.message import get_available_agents

    # 从数据库获取
    try:
        database_agents = await get_available_agents()
        if database_agents:
            print("✅ 从数据库获取的Agent列表:")
            if isinstance(database_agents, dict) and "agents" in database_agents:
                for agent in database_agents["agents"][:5]:  # 只显示前5个
                    print(f"   - {agent.get('agent_id', 'Unknown')}")
        else:
            print("⚠️ 数据库中没有可用的Agent")
    except Exception as e:
        print(f"❌ 从数据库获取Agent列表失败: {e}")


# 示例4：配置重载
async def example_reload_config(agent_id: str):
    """
    示例：重新加载配置
    """
    from src.common.message import reload_agent_config

    try:
        # 重新加载配置
        merged_config = await reload_agent_config(agent_id)
        if merged_config:
            print(f"✅ 成功重新加载Agent配置: {agent_id}")
        else:
            print(f"❌ 重新加载Agent配置失败: {agent_id}")

    except Exception as e:
        print(f"❌ 重新加载配置失败: {e}")


# 示例5：检查数据库可用性
def example_check_database_availability():
    """
    示例：检查数据库可用性
    """
    from src.common.message import get_agent_config_loader, get_db_agent_config_loader

    # 检查数据库可用性
    db_loader = get_db_agent_config_loader()
    is_available = db_loader.is_available()
    print(f"✅ 数据库可用性: {is_available}")

    if is_available:
        print("✅ 数据库模块正常，可以加载Agent配置")
    else:
        print("⚠️ 数据库模块不可用，请检查maim_db安装和数据库连接")

    # 获取加载器状态
    loader = get_agent_config_loader()
    print(f"✅ 配置加载器状态: {'正常' if loader.is_available() else '不可用'}")


# 示例配置字典
SAMPLE_AGENT_CONFIG = {
    "agent_id": "example_agent",
    "name": "示例Agent",
    "description": "这是一个示例Agent配置",
    "tags": ["示例", "测试"],
    "persona": {
        "personality": "我是一个友好的AI助手，喜欢帮助用户解决问题。",
        "reply_style": "友好、耐心、专业",
        "interest": "技术、科学、艺术",
        "plan_style": "在群聊中积极参与，提供有价值的信息",
        "private_plan_style": "在私聊中提供个性化帮助",
        "visual_style": "简洁、清晰的技术风格",
        "states": ["友善助手", "专业顾问"],
        "state_probability": 0.1,
    },
    "bot_overrides": {"platform": "qq", "nickname": "小助手", "alias_names": ["助手", "AI小助手"]},
    "config_overrides": {"chat": {"max_context_size": 20, "talk_value": 1.2}, "emoji": {"emoji_chance": 0.5}},
}


async def main():
    """
    运行所有示例
    """
    print("🚀 Agent配置系统使用示例（数据库版）\n")

    # 示例5：检查数据库可用性
    print("=== 检查数据库可用性 ===")
    example_check_database_availability()
    print()

    # 示例3：获取可用Agent列表
    print("=== 获取可用Agent列表 ===")
    await example_get_available_agents()
    print()

    # 示例1：从数据库加载Agent配置
    print("=== 从数据库加载Agent配置 ===")
    await example_load_from_database("example_agent")
    print()

    # 示例2：创建融合配置
    print("=== 创建融合配置 ===")
    await example_create_merged_config("example_agent")
    print()

    # 示例4：配置重载
    print("=== 配置重载 ===")
    await example_reload_config("example_agent")
    print()

    print("✅ 所有示例运行完成！")


if __name__ == "__main__":
    asyncio.run(main())
