import json
import glob


def check_agent_errors():
    """检查日志文件中的Agent相关错误"""
    logs = glob.glob("logs/*.log.jsonl")
    logs.sort(reverse=True)  # 按时间倒序排列

    print("检查最新的5个日志文件...")
    found_errors = []

    for log in logs[:5]:
        print(f"\n检查文件: {log}")
        try:
            with open(log, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        event = str(entry.get("event", "")).lower()
                        logger = str(entry.get("logger_name", "")).lower()

                        # 检查是否包含agent相关错误
                        if "agent" in event or "agent" in logger:
                            if "error" in event or "exception" in event or entry.get("level") in ["error", "exception"]:
                                print(f"找到Agent错误: {entry}")
                                found_errors.append(entry)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"读取文件 {log} 时出错: {e}")

    if not found_errors:
        print("\n未找到Agent相关的错误信息")
    else:
        print(f"\n总共找到 {len(found_errors)} 个Agent相关错误")

    return found_errors


if __name__ == "__main__":
    check_agent_errors()
