"""Hoshino 运行时初始化。必须在 nonebot.init() 后、nonebot.run() 前调用。"""

import nonebot

from hoshino.platform.ob11.bootstrap import apply_patches
from hoshino.platform.ob11.events import GroupReactionEvent, GroupMsgEmojiLikeEvent
from hoshino.platform.ob11.types import Adapter
from hoshino.core.config import config as _config
from hoshino.core import hooks


def bootstrap() -> None:
    driver = nonebot.get_driver()

    # 1. 创建数据目录
    _config.data_dir.mkdir(exist_ok=True)
    _config.static_dir.mkdir(exist_ok=True)
    data_dir = _config.data_dir
    for sub in ("favorite", "image", "db", "service", "video"):
        (data_dir / sub).mkdir(exist_ok=True)

    # 2. 应用 OB11 运行时 patch
    apply_patches()

    # 3. 注册自定义事件模型
    Adapter.add_custom_model(GroupReactionEvent)
    Adapter.add_custom_model(GroupMsgEmojiLikeEvent)

    # 4. 配置日志
    # Lazy import: hoshino.log imports hoshino.service state used by bootstrap patches.
    from hoshino.core.log import configure as _log_configure
    _log_configure()

    # 5. 下发所有延迟 hook 到真实 driver
    hooks.replay(driver)
