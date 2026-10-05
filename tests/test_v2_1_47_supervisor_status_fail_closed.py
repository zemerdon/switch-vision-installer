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

print("Installer v2.1.47 Supervisor status fail-closed regression: PASS")
