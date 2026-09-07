from __future__ import annotations

from pathlib import Path
import importlib.util
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "switch_vision_installer" / "app"

fake_installer = types.ModuleType("installer")
fake_installer.INSTALLER_VERSION = "2.1.36"
fake_installer.normalise_version = lambda value: str(value or "").strip().lstrip("v")
fake_installer.COMPONENT_DIR = Path("/tmp/no-component")
fake_installer.installed_version = lambda: "2.1.36"
fake_installer.load_options = lambda: {"allow_prerelease": False}
fake_installer.discovery_status = lambda: {"installed": True, "version": "2.3.46", "state": "started", "slug": "discovery"}
fake_installer.snmp2mqtt_status = lambda: {"installed": True, "version": "0.9.18", "state": "started", "slug": "snmp"}
fake_installer.unifi2mqtt_status = lambda: {"installed": False, "version": None, "state": "not_installed", "slug": "unifi"}
sys.modules["installer"] = fake_installer

fake_repo = types.ModuleType("repository_setup")
sys.modules["repository_setup"] = fake_repo

module_spec = importlib.util.spec_from_file_location("component_manager", APP / "component_manager.py")
module = importlib.util.module_from_spec(module_spec)
assert module_spec and module_spec.loader
sys.modules["component_manager"] = module
module_spec.loader.exec_module(module)

by_id = {item.component_id: item for item in module.COMPONENTS}
assert by_id["core"].publication_authority == "github_release"
assert by_id["unifi2mqtt"].publication_authority == "github_release"
assert by_id["discovery"].publication_authority == "oci_image"
assert by_id["discovery"].oci_image == "zemerdon/switch-vision-discovery"
assert by_id["snmp2mqtt"].publication_authority == "oci_image"
assert by_id["installer"].publication_authority == "repository_current"

module.resolve_repository = lambda spec: spec.repositories[0]
module._remote_version = lambda spec: {
    "discovery": "2.3.46",
    "snmp2mqtt": "0.9.18",
    "installer": "2.1.36",
}.get(spec.component_id, "")
module._oci_token = lambda image: f"token-for-{image}"
module._oci_amd64_manifest = lambda image, version, token: {
    "config": {"digest": f"sha256:{image.rsplit('/', 1)[-1]}-{version}"}
}
oci_calls = []
def oci_request(image, path, token, accept=None):
    oci_calls.append((image, path, token, accept))
    return {
        "created": "2026-09-07T17:07:00Z",
        "config": {"Labels": {"org.opencontainers.image.revision": "source-sha"}},
    }
module._oci_request = oci_request
module._github_request = lambda _url: (_ for _ in ()).throw(AssertionError("OCI metadata must not use GitHub Releases"))

for component_id, version in (("discovery", "2.3.46"), ("snmp2mqtt", "0.9.18")):
    module.clear_cache()
    result = module._public_release_metadata(by_id[component_id])
    assert result["public_release_kind"] == "oci_image"
    assert result["public_release_version"] == version
    assert result["public_release_published_at"] == "2026-09-07T17:07:00Z"
    assert result["release_metadata_error"] is None

assert all("blobs/sha256:" in path for _, path, _, _ in oci_calls)

repository_calls = []
def repository_current(url):
    repository_calls.append(url)
    assert url == "https://api.github.com/repos/zemerdon/switch-vision-installer/commits/main"
    return {
        "commit": {"committer": {"date": "2026-09-07T17:08:00Z"}},
        "html_url": "https://github.com/zemerdon/switch-vision-installer/commit/current",
    }
module._github_request = repository_current
module.clear_cache()
installer = module._public_release_metadata(by_id["installer"])
assert installer == {
    "public_release_version": "2.1.36",
    "public_release_published_at": "2026-09-07T17:08:00Z",
    "public_release_url": "https://github.com/zemerdon/switch-vision-installer/commit/current",
    "public_release_kind": "repository_current",
    "release_metadata_error": None,
}
assert len(repository_calls) == 1

ui = (ROOT / "switch_vision_installer" / "www" / "component-manager.js").read_text(encoding="utf-8")
assert "Public OCI image" in ui
assert "Repository current" in ui
assert "Latest public" in ui

print("Installer v2.1.36 publication-authority regression: PASS")
