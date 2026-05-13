# 微博 `__init__.py` 拆分设计

## 背景

[`hoshino/modules/information/weibo/__init__.py`](../hoshino/modules/information/weibo/__init__.py) 当前约 657 行，混杂了以下关注点：

- 收藏夹系统（数据加载/保存/搜索/构建消息，约 200 行）
- 微博 URL 正则匹配与 reaction 处理（约 80 行）
- 配置命令（约 50 行）
- 订阅管理命令（约 60 行）
- Superuser 娱乐命令与搜索命令（约 100 行）

post/sub runtime 重构（见 [`2026-05-13-weibo-post-pipeline-design.md`](./2026-05-13-weibo-post-pipeline-design.md)）完成后，runtime 逻辑已收入 `internal/`，但 `__init__.py` 的拆分尚未纳入范围。本次设计将这些关注点按职责分离到独立文件。

## 目标

- 收藏系统 → `fav.py`（数据层 + 命令层）
- URL 解析 + reaction 处理 → `resolve.py`
- `__init__.py` 瘦身为插件入口：import 聚合、sv 注册、保留紧密耦合 db 的命令

## 非目标

- 不改变收藏夹 JSON 文件格式或存储路径
- 不修改微博 URL 正则的匹配规则
- 不调整现有命令的交互行为或权限模型
- 不对 `db.py`、`sv.py`、`pw.py` 做任何修改
- 不改变 `internal/` 目录的接口

## 目标文件结构

```
weibo/
├── __init__.py           # 插件入口 (~200行)
├── fav.py                # [NEW] 收藏夹系统
├── resolve.py            # [NEW] URL 解析 + reaction
├── sv.py                 # Service (不变)
├── db.py                 # DB (不变)
├── pw.py                 # Playwright (不变)
├── post.py               # WeiboPost (按 Phase 1 收尾后)
├── post_helper.py        # post facade
├── post_model_helper.py  # 辅助函数
├── request.py            # cookie + 导出
├── request_runtime.py   # API 实现
├── sub.py                # 定时任务
├── sub_helper.py         # sub facade
└── internal/
    ├── __init__.py
    ├── post_runtime.py
    └── sub_runtime.py
```

## `fav.py` 设计

### 数据层

所有数据操作封装为模块级函数，保持纯函数风格（副作用仅在文件 I/O）：

```python
# 持久化操作
_load_weibo_favs() -> dict[str, list[str]]
_save_weibo_favs(favorites: dict[str, list[str]]) -> None
append_fav(uid: str, id: str) -> bool          # 唯一的外部写入口

# 查询操作
_list_favorite_uid_ids(target_uid: str | None) -> list[str]
_load_favorite_post_metadata(uid: str, post_id: str) -> dict | None
_summarize_favorite_content(content: str, limit: int = 80) -> str
_search_favorite_posts(keyword: str, target_uid: str | None) -> list[dict]
_resolve_favorite_uid_ids(post_ref: str) -> list[str]
_build_favorite_search_messages(keyword: str, results: list[dict], target_uid: str | None) -> list[Message]
```

### 命令层

三个收藏命令 handler 从 `__init__.py` 迁入：

- `random_weibo_favorite(bot, event)` — `sv.on_command("随机微博收藏")`
- `search_weibo_favorite(bot, event)` — `sv.on_command("搜索微博收藏")`
- `show_weibo_favorite(bot, event)` — `sv.on_command("查看微博收藏")`

handler 函数名与 `__init__.py` 中的现有函数一致，`__init__.py` 改为 import 后直接注册。

### 对外接口

```python
__all__ = [
    "append_fav",
    "random_weibo_favorite",
    "search_weibo_favorite",
    "show_weibo_favorite",
]
```

### 内部依赖

- `weibo_img_dir`, `weibo_msg_dir`, `weibo_video_dir` → 从 `post.py`（或 helper）import
- `post_msg_from_uid_id`, `render_messages` → 从 `post.py` import
- `send_segments` → 从 `hoshino.util` import

## `resolve.py` 设计

### 职责

提供微博 URL 的识别与 reaction 处理逻辑，不持有 sv 注册。

### 内容

```python
weibo_regexs: dict[str, re.Pattern]  # 三个编译好的正则

async def reaction_weibo_rule(bot: Bot, event: GroupMsgEmojiLikeEvent, state: T_State) -> bool:
    """检查是否是 319 emoji reaction 且消息包含微博 URL"""

async def handle_weibo_reaction(state: T_State) -> None:
    """从缓存或 API 获取微博信息，调用 append_fav 收藏"""
```

`handle_weibo_reaction` 内部调用 `append_fav` 需要 import `fav.py`。这是 fav ↔ resolve 之间的唯一交叉依赖，方向为 `resolve → fav`（resolve 依赖 fav 的数据写入能力）。

### 对外接口

```python
__all__ = [
    "weibo_regexs",
    "reaction_weibo_rule",
    "handle_weibo_reaction",
]
```

### 注册方式

`sv.on_notice` 的注册保留在 `__init__.py` 中，resolve 只提供纯函数：

```python
# __init__.py
from .resolve import reaction_weibo_rule, handle_weibo_reaction

svpost_notice = sv.on_notice(
    rule=reaction_weibo_rule,
    permission=SUPERUSER,
    priority=5,
    block=True,
)

@svpost_notice.handle()
async def _handle_weibo_reaction(state: T_State):
    await handle_weibo_reaction(state)
```

## `__init__.py` 最终形态

拆分后 `__init__.py` 保留以下内容（约 200 行）：

1. **Import 聚合** — 从各子模块导入符号
2. **sv.on_notice 注册** — reaction 规则绑定
3. **配置命令** — `configwb`, `showconfigwb`
4. **订阅管理命令** — 添加/删除/列出/查看订阅
5. **Superuser 命令** — `微博随图`, `微博随影`, `查库微博`
6. **收藏命令注册** — 从 `fav.py` import handler 后注册

### 保留在 `__init__.py` 的理由

- 配置和订阅管理命令直接操作 `db.py` 的 CRUD 函数，代码量小且紧密耦合
- `微博随图`/`微博随影` 各约 20 行，移到独立文件反而增加 import 链路
- `查库微博` 约 20 行，直接操作 `db.py`

### Import 拓扑

```
__init__.py
  ├── .db         (CRUD)
  ├── .sv         (sv)
  ├── .sub        (uid_manager)
  ├── .post       (WeiboPost, render_messages, post_msg_from_uid_id, ...)
  ├── .request    (get_weibo_new, parse_weibo_with_id, parse_mapp_weibo)
  ├── .fav        (append_fav, 收藏命令 handlers)
  └── .resolve    (weibo_regexs, reaction_weibo_rule, handle_weibo_reaction)

resolve.py
  └── .fav        (append_fav)
```

没有循环依赖。最长依赖链为 `__init__ → resolve → fav → post`。

## 兼容性要求

- 所有命令的别名、权限、优先级保持不变
- 收藏夹 JSON 格式和路径（`config.data_dir / "weibofavorite.json"`）不变
- `weibo_regexs` 的 key（`"weibo"`, `"mweibo"`, `"mappweibo"`）和匹配逻辑不变
- reaction handler 的 state 键名（`__weibo_name`, `__weibo_url` 等）不变

## 错误处理

- 收藏夹加载失败时返回空字典（保持现有行为）
- reaction 处理中 API 解析失败时记录错误日志，不抛出（保持现有行为）
- `append_fav` 重复添加时返回 `False`（保持现有行为）

## 测试要求

- 收藏夹 JSON 读写往返测试
- `_search_favorite_posts` 关键词匹配测试（含 casefold 行为）
- `_resolve_favorite_uid_ids` 引用解析测试（ID 和 UID_ID 两种输入）
- reaction rule 真/假阳性判断测试
- `handle_weibo_reaction` 对不同 URL 类型走不同解析路径的覆盖

## 与其他 spec 的关系

本 spec 覆盖 Phase 2（`__init__.py` 拆分）。Phase 1（post/sub runtime 收尾）的 spec 见 [`2026-05-13-weibo-post-pipeline-design.md`](./2026-05-13-weibo-post-pipeline-design.md)。

两个 spec 按顺序执行：先完成 Phase 1 的 runtime 清理，再进行 Phase 2 的 `__init__.py` 拆分。相互之间没有强依赖——Phase 2 的 `fav.py` 和 `resolve.py` 只依赖 Phase 1 完成后稳定的 public API（`post.py`, helper），不依赖 runtime 内部实现。
