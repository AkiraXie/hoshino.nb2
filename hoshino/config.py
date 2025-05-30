from __future__ import annotations
from nonebot.config import Config as BaseConfig
from pathlib import Path


class HoshinoConfig(BaseConfig):
    """Hoshino配置类"""

    # hoshino特有配置
    modules: list[str] = [
        "information",
        "interactive",
        "develop",
        "tools",
        "entertainment",
    ]
    data: str = "data"
    static: str = "static"
    zai: str = "はい！私はいつも貴方の側にいますよ！"
    debug: bool = False

    @property
    def data_dir(self) -> Path:
        """数据目录路径"""
        return Path(self.data).resolve()

    @property
    def static_dir(self) -> Path:
        """静态资源目录路径"""
        return Path(self.static).resolve()

    @property
    def modules_dir(self) -> Path:
        """模块目录路径"""
        return Path("hoshino/modules").resolve()

    class Config:
        env_file = ".env.prod"
        env_file_encoding = "utf-8"
        case_sensitive = False


# 全局配置实例
config = HoshinoConfig()
