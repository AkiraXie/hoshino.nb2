"""每个插件 1-2 条命令的基础响应测试"""
import pytest
from conftest import init_nonebot, get_service


def _service_has_command(sv_name: str, cmd_name: str) -> bool:
    sv = get_service(sv_name)
    if not sv:
        return False
    for m in sv.matchers:
        if cmd_name in str(m):
            return True
    return False


# ── tools ──
def test_b64_commands(init_nonebot):
    assert _service_has_command("b64", "b64加密")
    assert _service_has_command("b64", "b64")

def test_nbnhhsh_loaded(init_nonebot):
    assert get_service("nbnhhsh") is not None

# ── entertainment ──
def test_bihua_commands(init_nonebot):
    assert get_service("bihua") is not None

def test_dice_loaded(init_nonebot):
    assert get_service("dice") is not None

def test_coser_loaded(init_nonebot):
    assert get_service("coser") is not None

# ── develop ──
def test_echoandsay_commands(init_nonebot):
    assert _service_has_command("echoandsay", "echo")
    assert _service_has_command("echoandsay", "say")

# ── interactive ──
def test_chooseone_commands(init_nonebot):
    assert _service_has_command("chooseone", "选择")

def test_steam_loaded(init_nonebot):
    assert get_service("steam") is not None

def test_qa_commands(init_nonebot):
    assert _service_has_command("QA", "有人问")
    assert _service_has_command("QA", "我问")

def test_alisten_loaded(init_nonebot):
    assert get_service("alisten") is not None

def test_qbitorrent_loaded(init_nonebot):
    assert get_service("qbitorrent") is not None

def test_foods_loaded(init_nonebot):
    assert get_service("foods") is not None

def test_emojimix_loaded(init_nonebot):
    assert get_service("emojimix") is not None

# ── information ──
def test_weibo_commands(init_nonebot):
    sv = get_service("weibo")
    assert sv is not None
    assert len(sv.matchers) > 0, "weibo has no matchers"

def test_bilireq_commands(init_nonebot):
    assert _service_has_command("bilireq", "添加动态")

def test_pushlive_loaded(init_nonebot):
    assert get_service("pushlive") is not None

def test_resolve_loaded(init_nonebot):
    assert get_service("resolve") is not None

# ── help ──
def test_help_commands(init_nonebot):
    assert _service_has_command("help", "help")
