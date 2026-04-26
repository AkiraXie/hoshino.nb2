from dataclasses import dataclass
from datetime import datetime

@dataclass
class LiveInfo:
    """直播推送信息"""

    title: str = ""
    """直播标题"""
    cover: str = ""
    """直播封面"""
    url: str = ""
    """直播链接"""
    anchor: str = ""
    """主播名称"""
    show_time: datetime = None
    """开播时间"""
    show_status: int = 0
    """直播状态，0-未开播，1-直播中，2-其他状态"""
    platform: str = "Unknown"
    """直播平台"""