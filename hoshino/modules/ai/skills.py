"""Skill catalog / scope state 领域层。

内置技能位于 ``hoshino/modules/ai/skills/<name>/SKILL.md``；本地技能位于
``data/skills/<name>/SKILL.md``，本地覆盖同名内置。frontmatter 使用 Harness 支持的
SKILL.md 格式（``name`` + ``description``），不自研一套不兼容的 capability 协议。

scope 启停存 DB（``ai_skill_states``，无行默认启用）。Task 创建时的 skill archive
属于产品状态，落地在 Task 阶段；本层只负责 catalog 与 scope state。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from hoshino import data_dir

from . import store

BUILTIN_SKILLS_DIR = os.path.join(os.path.dirname(__file__), "skills")
LOCAL_SKILLS_DIR = os.path.join(data_dir, "skills")

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


@dataclass(frozen=True, slots=True)
class SkillInfo:
    name: str
    description: str
    source: str  # "builtin" | "local"
    path: str
    body: str
    version: str = ""


def _parse_skill(path: str, name: str, source: str) -> SkillInfo | None:
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        return None
    body = raw
    description = ""
    version = ""
    m = _FRONTMATTER_RE.match(raw)
    if m:
        front, body = m.group(1), m.group(2)
        for line in front.splitlines():
            if line.startswith("description:"):
                description = line.split(":", 1)[1].strip()
            elif line.startswith("version:"):
                version = line.split(":", 1)[1].strip()
    return SkillInfo(
        name=name,
        description=description,
        source=source,
        path=path,
        body=body.strip(),
        version=version,
    )


def _scan_dir(skills_dir: str, source: str) -> dict[str, SkillInfo]:
    result: dict[str, SkillInfo] = {}
    if not os.path.isdir(skills_dir):
        return result
    for name in sorted(os.listdir(skills_dir)):
        skill_path = os.path.join(skills_dir, name, "SKILL.md")
        if not os.path.isfile(skill_path):
            continue
        skill = _parse_skill(skill_path, name, source)
        if skill is not None:
            result[name] = skill
    return result


def list_skills() -> list[SkillInfo]:
    """内置 + 本地合并；本地覆盖同名内置。"""
    catalog = _scan_dir(BUILTIN_SKILLS_DIR, "builtin")
    catalog.update(_scan_dir(LOCAL_SKILLS_DIR, "local"))
    return sorted(catalog.values(), key=lambda s: s.name)


def get_skill(name: str) -> SkillInfo | None:
    for skill in list_skills():
        if skill.name == name:
            return skill
    return None


def list_enabled(scope_key: str) -> list[SkillInfo]:
    """返回当前 scope 已启用的技能（无行默认启用）。"""
    return [
        skill
        for skill in list_skills()
        if store.get_skill_enabled(scope_key, skill.name)
    ]


def set_enabled(scope_key: str, name: str, enabled: bool) -> bool:
    """启用/停用技能；技能不存在返回 False。"""
    if get_skill(name) is None:
        return False
    store.set_skill_enabled(scope_key, name, enabled)
    return True
