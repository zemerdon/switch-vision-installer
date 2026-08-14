from __future__ import annotations

from pathlib import Path
import importlib.util
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "switch_vision_installer" / "app"

fake_installer = types.ModuleType("installer")
fake_installer.INSTALLER_VERSION = "2.1.14"
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

snmp = module._spec("snmp2mqtt")
assert snmp.repositories[0] == "switch-vision-snmp2mqtt"
assert "switch-vision-snmp2mqtt-addon" in snmp.repositories
assert snmp.config_path == "switch-vision-snmp2mqtt/config.yaml"

discovery = module._spec("discovery")
assert discovery.min_core == "2.1.5"

order = [spec.component_id for spec in module.COMPONENTS]
assert order == ["core", "discovery", "snmp2mqtt", "unifi2mqtt", "installer"]
print("component manager regression tests: PASS")

# The future canonical SNMP2MQTT name currently belongs to the engine repo.
# Resolver must reject it unless the expected Home Assistant app config exists.
module.clear_cache()
def raw_before_rename(repo, path):
    if repo == "switch-vision-snmp2mqtt":
        raise FileNotFoundError("engine repo has no HA app config")
    if repo == "switch-vision-snmp2mqtt-addon":
        return 'name: Switch Vision SNMP2MQTT\nversion: "0.9.7"\n'
    raise FileNotFoundError(repo)
module._raw_text = raw_before_rename
assert module.resolve_repository(snmp) == "switch-vision-snmp2mqtt-addon"

# After the rename, the canonical repo contains the HA app layout and wins.
module.clear_cache()
def raw_after_rename(repo, path):
    if repo == "switch-vision-snmp2mqtt":
        return 'name: Switch Vision SNMP2MQTT\nversion: "0.9.7"\n'
    raise FileNotFoundError(repo)
module._raw_text = raw_after_rename
assert module.resolve_repository(snmp) == "switch-vision-snmp2mqtt"

# Discovery dependency must block a direct update on old Core.
fake_installer.installed_version = lambda: "2.1.4"
module._remote_version = lambda spec: {"discovery":"2.1.7","core":"2.1.5","snmp2mqtt":"0.9.7","unifi2mqtt":"2.0.38","installer":"2.1.14"}.get(spec.component_id, "")
module.clear_cache()
row = module._component_status(discovery)
assert row["dependency_ok"] is False
assert "v2.1.5+" in row["dependency_note"]

print("repository rename/dependency regressions: PASS")
