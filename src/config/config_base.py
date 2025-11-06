from dataclasses import dataclass, fields, MISSING
from typing import TypeVar, Type, Any, get_origin, get_args, Literal, get_type_hints

T = TypeVar("T", bound="ConfigBase")

TOML_DICT_TYPE = {
    int,
    float,
    str,
    bool,
    list,
    dict,
}


@dataclass
class ConfigBase:
    """配置类的基类"""

    @classmethod
    def from_dict(cls: Type[T], data: dict[str, Any]) -> T:
        """从字典加载配置字段"""
        if not isinstance(data, dict):
            raise TypeError(f"Expected a dictionary, got {type(data).__name__}")

        init_args: dict[str, Any] = {}
        type_hints = get_type_hints(cls)

        for f in fields(cls):
            field_name = f.name

            if field_name.startswith("_"):
                # 跳过以 _ 开头的字段
                continue

            if not f.init:
                # 跳过不参与 __init__ 的字段（例如常量字段）
                continue

            raw_value = data.get(field_name, MISSING)

            if raw_value is MISSING:
                if f.default is not MISSING:
                    init_args[field_name] = f.default
                    continue
                if f.default_factory is not MISSING:  # type: ignore[truthy-function]
                    init_args[field_name] = f.default_factory()  # type: ignore[call-arg]
                    continue
                raise ValueError(f"Missing required field: '{field_name}'")

            value = raw_value
            field_type = type_hints.get(field_name, f.type)

            try:
                init_args[field_name] = cls._convert_field(value, field_type)  # type: ignore
            except TypeError as e:
                raise TypeError(f"Field '{field_name}' has a type error: {e}") from e
            except Exception as e:
                raise RuntimeError(f"Failed to convert field '{field_name}' to target type: {e}") from e

        return cls(**init_args)

    @classmethod
    def _convert_field(cls, value: Any, field_type: Type[Any]) -> Any:
        """
        转换字段值为指定类型

        1. 对于嵌套的 dataclass，递归调用相应的 from_dict 方法
        2. 对于泛型集合类型（list, set, tuple），递归转换每个元素
        3. 对于基础类型（int, str, float, bool），直接转换
        4. 对于其他类型，尝试直接转换，如果失败则抛出异常
        """

        # 优先展开 tomlkit 的包装类型
        try:
            if hasattr(value, "unwrap"):
                value = value.unwrap()
        except Exception:
            pass

        # 如果是嵌套的 dataclass，递归调用 from_dict 方法
        if isinstance(field_type, type) and issubclass(field_type, ConfigBase):
            if not isinstance(value, dict):
                raise TypeError(f"Expected a dictionary for {field_type.__name__}, got {type(value).__name__}")
            return field_type.from_dict(value)

        # 处理泛型集合类型（list, set, tuple）
        field_origin_type = get_origin(field_type)
        field_type_args = get_args(field_type)

        if field_origin_type in {list, set, tuple}:
            expected_type_name = getattr(field_type, "__name__", getattr(field_origin_type, "__name__", str(field_type)))

            if field_origin_type is list:
                if not isinstance(value, list):
                    raise TypeError(f"Expected a list for {expected_type_name}, got {type(value).__name__}")
                iterable_value = value
                elem_type = field_type_args[0] if field_type_args else Any
                return [cls._convert_field(item, elem_type) for item in iterable_value]

            if field_origin_type is set:
                if not isinstance(value, (set, list, tuple)):
                    raise TypeError(f"Expected a set or list for {expected_type_name}, got {type(value).__name__}")
                iterable_value = list(value)
                elem_type = field_type_args[0] if field_type_args else Any
                return {cls._convert_field(item, elem_type) for item in iterable_value}

            if field_origin_type is tuple:
                if not isinstance(value, (list, tuple)):
                    raise TypeError(f"Expected a tuple or list for {expected_type_name}, got {type(value).__name__}")
                iterable_value = list(value)
                if field_type_args and len(field_type_args) == 2 and field_type_args[1] is Ellipsis:
                    elem_type = field_type_args[0]
                    if isinstance(elem_type, type) and issubclass(elem_type, ConfigBase):
                        return tuple(elem_type.from_dict(item) for item in iterable_value)
                    return tuple(cls._convert_field(item, elem_type) for item in iterable_value)
                if field_type_args and len(field_type_args) != 2 and len(iterable_value) != len(field_type_args):
                    raise TypeError(
                        f"Expected {len(field_type_args)} items for {expected_type_name}, got {len(iterable_value)}"
                    )
                if not field_type_args:
                    return tuple(iterable_value)
                converted_items = []
                for item, target_type in zip(iterable_value, field_type_args, strict=False):
                    converted_items.append(cls._convert_field(item, target_type))
                return tuple(converted_items)

        if field_origin_type is dict:
            # 检查提供的value是否为dict
            if not isinstance(value, dict):
                raise TypeError(f"Expected a dictionary for {field_type.__name__}, got {type(value).__name__}")

            # 检查字典的键值类型
            if len(field_type_args) != 2:
                raise TypeError(f"Expected a dictionary with two type arguments for {field_type.__name__}")
            key_type, value_type = field_type_args

            return {cls._convert_field(k, key_type): cls._convert_field(v, value_type) for k, v in value.items()}

        # 处理基础类型，例如 int, str 等
        if field_origin_type is type(None) and value is None:  # 处理Optional类型
            return None

        # 处理Literal类型
        if field_origin_type is Literal or get_origin(field_type) is Literal:
            # 获取Literal的允许值
            allowed_values = get_args(field_type)
            if value in allowed_values:
                return value
            else:
                raise TypeError(f"Value '{value}' is not in allowed values {allowed_values} for Literal type")

        if field_type is Any or isinstance(value, field_type):
            return value

        # 其他类型，尝试直接转换
        try:
            return field_type(value)
        except (ValueError, TypeError) as e:
            raise TypeError(f"Cannot convert {type(value).__name__} to {field_type.__name__}") from e

    def __str__(self):
        """返回配置类的字符串表示"""
        return f"{self.__class__.__name__}({', '.join(f'{f.name}={getattr(self, f.name)}' for f in fields(self))})"
