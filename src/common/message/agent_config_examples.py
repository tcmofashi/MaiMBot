"""
Agent专用配置获取示例
演示如何获取和使用Agent专用的global_config和model_config
"""

import asyncio
from typing import Optional, Tuple
from src.common.message import (
    load_agent_config,
    create_agent_global_config,
    create_agent_model_config,
    get_db_agent_config_loader,
)


async def example_basic_usage(agent_id: str) -> Tuple[Optional[object], Optional[object]]:
    """
    基础使用示例：获取Agent的global_config和model_config
    """
    print(f"🚀 获取Agent {agent_id} 的专用配置")

    # 1. 检查数据库可用性
    db_loader = get_db_agent_config_loader()
    if not db_loader.is_available():
        print("❌ 数据库模块不可用")
        return None, None

    # 2. 获取Agent专用的global_config
    print("📥 获取global_config...")
    global_config = await create_agent_global_config(agent_id)
    if not global_config:
        print("❌ global_config获取失败")
        return None, None

    # 3. 获取Agent专用的model_config
    print("📥 获取model_config...")
    model_config = await create_agent_model_config(agent_id)
    if not model_config:
        print("❌ model_config获取失败")
        return None, None

    # 4. 显示配置信息
    print("✅ 配置获取成功!")
    print("  📋 Agent配置概览:")
    print(f"     - Bot平台: {getattr(global_config.bot, 'platform', 'N/A')}")
    print(f"     - 昵称: {getattr(global_config.bot, 'nickname', 'N/A')}")
    print(f"     - 人格: {getattr(global_config.personality, 'personality', 'N/A')[:50]}...")
    print(f"     - 模型名称: {getattr(model_config, 'model_name', 'N/A')}")
    print(f"     - 温度设置: {getattr(model_config, 'temperature', 'N/A')}")

    return global_config, model_config


async def example_agent_config_details(agent_id: str):
    """
    详细配置示例：展示Agent配置的详细信息
    """
    print(f"🔍 Agent {agent_id} 详细配置分析")

    # 获取原始Agent配置
    agent_config = await load_agent_config(agent_id)
    if not agent_config:
        print("❌ Agent配置不存在")
        return

    print("📋 Agent基本信息:")
    print(f"   - ID: {agent_config.agent_id}")
    print(f"   - 名称: {agent_config.name}")
    print(f"   - 描述: {agent_config.description}")
    print(f"   - 标签: {agent_config.tags}")

    print("\n🧠 人格配置:")
    persona = agent_config.persona
    print(f"   - 人格描述: {persona.personality}")
    print(f"   - 回复风格: {persona.reply_style}")
    print(f"   - 兴趣领域: {persona.interest}")
    print(f"   - 群聊风格: {persona.plan_style}")
    print(f"   - 私聊风格: {persona.private_plan_style}")

    if hasattr(persona, "states") and persona.states:
        print(f"   - 状态列表: {persona.states}")
        print(f"   - 状态切换概率: {persona.state_probability}")

    print("\n⚙️ Bot覆盖配置:")
    bot_overrides = agent_config.bot_overrides
    print(f"   - 平台: {bot_overrides.platform}")
    print(f"   - QQ账号: {bot_overrides.qq_account}")
    print(f"   - 昵称: {bot_overrides.nickname}")
    print(f"   - 别名列表: {bot_overrides.alias_names}")

    print("\n🔧 配置覆盖:")
    config_overrides = agent_config.config_overrides
    if config_overrides.chat:
        print("   聊天配置覆盖:")
        chat = config_overrides.chat
        print(f"     - 最大上下文: {chat.max_context_size}")
        print(f"     - 规划器大小: {chat.planner_size}")
        print(f"     - 聊天价值: {chat.talk_value}")

    if config_overrides.mood:
        print("   情绪配置覆盖:")
        mood = config_overrides.mood
        print(f"     - 启用情绪: {mood.enable_mood}")
        print(f"     - 更新阈值: {mood.mood_update_threshold}")

    if config_overrides.memory:
        print("   记忆配置覆盖:")
        memory = config_overrides.memory
        print(f"     - 最大记忆数: {memory.max_memory_number}")
        print(f"     - 构建频率: {memory.memory_build_frequency}")


async def example_config_comparison(agent_id: str):
    """
    配置对比示例：比较基础配置和Agent专用配置
    """
    print(f"⚖️ Agent {agent_id} 配置对比分析")

    try:
        # 获取基础配置
        from src.config.config import global_config as base_global_config

        print("📊 基础配置:")
        print(f"   - Bot平台: {getattr(base_global_config.bot, 'platform', 'N/A')}")
        print(f"   - 昵称: {getattr(base_global_config.bot, 'nickname', 'N/A')}")
        print(f"   - 人格: {getattr(base_global_config.personality, 'personality', 'N/A')[:50]}...")

        # 获取Agent专用配置
        agent_global_config = await create_agent_global_config(agent_id)
        _ = await create_agent_model_config(agent_id)  # 获取但不使用，用于完整性

        if not agent_global_config:
            print("❌ Agent配置获取失败")
            return

        print("\n🎯 Agent专用配置:")
        print(f"   - Bot平台: {getattr(agent_global_config.bot, 'platform', 'N/A')}")
        print(f"   - 昵称: {getattr(agent_global_config.bot, 'nickname', 'N/A')}")
        print(f"   - 人格: {getattr(agent_global_config.personality, 'personality', 'N/A')[:50]}...")

        # 比较差异
        print("\n🔍 配置差异分析:")
        if hasattr(agent_global_config.bot, "platform") and hasattr(base_global_config.bot, "platform"):
            if agent_global_config.bot.platform != base_global_config.bot.platform:
                print(f"   ✅ 平台已覆盖: {base_global_config.bot.platform} → {agent_global_config.bot.platform}")

        if hasattr(agent_global_config.bot, "nickname") and hasattr(base_global_config.bot, "nickname"):
            if agent_global_config.bot.nickname != base_global_config.bot.nickname:
                print(f"   ✅ 昵称已覆盖: {base_global_config.bot.nickname} → {agent_global_config.bot.nickname}")

        if hasattr(agent_global_config.personality, "personality") and hasattr(
            base_global_config.personality, "personality"
        ):
            if agent_global_config.personality.personality != base_global_config.personality.personality:
                print("   ✅ 人格已覆盖: 基础人格 → Agent专用人格")

    except Exception as e:
        print(f"❌ 配置对比失败: {e}")


async def example_multiple_agents():
    """
    多Agent配置示例：批量获取多个Agent的配置
    """
    print("👥 多Agent配置批量获取")

    from src.common.message import get_available_agents

    # 获取所有可用Agent
    agents_info = await get_available_agents()
    if not agents_info or "agents" not in agents_info:
        print("❌ 没有可用的Agent")
        return

    agent_ids = [agent["agent_id"] for agent in agents_info["agents"][:5]]  # 只处理前5个
    print(f"📋 发现 {len(agent_ids)} 个Agent: {agent_ids}")

    # 并行获取配置
    tasks = [create_agent_global_config(agent_id) for agent_id in agent_ids]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    successful_configs = {}
    failed_agents = []

    for agent_id, result in zip(agent_ids, results, strict=True):
        if isinstance(result, Exception):
            print(f"❌ Agent {agent_id} 配置获取失败: {result}")
            failed_agents.append(agent_id)
        else:
            successful_configs[agent_id] = result
            print(f"✅ Agent {agent_id} 配置获取成功")

    print("\n📊 批量获取结果:")
    print(f"   - 成功: {len(successful_configs)} 个")
    print(f"   - 失败: {len(failed_agents)} 个")

    # 展示成功获取的配置概要
    for agent_id, config in successful_configs.items():
        print(f"   📋 {agent_id}:")
        print(f"     - 平台: {getattr(config.bot, 'platform', 'N/A')}")
        print(f"     - 昵称: {getattr(config.bot, 'nickname', 'N/A')}")


async def example_config_validation(agent_id: str):
    """
    配置验证示例：验证Agent配置的完整性
    """
    print(f"🔍 Agent {agent_id} 配置验证")

    # 获取配置
    global_config = await create_agent_global_config(agent_id)
    model_config = await create_agent_model_config(agent_id)

    if not global_config or not model_config:
        print("❌ 配置获取失败，无法验证")
        return False

    # 验证必需字段
    validation_errors = []

    # 验证global_config
    required_global_fields = ["bot", "personality", "chat"]
    for field in required_global_fields:
        if not hasattr(global_config, field):
            validation_errors.append(f"global_config缺少字段: {field}")

    if hasattr(global_config, "bot"):
        bot = global_config.bot
        if not hasattr(bot, "platform") or not bot.platform:
            validation_errors.append("bot.platform不能为空")

    # 验证model_config
    if not hasattr(model_config, "model_name") or not model_config.model_name:
        validation_errors.append("model_config.model_name不能为空")

    if validation_errors:
        print("❌ 配置验证失败:")
        for error in validation_errors:
            print(f"   - {error}")
        return False
    else:
        print("✅ 配置验证通过")
        return True


async def main():
    """
    运行所有示例
    """
    print("🎯 Agent专用配置获取示例集合\n")

    # 选择一个示例Agent ID
    example_agent_id = "example_agent"

    # 1. 基础使用示例
    print("=" * 50)
    print("1. 基础使用示例")
    print("=" * 50)
    global_config, model_config = await example_basic_usage(example_agent_id)
    print()

    # 2. 详细配置示例
    print("=" * 50)
    print("2. 详细配置示例")
    print("=" * 50)
    await example_agent_config_details(example_agent_id)
    print()

    # 3. 配置对比示例
    print("=" * 50)
    print("3. 配置对比示例")
    print("=" * 50)
    await example_config_comparison(example_agent_id)
    print()

    # 4. 配置验证示例
    print("=" * 50)
    print("4. 配置验证示例")
    print("=" * 50)
    await example_config_validation(example_agent_id)
    print()

    # 5. 多Agent配置示例
    print("=" * 50)
    print("5. 多Agent配置示例")
    print("=" * 50)
    await example_multiple_agents()
    print()

    print("✅ 所有示例运行完成!")


if __name__ == "__main__":
    asyncio.run(main())
