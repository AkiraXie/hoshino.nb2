from hoshino.core.service import Service

from .config import XSettings

sv = Service("x", enable_on_default=False, visible=False, config_type=XSettings)


__all__ = ["sv"]
