from pathlib import Path
import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "switch_vision_installer" / "app"
CONFIG = (ROOT / "switch_vision_installer/config.yaml").read_text(encoding="utf-8")
CHANGELOG = (ROOT / "switch_vision_installer/CHANGELOG.md").read_text(encoding="utf-8")
WEB = (ROOT / "switch_vision_installer/www/installer.js").read_text(encoding="utf-8")
MANAGER = (APP / "component_manager.py").read_text(encoding="utf-8")
WEB_MANAGER = (APP / "web_manager.py").read_text(encoding="utf-8")

assert 'version: "2.1.41"' in CONFIG
assert "## v2.1.41 — Reliable component update checks" in CHANGELOG
assert "api/check-components" in WEB
assert "def refresh_component_sources()" in MANAGER
assert 'parsed.path == "/api/check-components"' in WEB_MANAGER

spec = importlib.util.spec_from_file_location("sv_installer_2141", APP / "installer.py")
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

calls = []
def request_ok(path, method="GET", payload=None):
    calls.append((path, method))
    if path == "/addons/reload":
        raise RuntimeError("legacy endpoint unavailable")
    return {"result": "ok"}

mod.supervisor_request = request_ok
mod.reload_addon_store()
assert calls == [("/addons/reload", "POST"), ("/store/reload", "POST")]

calls.clear()
def request_store_fail(path, method="GET", payload=None):
    calls.append((path, method))
    if path == "/store/reload":
        raise RuntimeError("store pull failed")
    return {"result": "ok"}

mod.supervisor_request = request_store_fail
try:
    mod.reload_addon_store()
except RuntimeError as exc:
    assert "App Store refresh failed" in str(exc)
else:
    raise AssertionError("store reload failure must not be masked by /addons/reload success")

print("Installer v2.1.41 reliable update refresh regression: PASS")
