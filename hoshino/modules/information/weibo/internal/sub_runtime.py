import asyncio
import random
import time
from dataclasses import dataclass

from ..db import (
    get_group_config,
    list_subscriptions_by_uid,
    uid_has_any_subscription,
    update_subscriptions_for_uid,
)
from ..post import WeiboPost
from .post_runtime import (
    WeiboDispatchTask,
    adapt_post_message,
    cache_weibo_msg_id,
)
from ..request import get_weibo_list
from ..sv import sv


WEIBO_COLD_UID_THRESHOLD = 24 * 60 * 60
WEIBO_DISPATCH_WORKER_COUNT = 8


@dataclass
class RuntimeState:
    enable_groups: dict[int, list[object]]
    group_configs: dict[int, object]
    uid_rows: list[object]


@dataclass
class MatchedPost:
    post: WeiboPost
    group_ids: list[int]
    with_screenshot: bool


@dataclass
class DeliveryPlan:
    bot: object
    gid: int
    post: WeiboPost
    message: object
    use_segments: bool


class SubscriptionMatcher:
    def _match_keywords(self, post: WeiboPost, keywords: list[str]) -> bool:
        if not keywords:
            return True
        if any(keyword in post.content for keyword in keywords):
            return True
        if post.repost and any(keyword in post.repost.content for keyword in keywords):
            return True
        return False

    def match_posts(self, posts: list[WeiboPost], state: RuntimeState) -> list[MatchedPost]:
        rows = state.uid_rows
        row_keywords_map = {
            row.group: [kw for kw in row.keyword.split("-_-") if kw] if row.keyword else []
            for row in rows
        }

        matched_posts: list[MatchedPost] = []
        for post in posts:
            matched_groups: list[int] = []
            with_screenshot = False
            for row in rows:
                if row.group not in state.enable_groups:
                    continue
                if post.timestamp <= row.time:
                    continue
                if not self._match_keywords(post, row_keywords_map[row.group]):
                    continue

                matched_groups.append(row.group)
                group_config = state.group_configs.get(row.group)
                if group_config and bool(group_config.send_screenshot):
                    with_screenshot = True

            if not matched_groups:
                continue
            matched_posts.append(
                MatchedPost(
                    post=post,
                    group_ids=matched_groups,
                    with_screenshot=with_screenshot,
                )
            )
        return matched_posts


class FetchMainline:
    def __init__(self, matcher: SubscriptionMatcher, *, cold_uid_threshold: int) -> None:
        self.matcher = matcher
        self.cold_uid_threshold = cold_uid_threshold

    def _load_group_configs(self, group_ids: list[int]) -> dict[int, object]:
        return {group_id: get_group_config(group_id) for group_id in set(group_ids)}

    async def run_cycle(self, uid_str: str, uid_manager, weibo_queue) -> bool:
        try:
            rows = list_subscriptions_by_uid(uid_str)
            if not rows:
                await uid_manager.remove_uid(uid_str, lambda uid: uid_has_any_subscription(uid))
                return True

            state = RuntimeState(
                enable_groups=await sv.get_enable_groups(),
                group_configs=self._load_group_configs([row.group for row in rows]),
                uid_rows=rows,
            )
            latest_known_ts = max(row.time for row in rows)
            now_ts = time.time()
            if latest_known_ts > 0 and now_ts - latest_known_ts > 2 * self.cold_uid_threshold:
                await uid_manager.mark_cold(uid_str)

            min_ts = max(now_ts - self.cold_uid_threshold, latest_known_ts)
            posts = await get_weibo_list(uid_str, min_ts)
            if not posts:
                return True

            await uid_manager.unmark_cold(uid_str)
            matched_posts = self.matcher.match_posts(posts, state)
            for item in matched_posts:
                built_message = await self._build_message(uid_str, item.post, item.with_screenshot)
                if not built_message:
                    continue
                for group_id in item.group_ids:
                    task = WeiboDispatchTask(item.post, built_message, group_id)
                    if weibo_queue.put(task):
                        sv.logger.info(
                            f"获取到微博更新: {item.post.uid} {item.post.nickname} {group_id} {item.post.timestamp} {item.post.url}"
                        )

            update_subscriptions_for_uid(uid_str, max(post.timestamp for post in posts), posts[0].nickname)
            return True
        except Exception:
            sv.logger.error(f"获取微博更新失败 UID {uid_str}")
            return False

    async def _build_message(self, uid_str: str, post: WeiboPost, with_screenshot: bool):
        try:
            message = await post.get_message(
                with_screenshot=with_screenshot,
                screenshot_timeout=3.0,
            )
        except Exception as e:
            sv.logger.error(f"微博获取消息失败: uid={uid_str} post={post.id} error={e}")
            return None

        try:
            return await post.save(message)
        except Exception as e:
            sv.logger.error(f"微博推送归档失败: uid={uid_str} post={post.id} error={e}")
            return message


class DispatchMainline:
    def __init__(self, *, dispatch_worker_count: int) -> None:
        self.dispatch_worker_count = dispatch_worker_count

    async def build_state(self, group_id: int) -> RuntimeState:
        enable_groups = await sv.get_enable_groups()
        group_configs: dict[int, object] = {}
        if group_id in enable_groups:
            group_configs[group_id] = get_group_config(group_id)
        return RuntimeState(
            enable_groups=enable_groups,
            group_configs=group_configs,
            uid_rows=[],
        )

    async def build_plan(
        self,
        task: WeiboDispatchTask,
        state: RuntimeState,
        current_dispatches: int,
    ) -> DeliveryPlan | None:
        await asyncio.sleep(random.uniform(0.1, 1))
        if task.group_id not in state.enable_groups:
            return None

        busy = current_dispatches > self.dispatch_worker_count / 2
        sv.logger.info(
            "微博推送准备发送: "
            f"group={task.group_id} uid={task.post.uid} post={task.post.id} active={current_dispatches} busy={busy} "
        )

        group_config = state.group_configs.get(task.group_id)
        if group_config is None:
            group_config = get_group_config(task.group_id)
            state.group_configs[task.group_id] = group_config

        adapted = adapt_post_message(task.message, group_config, busy=busy)
        if not adapted:
            sv.logger.info(
                f"跳过微博推送: group={task.group_id} uid={task.post.uid} post={task.post.id} (only_pic且无图)"
            )
            return None

        return DeliveryPlan(
            bot=state.enable_groups[task.group_id][0],
            gid=task.group_id,
            post=task.post,
            message=adapted,
            use_segments=bool(group_config.send_segments) and not busy,
        )


class DeliveryExecutor:
    async def send(self, plan: DeliveryPlan) -> dict:
        return await plan.post.send(
            bot=plan.bot,
            gid=plan.gid,
            post_message=plan.message,
            use_segments=plan.use_segments,
        )


class WeiboDispatchRuntime:
    def __init__(
        self,
        *,
        weibo_queue,
        uid_manager,
        dispatch_worker_count: int = WEIBO_DISPATCH_WORKER_COUNT,
        cold_uid_threshold: int = WEIBO_COLD_UID_THRESHOLD,
    ) -> None:
        self.weibo_queue = weibo_queue
        self.uid_manager = uid_manager
        self.dispatch_worker_count = dispatch_worker_count
        self.cold_uid_threshold = cold_uid_threshold
        self.fetch_lock = asyncio.Lock()
        self.dispatch_state_lock = asyncio.Lock()
        self.active_dispatches = 0
        self.matcher = SubscriptionMatcher()
        self.fetch_mainline = FetchMainline(self.matcher, cold_uid_threshold=cold_uid_threshold)
        self.dispatch_mainline = DispatchMainline(dispatch_worker_count=dispatch_worker_count)
        self.delivery_executor = DeliveryExecutor()

    async def run_fetch_mainline(self, uid_str: str) -> bool:
        return await self.fetch_mainline.run_cycle(uid_str, self.uid_manager, self.weibo_queue)

    async def run_dispatch_mainline(
        self,
        task: WeiboDispatchTask,
        current_dispatches: int,
    ) -> tuple[RuntimeState, DeliveryPlan | None, dict | None]:
        state = await self.dispatch_mainline.build_state(task.group_id)
        plan = await self.dispatch_mainline.build_plan(task, state, current_dispatches)
        if not plan:
            return state, None, None
        response = await self.delivery_executor.send(plan)
        return state, plan, response

    async def fetch_next_update(self) -> None:
        if self.fetch_lock.locked():
            return
        async with self.fetch_lock:
            uid_str = await self.uid_manager.get_next_uid()
            if not uid_str:
                return
            success = await self.run_fetch_mainline(uid_str)
            await self.uid_manager.finish_processing(uid_str, success)

    async def handle_dispatch(self, task: WeiboDispatchTask) -> None:
        async with self.dispatch_state_lock:
            self.active_dispatches += 1
            current_dispatches = self.active_dispatches

        removed = False
        sleep_delay = 1.0
        try:
            sv.logger.info(
                f"推送微博更新: {task.post.uid} {task.post.nickname} {task.group_id} {task.post.timestamp} {task.post.url}, active={current_dispatches}"
            )

            state, plan, response = await self.run_dispatch_mainline(task, current_dispatches)
            if not plan:
                if task.group_id not in state.enable_groups:
                    self.weibo_queue.remove(task)
                    removed = True
                    sleep_delay = 0.5
                return

            message_id = response.get("message_id") if isinstance(response, dict) else None
            if message_id:
                sv.logger.info(
                    f"微博推送成功: group={task.group_id} uid={task.post.uid} post={task.post.id} message_id={message_id}"
                )
                cache_weibo_msg_id(message_id, task.post.uid, task.post.id)
        except Exception as e:
            sv.logger.error(f"发送 weibo post 失败: {e}")
        finally:
            if not removed:
                self.weibo_queue.remove(task)
            await asyncio.sleep(sleep_delay)
            async with self.dispatch_state_lock:
                self.active_dispatches = max(0, self.active_dispatches - 1)
                sv.logger.info(
                    f"微博推送完成: uid={task.post.uid} post={task.post.id} active={self.active_dispatches}"
                )

    async def dispatch_worker(self, worker_id: int) -> None:
        while True:
            task = self.weibo_queue.get()
            if not task:
                await asyncio.sleep(0.5)
                continue
            try:
                await self.handle_dispatch(task)
            except Exception as e:
                sv.logger.error(f"微博推送 worker {worker_id} 处理失败: {e}")
                self.weibo_queue.remove(task)
                await asyncio.sleep(1)

    async def bootstrap(self, rows) -> None:
        uid_latest_time: dict[str, float] = {}
        for uid, ts in rows:
            uid_str = str(uid)
            uid_latest_time[uid_str] = max(uid_latest_time.get(uid_str, 0.0), float(ts or 0.0))

        uids = list(uid_latest_time)
        random.shuffle(uids)
        await self.uid_manager.init(uids)

        now_ts = time.time()
        for uid, latest_ts in uid_latest_time.items():
            if latest_ts > 0 and now_ts - latest_ts > self.cold_uid_threshold:
                await self.uid_manager.mark_cold(uid)

        for worker_id in range(self.dispatch_worker_count):
            asyncio.create_task(self.dispatch_worker(worker_id))


__all__ = [
    "WEIBO_COLD_UID_THRESHOLD",
    "WEIBO_DISPATCH_WORKER_COUNT",
    "RuntimeState",
    "WeiboDispatchRuntime",
]