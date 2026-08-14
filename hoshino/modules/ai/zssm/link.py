"""zssm 链接处理：web_fetch 静态抓取优先，browser_use 渲染截图兜底。

- ``web_fetch``：抓取网页正文转 markdown（快、保真、SSRF 防护内建）；
- 抓取失败或内容为空时回退 ``browser_use``：Playwright 渲染截图 → vision 模型
  描述（覆盖 JS 渲染页面；需要配置 vision 模型）；
- 两者都失败直接抛 ``ValueError``（调用方直接回复错误，不做重试）。
"""

from __future__ import annotations

import re

from hoshino.ai.tools.web.browser_use import browse_page_description
from hoshino.ai.tools.web.web_fetch import fetch_url_to_markdown

# 链接提取：http(s) 起，到空白/中文标点/引号为止（参考 CoolQBot 语义）。
_URL_PATTERN = re.compile(
    r"https?://[^\s<>\"'，。；：！？、（）【】《》「」『』]+", re.IGNORECASE
)
_TRAILING_URL_PUNCTUATION = ".,;:!?，。；：！？、)]}）】》」』"

# web_fetch 的失败/空结果前缀（据此判定需要 browser_use 兜底）。
_WEB_FAILED_PREFIXES = ("仅支持", "拒绝", "抓取失败", "（空内容）")


def extract_urls(*texts: str) -> list[str]:
    """按出现顺序提取并去重 HTTP(S) 链接。"""
    urls: list[str] = []
    seen: set[str] = set()
    for text in texts:
        for match in _URL_PATTERN.finditer(text):
            url = match.group(0).rstrip(_TRAILING_URL_PUNCTUATION)
            if url and url not in seen:
                seen.add(url)
                urls.append(url)
    return urls


def _fetch_failed(content: str) -> bool:
    return (not content) or content.startswith(_WEB_FAILED_PREFIXES)


async def load_url(
    url: str,
    *,
    record,
    vision_model: str,
    config,
) -> dict[str, str]:
    """加载单个链接，返回 ``{"url", "kind", "content"}``；失败抛 ValueError。

    kind：``web``（网页正文 markdown）或 ``browser``（网页截图 vision 描述）。
    """
    content = await fetch_url_to_markdown(url, verify_ssl=config.web_fetch_verify_ssl)
    if not _fetch_failed(content):
        return {"url": url, "kind": "web", "content": content}
    if not vision_model:
        raise ValueError(f"无法获取页面内容：{url}（未配置多模态模型，无法渲染兜底）。")
    description = await browse_page_description(
        url,
        proxy=config.proxy,
        record=record,
        vision_model=vision_model,
    )
    # browser_use 的错误提示（网页加载超时/访问失败/截图超限/识别失败等）
    if any(
        mark in description
        for mark in ("失败", "不可用", "超时", "为空", "超过", "仅支持", "拒绝")
    ):
        raise ValueError(f"无法获取页面内容：{url}（{description}）。")
    return {"url": url, "kind": "browser", "content": description}
