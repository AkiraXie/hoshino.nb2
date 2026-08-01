"""image_web —— 图片浏览站点后端。

统一入口::

    uv run python -m image_web {x,weibo} [--host H] [--port N] [--reload]

每个 provider 位于 ``image_web/<name>/server.py``，暴露 ``create_app()`` 与模块级
``app``，并在 ``image_web/registry.py`` 中登记。共享基础设施位于 ``image_web/common``。
"""
