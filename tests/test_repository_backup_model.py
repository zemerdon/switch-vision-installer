#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import importlib.util
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "switch_vision_installer" / "app" / "installer.py"
INSTALLER_JS = ROOT / "switch_vision_installer" / "www" / "installer.js"

spec = importlib.util.spec_from_file_location("sv_installer_backup_test", INSTALLER)
if spec is None or spec.loader is None:
    raise SystemExit("Unable to import installer.py")
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

assert mod.INSTALLER_VERSION == "2.1.14"

with tempfile.TemporaryDirectory() as td:
    digest_base = Path(td)
    release_component = digest_base / "release"
    installed_component = digest_base / "installed"
    release_component.mkdir()
    installed_component.mkdir()

    (release_component / "__init__.py").write_text("# fixture\n", encoding="utf-8")
    (installed_component / "__init__.py").write_text("# fixture\n", encoding="utf-8")

    cache = installed_component / "__pycache__"
    cache.mkdir()
    (cache / "__init__.cpython-314.pyc").write_bytes(b"runtime cache")
    (installed_component / "stray.pyc").write_bytes(b"runtime cache")

    assert mod.tree_digest(release_component) == mod.tree_digest(installed_component)

    (installed_component / "__init__.py").write_text("# changed\n", encoding="utf-8")
    assert mod.tree_digest(release_component) != mod.tree_digest(installed_component)


blank_switch = {
    "switch_name": "",
    "switch_host": "",
    "sensor_prefix": "",
    "snmp_community": "readonly",
    "walk_mode": "targeted",
    "switch_model": "auto",
    "card_header_title": "",
}
real_switch = {
    "switch_name": "SW1",
    "switch_host": "192.0.2.1",
}
assert mod.configured_switch_count({"switches": [blank_switch]}) == 0
assert mod.configured_switch_count({"switches": [blank_switch, real_switch]}) == 1
assert mod.configured_switch_count({"devices": [{"name": "legacy"}]}) == 1


source = INSTALLER.read_text(encoding="utf-8")
web_source = INSTALLER_JS.read_text(encoding="utf-8")
web_py_source = (
    ROOT / "switch_vision_installer" / "app" / "web.py"
).read_text(encoding="utf-8")

assert "Wait about one minute, then click Reinstall to retry Discovery." in web_py_source
assert "Components that are already current will be left unchanged." in web_py_source
assert "check Home Assistant " in web_py_source
assert "Supervisor logs for details." in web_py_source
assert "Original error: " in web_py_source
create_section = source[source.index("def create_backup("):source.index("def create_manual_backup(")]
restore_section = source[source.index("def restore_backup("):source.index("def collect_custom_assets(")]

assert 'copy_backup(DISCOVERY_DIR' not in create_section
assert 'copy_backup(SNMP2MQTT_DIR' not in create_section
assert 'unifi2mqtt-options.json' in create_section
assert 'unifi2mqtt_options_configured' in create_section
assert 'addons/switch_vision_snmp2mqtt' not in restore_section
assert 'unifi2mqtt_options_configured' in restore_section
assert 'Restart Switch Vision Discovery' in restore_section
assert 'mappings.append((release_snmp2mqtt, SNMP2MQTT_DIR, "SNMP2MQTT add-on"))' not in source

assert "skipped=(r.skipped||[])" in web_source
assert "<b>Skipped safely:</b>" in web_source
assert "unifi2mqtt_configuration_skipped_unconfigured" in web_source
assert "Not saved (not configured)" in web_source

configured_unifi = {
    "controller_url": "https://192.0.2.2",
    "site_id": "default",
    "api_key": "fixture-api-key",
    "verify_ssl": "false",
    "poll_interval": "30",
    "mqtt_host": "core-mosquitto",
    "mqtt_port": "1883",
    "mqtt_username": "",
    "mqtt_password": "",
    "mqtt_topic_prefix": "switch_vision/unifi",
    "mqtt_discovery_prefix": "homeassistant",
}
unconfigured_unifi = {
    "controller_url": "https://192.168.1.1",
    "site_id": None,
    "api_key": None,
    "verify_ssl": "false",
    "poll_interval": "30",
    "mqtt_host": "core-mosquitto",
    "mqtt_port": "1883",
    "mqtt_username": "",
    "mqtt_password": "",
    "mqtt_topic_prefix": "switch_vision/unifi",
    "mqtt_discovery_prefix": "homeassistant",
}

assert mod.unifi2mqtt_options_configured(configured_unifi) is True
assert mod.unifi2mqtt_options_configured(unconfigured_unifi) is False
assert mod.unifi2mqtt_options_configured(None) is False

with tempfile.TemporaryDirectory() as td:
    base = Path(td)
    mod.BACKUP_DIR = base / "backups"
    mod.LEGACY_BACKUP_DIR = base / "legacy-backups"
    mod.HA_CONFIG = base / "homeassistant"
    mod.COMPONENT_DIR = mod.HA_CONFIG / "custom_components" / "switch_vision"
    mod.FRONTEND_DIR = mod.HA_CONFIG / "www" / "switch-vision"
    mod.GENERATED_SNMP2MQTT_YAML = base / "share" / "switch_vision" / "generated-snmp2mqtt.yaml"

    mod.COMPONENT_DIR.mkdir(parents=True)
    (mod.COMPONENT_DIR / "__init__.py").write_text("# fixture\n", encoding="utf-8")
    mod.FRONTEND_DIR.mkdir(parents=True)
    (mod.FRONTEND_DIR / "fixture.js").write_text("// fixture\n", encoding="utf-8")
    mod.GENERATED_SNMP2MQTT_YAML.parent.mkdir(parents=True)
    mod.GENERATED_SNMP2MQTT_YAML.write_text("switches: []\n", encoding="utf-8")
    storage = mod.HA_CONFIG / ".storage" / "switch_vision_calibrations"
    storage.parent.mkdir(parents=True)
    storage.write_text('{"fixture": true}\n', encoding="utf-8")

    discovery_options = {"switches": [{"switch_name": "SW1", "switch_host": "192.0.2.1"}]}
    snmp_options = {"mqtt_host": "core-mosquitto", "mqtt_password": "fixture-secret"}

    mod.get_discovery_options = lambda: discovery_options
    mod.get_snmp2mqtt_options = lambda: snmp_options
    mod.get_unifi2mqtt_options = lambda: configured_unifi
    mod.installed_version = lambda: "2.1.2"
    mod.prune_backups = lambda: {"ok": True}

    backup = mod.create_backup(force=True)
    assert backup is not None and backup.is_dir()
    assert not (backup / "addons").exists(), "repository app source was archived"
    assert json.loads((backup / "discovery-options.json").read_text()) == discovery_options
    assert json.loads((backup / "snmp2mqtt-options.json").read_text()) == snmp_options
    assert json.loads((backup / "unifi2mqtt-options.json").read_text()) == configured_unifi

    meta = json.loads((backup / "backup.json").read_text())
    assert meta["discovery_configuration_saved"] is True
    assert meta["snmp2mqtt_configuration_saved"] is True
    assert meta["unifi2mqtt_configuration_saved"] is True
    assert meta["unifi2mqtt_configuration_skipped_unconfigured"] is False

    mod.validate_backup(backup)

    captured = {}
    mod.set_discovery_options = lambda options, slug=None: captured.__setitem__("discovery", options)
    mod.set_snmp2mqtt_options = lambda options: captured.__setitem__("snmp", options)
    mod.set_unifi2mqtt_options = lambda options: captured.__setitem__("unifi", options)

    result = mod.restore_backup(backup.name)
    assert result["ok"] is True
    assert captured["discovery"] == discovery_options
    assert captured["snmp"] == snmp_options
    assert captured["unifi"] == configured_unifi
    assert "SNMP2MQTT add-on" not in result["restored"]
    assert "UniFi2MQTT configuration" in result["restored"]
    assert result["skipped"] == []
    assert result["required_actions"] == [
        "Restart Home Assistant Core",
        "Restart Switch Vision Discovery",
        "Restart Switch Vision SNMP2MQTT",
        "Restart Switch Vision UniFi2MQTT if it is running",
        "Hard-refresh the browser",
    ]

    (backup / "unifi2mqtt-options.json").write_text(
        json.dumps(unconfigured_unifi, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = json.loads((backup / "backup-manifest.json").read_text(encoding="utf-8"))
    manifest["files"] = mod.backup_file_hashes(backup)
    (backup / "backup-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    captured.pop("unifi", None)

    legacy_result = mod.restore_backup(backup.name)
    assert legacy_result["ok"] is True
    assert "unifi" not in captured, "unconfigured UniFi defaults were POSTed to Supervisor"
    assert "UniFi2MQTT configuration" not in legacy_result["restored"]
    assert legacy_result["skipped"] == [
        "UniFi2MQTT configuration (backup contains unconfigured defaults)"
    ]
    assert "Generated SNMP2MQTT YAML" in legacy_result["restored"]
    assert "Calibration storage" in legacy_result["restored"]
    assert legacy_result["required_actions"] == [
        "Restart Home Assistant Core",
        "Restart Switch Vision Discovery",
        "Restart Switch Vision SNMP2MQTT",
        "Hard-refresh the browser",
    ]

    mod.get_unifi2mqtt_options = lambda: unconfigured_unifi
    unconfigured_backup = mod.create_backup(force=True)
    assert unconfigured_backup is not None
    assert not (unconfigured_backup / "unifi2mqtt-options.json").exists()
    unconfigured_meta = json.loads((unconfigured_backup / "backup.json").read_text())
    assert unconfigured_meta["unifi2mqtt_configuration_saved"] is False
    assert unconfigured_meta["unifi2mqtt_configuration_skipped_unconfigured"] is True
    assert "UniFi2MQTT configuration" not in mod.backup_contents(unconfigured_backup)
    mod.validate_backup(unconfigured_backup)

print("Switch Vision Installer repository backup/restore regression: PASS")
print("Switch Vision Installer unconfigured UniFi restore regression: PASS")
print("Switch Vision Installer restore guidance/UI regression: PASS")
