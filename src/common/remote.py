"""Legacy telemetry module placeholder.

Telemetry 心跳已在 2025-12-09 被移除，此文件仅保留占位，防止旧版本 import 失败。
"""


class TelemetryHeartBeatTask:  # pragma: no cover - 防御性占位
    """兼容占位符，防止旧代码引用此类时报错。

    新版本不会再实例化此类；如仍被引用，将在初始化时报错提示开发者移除依赖。
    """

    def __init__(self, *_, **__):
        raise RuntimeError("TelemetryHeartBeatTask 已移除，请勿再实例化该模块。")
