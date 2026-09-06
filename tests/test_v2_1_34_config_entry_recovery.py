#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "switch_vision_installer" / "app"
sys.path.insert(0, str(APP))

import installer  # noqa: E402
import web  # noqa: E402


def use_component_tree(base: Path) -> None:
    installer.COMPONENT_DIR = base / "custom_components" / "switch_vision"
    installer.COMPONENT_DIR.mkdir(parents=True, exist_ok=True)


with tempfile.TemporaryDirectory() as td:
    use_component_tree(Path(td))

    calls: list[tuple[str, str, object]] = []

    def existing(path: str, method: str = "GET", payload=None):
        calls.append((path, method, payload))
        if path == "/core/api/config/config_entries/entry?domain=switch_vision":
            return [{"domain": "switch_vision", "entry_id": "existing-entry", "state": "loaded"}]
        raise AssertionError(path)

    installer.supervisor_request = existing
    result = installer.ensure_switch_vision_config_entry()
    assert result["present"] is True
    assert result["created"] is False
    assert result["restart_required"] is False
    assert result["entry_id"] == "existing-entry"
    assert len(calls) == 1

with tempfile.TemporaryDirectory() as td:
    use_component_tree(Path(td))
    created = {"value": False}
    calls = []

    def missing_then_create(path: str, method: str = "GET", payload=None):
        calls.append((path, method, payload))
        if path == "/core/api/config/config_entries/entry?domain=switch_vision":
            if created["value"]:
                return [{"domain": "switch_vision", "entry_id": "created-entry", "state": "loaded"}]
            return []
        if path == "/core/api/config/config_entries/flow" and method == "POST":
            assert payload == {"handler": "switch_vision"}
            return {
                "type": "form",
                "flow_id": "flow-1",
                "handler": "switch_vision",
                "step_id": "user",
                "data_schema": [],
            }
        if path == "/core/api/config/config_entries/flow/flow-1" and method == "POST":
            assert payload == {}
            created["value"] = True
            return {"type": "create_entry", "title": "Switch Vision"}
        raise AssertionError((path, method, payload))

    installer.supervisor_request = missing_then_create
    result = installer.ensure_switch_vision_config_entry()
    assert result["present"] is True
    assert result["created"] is True
    assert result["restart_required"] is False
    assert result["entry_id"] == "created-entry"

with tempfile.TemporaryDirectory() as td:
    use_component_tree(Path(td))

    def handler_unavailable(path: str, method: str = "GET", payload=None):
        if path == "/core/api/config/config_entries/entry?domain=switch_vision":
            return []
        if path == "/core/api/config/config_entries/flow":
            raise RuntimeError(
                "Supervisor API POST /core/api/config/config_entries/flow failed "
                "with HTTP 404: Invalid handler specified"
            )
        raise AssertionError(path)

    installer.supervisor_request = handler_unavailable
    result = installer.ensure_switch_vision_config_entry()
    assert result["present"] is False
    assert result["created"] is False
    assert result["restart_required"] is True

restart_calls: list[str] = []
web.supervisor_request = lambda path, method="POST": restart_calls.append(path) or {"ok": True}
sequence = iter(
    [
        {"present": False, "created": False, "restart_required": True},
        {"present": True, "created": True, "restart_required": False, "entry_id": "after-restart"},
    ]
)
web.installer_core.ensure_switch_vision_config_entry = lambda: next(sequence)
web.time.sleep = lambda _seconds: None
restart_result = web.request_core_restart_async()
assert restart_calls == ["/core/restart"]
assert restart_result["ok"] is True
assert restart_result["core_restarted"] is True
assert restart_result["config_entry"]["present"] is True
assert restart_result["config_entry"]["entry_id"] == "after-restart"

config = (ROOT / "switch_vision_installer" / "config.yaml").read_text(encoding="utf-8")
assert "homeassistant_api: true" in config

print("Switch Vision Installer v2.1.34 config-entry recovery regression: PASS")
