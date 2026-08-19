"""CoolCat 应用包的稳定公共接口。"""

from .config import CONFIG_PATH, DEFAULT_CONFIG, load_config, save_config
from .runtime import BASE_DIR, CAT_STYLES, COLORS
from .detection import CameraThread
from .platform.autostart import (
    AUTOSTART_REG_NAME, AUTOSTART_REG_PATH, _autostart_command,
    is_autostart_enabled, set_autostart,
)
from .ui.dialogs import AuthDialog, SettingsDialog, StyledMessageDialog
from .cat_window import CatWindow

__all__ = [
    "AuthDialog", "AUTOSTART_REG_NAME", "AUTOSTART_REG_PATH", "BASE_DIR",
    "CameraThread", "CatWindow", "CAT_STYLES", "COLORS", "CONFIG_PATH",
    "DEFAULT_CONFIG", "SettingsDialog", "StyledMessageDialog",
    "_autostart_command", "is_autostart_enabled", "load_config",
    "save_config", "set_autostart",
]
