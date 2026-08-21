#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
replacements = {
    'INSTALLER_VERSION == "2.1.24"': 'INSTALLER_VERSION == "2.1.25"',
    'version: "2.1.24"': 'version: "2.1.25"',
}
changed = []
for path in sorted((ROOT / "tests").glob("test_*.py")):
    text = path.read_text(encoding="utf-8")
    updated = text
    for old, new in replacements.items():
        updated = updated.replace(old, new)
    if updated == text:
        continue
    path.write_text(updated, encoding="utf-8", newline="\n")
    changed.append(path.name)
if not changed:
    raise SystemExit("No current Installer version test fixtures found to advance")
print("Updated Installer version fixtures:", ", ".join(changed))
