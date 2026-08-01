"""provider 注册表：name -> (后端模块路径, 默认后端端口)。

新增 provider：创建 ``image_web/<name>/server.py``（暴露 ``create_app()`` 与模块级
``app``），并在下方登记一行即可被统一入口识别。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderSpec:
    module: str
    default_port: int


PROVIDERS: dict[str, ProviderSpec] = {
    "x": ProviderSpec(module="image_web.x.server", default_port=9997),
    "weibo": ProviderSpec(module="image_web.weibo.server", default_port=9998),
}
