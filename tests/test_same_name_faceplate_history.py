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

def test_catalogue_archives_unchanged_and_changed_stock_images() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        existing, incoming = root / "installed", root / "new"
        component = root / "installed-component"
        name1, name2 = "same.png", "edited.png"
        old1, old2, new2 = b"unchanged", b"old-artwork", b"new-artwork"
        hashes = {name1: hashlib.sha256(old1).hexdigest(),
                  name2: hashlib.sha256(old2).hexdigest()}
        component.mkdir()
        (component / "stock-assets.json").write_text(json.dumps({
            "schema": "switch-vision-stock-assets-v1",
            "assets": {"faceplates": hashes},
        }))
        new_component = incoming / "custom_components/switch_vision"
        new_component.mkdir(parents=True)
        (new_component / "stock-assets.json").write_text(json.dumps({
            "schema": "switch-vision-stock-assets-v1",
            "assets": {"faceplates": {
                name1: hashes[name1], name2: hashlib.sha256(new2).hexdigest()
            }},
        }))
        _image(existing, name1, old1)
        _image(existing, name2, old2)
        _image(incoming, name1, old1)
        _image(incoming, name2, new2)
        stage = root / "stage"
        assert history.stage_history(incoming, component, existing, stage) == 1
        assert (stage / "faceplate-history" / hashes[name1] / name1).read_bytes() == old1
        assert (stage / "faceplate-history" / hashes[name2] / name2).read_bytes() == old2
        assert (stage / "faceplate-history" / "legacy" / name2).read_bytes() == old2
        # Repeated versions deduplicate unchanged originals.
        from shutil import copytree
        copytree(stage / "faceplate-history", existing / "faceplate-history")
        again = root / "again"
        assert history.stage_history(incoming, component, existing, again) == 1
        assert (again / "faceplate-history" / hashes[name1] / name1).read_bytes() == old1


if __name__ == "__main__":
    test_catalogue_archives_unchanged_and_changed_stock_images()
    test_same_name_installer_retains_original_for_preview()
    test_no_fabricated_archive_on_untrusted_installed_art()
    print("INSTALLER_SAME_NAME_FACEPLATE_HISTORY_PASS")
