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
        "ai",
    ]
    data: str = "data"
    static: str = "static"
    zai: str = "はい！私はいつも貴方の側にいますよ！"
    chrome_path: str = "./chrome-files"
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


# 注意：不要在这里定义 v1 风格 `class Config`（env_file 等）——它会替换
# nonebot 的 SettingsConfig，导致 pydantic-settings 对动态挂载字段（如 AI_*）
# 的 env 读取失效。继承 nonebot Config 的 model_config 即可（env_file 含
# .env.prod，case_sensitive=False）。AI 等插件字段由下方挂载机制动态加入。


def _mount_config_extensions(hsn_cls) -> None:
    """触发各插件配置挂载（字段定义在各自模块，这里只调用，避免循环导入）。

    当前挂载：``hoshino/ai/config.py`` 的 ``AIConfig`` → ``ai_*`` 字段
    （env 名 ``AI_*``，写于 .env.prod / .env.prod.example）。
    """
    try:
        from hoshino.ai.config import mount_into_hsnconfig
    except ImportError:
        return
    mount_into_hsnconfig(hsn_cls)


_mount_config_extensions(HoshinoConfig)

# 全局配置实例
config = HoshinoConfig()
