"""Guard the retired Installer preview boundary while retaining diagnostic dry-run."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "switch_vision_installer/app"
sys.path.insert(0, str(APP))
import installer
import web
import faceplate_history

assert not hasattr(faceplate_history, "stage_preflight_previews")
assert "/api/faceplate-preview" not in (APP / "web.py").read_text()
assert "faceplate-previews" not in (APP / "installer.py").read_text()
assert "faceplate_preview_sha256" not in (APP / "installer.py").read_text()
assert "api/dry-run" in (APP / "web.py").read_text()
assert "stage_history" in (APP / "faceplate_history.py").read_text()
assert "preserve_sha_pairs" in (APP / "faceplate_history.py").read_text()

with TemporaryDirectory() as tmp:
    base=Path(tmp)
    staged=base/"staged"
    staged.mkdir()
    release={"version":"2.1.64","asset_name":"switch-vision-test.zip"}
    with (
        patch.object(installer,"prepare_release",return_value=(release,base/"temp",staged,"aa"*32,True)),
        patch.object(installer,"component_plan",return_value=([("src","dest","Core")],[],[])),
        patch.object(installer,"collect_custom_assets",return_value={"faceplates":["custom.png"]}),
        patch.object(installer._faceplate_history,"faceplate_change_summary",
                     return_value={"new":[],"changed":[]}),
        patch.object(installer,"preflight_checks",return_value={"checks":[{"name":"checksum","ok":True,"detail":"verified"}]}),
        patch.object(installer,"load_options",return_value={"create_backup":True}),
        patch.object(installer.shutil,"rmtree"),
    ):
        result=installer.dry_run()
    assert result["dry_run"] is True
    assert result["version"]=="2.1.64"
    assert result["faceplate_changes"]=={"new":[],"changed":[]}
    assert result["checksum_verified"] is True
    assert "faceplate_preview_sha256" not in result
    assert result["would_create_backup"] is True
    assert result["would_preserve"]==["faceplates/custom.png"]
print("Installer 2.1.64 orphan preview retirement and live dry-run contract: PASS")
