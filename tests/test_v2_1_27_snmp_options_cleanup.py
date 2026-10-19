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

# Both MQTT app repositories must use the same effect ordering while keeping
# distinct public entrypoints and every previously supported failure outcome.
import time as builtin_time

for product, repo, lookup_name, ensure_name in (
    ("SNMP2MQTT", mod.SNMP2MQTT_REPOSITORY, "find_snmp2mqtt_slug", "ensure_snmp2mqtt_repository"),
    ("UniFi2MQTT", mod.UNIFI2MQTT_REPOSITORY, "find_unifi2mqtt_slug", "ensure_unifi2mqtt_repository"),
):
    ensure = getattr(mod, ensure_name)
    for scenario in ("available", "new", "existing", "race", "failed", "unavailable"):
        events = []
        repositories = []
        if scenario == "existing":
            repositories.append({"source": repo + ".git"})
        state_available = [scenario == "available"]

        def find_slug(*, include_store=False):
            assert include_store is True
            events.append(("lookup",))
            if not state_available[0]:
                raise LookupError("App missing in store")
            return "fixture_" + product

        def repository_list():
            events.append(("repositories",))
            return list(repositories)

        def post(path, *, method="GET", payload=None):
            assert (path, method, payload) == (
                "/store/repositories", "POST", {"repository": repo}
            )
            events.append(("register",))
            if scenario == "race":
                repositories.append({"url": repo})
                raise RuntimeError("Concurrent registration")
            if scenario == "failed":
                raise RuntimeError("Store rejected registration")
            repositories.append({"url": repo})

        def reload_store():
            events.append(("refresh",))
            if scenario != "unavailable":
                state_available[0] = True

        progress = lambda message, value: events.append(("progress", message, value))
        setattr(fake, lookup_name, find_slug)
        fake.supervisor_request = post
        fake.reload_addon_store = reload_store
        mod._repository_list = repository_list

        if scenario == "unavailable":
            # Deterministic monotonic clock: prove the 120s failure branch
            # without sleeping or changing the host's real clock.
            tick = [0]
            def monotonic():
                tick[0] += 121
                return tick[0]
            mod.time = types.SimpleNamespace(monotonic=monotonic, sleep=unexpected)

        if scenario in ("failed", "unavailable"):
            try:
                ensure(progress)
            except RuntimeError as exc:
                if scenario == "failed":
                    assert str(exc) == "Store rejected registration"
                else:
                    assert str(exc) == (
                        f"Switch Vision {product} repository is registered, but the app "
                        "did not become available in the Home Assistant store within 120 seconds."
                    )
            else:
                raise AssertionError(f"{product} {scenario} must fail safely")
            if scenario == "failed":
                assert ("refresh",) not in events
        else:
            result = ensure(progress)
            assert result == {
                "added": scenario == "new",
                "available": True,
                "slug": "fixture_" + product,
                "repository": repo,
            }, (product, scenario, result)
            assert events[-1] == ("lookup",), (product, scenario, events)
            if scenario == "available":
                assert events == [("lookup",)]
            else:
                assert ("refresh",) in events
                assert events.index(("refresh",)) < len(events) - 1

        registrations = [e for e in events if e == ("register",)]
        assert len(registrations) == (0 if scenario in ("available", "existing") else 1)
        if scenario == "race":
            assert len([e for e in events if e == ("repositories",)]) == 2
        if scenario != "available":
            assert ("progress", "Refreshing the Home Assistant App store…", 4) in events or scenario == "failed"
        mod.time = builtin_time

# The separate Discovery repository path intentionally retains its own
# repository-slug and exact store identity verification.
assert "repository_slug = str(repository_entry.get" in source or (
    "repository_slug = str(repository_entry.get"
    in MODULE.read_text(encoding="utf-8")
)
assert repr(state["options"]) == original

print("Installer shared MQTT-app repository lifecycle: both app variants and all failure paths PASS")
print(
    "Switch Vision Installer v2.1.30 SNMP2MQTT Home Assistant option preservation: PASS"
)
