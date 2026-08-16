"""persona 领域层：三级解析、CRUD 与绑定、模板变量渲染。

优先级：scope 级（scope 绑定）> 全局级 > 默认级（``AIConfig.system_prompt``）。
persona 与绑定全部存 DB（``ai_personas`` / ``ai_scope_personas`` / ``ai_globals``）。
本模块是领域函数；LLM tool（``persona_manage``）与 admin command 都是薄入口，共用这里
的函数，互不调用对方 handler。

persona 文本支持 ``{{variable}}`` 严格模板插值（对齐 DeepSeek Harness 的
dsh-persona）：作用域解析后、注入模型前渲染；未知变量 fail loud（ValueError），
由调用方捕获回退原文并记日志。
"""

from __future__ import annotations

import json
import re
import time

from . import prompts, store
from .config import AIConfig

GLOBAL_PERSONA_KEY = "global_persona"

# 模板变量名：小写字母开头，字母数字下划线（与 dsh 的 VARIABLE_NAME 一致）。
_VARIABLE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_GROUP_AT = re.compile(r"\{\{([^{}]*)\}\}")

# 内置变量集（固定集合；集合外的引用 fail loud，集合内解析失败渲染为空串）。
BUILTIN_VARIABLES = frozenset({"date", "time", "weekday", "scope", "group_name", "user_name"})


def builtin_variables(scope_key: str | None) -> dict[str, str]:
    """内置模板变量：日期/时间/星期/scope 稳定可用，群名/昵称尽力而为。"""
    now = time.localtime()
    return {
        "date": time.strftime("%Y-%m-%d", now),
        "time": time.strftime("%H:%M", now),
        "weekday": time.strftime("%A", now),
        "scope": scope_key or "",
        "group_name": "",
        "user_name": "",
    }


def render_persona(text: str, variables: dict[str, str]) -> str:
    """渲染 persona 模板：替换 ``{{variable}}``，未知变量抛 ValueError。

    集合外的变量名 fail loud（对齐 dsh 语义，尽早暴露模板笔误）；集合内的
    变量由调用方填值，值为空串时渲染为空（可选变量，如解析不到的群名）。
    """
    result = ""
    last = 0
    for match in _GROUP_AT.finditer(text):
        name = match.group(1)
        if not _VARIABLE_NAME.match(name):
            raise ValueError(
                f"persona 模板变量名非法：{{{{{name}}}}}（须匹配 {_VARIABLE_NAME.pattern}）"
            )
        if name not in variables:
            raise ValueError(
                f"persona 模板引用了未知变量 {{{{ {name} }}}}；"
                f"可用内置变量：{', '.join(sorted(BUILTIN_VARIABLES))}"
            )
        result += text[last : match.start()] + variables[name]
        last = match.end()
    return result + text[last:]


def build_prompt(
    name: str,
    gender: str = "",
    personality: str = "",
    description: str = "",
) -> str:
    """按特征模板拼装 persona prompt。"""
    head = f"你是 {name}"
    if gender:
        head += f"，{gender}"
    if personality:
        head += f"。{personality}"
    prompt = head + "。"
    if description:
        prompt += f"\n{description}"
    return prompt


def resolve_prompt(scope_key: str | None, config: AIConfig) -> str:
    """三级解析：scope 级 > 全局级 > 默认级。"""
    if scope_key:
        persona_id = store.get_scope_persona_id(scope_key)
        if persona_id is not None:
            persona = store.get_persona_by_id(persona_id)
            if persona and persona["prompt"]:
                return persona["prompt"]
    global_name = store.get_global_value(GLOBAL_PERSONA_KEY)
    if global_name:
        persona = store.get_persona_by_name(global_name)
        if persona and persona["prompt"]:
            return persona["prompt"]
    return config.system_prompt


def resolve_persona(scope_key: str | None, config: AIConfig) -> str:
    """兼容别名：旧调用方（测试/历史入口）仍可用。"""
    return resolve_prompt(scope_key, config)


def list_personas() -> list[dict]:
    return store.list_personas()


def get_persona(name: str) -> dict | None:
    return store.get_persona_by_name(name)


def create_persona(
    name: str,
    *,
    gender: str = "",
    personality: str = "",
    description: str = "",
    begin_dialogs: list[dict[str, str]] | None = None,
    created_by: str = "",
) -> dict:
    """创建 persona；prompt 由特征模板生成。重名抛 ValueError（由入口层转提示）。"""
    if store.get_persona_by_name(name) is not None:
        raise ValueError(f"persona `{name}` 已存在。")
    prompt = build_prompt(name, gender, personality, description)
    traits = json.dumps(
        {
            "gender": gender,
            "personality": personality,
            "description": description,
        },
        ensure_ascii=False,
    )
    return store.create_persona(
        name=name,
        gender=gender,
        personality=personality,
        description=description,
        prompt=prompt,
        traits_json=traits,
        begin_dialogs_json=dialogs_to_json(begin_dialogs),
        created_by=created_by,
    )


def update_persona(
    name: str,
    *,
    gender: str | None = None,
    personality: str | None = None,
    description: str | None = None,
    begin_dialogs: list[dict[str, str]] | None = None,
) -> dict | None:
    """更新特征并重新生成 prompt；persona 不存在返回 None。"""
    current = store.get_persona_by_name(name)
    if current is None:
        return None
    new_gender = gender if gender is not None else current["gender"]
    new_personality = personality if personality is not None else current["personality"]
    new_description = description if description is not None else current["description"]
    prompt = build_prompt(name, new_gender, new_personality, new_description)
    return store.update_persona(
        name,
        gender=new_gender,
        personality=new_personality,
        description=new_description,
        prompt=prompt,
        begin_dialogs_json=(dialogs_to_json(begin_dialogs) if begin_dialogs is not None else None),
    )


def delete_persona(name: str) -> bool:
    return store.delete_persona(name)


def bind_scope(scope_key: str, name: str, updated_by: str = "") -> bool:
    """绑定 scope 级 persona；persona 不存在返回 False。"""
    persona = store.get_persona_by_name(name)
    if persona is None:
        return False
    store.bind_scope_persona(scope_key, persona["id"], updated_by)
    return True


def clear_scope(scope_key: str) -> bool:
    return store.clear_scope_persona(scope_key)


def set_global(name: str) -> bool:
    """设置全局 persona；persona 不存在返回 False。"""
    persona = store.get_persona_by_name(name)
    if persona is None:
        return False
    store.set_global_value(GLOBAL_PERSONA_KEY, name)
    return True


def clear_global() -> bool:
    return store.clear_global_value(GLOBAL_PERSONA_KEY)


def dialogs_to_json(dialogs: list[dict[str, str]] | None) -> str:
    """示例对话 → JSON 存储（只保留 user/assistant 字段）。"""
    if not dialogs:
        return "[]"
    cleaned = [
        {"user": d.get("user", ""), "assistant": d.get("assistant", "")}
        for d in dialogs
        if isinstance(d, dict) and d.get("user") and d.get("assistant")
    ]
    return json.dumps(cleaned, ensure_ascii=False)


def parse_dialogs_text(text: str, char_name: str) -> list[dict[str, str]]:
    """把交替的「用户: … <名字>: …」文本解析成示例对话对。

    按角色前缀切分（支持同一行内多轮，聊天输入没有换行）；user 侧前缀为
    ``用户:`` / ``user:``，assistant 侧为 ``<char_name>:`` / ``assistant:`` /
    ``你:`` / ``我:``。不完整的轮丢弃。供 ``ai persona create/update --dialogs`` 使用。
    """
    pattern = re.compile(
        rf"(用户|user|assistant|你|我|{re.escape(char_name)})\s*:\s*",
        re.IGNORECASE,
    )
    matches = list(pattern.finditer(text))
    dialogs: list[dict[str, str]] = []
    user_part: str | None = None
    for index, match in enumerate(matches):
        role = match.group(1).lower()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        content = text[match.end() : end].strip()
        if not content:
            continue
        if role in ("用户", "user"):
            user_part = content
        elif user_part is not None:
            dialogs.append({"user": user_part, "assistant": content})
            user_part = None
    return dialogs


def resolve_dialogs(scope_key: str | None) -> list[dict[str, str]]:
    """解析当前 scope 的示例对话：scope 级 persona > 全局 > 默认内置。"""
    if scope_key:
        persona_id = store.get_scope_persona_id(scope_key)
        if persona_id is not None:
            persona = store.get_persona_by_id(persona_id)
            if persona and persona["begin_dialogs"]:
                return persona["begin_dialogs"]
    global_name = store.get_global_value(GLOBAL_PERSONA_KEY)
    if global_name:
        persona = store.get_persona_by_name(global_name)
        if persona and persona["begin_dialogs"]:
            return persona["begin_dialogs"]
    return list(prompts.DEFAULT_BEGIN_DIALOGS)


def missing_traits(gender: str, personality: str, description: str) -> str:
    """create 时缺失特征返回补全提示；全部补齐返回空串。"""
    missing = []
    if not gender:
        missing.append("性别")
    if not personality:
        missing.append("性格")
    if not description:
        missing.append("简介")
    return "创建人格需补充：" + "、".join(missing) if missing else ""
