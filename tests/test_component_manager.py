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
fake_installer.installed_version = lambda: "2.3.10"
fake_installer.load_options = lambda: {"allow_prerelease": False}
fake_installer.discovery_status = lambda: {"installed": True, "version": "2.1.34", "state": "started", "slug": "repo_discovery"}
fake_installer.snmp2mqtt_status = lambda: {"installed": True, "version": "0.9.15", "state": "started", "slug": "repo_snmp"}
fake_installer.unifi2mqtt_status = lambda: {"installed": False, "version": None, "state": "not_installed", "slug": "repo_unifi"}
fake_installer._find_addon = lambda *args, **kwargs: {"slug": "repo_installer"}
fake_installer.download_and_install = lambda progress=None: types.SimpleNamespace(__dict__={"ok": True, "version": "2.4.8", "installed": [], "unchanged": ["Core"], "warnings": [], "required_actions": []})
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
assert discovery.min_core == "2.3.10"

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
        return 'name: Switch Vision SNMP2MQTT\nversion: "0.9.15"\n'
    raise FileNotFoundError(repo)
module._raw_text = raw_app_repository
assert module.resolve_repository(snmp) == "switch-vision-snmp2mqtt-addon"
assert all(repo != "switch-vision-snmp2mqtt" for repo, _ in raw_calls)

# Discovery dependency must block a direct update on Core older than the
# Calibration Profile API contract introduced in Core v2.3.10.
fake_installer.installed_version = lambda: "2.3.9"
module._remote_version = lambda spec: {"discovery":"2.1.34","core":"2.3.10","snmp2mqtt":"0.9.15","unifi2mqtt":"2.0.47","installer":"2.1.26"}.get(spec.component_id, "")
module.clear_cache()
row = module._component_status(discovery)
assert row["dependency_ok"] is False
assert row["status"] == "dependency_mismatch"
assert "v2.3.10+" in row["dependency_note"]
assert "Installed Core: v2.3.9" in row["dependency_note"]

# A current Discovery with an unmet dependency still needs attention. If the
# published Core cannot satisfy that dependency, Update All must be blocked.
module._remote_version = lambda spec: {"discovery":"2.1.34","core":"2.3.9","snmp2mqtt":"0.9.15","unifi2mqtt":"2.0.47","installer":"2.1.26"}.get(spec.component_id, "")
module.clear_cache()
snapshot = module.component_status()
discovery_row = next(item for item in snapshot["components"] if item["id"] == "discovery")
assert discovery_row["status"] == "dependency_mismatch"
assert snapshot["update_all_blocked"] is True
assert "Publish/update Core first" in snapshot["update_all_blocked_reason"]

# Once a compatible Core is published, Update All is allowed and upgrades Core
# first; Discovery remains marked Needs attention only until that Core update runs.
module._remote_version = lambda spec: {"discovery":"2.1.34","core":"2.3.10","snmp2mqtt":"0.9.15","unifi2mqtt":"2.0.47","installer":"2.1.26"}.get(spec.component_id, "")
module.clear_cache()
snapshot = module.component_status()
assert snapshot["update_all_blocked"] is False
assert snapshot["updates_available"] >= 1

print("repository identity/dependency regressions: PASS")

# Installer self-update safety remains independent of the Discovery dependency.
fake_installer.INSTALLER_VERSION = "2.1.25"
fake_installer.installed_version = lambda: "2.3.10"
module._remote_version = lambda spec: {
    "discovery": "2.1.34",
    "core": "2.3.10",
    "snmp2mqtt": "0.9.15",
    "unifi2mqtt": "2.0.47",
    "installer": "2.1.26",
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

# Installer v2.1.35 authoritative public release metadata is independent of the
# existing main/config-driven latest-version contract used for update decisions.
module.clear_cache()
release_calls = []
module.resolve_repository = lambda spec: spec.repositories[0]
def github_release(url):
    release_calls.append(url)
    assert url == (
        "https://api.github.com/repos/zemerdon/"
        "switch-vision-releases/releases/latest"
    )
    return {
        "tag_name": "v9.8.7",
        "published_at": "2026-09-06T12:34:56Z",
        "html_url": "https://github.com/zemerdon/switch-vision-releases/releases/tag/v9.8.7",
    }
module._github_request = github_release
public = module._public_release_metadata(core)
assert public["public_release_version"] == "9.8.7"
assert public["public_release_published_at"] == "2026-09-06T12:34:56Z"
assert public["public_release_url"].endswith("/releases/tag/v9.8.7")
assert public["release_metadata_error"] is None
assert module._public_release_metadata(core) == public
assert len(release_calls) == 1

module.clear_cache()
def unavailable_release(_url):
    raise OSError("offline")
module._github_request = unavailable_release
unavailable = module._public_release_metadata(core)
assert unavailable["public_release_version"] is None
assert unavailable["public_release_published_at"] is None
assert unavailable["public_release_url"] is None
assert unavailable["release_metadata_error"].startswith("OSError:")

# The enrichment pass must iterate the live COMPONENTS catalog; no second
# component list is permitted.
release_components = []
base_snapshot = module.component_status()
def base_status():
    return {
        **base_snapshot,
        "components": [dict(row) for row in base_snapshot["components"]],
    }
module.component_status = base_status
def public_release_stub(spec):
    release_components.append(spec.component_id)
    return {
        "public_release_version": "9.9.9",
        "public_release_published_at": "2026-09-06T12:34:56Z",
        "public_release_url": f"https://example.invalid/{spec.component_id}",
        "release_metadata_error": None,
    }
module._public_release_metadata = public_release_stub
enriched = module.component_status_with_releases()
assert release_components == order
assert [row["id"] for row in enriched["components"]] == order
assert all(row["public_release_version"] == "9.9.9" for row in enriched["components"])
assert all(
    row["public_release_published_at"] == "2026-09-06T12:34:56Z"
    for row in enriched["components"]
)
assert [
    row["latest_version"] for row in enriched["components"]
] == [
    row["latest_version"] for row in base_snapshot["components"]
]

ui = (ROOT / "switch_vision_installer" / "www" / "component-manager.js").read_text(
    encoding="utf-8"
)
assert "public_release_version" in ui
assert "public_release_published_at" in ui
assert "new Intl.DateTimeFormat" in ui
assert "Release time unavailable" in ui
assert "lastModified" not in ui

manager = (APP / "web_manager.py").read_text(encoding="utf-8")
assert "component_status_with_releases()" in manager
print("Installer v2.1.35 public release presentation regression: PASS")
