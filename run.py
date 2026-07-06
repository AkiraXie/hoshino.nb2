import nonebot
from nonebot.adapters.onebot.v11 import Adapter


# 使用自定义配置初始化nonebot
nonebot.init()
driver = nonebot.get_driver()
driver.register_adapter(Adapter)

# 必须在任何 hoshino 模块导入之前加载 alconna ——
# hoshino 的 import 链（bootstrap → platform.message/target → nonebot_plugin_alconna.uniseg）
# 会把它当作普通模块 import；若此刻尚未作为 plugin 注册，NoneBot 会抛
# RuntimeError: not loaded as a plugin，所有 Alconna matcher 静默失效。
nonebot.load_plugin("nonebot_plugin_apscheduler")
nonebot.load_plugin("nonebot_plugin_alconna")

# 延后到 alconna 注册完成后再 import hoshino
from hoshino import config
from hoshino.bootstrap import bootstrap

base = "hoshino/base/"

bootstrap()

nonebot.load_plugins(base)

if modules := config.modules:
    for module in modules:
        print(f"加载模块: {module}")
        nonebot.load_plugins(config.modules_dir / module)


def main():
    nonebot.run()


if __name__ == "__main__":
    main()
