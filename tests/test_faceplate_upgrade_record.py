"""Regression: install-time choices persist without a Calibration save."""
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "switch_vision_installer/app"))
import faceplate_history as history
import faceplate_upgrade_record as record


def test_capture_and_no_new_switch() -> None:
    with TemporaryDirectory() as tmp:
        base = Path(tmp)
        installed, release = base / "installed", base / "release"
        component = base / "component"
        name = "cisco-3850-12xs.png"
        old, new = b"old-art", b"new-art"
        old_sha, new_sha = (hashlib.sha256(b).hexdigest() for b in (old, new))
        for target, data in ((installed / "faceplates" / name, old),
                             (release / "faceplates" / name, new)):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        for target, sha in ((component / "stock-assets.json", old_sha),
                            (release / "custom_components/switch_vision/stock-assets.json", new_sha)):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps({"schema": "switch-vision-stock-assets-v1",
                                         "assets": {"faceplates": {name: sha}}}))
        model = release / "devices/supported_devices.json"
        model.parent.mkdir(parents=True)
        model.write_text(json.dumps({"devices": [{"model": "WS-C3850-12XS-E",
                          "dashboard_support": True,
                          "default_faceplate": "faceplates/" + name}]}))
        stage = base / "stage"
        assert history.stage_history(release, component, installed, stage) == 1
        options = {"switches": [{"switch_name": "SW3", "switch_model": "WS-C3850-12XS-E",
                                "snmp_community": "TOP_SECRET"}]}
        prepared = record.prepare_record(release, component, installed, stage, options)
        assert prepared["native_SW3"][name] == {"before": old_sha, "after": new_sha}
        assert "native_SW4" not in prepared
        path = base / "private/upgrade-record.json"
        assert record.store_record(path, prepared) == 2
        assert record.store_record(path, prepared) == 0
        assert "TOP_SECRET" not in path.read_text()
        assert record.read_record(path) == prepared
        assert record.existing_switches({"switches": [
            {"switch_name": "A B", "switch_model": "auto"},
            {"switch_name": "A_B", "switch_model": "auto"}]}) == {}
        (stage / "faceplate-history" / old_sha / name).write_bytes(b"tampered")
        assert record.prepare_record(release, component, installed, stage, options) == {}
        assert record.prepare_record(release, component, installed, stage, None) == {}


if __name__ == "__main__":
    test_capture_and_no_new_switch()
    print("INSTALLER_PREUPGRADE_RECORD_PASS")
