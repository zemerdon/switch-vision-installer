from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "switch_vision_installer" / "app"
sys.path.insert(0, str(APP))

CONFIG = (ROOT / "switch_vision_installer/config.yaml").read_text(encoding="utf-8")
CHANGELOG = (ROOT / "switch_vision_installer/CHANGELOG.md").read_text(encoding="utf-8")
JS = (ROOT / "switch_vision_installer/www/component-manager.js").read_text(encoding="utf-8")
WEB_MANAGER = (APP / "web_manager.py").read_text(encoding="utf-8")

assert 'version: "2.1.42"' in CONFIG
assert "## v2.1.42 — Per-component reinstall controls" in CHANGELOG
assert "component-reinstall" in JS
assert "component-external-reinstall" in JS
assert "api/reinstall-component" in JS
assert 'parsed.path == "/api/reinstall-component"' in WEB_MANAGER

import component_manager as manager

core_calls = []
manager._component_status = lambda spec: {
    "installed": True,
    "installed_version": "2.7.29",
    "dependency_ok": True,
}
manager._spec = lambda component_id: SimpleNamespace(
    component_id=component_id,
    label="Switch Vision Core",
    kind="core",
    min_core=None,
)
manager.installer_core.download_and_install = (
    lambda progress=None, *, force=False: (
        core_calls.append(force)
        or SimpleNamespace(
            __dict__={
                "ok": True,
                "version": "2.7.29",
                "installed": ["Custom component", "Dashboard frontend and visual assets"],
                "required_actions": ["Restart Home Assistant Core"],
            }
        )
    )
)
payload = manager.reinstall_component("core")
assert core_calls == [True]
assert payload["component_reinstall"] == "core"

manager._spec = lambda component_id: SimpleNamespace(
    component_id=component_id,
    label="Switch Vision Discovery",
    kind="addon",
    min_core=None,
)
manager._component_status = lambda spec: {
    "installed": True,
    "slug": "repo_switch_vision_discovery",
    "dependency_ok": True,
}
manager._set_repository_compatibility = lambda: None
manager._remote_version = lambda spec: "3.0.5"
manager.installer_core.addon_info = lambda slug: {
    "version": "3.0.5",
    "state": "started",
    "options": {"demo": False, "poll_interval": 30},
}
calls = []
manager.installer_core.supervisor_request = (
    lambda path, method="GET", payload=None: calls.append(("request", path, method, payload)) or {}
)
manager.installer_core.reload_addon_store = lambda: calls.append(("reload",))
manager.installer_core.supervisor_store_request = (
    lambda path, payload=None, progress=None: calls.append(("store", path, payload)) or {}
)
wait_results = iter([
    {"version": "3.0.5", "state": "stopped"},
    {"version": "3.0.5", "state": "started"},
])
manager.installer_core.wait_for_addon = lambda *args, **kwargs: next(wait_results)
manager.clear_cache = lambda: calls.append(("clear",))

payload = manager._addon_reinstall("discovery")
assert ("request", "/addons/repo_switch_vision_discovery/uninstall", "POST", {"remove_config": False}) in calls
assert ("store", "/store/addons/repo_switch_vision_discovery/install", {"background": False}) in calls
assert (
    "request",
    "/addons/repo_switch_vision_discovery/options",
    "POST",
    {"options": {"demo": False, "poll_interval": 30}},
) in calls
assert ("request", "/addons/repo_switch_vision_discovery/start", "POST", None) in calls
assert payload["settings_restored"] is True
assert payload["running_state_restored"] is True
assert payload["version"] == "3.0.5"

print("Installer v2.1.42 per-component reinstall controls: PASS")
