"""Task runtime：显式 Research/Plan 类任务的后台执行层。

Task 复用能力底座（``deps``/``providers``/``runner``/``persona``/``tools``/``skills``），
以独立 Task conversation 运行，不读写 ``#`` 即时聊天的对话历史。
"""
