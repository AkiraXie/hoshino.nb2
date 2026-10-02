"""回复交付形态：纯文本消息 or Markdown 图片。

chat surface 的最终回复有两种形态，交付前必须先定下来，规则是硬的（**必须（MUST）**
/ **禁止（MUST NOT）** / **应当（SHOULD）** / **绝不（NEVER）** 级别）：

- **text**：纯文本消息，聊天框里直接显示、能随手复制；**禁止（MUST NOT）** 含任何
  Markdown 语法或排版意图（标题、加粗、列表、表格、代码围栏、行内代码、链接、公式、
  项目符号 / 中文序号 / 【小标题】这类「看起来像排版」的写法都算）。发出前按
  自然段与 140~210 字浮动窗口分段，多条整合成一条合并转发聊天记录发出。
- **image**：Markdown → PNG，**应当（SHOULD）** 用于需要排版才看得清的长内容。

**图片是保底**。判定顺序（``to_delivery``）：

1. 正文里出现 Markdown / 排版记号 → 一律 image，模型声明的 text 也会被改判
   （``escalated``）——Markdown 只允许出现在图片里；
2. 没有排版记号时，模型调过 ``reply`` 工具就按它声明的形态；
3. 模型直接写文字终局（没调工具）时按内容判定：干净的口语化文字走 text，
   含排版记号走 image（同 1）。

形态由 ``reply`` **输出工具**决定（``providers.build_agent`` 把它挂进 chat 的
``output_type``）：模型调它一次就把「形态 + 正文」一起交出来，run 随之结束，
``result.output`` 是 ``Reply``。

本模块是「形态判定 + 分段」的纯逻辑，加一个输出工具函数；判定与分段部分不依赖
会话状态，可直接单独调用（``to_delivery`` / ``split_plain_text`` / ``needs_image``）。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from loguru import logger
from pydantic_ai import ModelRetry, RunContext

from . import preamble
from .deps import AgentDeps

ReplyFormat = Literal["text", "image"]

# 工具名即模型看到的名字：它交付的就是「回复」本身，不是某个副作用的开关。
TOOL_NAME = "reply"

# 纯文本分段窗口（微博/推特长度量级）：只在单段超长时才按句子边界切，
# 目标是把每条消息控制在 min~max 之间，避免一条几十行的文字墙。
SEGMENT_MIN_CHARS = 140
SEGMENT_MAX_CHARS = 210


@dataclass(frozen=True, slots=True)
class Reply:
    """模型通过 ``reply`` 工具声明的一次交付：正文 + 形态（+ 可选来源）。"""

    content: str
    format: ReplyFormat
    sources: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Delivery:
    """归一后的最终交付（供发送与日志）。

    ``source``：形态来自模型显式选择还是文本终局自动判定；``escalated`` 记录
    「声明 text 但正文含 Markdown，被改判为图片」这一次数（观测用）；``sources``
    是模型声明的来源链接，只在纯文本形态保留（图片形态不用来源）。
    """

    content: str
    format: ReplyFormat
    source: Literal["tool", "auto"]
    escalated: bool = False
    sources: tuple[str, ...] = ()


async def deliver_reply(
    ctx: RunContext[AgentDeps],
    content: str,
    format: ReplyFormat,
    sources: list[str] | None = None,
) -> Reply:
    """交付本轮回复给用户，并决定它是纯文本消息还是 Markdown 图片。

    调用本工具即结束本轮：**必须（MUST）** 在搜索 / 抓取 / 看图 / 读文件等工具都调完
    之后再调它，**禁止（MUST NOT）** 调用后再输出任何文字。

    format 二选一，规则是硬约束（**必须（MUST）** / **禁止（MUST NOT）** /
    **应当（SHOULD）** / **绝不（NEVER）** 级别），违反会被系统改判：

    - text：纯文本消息，给用户能读、能随手复制的文字。
      - **必须（MUST）** 平铺直叙：一段段普通的话，想到什么说什么。
      - **禁止（MUST NOT）** 出现任何 Markdown 语法或排版记号：# 标题、**加粗**、
        - 列表、| 表格 |、``` 代码围栏、`行内代码`、[链接](url)、$公式$、
        • 项目符号、一、/ 1、这类序号、【小标题】。
      - **禁止（MUST NOT）** 用换行、缩进、序号做视觉排版（空行只用来分自然段）；
        也 **禁止（MUST NOT）** 以 # 开头（会被当成指令再次触发机器人）。
      - 系统发送前会检查正文：只要检出 Markdown，这一条就会强制按图片发出，
        用户就复制不到了——想发文字就一个字都不许排版。
      - **应当（SHOULD）** 用于：闲聊寒暄与简短回答；结论、建议、说明一件事；
        搜索结果 / 天气 / 价格 / 时间 / 比分等「念出来就行」的事实；OCR、读图、
        翻译等原文复述；用户要复制走的内容；用户说了「发文字」「直接打字」。
      - 长了系统会自动切成几条、合并成一条转发聊天记录发出，不用你手动分段；
        要用户复制走的命令、代码、配置，一行行原样直写。
    - image：把 Markdown 渲染成图片，可以放心用完整 Markdown——标题、加粗、列表、
      表格、代码块、行内代码、LaTeX 公式。
      - **应当（SHOULD）** 用于需要排版才看得清的成篇内容：调研与资料整理、
        多对象或多方案对比、归纳总结、时间线 / 信息流 / 历史脉络讲述、
        知识讲解与教程、长篇结构化说明。
      - 用户说了「整理成图」「做张图」时 **必须（MUST）** 用它。
      - **禁止（MUST NOT）** 用它交付一两句话就能说清的东西——用户要的是能读能复制的文字。

    **绝不（NEVER）** 在拿不准时选 text：判断不了要不要排版，就 **必须（MUST）**
    选 image——图片是保底，做成图片不会比拍成文字更糟。text 只留给上面列的那几类
    明确场景，选了它就 **必须（MUST）** 写纯文字。

    sources 是本次回答实际用到的信息来源链接（只对 text 形态生效，图片形态会被忽略）：
    - 用了 web_search / web_fetch 且答案依赖这些结果时，**必须（MUST）** 填这里：
      一行一条原始链接，只写 URL（不要 Markdown 链接语法、不要标题说明）。
    - 系统会把它们作为聊天记录里单独一条「来源」发出；正文里 **禁止（MUST NOT）**
      再重复贴这些链接（纯文本正文本来就不许 Markdown 链接）。
    - 纯闲聊、纯推理、纯翻译，或回答没依赖外部来源时留空。
    """
    text = content.strip()
    if not text:
        raise ModelRetry("回复内容不能为空：把要对用户说的完整内容放进 content。")
    preamble.guard_preamble(ctx, text, source=TOOL_NAME)
    return Reply(content=text, format=format, sources=_normalize_sources(sources))


def _normalize_sources(sources: Sequence[str] | None) -> tuple[str, ...]:
    """来源链接归一：去首尾空白、丢空串、按首次出现顺序去重。"""
    seen: set[str] = set()
    result: list[str] = []
    for raw in sources or ():
        value = str(raw).strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)


def sources_text(sources: Sequence[str]) -> str:
    """来源清单 → 聊天记录里「来源」节点的正文：一行一条链接。"""
    return "\n".join(sources)


# ------------------------------------------------------------ 形态判定

# 出现任何一条即认为「正文带了排版」→ 图片保底。
# 前半是 Markdown 语法，后半是中文聊天里常见的非 Markdown 排版记号（项目符号、
# 中文序号、【小标题】），这一类同样属于「边界不清晰」，按保底规则走图片。
_STRUCTURE_MARKERS: tuple[re.Pattern[str], ...] = (
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
    re.compile(r"^[ \t]*[•·‧・▪◦●]\s*", re.M),  # 项目符号
    re.compile(r"^[ \t]*[0-9]+[、．]", re.M),  # 数字顿号序号
    re.compile(r"^[ \t]*[一二三四五六七八九十]+[、.．)）]", re.M),  # 中文序号
    re.compile(r"^[ \t]{0,3}【[^】\n]+】", re.M),  # 【小标题】
    re.compile(r"^[ \t]*(?:[-=—─]{3,})[ \t]*$", re.M),  # 分隔线（全角/等号）
)


def needs_image(text: str) -> bool:
    """正文是否带排版意图（Markdown 语法或中文式排版记号）→ 走图片。"""
    return any(marker.search(text) for marker in _STRUCTURE_MARKERS)


def to_delivery(output: object) -> Delivery:
    """把 run 输出归一为可交付的 ``Delivery``（形态判定见模块 docstring）。"""
    sources: tuple[str, ...] = ()
    if isinstance(output, Reply):
        fmt, content, source = output.format, output.content, "tool"
        sources = output.sources
    else:
        content = str(output)
        fmt: ReplyFormat = "image" if needs_image(content) else "text"
        source: Literal["tool", "auto"] = "auto"

    escalated = False
    if fmt == "text" and needs_image(content):
        # 模型声明了 text 却写了排版：按「有 Markdown 就是 Markdown」改判为图片，
        # 不在这里替它抹语法（那样内容会被拍扁，表格/代码会走形）。
        fmt, escalated = "image", True
        logger.info("AI 回复检出排版记号，text 形态改判为图片 chars={}", len(content))
    if fmt == "image":
        # 图片形态不用来源：链接本来就能写进 Markdown，不需要单独节点。
        sources = ()
    return Delivery(
        content=content, format=fmt, source=source, escalated=escalated, sources=sources
    )


# ------------------------------------------------------------ 纯文本分段

_PARAGRAPH_SPLIT_RE = re.compile(r"\n[ \t]*\n+")
# 句末标点后断开（保留标点）；英文句点只在后面跟空白时断，避免切碎 URL / 版本号；
# 换行也是句子边界。
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?；;…])|(?<=\.)(?=\s)|\n+")
# 单句超长（无句末标点）时退到逗号级。
_CLAUSE_SPLIT_RE = re.compile(r"(?<=[，,、：:])")


def _pieces(text: str, max_chars: int) -> list[str]:
    """一段文字 → 每片不超过 ``max_chars`` 的句子片段（无标点长串硬切兜底）。"""
    pieces: list[str] = []
    for sentence in _SENTENCE_SPLIT_RE.split(text):
        if not sentence:
            continue
        if len(sentence) <= max_chars:
            pieces.append(sentence)
            continue
        for clause in _CLAUSE_SPLIT_RE.split(sentence):
            if not clause:
                continue
            if len(clause) <= max_chars:
                pieces.append(clause)
            else:
                pieces.extend(clause[i : i + max_chars] for i in range(0, len(clause), max_chars))
    return pieces


def _pack(pieces: list[str], *, min_chars: int, max_chars: int) -> list[str]:
    """句子片段打包成 ``min_chars``~``max_chars`` 的几条消息（保证不丢字）。

    先贪心：够 ``min_chars`` 或下一片塞不下就收一条；再修尾巴——尾条太短时优先
    并进上一条，并进会超长就把最后两条按片段边界对半分，让每条都落进窗口。
    """
    groups: list[list[str]] = []
    current: list[str] = []
    length = 0
    for piece in pieces:
        if current and (length >= min_chars or length + len(piece) > max_chars):
            groups.append(current)
            current, length = [], 0
        current.append(piece)
        length += len(piece)
    if current:
        groups.append(current)
    _fix_short_tail(groups, min_chars=min_chars, max_chars=max_chars)
    return ["".join(group).strip() for group in groups if "".join(group).strip()]


def _fix_short_tail(groups: list[list[str]], *, min_chars: int, max_chars: int) -> None:
    """尾条短于 ``min_chars`` 时就地修正最后两条（并进上一条 / 对半分）。"""
    if len(groups) < 2 or _length(groups[-1]) >= min_chars:
        return
    previous, tail = groups[-2], groups[-1]
    if _length(previous) + _length(tail) <= max_chars:
        previous.extend(tail)
        groups.pop()
        return
    merged = previous + tail
    total = _length(merged)
    if total < 2 * min_chars or total > 2 * max_chars:
        return
    # 在片段边界里挑最靠近一半、且两半都还在窗口内的切点；挑不到就保持原样。
    best: int | None = None
    offset = 0
    for index in range(1, len(merged)):
        offset += len(merged[index - 1])
        if not (min_chars <= offset <= max_chars and min_chars <= total - offset <= max_chars):
            continue
        if best is None or abs(offset - total / 2) < abs(best - total / 2):
            best = offset
    if best is None:
        return
    head: list[str] = []
    rest: list[str] = []
    offset = 0
    for piece in merged:
        (head if offset < best else rest).append(piece)
        offset += len(piece)
    groups[-2:] = [head, rest]


def _length(pieces: list[str]) -> int:
    """片段列表的总字符数。"""
    return sum(len(piece) for piece in pieces)


def _all_pieces(text: str, max_chars: int) -> list[str]:
    """整条正文 → 可拼接的片段序列（段间保留空行，超长段再按句子切）。

    自然段是**首选断点**而不是硬边界：短段会被打包进同一条消息（避免一句一条
    刷屏），长段内的句子同理；只有单段超过 ``max_chars`` 才在段内切。
    """
    pieces: list[str] = []
    for raw_paragraph in _PARAGRAPH_SPLIT_RE.split(text.strip()):
        paragraph = raw_paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= max_chars:
            pieces.append(paragraph)
        else:
            pieces.extend(_pieces(paragraph, max_chars))
        # 段间空行挂在前一段末尾，拼接后再统一 strip；最后一段不带（末尾必被 strip，
        # 留着会让长度预算比实际消息长 2 字，尾巴就没法并了）。
        pieces[-1] += "\n\n"
    if pieces:
        pieces[-1] = pieces[-1].removesuffix("\n\n")
    return pieces


def split_plain_text(
    text: str,
    *,
    min_chars: int = SEGMENT_MIN_CHARS,
    max_chars: int = SEGMENT_MAX_CHARS,
) -> list[str]:
    """纯文本 → 逐条发送的消息列表（保证不丢字）。

    - 整条不超过 ``max_chars`` → 一条消息（简短回复不会被拆成好几句）；
    - 更长时按 ``min_chars``~``max_chars`` 打包：自然段优先当断点，段内按句子切，
      尾条过短时并进上一条或与上一条对半分；
    - 无句末标点的长串退到逗号切，最后按 ``max_chars`` 硬切。
    """
    pieces = _all_pieces(text, max_chars)
    if not pieces:
        return []
    return _pack(pieces, min_chars=min_chars, max_chars=max_chars)
