#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import importlib.util
import json
import stat
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "switch_vision_installer" / "app" / "installer.py"
WEB = ROOT / "switch_vision_installer" / "app" / "web.py"
WEB_MANAGER = ROOT / "switch_vision_installer" / "app" / "web_manager.py"
COMPONENT_MANAGER = ROOT / "switch_vision_installer" / "app" / "component_manager.py"

spec = importlib.util.spec_from_file_location("sv_installer_v219_test", INSTALLER)
if spec is None or spec.loader is None:
    raise SystemExit("Unable to import installer.py")
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

assert mod.INSTALLER_VERSION == "2.1.23"

assert hasattr(mod, "stat")

release_payload = {
    "tag_name": "2.2.2",
    "name": "Switch Vision v2.2.2",
    "prerelease": False,
    "assets": [
        {
            "name": "switch-vision-2.2.2.zip",
            "size": 123,
            "browser_download_url": "https://example.invalid/release.zip",
            "digest": "sha256:" + "a" * 64,
        },
        {
            "name": "switch-vision-2.2.2-source.zip",
            "size": 999,
            "browser_download_url": "https://example.invalid/source.zip",
        },
    ],
}
mod.request_json = lambda url: release_payload
mod.load_options = lambda: {
    "release_api_url": "https://example.invalid/releases/latest",
    "allow_custom_release_source": True,
    "release_asset_pattern": "switch-vision-*.zip",
    "allow_prerelease": False,
}
release = mod.latest_release()
assert release["asset_name"] == "switch-vision-2.2.2.zip"
assert release["asset_digest"] == "a" * 64

bad_payload = dict(release_payload)
bad_payload["assets"] = [
    {
        "name": "switch-vision-random.zip",
        "size": 1000,
        "browser_download_url": "https://example.invalid/random.zip",
        "digest": "sha256:" + "b" * 64,
    }
]
mod.request_json = lambda url: bad_payload
try:
    mod.latest_release()
except RuntimeError as exc:
    assert "must contain exactly one installable asset" in str(exc)
else:
    raise AssertionError("mismatched release asset was accepted")

with tempfile.TemporaryDirectory() as td:
    assert mod.expected_release_checksum(
        {"asset_digest": "c" * 64, "checksum_asset_url": None}, Path(td)
    ) == "c" * 64
    try:
        mod.expected_release_checksum(
            {"asset_digest": None, "checksum_asset_url": None}, Path(td)
        )
    except RuntimeError as exc:
        assert "trusted SHA-256" in str(exc)
    else:
        raise AssertionError("unsigned release was accepted")

with tempfile.TemporaryDirectory() as td:
    base = Path(td)
    mod.COMPONENT_DIR = base / "custom_components" / "switch_vision"
    mod.DISCOVERY_DIR = base / "discovery"
    mod.DISCOVERY_DIR.mkdir(parents=True)
    (mod.DISCOVERY_DIR / "config.yaml").write_text(
        'version: "9.9.9"\n', encoding="utf-8"
    )
    assert mod.installed_version() is None
    mod.COMPONENT_DIR.mkdir(parents=True)
    (mod.COMPONENT_DIR / "manifest.json").write_text(
        json.dumps({"version": "2.2.2"}), encoding="utf-8"
    )
    assert mod.installed_version() == "2.2.2"

calls = []
def flaky(path, method="GET", payload=None):
    calls.append((path, method))
    if len(calls) < 3:
        raise RuntimeError("Supervisor API POST /store/addons/x/update failed with HTTP 500")
    return {"ok": True}
mod.supervisor_request = flaky
mod.time.sleep = lambda seconds: None
assert mod.supervisor_store_request("/store/addons/x/update", attempts=4)["ok"] is True
assert len(calls) == 3

calls.clear()
def forbidden(path, method="GET", payload=None):
    calls.append((path, method))
    raise RuntimeError("Supervisor API POST /store/addons/x/update failed with HTTP 403")
mod.supervisor_request = forbidden
try:
    mod.supervisor_store_request("/store/addons/x/update", attempts=4)
except RuntimeError:
    pass
else:
    raise AssertionError("non-transient store error was retried/accepted")
assert len(calls) == 1

with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "backup"
    secret = root / "discovery-options.json"
    secret.parent.mkdir(parents=True)
    secret.write_text('{"snmp_community":"secret"}\n', encoding="utf-8")
    nested = root / "nested"
    nested.mkdir()
    mod.secure_backup_permissions(root)
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(nested.stat().st_mode) == 0o700
    assert stat.S_IMODE(secret.stat().st_mode) == 0o600

installer_source = INSTALLER.read_text(encoding="utf-8")
assert "Compatibility install endpoint also failed" in installer_source
assert "Backup permission verification failed" in installer_source
assert "Backup contains unsupported symbolic link" in installer_source
assert "options could not be captured safely" in installer_source
assert "asset_name_lower = expected_name.lower()" in installer_source

# Transactional restore rolls files/settings back if a later restore step fails.
with tempfile.TemporaryDirectory() as td:
    base = Path(td)
    mod.BACKUP_DIR = base / "backups"
    mod.LEGACY_BACKUP_DIR = base / "legacy-backups"
    mod.WORK_DIR = base / "work"
    mod.HA_CONFIG = base / "homeassistant"
    mod.COMPONENT_DIR = mod.HA_CONFIG / "custom_components" / "switch_vision"
    mod.FRONTEND_DIR = mod.HA_CONFIG / "www" / "switch-vision"
    mod.GENERATED_SNMP2MQTT_YAML = (
        base / "share" / "switch_vision" / "generated-snmp2mqtt.yaml"
    )

    mod.COMPONENT_DIR.mkdir(parents=True)
    (mod.COMPONENT_DIR / "state.txt").write_text("current\n", encoding="utf-8")
    mod.FRONTEND_DIR.mkdir(parents=True)
    (mod.FRONTEND_DIR / "state.txt").write_text("current\n", encoding="utf-8")
    mod.GENERATED_SNMP2MQTT_YAML.parent.mkdir(parents=True)
    mod.GENERATED_SNMP2MQTT_YAML.write_text("current: true\n", encoding="utf-8")
    calibration = mod.HA_CONFIG / ".storage" / "switch_vision_calibrations"
    calibration.parent.mkdir(parents=True)
    calibration.write_text('{"current":true}\n', encoding="utf-8")

    current_discovery = {"marker": "current-discovery"}
    current_snmp = {"marker": "current-snmp"}
    current_unifi = {"marker": "current-unifi"}
    mod.get_discovery_options = lambda: dict(current_discovery)
    mod.get_snmp2mqtt_options = lambda: dict(current_snmp)
    mod.get_unifi2mqtt_options = lambda: dict(current_unifi)

    captured = {}
    mod.set_discovery_options = lambda options, slug=None: captured.__setitem__(
        "discovery", dict(options)
    )
    def set_snmp(options):
        if options.get("marker") == "restore-snmp":
            raise RuntimeError("fixture restore failure")
        captured["snmp"] = dict(options)
    mod.set_snmp2mqtt_options = set_snmp
    mod.set_unifi2mqtt_options = lambda options: captured.__setitem__(
        "unifi", dict(options)
    )

    selected = mod.BACKUP_DIR / "selected"
    (selected / "custom_components" / "switch_vision").mkdir(parents=True)
    (selected / "custom_components" / "switch_vision" / "state.txt").write_text(
        "restored\n", encoding="utf-8"
    )
    (selected / "www" / "switch-vision").mkdir(parents=True)
    (selected / "www" / "switch-vision" / "state.txt").write_text(
        "restored\n", encoding="utf-8"
    )
    (selected / "discovery-options.json").write_text(
        json.dumps({"marker": "restore-discovery"}), encoding="utf-8"
    )
    (selected / "snmp2mqtt-options.json").write_text(
        json.dumps({"marker": "restore-snmp"}), encoding="utf-8"
    )
    manifest = {
        "schema": 1,
        "installer_version": "fixture",
        "files": mod.backup_file_hashes(selected),
    }
    (selected / "backup-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    try:
        mod.restore_backup("selected")
    except RuntimeError as exc:
        assert "temporary safety snapshot" in str(exc)
    else:
        raise AssertionError("fixture restore failure unexpectedly succeeded")

    assert (mod.COMPONENT_DIR / "state.txt").read_text() == "current\n"
    assert (mod.FRONTEND_DIR / "state.txt").read_text() == "current\n"
    assert mod.GENERATED_SNMP2MQTT_YAML.read_text() == "current: true\n"
    assert calibration.read_text() == '{"current":true}\n'
    assert captured["discovery"] == current_discovery
    assert captured["snmp"] == current_snmp
    assert captured["unifi"] == current_unifi

installer_source = INSTALLER.read_text(encoding="utf-8")
web_source = WEB.read_text(encoding="utf-8")
manager_source = WEB_MANAGER.read_text(encoding="utf-8")
component_source = COMPONENT_MANAGER.read_text(encoding="utf-8")

assert 'expected_name = f"switch-vision-{version}.zip"' in installer_source
assert "Release identity mismatch" in installer_source
assert "def _capture_restore_snapshot" in installer_source
assert "def _rollback_restore_snapshot" in installer_source
assert "transactional_restore" in installer_source
assert "target.chmod(0o700)" in installer_source
assert "def start_job" in web_source
assert "Reserve the mutation slot before returning HTTP 202" in web_source
assert 'run_locked("delete backup"' in web_source
assert 'run_locked("install discovery"' in web_source
assert "legacy_web.start_job" in manager_source
assert 'legacy_web.operation["active"]' not in manager_source
assert "supervisor_store_request(" in component_source
assert "expected_version = installer_core.normalise_version(_remote_version(spec))" in component_source

print("Switch Vision Installer v2.1.20 hardening regression: PASS")
