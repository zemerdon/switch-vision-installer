"""Installer-owned SHA preflight and local preservation, no bundled history."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "switch_vision_installer/app"))
from faceplate_history import compare_sha_pairs, preserve_sha_pairs, faceplate_change_summary


def digest(data):
    return hashlib.sha256(data).hexdigest()


def release(root, png, x, *, alias_x=None):
    frontend = root
    component = root / "custom_components/switch_vision"
    component.mkdir(parents=True)
    image = frontend / "faceplates/example.png"
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(png)
    geometry = {
        "schema": "switch-vision-interactive-calibration-v1",
        "image": {"file": "faceplates/example.png"},
        "ports": {"1": {"center": [x, 10]}}, "sfp": {},
    }
    path = frontend / "calibration/faceplate-example.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(geometry))
    if alias_x is not None:
        geometry["ports"]["1"]["center"][0] = alias_x
        (path.parent / "example-model-specific.json").write_text(json.dumps(geometry))
    (component / "stock-assets.json").write_text(json.dumps({
        "schema": "switch-vision-stock-assets-v1",
        "assets": {"faceplates": {"example.png": digest(png)}},
    }))
    return component


class SHAHistoryTests(unittest.TestCase):
    def test_no_change_no_history_even_when_component_version_changes(self):
        with TemporaryDirectory() as td:
            b = Path(td)
            old, new, stage = (b / name for name in ("old", "new", "stage"))
            component = release(old, b"pixels", 10, alias_x=42)
            release(new, b"pixels", 10, alias_x=300)
            self.assertEqual(compare_sha_pairs(new, component, old), [])
            self.assertEqual(preserve_sha_pairs(new, component, old, stage), [])
            self.assertFalse((stage / "faceplate-history").exists())

    def test_image_change_and_geometry_only_change_keep_one_canonical_pair(self):
        for png, x in ((b"new", 10), (b"pixels", 20)):
            with self.subTest(png=png, geometry=x), TemporaryDirectory() as td:
                b = Path(td)
                old, new, stage = (b / name for name in ("old", "new", "stage"))
                component = release(old, b"pixels", 10, alias_x=42)
                release(new, png, x, alias_x=200)
                changed = compare_sha_pairs(new, component, old)
                self.assertEqual(len(changed), 1)
                row = changed[0]
                self.assertEqual(row["geometry_file"], "faceplate-example.json")
                self.assertEqual(preserve_sha_pairs(new, component, old, stage), changed)
                stored = stage / row["path"]
                factory = stage / row["geometry_path"]
                self.assertEqual(stored.read_bytes(), b"pixels")
                self.assertEqual(json.loads(factory.read_text())["ports"]["1"]["center"], [10, 10])
                self.assertEqual(len(json.loads((stage / "faceplate-history/revisions/sha/manifest.json").read_text())["faceplates"]["example.png"]), 1)

    def test_selected_older_pair_survives_skipped_upgrades(self):
        with TemporaryDirectory() as td:
            b = Path(td)
            old, mid, final, stage1, stage2 = (b / name for name in
                                              ("old", "mid", "final", "stage1", "stage2"))
            component = release(old, b"A", 10)
            release(mid, b"B", 20)
            release(final, b"C", 30)
            initial = preserve_sha_pairs(mid, component, old, stage1)
            self.assertEqual(len(initial), 1)
            # A selected A survives even after B has become installed stock.
            import shutil
            shutil.copytree(mid, b / "installed")
            installed = b / "installed"
            shutil.copytree(stage1 / "faceplate-history", installed / "faceplate-history")
            selected = b / "choices.json"
            selected.write_text(json.dumps({"data": {"stock_artwork_choices": {
                "native_a": {"filename": "example.png", "sha256": initial[0]["sha256"],
                              "geometry_sha256": initial[0]["geometry_sha256"]},
            }}}))
            changes = preserve_sha_pairs(final, installed / "custom_components/switch_vision",
                                          installed, stage2, selected)
            self.assertEqual(len(changes), 1)
            rows = json.loads((stage2 / "faceplate-history/revisions/sha/manifest.json").read_text())["faceplates"]["example.png"]
            self.assertEqual(len(rows), 2)
            self.assertEqual((stage2 / rows[0]["path"]).read_bytes(), b"A")
            self.assertEqual((stage2 / rows[1]["path"]).read_bytes(), b"B")

    def test_new_dedicated_stock_not_confused_with_generic_revision(self):
        with TemporaryDirectory() as td:
            b = Path(td)
            old, new, stage = (b / name for name in ("old", "new", "stage"))
            component = release(old, b"generic", 10)
            release(new, b"generic", 10)
            # A dedicated model now has its own faceplate + factory geometry;
            # shared generic files remain byte-identical and must not be
            # archived as if their stock revision had changed.
            dedicated = new / "faceplates/dedicated.png"
            dedicated.write_bytes(b"dedicated")
            geometry = {
                "schema": "switch-vision-interactive-calibration-v1",
                "image": {"file": "faceplates/dedicated.png"},
                "ports": {"1": {"center": [40, 10]}}, "sfp": {},
            }
            (new / "calibration/faceplate-dedicated.json").write_text(json.dumps(geometry))
            assets = new / "custom_components/switch_vision/stock-assets.json"
            data = json.loads(assets.read_text())
            data["assets"]["faceplates"]["dedicated.png"] = digest(b"dedicated")
            assets.write_text(json.dumps(data))
            before = faceplate_change_summary(new, component, old)
            self.assertEqual(before["new"], ["dedicated.png"])
            self.assertEqual(before["changed"], [])
            self.assertEqual(preserve_sha_pairs(new, component, old, stage), [])
            self.assertFalse((stage / "faceplate-history").exists())

    def test_tamper_blocks_pair_preservation(self):
        with TemporaryDirectory() as td:
            b = Path(td)
            old, new = b / "old", b / "new"
            component = release(old, b"A", 10)
            release(new, b"B", 10)
            (old / "faceplates/example.png").write_bytes(b"tampered")
            with self.assertRaisesRegex(RuntimeError, "Cannot verify"):
                preserve_sha_pairs(new, component, old, b / "stage")


if __name__ == "__main__":
    unittest.main()
