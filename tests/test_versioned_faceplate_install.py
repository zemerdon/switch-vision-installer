"""Installer must carry Core's versioned image/geometry tree unchanged."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "switch_vision_installer/app"))
import installer


class InstallerBundledFaceplatesTests(unittest.TestCase):
    def test_build_stage_carries_archived_pairs_without_legacy_record(self) -> None:
        with TemporaryDirectory(prefix="faceplate-install-") as tmp:
            root = Path(tmp)
            source = root / "release"
            stage = root / "stage"
            directory = source / "faceplates-old" / "2.7.92"
            directory.mkdir(parents=True)
            (directory / "switch.png").write_bytes(b"historical-image")
            (directory / "switch.json").write_text(json.dumps({"ports": {"1": {}}}))
            (source / "faceplates-old/manifest.json").write_text('{"schema":1}')
            original = installer._faceplate_history.stage_history
            try:
                installer._faceplate_history.stage_history = lambda *args: 0
                installer.build_frontend_stage(source, stage)
            finally:
                installer._faceplate_history.stage_history = original
            for name in ("switch.png", "switch.json"):
                self.assertEqual((stage / "faceplates-old/2.7.92" / name).read_bytes(),
                                 (directory / name).read_bytes())
            self.assertEqual((stage / "faceplates-old/manifest.json").read_bytes(),
                             (source / "faceplates-old/manifest.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
