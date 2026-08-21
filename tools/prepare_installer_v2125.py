#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "switch_vision_installer"
VERSION = "2.1.25"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace("\r\n", "\n").replace("\r", "\n"), encoding="utf-8", newline="\n")


# Version metadata.
config_path = APP / "config.yaml"
config = read(config_path)
config = config.replace('version: "2.1.24"', f'version: "{VERSION}"', 1)
write(config_path, config)

installer_path = APP / "app" / "installer.py"
installer = read(installer_path)
installer = installer.replace('INSTALLER_VERSION = "2.1.24"', f'INSTALLER_VERSION = "{VERSION}"', 1)

# Keep normal official release checks quota-free while enriching display metadata
# from the deterministic asset URL using HEAD only. Failure is advisory: update
# discovery/install still works with unknown display metadata.
pattern = re.compile(
    r"def official_latest_release\(\) -> dict\[str, Any\]:\n.*?\n\n\ndef latest_release\(\) -> dict\[str, Any\]:",
    re.S,
)
replacement = '''def _official_release_asset_metadata(url: str) -> dict[str, Any]:
    """Best-effort public asset metadata without using GitHub REST API quota."""
    request = urllib.request.Request(
        url,
        method="HEAD",
        headers={"User-Agent": f"Switch-Vision-Installer/{INSTALLER_VERSION}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            headers = response.headers
            raw_size = str(headers.get("Content-Length") or "").strip()
            size = int(raw_size) if raw_size.isdigit() else None
            if size is not None and size <= 0:
                size = None
            modified = str(headers.get("Last-Modified") or "").strip() or None
            return {"asset_size": size, "published_at": modified}
    except Exception:
        return {"asset_size": None, "published_at": None}


def official_latest_release() -> dict[str, Any]:
    """Build trusted official release metadata from deterministic public paths."""
    version = official_latest_release_version()
    expected_name = f"switch-vision-{version}.zip"
    checksum_name = f"{expected_name}.sha256"
    download_base = f"{OFFICIAL_RELEASE_DOWNLOAD_BASE}/{version}"
    asset_url = f"{download_base}/{expected_name}"
    display_metadata = _official_release_asset_metadata(asset_url)
    return {
        "version": version,
        "name": f"Switch Vision Core v{version}",
        "published_at": display_metadata.get("published_at"),
        "asset_name": expected_name,
        "asset_url": asset_url,
        "asset_size": display_metadata.get("asset_size"),
        "asset_digest": None,
        "html_url": f"https://github.com/zemerdon/switch-vision-releases/releases/tag/{version}",
        "changelog": _official_release_notes(version),
        "checksum_asset_name": checksum_name,
        "checksum_asset_url": f"{download_base}/{checksum_name}",
    }


def latest_release() -> dict[str, Any]:'''
installer, count = pattern.subn(replacement, installer, count=1)
if count != 1:
    raise SystemExit("Could not replace official_latest_release block")
write(installer_path, installer)

# Frontend must not convert null/unknown asset metadata into a fabricated 0 B.
js_path = APP / "www" / "installer.js"
js = read(js_path)
old = "function fmtBytes(n){if(!Number.isFinite(Number(n)))return'—';"
new = "function fmtBytes(n){if(n===null||n===undefined||n==='')return'—';if(!Number.isFinite(Number(n)))return'—';"
if old not in js:
    raise SystemExit("fmtBytes source marker missing")
js = js.replace(old, new, 1)
write(js_path, js)

# Clarify that the API URL is an advanced custom-source option only.
translation_path = APP / "translations" / "en.yaml"
translations = read(translation_path)
translations = translations.replace(
    "  release_api_url:\n    name: Release API URL\n    description: GitHub API endpoint used to locate the latest public release.\n",
    "  release_api_url:\n    name: Custom release API URL\n    description: Used only when Allow custom release source is enabled. Official releases use the quota-free GitHub release redirect and deterministic download paths.\n"
    "  allow_custom_release_source:\n    name: Allow custom release source\n    description: Advanced option. Keep disabled for normal Switch Vision updates; enable only when intentionally using a custom release API.\n",
    1,
)
translations = translations.replace(
    "  release_asset_pattern:\n    name: Release asset pattern\n    description: Filename pattern used to select the installable ZIP.\n",
    "  release_asset_pattern:\n    name: Custom release asset pattern\n    description: Filename pattern used only with an explicitly enabled custom release source. Official releases use deterministic asset names.\n",
    1,
)
write(translation_path, translations)

# Make the permanent validator future-proof: compile every regression and run
# every test file as its own Python process, so newly added tests cannot silently
# exist without normal PR CI executing them.
workflow_path = ROOT / ".github" / "workflows" / "validate.yaml"
workflow = read(workflow_path)
compile_start = workflow.index("      - name: Compile Python\n")
compile_end = workflow.index("      - name: Check shell syntax\n", compile_start)
compile_block = '''      - name: Compile Python
        run: |
          python -m py_compile \\
            switch_vision_installer/app/installer.py \\
            switch_vision_installer/app/repository_setup.py \\
            switch_vision_installer/app/web.py \\
            switch_vision_installer/app/component_manager.py \\
            switch_vision_installer/app/web_manager.py \\
            tests/*.py

'''
workflow = workflow[:compile_start] + compile_block + workflow[compile_end:]

regression_start = workflow.index("      - name: Validate repository-era backup and restore\n")
regression_end = workflow.index("      - name: Validate release metadata\n", regression_start)
regression_block = '''      - name: Run permanent regression suite
        shell: bash
        run: |
          set -euo pipefail
          for test in tests/test_*.py; do
            echo "::group::$test"
            python "$test"
            echo "::endgroup::"
          done

'''
workflow = workflow[:regression_start] + regression_block + workflow[regression_end:]
write(workflow_path, workflow)

# Keep the existing 2.1.24 regression network-isolated now that official
# metadata enrichment has its own HEAD request.
test_2124_path = ROOT / "tests" / "test_v2_1_24_rate_limit_safe_release.py"
test_2124 = read(test_2124_path)
old_ctx = '''        with patch.object(installer, "official_latest_release_version", return_value="2.4.3"), \\
             patch.object(installer, "_official_release_notes", return_value="notes"):\n'''
new_ctx = '''        with patch.object(installer, "official_latest_release_version", return_value="2.4.3"), \\
             patch.object(installer, "_official_release_asset_metadata", return_value={"asset_size": None, "published_at": None}), \\
             patch.object(installer, "_official_release_notes", return_value="notes"):\n'''
if old_ctx not in test_2124:
    raise SystemExit("2.1.24 metadata test context marker missing")
test_2124 = test_2124.replace(old_ctx, new_ctx, 1)
write(test_2124_path, test_2124)

# New permanent regression for metadata enrichment, truthful unknown rendering,
# option wording, version metadata, and the no-REST contract.
test_2125_path = ROOT / "tests" / "test_v2_1_25_release_metadata.py"
write(test_2125_path, '''from __future__ import annotations

import importlib.util
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
        with patch.object(installer, "official_latest_release_version", return_value="2.4.6"), \\
             patch.object(installer, "_official_release_asset_metadata", return_value={"asset_size": 7654321, "published_at": "Fri, 21 Aug 2026 06:44:00 GMT"}), \\
             patch.object(installer, "_official_release_notes", return_value="notes"), \\
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

    def test_version_metadata_is_2_1_25(self):
        config = (APP / "config.yaml").read_text(encoding="utf-8")
        self.assertIn('version: "2.1.25"', config)
        self.assertEqual(installer.INSTALLER_VERSION, "2.1.25")


if __name__ == "__main__":
    unittest.main()
''')

# Changelog.
changelog_path = APP / "CHANGELOG.md"
changelog = read(changelog_path)
entry = '''# Changelog

## v2.1.25 — Audit hardening and release metadata cleanup

- Run every permanent Installer regression test automatically in normal PR CI, including the v2.1.24 GitHub rate-limit-safe release test.
- Execute each regression file in its own Python process so module state cannot leak between historical hardening tests.
- Enrich official Core release display metadata with a quota-free HEAD request to the deterministic release asset URL; official version discovery and installation continue to avoid the GitHub REST API.
- Render unavailable asset size as unknown instead of incorrectly displaying `0 B`.
- Clarify Home Assistant options so `release_api_url` is identified as an advanced custom-source setting only; normal official releases use the quota-free GitHub redirect/download path.
- Preserve deterministic official asset names, published SHA-256 verification, archive limits, atomic replacement, backup/restore behaviour, and component-management semantics unchanged.

'''
if changelog.startswith("# Changelog\n\n") and "## v2.1.25" not in changelog:
    changelog = entry + changelog[len("# Changelog\n\n"):]
write(changelog_path, changelog)

print("Prepared Switch Vision Installer v2.1.25 audit hardening")
