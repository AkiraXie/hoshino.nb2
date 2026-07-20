"""Hoshino 运行时初始化。必须在 nonebot.init() 后、nonebot.run() 前调用。"""

import nonebot

from hoshino.core import hooks
from hoshino.core.config import config as _config
from hoshino.platform.ob11.bootstrap import apply_patches
from hoshino.platform.ob11.events import GroupMsgEmojiLikeEvent, GroupReactionEvent
from hoshino.platform.ob11.types import Adapter as OB11Adapter


def bootstrap() -> None:
    driver = nonebot.get_driver()

    # 1. 创建数据目录
    _config.data_dir.mkdir(exist_ok=True)
    _config.static_dir.mkdir(exist_ok=True)
    data_dir = _config.data_dir
    for sub in ("favorite", "image", "db", "service", "video"):
        (data_dir / sub).mkdir(exist_ok=True)

    # 2. OB11-only patch and custom notice models.  Milky ships its reaction
    #    event natively, so it must not be made to depend on these extensions.
    if OB11Adapter.get_name() in nonebot.get_adapters():
        apply_patches()
        OB11Adapter.add_custom_model(GroupReactionEvent)
        OB11Adapter.add_custom_model(GroupMsgEmojiLikeEvent)

    # 4. 配置日志
    # Lazy import: hoshino.log imports hoshino.service state used by bootstrap patches.
    from hoshino.core.log import configure as _log_configure

    _log_configure()

    # 5. 下发所有延迟 hook 到真实 driver
    hooks.replay(driver)
