"""Structured Service configuration：config_type 的加载/默认生成/类型强转/保存校验整体行为。"""

import json
from dataclasses import dataclass

import pytest


@dataclass(frozen=True, slots=True)
class ExampleSettings:
    enabled: bool = True
    limit: int = 10
    interval: float = 1.5
    name: str | None = None


def test_typed_service_config_roundtrip(tmp_path, monkeypatch):
    """Service(config_type=...) 整体行为：默认文件生成、类型强转读取、保存校验与写回。"""
    import hoshino.core.service as service_module

    service_dir = tmp_path / "service"
    config_dir = tmp_path / "service_config"
    monkeypatch.setattr(service_module, "_service_dir", service_dir)
    monkeypatch.setattr(service_module, "_service_config_dir", config_dir)

    # 首次创建：默认配置文件落盘，get_config 返回类型化默认值
    service = service_module.Service("typed_roundtrip_test", config_type=ExampleSettings)
    config_file = config_dir / "typed_roundtrip_test.json"
    assert config_file.exists()
    assert json.loads(config_file.read_text(encoding="utf8")) == {
        "enabled": True,
        "limit": 10,
        "interval": 1.5,
        "name": None,
    }
    assert service.get_config() == ExampleSettings()

    # 已有配置文件：字符串值按字段类型强转
    service_module._loaded_services.pop("typed_roundtrip_test", None)
    (config_dir / "typed_roundtrip_test.json").write_text(
        json.dumps({"enabled": False, "limit": "42", "interval": "2.5", "name": "custom"}),
        encoding="utf8",
    )
    service = service_module.Service("typed_roundtrip_test", config_type=ExampleSettings)
    assert service.get_config() == ExampleSettings(
        enabled=False, limit=42, interval=2.5, name="custom"
    )

    # save_config：非法值被 TypeAdapter 拒绝；合法值写回后重读一致
    with pytest.raises(ValueError):
        service.save_config({"enabled": False, "limit": "nope"})
    service.save_config({"enabled": False, "limit": 99, "name": "saved"})
    raw = json.loads(config_file.read_text(encoding="utf8"))
    assert raw["limit"] == 99
    assert raw["name"] == "saved"
    assert service.get_config() == ExampleSettings(enabled=False, limit=99, name="saved")

    service_module._loaded_services.pop("typed_roundtrip_test", None)
