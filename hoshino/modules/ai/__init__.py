"""AI 业务分类：本目录只放 NoneBot 插件。

``chat.py``（``#`` 聊天）、``ai_admin.py``（``ai`` 管理命令）、``task_commands.py``
（``ai task`` 命令与 scheduler 注册）、``zssm.py``（``zssm`` 解释命令）是全部插件；AI 基建位于 ``hoshino.ai`` 包，
插件通过 ``from hoshino.ai import ...`` 引用。

注意：本包 ``__init__`` 保持 docstring-only —— ``nonebot.load_plugins`` 扫描本目录
时先 import 包本身，任何会把 ``hoshino.ai`` 链（含 nonebot 相关模块）提前加载的
import 都会在 ``controlled_modules`` 建立前触发 "Module ... is not loaded as a
plugin!"。
"""
