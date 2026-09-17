from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = (ROOT / "switch_vision_installer/CHANGELOG.md").read_text(encoding="utf-8")

assert "## v2.1.40 — Switch Vision Local candidate refresh" in CHANGELOG
assert "canonical/public Installer runtime behavior unchanged" in CHANGELOG
assert "Local-only repository/Core routing remains an sv-dev test projection" in CHANGELOG

print("Installer v2.1.40 Local candidate historical contract: PASS")
