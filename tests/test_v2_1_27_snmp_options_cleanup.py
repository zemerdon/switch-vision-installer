#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import importlib.util
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "switch_vision_installer" / "app" / "repository_setup.py"

state = {
    "options": {
        "homeassistant": {
            "discovery": False,
            "prefix": "custom-prefix",
        },
        "mqtt": {
            "host": "broker.example",
            "port": 1883,
            "username": "switchvision",
            "password": "keep-this-secret",
        },
        "targets_path": "/config/app_configs/switch_vision_snmp2mqtt/targets.yaml",
        "use_switch_vision_generated_yaml": True,
        "switch_vision_generated_yaml_path": "/share/switch_vision/generated-snmp2mqtt.yaml",
        "imported_targets_path": "/config/app_configs/switch_vision_snmp2mqtt/imported/generated-snmp2mqtt.yaml",
        "backup_existing_config": False,
    }
}
original = repr(state["options"])

fake = types.ModuleType("installer")
fake.find_snmp2mqtt_slug = (
    lambda include_store=False: "repo_switch_vision_snmp2mqtt"
)

def unexpected(*args, **kwargs):
    raise AssertionError(
        "Installer must not read or rewrite SNMP2MQTT options during repository setup"
    )

fake.addon_info = unexpected
fake.supervisor_request = unexpected
fake.reload_addon_store = lambda: None
fake.find_unifi2mqtt_slug = (
    lambda include_store=False: "repo_switch_vision_unifi2mqtt"
)
sys.modules["installer"] = fake

spec = importlib.util.spec_from_file_location(
    "sv_repository_setup_v2130_test", MODULE
)
if spec is None or spec.loader is None:
    raise SystemExit("Unable to import repository_setup.py")
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

result = mod.ensure_snmp2mqtt_repository()
assert result["available"] is True
assert result["slug"] == "repo_switch_vision_snmp2mqtt"
assert repr(state["options"]) == original
assert state["options"]["homeassistant"]["discovery"] is False
assert state["options"]["homeassistant"]["prefix"] == "custom-prefix"
assert state["options"]["mqtt"]["password"] == "keep-this-secret"

source = MODULE.read_text(encoding="utf-8")
assert "_sanitize_snmp2mqtt_saved_options" not in source
assert 'cleaned.pop("homeassistant", None)' not in source
assert "/addons/{slug}/options" not in source

print(
    "Switch Vision Installer v2.1.30 SNMP2MQTT Home Assistant option preservation: PASS"
)
