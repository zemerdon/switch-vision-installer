from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath
from typing import Any, Callable
import hashlib
import json
import os
import shutil
import tempfile
import urllib.request
import urllib.error
import zipfile
import re

INSTALLER_VERSION = "1.9.0"
OPTIONS_PATH = Path(os.environ.get("SV_INSTALLER_OPTIONS", "/data/options.json"))
STATE_PATH = Path(os.environ.get("SV_INSTALLER_STATE", "/data/state.json"))
WORK_DIR = Path(os.environ.get("SV_INSTALLER_WORK", "/data/work"))
BACKUP_DIR = Path(os.environ.get("SV_INSTALLER_BACKUPS", "/share/switch-vision-backups"))
LEGACY_BACKUP_DIR = Path("/share/switch_vision/installer_backups")
HA_CONFIG = Path("/homeassistant")
ADDONS_DIR = Path("/addons")

COMPONENT_DIR = HA_CONFIG / "custom_components" / "switch_vision"
FRONTEND_DIR = HA_CONFIG / "www" / "switch-vision"
DISCOVERY_DIR = ADDONS_DIR / "switch_vision_discovery"
SNMP2MQTT_DIR = ADDONS_DIR / "switch_vision_snmp2mqtt"
SHARE_DIR = Path("/share")
GENERATED_SNMP2MQTT_YAML = SHARE_DIR / "switch_vision" / "generated-snmp2mqtt.yaml"

FRONTEND_FOLDERS = ("calibration", "css", "faceplates", "js", "layouts", "logos")
BUNDLED_ASSET_NAMES = {
    "logos": {"sv-logo.png", "cisco.svg", "juniper.svg", "1984-cisco-logo.svg", "1996-cisco-logo.svg", "2016-cisco-logo.svg", "README.txt"},
    "faceplates": {"sv-dark.png", "sv-light.png", "README.txt"},
}
Progress = Callable[[str, int], None]

SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")

def supervisor_request(path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if not SUPERVISOR_TOKEN:
        raise RuntimeError("Supervisor API token is unavailable.")
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"http://supervisor{path}",
        method=method,
        data=data,
        headers={
            "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)

def find_discovery_slug(include_store: bool = False) -> str:
    addon = _find_addon(
        lambda slug, name: (
            slug.endswith("switch_vision_discovery")
            or "switch-vision-discovery" in slug
            or name == "switch vision discovery"
        ),
        include_store=include_store,
    )
    if addon:
        return str(addon.get("slug", ""))
    raise RuntimeError("Switch Vision Discovery add-on was not found by Supervisor.")

def get_discovery_options() -> dict[str, Any] | None:
    try:
        slug = find_discovery_slug()
        info = supervisor_request(f"/addons/{slug}/info")
        options = info.get("data", {}).get("options")
        return options if isinstance(options, dict) else None
    except Exception:
        return None

def set_discovery_options(options: dict[str, Any]) -> None:
    slug = find_discovery_slug()
    supervisor_request(f"/addons/{slug}/options", method="POST", payload={"options": options})

def configured_switch_count(options: dict[str, Any] | None) -> int:
    if not isinstance(options, dict):
        return 0
    for key in ("switches", "devices", "targets"):
        value = options.get(key)
        if isinstance(value, list):
            return len(value)
    return 0


def _find_addon(predicate: Callable[[str, str], bool], include_store: bool = False) -> dict[str, Any] | None:
    endpoints = ["/addons"]
    if include_store:
        endpoints.append("/store")
    for endpoint in endpoints:
        try:
            payload = supervisor_request(endpoint)
        except Exception:
            continue
        data = payload.get("data", {})
        candidates = data.get("addons", []) if isinstance(data, dict) else []
        if not isinstance(candidates, list):
            continue
        for addon in candidates:
            if not isinstance(addon, dict):
                continue
            slug = str(addon.get("slug", ""))
            name = str(addon.get("name", ""))
            if predicate(slug.lower(), name.lower()):
                return addon
    return None


def discovery_status() -> dict[str, Any]:
    installed_addon = _find_addon(
        lambda slug, name: (
            slug.endswith("switch_vision_discovery")
            or "switch-vision-discovery" in slug
            or name == "switch vision discovery"
        ),
        include_store=False,
    )
    store_addon = _find_addon(
        lambda slug, name: (
            slug.endswith("switch_vision_discovery")
            or "switch-vision-discovery" in slug
            or name == "switch vision discovery"
        ),
        include_store=True,
    )
    if installed_addon:
        slug = str(installed_addon.get("slug", ""))
        try:
            info_payload = supervisor_request(f"/addons/{slug}/info")
            info = info_payload.get("data", {})
        except Exception:
            info = installed_addon
        return {
            "files_present": DISCOVERY_DIR.is_dir(),
            "available": True,
            "installed": True,
            "slug": slug,
            "version": info.get("version") or info.get("version_latest") or installed_addon.get("version"),
            "state": info.get("state") or installed_addon.get("state") or "unknown",
            "ingress_entry": info.get("ingress_entry") or installed_addon.get("ingress_entry"),
            "webui": info.get("webui") or installed_addon.get("webui"),
        }
    return {
        "files_present": DISCOVERY_DIR.is_dir(),
        "available": bool(store_addon) or DISCOVERY_DIR.is_dir(),
        "installed": False,
        "slug": str(store_addon.get("slug", "")) if store_addon else None,
        "version": store_addon.get("version") if store_addon else None,
        "state": "not_installed",
        "ingress_entry": None,
        "webui": None,
    }

def find_snmp2mqtt_slug(include_store: bool = False) -> str:
    addon = _find_addon(
        lambda slug, name: (
            "switch_vision_snmp2mqtt" in slug
            or "switch-vision-snmp2mqtt" in slug
            or name == "switch vision snmp2mqtt"
            or ("switch vision" in name and "snmp2mqtt" in name)
        ),
        include_store=include_store,
    )
    if addon:
        return str(addon.get("slug", ""))
    raise RuntimeError("Switch Vision SNMP2MQTT add-on was not found by Supervisor.")

def get_snmp2mqtt_info() -> dict[str, Any] | None:
    try:
        slug = find_snmp2mqtt_slug()
        info = supervisor_request(f"/addons/{slug}/info")
        data = info.get("data", {})
        return data if isinstance(data, dict) else None
    except Exception:
        return None

def get_snmp2mqtt_options() -> dict[str, Any] | None:
    info = get_snmp2mqtt_info()
    options = info.get("options") if isinstance(info, dict) else None
    return options if isinstance(options, dict) else None

def set_snmp2mqtt_options(options: dict[str, Any]) -> None:
    slug = find_snmp2mqtt_slug()
    supervisor_request(f"/addons/{slug}/options", method="POST", payload={"options": options})

def snmp2mqtt_status() -> dict[str, Any]:
    installed_addon = _find_addon(
        lambda slug, name: (
            "switch_vision_snmp2mqtt" in slug
            or "switch-vision-snmp2mqtt" in slug
            or name == "switch vision snmp2mqtt"
            or ("switch vision" in name and "snmp2mqtt" in name)
        ),
        include_store=False,
    )
    store_addon = _find_addon(
        lambda slug, name: (
            "switch_vision_snmp2mqtt" in slug
            or "switch-vision-snmp2mqtt" in slug
            or name == "switch vision snmp2mqtt"
            or ("switch vision" in name and "snmp2mqtt" in name)
        ),
        include_store=True,
    )
    if installed_addon:
        slug = str(installed_addon.get("slug", ""))
        try:
            info_payload = supervisor_request(f"/addons/{slug}/info")
            info = info_payload.get("data", {})
        except Exception:
            info = installed_addon
        return {
            "present": SNMP2MQTT_DIR.is_dir(),
            "available": True,
            "installed": True,
            "slug": slug,
            "version": info.get("version") or info.get("version_latest") or installed_addon.get("version"),
            "state": info.get("state") or installed_addon.get("state") or "unknown",
            "generated_yaml": GENERATED_SNMP2MQTT_YAML.is_file(),
        }
    return {
        "present": SNMP2MQTT_DIR.is_dir(),
        "available": bool(store_addon) or SNMP2MQTT_DIR.is_dir(),
        "installed": False,
        "slug": str(store_addon.get("slug", "")) if store_addon else None,
        "version": store_addon.get("version") or store_addon.get("version_latest") if store_addon else None,
        "state": "not_installed",
        "generated_yaml": GENERATED_SNMP2MQTT_YAML.is_file(),
        "ingress_entry": None,
        "webui": None,
    }


def reload_addon_store() -> None:
    errors: list[str] = []
    for endpoint in ("/addons/reload", "/store/reload"):
        try:
            supervisor_request(endpoint, method="POST")
        except Exception as exc:
            errors.append(f"{endpoint}: {exc}")
    if len(errors) == 2:
        raise RuntimeError("Unable to reload Home Assistant add-on information: " + "; ".join(errors))


def install_supervisor_addon(kind: str) -> dict[str, Any]:
    reload_addon_store()
    if kind == "discovery":
        slug = find_discovery_slug(include_store=True)
    elif kind == "snmp2mqtt":
        slug = find_snmp2mqtt_slug(include_store=True)
    else:
        raise RuntimeError(f"Unsupported add-on kind: {kind}")
    try:
        result = supervisor_request(
            f"/store/addons/{slug}/install",
            method="POST",
            payload={"background": False},
        )
    except Exception:
        result = supervisor_request(f"/addons/{slug}/install", method="POST")
    return {"slug": slug, "supervisor": result}

def find_release_snmp2mqtt_dir(root: Path) -> Path | None:
    candidates = [
        root / "addons" / "switch_vision_snmp2mqtt",
        root / "addons" / "switch-vision-snmp2mqtt-addon",
        root / "switch_vision_snmp2mqtt",
    ]
    return next((path for path in candidates if path.is_dir()), None)

@dataclass
class InstallResult:
    ok: bool
    version: str
    backup: str | None
    installed: list[str]
    unchanged: list[str]
    preserved: list[str]
    warnings: list[str]
    required_actions: list[str]
    checksum: str
    completed_at: str


def load_options() -> dict[str, Any]:
    defaults = {
        "release_api_url": "https://api.github.com/repos/zemerdon/switch-vision-releases/releases/latest",
        "release_asset_pattern": "switch-vision-*.zip",
        "preserve_custom_assets": True,
        "create_backup": True,
        "allow_prerelease": False,
        "backup_retention": 5,
    }
    if OPTIONS_PATH.exists():
        try:
            defaults.update(json.loads(OPTIONS_PATH.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass
    return defaults


def request_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": f"Switch-Vision-Installer/{INSTALLER_VERSION}"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def latest_release() -> dict[str, Any]:
    options = load_options()
    payload = request_json(str(options["release_api_url"]))
    if payload.get("prerelease") and not options.get("allow_prerelease"):
        raise RuntimeError("Latest GitHub release is marked as a prerelease.")
    pattern = str(options.get("release_asset_pattern") or "switch-vision-*.zip")
    assets = [a for a in payload.get("assets", []) if fnmatch(str(a.get("name", "")), pattern)]
    assets = [a for a in assets if "source" not in str(a.get("name", "")).lower()]
    if not assets:
        raise RuntimeError(f"No installable release asset matched {pattern!r}.")
    asset = sorted(assets, key=lambda a: int(a.get("size", 0)), reverse=True)[0]
    version = str(payload.get("tag_name") or payload.get("name") or "").strip().lstrip("v")
    checksum_assets = [a for a in payload.get("assets", []) if str(a.get("name", "")).lower() in {"sha256sums.txt", "sha256sum.txt", "checksums.txt"} or str(a.get("name", "")).lower().endswith((".sha256", ".sha256sum"))]
    checksum_asset = checksum_assets[0] if checksum_assets else None
    return {
        "version": version, "name": payload.get("name") or payload.get("tag_name"),
        "published_at": payload.get("published_at"), "asset_name": asset.get("name"),
        "asset_url": asset.get("browser_download_url"), "asset_size": asset.get("size"),
        "html_url": payload.get("html_url"),
        "checksum_asset_name": checksum_asset.get("name") if checksum_asset else None,
        "checksum_asset_url": checksum_asset.get("browser_download_url") if checksum_asset else None,
    }



def download_file(url: str, destination: Path, timeout: int = 120) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": f"Switch-Vision-Installer/{INSTALLER_VERSION}"})
    with urllib.request.urlopen(request, timeout=timeout) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def expected_release_checksum(release: dict[str, Any], work_dir: Path) -> str | None:
    url = release.get("checksum_asset_url")
    if not url:
        return None
    checksum_file = work_dir / str(release.get("checksum_asset_name") or "SHA256SUMS.txt")
    download_file(str(url), checksum_file, timeout=30)
    text = checksum_file.read_text(encoding="utf-8", errors="replace")
    asset_name = str(release.get("asset_name") or "")
    for line in text.splitlines():
        if asset_name and asset_name in line:
            match = re.search(r"\b([a-fA-F0-9]{64})\b", line)
            if match:
                return match.group(1).lower()
    if str(release.get("checksum_asset_name", "")).lower().endswith((".sha256", ".sha256sum")):
        match = re.search(r"\b([a-fA-F0-9]{64})\b", text)
        if match:
            return match.group(1).lower()
    raise RuntimeError(f"Checksum file does not contain an entry for {asset_name}.")


def path_writable(path: Path) -> bool:
    probe_parent = path if path.exists() and path.is_dir() else path.parent
    try:
        probe_parent.mkdir(parents=True, exist_ok=True)
        probe = probe_parent / f".sv-installer-write-test-{os.getpid()}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def preflight_checks(release: dict[str, Any] | None = None) -> dict[str, Any]:
    release = release or latest_release()
    checks: list[dict[str, Any]] = []
    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
    add("Supervisor API", bool(SUPERVISOR_TOKEN), "Supervisor token available" if SUPERVISOR_TOKEN else "Supervisor token unavailable")
    if SUPERVISOR_TOKEN:
        try:
            supervisor_request("/info")
            checks[-1] = {"name": "Supervisor API", "ok": True, "detail": "Supervisor API responded successfully"}
        except Exception as exc:
            checks[-1] = {"name": "Supervisor API", "ok": False, "detail": str(exc)}
    for label, path in (("Home Assistant configuration", HA_CONFIG), ("Local add-ons", ADDONS_DIR), ("Shared storage", SHARE_DIR), ("Installer work directory", WORK_DIR)):
        add(f"Writable: {label}", path_writable(path), str(path))
    usage = shutil.disk_usage(SHARE_DIR if SHARE_DIR.exists() else Path("/"))
    asset_size = int(release.get("asset_size") or 0)
    required = max(128 * 1024 * 1024, asset_size * 4)
    add("Available disk space", usage.free >= required, f"{usage.free // (1024*1024)} MB free; {required // (1024*1024)} MB required")
    add("Release asset", bool(release.get("asset_url") and release.get("asset_name")), str(release.get("asset_name") or "Missing"))
    add("Published checksum", bool(release.get("checksum_asset_url")), str(release.get("checksum_asset_name") or "No checksum asset published; computed SHA-256 only"))
    blocking = [c for c in checks if not c["ok"] and c["name"] != "Published checksum"]
    return {"ok": not blocking, "checks": checks, "release": release}


def installed_version() -> str | None:
    manifest = COMPONENT_DIR / "manifest.json"
    if manifest.exists():
        try:
            return str(json.loads(manifest.read_text(encoding="utf-8")).get("version") or "") or None
        except (OSError, json.JSONDecodeError):
            pass
    config = DISCOVERY_DIR / "config.yaml"
    if config.exists():
        for line in config.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("version:"):
                return line.split(":", 1)[1].strip().strip('"\'')
    return None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_digest(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(path.name.encode()); digest.update(path.read_bytes()); return digest.hexdigest()
    for file in sorted(p for p in path.rglob("*") if p.is_file()):
        digest.update(file.relative_to(path).as_posix().encode("utf-8")); digest.update(b"\0")
        with file.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def safe_extract(archive: Path, destination: Path) -> None:
    destination = destination.resolve()
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            member = PurePosixPath(info.filename)
            if member.is_absolute() or ".." in member.parts:
                raise RuntimeError(f"Unsafe archive member: {info.filename}")
            target = (destination / Path(*member.parts)).resolve()
            if destination not in target.parents and target != destination:
                raise RuntimeError(f"Archive path escapes staging: {info.filename}")
        zf.extractall(destination)


def find_release_root(extracted: Path) -> Path:
    candidates = [extracted, *(p for p in extracted.iterdir() if p.is_dir())]
    for candidate in candidates:
        if (candidate / "custom_components" / "switch_vision").is_dir() and (candidate / "addons" / "switch_vision_discovery").is_dir():
            return candidate
    raise RuntimeError("Release ZIP does not contain the expected Switch Vision folders.")


def copy_backup(source: Path, root: Path, label: str) -> None:
    if source.exists():
        shutil.copytree(source, root / label, dirs_exist_ok=True)


def backup_contents(path: Path) -> list[str]:
    entries = []
    if (path / "custom_components/switch_vision").is_dir(): entries.append("Custom component")
    if (path / "www/switch-vision").is_dir(): entries.append("Dashboard frontend")
    if (path / "addons/switch_vision_discovery").is_dir(): entries.append("Discovery add-on")
    if (path / "addons/switch_vision_snmp2mqtt").is_dir(): entries.append("SNMP2MQTT add-on")
    if (path / ".storage/switch_vision_calibrations").is_file(): entries.append("Calibration storage")
    if (path / "discovery-options.json").is_file(): entries.append("Discovery configuration")
    if (path / "snmp2mqtt-options.json").is_file(): entries.append("SNMP2MQTT configuration")
    if (path / "share/switch_vision/generated-snmp2mqtt.yaml").is_file(): entries.append("Generated SNMP2MQTT YAML")
    return entries



def backup_file_hashes(path: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for file in sorted(p for p in path.rglob("*") if p.is_file() and p.name not in {"backup.json", "backup-manifest.json"}):
        hashes[file.relative_to(path).as_posix()] = sha256(file)
    return hashes


def validate_backup(path: Path) -> dict[str, Any]:
    manifest_path = path / "backup-manifest.json"
    if not manifest_path.is_file():
        # Upgrade older installer backups in place so v1.8.3 and earlier remain restorable.
        manifest = {
            "schema": 1,
            "installer_version": "legacy",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "installed_version": None,
            "files": backup_file_hashes(path),
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = manifest.get("files")
    if not isinstance(expected, dict):
        raise RuntimeError("Backup validation failed: manifest file list is invalid.")
    missing: list[str] = []
    mismatched: list[str] = []
    for relative, digest in expected.items():
        file = path / relative
        if not file.is_file():
            missing.append(relative)
        elif sha256(file) != digest:
            mismatched.append(relative)
    if missing or mismatched:
        detail = []
        if missing: detail.append("missing: " + ", ".join(missing[:10]))
        if mismatched: detail.append("checksum mismatch: " + ", ".join(mismatched[:10]))
        raise RuntimeError("Backup validation failed (" + "; ".join(detail) + ").")
    return {"ok": True, "file_count": len(expected), "manifest": manifest}


def prune_backups() -> dict[str, Any]:
    keep = max(1, int(load_options().get("backup_retention", 5)))
    paths = sorted((p for p in BACKUP_DIR.iterdir() if p.is_dir()), reverse=True)
    removed: list[str] = []
    for old in paths[keep:]:
        removed.append(old.name)
        shutil.rmtree(old, ignore_errors=True)
    return {"ok": True, "retention": keep, "removed": removed, "remaining": min(len(paths), keep)}


def apply_backup_retention() -> dict[str, Any]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    result = prune_backups()
    result["backup_path"] = str(BACKUP_DIR)
    return result


def create_backup(force: bool = False) -> Path | None:
    if not force and not load_options().get("create_backup", True): return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    target = BACKUP_DIR / f"switch-vision-{stamp}"
    target.mkdir(parents=True, exist_ok=False)
    copy_backup(COMPONENT_DIR, target, "custom_components/switch_vision")
    copy_backup(FRONTEND_DIR, target, "www/switch-vision")
    copy_backup(DISCOVERY_DIR, target, "addons/switch_vision_discovery")
    copy_backup(SNMP2MQTT_DIR, target, "addons/switch_vision_snmp2mqtt")
    discovery_options = get_discovery_options()
    if discovery_options is not None:
        (target / "discovery-options.json").write_text(json.dumps(discovery_options, indent=2) + "\n", encoding="utf-8")
    snmp2mqtt_options = get_snmp2mqtt_options()
    if snmp2mqtt_options is not None:
        (target / "snmp2mqtt-options.json").write_text(json.dumps(snmp2mqtt_options, indent=2) + "\n", encoding="utf-8")
    if GENERATED_SNMP2MQTT_YAML.is_file():
        yaml_target = target / "share" / "switch_vision" / GENERATED_SNMP2MQTT_YAML.name
        yaml_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(GENERATED_SNMP2MQTT_YAML, yaml_target)
    storage = HA_CONFIG / ".storage" / "switch_vision_calibrations"
    if storage.exists():
        (target / ".storage").mkdir(parents=True, exist_ok=True); shutil.copy2(storage, target / ".storage" / storage.name)
    meta = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "installed_version": installed_version(),
        "contents": backup_contents(target),
        "discovery_configuration_saved": discovery_options is not None,
        "configured_switches": configured_switch_count(discovery_options),
        "snmp2mqtt_configuration_saved": snmp2mqtt_options is not None,
        "snmp2mqtt_generated_yaml_saved": GENERATED_SNMP2MQTT_YAML.is_file(),
    }
    (target / "backup.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "schema": 1,
        "installer_version": INSTALLER_VERSION,
        "created_at": meta["created_at"],
        "installed_version": meta["installed_version"],
        "files": backup_file_hashes(target),
    }
    (target / "backup-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    validate_backup(target)
    prune_backups()
    return target


def create_manual_backup(progress: Progress | None = None) -> dict[str, Any]:
    if progress: progress("Collecting Switch Vision files and settings…", 15)
    target = create_backup(force=True)
    if target is None:
        raise RuntimeError("Backup creation did not return a backup path.")
    if progress: progress("Validating backup checksums…", 80)
    validation = validate_backup(target)
    meta: dict[str, Any] = {}
    try:
        meta = json.loads((target / "backup.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    if progress: progress("Backup created and verified.", 100)
    return {
        "ok": True,
        "backup_created": True,
        "backup": target.name,
        "backup_path": str(target),
        "verified": True,
        "file_count": validation.get("file_count", 0),
        "version": meta.get("installed_version"),
        "contents": meta.get("contents") or backup_contents(target),
        "configured_switches": int(meta.get("configured_switches") or 0),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


def validate_named_backup(name: str, progress: Progress | None = None) -> dict[str, Any]:
    backup = _safe_backup_path(name)
    if progress: progress(f"Validating {name}…", 25)
    validation = validate_backup(backup)
    if progress: progress("Backup validation completed.", 100)
    return {
        "ok": True,
        "backup_validated": True,
        "backup": name,
        "verified": True,
        "file_count": validation.get("file_count", 0),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


def _backup_roots() -> list[Path]:
    roots = [BACKUP_DIR]
    if LEGACY_BACKUP_DIR != BACKUP_DIR and LEGACY_BACKUP_DIR.is_dir():
        roots.append(LEGACY_BACKUP_DIR)
    return roots


def list_backups() -> list[dict[str, Any]]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    result = []
    paths: list[Path] = []
    for root in _backup_roots():
        paths.extend(p for p in root.iterdir() if p.is_dir())
    for path in sorted(paths, key=lambda p: p.name, reverse=True):
        meta: dict[str, Any] = {}
        try: meta = json.loads((path / "backup.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError): pass
        result.append({
            "name": path.name,
            "path": str(path),
            "legacy_location": path.parent == LEGACY_BACKUP_DIR,
            "created_at": meta.get("created_at"),
            "version": meta.get("installed_version"),
            "contents": meta.get("contents") or backup_contents(path),
            "discovery_configuration_saved": bool(meta.get("discovery_configuration_saved")),
            "configured_switches": int(meta.get("configured_switches") or 0),
            "snmp2mqtt_configuration_saved": bool(meta.get("snmp2mqtt_configuration_saved")),
            "snmp2mqtt_generated_yaml_saved": bool(meta.get("snmp2mqtt_generated_yaml_saved")),
        })
    return result


def _safe_backup_path(name: str) -> Path:
    if not name or Path(name).name != name:
        raise RuntimeError("Invalid backup name.")
    for root in _backup_roots():
        path = (root / name).resolve()
        resolved_root = root.resolve()
        if resolved_root in path.parents and path.is_dir():
            return path
    raise RuntimeError("Backup not found.")


def delete_backup(name: str) -> dict[str, Any]:
    path = _safe_backup_path(name); shutil.rmtree(path)
    return {"ok": True, "deleted": name}


def replace_tree(source: Path, destination: Path) -> None:
    if destination.exists(): shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True); shutil.copytree(source, destination)


def restore_backup(name: str, progress: Progress | None = None) -> dict[str, Any]:
    backup = _safe_backup_path(name)
    validate_backup(backup)
    restored: list[str] = []
    mappings = [
        (backup / "custom_components/switch_vision", COMPONENT_DIR, "Custom component"),
        (backup / "www/switch-vision", FRONTEND_DIR, "Dashboard frontend"),
        (backup / "addons/switch_vision_discovery", DISCOVERY_DIR, "Discovery add-on"),
        (backup / "addons/switch_vision_snmp2mqtt", SNMP2MQTT_DIR, "SNMP2MQTT add-on"),
    ]
    for idx, (source, destination, label) in enumerate(mappings, start=1):
        if source.is_dir():
            if progress: progress(f"Restoring {label}…", 20 + idx * 18)
            replace_tree(source, destination); restored.append(label)
    discovery_options_file = backup / "discovery-options.json"
    if discovery_options_file.is_file():
        options = json.loads(discovery_options_file.read_text(encoding="utf-8"))
        if isinstance(options, dict):
            if progress: progress("Restoring Discovery configuration…", 82)
            set_discovery_options(options)
            restored.append(f"Discovery configuration ({configured_switch_count(options)} switches)")
    snmp2mqtt_options_file = backup / "snmp2mqtt-options.json"
    if snmp2mqtt_options_file.is_file():
        options = json.loads(snmp2mqtt_options_file.read_text(encoding="utf-8"))
        if isinstance(options, dict):
            if progress: progress("Restoring SNMP2MQTT configuration…", 86)
            set_snmp2mqtt_options(options)
            restored.append("SNMP2MQTT configuration")
    generated_yaml = backup / "share" / "switch_vision" / "generated-snmp2mqtt.yaml"
    if generated_yaml.is_file():
        GENERATED_SNMP2MQTT_YAML.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(generated_yaml, GENERATED_SNMP2MQTT_YAML)
        restored.append("Generated SNMP2MQTT YAML")
    storage = backup / ".storage" / "switch_vision_calibrations"
    if storage.is_file():
        target = HA_CONFIG / ".storage" / storage.name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(storage, target); restored.append("Calibration storage")
    if not restored: raise RuntimeError("The selected backup contains no restorable Switch Vision components.")
    actions = []
    if "Custom component" in restored: actions.append("Restart Home Assistant Core")
    if "Discovery add-on" in restored: actions.extend(["Rebuild or reinstall Switch Vision Discovery", "Start Switch Vision Discovery"])
    if "SNMP2MQTT add-on" in restored: actions.extend(["Rebuild or reinstall Switch Vision SNMP2MQTT", "Start Switch Vision SNMP2MQTT"])
    if "SNMP2MQTT configuration" in restored or "Generated SNMP2MQTT YAML" in restored: actions.append("Restart Switch Vision SNMP2MQTT")
    if "Dashboard frontend" in restored: actions.append("Hard-refresh the browser")
    return {"ok": True, "backup": name, "restored": restored, "required_actions": actions, "completed_at": datetime.now(timezone.utc).isoformat()}


def collect_custom_assets() -> dict[str, dict[str, bytes]]:
    if not load_options().get("preserve_custom_assets", True): return {}
    result: dict[str, dict[str, bytes]] = {}
    for folder in ("logos", "faceplates"):
        source = FRONTEND_DIR / folder
        if not source.is_dir(): continue
        bundled = BUNDLED_ASSET_NAMES.get(folder, set())
        custom = {path.name: path.read_bytes() for path in source.iterdir() if path.is_file() and path.name not in bundled}
        if custom: result[folder] = custom
    return result


def build_frontend_stage(root: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for folder in FRONTEND_FOLDERS:
        source = root / folder
        if source.is_dir(): shutil.copytree(source, target / folder)


def component_plan(root: Path) -> tuple[list[tuple[Path, Path, str]], list[str], list[str]]:
    with tempfile.TemporaryDirectory(dir=WORK_DIR) as td:
        frontend_stage = Path(td) / "frontend"
        build_frontend_stage(root, frontend_stage)
        mappings = [
            (root / "custom_components" / "switch_vision", COMPONENT_DIR, "Custom component"),
            (root / "addons" / "switch_vision_discovery", DISCOVERY_DIR, "Discovery add-on"),
            (frontend_stage, FRONTEND_DIR, "Dashboard frontend and visual assets"),
        ]
        release_snmp2mqtt = find_release_snmp2mqtt_dir(root)
        if release_snmp2mqtt is not None:
            mappings.append((release_snmp2mqtt, SNMP2MQTT_DIR, "SNMP2MQTT add-on"))
        # Frontend stage is temporary, so return copied source paths only from a persistent temp clone.
        persistent = WORK_DIR / "plan-frontend"
        if persistent.exists(): shutil.rmtree(persistent)
        shutil.copytree(frontend_stage, persistent)
        mappings = [(persistent if label == "Dashboard frontend and visual assets" else src, dst, label) for src, dst, label in mappings]
    changed = [(src, dst, label) for src, dst, label in mappings if tree_digest(src) != tree_digest(dst)]
    unchanged = [label for src, dst, label in mappings if tree_digest(src) == tree_digest(dst)]
    missing = [label for src, dst, label in mappings if not dst.exists()]
    return changed, unchanged, missing


def install_release(root: Path, version: str, checksum: str, progress: Progress | None = None) -> InstallResult:
    if progress: progress("Comparing installed components…", 48)
    changed, unchanged, _ = component_plan(root)
    backup = create_backup() if changed else None
    if backup is not None:
        validate_backup(backup)
    if progress: progress("Backup verified. Installing changed components…", 62)
    custom_assets = collect_custom_assets(); installed=[]; preserved=[]; warnings=[]
    preserved_snmp2mqtt_options = get_snmp2mqtt_options()
    try:
        for idx, (source, destination, label) in enumerate(changed, start=1):
            replace_tree(source, destination); installed.append(label)
            if progress: progress(f"Installed {label}…", 62 + idx * 7)
        if "Dashboard frontend and visual assets" in installed:
            for folder, files in custom_assets.items():
                target = FRONTEND_DIR / folder; target.mkdir(parents=True, exist_ok=True)
                for name, data in files.items():
                    path = target / name
                    if not path.exists(): path.write_bytes(data); preserved.append(f"{folder}/{name}")
                    else: warnings.append(f"Custom asset not restored because the release now provides {folder}/{name}")
        if "SNMP2MQTT add-on" in installed and preserved_snmp2mqtt_options is not None:
            try: set_snmp2mqtt_options(preserved_snmp2mqtt_options)
            except Exception as exc: warnings.append(f"SNMP2MQTT options could not be restored automatically: {exc}")
    except Exception as exc:
        rollback_note = ""
        if backup is not None:
            try:
                restore_backup(backup.name)
                rollback_note = " Previous files were restored from the verified backup."
            except Exception as rollback_exc:
                rollback_note = f" Automatic rollback also failed: {rollback_exc}"
        raise RuntimeError(f"Installation failed: {exc}.{rollback_note}") from exc
    if find_release_snmp2mqtt_dir(root) is None:
        warnings.append("The Switch Vision release does not contain an SNMP2MQTT add-on package; the existing add-on was left unchanged.")
    if not GENERATED_SNMP2MQTT_YAML.is_file():
        warnings.append("Generated SNMP2MQTT YAML was not found at /share/switch_vision/generated-snmp2mqtt.yaml.")
    actions=[]
    if "Custom component" in installed: actions.append("Restart Home Assistant Core")
    if "Discovery add-on" in installed: actions.extend(["Rebuild or reinstall Switch Vision Discovery", "Start Switch Vision Discovery", "Run Discovery"])
    if "SNMP2MQTT add-on" in installed: actions.extend(["Rebuild or reinstall Switch Vision SNMP2MQTT", "Restart Switch Vision SNMP2MQTT"])
    if "Dashboard frontend and visual assets" in installed: actions.append("Hard-refresh the browser if older frontend content remains")
    result = InstallResult(True, version, str(backup) if backup else None, installed, unchanged, preserved, warnings, actions, checksum, datetime.now(timezone.utc).isoformat())
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8")
    return result


def prepare_release(progress: Progress | None = None) -> tuple[dict[str, Any], Path, Path, str, bool]:
    if progress: progress("Checking the latest public release…", 5)
    release = latest_release()
    report = preflight_checks(release)
    if not report["ok"]:
        failed = "; ".join(c["name"] + ": " + c["detail"] for c in report["checks"] if not c["ok"] and c["name"] != "Published checksum")
        raise RuntimeError("Preflight checks failed: " + failed)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = Path(tempfile.mkdtemp(dir=WORK_DIR))
    archive = tmp_path / str(release["asset_name"])
    if progress: progress(f"Downloading {release['asset_name']}…", 18)
    download_file(str(release["asset_url"]), archive)
    if archive.stat().st_size <= 0:
        raise RuntimeError("Downloaded release archive is empty.")
    if progress: progress("Verifying checksum and archive structure…", 35)
    actual = sha256(archive)
    expected = expected_release_checksum(release, tmp_path)
    if expected and actual != expected:
        raise RuntimeError(f"Release checksum mismatch: expected {expected}, received {actual}.")
    extracted = tmp_path / "extracted"; extracted.mkdir()
    safe_extract(archive, extracted)
    root = find_release_root(extracted)
    return release, tmp_path, root, actual, bool(expected)


def dry_run(progress: Progress | None = None) -> dict[str, Any]:
    release, tmp_path, root, checksum, checksum_verified = prepare_release(progress)
    try:
        changed, unchanged, missing = component_plan(root)
        custom_assets = collect_custom_assets()
        plan = {
            "ok": True, "dry_run": True, "version": str(release["version"]),
            "asset": release["asset_name"], "checksum": checksum,
            "checksum_verified": checksum_verified,
            "would_change": [label for _,_,label in changed],
            "unchanged": unchanged, "missing": missing,
            "would_create_backup": bool(changed and load_options().get("create_backup", True)),
            "would_preserve": [f"{folder}/{name}" for folder, files in custom_assets.items() for name in files],
            "preflight": preflight_checks(release)["checks"],
            "message": "Dry run completed. No files or settings were changed.",
        }
        if progress: progress("Dry run completed. No changes were made.", 100)
        return plan
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)
        shutil.rmtree(WORK_DIR / "plan-frontend", ignore_errors=True)


def download_and_install(progress: Progress | None = None) -> InstallResult:
    release, tmp_path, root, checksum, _ = prepare_release(progress)
    try:
        result = install_release(root, str(release["version"]), checksum, progress)
        if progress: progress("Installation completed successfully.", 100)
        return result
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)
        shutil.rmtree(WORK_DIR / "plan-frontend", ignore_errors=True)


def status() -> dict[str, Any]:
    state = None
    if STATE_PATH.exists():
        try: state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError): pass
    discovery = discovery_status()
    snmp = snmp2mqtt_status()
    return {
        "installer_version": INSTALLER_VERSION,
        "installed_version": installed_version(),
        "component_present": COMPONENT_DIR.is_dir(),
        "frontend_present": FRONTEND_DIR.is_dir(),
        "discovery_present": bool(discovery.get("files_present")),
        "discovery_available": bool(discovery.get("available")),
        "discovery_installed": bool(discovery.get("installed")),
        "discovery_slug": discovery.get("slug"),
        "discovery_version": discovery.get("version"),
        "discovery_state": discovery.get("state"),
        "discovery_ingress_entry": discovery.get("ingress_entry"),
        "discovery_webui": discovery.get("webui"),
        "discovery_details_path": f"/config/app/{discovery.get('slug')}/info" if discovery.get("slug") else None,
        "snmp2mqtt_present": bool(snmp.get("present")),
        "snmp2mqtt_available": bool(snmp.get("available")),
        "snmp2mqtt_slug": snmp.get("slug"),
        "snmp2mqtt_installed": bool(snmp.get("installed")),
        "snmp2mqtt_version": snmp.get("version"),
        "snmp2mqtt_state": snmp.get("state"),
        "snmp2mqtt_ingress_entry": snmp.get("ingress_entry"),
        "snmp2mqtt_webui": snmp.get("webui"),
        "snmp2mqtt_details_path": f"/config/app/{snmp.get('slug')}/info" if snmp.get("slug") else None,
        "snmp2mqtt_generated_yaml": bool(snmp.get("generated_yaml")),
        "backup_path": str(BACKUP_DIR),
        "backup_retention": max(1, int(load_options().get("backup_retention", 5))),
        "last_result": state,
    }
