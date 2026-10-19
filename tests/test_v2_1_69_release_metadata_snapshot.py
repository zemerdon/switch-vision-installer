"""Component release metadata must reuse status-owned published versions."""
from __future__ import annotations

from pathlib import Path
import importlib.util
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "switch_vision_installer" / "app"

fake_installer = types.ModuleType("installer")
fake_installer.INSTALLER_VERSION = "2.1.69"
fake_installer.normalise_version = lambda v: str(v or "").strip().lstrip("v")
sys.modules["installer"] = fake_installer
sys.modules["repository_setup"] = types.ModuleType("repository_setup")
module_spec = importlib.util.spec_from_file_location("component_manager_2169", APP / "component_manager.py")
manager = importlib.util.module_from_spec(module_spec)
assert module_spec and module_spec.loader
sys.modules[module_spec.name] = manager
module_spec.loader.exec_module(manager)

by_id = {spec.component_id: spec for spec in manager.COMPONENTS}
manager.resolve_repository = lambda spec: spec.repositories[0]
version_calls = []
manager._remote_version = lambda spec: version_calls.append(spec.component_id) or "SHOULD-NOT-FETCH"
oci_calls = []
manager._oci_image_metadata = lambda spec, version: (
    oci_calls.append((spec.component_id, version))
    or {
        "public_release_version": version,
        "public_release_published_at": "2026-10-20T00:00:00Z",
        "public_release_url": "https://example.invalid/oci",
        "public_release_kind": "oci_image",
    }
)
github_calls = []
def github(url):
    github_calls.append(url)
    if url.endswith("/commits/main"):
        return {
            "commit": {"committer": {"date": "2026-10-20T00:00:00Z"}},
            "html_url": "https://example.invalid/commit",
        }
    if url.endswith("/releases/latest"):
        return {"tag_name": "v1.0.0", "published_at": "2026-10-20T00:00:00Z",
                "html_url": "https://example.invalid/release"}
    raise AssertionError(f"Unexpected URL: {url}")
manager._github_request = github

versions = {
    "core": "2.8.7",
    "discovery": "3.0.90",
    "snmp2mqtt": "1.0.11",
    "unifi2mqtt": "4.0.8",
    "installer": "2.1.69",
}
# This mirrors the actual status snapshot after its own latest-version requests.
def status():
    return {"components": [
        {"id": spec.component_id, "latest_version": versions[spec.component_id]}
        for spec in manager.COMPONENTS
    ]}
manager.component_status = status
first = manager.component_status_with_releases()
assert version_calls == [], f"Second published-version requests: {version_calls}"
assert oci_calls == [("discovery", "3.0.90"), ("snmp2mqtt", "1.0.11")]
assert len(github_calls) == 3
assert all(row["release_metadata_error"] is None for row in first["components"])
assert next(row for row in first["components"] if row["id"] == "installer")["public_release_version"] == "2.1.69"

# The same published version may reuse cached presentation metadata.
second = manager.component_status_with_releases()
assert second == first
assert len(oci_calls) == 2
assert len(github_calls) == 3
assert version_calls == []

# A newly observed published version must never inherit an earlier OCI or
# repository-current result even within the presentation-cache lifetime.
versions["discovery"] = "3.0.91"
versions["installer"] = "2.1.70"
third = manager.component_status_with_releases()
assert oci_calls[-1] == ("discovery", "3.0.91")
assert len(oci_calls) == 3
assert len(github_calls) == 4
assert next(row for row in third["components"] if row["id"] == "installer")["public_release_version"] == "2.1.70"
assert version_calls == []

# An unavailable version fails closed instead of re-fetching a different
# public version behind the original status snapshot.
versions["snmp2mqtt"] = None
fourth = manager.component_status_with_releases()
unavailable = next(row for row in fourth["components"] if row["id"] == "snmp2mqtt")
assert unavailable["public_release_version"] is None
assert unavailable["release_metadata_error"].startswith("RuntimeError:")
assert len(oci_calls) == 3
assert version_calls == []

# Standalone call sites (without a status snapshot) still resolve for
# themselves; this does not change update/install version policy.
manager.clear_cache()
direct = manager._public_release_metadata(by_id["discovery"])
assert version_calls == ["discovery"]
assert direct["public_release_version"] == "SHOULD-NOT-FETCH"

print("Installer 2.1.69 status-owned metadata and error/cache regression: PASS")
