"""computer/hoshino_nb2_code：仓库知识工具（只读）。

让 AI agent 了解当前代码仓库（hoshino.nb2）的基本情况、开发规范与 agent 工作流
程，并可直接读取仓库内文档/代码，用于改进 AI 模块自身代码（``hoshino/ai/``）。

只读、不执行、不落盘；路径严格限定在仓库根目录内（symlink 解析后 containment），
敏感路径（.env、.git、凭据、data/logs 等运行时目录）直接拒绝。工具受 computer
类别绑定控制：默认不注入，需管理员在 scope 显式开启。
"""

from __future__ import annotations

import os
from typing import Literal

from pydantic_ai import RunContext

from ...deps import AgentDeps

# hoshino/ai/tools/computer/repo_code.py → 上溯 4 级到仓库根目录。
_REPO_ROOT = os.path.realpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..")
)

_SENSITIVE_PARTS = (
    ".env",
    ".git",
    "credentials",
    "secrets",
    "id_rsa",
    "id_ed25519",
    "node_modules",
    "logs",
    "data",
    "__pycache__",
)
_MAX_READ_CHARS = 50_000

RepoAction = Literal["overview", "norms", "flow", "ai_module", "read"]

_OVERVIEW = """【hoshino.nb2 仓库概览】
项目：HoshinoBot，迁移到 NoneBot2 的多适配器 QQ 机器人（Python >=3.12，依赖由 uv 管理）。
- 适配器：OneBot V11（Lagrange/LLOneBot）、Milky（QQNT）、Telegram
- 启动：run.py（加载顺序是运行契约）；`uv run python run.py`；配置默认 .env.prod
- 运行时数据在 data/（不要清理/迁移）；独立微博图片 Web 应用：image_web/ + 前端

代码结构（依赖方向）：
- hoshino/core：平台中立核心（Service/权限/规则/调度）
- hoshino/platform：adapter 中立事件/DI/Target/Bot API（ob11/milky/telegram 隔离区）
- hoshino/content：内容推送引擎
- hoshino/base + hoshino/modules/<category>：内置服务与业务插件
- hoshino/ai：AI 对话/任务模块（本工具的改进对象）
- nb-tests/：NoneBug 跨适配器测试；.tests/：legacy 与微博专项测试

常用命令：
- uv run pytest nb-tests -q
- uv run pytest nb-tests/test_ai_persona.py nb-tests/test_ai_chat.py -q
- uv run ruff check . ；uv run ruff format --check . ；git diff --check"""

_NORMS = """【开发规范（AGENTS.md 要点）】
- 事实来源：以当前代码、pyproject.toml、测试与实际命令结果为准，文档可能滞后
- 改前先读相关实现与调用方；改动聚焦，不顺手重构无关代码，不覆盖用户改动
- 修复/实现配与风险相称的测试；涉及权限/规则/平台分发时覆盖成功与拒绝路径
- 结论必须有 lint/测试/构建/运行探针等客观证据；说明未执行或未通过的检查
- 不执行生产操作、不用真实机器人凭据或生产群聊测试、不提交 .env.prod 中的秘密
- 除非用户明确要求，不主动提交/推送 Git
- plan/调查报告/执行报告统一落 agent-plan-report/（已 gitignore；禁写 token/秘密，
  只记脱敏后的键名、数量、路径、命令结果与验证结论）

Python 风格（§7）：3.12 兼容；import 分组置顶；函数内 import 仅限循环依赖/可选依赖；
异步 I/O 不用阻塞调用；资源用 with 管理；捕获 Exception 不捕 BaseException；
日志带操作上下文但不输出秘密；公共 API 小而稳定。

测试策略（§8，风险递增）：纯函数单测 → Service/matcher 相关 nb-tests（至少 OB11/Milky）
→ 插件行为走真实 dispatch → 公共核心改动跑全量 nb-tests → 微博改动跑 .tests。

交付检查（§10）：git diff --check、ruff check/format、聚焦测试；公共核心或跨平台
改动再跑 uv run pytest nb-tests -q；前端改动跑前端 build。"""

_FLOW = """【agent 工作流程】
协作约定：Agent 的 plan / 调查报告 / 执行报告统一放 agent-plan-report/（gitignore，
禁写 secrets，只记录脱敏后的键名/路径/命令结果/验证结论）。plan 阶段不改业务代码，
用户确认后再执行，并在同一目录补执行结果与未覆盖风险。

专题文档（agent-flow/）：
- architecture.md：分层与 adapter 隔离边界
- ai.md：AI 模块结构（pydantic-ai 能力使用 + 自有扩展 + 参考致谢）
- ai-tools.md：AI 模块工具系统（注册表、类别/风险门控、hoshino-nb2-code 工具）
- docs/plugin-development.md：插件开发完整指南
- milky.md / telegram.md：平台能力与限制
- milky-plugin-test-protocol.md：Milky 端到端行为测试标准"""

_AI_MODULE = """【AI 模块自身（hoshino/ai/）与改进指南】
- config.py：AIConfig（默认 provider、护栏、代理、渲染配置）
- prompts.py：DEFAULT_SYSTEM_PROMPT（默认人格）、DEFAULT_BEGIN_DIALOGS（few-shot
  示例对话，锚定说话方式）、TOOL_CALL_PROMPT；output.md 加载为 OUTPUT_STYLE_RULES
  （强制输出规范，所有 persona 生效）
- persona.py：三级 persona 解析（scope > 全局 > 默认）与 {{variable}} 模板渲染
- providers.py：build_agent 组装（model/动态 system prompt/工具集）
- runner.py：run_agent 驱动、describe_node 实时日志、重试
- store.py / metrics.py：SQLite 持久化与用量统计（ai stats 数据源）
- tools/：注册表 tools/__init__.py REGISTRATIONS（分类/风险/surface）与实现
  （core/computer/bot/web/skill）；computer 默认不注入，需管理员显式开启
- task/：后台任务运行时（TaskContext/审批/调度）
- modules/ai/：chat.py（# 对话入口）、ai_admin.py（管理命令）、zssm.py（解释命令）
- 模块结构、pydantic-ai 能力使用与自有扩展见 agent-flow/ai.md；工具系统完整说明见
  agent-flow/ai-tools.md

改进 AI 行为常见落点：
- 人格/口吻：prompts.py 的 DEFAULT_SYSTEM_PROMPT / DEFAULT_BEGIN_DIALOGS
- 输出格式/禁用词：hoshino/ai/output.md（改动注意保留测试断言的关键词）
- 新增工具：tools/<category>/xxx.py 写函数 + tools/__init__.py 注册一行
- 新增配置：hoshino/ai/config.py AIConfig 字段（挂载进 HoshinoConfig，env AI_*，写 .env.prod）

验证：uv run pytest nb-tests/test_ai_persona.py nb-tests/test_ai_chat.py -q；
uv run ruff check hoshino/ai；真实 provider 人格探针：
uv run python nb-tests/one-shot/live_ai_persona_probe.py"""


def _resolve_contained(root: str, path: str) -> str:
    """解析 path 相对 root 的绝对路径；越界抛 ValueError。"""
    candidate = os.path.abspath(os.path.join(root, path))
    resolved = os.path.realpath(candidate)
    real_root = os.path.realpath(root)
    if not (resolved == real_root or resolved.startswith(real_root + os.sep)):
        raise ValueError("路径越出仓库根目录。")
    return resolved


def _read_repo_file(path: str) -> str:
    if path.startswith("/") or ".." in path.split("/"):
        return "只接受仓库内的相对路径（如 `hoshino/ai/prompts.py`）。"
    try:
        resolved = _resolve_contained(_REPO_ROOT, path)
    except ValueError as exc:
        return str(exc)
    parts = resolved.replace(os.sep, "/").lower().split("/")
    if any(part in _SENSITIVE_PARTS or part.startswith(".env") for part in parts):
        return "敏感路径不允许访问。"
    if not os.path.isfile(resolved):
        return f"文件不存在：{path}"
    try:
        with open(resolved, encoding="utf-8") as fh:
            return fh.read(_MAX_READ_CHARS)
    except (OSError, UnicodeDecodeError) as exc:
        return f"读取失败：{exc}"


async def hoshino_nb2_code(
    ctx: RunContext[AgentDeps],
    action: RepoAction,
    path: str = "",
) -> str:
    """了解 hoshino.nb2 仓库：基本情况 / 开发规范 / agent 流程 / AI 模块自身（只读）。

    - overview：仓库概览（项目、技术栈、目录结构、常用命令）
    - norms：开发规范摘要（事实来源、风格、测试策略、交付检查）
    - flow：agent 工作流程（专题文档索引、plan/report 约定）
    - ai_module：AI 模块自身结构与改进指南（hoshino/ai/ 布局、加工具、测试位置）
    - read <path>：读取仓库内文件全文（限定仓库根目录，拒绝敏感路径）

    用于改进本仓库代码（尤其是 hoshino/ai/）前快速掌握上下文；详细内容可
    read 对应源文件（如 `read AGENTS.md`、`read hoshino/ai/prompts.py`）。
    """
    match action:
        case "overview":
            return _OVERVIEW
        case "norms":
            return _NORMS
        case "flow":
            return _FLOW
        case "ai_module":
            return _AI_MODULE
        case "read":
            if not path:
                return "read 需要 path 参数，如 `read hoshino/ai/prompts.py`。"
            return _read_repo_file(path)
        case _:
            return "未知 action，可用：overview / norms / flow / ai_module / read。"
