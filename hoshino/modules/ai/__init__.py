"""AI 业务分类。

公共 AI 基建（config / store / providers / base / metrics / rendering /
persona / context / deps）不 ``import nonebot``，因此不会被
``nonebot.load_plugins`` 当作插件加载；``chat.py`` 与 ``ai_admin.py`` 是真正的
NoneBot 插件。``task/commands.py`` 同样是插件（``ai task`` NORMAL matcher 与
scheduler hooks），因位于子包目录不会被 ``load_plugins`` 遍历，由 ``ai_admin``
在插件加载期显式导入完成注册。

注意：这里不能直接 ``import`` task 子包 —— 它会把 ``providers`` 等模块链提前到
``load_plugins`` 的 ``controlled_modules`` 建立之前加载，触发
"Module ... is not loaded as a plugin!"。
"""
