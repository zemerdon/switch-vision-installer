#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import importlib.util
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "switch_vision_installer" / "app" / "installer.py"

spec = importlib.util.spec_from_file_location("sv_installer_backup_test", INSTALLER)
if spec is None or spec.loader is None:
    raise SystemExit("Unable to import installer.py")
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

assert mod.INSTALLER_VERSION == "2.1.8"

source = INSTALLER.read_text(encoding="utf-8")
create_section = source[source.index("def create_backup("):source.index("def create_manual_backup(")]
restore_section = source[source.index("def restore_backup("):source.index("def collect_custom_assets(")]

assert 'copy_backup(DISCOVERY_DIR' not in create_section
assert 'copy_backup(SNMP2MQTT_DIR' not in create_section
assert 'unifi2mqtt-options.json' in create_section
assert 'addons/switch_vision_snmp2mqtt' not in restore_section
assert 'unifi2mqtt-options.json' in restore_section
assert 'mappings.append((release_snmp2mqtt, SNMP2MQTT_DIR, "SNMP2MQTT add-on"))' not in source

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
    unifi_options = {"controller_url": "https://192.0.2.2", "api_key": "fixture-api-key"}

    mod.get_discovery_options = lambda: discovery_options
    mod.get_snmp2mqtt_options = lambda: snmp_options
    mod.get_unifi2mqtt_options = lambda: unifi_options
    mod.installed_version = lambda: "2.1.2"
    mod.prune_backups = lambda: {"ok": True}

    backup = mod.create_backup(force=True)
    assert backup is not None and backup.is_dir()
    assert not (backup / "addons").exists(), "repository app source was archived"
    assert json.loads((backup / "discovery-options.json").read_text()) == discovery_options
    assert json.loads((backup / "snmp2mqtt-options.json").read_text()) == snmp_options
    assert json.loads((backup / "unifi2mqtt-options.json").read_text()) == unifi_options

    meta = json.loads((backup / "backup.json").read_text())
    assert meta["discovery_configuration_saved"] is True
    assert meta["snmp2mqtt_configuration_saved"] is True
    assert meta["unifi2mqtt_configuration_saved"] is True

    mod.validate_backup(backup)

    captured = {}
    mod.set_discovery_options = lambda options, slug=None: captured.__setitem__("discovery", options)
    mod.set_snmp2mqtt_options = lambda options: captured.__setitem__("snmp", options)
    mod.set_unifi2mqtt_options = lambda options: captured.__setitem__("unifi", options)

    result = mod.restore_backup(backup.name)
    assert result["ok"] is True
    assert captured["discovery"] == discovery_options
    assert captured["snmp"] == snmp_options
    assert captured["unifi"] == unifi_options
    assert "SNMP2MQTT add-on" not in result["restored"]
    assert "UniFi2MQTT configuration" in result["restored"]

print("Switch Vision Installer repository backup/restore regression: PASS")
