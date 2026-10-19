from __future__ import annotations

from pathlib import Path
import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "switch_vision_installer" / "app"

spec = importlib.util.spec_from_file_location("sv_installer_2147", APP / "installer.py")
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def unavailable(path, method="GET", payload=None, *, timeout=30.0):
    raise RuntimeError(f"Supervisor unavailable for {path}")


mod.supervisor_request = unavailable
try:
    mod._find_addon(lambda _slug, _name: True, include_store=False, fail_on_unavailable=True)
except RuntimeError as exc:
    assert str(exc) == "Home Assistant Supervisor app status is unavailable."
else:
    raise AssertionError("Supervisor lookup failure was mistaken for not-installed state")


def empty_success(path, method="GET", payload=None, *, timeout=30.0):
    assert path == "/addons"
    return {"data": {"addons": []}}


mod.supervisor_request = empty_success
assert (
    mod._find_addon(
        lambda _slug, _name: True,
        include_store=False,
        fail_on_unavailable=True,
    )
    is None
)


mod.supervisor_request = unavailable
for func in (
    mod.find_discovery_slug,
    mod.discovery_status,
    mod.find_snmp2mqtt_slug,
    mod.snmp2mqtt_status,
    mod.find_unifi2mqtt_slug,
    mod.unifi2mqtt_status,
):
    try:
        func()
    except RuntimeError as exc:
        assert "Supervisor app status is unavailable" in str(exc), (func.__name__, exc)
    else:
        raise AssertionError(f"{func.__name__} did not fail closed")

# Source-bound positive, absent and failed-info contracts for each status family.
import tempfile

with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    mod.GENERATED_SNMP2MQTT_YAML = root / "generated.yaml"
    mod.GENERATED_SNMP2MQTT_YAML.write_text("fixture", encoding="utf-8")

    for component, path_name, func, key in (
        ("discovery", "DISCOVERY_DIR", mod.discovery_status, "files_present"),
        ("snmp2mqtt", "SNMP2MQTT_DIR", mod.snmp2mqtt_status, "present"),
        ("unifi2mqtt", "UNIFI2MQTT_DIR", mod.unifi2mqtt_status, "present"),
    ):
        directory = root / component
        setattr(mod, path_name, directory)
        slug = "repo_switch_vision_" + component
        installed_row = {"slug": slug, "version": "1.0.0", "state": "stopped"}
        store_row = {"slug": slug, "version_latest": "2.0.0"}
        info = {
            "version": "2.0.0", "state": "started",
            "ingress_entry": "/internal", "webui": "/ui",
        }

        for situation in ("installed", "info_error", "store", "absent_local"):
            calls = []
            def request(path, method="GET", payload=None, *, timeout=30.0):
                calls.append(path)
                if path == "/addons":
                    return {"data": {"addons": [installed_row] if situation in ("installed", "info_error") else []}}
                if path == f"/addons/{slug}/info":
                    if situation == "info_error":
                        raise RuntimeError("Supervisor detail unavailable")
                    return {"data": dict(info)}
                if path == "/store":
                    return {"data": {"addons": [store_row] if situation == "store" else []}}
                raise AssertionError(f"unexpected Supervisor operation: {path}")

            mod.supervisor_request = request
            if situation == "absent_local":
                directory.mkdir()
            result = func()

            assert result[key] is (situation == "absent_local")
            assert result["slug"] == (slug if situation != "absent_local" else None)
            assert result["available"] is True
            assert result["installed"] is (situation in ("installed", "info_error"))
            if situation == "installed":
                assert result["version"] == "2.0.0"
                assert result["state"] == "started"
            elif situation == "info_error":
                assert result["version"] == "1.0.0"
                assert result["state"] == "stopped"
            elif situation == "store":
                assert result["version"] == (None if component == "discovery" else "2.0.0")
                assert result["state"] == "not_installed"
            else:
                assert result["version"] is None
                assert result["state"] == "not_installed"

            if component == "snmp2mqtt":
                assert result["generated_yaml"] is True
                if situation in ("installed", "info_error"):
                    assert "ingress_entry" not in result and "webui" not in result
                else:
                    assert result["ingress_entry"] is None and result["webui"] is None
            elif situation == "installed":
                assert result["ingress_entry"] == "/internal" and result["webui"] == "/ui"
            elif situation == "info_error":
                assert result["ingress_entry"] is None and result["webui"] is None
            else:
                assert result["ingress_entry"] is None and result["webui"] is None

            # Exactly one installed-list query per path, never a redundant
            # second /addons lookup; installed state never needs /store.
            assert calls == (
                ["/addons", f"/addons/{slug}/info"]
                if situation in ("installed", "info_error")
                else ["/addons", "/store"]
            ), (component, situation, calls)

            if situation == "absent_local":
                directory.rmdir()

assert mod._matches_switch_vision_app(
    "discovery", "repo_switch_vision_discovery", ""
)
assert not mod._matches_switch_vision_app(
    "discovery", "repo_switch_vision_discovery_old", ""
)
assert mod._matches_switch_vision_app(
    "unifi2mqtt", "unrelated", "switch vision unifi2mqtt"
)
assert mod._matches_switch_vision_app(
    "snmp2mqtt", "legacy-switch-vision-snmp2mqtt", ""
)
print("Installer shared status response and Supervisor query contracts: PASS")
print("Installer v2.1.47 Supervisor status fail-closed regression: PASS")
