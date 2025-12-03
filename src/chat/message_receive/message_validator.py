"""
消息验证器
提供消息隔离验证和格式兼容性检查
"""

import re
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass, field as dataclass_field
from datetime import datetime
from enum import Enum

from maim_message.message import BaseMessageInfo, Seg

from src.common.logger import get_logger
from .message import MessageRecv
from .isolated_message import IsolatedMessageRecv

# 导入隔离上下文
try:
    from ..isolation import (
        IsolationContext,
        IsolationScope,
        IsolationLevel,
        IsolationValidator as BaseIsolationValidator,
    )
except ImportError:
    # 兼容性处理
    class IsolationContext:
        pass

    class IsolationScope:
        pass

    class IsolationLevel:
        TENANT = "tenant"
        AGENT = "agent"
        PLATFORM = "platform"
        CHAT = "chat"

    class BaseIsolationValidator:
        def validate(self, *args, **kwargs):
            return ValidationResult(is_valid=True)


logger = get_logger("message_validator")


class ValidationSeverity(Enum):
    """验证严重程度"""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ValidationError:
    """验证错误"""

    code: str
    message: str
    severity: ValidationSeverity = ValidationSeverity.ERROR
    field: Optional[str] = None
    context: Dict[str, Any] = dataclass_field(default_factory=dict)

    def __str__(self) -> str:
        return f"[{self.severity.value.upper()}] {self.code}: {self.message}"


@dataclass
class ValidationResult:
    """验证结果"""

    is_valid: bool
    errors: List[ValidationError] = dataclass_field(default_factory=list)
    warnings: List[ValidationError] = dataclass_field(default_factory=list)
    metadata: Dict[str, Any] = dataclass_field(default_factory=dict)

    def add_error(self, error: ValidationError) -> None:
        """添加错误"""
        self.errors.append(error)
        if error.severity in [ValidationSeverity.ERROR, ValidationSeverity.CRITICAL]:
            self.is_valid = False

    def add_warning(self, warning: ValidationError) -> None:
        """添加警告"""
        self.warnings.append(warning)

    def has_errors(self) -> bool:
        """是否有错误"""
        return len(self.errors) > 0

    def has_warnings(self) -> bool:
        """是否有警告"""
        return len(self.warnings) > 0

    def get_critical_errors(self) -> List[ValidationError]:
        """获取严重错误"""
        return [e for e in self.errors if e.severity == ValidationSeverity.CRITICAL]

    def get_error_summary(self) -> str:
        """获取错误摘要"""
        if not self.has_errors():
            return "验证通过"

        critical_count = len(self.get_critical_errors())
        error_count = len(self.errors) - critical_count
        warning_count = len(self.warnings)

        parts = []
        if critical_count > 0:
            parts.append(f"{critical_count}个严重错误")
        if error_count > 0:
            parts.append(f"{error_count}个错误")
        if warning_count > 0:
            parts.append(f"{warning_count}个警告")

        return f"验证失败: {', '.join(parts)}"


class MessageFormatValidator:
    """消息格式验证器"""

    def __init__(self):
        self.required_fields = {
            "message_info": BaseMessageInfo,
            "message_segment": Seg,
        }
        self.optional_fields = {
            "raw_message": str,
            "processed_plain_text": str,
        }
        self.isolation_fields = {
            "tenant_id": str,
            "agent_id": str,
            "isolation_context": (IsolationContext, type(None)),
        }

    def validate_message_format(self, message_data: Dict[str, Any]) -> ValidationResult:
        """验证消息格式"""
        result = ValidationResult(is_valid=True)

        # 验证必需字段
        for field_name, field_type in self.required_fields.items():
            if field_name not in message_data:
                result.add_error(
                    ValidationError(
                        code="MISSING_REQUIRED_FIELD",
                        message=f"缺少必需字段: {field_name}",
                        field=field_name,
                        severity=ValidationSeverity.CRITICAL,
                    )
                )
            elif not isinstance(message_data[field_name], field_type):
                result.add_error(
                    ValidationError(
                        code="INVALID_FIELD_TYPE",
                        message=f"字段 {field_name} 类型错误，期望 {field_type.__name__}",
                        field=field_name,
                        context={
                            "expected_type": field_type.__name__,
                            "actual_type": type(message_data[field_name]).__name__,
                        },
                    )
                )

        # 验证可选字段类型
        for field_name, field_type in self.optional_fields.items():
            if field_name in message_data and message_data[field_name] is not None:
                if not isinstance(message_data[field_name], field_type):
                    result.add_error(
                        ValidationError(
                            code="INVALID_OPTIONAL_FIELD_TYPE",
                            message=f"可选字段 {field_name} 类型错误，期望 {field_type.__name__}",
                            field=field_name,
                            context={
                                "expected_type": field_type.__name__,
                                "actual_type": type(message_data[field_name]).__name__,
                            },
                            severity=ValidationSeverity.WARNING,
                        )
                    )

        # 验证隔离字段
        isolation_result = self._validate_isolation_fields(message_data)
        result.errors.extend(isolation_result.errors)
        result.warnings.extend(isolation_result.warnings)

        return result

    def _validate_isolation_fields(self, message_data: Dict[str, Any]) -> ValidationResult:
        """验证隔离字段"""
        result = ValidationResult(is_valid=True)

        has_isolation = any(field in message_data for field in self.isolation_fields)

        if not has_isolation:
            result.add_warning(
                ValidationError(
                    code="MISSING_ISOLATION_FIELDS",
                    message="消息缺少隔离字段，将使用默认隔离策略",
                    severity=ValidationSeverity.WARNING,
                )
            )
            return result

        # 验证隔离字段类型
        for field_name, field_type in self.isolation_fields.items():
            if field_name in message_data and message_data[field_name] is not None:
                expected_types = field_type if isinstance(field_type, tuple) else (field_type,)
                if not isinstance(message_data[field_name], expected_types):
                    result.add_error(
                        ValidationError(
                            code="INVALID_ISOLATION_FIELD_TYPE",
                            message=f"隔离字段 {field_name} 类型错误",
                            field=field_name,
                            context={"expected_types": [t.__name__ for t in expected_types]},
                        )
                    )

        # 验证隔离字段一致性
        if "tenant_id" in message_data and "agent_id" in message_data:
            if not message_data["tenant_id"] or not message_data["agent_id"]:
                result.add_error(
                    ValidationError(
                        code="EMPTY_ISOLATION_FIELDS",
                        message="tenant_id和agent_id不能为空",
                        severity=ValidationSeverity.ERROR,
                    )
                )

        return result


class IsolationConsistencyValidator:
    """隔离一致性验证器"""

    def __init__(self):
        self.allowed_isolation_levels = [
            IsolationLevel.TENANT,
            IsolationLevel.AGENT,
            IsolationLevel.PLATFORM,
            IsolationLevel.CHAT,
        ]

    def validate_isolation_consistency(self, message: Union[MessageRecv, IsolatedMessageRecv]) -> ValidationResult:
        """验证隔离一致性"""
        result = ValidationResult(is_valid=True)

        # 基本隔离信息验证
        if not message.tenant_id:
            result.add_error(
                ValidationError(
                    code="MISSING_TENANT_ID",
                    message="消息缺少tenant_id",
                    field="tenant_id",
                    severity=ValidationSeverity.CRITICAL,
                )
            )

        if not message.agent_id:
            result.add_error(
                ValidationError(
                    code="MISSING_AGENT_ID",
                    message="消息缺少agent_id",
                    field="agent_id",
                    severity=ValidationSeverity.CRITICAL,
                )
            )

        # 隔离上下文验证
        if message.isolation_context:
            context_result = self._validate_isolation_context(message)
            result.errors.extend(context_result.errors)
            result.warnings.extend(context_result.warnings)

        # 隔离级别验证
        isolation_level = message.get_isolation_level()
        if isolation_level not in self.allowed_isolation_levels:
            result.add_warning(
                ValidationError(
                    code="UNKNOWN_ISOLATION_LEVEL",
                    message=f"未知的隔离级别: {isolation_level}",
                    field="isolation_level",
                    context={"isolation_level": isolation_level, "allowed_levels": self.allowed_isolation_levels},
                )
            )

        # 聊天流隔离验证
        if hasattr(message, "chat_stream") and message.chat_stream:
            chat_result = self._validate_chat_stream_isolation(message)
            result.errors.extend(chat_result.errors)
            result.warnings.extend(chat_result.warnings)

        return result

    def _validate_isolation_context(self, message: Union[MessageRecv, IsolatedMessageRecv]) -> ValidationResult:
        """验证隔离上下文一致性"""
        result = ValidationResult(is_valid=True)

        context = message.isolation_context

        # 验证租户一致性
        if context.tenant_id != message.tenant_id:
            result.add_error(
                ValidationError(
                    code="TENANT_ID_MISMATCH",
                    message="隔离上下文的tenant_id与消息的tenant_id不匹配",
                    context={"context_tenant_id": context.tenant_id, "message_tenant_id": message.tenant_id},
                )
            )

        # 验证智能体一致性
        if context.agent_id != message.agent_id:
            result.add_error(
                ValidationError(
                    code="AGENT_ID_MISMATCH",
                    message="隔离上下文的agent_id与消息的agent_id不匹配",
                    context={"context_agent_id": context.agent_id, "message_agent_id": message.agent_id},
                )
            )

        # 验证平台一致性
        if hasattr(context, "platform") and context.platform:
            message_platform = getattr(message.chat_stream, "platform", None) if message.chat_stream else None
            if message_platform and context.platform != message_platform:
                result.add_warning(
                    ValidationError(
                        code="PLATFORM_MISMATCH",
                        message="隔离上下文的platform与聊天流的platform不匹配",
                        context={"context_platform": context.platform, "chat_stream_platform": message_platform},
                    )
                )

        return result

    def _validate_chat_stream_isolation(self, message: Union[MessageRecv, IsolatedMessageRecv]) -> ValidationResult:
        """验证聊天流隔离"""
        result = ValidationResult(is_valid=True)

        chat_stream = message.chat_stream

        # 验证聊天流的智能体ID
        if hasattr(chat_stream, "agent_id") and chat_stream.agent_id:
            if chat_stream.agent_id != message.agent_id:
                result.add_warning(
                    ValidationError(
                        code="CHAT_STREAM_AGENT_MISMATCH",
                        message="聊天流的agent_id与消息的agent_id不匹配",
                        context={"chat_stream_agent_id": chat_stream.agent_id, "message_agent_id": message.agent_id},
                    )
                )

        # 验证聊天流的租户ID
        if hasattr(chat_stream, "tenant_id") and chat_stream.tenant_id:
            if chat_stream.tenant_id != message.tenant_id:
                result.add_error(
                    ValidationError(
                        code="CHAT_STREAM_TENANT_MISMATCH",
                        message="聊天流的tenant_id与消息的tenant_id不匹配",
                        context={
                            "chat_stream_tenant_id": chat_stream.tenant_id,
                            "message_tenant_id": message.tenant_id,
                        },
                    )
                )

        return result


class MessageIntegrityValidator:
    """消息完整性验证器"""

    def __init__(self):
        self.max_message_length = 10000  # 最大消息长度
        self.max_text_length = 5000  # 最大文本长度
        self.forbidden_patterns = [
            r"<script[^>]*>.*?</script>",  # 脚本标签
            r"javascript:",  # JavaScript协议
            r"data:text/html",  # HTML数据URI
        ]

    def validate_message_integrity(self, message: Union[MessageRecv, IsolatedMessageRecv]) -> ValidationResult:
        """验证消息完整性"""
        result = ValidationResult(is_valid=True)

        # 验证消息ID
        if not message.message_info or not message.message_info.message_id:
            result.add_error(
                ValidationError(
                    code="MISSING_MESSAGE_ID",
                    message="消息缺少message_id",
                    field="message_info.message_id",
                    severity=ValidationSeverity.ERROR,
                )
            )

        # 验证消息时间
        if message.message_info and message.message_info.time:
            message_time = message.message_info.time
            current_time = datetime.now().timestamp()
            if abs(current_time - message_time) > 86400:  # 24小时
                result.add_warning(
                    ValidationError(
                        code="MESSAGE_TIME_TOO_OLD",
                        message="消息时间戳过于陈旧",
                        field="message_info.time",
                        context={"message_time": message_time, "current_time": current_time},
                    )
                )

        # 验证消息长度
        text_length = len(message.processed_plain_text)
        if text_length > self.max_text_length:
            result.add_warning(
                ValidationError(
                    code="MESSAGE_TOO_LONG",
                    message=f"消息文本过长: {text_length} > {self.max_text_length}",
                    context={"text_length": text_length, "max_length": self.max_text_length},
                )
            )

        # 验证安全性
        security_result = self._validate_message_security(message)
        result.errors.extend(security_result.errors)
        result.warnings.extend(security_result.warnings)

        return result

    def _validate_message_security(self, message: Union[MessageRecv, IsolatedMessageRecv]) -> ValidationResult:
        """验证消息安全性"""
        result = ValidationResult(is_valid=True)

        text = message.processed_plain_text

        # 检查危险模式
        for pattern in self.forbidden_patterns:
            if re.search(pattern, text, re.IGNORECASE | re.DOTALL):
                result.add_error(
                    ValidationError(
                        code="DANGEROUS_CONTENT",
                        message=f"消息包含危险内容: {pattern}",
                        severity=ValidationSeverity.CRITICAL,
                        context={"pattern": pattern},
                    )
                )

        # 检查可疑内容
        suspicious_patterns = [
            r"password\s*[:=]\s*\S+",
            r"token\s*[:=]\s*\S+",
            r"api_key\s*[:=]\s*\S+",
        ]

        for pattern in suspicious_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                result.add_warning(
                    ValidationError(
                        code="SUSPICIOUS_CONTENT", message=f"消息包含可疑内容: {pattern}", context={"pattern": pattern}
                    )
                )

        return result


class MessageValidator:
    """综合消息验证器"""

    def __init__(self):
        self.format_validator = MessageFormatValidator()
        self.isolation_validator = IsolationConsistencyValidator()
        self.integrity_validator = MessageIntegrityValidator()

        # 基础隔离验证器
        try:
            self.base_isolation_validator = BaseIsolationValidator()
        except Exception:
            self.base_isolation_validator = None

    async def validate_message_data(self, message_data: Dict[str, Any]) -> ValidationResult:
        """验证消息数据字典"""
        # 格式验证
        format_result = self.format_validator.validate_message_format(message_data)

        # 创建临时消息实例进行进一步验证
        try:
            from .message import MessageRecv

            # 检查是否在异步上下文中
            import asyncio

            try:
                asyncio.get_running_loop()
                # 在异步上下文中，使用await
                temp_message = await MessageRecv.from_dict(message_data)
            except RuntimeError:
                # 不在异步上下文中，创建新的事件循环
                temp_message = asyncio.run(MessageRecv.from_dict(message_data))

            # 隔离一致性验证
            isolation_result = self.isolation_validator.validate_isolation_consistency(temp_message)

            # 完整性验证
            integrity_result = self.integrity_validator.validate_message_integrity(temp_message)

            # 合并结果
            result = ValidationResult(is_valid=True)
            result.errors.extend(format_result.errors)
            result.errors.extend(isolation_result.errors)
            result.errors.extend(integrity_result.errors)
            result.warnings.extend(format_result.warnings)
            result.warnings.extend(isolation_result.warnings)
            result.warnings.extend(integrity_result.warnings)

            return result

        except Exception as e:
            format_result.add_error(
                ValidationError(
                    code="MESSAGE_CREATION_FAILED",
                    message=f"无法从数据创建消息实例: {str(e)}",
                    severity=ValidationSeverity.CRITICAL,
                    context={"exception": str(e)},
                )
            )
            return format_result

    def validate_message(self, message: Union[MessageRecv, IsolatedMessageRecv]) -> ValidationResult:
        """验证消息对象"""
        # 隔离一致性验证
        isolation_result = self.isolation_validator.validate_isolation_consistency(message)

        # 完整性验证
        integrity_result = self.integrity_validator.validate_message_integrity(message)

        # 基础隔离验证
        base_result = ValidationResult(is_valid=True)
        if self.base_isolation_validator:
            try:
                base_validation = self.base_isolation_validator.validate(message)
                if not base_validation.is_valid:
                    for error in base_validation.errors:
                        base_result.add_error(
                            ValidationError(
                                code=f"BASE_{error.code}",
                                message=f"基础隔离验证失败: {error.message}",
                                severity=ValidationSeverity.ERROR,
                                context=error.context,
                            )
                        )
            except Exception as e:
                base_result.add_warning(
                    ValidationError(
                        code="BASE_VALIDATION_FAILED",
                        message=f"基础隔离验证器执行失败: {str(e)}",
                        severity=ValidationSeverity.WARNING,
                    )
                )

        # 合并结果
        result = ValidationResult(is_valid=True)
        result.errors.extend(isolation_result.errors)
        result.errors.extend(integrity_result.errors)
        result.errors.extend(base_result.errors)
        result.warnings.extend(isolation_result.warnings)
        result.warnings.extend(integrity_result.warnings)
        result.warnings.extend(base_result.warnings)

        return result

    def validate_isolated_message(self, message: IsolatedMessageRecv) -> ValidationResult:
        """验证隔离化消息"""
        result = self.validate_message(message)

        # 额外的隔离化消息验证
        if not message.isolated_message_id:
            result.add_error(
                ValidationError(
                    code="MISSING_ISOLATED_MESSAGE_ID",
                    message="隔离化消息缺少isolated_message_id",
                    field="isolated_message_id",
                    severity=ValidationSeverity.ERROR,
                )
            )

        # 验证隔离元数据
        if not message.isolation_metadata:
            result.add_warning(
                ValidationError(
                    code="MISSING_ISOLATION_METADATA",
                    message="隔离化消息缺少isolation_metadata",
                    field="isolation_metadata",
                )
            )

        # 验证跨隔离标记
        if message.is_cross_isolation_message():
            result.add_warning(
                ValidationError(
                    code="CROSS_ISOLATION_MESSAGE",
                    message="消息标记为跨隔离边界",
                    context={
                        "cross_tenant": message.is_cross_tenant,
                        "cross_agent": message.is_cross_agent,
                        "cross_platform": message.is_cross_platform,
                    },
                )
            )

        return result

    def validate_compatibility(self, message: Union[MessageRecv, IsolatedMessageRecv]) -> ValidationResult:
        """验证向后兼容性"""
        result = ValidationResult(is_valid=True)

        # 检查兼容性字段
        if not hasattr(message, "message_info"):
            result.add_error(
                ValidationError(
                    code="MISSING_COMPATIBILITY_FIELD",
                    message="消息缺少兼容性字段: message_info",
                    field="message_info",
                    severity=ValidationSeverity.CRITICAL,
                )
            )

        if not hasattr(message, "message_segment"):
            result.add_error(
                ValidationError(
                    code="MISSING_COMPATIBILITY_FIELD",
                    message="消息缺少兼容性字段: message_segment",
                    field="message_segment",
                    severity=ValidationSeverity.CRITICAL,
                )
            )

        # 检查方法兼容性
        required_methods = ["get_isolation_level", "get_isolation_scope", "ensure_isolation_context"]
        for method_name in required_methods:
            if not hasattr(message, method_name) or not callable(getattr(message, method_name)):
                result.add_error(
                    ValidationError(
                        code="MISSING_COMPATIBILITY_METHOD",
                        message=f"消息缺少兼容性方法: {method_name}",
                        field=method_name,
                        severity=ValidationSeverity.ERROR,
                    )
                )

        return result


# 全局验证器实例
_message_validator = None


def get_message_validator() -> MessageValidator:
    """获取全局消息验证器实例"""
    global _message_validator
    if _message_validator is None:
        _message_validator = MessageValidator()
    return _message_validator


async def validate_message_data(message_data: Dict[str, Any]) -> ValidationResult:
    """验证消息数据字典（便捷函数）"""
    validator = get_message_validator()
    return await validator.validate_message_data(message_data)


def validate_message(message: Union[MessageRecv, IsolatedMessageRecv]) -> ValidationResult:
    """验证消息对象（便捷函数）"""
    validator = get_message_validator()
    return validator.validate_message(message)


def validate_isolated_message(message: IsolatedMessageRecv) -> ValidationResult:
    """验证隔离化消息（便捷函数）"""
    validator = get_message_validator()
    return validator.validate_isolated_message(message)


def validate_compatibility(message: Union[MessageRecv, IsolatedMessageRecv]) -> ValidationResult:
    """验证向后兼容性（便捷函数）"""
    validator = get_message_validator()
    return validator.validate_compatibility(message)
