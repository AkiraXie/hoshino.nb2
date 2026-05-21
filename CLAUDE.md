# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

HoshinoBot 迁移至 NoneBot2 的 QQ 机器人，通过 onebot v11 适配器连接 Lagrange/LLOneBot 等协议实现。uv 管理依赖，Python >= 3.10。

## Essential Commands

```bash
# 运行 bot
uv run python run.py

# 构建并启动 weibo_image_web（FastAPI 后端 + React 前端）
weibo_image_web/start_dev.sh

# 仅前端开发（Vite dev server，端口 5173）
cd weibo_image_web/frontend && npm run dev

# 前端构建
cd weibo_image_web/frontend && npm run build

# Lint
uv run ruff check .

# 添加/移除依赖
uv add <package>
uv remove <package>
```

## Architecture

### 启动流程

1. `run.py` 调用 `nonebot.init()` 后调用 `bootstrap()`
2. `bootstrap()` 按顺序执行：创建数据目录 → patch `Bot.send` 和 `Matcher.got` → 注册自定义事件类型 (`GroupReactionEvent`, `GroupMsgEmojiLikeEvent`) → 配置日志 → 将延迟 hook 下发至真实 driver
3. 加载 `hoshino/base/` 下的基础服务，再按配置加载 `hoshino/modules/` 下的模块

### Hook 注册表 (`hoshino/hooks.py`)

由于模块在 `nonebot.init()` 前就被 import，此时无法使用 NoneBot 的 hook 系统。`_Registry` 在 import 阶段收集回调，`bootstrap()` 时通过 `replay()` 统一下发：

- `on_startup` / `on_shutdown` / `on_bot_connect` / `on_bot_disconnect` — 标准生命周期
- `on_serial_startup` — 串行执行的 startup，阻塞 server 启动
- `on_post_startup` — server 启动后以 `asyncio.create_task` 后台执行，不阻塞
- `run_preprocessor` / `event_preprocessor` — 消息预处理

模块代码中应使用 `from hoshino.hooks import on_startup` 而非 `from nonebot import get_driver().on_startup`。

### Service 系统 (`hoshino/service.py`)

核心抽象。每个功能模块创建一个 `Service` 实例来管理群级开关：

```python
sv = Service("name", manage_perm=ADMIN, enable_on_default=True, visible=True)
```

- 服务状态持久化到 `data/service/{name}.json`
- 各群独立 enable/disable，`check_service()` 返回 `Rule` 过滤事件
- 所有 `Service.on_*` 方法（`on_command`, `on_keyword`, `on_regex`, `on_message`, `on_notice`, `on_request` 等）自动注入 service check rule
- `MatcherWrapper` 封装 NoneBot 的 `Matcher`，提供 `send`/`finish`/`reject`/`pause` 方法
- 每服务配置从 `hoshino/service_config/{name}.json` 读取

### Bootstrap Patches

`botstrap.py` 对 NoneBot 做了两处 monkey-patch：

1. **`Bot.send()`** — 根据 event 自动推断 `message_type`，支持 `at_sender`（群聊中 @ 用户）和 `call_header`（群聊中拼接头衔/群昵称）
2. **`Matcher.got()`** — 增加 `args_parser` 参数，允许自定义参数解析（类似 `receive` 但带解析器）

`hoshino/types.py` 提供 IDE TYPE_CHECKING stub，让 IDE 能识别这些扩展方法。

### 模块约束

模块只能在 `hoshino/modules/<category>/` 下（category = information, interactive, develop, tools, entertainment 等），由 `.env.prod` 的 `modules` 列表控制加载哪些类别。

### 自定义事件 (`hoshino/event.py`)

扩展 Lagrange (`GroupReactionEvent`) 和 LLOneBot (`GroupMsgEmojiLikeEvent`) 的消息表情回应事件，`bootstrap()` 注册到 Adapter。

### weibo_image_web

独立的前后端分离项目，不依赖 NoneBot：

- **后端**: `weibo_image_web/server.py` (FastAPI, 端口 9998)，读取 `data/weibomsgs/` 索引微博内容，提供 REST API
- **前端**: `weibo_image_web/frontend/` (React 19 + Vite 6 + TypeScript + Tailwind CSS 4)，瀑布流图片浏览 SPA
- `start_dev.sh` 一键构建前端并启动后端

### 数据目录

`data/` 下：`image/`, `favorite/`, `video/`, `db/`（SQLite cookies 数据库）, `service/`（服务开关状态 JSON）, `weibomsgs/`（微博数据）

## Remote Development

此项目运行在远程机器上。测试服务时需先运行 `ip addr` 获取实际 IP，**禁止使用 localhost/127.0.0.1**。前端 UI 验证使用 playwright-mcp 打开浏览器测试。

## 代码风格

- 严格保持 Python 3.10 兼容性（使用 `Optional[str]` 而非 `str | None` 作为运行时注解）
- `from __future__ import annotations` 在需要推迟求值的文件中使用
- Ruff lint（配置在 `pyproject.toml` 的 `[tool.ruff]` 段）
- 默认不写注释，除非 WHY 不明显
