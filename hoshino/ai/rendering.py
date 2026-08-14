"""Markdown → HTML → Playwright PNG 渲染。

链路：``markdown-it-py`` 渲染 Markdown 到 HTML（服务端 pygments 高亮代码块），
内嵌 CSS 后交给仓库既有 Playwright 设施截图成 PNG。

``markdown_to_html`` / ``build_full_html`` 为纯函数，便于测试；真正依赖浏览器的
``render_markdown`` 在 chat 插件中用 ``asyncio.wait_for`` 包裹，超时或异常统一回退
纯文本。
"""

from __future__ import annotations

import re
from typing import Any

from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name, TextLexer

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


def make_markdown() -> MarkdownIt:
    """构建配置好插件与高亮渲染的 MarkdownIt 实例。"""
    md = MarkdownIt("gfm-like", {"html": True, "linkify": True}).use(tasklists_plugin)
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
    # 惰性导入：hoshino.util.playwrights 顶层依赖 NoneBot 已初始化，
    # 而本模块的纯函数需在无 NoneBot 环境（如纯函数测试）下可用。
    from hoshino.util.playwrights import get_b

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
