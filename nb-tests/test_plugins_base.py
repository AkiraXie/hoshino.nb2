"""Per-plugin import health + Alconna parse checks — base/develop/tools/entertainment."""

import pytest
from arclet.alconna import command_manager


@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_import_black():
    import hoshino.base.black as m
    assert m

@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_import_help():
    import hoshino.base.help as m
    assert m.sv is not None

@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_help_cmd_parses():
    cmd = command_manager.get_command("help")
    assert cmd is not None
    assert cmd.parse("help").matched

@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_import_ls():
    import hoshino.base.ls as m
    assert m

@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_import_zai():
    import hoshino.base.zai as m
    assert m

@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_import_cookies():
    import hoshino.base.cookies as m
    assert m

@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_import_broadcast():
    import hoshino.base.broadcast as m
    assert m

@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_import_service_manage():
    import hoshino.base.service_manage as m
    assert m

@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_lssv_cmd():
    cmd = command_manager.get_command("lssv")
    assert cmd is not None
    assert cmd.parse("lssv").matched

@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_enable_cmd():
    cmd = command_manager.get_command("enable")
    assert cmd is not None
    assert cmd.parse("enable dice").matched

@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_disable_cmd():
    cmd = command_manager.get_command("disable")
    assert cmd is not None
    assert cmd.parse("disable dice").matched

@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_import_echoandsay():
    import hoshino.modules.develop.echoandsay as m
    assert m.sv is not None

@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_import_server_info():
    import hoshino.modules.develop.server_info as m
    assert m

@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_import_healthchecker():
    import hoshino.modules.develop.healthchecker as m
    assert m

@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_import_b64():
    import hoshino.modules.tools.b64 as m
    assert m.sv is not None

@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_b64_encrypt_parses():
    cmd = command_manager.get_command("b64加密")
    assert cmd is not None
    assert cmd.parse("b64加密 hello").matched

@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_import_nbnhhsh():
    import hoshino.modules.tools.nbnhhsh as m
    assert m.sv is not None

@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_import_dice():
    import hoshino.modules.entertainment.dice as m
    assert m.sv is not None

@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_import_bihua():
    import hoshino.modules.entertainment.bihua as m
    assert m.sv is not None

@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_import_coser():
    import hoshino.modules.entertainment.coser as m
    assert m.sv is not None
