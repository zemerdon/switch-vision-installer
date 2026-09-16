from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "switch_vision_installer/www/index.html").read_text(encoding="utf-8")
JS = (ROOT / "switch_vision_installer/www/installer.js").read_text(encoding="utf-8")
WEB = (ROOT / "switch_vision_installer/app/web.py").read_text(encoding="utf-8")

# The duplicate Installer UI is gone.
assert 'id="dry-run"' not in INDEX
assert 'id="backups-section"' not in INDEX
assert 'id="create-backup"' not in INDEX
assert "$('dry-run').addEventListener" not in JS
assert "$('create-backup').addEventListener" not in JS
assert "$('backups').addEventListener" not in JS

# Trusted backend capabilities remain available for internal/Maintenance use.
assert 'api/dry-run' in WEB
assert 'api/create-backup' in WEB
assert 'api/validate-backup' in WEB
assert 'api/restore' in WEB

print("Installer v2.1.39 UI cleanup regression: PASS")
