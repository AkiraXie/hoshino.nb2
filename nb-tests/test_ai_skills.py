"""Skill catalog / scope state 领域层测试。"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.usefixtures("_clear_uninfo_cache")


def test_list_skills_contains_builtin(tmp_store):
    from hoshino.ai import skills

    names = {s.name for s in skills.list_skills()}
    assert "web-research" in names


def test_get_skill_parses_frontmatter(tmp_store):
    from hoshino.ai import skills

    skill = skills.get_skill("web-research")
    assert skill is not None
    assert skill.source == "builtin"
    assert skill.description
    assert skill.version == "1.0.0"
    assert skill.body


def test_default_all_enabled(tmp_store):
    """无 scope 状态行时默认全启用。"""
    from hoshino.ai import skills

    all_skills = skills.list_skills()
    enabled = skills.list_enabled("milky:1")
    assert [s.name for s in enabled] == [s.name for s in all_skills]


def test_disable_excludes(tmp_store):
    from hoshino.ai import skills

    assert skills.set_enabled("milky:1", "web-research", False) is True
    assert skills.list_enabled("milky:1") == []
    assert skills.set_enabled("milky:1", "web-research", True) is True
    assert [s.name for s in skills.list_enabled("milky:1")] == ["web-research"]


def test_set_enabled_missing_skill_returns_false(tmp_store):
    from hoshino.ai import skills

    assert skills.set_enabled("milky:1", "不存在", True) is False


def test_local_skill_overrides_builtin(tmp_store, tmp_path, monkeypatch):
    from hoshino.ai import skills

    local_dir = tmp_path / "skills"
    (local_dir / "web-research").mkdir(parents=True)
    (local_dir / "web-research" / "SKILL.md").write_text(
        "---\nname: web-research\ndescription: 本地覆盖版。\n---\n本地正文\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(skills, "LOCAL_SKILLS_DIR", str(local_dir))
    skill = skills.get_skill("web-research")
    assert skill is not None
    assert skill.source == "local"
    assert skill.description == "本地覆盖版。"
    assert "本地正文" in skill.body
