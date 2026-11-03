"""Customer-facing Installer history must not acquire local-development suffixes."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "switch_vision_installer" / "CHANGELOG.md"


def test_no_development_stage_suffixes_in_customer_changelog():
    text = CHANGELOG.read_text(encoding="utf-8")
    assert not re.search(r"(?mi)^#{1,4} [^\n]*\((?:Local|Local pilot)\)\s*$", text)
    config = (ROOT / "switch_vision_installer" / "config.yaml").read_text(encoding="utf-8")
    version = re.search(r'(?m)^version:\s*"?([0-9]+\.[0-9]+\.[0-9]+)"?\s*$', config)
    assert version is not None
    assert text.startswith(f"## v{version.group(1)} ")
