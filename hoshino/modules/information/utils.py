import asyncio
from dataclasses import dataclass, field
from asyncio import Queue
from hoshino import Message, MessageSegment
from typing import Union, TypeVar, Generic
import time


@dataclass
class Post:
    """统一的动态/微博数据基类"""

    uid: str
    """用户ID"""
    id: str
    """动态/微博ID"""
    content: str
    """文本内容"""
    platform: str
    """平台标识: 'weibo' 或 'bilibili'"""
    title: str = ""
    images: list[str] = field(default_factory=list)
    """图片列表"""
    videos: list[str] = field(default_factory=list)
    """视频链接"""
    timestamp: float = 0.0
    """发布/获取时间戳, 秒"""
    url: str = ""
    """来源链接"""
    nickname: str = ""
    """发布者昵称"""
    description: str = ""
    """描述信息"""
    repost: Union["Post", None] = None
    """转发的Post"""

    async def get_message(
        self, with_screenshot: bool = True
    ) -> list[Message | MessageSegment]: ...
    def get_referer(self) -> str: ...


T = TypeVar("T", bound="Post")


class PostQueue(Queue, Generic[T]):
    """统一的队列管理器，支持泛型"""

    def __init__(self, maxsize: int = 0) -> None:
        super().__init__(maxsize)
        self._set = set()

    def put(self, item: T) -> bool:
        """放入队列，如果ID已存在则跳过"""
        item_id = item.id
        if item_id not in self._set:
            self._set.add(item_id)
            super().put_nowait(item)
            loop = asyncio.get_event_loop()
            loop.call_later(3600, self.remove_id, item_id)
            return True
        return False

    def get(self) -> T | None:
        """从队列获取项目"""
        if self.empty():
            return None
        item = super().get_nowait()
        return item

    def remove_id(self, item_id: str) -> None:
        """从集合中移除ID"""
        self._set.discard(item_id)


class UIDManager:
    """统一的UID管理器"""

    def __init__(self, platform: str):
        self.platform = platform
        self._uids: set[str] = set()
        self._uid_queue = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._processing_uids: set[str] = set()
        self._last_fetch_times: dict[str, float] = {}
        self._min_interval = 180

    async def init(self, uids: list[str]):
        """从UID列表初始化管理器"""
        async with self._lock:
            self._uids = set(uids)
            # 清空队列并重新填充
            while not self._uid_queue.empty():
                try:
                    self._uid_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            for uid in self._uids:
                await self._uid_queue.put(uid)

    async def add_uid(self, uid: str):
        """添加 UID"""
        uid_str = str(uid)
        async with self._lock:
            if uid_str not in self._uids:
                self._uids.add(uid_str)
                await self._uid_queue.put(uid_str)

    async def remove_uid(self, uid: str, check_db_func):
        """删除 UID（如果该 UID 没有其他群订阅）"""
        uid_str = str(uid)
        # 检查是否还有其他群订阅此 UID
        has_subscription = check_db_func(uid)
        if not has_subscription:
            async with self._lock:
                if uid_str in self._uids:
                    self._uids.remove(uid_str)
                    self._processing_uids.discard(uid_str)

    def _should_fetch_uid(self, uid: str) -> bool:
        """检查UID是否需要抓取"""
        current_time = time.time()
        last_time = self._last_fetch_times.get(uid, 0)
        return current_time - last_time >= self._min_interval

    def _update_fetch_time(self, uid: str):
        """更新UID的抓取时间"""
        self._last_fetch_times[uid] = time.time()

    async def get_next_uid(self) -> str | None:
        """获取下一个要检查的 UID"""
        max_attempts = len(self._uids) * 2 if self._uids else 1  # 增加尝试次数
        attempts = 0

        while attempts < max_attempts:
            if self._uid_queue.empty():
                return None

            uid = await self._uid_queue.get()

            async with self._lock:
                if uid in self._uids and uid not in self._processing_uids:
                    # 检查是否需要抓取
                    if self._should_fetch_uid(uid):
                        self._processing_uids.add(uid)
                        await self._uid_queue.put(uid)  # 重新放入队列
                        return uid
                    else:
                        # 不需要抓取，直接重新入队
                        await self._uid_queue.put(uid)
                        attempts += 1
                elif uid in self._uids:
                    # UID 有效但正在处理中，跳过并重新放入队列
                    await self._uid_queue.put(uid)
                    attempts += 1
                else:
                    # UID 已被删除，跳过
                    attempts += 1

        return None

    async def finish_processing(self, uid: str, success: bool = True):
        """标记 UID 处理完成"""
        async with self._lock:
            self._processing_uids.discard(uid)
            if success:
                self._update_fetch_time(uid)

    def get_count(self) -> int:
        """获取可以立即抓取的UID数量"""
        count = 0
        for uid in self._uids:
            if self._should_fetch_uid(uid) and uid not in self._processing_uids:
                count += 1
        return count
