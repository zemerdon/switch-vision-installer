from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "switch_vision_installer" / "app"

def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

installer = load_module("installer_v2124_actual", APP / "installer.py")
sys.modules["installer"] = installer
repository_setup = load_module("repository_setup_v2124_actual", APP / "repository_setup.py")
sys.modules["repository_setup"] = repository_setup
component_manager = load_module("component_manager_v2124_actual", APP / "component_manager.py")

class FakeRedirectResponse:
    def __enter__(self): return self
    def __exit__(self, exc_type, exc, tb): return False
    def geturl(self): return "https://github.com/zemerdon/switch-vision-releases/releases/tag/2.4.3"

class InstallerRateLimitSafeReleaseTests(unittest.TestCase):
    def test_official_version_uses_releases_redirect_not_rest_api(self):
        seen = []
        def fake_urlopen(request, timeout=0):
            seen.append((request.full_url, request.get_method()))
            return FakeRedirectResponse()
        with patch.object(installer.urllib.request, "urlopen", side_effect=fake_urlopen):
            self.assertEqual(installer.official_latest_release_version(), "2.4.3")
        self.assertEqual(seen, [(installer.OFFICIAL_RELEASE_LATEST_URL, "HEAD")])
        self.assertFalse(any("api.github.com" in url for url, _ in seen))

    def test_official_metadata_is_deterministic_and_checksum_backed(self):
        with patch.object(installer, "official_latest_release_version", return_value="2.4.3"), \
             patch.object(installer, "_official_release_notes", return_value="notes"):
            release = installer.official_latest_release()
        self.assertEqual(release["asset_name"], "switch-vision-2.4.3.zip")
        self.assertEqual(release["checksum_asset_name"], "switch-vision-2.4.3.zip.sha256")
        self.assertTrue(release["asset_url"].endswith("/2.4.3/switch-vision-2.4.3.zip"))
        self.assertTrue(release["checksum_asset_url"].endswith("/2.4.3/switch-vision-2.4.3.zip.sha256"))

    def test_official_latest_release_does_not_call_request_json(self):
        options = {"release_api_url": installer.OFFICIAL_RELEASE_API_URL, "allow_custom_release_source": False, "release_asset_pattern": "switch-vision-*.zip", "allow_prerelease": False}
        with patch.object(installer, "load_options", return_value=options), \
             patch.object(installer, "official_latest_release", return_value={"version": "2.4.3"}), \
             patch.object(installer, "request_json", side_effect=AssertionError("REST API must not be used")):
            self.assertEqual(installer.latest_release()["version"], "2.4.3")

    def test_component_manager_core_status_uses_non_api_resolver(self):
        core = next(spec for spec in component_manager.COMPONENTS if spec.component_id == "core")
        with patch.object(installer, "official_latest_release_version", return_value="2.4.3") as latest, \
             patch.object(component_manager, "_github_request", side_effect=AssertionError("REST API must not be used")):
            self.assertEqual(component_manager._remote_version(core), "2.4.3")
            latest.assert_called_once_with()

if __name__ == "__main__": unittest.main()
