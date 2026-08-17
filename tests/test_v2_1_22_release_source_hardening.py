#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import importlib.util
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "switch_vision_installer" / "app"
INSTALLER = APP / "installer.py"
CONFIG = ROOT / "switch_vision_installer" / "config.yaml"
sys.path.insert(0, str(APP))

spec = importlib.util.spec_from_file_location("sv_installer_v222", INSTALLER)
assert spec and spec.loader
installer = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = installer
spec.loader.exec_module(installer)

assert installer.INSTALLER_VERSION == "2.1.23"
assert installer.OFFICIAL_RELEASE_API_URL == (
    "https://api.github.com/repos/zemerdon/"
    "switch-vision-releases/releases/latest"
)

config_text = CONFIG.read_text(encoding="utf-8")
assert 'version: "2.1.22"' in config_text
assert "allow_custom_release_source: false" in config_text
assert "allow_custom_release_source: bool" in config_text

official = {
    "release_api_url": installer.OFFICIAL_RELEASE_API_URL,
    "allow_custom_release_source": False,
}
assert installer.validated_release_api_url(official) == installer.OFFICIAL_RELEASE_API_URL

custom_url = "https://example.invalid/releases/latest"

try:
    installer.validated_release_api_url(
        {"release_api_url": custom_url, "allow_custom_release_source": False}
    )
except RuntimeError as exc:
    assert "Custom Core release sources are disabled" in str(exc)
    assert "allow_custom_release_source" in str(exc)
else:
    raise AssertionError("custom release source was accepted without explicit opt-in")

assert installer.validated_release_api_url(
    {"release_api_url": custom_url, "allow_custom_release_source": True}
) == custom_url

with tempfile.TemporaryDirectory() as td:
    options_path = Path(td) / "options.json"
    old_options_path = installer.OPTIONS_PATH
    old_request_json = installer.request_json
    seen = []
    try:
        installer.OPTIONS_PATH = options_path

        def fake_request_json(url: str):
            seen.append(url)
            return {
                "tag_name": "v9.9.9",
                "name": "fixture",
                "prerelease": False,
                "assets": [
                    {
                        "name": "switch-vision-9.9.9.zip",
                        "browser_download_url": "https://example.invalid/core.zip",
                        "size": 123,
                        "digest": "sha256:" + ("a" * 64),
                    }
                ],
            }

        installer.request_json = fake_request_json

        options_path.write_text(
            json.dumps(
                {
                    "release_api_url": custom_url,
                    "allow_custom_release_source": False,
                }
            ),
            encoding="utf-8",
        )

        try:
            installer.latest_release()
        except RuntimeError as exc:
            assert "Custom Core release sources are disabled" in str(exc)
        else:
            raise AssertionError("latest_release contacted an untrusted source")

        assert seen == []

        options_path.write_text(
            json.dumps(
                {
                    "release_api_url": custom_url,
                    "allow_custom_release_source": True,
                }
            ),
            encoding="utf-8",
        )

        release = installer.latest_release()
        assert seen == [custom_url]
        assert release["version"] == "9.9.9"
        assert release["asset_name"] == "switch-vision-9.9.9.zip"
    finally:
        installer.OPTIONS_PATH = old_options_path
        installer.request_json = old_request_json

print("Switch Vision Installer v2.1.22 release-source hardening: PASS")
