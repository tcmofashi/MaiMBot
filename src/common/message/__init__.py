"""Maim Message - A message handling library"""

__version__ = "0.1.0"

from .api import get_global_api, set_global_message_handler


__all__ = [
    "get_global_api",
    "set_global_message_handler",
]
