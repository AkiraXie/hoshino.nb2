"""GoalService 单元测试：每 scope 单目标 + revision CAS + phase 迁移 + round cap。"""

from __future__ import annotations

import pytest

from hoshino.ai.goal import GoalConflict, GoalRef, GoalService


@pytest.fixture
def svc():
    return GoalService()


def test_create_and_get(svc, tmp_store):
    goal = svc.create("milky:1", "学习 dsh", max_rounds=3)
    assert goal.phase == "active"
    assert goal.revision == 1
    assert goal.max_rounds == 3

    loaded = svc.get("milky:1")
    assert loaded is not None
    assert loaded.objective == "学习 dsh"
    assert svc.get("milky:ghost") is None


def test_create_replaces_existing(svc, tmp_store):
    svc.create("milky:1", "旧目标", max_rounds=2)
    svc.create("milky:1", "新目标")
    loaded = svc.get("milky:1")
    assert loaded.objective == "新目标"
    assert loaded.revision == 1  # create 重置 revision
    assert loaded.max_rounds is None


def test_create_requires_nonempty_objective(svc, tmp_store):
    with pytest.raises(ValueError, match="不能为空"):
        svc.create("milky:1", "   ")


def test_update_cas_conflict(svc, tmp_store):
    svc.create("milky:1", "目标")
    with pytest.raises(GoalConflict):
        svc.update("milky:1", GoalRef("milky:1", 99), "pause")
    with pytest.raises(GoalConflict):
        svc.update("milky:ghost", GoalRef("milky:ghost", 1), "pause")


def test_phase_transitions(svc, tmp_store):
    svc.create("milky:1", "目标")
    g = svc.update("milky:1", GoalRef("milky:1", 1), "pause")
    assert g.phase == "paused" and g.revision == 2
    g = svc.update("milky:1", GoalRef("milky:1", 2), "resume")
    assert g.phase == "active" and g.revision == 3
    g = svc.update("milky:1", GoalRef("milky:1", 3), "complete")
    assert g.phase == "complete" and g.revision == 4


def test_blocked_requires_reason(svc, tmp_store):
    svc.create("milky:1", "目标")
    with pytest.raises(ValueError, match="阻塞原因"):
        svc.update("milky:1", GoalRef("milky:1", 1), "blocked", blocked_reason="   ")
    g = svc.update(
        "milky:1", GoalRef("milky:1", 1), "blocked", blocked_reason="等待审批"
    )
    assert g.phase == "blocked"
    assert g.blocked_reason == "等待审批"


def test_round_cap_auto_completes(svc, tmp_store):
    svc.create("milky:1", "目标", max_rounds=2)
    g = svc.update("milky:1", GoalRef("milky:1", 1), "advance_round")
    assert g.completed_rounds == 1 and g.phase == "active"
    g = svc.update("milky:1", GoalRef("milky:1", 2), "advance_round")
    assert g.completed_rounds == 2 and g.phase == "complete"

    # 终态不再推进轮次（无 revision 变化）
    g2 = svc.update("milky:1", GoalRef("milky:1", 3), "advance_round")
    assert g2.completed_rounds == 2 and g2.revision == 3


def test_edit_and_clear(svc, tmp_store):
    svc.create("milky:1", "旧目标")
    g = svc.update("milky:1", GoalRef("milky:1", 1), "edit", objective="新目标")
    assert g.objective == "新目标" and g.revision == 2

    with pytest.raises(ValueError, match="不能为空"):
        svc.update("milky:1", GoalRef("milky:1", 2), "edit", objective="  ")

    assert svc.clear("milky:1") is True
    assert svc.get("milky:1") is None
    assert svc.clear("milky:1") is False


def test_unknown_action_rejected(svc, tmp_store):
    svc.create("milky:1", "目标")
    with pytest.raises(ValueError, match="未知 goal action"):
        svc.update("milky:1", GoalRef("milky:1", 1), "fly")
