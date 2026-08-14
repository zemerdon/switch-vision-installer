from __future__ import annotations

from pathlib import Path
import importlib.util
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "switch_vision_installer" / "app"

fake_installer = types.ModuleType("installer")
fake_installer.INSTALLER_VERSION = "2.1.19"
fake_installer.COMPONENT_DIR = Path("/tmp/no-component")
fake_installer.normalise_version = lambda value: str(value or "").strip().lstrip("v")
fake_installer.installed_version = lambda: "2.1.5"
fake_installer.load_options = lambda: {"allow_prerelease": False}
fake_installer.discovery_status = lambda: {"installed": True, "version": "2.1.7", "state": "started", "slug": "repo_discovery"}
fake_installer.snmp2mqtt_status = lambda: {"installed": True, "version": "0.9.7", "state": "started", "slug": "repo_snmp"}
fake_installer.unifi2mqtt_status = lambda: {"installed": False, "version": None, "state": "not_installed", "slug": "repo_unifi"}
fake_installer._find_addon = lambda *args, **kwargs: {"slug": "repo_installer"}
fake_installer.download_and_install = lambda progress=None: types.SimpleNamespace(__dict__={"ok": True, "version": "2.1.5", "installed": [], "unchanged": ["Core"], "warnings": [], "required_actions": []})
sys.modules["installer"] = fake_installer

fake_repo = types.ModuleType("repository_setup")
fake_repo.SNMP2MQTT_REPOSITORY = "legacy"
fake_repo.DISCOVERY_REPOSITORY = "discovery"
fake_repo.UNIFI2MQTT_REPOSITORY = "unifi"
sys.modules["repository_setup"] = fake_repo

spec = importlib.util.spec_from_file_location("component_manager", APP / "component_manager.py")
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules["component_manager"] = module
spec.loader.exec_module(module)

assert module.compare_versions("2.1.14", "2.1.13") > 0
assert module.compare_versions("2.1.7", "2.1.7") == 0
assert module.compare_versions("0.9.7", "0.10.0") < 0

core = module._spec("core")
assert core.repositories == ("switch-vision-releases",)

snmp = module._spec("snmp2mqtt")
assert snmp.repositories == ("switch-vision-snmp2mqtt-addon",)
assert snmp.config_path == "switch-vision-snmp2mqtt/config.yaml"

discovery = module._spec("discovery")
assert discovery.min_core == "2.1.5"

order = [spec.component_id for spec in module.COMPONENTS]
assert order == ["core", "discovery", "snmp2mqtt", "unifi2mqtt", "installer"]
print("component manager regression tests: PASS")

# The SNMP2MQTT Home Assistant app repository is permanent. The engine source
# repository must never be probed as an app repository candidate.
module.clear_cache()
raw_calls = []
def raw_app_repository(repo, path):
    raw_calls.append((repo, path))
    if repo == "switch-vision-snmp2mqtt-addon":
        return 'name: Switch Vision SNMP2MQTT\nversion: "0.9.7"\n'
    raise FileNotFoundError(repo)
module._raw_text = raw_app_repository
assert module.resolve_repository(snmp) == "switch-vision-snmp2mqtt-addon"
assert all(repo != "switch-vision-snmp2mqtt" for repo, _ in raw_calls)

# Discovery dependency must block a direct update on old Core.
fake_installer.installed_version = lambda: "2.1.4"
module._remote_version = lambda spec: {"discovery":"2.1.7","core":"2.1.5","snmp2mqtt":"0.9.7","unifi2mqtt":"2.0.38","installer":"2.1.19"}.get(spec.component_id, "")
module.clear_cache()
row = module._component_status(discovery)
assert row["dependency_ok"] is False
assert row["status"] == "dependency_mismatch"
assert "v2.1.5+" in row["dependency_note"]
assert "Installed Core: v2.1.4" in row["dependency_note"]

# A current Discovery with an unmet dependency still needs attention. If the
# published Core cannot satisfy that dependency, Update All must be blocked.
module._remote_version = lambda spec: {"discovery":"2.1.7","core":"2.1.4","snmp2mqtt":"0.9.7","unifi2mqtt":"2.0.38","installer":"2.1.19"}.get(spec.component_id, "")
module.clear_cache()
snapshot = module.component_status()
discovery_row = next(item for item in snapshot["components"] if item["id"] == "discovery")
assert discovery_row["status"] == "dependency_mismatch"
assert snapshot["update_all_blocked"] is True
assert "Publish/update Core first" in snapshot["update_all_blocked_reason"]

# Once a compatible Core is published, Update All is allowed and upgrades Core
# first; Discovery remains marked Needs attention only until that Core update runs.
module._remote_version = lambda spec: {"discovery":"2.1.7","core":"2.1.5","snmp2mqtt":"0.9.7","unifi2mqtt":"2.0.38","installer":"2.1.19"}.get(spec.component_id, "")
module.clear_cache()
snapshot = module.component_status()
assert snapshot["update_all_blocked"] is False
assert snapshot["updates_available"] >= 1

print("repository identity/dependency regressions: PASS")

# Installer self-update safety.
fake_installer.INSTALLER_VERSION = "2.1.18"
fake_installer.installed_version = lambda: "2.1.5"
module._remote_version = lambda spec: {
    "discovery": "2.1.7",
    "core": "2.1.5",
    "snmp2mqtt": "0.9.7",
    "unifi2mqtt": "2.0.38",
    "installer": "2.1.19",
}.get(spec.component_id, "")
module.clear_cache()
snapshot = module.component_status()
for component_row in snapshot["components"]:
    assert "legacy_repository" not in component_row
installer_row = next(item for item in snapshot["components"] if item["id"] == "installer")
assert installer_row["update_available"] is True
assert installer_row["external_update"] is True
assert snapshot["installer_update_external"] is True
assert "installer" not in snapshot["update_order"]
assert snapshot["actions_available"] == 0

result = module.update_component("installer")
assert result["ok"] is True
assert result["self_update_external"] is True
assert result["installed"] == []
assert any("Home Assistant Settings" in item for item in result["required_actions"])

print("installer self-update safety regression: PASS")
