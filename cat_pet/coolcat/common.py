"""兼容聚合层；新代码应优先从具体职责模块导入。"""

from .runtime import *
from .config import *
from .platform.windows import *
from .platform.autostart import *
from .platform.hotkeys import *

__all__ = [name for name in globals() if not name.startswith('__')]
