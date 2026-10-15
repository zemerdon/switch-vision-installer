"""Aged-out selected artwork survives only with exact factory geometry."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from shutil import copytree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "switch_vision_installer/app"))
import faceplate_history as history


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def bundle(root: Path, version: str, png: bytes, x: int,
           *, current: bool = False) -> dict:
    name = "example.png"
    image_path = (f"faceplates/{name}" if current
                  else f"faceplates-old/{version}/{name}")
    geo_path = ("calibration/faceplate-example.json" if current
                else f"faceplates-old/{version}/example.json")
    geometry = json.dumps({
        "schema": "switch-vision-interactive-calibration-v1",
        "image": {"file": "faceplates/example.png"},
        "ports": {"1": {"center": [x, 10]}}, "sfp": {},
    }).encode()
    for rel, value in ((image_path, png), (geo_path, geometry)):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    return {
        "version": version, "filename": name, "sha256": sha(png),
        "geometry_sha256": sha(geometry),
        "path": image_path, "geometry_path": geo_path,
    }


def manifest(root: Path, rows: list[dict]) -> None:
    target = root / "faceplates-old/manifest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "schema": 1, "core_version": "2.7.99",
        "faceplates": {"example.png": rows},
    }))


class SelectedRetentionTests(unittest.TestCase):
    def test_selected_rotation_across_installs_and_calibration_isolation(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            old, incoming, stage = (base / p for p in ("old", "incoming", "stage"))
            selected = bundle(old, "2.7.70", b"art-a", 10)
            unselected = bundle(old, "2.7.71", b"art-b", 15)
            manifest(old, [selected, unselected])
            incoming_latest = bundle(incoming, "2.7.99", b"art-c", 20, current=True)
            manifest(incoming, [incoming_latest])
            store = base / ".storage/switch_vision_calibrations"
            store.parent.mkdir()
            original = json.dumps({"version": 1, "key": "switch_vision_calibrations",
                "data": {"profiles": {"native_SW1": {"ports": {"1": {"x": 7}}}},
                         "stock_artwork_choices": {"native_SW1": {
                             "filename": selected["filename"],
                             "sha256": selected["sha256"],
                             "version": selected["version"],
                             "geometry_sha256": selected["geometry_sha256"],
                         }}}}).encode()
            store.write_bytes(original)
            self.assertEqual(history.preserve_selected_pairs(incoming, old, stage, store), 1)
            kept = stage / "faceplate-history/revisions/2.7.70"
            self.assertEqual((kept / "example.png").read_bytes(), b"art-a")
            self.assertEqual(json.loads((kept / "example.json").read_text())
                             ["ports"]["1"]["center"], [10, 10])
            self.assertFalse((stage / "faceplate-history/revisions/2.7.71").exists())
            self.assertEqual(store.read_bytes(), original)

            # Later update: the selected pair is no longer in the shipped
            # archive, but the local verified pair stays pinned.
            subsequent = base / "subsequent"
            later = base / "later"
            manifest(subsequent, [incoming_latest])
            copytree(stage / "faceplate-history", old / "faceplate-history")
            manifest(old, [unselected])
            self.assertEqual(history.preserve_selected_pairs(subsequent, old, later, store), 1)
            self.assertEqual((later / "faceplate-history/revisions/2.7.70/example.png").read_bytes(),
                             b"art-a")
            self.assertEqual(store.read_bytes(), original)

            # A deselection does not create permanent history.
            store.write_text(json.dumps({"data": {"stock_artwork_choices": {}}}))
            expired = base / "expired"
            self.assertEqual(history.preserve_selected_pairs(subsequent, old, expired, store), 0)
            self.assertFalse((expired / "faceplate-history").exists())

    def test_corrupt_selected_geometry_blocks_replacement(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            old, incoming, stage = (base / p for p in ("old", "incoming", "stage"))
            selected = bundle(old, "2.7.70", b"art-a", 10)
            manifest(old, [selected])
            latest = bundle(incoming, "2.7.90", b"art-b", 20, current=True)
            manifest(incoming, [latest])
            store = base / "choices.json"
            store.write_text(json.dumps({"data": {"stock_artwork_choices": {
                "native_SW1": {
                    "filename": "example.png", "sha256": selected["sha256"],
                    "version": selected["version"],
                    "geometry_sha256": selected["geometry_sha256"],
                }}}}))
            (old / selected["geometry_path"]).write_text("tampered")
            with self.assertRaisesRegex(RuntimeError, "corrupt/missing"):
                history.preserve_selected_pairs(incoming, old, stage, store)
            self.assertFalse((stage / "faceplate-history/revisions/manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
