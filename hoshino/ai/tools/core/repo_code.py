"""core/hoshino_nb2_code：仓库知识工具（只读）。

让 AI agent 了解当前代码仓库（hoshino.nb2）的基本情况、开发规范与 agent 工作流
程，并可直接读取仓库内文档/代码。询问机器人本身（命令含义、实现、help 文本）
时优先用本工具，而不是凭印象编。

只读、不执行、不落盘；路径严格限定在仓库根目录内（symlink 解析后 containment），
敏感路径（.env、.git、凭据、data/logs 等运行时目录）直接拒绝。属于 core 类别，
chat / zssm 默认注入。
"""

from __future__ import annotations

import ast
import os
from typing import Literal

from arclet.alconna import command_manager
from pydantic_ai import RunContext

from ...deps import AgentDeps

# hoshino/ai/tools/core/repo_code.py → 上溯 4 级到仓库根目录。
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
_MAX_HELP_CHARS = 8_000
_MAX_HELP_MATCHES = 8

RepoAction = Literal["overview", "norms", "flow", "ai_module", "help", "read"]

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
- 默认不信任 agent-plan-report/ 旧稿（含 archived/）；流程规范只信 AGENTS.md 与
  agent-flow/。调研/规划/报告由当前任务自行产出，需要落盘时仍写 agent-plan-report/
  （gitignore；禁写 token/秘密，只记脱敏键名、数量、路径、命令结果与验证结论）

Python 风格（§7）：3.12 兼容；import 分组置顶；函数内 import 仅限循环依赖/可选依赖；
异步 I/O 不用阻塞调用；资源用 with 管理；捕获 Exception 不捕 BaseException；
日志带操作上下文但不输出秘密；公共 API 小而稳定。

测试策略（§8，风险递增）：纯函数单测 → Service/matcher 相关 nb-tests（至少 OB11/Milky）
→ 插件行为走真实 dispatch → 公共核心改动跑全量 nb-tests → 微博改动跑 .tests。

交付检查（§10）：git diff --check、ruff check/format、聚焦测试；公共核心或跨平台
改动再跑 uv run pytest nb-tests -q；前端改动跑前端 build。"""

_FLOW = """【agent 工作流程】
协作约定：默认不信任 agent-plan-report/ 旧稿（含 archived/）。流程规范只信 AGENTS.md
与 agent-flow/；调研/规划/报告由当前任务自行产出。需要落盘时仍写 agent-plan-report/
（gitignore，禁写 secrets，只记脱敏键名/路径/命令结果/验证结论）。plan 阶段不改业务
代码，用户确认后再执行，并在同一目录补执行结果与未覆盖风险。

专题文档（agent-flow/）：
- architecture.md：分层与 adapter 隔离边界
- ai.md：AI 模块结构（pydantic-ai 能力使用 + 自有扩展 + 参考致谢）
- ai-tools.md：AI 模块工具系统（注册表、类别/风险门控、hoshino_nb2_code 工具）
- docs/plugin-development.md：插件开发完整指南
- milky.md / telegram.md：平台能力与限制
- milky-plugin-test-protocol.md：Milky 端到端行为测试标准"""

_AI_MODULE = """【AI 模块自身（hoshino/ai/）与改进指南】
- config.py：AIConfig（默认 provider、护栏、代理、渲染配置）
- prompts.py：DEFAULT_SYSTEM_PROMPT（默认人格）、DEFAULT_BEGIN_DIALOGS（few-shot
  示例对话，锚定说话方式）、TOOL_CALL_PROMPT；output.md 加载为 OUTPUT_STYLE_RULES
  （强制输出规范，所有 persona 生效）
- persona.py：三级 persona 解析（scope > 全局 > 默认）与 {{variable}} 模板渲染
- providers.py：build_agent 组装（model/动态 system prompt/工具集/输出形态）
- reply.py：回复交付形态（纯文本消息 / Markdown 图片）：reply 输出工具、排版判定
  （带 Markdown/排版记号一律图片，图片是保底）、纯文本分段（140~210 字/条），
  工具文档即该模块的 deliver_reply docstring
- runner.py：run_agent 驱动、describe_node 实时日志、重试
- store.py / metrics.py：SQLite 持久化与用量统计（ai stats 数据源）
- tools/：注册表 tools/__init__.py REGISTRATIONS（分类/风险/surface）与实现
  （core/computer/bot/web/skill）；hoshino_nb2_code 属于 core，chat/zssm 默认可用；
  computer（bash/python/file）默认不注入，需管理员显式开启
- task/：后台任务运行时（TaskContext/审批/调度）
- modules/ai/：chat.py（# 对话入口）、ai_admin.py（管理命令）、zssm.py（解释命令）
- 模块结构、pydantic-ai 能力使用与自有扩展见 agent-flow/ai.md；工具系统完整说明见
  agent-flow/ai-tools.md

改进 AI 行为常见落点：
- 人格/口吻：prompts.py 的 DEFAULT_SYSTEM_PROMPT / DEFAULT_BEGIN_DIALOGS
- 输出格式/禁用词：hoshino/ai/output.md（改动注意保留测试断言的关键词）
- 回复形态（纯文本 vs 图片）：hoshino/ai/reply.py（工具文档与形态判定同处一模块）
- 新增工具：tools/<category>/xxx.py 写函数 + tools/__init__.py 注册一行
- 新增配置：hoshino/ai/config.py AIConfig 字段（挂载进 HoshinoConfig，env AI_*，写 .env.prod）

验证：uv run pytest nb-tests/modules/ai -q；uv run ruff check hoshino/ai；
真实 provider 探针：ONE_SHOT_LIVE=1 uv run pytest
nb-tests/one-shot/test_persona_live.py nb-tests/one-shot/test_reply_format_live.py -s -q"""

# 用户问机器人命令时优先读这些 help 文本；query 对命令名做前缀/子串匹配。
_HELP_SOURCES: tuple[tuple[str, str, str], ...] = (
    ("ai", "hoshino/modules/ai/ai_admin.py", "USAGE"),
    ("ai setup", "hoshino/modules/ai/ai_admin.py", "_SETUP_USAGE"),
    ("ai model", "hoshino/modules/ai/ai_admin.py", "_MODEL_USAGE"),
    ("ai search", "hoshino/modules/ai/ai_admin.py", "_SEARCH_USAGE"),
    ("ai tools", "hoshino/modules/ai/ai_admin.py", "_TOOLS_USAGE"),
    ("ai persona", "hoshino/modules/ai/ai_admin.py", "_PERSONA_USAGE"),
    ("ai config", "hoshino/modules/ai/ai_admin.py", "_CONFIG_USAGE"),
    ("ai alter", "hoshino/modules/ai/ai_admin.py", "_ALTER_USAGE"),
    ("ai task", "hoshino/modules/ai/task_commands.py", "_USAGE"),
    ("zssm", "hoshino/modules/ai/zssm/__init__.py", ""),
    ("#new / #switch / #list / #clear / #goal", "hoshino/modules/ai/chat.py", ""),
)


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


def _truncate(text: str, limit: int = _MAX_HELP_CHARS) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n…(截断)"


def _normalize_help_query(raw: str) -> str:
    """去掉 # / 前导 help，便于 ``#help ai model set`` 落到 ``ai model set``。"""
    tokens = raw.strip().lstrip("#").split()
    if tokens and tokens[0].casefold() in {"help", "?"}:
        tokens = tokens[1:]
    return " ".join(tokens).casefold()


def _label_tokens(label: str) -> list[str]:
    cleaned = label.replace("/", " ").replace("|", " ").replace("、", " ")
    return [tok.lstrip("#") for tok in cleaned.casefold().split() if tok.lstrip("#")]


def _match_rank(query: str, label: str) -> tuple[int, int] | None:
    """匹配优先级：精确 > 标签是 query 前缀（``ai model`` vs ``ai model set``）> 其它。"""
    if not query:
        return None
    l_tokens = _label_tokens(label)
    q_tokens = query.replace("/", " ").split()
    label_cf = " ".join(l_tokens)
    if not q_tokens or not l_tokens:
        return None
    if query == label_cf:
        return (0, -len(l_tokens))
    if q_tokens[: len(l_tokens)] == l_tokens:
        return (1, -len(l_tokens))
    if l_tokens[: len(q_tokens)] == q_tokens:
        return (2, -len(l_tokens))
    if all(token in l_tokens for token in q_tokens):
        return (2, -len(q_tokens))
    if query in label.casefold():
        return (3, -len(label))
    return None


def _select_help_sources(query: str) -> list[tuple[str, str, str]]:
    scored: list[tuple[tuple[int, int], tuple[str, str, str]]] = []
    for item in _HELP_SOURCES:
        rank = _match_rank(query, item[0])
        if rank is not None:
            scored.append((rank, item))
    if not scored:
        return []
    scored.sort(key=lambda pair: pair[0])
    specific = [item for rank, item in scored if rank[0] <= 1]
    if specific:
        return [max(specific, key=lambda item: (len(_label_tokens(item[0])), len(item[0])))]
    return [item for _, item in scored]


def _joined_constant(node: ast.AST) -> str | None:
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError):
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, tuple) and value and all(isinstance(part, str) for part in value):
        return "".join(value)
    return None


def _extract_named_string(source: str, name: str) -> str | None:
    """抽出模块级 ``NAME = \"...\"`` / 括号拼接字符串常量。"""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id != name:
            continue
        return _joined_constant(node.value)
    return None


def _module_docstring(source: str) -> str:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ""
    return ast.get_docstring(tree) or ""


def _alconna_help(query: str) -> list[str]:
    """运行时 Alconna 注册表的 get_help()；bot 未加载时返回空。"""
    hits: list[str] = []
    try:
        commands = command_manager.get_commands()
    except Exception:
        return []
    for cmd in commands:
        name = str(getattr(cmd, "name", "") or "")
        if not name:
            continue
        name_cf = name.casefold()
        aliases = [str(a) for a in getattr(cmd, "aliases", ()) or ()]
        names = [name_cf, *[a.casefold() for a in aliases]]
        if not any(query == n or query.startswith(f"{n} ") for n in names):
            continue
        meta = getattr(cmd, "meta", None)
        description = str(getattr(meta, "description", "") or "")
        usage = str(getattr(meta, "usage", "") or "")
        example = str(getattr(meta, "example", "") or "")
        try:
            help_text = cmd.get_help().strip()
        except Exception:
            help_text = ""
        extra = []
        if description and description != "Unknown":
            extra.append(f"description：{description}")
        if usage:
            extra.append(f"usage：{usage}")
        if example:
            extra.append(f"example：{example}")
        body = "\n".join([*extra, help_text]).strip() or "（无 help 文本）"
        hits.append(f"【Alconna `{name}`】\n{_truncate(body)}")
        if len(hits) >= _MAX_HELP_MATCHES:
            break
    return hits


def _help_catalog() -> str:
    lines = ["可查询的内置命令 help（query 用命令名，如 `ai model` / `zssm` / `#goal`）："]
    lines.extend(f"- {label}  ← {path}" for label, path, _ in _HELP_SOURCES)
    lines.append("也可直接 query 任意已加载的 Alconna 命令名，会返回运行时 get_help()。")
    return "\n".join(lines)


def _lookup_help(query: str) -> str:
    needle = _normalize_help_query(query)
    if not needle:
        return _help_catalog()

    matched = _select_help_sources(needle)

    sections: list[str] = []
    for label, path, const_name in matched:
        source = _read_repo_file(path)
        if source.startswith(("文件不存在", "读取失败", "敏感路径", "只接受", "路径越出")):
            sections.append(f"【{label}】读取 `{path}` 失败：{source}")
            continue
        if const_name:
            text = _extract_named_string(source, const_name)
            if text is None:
                sections.append(f"【{label}】`{path}` 中未找到 `{const_name}`。可 read 该文件。")
                continue
            sections.append(f"【{label}】`{path}` / `{const_name}`\n{_truncate(text.strip())}")
        else:
            doc = _module_docstring(source)
            if not doc:
                sections.append(f"【{label}】`{path}` 无模块 docstring，可 read 该文件。")
                continue
            sections.append(f"【{label}】`{path}` 模块说明\n{_truncate(doc)}")
        if len(sections) >= _MAX_HELP_MATCHES:
            break

    sections.extend(_alconna_help(needle))
    if sections:
        return "\n\n".join(sections[:_MAX_HELP_MATCHES])
    return (
        f"没有找到与 `{query}` 匹配的命令 help。\n"
        f"{_help_catalog()}\n"
        "也可以 `read` 对应源文件，例如 `hoshino/modules/ai/ai_admin.py`。"
    )


async def hoshino_nb2_code(
    ctx: RunContext[AgentDeps],
    action: RepoAction,
    path: str = "",
    query: str = "",
) -> str:
    """了解 hoshino.nb2 仓库与机器人命令：概况 / 规范 / 流程 / 命令 help（只读）。

    - overview：仓库概览（项目、技术栈、目录结构、常用命令）
    - norms：开发规范摘要（事实来源、风格、测试策略、交付检查）
    - flow：agent 工作流程（专题文档索引、plan/report 约定）
    - ai_module：AI 模块自身结构与改进指南（hoshino/ai/ 布局、加工具、测试位置）
    - help [query]：查机器人命令含义。query 为空列出目录；否则匹配内置 USAGE /
      模块说明，以及运行时 Alconna get_help()。例如 `help ai model`、`help zssm`、
      `help #goal`。用户问「zssm / ai model reset / #help ai model set 是什么意思」
      时必须先调本 action，不要凭印象编。需要实现细节时再 read 对应源文件。
    - read <path>：读取仓库内文件全文（限定仓库根目录，拒绝敏感路径）

    用于回答「这个机器人能干什么 / 这条命令是什么意思」，以及改进本仓库代码前
    快速掌握上下文。详细实现可再 read 对应源文件
    （如 `read AGENTS.md`、`read hoshino/ai/prompts.py`、
    `read hoshino/modules/ai/ai_admin.py`）。
    """
    del ctx  # pydantic-ai 需要 ctx 签名；本工具只读仓库，不读会话状态。
    match action:
        case "overview":
            return _OVERVIEW
        case "norms":
            return _NORMS
        case "flow":
            return _FLOW
        case "ai_module":
            return _AI_MODULE
        case "help":
            return _lookup_help(query or path)
        case "read":
            if not path:
                return "read 需要 path 参数，如 `read hoshino/ai/prompts.py`。"
            return _read_repo_file(path)
        case _:
            return "未知 action，可用：overview / norms / flow / ai_module / help / read。"
