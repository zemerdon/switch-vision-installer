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


def test_installer_auto_start_does_not_trigger_component_updates():
    root = ROOT / "switch_vision_installer"
    config = (root / "config.yaml").read_text(encoding="utf-8")
    assert re.search(r"(?m)^startup: application$", config)
    assert re.search(r"(?m)^boot: auto$", config)
    run_sh = (root / "run.sh").read_text(encoding="utf-8")
    assert "exec python3 /opt/switch-vision-installer/app/web_manager.py" in run_sh
    source = (root / "app/web_manager.py").read_text(encoding="utf-8")
    main = source.split('if __name__ == "__main__":', 1)[1]
    assert "recover_interrupted_tree_replacements()" in main
    assert "ThreadingHTTPServer(" in main
    assert "update_all(" not in main
    assert "update_component(" not in main
    assert "reinstall_component(" not in main
