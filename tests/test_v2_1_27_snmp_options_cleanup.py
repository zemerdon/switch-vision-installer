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
        "homeassistant": "2026.7.1",
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
posts: list[tuple[str, str, dict]] = []
progress_messages: list[str] = []

fake = types.ModuleType("installer")
fake.find_snmp2mqtt_slug = lambda include_store=False: "repo_switch_vision_snmp2mqtt"
fake.addon_info = lambda slug: {"slug": slug, "options": dict(state["options"])}

def supervisor_request(path, method="GET", payload=None):
    if path.endswith("/options") and method == "POST":
        assert isinstance(payload, dict)
        cleaned = payload.get("options")
        assert isinstance(cleaned, dict)
        state["options"] = dict(cleaned)
        posts.append((path, method, payload))
        return {"result": "ok"}
    if path == "/store/repositories":
        return {"data": {"repositories": []}}
    raise AssertionError(f"unexpected Supervisor request: {method} {path}")

fake.supervisor_request = supervisor_request
fake.reload_addon_store = lambda: None
fake.find_unifi2mqtt_slug = lambda include_store=False: "repo_switch_vision_unifi2mqtt"
sys.modules["installer"] = fake

spec = importlib.util.spec_from_file_location("sv_repository_setup_v2127_test", MODULE)
if spec is None or spec.loader is None:
    raise SystemExit("Unable to import repository_setup.py")
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

progress = lambda message, percent: progress_messages.append(str(message))
assert mod._sanitize_snmp2mqtt_saved_options(progress) is True
assert len(posts) == 1
assert "homeassistant" not in state["options"]
assert state["options"]["mqtt"]["password"] == "keep-this-secret"
assert state["options"]["mqtt"]["host"] == "broker.example"
assert state["options"]["targets_path"].endswith("/targets.yaml")
assert state["options"]["use_switch_vision_generated_yaml"] is True
assert state["options"]["backup_existing_config"] is False
assert any("obsolete SNMP2MQTT" in message for message in progress_messages)

# The migration is idempotent: once the stray key is gone, no second write is
# made and all legitimate options remain untouched.
posts.clear()
assert mod._sanitize_snmp2mqtt_saved_options(progress) is False
assert posts == []
assert state["options"]["mqtt"]["password"] == "keep-this-secret"

source = MODULE.read_text(encoding="utf-8")
assert "_sanitize_snmp2mqtt_saved_options(progress)" in source
assert 'cleaned.pop("homeassistant", None)' in source
assert 'payload={"options": cleaned}' in source

print("Switch Vision Installer v2.1.27 SNMP2MQTT option cleanup: PASS")
