"""话题切换检测：识别上下文中的话题边界，截断不相关的旧历史。

核心思路：
- 用字符级 Jaccard 相似度比较新旧消息的话题相关性
- 检测到话题切换时，截断不相关的旧话题历史
- 保留最近话题的完整上下文

检测策略：
1. 提取消息中的"关键词"（去除停用词后的字符集合）
2. 计算新旧消息关键词的 Jaccard 相似度
3. 相似度低于阈值视为话题切换
4. 从最近边界向前扫描，找到与新提问相关的最早话题起点
5. 截断起点之前的历史，保留起点之后的完整上下文

阈值说明：
- 0.08 是经验值，中文短文本（群聊场景）下效果较好
- 可在 AIConfig.topic_shift_threshold 中调整
- 设为 0 关闭检测（所有历史都视为相关）
"""

from __future__ import annotations

import re

from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

# 中文停用词（高频虚词、助词、标点等）
_STOP_WORDS = frozenset(
    "的了吗呢吧啊哦嗯把被让给在到和与或而但如若虽然所以因此于是然后"
    "就也都还很更最这那这个那个什么怎么为什么如何哪谁多少几些一二三"
    "四五六七八九十百千万亿个只又再已经正在将要可以能够应该必须要不没"
    "有我是他她它们你我我们你们他们自己别人大家人家人们这里那里哪里"
    "这样那样怎样多么这么那么太非常极其相当比较稍微有点儿些一点一些下上"
    "里外前后中间旁边左右远近高低长短大小好坏对错是非真假新旧冷热快慢"
    "早晚先后第一第二第三最后最初最终目前现在以前以后之前之后当时后来"
    "最近刚刚已经正在将要可以能够应该必须要不没有"
)

# 话题分割的关键词提取正则（去除标点、数字、空白）
_KEYWORD_PATTERN = re.compile(r"[\u4e00-\u9fa5a-zA-Z]")


def extract_keywords(text: str) -> set[str]:
    """从文本中提取关键词字符集合（去停用词、去重）。"""
    chars = _KEYWORD_PATTERN.findall(text)
    return {c for c in chars if c not in _STOP_WORDS}


def _split_into_topics(messages: list[ModelMessage]) -> list[tuple[int, int]]:
    """按用户消息切分话题段落，返回 [(start_idx, end_idx), ...] 列表。

    每个段落从一条用户消息开始，到下一条用户消息之前结束（含中间的
    工具调用、助手回复等）。
    """
    boundaries: list[int] = []
    for idx, msg in enumerate(messages):
        if isinstance(msg, ModelRequest) and any(isinstance(p, UserPromptPart) for p in msg.parts):
            boundaries.append(idx)

    if not boundaries:
        return []

    segments: list[tuple[int, int]] = []
    for i, start in enumerate(boundaries):
        end = boundaries[i + 1] if i + 1 < len(boundaries) else len(messages)
        segments.append((start, end))
    return segments


def _find_topic_boundary(
    messages: list[ModelMessage],
    new_question: str,
    threshold: float,
    window_size: int,
) -> int | None:
    """找到与新提问相关的最早话题起点索引。

    从最近的话题边界向前扫描，找到第一个与新提问相似度 >= 阈值的边界。
    如果所有历史话题都与新提问无关，返回 None（保留全部历史）。

    Args:
        messages: 完整历史消息列表
        new_question: 新提问的文本
        threshold: 相似度阈值（低于此值视为无关）
        window_size: 向前扫描的最大轮数

    Returns:
        话题起点索引，或 None（表示所有历史都相关）
    """
    segments = _split_into_topics(messages)
    if not segments:
        return None

    new_kws = extract_keywords(new_question)
    if not new_kws:
        return None  # 新提问无关键词，保守处理

    # 从最近的话题向前扫描，找到第一个相关的
    for start_idx, end_idx in reversed(segments[-window_size:]):
        # 提取该段落内所有用户消息的关键词
        topic_kws: set[str] = set()
        for msg in messages[start_idx:end_idx]:
            if isinstance(msg, ModelRequest):
                for part in msg.parts:
                    if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                        topic_kws.update(extract_keywords(part.content))

        if not topic_kws:
            continue

        # 计算 Jaccard 相似度
        intersection = len(new_kws & topic_kws)
        union = len(new_kws | topic_kws)
        similarity = intersection / union if union > 0 else 0.0

        if similarity >= threshold:
            return start_idx

    return None  # 所有历史话题都与新提问无关


def truncate_by_topic_shift(
    messages: list[ModelMessage],
    new_question: str,
    threshold: float = 0.08,
    window_size: int = 5,
) -> list[ModelMessage]:
    """话题切换截断：如果新提问与历史话题无关，截断不相关的旧历史。

    Args:
        messages: 完整历史消息列表
        new_question: 新提问的文本
        threshold: 相似度阈值（低于此值视为话题切换）
        window_size: 向前扫描的最大轮数

    Returns:
        截断后的消息列表（从相关话题起点开始）
    """
    if not messages or not new_question or threshold <= 0:
        return messages

    # 至少需要 2 轮对话才可能检测到话题切换
    user_msg_count = sum(
        1
        for msg in messages
        if isinstance(msg, ModelRequest) and any(isinstance(p, UserPromptPart) for p in msg.parts)
    )
    if user_msg_count < 2:
        return messages

    boundary_idx = _find_topic_boundary(messages, new_question, threshold, window_size)
    if boundary_idx is None:
        return messages  # 所有历史都相关，不截断

    return messages[boundary_idx:]


def detect_topic_boundaries(messages: list[ModelMessage], threshold: float = 0.08) -> list[int]:
    """识别消息历史中的所有话题边界索引（用于 compaction 摘要生成）。

    返回每个话题起点的索引列表。如果只有 1 个话题（无切换），返回 [0]。

    Args:
        messages: 消息历史列表
        threshold: 相似度阈值

    Returns:
        话题起点索引列表（升序）
    """
    if not messages or threshold <= 0:
        return [0] if messages else []

    segments = _split_into_topics(messages)
    if len(segments) <= 1:
        return [0] if segments else []

    boundaries: list[int] = [segments[0][0]]

    for i in range(1, len(segments)):
        prev_start, prev_end = segments[i - 1]
        curr_start, curr_end = segments[i]

        # 提取前一个话题的关键词
        prev_kws: set[str] = set()
        for msg in messages[prev_start:prev_end]:
            if isinstance(msg, ModelRequest):
                for part in msg.parts:
                    if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                        prev_kws.update(extract_keywords(part.content))

        # 提取当前话题的用户消息关键词
        curr_kws: set[str] = set()
        for msg in messages[curr_start:curr_end]:
            if isinstance(msg, ModelRequest):
                for part in msg.parts:
                    if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                        curr_kws.update(extract_keywords(part.content))

        if not prev_kws or not curr_kws:
            continue  # 无法比较，保守视为同一话题

        # 计算相似度
        intersection = len(prev_kws & curr_kws)
        union = len(prev_kws | curr_kws)
        similarity = intersection / union if union > 0 else 0.0

        if similarity < threshold:
            boundaries.append(curr_start)

    return boundaries
