"""Regression for stock artwork revisions with stable faceplate filenames."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "switch_vision_installer/app/faceplate_history.py"
spec = importlib.util.spec_from_file_location("faceplate_history", MODULE)
assert spec and spec.loader
history = importlib.util.module_from_spec(spec)
spec.loader.exec_module(history)


def _manifest(component: Path, filename: str, data: bytes) -> str:
    digest = hashlib.sha256(data).hexdigest()
    component.mkdir(parents=True, exist_ok=True)
    (component / "stock-assets.json").write_text(json.dumps({
        "schema": "switch-vision-stock-assets-v1",
        "assets": {"faceplates": {filename: digest}},
    }))
    return digest


def _image(root: Path, name: str, data: bytes) -> None:
    target = root / "faceplates" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def test_same_name_installer_retains_original_for_preview() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        existing = root / "installed"
        incoming = root / "release"
        component = root / "current-component"
        stage = root / "stage"
        name = "cisco-3850-12xs.png"
        original, updated, next_update = b"original-stock", b"new-stock", b"next-revision"
        original_sha = _manifest(component, name, original)
        _manifest(incoming / "custom_components/switch_vision", name, updated)
        _image(existing, name, original)
        _image(incoming, name, updated)
        assert history.stage_history(incoming, component, existing, stage) == 1
        assert (stage / "faceplate-history" / original_sha / name).read_bytes() == original
        assert (stage / "faceplate-history" / "legacy" / name).read_bytes() == original
        # A later release retains the earliest legacy original, and archives
        # the intermediate image under its own exact content digest.
        second = root / "release-next"
        _manifest(second / "custom_components/switch_vision", name, next_update)
        _image(second, name, next_update)
        updated_sha = _manifest(component, name, updated)
        _image(existing, name, updated)
        from shutil import copytree
        copytree(stage / "faceplate-history", existing / "faceplate-history")
        later = root / "stage-next"
        assert history.stage_history(second, component, existing, later) == 1
        assert (later / "faceplate-history" / original_sha / name).read_bytes() == original
        assert (later / "faceplate-history" / updated_sha / name).read_bytes() == updated
        assert (later / "faceplate-history" / "legacy" / name).read_bytes() == original


def test_no_fabricated_archive_on_untrusted_installed_art() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        name = "same.png"
        installed = root / "installed"
        release = root / "release"
        _manifest(root / "current", name, b"trusted-original")
        _manifest(release / "custom_components/switch_vision", name, b"new")
        _image(installed, name, b"custom-tampered")
        _image(release, name, b"new")
        stage = root / "stage"
        assert history.stage_history(release, root / "current", installed, stage) == 0
        assert not (stage / "faceplate-history").exists()
        assert name == "same.png", "model stock filenames must never be renamed"

if __name__ == "__main__":
    test_same_name_installer_retains_original_for_preview()
    test_no_fabricated_archive_on_untrusted_installed_art()
    print("INSTALLER_SAME_NAME_FACEPLATE_HISTORY_PASS")
