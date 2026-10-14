from pathlib import Path
import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "switch_vision_installer" / "app"
CONFIG = (ROOT / "switch_vision_installer/config.yaml").read_text(encoding="utf-8")
CHANGELOG = (ROOT / "switch_vision_installer/CHANGELOG.md").read_text(encoding="utf-8")

assert 'version: "2.1.52"' in CONFIG
assert "## v2.1.43 — Reliable serialized App Store refresh" in CHANGELOG

spec = importlib.util.spec_from_file_location("sv_installer_2143", APP / "installer.py")
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

calls = []
def request_ok(path, method="GET", payload=None, *, timeout=30.0):
    calls.append((path, method, timeout))
    return {"result": "ok"}

mod.supervisor_request = request_ok
mod.reload_addon_store()
assert calls == [("/store/reload", "POST", 180.0)]

calls.clear()
def request_fail(path, method="GET", payload=None, *, timeout=30.0):
    calls.append((path, method, timeout))
    raise RuntimeError("store refresh failed")

mod.supervisor_request = request_fail
try:
    mod.reload_addon_store()
except RuntimeError as exc:
    assert "App Store refresh failed" in str(exc)
else:
    raise AssertionError("Installer App Store refresh must fail closed")

assert calls == [("/store/reload", "POST", 180.0)]
print("Installer v2.1.43 serialized App Store refresh: PASS")
