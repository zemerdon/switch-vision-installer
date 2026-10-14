#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools/sv_release_check.py"
SPEC = importlib.util.spec_from_file_location(
    "sv_installer_release_check_test",
    MODULE_PATH,
)
assert SPEC and SPEC.loader
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class InstallerReleaseCheckTests(unittest.TestCase):
    def test_current_version_contract_is_coherent(self):
        version = release.resolve_version(ROOT)
        self.assertEqual(version, "2.1.52")
        release.validate_version_contract(ROOT, version)

    def test_release_dependency_set_is_intentionally_empty(self):
        lines = [
            line.strip()
            for line in (
                ROOT / "tools/sv_release_check.requirements.txt"
            ).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertEqual(lines, [])

    def test_all_product_regressions_are_discovered(self):
        checks = release.permanent_checks(ROOT)
        expected = tuple(sorted((ROOT / "tests").glob("test_*.py")))
        self.assertEqual(checks[:-1], expected)
        self.assertEqual(
            checks[-1],
            ROOT / "tools/test_sv_release_check.py",
        )
        self.assertGreaterEqual(len(expected), 22)

    def test_release_check_is_local_and_non_publishing(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("SV_RELEASE_CHECK_PASS", source)
        self.assertIn("PYTHONDONTWRITEBYTECODE", source)
        self.assertIn('f"safe.directory={root}"', source)
        for forbidden in (
            "gh api",
            "gh release",
            "docker push",
            "git push",
            "git fetch",
            "workflow_dispatch",
        ):
            self.assertNotIn(forbidden, source)

    def test_dockerfile_contract_requires_digest_pinning(self):
        release.validate_dockerfile_contract(ROOT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
