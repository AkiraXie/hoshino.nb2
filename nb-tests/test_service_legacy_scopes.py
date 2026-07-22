"""Backward compatibility for pre-platform service state files."""

import json


def test_service_loads_legacy_groups_as_ob11_scopes(tmp_path, monkeypatch):
    import hoshino.core.service as service_module

    monkeypatch.setattr(service_module, "_service_dir", tmp_path)
    (tmp_path / "legacy_service.json").write_text(
        json.dumps(
            {
                "name": "legacy_service",
                "enable_group": [10001],
                "disable_group": [10002],
            }
        ),
        encoding="utf8",
    )

    service = service_module.Service("legacy_service", enable_on_default=False)

    assert service.enable_scope == {"ob11:10001"}
    assert service.disable_scope == {"ob11:10002"}
    assert service.check_enabled("ob11:10001")
    assert not service.check_enabled("ob11:10002")


def test_explicit_scopes_override_conflicting_legacy_groups():
    from hoshino.core.service import _load_service_scopes

    enable_scope, disable_scope = _load_service_scopes(
        {
            "enable_scope": ["ob11:10002"],
            "disable_scope": ["ob11:10001"],
            "enable_group": [10001],
            "disable_group": [10002],
        }
    )

    assert enable_scope == {"ob11:10002"}
    assert disable_scope == {"ob11:10001"}


def test_telegram_service_scope_survives_reload(tmp_path, monkeypatch):
    import hoshino.core.service as service_module

    service_name = "telegram_scope_persistence_test"
    scope_key = "telegram:-100123456"
    monkeypatch.setattr(service_module, "_service_dir", tmp_path)
    try:
        service = service_module.Service(service_name, enable_on_default=False)
        service.set_enable(scope_key)
        service_module._loaded_services.pop(service_name)

        reloaded = service_module.Service(service_name, enable_on_default=False)

        assert reloaded.check_enabled(scope_key)
        assert not (tmp_path / f"{service_name}.json.tmp").exists()
    finally:
        service_module._loaded_services.pop(service_name, None)
