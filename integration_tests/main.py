"""
多租户集成测试主程序

命令行入口，支持运行各种测试场景
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
current_path = Path(__file__).resolve()
project_root = current_path.parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from integration_tests.client import TestRunner  # noqa: E402
from integration_tests.config import TestConfig, create_default_config  # noqa: E402

logger = logging.getLogger(__name__)


def create_config_file(config_path: str, force: bool = False):
    """创建默认配置文件"""
    if os.path.exists(config_path) and not force:
        print(f"配置文件已存在: {config_path}")
        print("使用 --force 强制覆盖")
        return

    config = create_default_config()

    # 生成TOML配置
    toml_content = generate_toml_config(config)

    with open(config_path, "w", encoding="utf-8") as f:
        f.write(toml_content)

    print(f"配置文件已创建: {config_path}")


def generate_toml_config(config: TestConfig) -> str:
    """生成TOML格式的配置文件内容"""

    lines = [
        "# MaiBot 多租户集成测试配置文件",
        "",
        "[settings]",
        f"concurrent_users = {config.concurrent_users}",
        f"message_delay_min = {config.message_delay_min}",
        f"message_delay_max = {config.message_delay_max}",
        f"test_duration = {config.test_duration}",
        f'log_level = "{config.log_level}"',
        "",
        "[llm]",
        f'model_name = "{config.llm.model_name}"',
        f'api_base = "{config.llm.api_base or "null"}"',
        f'api_key = "{config.llm.api_key or "null"}"',
        f"temperature = {config.llm.temperature}",
        f"max_tokens = {config.llm.max_tokens}",
        f"timeout = {config.llm.timeout}",
        "",
        "# 租户配置",
        "[[tenants]]",
        'tenant_id = "tenant_a"',
        'tenant_name = "科技公司A"',
        'description = "专注于AI技术研发的科技公司"',
        "",
        "[tenants.settings]",
        'industry = "technology"',
        'size = "medium"',
        "",
        "[[tenants]]",
        'tenant_id = "tenant_b"',
        'tenant_name = "教育机构B"',
        'description = "在线教育平台"',
        "",
        "[tenants.settings]",
        'industry = "education"',
        'size = "large"',
        "",
        "[[tenants]]",
        'tenant_id = "tenant_c"',
        'tenant_name = "个人用户C"',
        'description = "个人开发者"',
        "",
        "[tenants.settings]",
        'industry = "individual"',
        'size = "small"',
        "",
        "# 智能体配置",
        "[[agents]]",
        'agent_id = "assistant_tech"',
        'agent_name = "技术助手"',
        'personality = "专业、严谨、善于技术解答"',
        'tenant_id = "tenant_a"',
        'description = "专注于技术问题的AI助手"',
        "",
        "[[agents]]",
        'agent_id = "tutor_edu"',
        'agent_name = "教育导师"',
        'personality = "耐心、亲切、善于教学"',
        'tenant_id = "tenant_b"',
        'description = "专注于教育辅导的AI助手"',
        "",
        "[[agents]]",
        'agent_id = "companion_general"',
        'agent_name = "通用伙伴"',
        'personality = "友善、幽默、健谈"',
        'tenant_id = "tenant_c"',
        'description = "日常聊天的AI伙伴"',
        "",
        "# 平台配置",
        "[[platforms]]",
        'platform = "qq"',
        'name = "QQ"',
        'description = "腾讯QQ平台"',
        "",
        "[[platforms]]",
        'platform = "wechat"',
        'name = "微信"',
        'description = "微信平台"',
        "",
        "[[platforms]]",
        'platform = "discord"',
        'name = "Discord"',
        'description = "Discord平台"',
        "",
        "# 测试场景配置",
        "[[scenarios]]",
        'name = "技术讨论群"',
        'description = "公司内部技术讨论群聊"',
        'tenant_id = "tenant_a"',
        'agent_id = "assistant_tech"',
        'platform = "qq"',
        'user_id = "dev_001"',
        'group_id = "tech_group_001"',
        "message_count = 15",
        'conversation_topics = ["Python编程", "算法优化", "系统架构", "Bug调试"]',
        "",
        "[[scenarios]]",
        'name = "一对一教学"',
        'description = "学生与教育导师的一对一交流"',
        'tenant_id = "tenant_b"',
        'agent_id = "tutor_edu"',
        'platform = "wechat"',
        'user_id = "student_001"',
        "message_count = 20",
        'conversation_topics = ["数学问题", "学习方法", "作业辅导", "考试准备"]',
        "",
        "[[scenarios]]",
        'name = "日常聊天"',
        'description = "个人用户的日常闲聊"',
        'tenant_id = "tenant_c"',
        'agent_id = "companion_general"',
        'platform = "discord"',
        'user_id = "user_001"',
        "message_count = 12",
        'conversation_topics = ["电影推荐", "兴趣爱好", "日常生活", "游戏讨论"]',
    ]

    return "\n".join(lines)


def setup_logging(log_level: str):
    """设置日志"""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler("integration_test.log", encoding="utf-8")],
    )


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="MaiBot 多租户集成测试工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 创建默认配置文件
  python -m integration_tests.main --create-config

  # 运行所有测试
  python -m integration_tests.main

  # 运行并发测试
  python -m integration_tests.main --mode concurrent --concurrent-users 10

  # 使用自定义配置
  python -m integration_tests.main --config my_config.toml

  # 只运行场景测试
  python -m integration_tests.main --mode scenarios
        """,
    )

    parser.add_argument("--config", dest="config_path", default=None, help="配置文件路径 (默认使用内置配置)")

    parser.add_argument(
        "--mode",
        choices=["all", "scenarios", "concurrent"],
        default="all",
        help="测试模式: all(全部), scenarios(场景测试), concurrent(并发测试)",
    )

    parser.add_argument("--concurrent-users", type=int, default=None, help="并发用户数 (覆盖配置文件中的设置)")

    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO", help="日志级别")

    parser.add_argument("--create-config", dest="create_config_path", metavar="PATH", help="创建默认配置文件到指定路径")

    parser.add_argument("--force", action="store_true", help="强制覆盖已存在的配置文件")

    parser.add_argument(
        "--server-url", default="http://localhost:8000", help="MaiBot服务器URL (默认: http://localhost:8000)"
    )

    parser.add_argument("--output", metavar="PATH", help="保存测试结果到文件")

    return parser.parse_args()


async def run_test_with_args(args):
    """根据命令行参数运行测试"""

    # 设置日志
    setup_logging(args.log_level)

    # 如果指定了创建配置文件
    if args.create_config_path:
        create_config_file(args.create_config_path, args.force)
        return

    logger.info("开始多租户集成测试")
    logger.info(f"测试模式: {args.mode}")
    logger.info(f"服务器URL: {args.server_url}")

    # 创建测试运行器
    runner = TestRunner(args.config_path)

    try:
        # 运行测试
        result = await runner.run_test(mode=args.mode, concurrent_users=args.concurrent_users)

        # 输出结果
        if "report" in result:
            print("\n" + "=" * 50)
            print(result["report"])
            print("=" * 50)

        # 保存结果到文件
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False, default=str)
            print(f"\n测试结果已保存到: {args.output}")

        # 输出关键指标
        if "concurrent_test" in result:
            concurrent = result["concurrent_test"]
            print("\n=== 关键指标 ===")
            print(f"并发用户数: {concurrent['concurrent_users']}")
            print(f"总消息数: {concurrent['total_messages_sent']}")
            print(f"成功率: {concurrent['overall_success_rate']:.2f}%")
            print(f"消息速率: {concurrent['messages_per_second']:.2f} msg/s")
            print(f"测试耗时: {concurrent['duration_seconds']:.2f} 秒")

        logger.info("测试完成")

    except KeyboardInterrupt:
        print("\n测试被用户中断")
    except Exception as e:
        logger.error(f"测试失败: {e}")
        raise


def main():
    """主函数"""
    args = parse_arguments()

    try:
        # 运行异步测试
        asyncio.run(run_test_with_args(args))
    except KeyboardInterrupt:
        print("\n程序被中断")
    except Exception as e:
        logger.error(f"程序执行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
