"""Markdown → HTML → Playwright PNG 渲染。

链路：``markdown-it-py`` 渲染 Markdown 到 HTML（服务端 pygments 高亮代码块、
LaTeX 数学公式经 ``latex2mathml`` 转 MathML 由 Chromium 原生排版），内嵌 CSS
后交给仓库既有 Playwright 设施截图成 PNG。

``markdown_to_html`` / ``build_full_html`` 为纯函数，便于测试；真正依赖浏览器的
``render_markdown`` 在 chat 插件中用 ``asyncio.wait_for`` 包裹，超时或异常统一回退
纯文本。
"""

from __future__ import annotations

import re
from html import escape
from typing import Any

from latex2mathml.converter import convert as latex_to_mathml
from loguru import logger
from markdown_it import MarkdownIt
from markdown_it.rules_block import StateBlock
from markdown_it.rules_inline import StateInline
from mdit_py_plugins.amsmath import amsmath_plugin
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.tasklists import tasklists_plugin
from mdit_py_plugins.utils import is_code_block
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name

from hoshino.util.playwrights import get_b

from .config import AIConfig

_PYGMENTS_STYLE: dict[str, str] = {"light": "default", "dark": "monokai"}
_HIGHLIGHT_CSS_CACHE: dict[str, str] = {}

_BASE_CSS = """
:root {{
  --bg: {bg};
  --fg: {fg};
  --code-bg: {code_bg};
  --border: {border};
  --link: {link};
  --accent: {accent};
  --pre-bg: {pre_bg};
}}
* {{ box-sizing: border-box; }}
html, body {{
  margin: 0;
  padding: 0;
  background: var(--bg);
  color: var(--fg);
  font-family: {font_stack};
  font-size: 15px;
  line-height: 1.8;
  letter-spacing: 0.02em;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}}
.md-body {{
  max-width: 780px;
  margin: 0 auto;
  padding: 16px 20px;
  overflow-wrap: break-word;
  word-break: break-word;
}}
.md-body h1, .md-body h2, .md-body h3, .md-body h4 {{
  margin: 1.1em 0 0.55em;
  line-height: 1.35;
}}
.md-body h1 {{ font-size: 1.6em; border-bottom: 2px solid var(--accent); padding-bottom: 0.3em; }}
.md-body h2 {{ font-size: 1.35em; border-bottom: 1px solid var(--border); padding-bottom: 0.25em; }}
.md-body h3 {{ font-size: 1.15em; }}
.md-body p {{ margin: 0.85em 0; }}
.md-body a {{ color: var(--link); text-decoration: none; }}
.md-body a:hover {{ text-decoration: underline; }}
.md-body ul, .md-body ol {{ margin: 0.75em 0; padding-left: 1.5em; }}
.md-body li {{ margin: 0.35em 0; }}
.md-body blockquote {{
  margin: 0.8em 0;
  padding: 0.4em 1em;
  border-left: 4px solid var(--accent);
  color: var(--fg);
  opacity: 0.9;
}}
.md-body code {{
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  font-size: 0.9em;
  background: var(--code-bg);
  padding: 0.15em 0.35em;
  border-radius: 4px;
}}
.md-body pre {{
  background: var(--pre-bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 12px 14px;
  overflow-x: auto;
  line-height: 1.5;
  margin: 0.8em 0;
}}
.md-body pre code {{
  background: transparent;
  padding: 0;
  border-radius: 0;
  font-size: 0.9em;
}}
.md-body table {{
  border-collapse: collapse;
  margin: 0.8em 0;
  width: 100%;
}}
.md-body th, .md-body td {{
  border: 1px solid var(--border);
  padding: 6px 10px;
  text-align: left;
}}
.md-body th {{ background: var(--code-bg); color: var(--accent); }}
.md-body img {{ max-width: 100%; border-radius: 6px; }}
.md-body math {{
  font-family: "Latin Modern Math", "STIX Two Math", "Noto Sans Math",
    "DejaVu Math TeX Gyre", "Cambria Math", serif;
  font-size: 1.05em;
}}
.md-body .math.block, .md-body .math.amsmath {{
  margin: 1em 0;
  text-align: center;
}}
.md-body code.math-raw {{ white-space: pre-wrap; }}
.md-body hr {{ border: none; border-top: 1px solid var(--border); margin: 1em 0; }}
.md-body .task-list-item {{
  list-style: none;
  margin-left: -1.4em;
}}
.md-body .task-list-item-checkbox {{
  margin-right: 0.4em;
  transform: scale(1.1);
}}
"""

_BASE_FONT_STACK = (
    '-apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans CJK SC", '
    '"PingFang SC", "Microsoft YaHei", "Helvetica Neue", Arial'
)
_EMOJI_FONTS = '"Apple Color Emoji", "Segoe UI Emoji", "Noto Color Emoji"'

_THEMES: dict[str, dict[str, str]] = {
    "light": {
        "bg": "#ffffff",
        "fg": "#1f2328",
        "code_bg": "#f6f8fa",
        "border": "#d0d7de",
        "link": "#0969da",
        "accent": "#0969da",
        "pre_bg": "#f6f8fa",
    },
    "dark": {
        "bg": "#1f2328",
        "fg": "#e6edf3",
        "code_bg": "#161b22",
        "border": "#30363d",
        "link": "#4493f8",
        "accent": "#58a6ff",
        "pre_bg": "#161b22",
    },
}


# 结尾收束词：prompt 层已禁用总结句，但模型偶发用近似变体收尾
# （「一句话总结」→「一句话：」→「一句话版本：」），这里是渲染前的确定性兜底。
_TRAILING_SUMMARY_RE = re.compile(
    r"^\s*(?:[-*]\s+)?(?:\*\*)?(一句话[\S]*|总结一下|总的来说|综上所述|"
    r"说到底|总之|总而言之|简而言之|重点来了|先给结论)\s*[:：，,]?(?:\*\*)?"
)


def strip_trailing_summary(text: str) -> str:
    """裁掉回复末尾的总结行（仅当该行以收束词开头且是最后一行）。

    chat 回复渲染前调用；task 结构化产出不走此清洗。整篇只有一行时不动手，
    避免裁成空回复。
    """
    lines = text.rstrip("\n").split("\n")
    if len(lines) <= 1:
        return text
    last = lines[-1].strip()
    if last and _TRAILING_SUMMARY_RE.match(last):
        lines.pop()
    return "\n".join(lines)


def _make_highlight_css(theme: str) -> str:
    """生成 pygments 高亮 CSS。按主题缓存。"""
    key = theme if theme in _THEMES else "light"
    cached = _HIGHLIGHT_CSS_CACHE.get(key)
    if cached is None:
        formatter = HtmlFormatter(
            style=_PYGMENTS_STYLE.get(key, "default"),
            cssclass="codehilite",
        )
        cached = formatter.get_style_defs(".codehilite")
        _HIGHLIGHT_CSS_CACHE[key] = cached
    return cached


def _pygments_fence(tokens: list[Any], idx: int, options: Any, env: Any) -> str:
    """markdown-it fence 渲染：用 pygments 服务端高亮代码块。"""
    token = tokens[idx]
    info = token.info.strip()
    lang = info.split()[0] if info else ""
    code = token.content
    try:
        lexer = get_lexer_by_name(lang) if lang else TextLexer()
    except Exception:
        lexer = TextLexer()
    formatter = HtmlFormatter(nowrap=True, cssclass="codehilite")
    body = highlight(code, lexer, formatter)
    return f'<pre class="codehilite"><code>{body}</code></pre>'


# 段落终止链：公式块出现在上一行文字之后时不带空行也要断开成独立块。
_PARAGRAPH_TERMINATORS = ["paragraph", "reference", "blockquote", "list", "footnote_def"]


def _render_latex(latex: str, *, display_mode: bool) -> str:
    """LaTeX → MathML；转换失败退回原始 LaTeX，至少让公式源码可见。"""
    try:
        return latex_to_mathml(latex, display="block" if display_mode else "inline")
    except Exception as exc:  # latex2mathml 对未知命令/未闭合环境抛多种异常
        logger.warning(
            f"LaTeX 转 MathML 失败，按原文渲染 error={type(exc).__name__} latex={latex[:80]!r}"
        )
        return f'<code class="math-raw">{escape(latex)}</code>'


def _render_inline_math(content: str, options: dict[str, Any]) -> str:
    """dollarmath 渲染器签名：``(content, {"display_mode": bool}) -> str``。"""
    return _render_latex(content, display_mode=bool(options.get("display_mode")))


def _render_math_inline_double(
    _self: Any, tokens: list[Any], idx: int, _options: Any, _env: Any
) -> str:
    """同一行里的 ``$$...$$``：dollarmath 默认包 ``<div>`` 会撕开段落，这里按行内处理。"""
    content = str(tokens[idx].content).strip()
    return f'<span class="math inline">{_render_latex(content, display_mode=False)}</span>'


def _render_block_math(content: str) -> str:
    """amsmath 渲染器签名 ``(content) -> str``；该插件只产出独立成块的公式。"""
    return _render_latex(content, display_mode=True)


def _is_escaped(src: str, pos: int) -> bool:
    """判断 pos 处的字符是否被反斜杠转义（奇数个前置反斜杠为转义）。"""
    backslashes = 0
    idx = pos - 1
    while idx >= 0 and src[idx] == "\\":
        backslashes += 1
        idx -= 1
    return backslashes % 2 == 1


def _math_inline_bracket(state: StateInline, silent: bool) -> bool:
    """``\\(...\\)`` 行内公式，产出与 dollarmath ``$...$`` 相同的 token。"""
    if state.src[state.pos : state.pos + 2] != "\\(" or _is_escaped(state.src, state.pos):
        return False
    closing = state.src.find("\\)", state.pos + 2)
    if closing < 0:
        return False
    content = state.src[state.pos + 2 : closing].strip()
    if not content:
        return False
    if not silent:
        token = state.push("math_inline", "math", 0)
        token.content = content
        token.markup = "\\("
    state.pos = closing + 2
    return True


def _parse_math_block(
    state: StateBlock,
    start_line: int,
    end_line: int,
    silent: bool,
    open_delim: str,
    close_delim: str,
) -> bool:
    """解析独立成块的公式，可跨行；silent（段落终止探测）只判断不产出 token。"""
    if is_code_block(state, start_line):
        return False
    start = state.bMarks[start_line] + state.tShift[start_line]
    if state.src[start : start + len(open_delim)] != open_delim:
        return False
    closing_line = start_line
    closing = state.src.find(close_delim, start + len(open_delim))
    while closing < 0 or closing > state.eMarks[closing_line]:
        closing_line += 1
        if closing_line >= end_line:
            return False
        closing = state.src.find(close_delim, state.bMarks[closing_line])
    content = state.src[start + len(open_delim) : closing].strip()
    if not content:
        return False
    state.line = closing_line + 1
    if not silent:
        token = state.push("math_block", "math", 0)
        token.block = True
        token.content = content
        token.markup = open_delim
        token.map = [start_line, state.line]
    return True


def _math_block_dollar(state: StateBlock, start_line: int, end_line: int, silent: bool) -> bool:
    """``$$...$$`` 块级公式。"""
    return _parse_math_block(state, start_line, end_line, silent, "$$", "$$")


def _math_block_bracket(state: StateBlock, start_line: int, end_line: int, silent: bool) -> bool:
    """``\\[...\\]`` 块级公式。"""
    return _parse_math_block(state, start_line, end_line, silent, "\\[", "\\]")


def _math_plugin(md: MarkdownIt) -> None:
    """补上 ``\\(...\\)`` / ``\\[...\\]`` 定界符，并让块级公式成为段落终止符。

    dollarmath 只认美元符，且它的 ``$$`` 块规则没有 alt 终止链、在终止探测时
    还会推 token（会把前一段正文吞掉），因此这里整体替换成自己的实现。
    """
    md.inline.ruler.before("escape", "math_inline_bracket", _math_inline_bracket)
    md.block.ruler.at("math_block", _math_block_dollar, {"alt": _PARAGRAPH_TERMINATORS})
    md.block.ruler.before(
        "fence", "math_block_bracket", _math_block_bracket, {"alt": _PARAGRAPH_TERMINATORS}
    )


def make_markdown() -> MarkdownIt:
    """构建配置好插件与高亮渲染的 MarkdownIt 实例。"""
    md = MarkdownIt("gfm-like", {"html": True, "linkify": True}).use(tasklists_plugin)
    # allow_digits=False 跟随 GitHub 规则：闭合的 $ 后面不能紧跟数字，避免把
    # 「花了 $20，值 $30」这类价格文本误判成行内公式。
    md.use(
        dollarmath_plugin,
        renderer=_render_inline_math,
        allow_digits=False,
        allow_space=True,
        allow_blank_lines=True,
        double_inline=True,
    )
    md.use(amsmath_plugin, renderer=_render_block_math)
    md.use(_math_plugin)
    md.add_render_rule("math_inline_double", _render_math_inline_double)
    md.renderer.rules["fence"] = _pygments_fence
    return md


def markdown_to_html(markdown_text: str) -> str:
    """Markdown → HTML（纯函数，不含高亮以外的浏览器依赖）。"""
    md = make_markdown()
    return md.render(markdown_text)


def build_full_html(
    html_body: str, theme: str = "light", emoji: bool = True, font: str = "Inter"
) -> str:
    """把渲染好的 HTML 包进带内嵌 CSS 的完整页面。

    ``emoji`` 控制彩色 emoji 字体；``font`` 为主字体 family 名（中文经字体栈回退）。
    """
    theme_values = _THEMES.get(theme, _THEMES["light"])
    font_stack = f'"{font}", {_BASE_FONT_STACK}'
    if emoji:
        font_stack += f", {_EMOJI_FONTS}"
    font_stack += ", sans-serif"
    base_css = _BASE_CSS.format(font_stack=font_stack, **theme_values)
    highlight_css = _make_highlight_css(theme)
    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>aichat</title>
<style>
{base_css}
{highlight_css}
</style>
</head>
<body>
<article class="md-body">
{html_body}
</article>
</body>
</html>"""


async def render_markdown(markdown_text: str, config: AIConfig) -> bytes:
    """渲染 Markdown 为 PNG bytes。依赖 Chromium，可能较慢。"""
    html_body = markdown_to_html(markdown_text)
    html = build_full_html(
        html_body,
        config.render_theme,
        emoji=config.render_emoji,
        font=config.render_font,
    )
    browser = await get_b()
    page = await browser.new_page(
        viewport={"width": 820, "height": 100},
        device_scale_factor=config.render_device_scale,
    )
    try:
        await page.set_content(html, wait_until="domcontentloaded")
        png = await page.screenshot(full_page=True, type="png")
        return bytes(png)
    finally:
        await page.close()
