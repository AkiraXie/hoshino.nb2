"""URL 脱敏工具：日志输出前抹掉 URL 中可能嵌入的凭据片段。"""

import re

# Telegram Bot API 文件 URL 形如 ``{api_server}/file/bot<token>/<file_path>``，
# 其中 ``bot<token>`` 内嵌机器人凭据，绝不能原样进日志。
# token 格式为 ``<bot_id>:<auth_hash>``（数字 + 字母数字下划线短横线）。
_BOT_TOKEN_PATTERN = re.compile(r"(bot)([A-Za-z0-9_-]+:[A-Za-z0-9_-]+)(/)")


def redact_url(url: str) -> str:
    """掩码 URL 中内嵌的凭据片段（当前覆盖 Telegram bot token）。

    新的凭据形态（如 query 参数里的 ``token=``）应在此追加对应规则，
    而不是在调用方逐个手工替换。
    """
    return _BOT_TOKEN_PATTERN.sub(r"\1<redacted>\3", url)


__all__ = ["redact_url"]
