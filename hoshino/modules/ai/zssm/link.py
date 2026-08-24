"""zssm 链接提取：从文本中抽取 HTTP(S) 链接。

实际抓取由解释 Agent 通过 web_fetch / browser_use 工具自主完成；
本模块只负责把 target/focus 里的链接列出来供模型参考（urls_in_target）。
"""

from __future__ import annotations

import re

# 链接提取：http(s) 起，到空白/中文标点/引号为止（参考 CoolQBot 语义）。
_URL_PATTERN = re.compile(r"https?://[^\s<>\"'，。；：！？、（）【】《》「」『』]+", re.IGNORECASE)
_TRAILING_URL_PUNCTUATION = ".,;:!?，。；：！？、)]}）】》」』"


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
