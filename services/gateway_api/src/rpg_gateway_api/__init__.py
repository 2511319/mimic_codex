"""Gateway API сервис для Telegram Mini App."""

from .app import create_app
from .version import __version__

__all__ = ["create_app", "__version__"]
