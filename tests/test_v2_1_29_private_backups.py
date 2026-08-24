#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import importlib.util
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "switch_vision_installer" / "app" / "installer.py"

spec = importlib.util.spec_from_file_location("sv_installer_private_backup_test", INSTALLER)
if spec is None or spec.loader is None:
    raise SystemExit("Unable to import installer.py")
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

assert mod.BACKUP_DIR == Path("/data/switch-vision-backups")
assert mod.SHARED_BACKUP_DIR == Path("/share/switch-vision-backups")
assert mod.LEGACY_BACKUP_DIR == Path("/share/switch_vision/installer_backups")
assert mod._backup_roots() == [mod.BACKUP_DIR]

with tempfile.TemporaryDirectory() as td:
    base = Path(td)
    mod.BACKUP_DIR = base / "data" / "switch-vision-backups"
    mod.SHARED_BACKUP_DIR = base / "share" / "switch-vision-backups"
    mod.LEGACY_BACKUP_DIR = base / "share" / "switch_vision" / "installer_backups"

    private = mod.BACKUP_DIR / "switch-vision-private"
    shared = mod.SHARED_BACKUP_DIR / "switch-vision-shared"
    legacy = mod.LEGACY_BACKUP_DIR / "switch-vision-legacy"
    private.mkdir(parents=True)
    shared.mkdir(parents=True)
    legacy.mkdir(parents=True)

    assert mod._backup_roots() == [mod.BACKUP_DIR]
    assert [item["name"] for item in mod.list_backups()] == ["switch-vision-private"]
    assert mod._safe_backup_path(private.name) == private.resolve()

    for name in (shared.name, legacy.name):
        try:
            mod._safe_backup_path(name)
        except RuntimeError as exc:
            assert "Backup not found" in str(exc)
        else:
            raise AssertionError(f"shared backup unexpectedly trusted: {name}")

print("Switch Vision Installer private backup trust regression: PASS")
