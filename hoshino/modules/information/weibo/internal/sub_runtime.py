import asyncio
import random
import time
from dataclasses import dataclass

from hoshino.content.dispatch import retry_delay
from hoshino.platform import Target, load_target_or_group

from ..db import (
    get_group_config,
    list_subscriptions_by_uid,
    uid_has_any_subscription,
    update_subscriptions_for_uid,
)
from ..post import WeiboPost
from .outbox import (
    MAX_ATTEMPTS,
    WeiboOutboxItem,
    WeiboOutboxStore,
    deserialize_post_message,
    serialize_post_message,
    serialize_weibo_post,
)
from .post_runtime import (
    adapt_post_message,
    cache_weibo_msg_id,
)
from ..request import get_weibo_list
from ..sv import sv


WEIBO_COLD_UID_THRESHOLD = 24 * 60 * 60
WEIBO_DISPATCH_BATCH_SIZE = 5


@dataclass
class RuntimeState:
    enable_groups: dict[int, list[object]]
    group_configs: dict[int, object]
    uid_rows: list[object]


@dataclass
class MatchedPost:
    post: WeiboPost
    rows: list[object]
    with_screenshot: bool


@dataclass
class DeliveryPlan:
    bot: object
    gid: int
    target: Target
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

    def match_posts(
        self, posts: list[WeiboPost], state: RuntimeState
    ) -> list[MatchedPost]:
        rows = state.uid_rows
        row_keywords_map = {
            row.group: [kw for kw in row.keyword.split("-_-") if kw]
            if row.keyword
            else []
            for row in rows
        }

        matched_posts: list[MatchedPost] = []
        for post in posts:
            matched_rows: list[object] = []
            with_screenshot = False
            for row in rows:
                if row.group not in state.enable_groups:
                    continue
                if post.timestamp <= row.time:
                    continue
                if not self._match_keywords(post, row_keywords_map[row.group]):
                    continue

                matched_rows.append(row)
                group_config = state.group_configs.get(row.group)
                if group_config and bool(group_config.send_screenshot):
                    with_screenshot = True

            if not matched_rows:
                continue
            matched_posts.append(
                MatchedPost(
                    post=post,
                    rows=matched_rows,
                    with_screenshot=with_screenshot,
                )
            )
        return matched_posts


class FetchMainline:
    def __init__(
        self, matcher: SubscriptionMatcher, *, cold_uid_threshold: int
    ) -> None:
        self.matcher = matcher
        self.cold_uid_threshold = cold_uid_threshold

    def _load_group_configs(self, group_ids: list[int]) -> dict[int, object]:
        return {group_id: get_group_config(group_id) for group_id in set(group_ids)}

    async def run_cycle(
        self, uid_str: str, uid_manager, outbox: WeiboOutboxStore
    ) -> bool:
        try:
            rows = list_subscriptions_by_uid(uid_str)
            if not rows:
                await uid_manager.remove_uid(
                    uid_str, lambda uid: uid_has_any_subscription(uid)
                )
                return True

            state = RuntimeState(
                enable_groups=await sv.get_enable_groups(),
                group_configs=self._load_group_configs([row.group for row in rows]),
                uid_rows=rows,
            )
            latest_known_ts = max(row.time for row in rows)
            now_ts = time.time()
            if (
                latest_known_ts > 0
                and now_ts - latest_known_ts > 2 * self.cold_uid_threshold
            ):
                await uid_manager.mark_cold(uid_str)

            min_ts = max(now_ts - self.cold_uid_threshold, latest_known_ts)
            posts = await get_weibo_list(uid_str, min_ts)
            if not posts:
                return True

            await uid_manager.unmark_cold(uid_str)
            matched_posts = self.matcher.match_posts(posts, state)
            for item in matched_posts:
                built_message = await self._build_message(
                    uid_str, item.post, item.with_screenshot
                )
                if not built_message:
                    continue
                # Phase 1 complete: message is archived. Enqueue to durable outbox.
                post_payload = serialize_weibo_post(item.post)
                message_payload = serialize_post_message(built_message)
                for row in item.rows:
                    inserted = await outbox.enqueue(
                        group_id=row.group,
                        target_data=row.target_data or "",
                        uid=item.post.uid,
                        post_id=item.post.id,
                        post_payload=post_payload,
                        message_payload=message_payload,
                    )
                    if inserted:
                        sv.logger.info(
                            f"获取到微博更新: {item.post.uid} {item.post.nickname} {row.group} {item.post.timestamp} {item.post.url}"
                        )

            update_subscriptions_for_uid(
                uid_str, max(post.timestamp for post in posts), posts[0].nickname
            )
            return True
        except Exception:
            sv.logger.error(f"获取微博更新失败 UID {uid_str}")
            return False

    async def _build_message(
        self, uid_str: str, post: WeiboPost, with_screenshot: bool
    ):
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
    """Reads due items from the durable outbox and delivers them."""

    def __init__(self, outbox: WeiboOutboxStore) -> None:
        self.outbox = outbox

    async def dispatch_due(self, limit: int = WEIBO_DISPATCH_BATCH_SIZE) -> int:
        items = await self.outbox.due_outbox(limit)
        if not items:
            return 0

        enable_groups = await sv.get_enable_groups()
        sent = 0

        for item in items:
            if item.group_id not in enable_groups:
                # Group no longer has the service enabled; mark sent to skip.
                await self.outbox.mark_sent(item.id)
                continue

            try:
                await self._deliver_one(item, enable_groups)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if item.attempts + 1 >= MAX_ATTEMPTS:
                    await self.outbox.mark_dead(item.id, f"{type(exc).__name__}: {exc}")
                    sv.logger.error(
                        f"微博推送永久失败: group={item.group_id} uid={item.uid} post={item.post_id} error={exc}"
                    )
                else:
                    retry_at = time.time() + retry_delay(item.attempts)
                    await self.outbox.mark_failed(
                        item.id, retry_at, f"{type(exc).__name__}: {exc}"
                    )
                    sv.logger.error(
                        f"微博推送失败(将重试): group={item.group_id} uid={item.uid} post={item.post_id} "
                        f"attempts={item.attempts + 1} error={exc}"
                    )
            else:
                await self.outbox.mark_sent(item.id)
                sent += 1

        return sent

    async def _deliver_one(
        self, item: WeiboOutboxItem, enable_groups: dict[int, list[object]]
    ) -> None:
        post = WeiboPost.from_dict(item.post_payload)
        message = deserialize_post_message(item.message_payload)
        group_config = get_group_config(item.group_id)

        adapted = adapt_post_message(message, group_config, busy=False)
        if not adapted:
            sv.logger.info(
                f"跳过微博推送: group={item.group_id} uid={item.uid} post={item.post_id} (only_pic且无图)"
            )
            return

        bot = enable_groups[item.group_id][0]
        target = load_target_or_group(item.target_data or None, item.group_id)
        use_segments = bool(group_config.send_segments)

        sv.logger.info(
            f"推送微博更新: {post.uid} {post.nickname} {item.group_id} {post.timestamp} {post.url}"
        )
        response = await post.send(
            bot=bot,
            gid=item.group_id,
            target=target,
            post_message=adapted,
            use_segments=use_segments,
        )

        message_id = response.get("message_id") if isinstance(response, dict) else None
        if message_id:
            sv.logger.info(
                f"微博推送成功: group={item.group_id} uid={item.uid} post={item.post_id} message_id={message_id}"
            )
            cache_weibo_msg_id(message_id, item.uid, item.post_id)


class WeiboDispatchRuntime:
    def __init__(
        self,
        *,
        outbox: WeiboOutboxStore,
        uid_manager,
        cold_uid_threshold: int = WEIBO_COLD_UID_THRESHOLD,
    ) -> None:
        self.outbox = outbox
        self.uid_manager = uid_manager
        self.cold_uid_threshold = cold_uid_threshold
        self.fetch_lock = asyncio.Lock()
        self.matcher = SubscriptionMatcher()
        self.fetch_mainline = FetchMainline(
            self.matcher, cold_uid_threshold=cold_uid_threshold
        )
        self.dispatch_mainline = DispatchMainline(outbox)

    async def fetch_next_update(self) -> None:
        if self.fetch_lock.locked():
            return
        async with self.fetch_lock:
            uid_str = await self.uid_manager.get_next_uid()
            if not uid_str:
                return
            success = await self.fetch_mainline.run_cycle(
                uid_str, self.uid_manager, self.outbox
            )
            await self.uid_manager.finish_processing(uid_str, success)

    async def dispatch_pending(self) -> int:
        return await self.dispatch_mainline.dispatch_due()

    async def bootstrap(self, rows) -> None:
        await self.outbox.initialize()

        uid_latest_time: dict[str, float] = {}
        for uid, ts in rows:
            uid_str = str(uid)
            uid_latest_time[uid_str] = max(
                uid_latest_time.get(uid_str, 0.0), float(ts or 0.0)
            )

        uids = list(uid_latest_time)
        random.shuffle(uids)
        await self.uid_manager.init(uids)

        now_ts = time.time()
        for uid, latest_ts in uid_latest_time.items():
            if latest_ts > 0 and now_ts - latest_ts > self.cold_uid_threshold:
                await self.uid_manager.mark_cold(uid)


__all__ = [
    "WEIBO_COLD_UID_THRESHOLD",
    "WEIBO_DISPATCH_BATCH_SIZE",
    "RuntimeState",
    "WeiboDispatchRuntime",
]
