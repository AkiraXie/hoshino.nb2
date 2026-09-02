from __future__ import annotations

from pathlib import Path

from nonebot.config import Config as BaseConfig
from pydantic import Field

from hoshino.ai.config import mount_into_hsnconfig


class HoshinoConfig(BaseConfig):
    """Hoshino配置类"""

    # hoshino特有配置
    # 用 default_factory 而非类级可变默认值：modules 是 pydantic-settings 字段，
    # 会从 .env.prod 的 MODULES 覆盖，ClassVar 会使其退化为静态默认值。
    modules: list[str] = Field(
        default_factory=lambda: [
            "information",
            "interactive",
            "develop",
            "tools",
            "entertainment",
            "ai",
        ]
    )
    data: str = "data"
    zai: str = "はい！私はいつも貴方の側にいますよ！"
    chrome_path: str = "./chrome-files"
    debug: bool = False

    @property
    def data_dir(self) -> Path:
        """数据目录路径"""
        return Path(self.data).resolve()

    @property
    def modules_dir(self) -> Path:
        """模块目录路径"""
        return Path("hoshino/modules").resolve()


# 注意：不要在这里定义 v1 风格 `class Config`（env_file 等）——它会替换
# nonebot 的 SettingsConfig，导致 pydantic-settings 对动态挂载字段（如 AI_*）
# 的 env 读取失效。继承 nonebot Config 的 model_config 即可（env_file 含
# .env.prod，case_sensitive=False）。AI 等插件字段由下方挂载机制动态加入。


def _mount_config_extensions(hsn_cls) -> None:
    """挂载 ``hoshino/ai/config.py`` 的 ``AIConfig`` → ``ai_*`` 字段（env ``AI_*``）。"""
    mount_into_hsnconfig(hsn_cls)


_mount_config_extensions(HoshinoConfig)

# 全局配置实例
config = HoshinoConfig()
