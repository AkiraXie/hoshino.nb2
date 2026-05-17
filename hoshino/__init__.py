"""HoshinoBot - 核心包。import 此模块不需 nonebot.init()。"""
from .config import config

hsn_nickname = next(iter(config.nickname), "Hoshino")
fav_dir     = config.data_dir / "favorite"
img_dir     = config.data_dir / "image"
db_dir      = config.data_dir / "db"
service_dir = config.data_dir / "service"
video_dir   = config.data_dir / "video"
data_dir    = config.data_dir
