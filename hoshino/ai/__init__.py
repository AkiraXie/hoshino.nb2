"""hoshino.ai：AI 能力基建包（非插件）。

包含 config / store / providers / provider / base / sessions / context / runner /
tools / task 等基础设施，供 ``hoshino/modules/ai`` 下的插件（chat、ai_admin、
task_commands）使用。本包不会被 ``nonebot.load_plugins`` 扫描（扫描路径固定为
``hoshino/modules/<category>``），因此模块命名无需 ``_`` 前缀；``__init__`` 保持
docstring-only，插件一律 ``from hoshino.ai.<submodule>`` 直连子模块。
"""
