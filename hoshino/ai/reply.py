"""回复交付形态：纯文本消息 or Markdown 图片。

chat surface 的最终回复有两种形态，交付前必须先定下来：

- **text**：纯文本消息，聊天框里直接显示、能随手复制；不允许任何 Markdown 语法。
- **image**：Markdown → PNG，适合分节分点、需要排版才看得清的长内容。

形态由 ``reply`` **输出工具**决定（``providers.build_agent`` 把它挂进 chat 的
``output_type``）：模型调它一次，就把「形态 + 正文」一起交出来，run 随之结束，
``result.output`` 是 ``Reply``。模型没调工具时（直接写文字终局）由
``needs_image`` 按内容判定：写了 Markdown 语法就是 Markdown（走图片），
没写就是纯文本（走文字消息）——与「Markdown 图片 / 纯文本消息」这个二分一致。

本模块是「形态判定 + 纯文本化」的纯逻辑，加一个输出工具函数；判定与转换部分不依赖
会话状态，可直接单独调用（``to_delivery`` / ``to_plain_text`` / ``needs_image``）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from loguru import logger
from pydantic_ai import ModelRetry, RunContext

from . import preamble
from .deps import AgentDeps

ReplyFormat = Literal["text", "image"]

# 工具名即模型看到的名字：它交付的就是「回复」本身，不是某个副作用的开关。
TOOL_NAME = "reply"


@dataclass(frozen=True, slots=True)
class Reply:
    """一次交付：正文 + 形态。"""

    content: str
    format: ReplyFormat


async def deliver_reply(
    ctx: RunContext[AgentDeps],
    content: str,
    format: ReplyFormat,
) -> Reply:
    """交付本轮回复给用户，并决定它是纯文本消息还是 Markdown 图片。

    调用本工具即结束本轮：调用后不要再输出任何文字，也要等其它工具
    （搜索 / 抓取 / 看图 / 读文件等）都调完之后再调它。

    format 按「用户拿到这条回复要做什么」二选一：

    - text：纯文本消息，聊天框里直接显示、能随手复制。
      硬性要求：content 里不要出现任何 Markdown 语法——不写 # 标题、**加粗**、
      - 列表、| 表格 |、``` 代码围栏、`行内代码`、[链接](url)、$公式$；也不要
      以 # 开头（会被当成指令再次触发机器人）。要用户复制走的命令、代码、配置，
      直接写成一行行普通文字。
      用于：闲聊寒暄与简短回答；结论、建议、说明一件事；搜索结果 / 天气 / 价格 /
      时间等「念出来就行」的事实；OCR、读图、翻译等原文复述；用户要复制走的内容；
      用户说了「发文字」「直接打字」。
    - image：把 Markdown 渲染成图片，可以用完整 Markdown——标题、加粗、列表、
      表格、代码块、行内代码、LaTeX 公式。
      用于需要「排版才看得清」的成篇内容：调研与资料整理、多对象或多方案对比、
      归纳总结、时间线 / 信息流 / 历史脉络讲述、知识讲解与教程、长篇结构化说明；
      用户说了「整理成图」「做张图」。

    拿不准时：一句话能说清、或者用户只关心内容本身（要读要抄要复制）→ text；
    内容要分节分点对照着看、长到在聊天框里会糊成一团 → image。
    倾向 text：短回答没做成图片不会更差，闲聊被做成图片却很难用。
    """
    text = content.strip()
    if not text:
        raise ModelRetry("回复内容不能为空：把要对用户说的完整内容放进 content。")
    preamble.guard_preamble(ctx, text, source=TOOL_NAME)
    return Reply(content=text, format=format)


# ------------------------------------------------------------ Markdown 形态判定

# 出现任何一条即认为「模型写的是 Markdown」→ 走图片。
# 与 output.md 的规范一一对应：这些语法只该在图片形态里出现。
_MARKDOWN_MARKERS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+\S", re.M),  # 标题
    re.compile(r"^[ \t]{0,3}(?:```|~~~)", re.M),  # 代码围栏
    re.compile(r"^[ \t]*\|.*\|", re.M),  # 表格行
    re.compile(r"^[ \t]{0,3}[-*+][ \t]+\S", re.M),  # 无序列表
    re.compile(r"^[ \t]{0,3}\d+[.)][ \t]+\S", re.M),  # 有序列表
    re.compile(r"^[ \t]{0,3}>[ \t]?\S", re.M),  # 引用
    re.compile(r"^[ \t]{0,3}(?:[-*_][ \t]*){3,}$", re.M),  # 分隔线
    re.compile(r"\*\*[^*\n]+\*\*"),  # 加粗
    re.compile(r"~~[^~\n]+~~"),  # 删除线
    re.compile(r"`[^`\n]+`"),  # 行内代码
    re.compile(r"!?\[[^\]\n]+\]\([^)\s]+[^)]*\)"),  # 链接 / 图片
    re.compile(r"\$\$"),  # 块级公式
)


def needs_image(text: str) -> bool:
    """文本终局时判定形态：含 Markdown 语法 → 图片，否则纯文本。"""
    return any(marker.search(text) for marker in _MARKDOWN_MARKERS)


def to_delivery(output: object) -> Reply:
    """把 run 输出归一为可交付的 ``Reply``。

    - 模型调过 reply 工具 → 用它声明的形态，不再替它猜；
    - 文本终局 → 按内容判定（``needs_image``）。

    text 形态统一过一遍 ``to_plain_text``：模型偶发漏写的 Markdown 语法由这里
    兜底抹掉，保证发出去的消息是纯文本。
    """
    if isinstance(output, Reply):
        fmt, content = output.format, output.content
    else:
        content = str(output)
        fmt = "image" if needs_image(content) else "text"
    if fmt == "text":
        plain = to_plain_text(content)
        if plain != content:
            logger.debug("AI 纯文本回复抹掉 Markdown 语法 chars={}→{}", len(content), len(plain))
        return Reply(content=plain, format="text")
    return Reply(content=content, format="image")


# ------------------------------------------------------------ Markdown → 纯文本

_FENCE_LINE_RE = re.compile(r"^[ \t]{0,3}(?:```|~~~)")
_HEADING_RE = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+")
_QUOTE_RE = re.compile(r"^[ \t]{0,3}>[ \t]?")
_RULE_RE = re.compile(r"^[ \t]{0,3}(?:[-*_][ \t]*){3,}$")
_TABLE_SEP_RE = re.compile(r"^[ \t]*\|?[ \t]*:?-{2,}[ \t:|-]*\|?[ \t]*$")
_LIST_RE = re.compile(r"^([ \t]*)[-*+][ \t]+")
_IMAGE_RE = re.compile(r"!\[([^\]\n]*)\]\(([^)\s]+)[^)]*\)")
_LINK_RE = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)[^)]*\)")
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_BOLD_RE = re.compile(r"\*\*([^*\n]+)\*\*|__([^_\n]+)__")
_STRIKE_RE = re.compile(r"~~([^~\n]+)~~")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def _plain_line(line: str) -> str:
    """单行 Markdown → 纯文本（空行保留分段，表格对齐行与分隔线整行丢弃）。"""
    if not line.strip():
        return line
    if _RULE_RE.match(line) or _TABLE_SEP_RE.match(line):
        return ""
    line = _HEADING_RE.sub("", line)
    line = _QUOTE_RE.sub("", line)
    if line.strip().startswith("|"):
        line = line.strip().strip("|").strip()
    line = _LIST_RE.sub(r"\1• ", line)
    line = _IMAGE_RE.sub(r"\1 (\2)", line)
    line = _LINK_RE.sub(r"\1 (\2)", line)
    line = _INLINE_CODE_RE.sub(r"\1", line)
    line = _BOLD_RE.sub(lambda m: m.group(1) or m.group(2), line)
    return _STRIKE_RE.sub(r"\1", line)


def to_plain_text(text: str) -> str:
    """Markdown → 纯文本：保留全部文字与代码内容，只抹掉语法标记。

    代码围栏内的内容原样保留（缩进、``#`` 注释、``-`` 开头都不能动，否则复制出去
    就废了），只丢掉围栏行本身。仅作 ``text`` 形态的兜底：正常路径下模型本来就
    该按纯文本写，这里只处理零星残留。
    """
    lines: list[str] = []
    in_fence = False
    for line in text.split("\n"):
        if _FENCE_LINE_RE.match(line):
            in_fence = not in_fence
            continue
        lines.append(line if in_fence else _plain_line(line))
    return _BLANK_LINES_RE.sub("\n\n", "\n".join(lines)).strip()
