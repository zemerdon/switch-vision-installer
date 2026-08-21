from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "switch_vision_installer"


def load_installer():
    path = APP / "app" / "installer.py"
    spec = importlib.util.spec_from_file_location("installer_v2125_actual", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


installer = load_installer()


class FakeAssetResponse:
    headers = {
        "Content-Length": "1234567",
        "Last-Modified": "Fri, 21 Aug 2026 06:44:00 GMT",
    }
    def __enter__(self): return self
    def __exit__(self, exc_type, exc, tb): return False


class InstallerReleaseMetadataTests(unittest.TestCase):
    def test_asset_metadata_uses_head_without_rest_api(self):
        seen = []
        def fake_urlopen(request, timeout=0):
            seen.append((request.full_url, request.get_method()))
            return FakeAssetResponse()
        url = "https://github.com/zemerdon/switch-vision-releases/releases/download/2.4.6/switch-vision-2.4.6.zip"
        with patch.object(installer.urllib.request, "urlopen", side_effect=fake_urlopen):
            metadata = installer._official_release_asset_metadata(url)
        self.assertEqual(metadata["asset_size"], 1234567)
        self.assertEqual(metadata["published_at"], "Fri, 21 Aug 2026 06:44:00 GMT")
        self.assertEqual(seen, [(url, "HEAD")])
        self.assertFalse(any("api.github.com" in target for target, _ in seen))

    def test_official_release_carries_best_effort_display_metadata(self):
        with patch.object(installer, "official_latest_release_version", return_value="2.4.6"), \
             patch.object(installer, "_official_release_asset_metadata", return_value={"asset_size": 7654321, "published_at": "Fri, 21 Aug 2026 06:44:00 GMT"}), \
             patch.object(installer, "_official_release_notes", return_value="notes"), \
             patch.object(installer, "request_json", side_effect=AssertionError("official path must not use REST API")):
            release = installer.official_latest_release()
        self.assertEqual(release["asset_size"], 7654321)
        self.assertEqual(release["published_at"], "Fri, 21 Aug 2026 06:44:00 GMT")
        self.assertTrue(release["asset_url"].endswith("/2.4.6/switch-vision-2.4.6.zip"))

    def test_unknown_asset_size_is_not_rendered_as_zero(self):
        js = (APP / "www" / "installer.js").read_text(encoding="utf-8")
        self.assertIn("if(n===null||n===undefined||n==='')return'—'", js)

    def test_custom_source_options_are_truthfully_labelled(self):
        text = (APP / "translations" / "en.yaml").read_text(encoding="utf-8")
        self.assertIn("name: Custom release API URL", text)
        self.assertIn("name: Allow custom release source", text)
        self.assertIn("quota-free GitHub release redirect", text)

    def test_current_config_still_has_valid_release_version_metadata(self):
        config = (APP / "config.yaml").read_text(encoding="utf-8")
        match = re.search(r'(?m)^version:\s*["\']?([^"\'\s#]+)', config)
        self.assertIsNotNone(match)
        self.assertRegex(match.group(1), r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
