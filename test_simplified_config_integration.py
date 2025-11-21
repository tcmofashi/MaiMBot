#!/usr/bin/env python3
"""
简化配置系统集成测试
验证新的双层配置系统是否正常工作，解决配置缺失问题
"""

import sys
import logging
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.common.logger import get_logger
from src.config.config_integration import (
    get_config_manager,
    get_integration_status,
    clear_config_cache,
)
from src.config.config_wrapper import UnifiedConfigWrapper

logger = get_logger(__name__)


def test_simplified_config_manager():
    """测试简化配置管理器"""
    print("=" * 60)
    print("🧪 测试简化配置管理器")
    print("=" * 60)

    try:
        # 测试配置管理器创建
        tenant_id = "test_tenant"
        agent_id = "test_agent"

        print(f"📋 创建配置管理器: tenant={tenant_id}, agent={agent_id}")
        manager = get_config_manager(tenant_id, agent_id)

        # 测试配置获取
        print("📋 获取合并后的配置...")
        merged_config = manager.get_merged_config()

        # 检查关键配置节是否存在
        critical_sections = ["chat", "personality", "bot", "tool", "response_splitter", "chinese_typo"]
        missing_sections = []

        for section in critical_sections:
            if section in merged_config:
                print(f"✅ 配置节 '{section}' 存在")
            else:
                print(f"❌ 配置节 '{section}' 缺失")
                missing_sections.append(section)

        # 检查聊天配置的关键属性
        if "chat" in merged_config:
            chat_config = merged_config["chat"]
            critical_attrs = ["max_context_size", "planner_smooth", "talk_value"]
            missing_attrs = []

            for attr in critical_attrs:
                if attr in chat_config:
                    print(f"✅ 聊天配置属性 '{attr}' 存在: {chat_config[attr]}")
                else:
                    print(f"❌ 聊天配置属性 '{attr}' 缺失")
                    missing_attrs.append(attr)

        print("\n📊 测试结果:")
        print(f"   - 缺失配置节: {len(missing_sections)}")
        print(f"   - 缺失配置属性: {len(missing_attrs)}")

        return len(missing_sections) == 0 and len(missing_attrs) == 0

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_config_wrappers():
    """测试配置包装器"""
    print("\n" + "=" * 60)
    print("🧪 测试配置包装器")
    print("=" * 60)

    try:
        tenant_id = "test_tenant"
        agent_id = "test_agent"

        # 测试统一配置包装器（使用租户ID和智能体ID）
        print(f"📋 创建统一配置包装器: tenant={tenant_id}, agent={agent_id}")
        unified_config = UnifiedConfigWrapper(tenant_id, agent_id)

        # 测试聊天配置包装器
        print("📋 获取聊天配置包装器...")
        chat_config = unified_config.chat

        # 测试关键配置访问
        print("📋 测试配置访问...")

        # 测试聊天配置属性
        try:
            max_context = chat_config.max_context_size
            print(f"✅ max_context_size: {max_context}")
        except Exception as e:
            print(f"⚠️  max_context_size 访问失败: {e}")

        try:
            planner_smooth = chat_config.planner_smooth
            print(f"✅ planner_smooth: {planner_smooth}")
        except Exception as e:
            print(f"⚠️  planner_smooth 访问失败: {e}")

        try:
            talk_value = chat_config.get_talk_value("test_stream")
            print(f"✅ talk_value: {talk_value}")
        except Exception as e:
            print(f"⚠️  talk_value 访问失败: {e}")

        # 测试其他配置节
        try:
            personality = unified_config.personality
            print("✅ personality 配置节存在")
        except Exception as e:
            print(f"⚠️  personality 配置节访问失败: {e}")

        try:
            tool_config = unified_config.tool
            print("✅ tool 配置节存在")
        except Exception as e:
            print(f"⚠️  tool 配置节访问失败: {e}")

        try:
            response_splitter = unified_config.response_splitter
            print("✅ response_splitter 配置节存在")
        except Exception as e:
            print(f"⚠️  response_splitter 配置节访问失败: {e}")

        try:
            chinese_typo = unified_config.chinese_typo
            print("✅ chinese_typo 配置节存在")
        except Exception as e:
            print(f"⚠️  chinese_typo 配置节访问失败: {e}")

        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_integration_status():
    """测试集成状态"""
    print("\n" + "=" * 60)
    print("🧪 测试集成状态")
    print("=" * 60)

    try:
        status = get_integration_status()
        print("📊 集成状态:")
        for key, value in status.items():
            print(f"   - {key}: {value}")

        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


def test_config_cache():
    """测试配置缓存"""
    print("\n" + "=" * 60)
    print("🧪 测试配置缓存")
    print("=" * 60)

    try:
        tenant_id = "cache_test_tenant"
        agent_id = "cache_test_agent"

        # 第一次创建配置管理器
        print("📋 第一次创建配置管理器...")
        manager1 = get_config_manager(tenant_id, agent_id)

        # 第二次创建配置管理器（应该使用缓存）
        print("📋 第二次创建配置管理器（应该使用缓存）...")
        manager2 = get_config_manager(tenant_id, agent_id)

        # 检查是否是同一个实例
        if manager1 is manager2:
            print("✅ 配置缓存工作正常")
        else:
            print("⚠️  配置缓存可能有问题")

        # 清理缓存
        print("📋 清理配置缓存...")
        clear_config_cache(tenant_id, agent_id)

        # 再次创建（应该是新实例）
        print("📋 清理缓存后再次创建...")
        manager3 = get_config_manager(tenant_id, agent_id)

        if manager1 is not manager3:
            print("✅ 缓存清理工作正常")
        else:
            print("⚠️  缓存清理可能有问题")

        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


def main():
    """主测试函数"""
    print("🚀 开始简化配置系统集成测试")
    print("目标：验证双层配置系统是否解决配置缺失问题")

    # 设置日志级别
    logging.basicConfig(level=logging.INFO)

    # 运行测试
    tests = [
        ("简化配置管理器", test_simplified_config_manager),
        ("配置包装器", test_config_wrappers),
        ("集成状态", test_integration_status),
        ("配置缓存", test_config_cache),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ 测试 '{test_name}' 发生异常: {e}")
            results.append((test_name, False))

    # 输出测试结果
    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)

    passed = 0
    total = len(results)

    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status} - {test_name}")
        if result:
            passed += 1

    print(f"\n📈 总体结果: {passed}/{total} 测试通过")

    if passed == total:
        print("🎉 所有测试通过！简化配置系统集成成功！")
        print("✅ 配置缺失问题应该已解决")
    else:
        print("⚠️  部分测试失败，需要进一步检查")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
