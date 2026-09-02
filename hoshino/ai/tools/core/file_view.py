"""core/file_view：读取聊天附件和工作目录内的文本、HTML、PDF、图片。"""

from pydantic_ai import RunContext

from ... import documents
from ...deps import AgentDeps


async def file_view(
    ctx: RunContext[AgentDeps],
    source: str,
    start_line: int | None = None,
    end_line: int | None = None,
):
    """查看一个本地附件/工作目录文件或 HTTP(S) 文件 URL。

    支持 txt、md、html、pdf 和图片。PDF 使用专用解析；不要用 web_fetch 解析 PDF。
    """
    return await documents.file_view(
        source,
        config=ctx.deps.config,
        deps=ctx.deps,
        start_line=start_line,
        end_line=end_line,
    )


tool = file_view
