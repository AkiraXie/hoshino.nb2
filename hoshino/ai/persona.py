"""persona 领域层：三级解析、CRUD 与绑定。

优先级：scope 级（scope 绑定）> 全局级 > 默认级（``AIConfig.system_prompt``）。
persona 与绑定全部存 DB（``ai_personas`` / ``ai_scope_personas`` / ``ai_globals``）。
本模块是领域函数；LLM tool（``persona_manage``）与 admin command 都是薄入口，共用这里
的函数，互不调用对方 handler。
"""

from __future__ import annotations

import json

from . import store
from .config import AIConfig

GLOBAL_PERSONA_KEY = "global_persona"


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
        created_by=created_by,
    )


def update_persona(
    name: str,
    *,
    gender: str | None = None,
    personality: str | None = None,
    description: str | None = None,
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
