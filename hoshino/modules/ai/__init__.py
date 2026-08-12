"""AI 业务分类。

公共 AI 基建（config / store / providers / base / metrics / rendering /
persona / context）不 ``import nonebot``，因此不会被 ``nonebot.load_plugins``
当作插件加载；``chat.py`` 与 ``ai_admin.py`` 是真正的 NoneBot 插件。
本模块仅做包标记，不注册任何 matcher。
"""
