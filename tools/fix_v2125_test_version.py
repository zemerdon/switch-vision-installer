#!/usr/bin/env python3
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "tests" / "test_repository_backup_model.py"
text = path.read_text(encoding="utf-8")
old = 'assert mod.INSTALLER_VERSION == "2.1.24"'
new = 'assert mod.INSTALLER_VERSION == "2.1.25"'
if old not in text:
    raise SystemExit("repository backup test version marker missing")
path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")
print("Updated repository backup version fixture for 2.1.25")
