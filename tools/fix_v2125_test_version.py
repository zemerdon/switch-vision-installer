#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
old = 'INSTALLER_VERSION == "2.1.24"'
new = 'INSTALLER_VERSION == "2.1.25"'
changed = []
for path in sorted((ROOT / "tests").glob("test_*.py")):
    text = path.read_text(encoding="utf-8")
    if old not in text:
        continue
    updated = text.replace(old, new)
    path.write_text(updated, encoding="utf-8", newline="\n")
    changed.append(path.name)
if not changed:
    raise SystemExit("No current Installer version test fixtures found to advance")
print("Updated Installer version fixtures:", ", ".join(changed))
