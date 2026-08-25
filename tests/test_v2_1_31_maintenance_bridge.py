#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import json
import stat
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "switch_vision_installer" / "app"
sys.path.insert(0, str(APP))

import installer  # noqa: E402
import web_manager  # noqa: E402


with tempfile.TemporaryDirectory() as td:
    base = Path(td)
    installer.OPTIONS_PATH = base / "options.json"
    installer.BACKUP_POLICY_PATH = base / "backup-policy.json"
    installer.BACKUP_DIR = base / "switch-vision-backups"
    installer.OPTIONS_PATH.write_text(
        json.dumps({"backup_retention": 20}) + "\n", encoding="utf-8"
    )

    # A pre-v2.1.31 installation had automatic retention permanently enabled.
    # Legacy values above the new user-facing limit are safely clamped to 10.
    assert installer.backup_policy() == {
        "automatic_retention": True,
        "retention_count": 10,
    }

    saved = installer.save_backup_policy(False, 3)
    assert saved == {"automatic_retention": False, "retention_count": 3}
    assert installer.BACKUP_POLICY_PATH.is_file()
    assert stat.S_IMODE(installer.BACKUP_POLICY_PATH.stat().st_mode) == 0o600

    installer.BACKUP_DIR.mkdir(parents=True)
    for index in range(5):
        (installer.BACKUP_DIR / f"switch-vision-20260825-00000{index}").mkdir()

    disabled = installer.prune_backups()
    assert disabled["automatic_retention"] is False
    assert disabled["retention_skipped"] is True
    assert disabled["removed"] == []
    assert len(list(installer.BACKUP_DIR.iterdir())) == 5

    manual = installer.apply_backup_retention()
    assert manual["retention"] == 3
    assert len(manual["removed"]) == 2
    assert len(list(installer.BACKUP_DIR.iterdir())) == 3

    for automatic, count in (("yes", 3), (True, 0), (True, 11), (True, True)):
        try:
            installer.save_backup_policy(automatic, count)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid backup policy accepted: {automatic!r}, {count!r}")

# The Supervisor-mediated bridge returns only approved metadata. Private paths
# and arbitrary stored option material must never cross into Maintenance.
clean = web_manager._sanitized_backup(
    {
        "name": "switch-vision-test",
        "path": "/data/switch-vision-backups/switch-vision-test",
        "created_at": "2026-08-25T00:00:00+00:00",
        "contents": ["Custom component", "Discovery configuration"],
        "secret": "must-not-leak",
    }
)
assert clean["name"] == "switch-vision-test"
assert "path" not in clean
assert "secret" not in clean

result = web_manager._sanitized_operation_result(
    {
        "ok": True,
        "backup": "switch-vision-test",
        "backup_path": "/data/switch-vision-backups/switch-vision-test",
        "required_actions": ["Restart Home Assistant Core"],
        "private": {"password": "no"},
    }
)
assert result == {
    "ok": True,
    "backup": "switch-vision-test",
    "required_actions": ["Restart Home Assistant Core"],
}

request = web_manager._parse_maintenance_request(
    json.dumps(
        {
            "schema": web_manager.MAINTENANCE_SCHEMA,
            "request_id": "maintenance-1234",
            "action": "status",
        }
    ).encode("utf-8")
)
assert request["action"] == "status"

for bad in (
    {"schema": "wrong", "request_id": "maintenance-1234", "action": "status"},
    {"schema": web_manager.MAINTENANCE_SCHEMA, "request_id": "bad", "action": "status"},
    {"schema": web_manager.MAINTENANCE_SCHEMA, "request_id": "maintenance-1234", "action": "shell"},
):
    try:
        web_manager._parse_maintenance_request(json.dumps(bad).encode("utf-8"))
    except ValueError:
        pass
    else:
        raise AssertionError(f"invalid maintenance request accepted: {bad}")

config = (ROOT / "switch_vision_installer" / "config.yaml").read_text(encoding="utf-8")
assert "stdin: true" in config
assert "backup_retention: int(1,10)" in config

print("Switch Vision Installer v2.1.31 Maintenance backup bridge regression: PASS")
