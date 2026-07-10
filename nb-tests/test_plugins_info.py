"""Per-plugin import health + command tests — information & interactive."""

import pytest
from arclet.alconna import command_manager


@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_import_weibo():
    import hoshino.modules.information.weibo as m
    assert m.sv is not None
    assert len(m.sv.matchers) > 0

@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_import_bilireq():
    import hoshino.modules.information.bilireq as m
    assert m.sv is not None

@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_import_pushlive():
    import hoshino.modules.information.pushlive as m
    assert m.sv is not None

@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_import_resolve():
    import hoshino.modules.information.resolve as m
    assert m.sv is not None

@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_import_steam():
    import hoshino.modules.interactive.steam as m
    assert m.sv is not None

@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_import_chooseone():
    import hoshino.modules.interactive.chooseone as m
    assert m.sv is not None

@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_import_foods():
    import hoshino.modules.interactive.foods as m
    assert m.sv is not None

@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_import_qa():
    import hoshino.modules.interactive.QA as m
    assert m.sv is not None
    assert len(m.sv.matchers) > 0

@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_import_alisten():
    import hoshino.modules.interactive.alisten as m
    assert m.sv is not None

@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_alisten_cmd():
    cmd = command_manager.get_command("点歌")
    assert cmd is not None
    assert cmd.parse("点歌 晴天").matched

@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_import_qbitorrent():
    import hoshino.modules.interactive.qbitorrent as m
    assert m.sv is not None

@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_qbt_cmd():
    cmd = command_manager.get_command("添加种子")
    assert cmd is not None
    assert cmd.parse("添加种子 magnet:?xt=urn:btih:test").matched

@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_import_emojimix():
    import hoshino.modules.interactive.emojimix as m
    assert m.sv is not None
