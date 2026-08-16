"""Structured Service configuration behavior."""

import json
from dataclasses import dataclass

import pytest


@dataclass(frozen=True, slots=True)
class ExampleSettings:
    enabled: bool = True
    limit: int = 10
    interval: float = 1.5
    name: str | None = None


def test_typed_service_config_generates_default_file(tmp_path, monkeypatch):
    import hoshino.core.service as service_module

    service_name = "typed_config_default_test"
    monkeypatch.setattr(service_module, "_service_dir", tmp_path / "service")
    monkeypatch.setattr(service_module, "_service_config_dir", tmp_path / "service_config")
    try:
        service = service_module.Service(service_name, config_type=ExampleSettings)

        config_file = tmp_path / "service_config" / f"{service_name}.json"
        assert config_file.exists()
        assert json.loads(config_file.read_text(encoding="utf8")) == {
            "enabled": True,
            "limit": 10,
            "interval": 1.5,
            "name": None,
        }
        assert service.get_config() == ExampleSettings()
    finally:
        service_module._loaded_services.pop(service_name, None)


def test_typed_service_config_returns_declared_type(tmp_path, monkeypatch):
    import hoshino.core.service as service_module

    service_name = "typed_config_existing_test"
    service_dir = tmp_path / "service"
    config_dir = tmp_path / "service_config"
    config_dir.mkdir()
    (config_dir / f"{service_name}.json").write_text(
        json.dumps(
            {
                "enabled": False,
                "limit": "42",
                "interval": "2.5",
                "name": "custom",
            }
        ),
        encoding="utf8",
    )
    monkeypatch.setattr(service_module, "_service_dir", service_dir)
    monkeypatch.setattr(service_module, "_service_config_dir", config_dir)
    try:
        service = service_module.Service(service_name, config_type=ExampleSettings)

        config = service.get_config()
        assert isinstance(config, ExampleSettings)
        assert config == ExampleSettings(
            enabled=False,
            limit=42,
            interval=2.5,
            name="custom",
        )
    finally:
        service_module._loaded_services.pop(service_name, None)


def test_save_config_writes_validated_json(tmp_path, monkeypatch):
    import hoshino.core.service as service_module

    service_name = "save_config_test"
    service_dir = tmp_path / "service"
    config_dir = tmp_path / "service_config"
    monkeypatch.setattr(service_module, "_service_dir", service_dir)
    monkeypatch.setattr(service_module, "_service_config_dir", config_dir)
    try:
        service = service_module.Service(service_name, config_type=ExampleSettings)
        config_file = config_dir / f"{service_name}.json"

        # 非法 dict（limit 传非数字字符串）应被 TypeAdapter 拒绝
        with pytest.raises(ValueError):
            service.save_config({"enabled": False, "limit": "nope"})

        # 合法 dict 写回后，重新读取应得到相同对象
        service.save_config({"enabled": False, "limit": 99, "name": "saved"})
        raw = json.loads(config_file.read_text(encoding="utf8"))
        assert raw["limit"] == 99
        assert raw["name"] == "saved"
        assert service.get_config() == ExampleSettings(enabled=False, limit=99, name="saved")
    finally:
        service_module._loaded_services.pop(service_name, None)
