#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import stat
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "switch_vision_installer" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import backup_manager  # noqa: E402
import installer  # noqa: E402


installer_source = (APP / "installer.py").read_text(encoding="utf-8")
backup_source = (APP / "backup_manager.py").read_text(encoding="utf-8")

assert "import backup_manager as _backup_manager" in installer_source
assert "def _backup_runtime()" in installer_source
assert "class BackupRuntime" in backup_source
for name in (
    "backup_policy",
    "save_backup_policy",
    "create_backup",
    "restore_backup_contents",
    "capture_restore_snapshot",
    "rollback_restore_snapshot",
    "restore_backup",
):
    assert f"def {name}(" in backup_source

# Security- and rollback-critical implementation belongs to the extracted
# domain, while installer.py retains only the compatibility surface.
for marker in (
    "Backup contains unsupported symbolic link",
    "Backup permission verification failed",
    "options could not be captured safely",
    "temporary safety snapshot",
):
    assert marker in backup_source
    assert marker not in installer_source

assert installer.copy_backup.__module__ == "installer"
assert installer.restore_backup.__module__ == "installer"

with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "backup"
    secret = root / "secret.json"
    secret.parent.mkdir(parents=True)
    secret.write_text('{"secret":"fixture"}\n', encoding="utf-8")
    nested = root / "nested"
    nested.mkdir()

    backup_manager.secure_backup_permissions(root)
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(nested.stat().st_mode) == 0o700
    assert stat.S_IMODE(secret.stat().st_mode) == 0o600

print("Switch Vision Installer backup-domain modularity regression: PASS")
