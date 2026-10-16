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
import stat
import tempfile
import threading
import time
import urllib.request
import urllib.error
import zipfile
import re
import sys

_MODULE_DIR = Path(__file__).resolve().parent
if str(_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(_MODULE_DIR))

import backup_manager as _backup_manager
import faceplate_history as _faceplate_history
import tree_transaction as _tree_transaction


INSTALLER_VERSION = "2.1.25"
OPTIONS_PATH = Path(os.environ.get("SV_INSTALLER_OPTIONS", "/data/options.json"))
STATE_PATH = Path(os.environ.get("SV_INSTALLER_STATE", "/data/state.json"))
WORK_DIR = Path(os.environ.get("SV_INSTALLER_WORK", "/data/work"))
BACKUP_DIR = Path("/data/switch-vision-backups")
BACKUP_POLICY_PATH = Path(
    os.environ.get("SV_INSTALLER_BACKUP_POLICY", "/data/backup-policy.json")
)
SHARED_BACKUP_DIR = Path("/share/switch-vision-backups")
LEGACY_BACKUP_DIR = Path("/share/switch_vision/installer_backups")
HA_CONFIG = Path("/homeassistant")
# Home Assistant Supervisor 2026.07 renamed the writable local app mapping
# from `addons` (/addons) to `local_apps` (/local_apps). The Installer uses
# the current mapping but still checks the legacy path during migration.
LOCAL_APPS_DIR = Path("/local_apps")
LEGACY_ADDONS_DIR = Path("/addons")
ADDONS_DIR = LOCAL_APPS_DIR

COMPONENT_DIR = HA_CONFIG / "custom_components" / "switch_vision"
FRONTEND_DIR = HA_CONFIG / "www" / "switch-vision"
DISCOVERY_DIR = LOCAL_APPS_DIR / "switch_vision_discovery"
LEGACY_DISCOVERY_DIR = LEGACY_ADDONS_DIR / "switch_vision_discovery"
SNMP2MQTT_DIR = LOCAL_APPS_DIR / "switch_vision_snmp2mqtt"
UNIFI2MQTT_DIR = LOCAL_APPS_DIR / "switch_vision_unifi2mqtt"
SHARE_DIR = Path("/share")
GENERATED_SNMP2MQTT_YAML = SHARE_DIR / "switch_vision" / "generated-snmp2mqtt.yaml"

FRONTEND_FOLDERS = ("calibration", "css", "faceplates", "faceplates-old", "js", "layouts", "logos")
BUNDLED_ASSET_NAMES = {
    "logos": {"sv-logo.png", "cisco.svg", "juniper.svg", "1984-cisco-logo.svg", "1996-cisco-logo.svg", "2016-cisco-logo.svg", "README.txt"},
    "faceplates": {"sv-dark.png", "sv-light.png", "README.txt"},
}
Progress = Callable[[str, int], None]

MAX_ARCHIVE_ENTRIES = 20_000
MAX_ARCHIVE_TOTAL_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_MEMBER_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_COMPRESSION_RATIO = 200.0

OFFICIAL_RELEASE_API_URL = (
    "https://api.github.com/repos/zemerdon/"
    "switch-vision-releases/releases/latest"
)
OFFICIAL_RELEASE_LATEST_URL = (
    "https://github.com/zemerdon/switch-vision-releases/releases/latest"
)
OFFICIAL_RELEASE_DOWNLOAD_BASE = (
    "https://github.com/zemerdon/switch-vision-releases/releases/download"
)
OFFICIAL_RELEASE_RAW_BASE = (
    "https://raw.githubusercontent.com/zemerdon/switch-vision-releases"
)

SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
_STORE_RELOAD_LOCK = threading.Lock()

def supervisor_request(
    path: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    *,
    timeout: float = 30.0,
) -> dict[str, Any]:
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
    try:
        request_timeout = max(1.0, min(float(timeout), 180.0))
        with urllib.request.urlopen(request, timeout=request_timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace").strip()
        except Exception:
            body = ""
        detail = ""
        if body:
            try:
                parsed = json.loads(body)
                detail = str(parsed.get("message") or parsed.get("error") or body)
            except Exception:
                detail = body
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(f"Supervisor API {method} {path} failed with HTTP {exc.code}{suffix}") from exc


def homeassistant_request(
    path: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> Any:
    """Call Home Assistant through the Supervisor API proxy."""
    clean = "/" + str(path or "").lstrip("/")
    return supervisor_request(f"/core/api{clean}", method=method, payload=payload)


def switch_vision_config_entry_status() -> dict[str, Any]:
    """Return the current Switch Vision Home Assistant config-entry state."""
    payload = homeassistant_request(
        "/config/config_entries/entry?domain=switch_vision"
    )
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        candidate = payload.get("data", payload)
        rows = candidate if isinstance(candidate, list) else []
    else:
        rows = []
    entries = [
        row
        for row in rows
        if isinstance(row, dict)
        and str(row.get("domain") or "").strip() == "switch_vision"
    ]
    entry = entries[0] if entries else {}
    return {
        "available": True,
        "present": bool(entries),
        "entry_id": str(entry.get("entry_id") or "") or None,
        "state": str(entry.get("state") or "") or None,
    }


def _switch_vision_flow_handler_unavailable(exc: Exception) -> bool:
    text = str(exc).lower()
    return "http 404" in text and "config_entries/flow" in text


def ensure_switch_vision_config_entry() -> dict[str, Any]:
    """Create the single Switch Vision config entry through HA's config flow."""
    if not COMPONENT_DIR.is_dir():
        return {
            "present": False,
            "created": False,
            "restart_required": False,
            "reason": "component_missing",
        }

    current = switch_vision_config_entry_status()
    if current["present"]:
        return {
            **current,
            "created": False,
            "restart_required": False,
        }

    try:
        start = homeassistant_request(
            "/config/config_entries/flow",
            method="POST",
            payload={"handler": "switch_vision"},
        )
    except Exception as exc:
        if _switch_vision_flow_handler_unavailable(exc):
            return {
                "present": False,
                "created": False,
                "restart_required": True,
                "reason": "flow_handler_unavailable",
            }
        raise

    if not isinstance(start, dict):
        raise RuntimeError("Home Assistant returned an invalid Switch Vision config-flow response.")

    flow_type = str(start.get("type") or "")
    if flow_type == "abort":
        reason = str(start.get("reason") or "")
        if reason not in {"already_configured", "single_instance_allowed"}:
            raise RuntimeError(f"Switch Vision config flow aborted unexpectedly: {reason or 'unknown'}")
    elif flow_type == "form":
        if str(start.get("step_id") or "") != "user":
            raise RuntimeError(
                "Switch Vision config flow returned an unexpected setup step: "
                + str(start.get("step_id") or "unknown")
            )
        flow_id = str(start.get("flow_id") or "").strip()
        if not flow_id:
            raise RuntimeError("Switch Vision config flow did not return a flow_id.")
        finish = homeassistant_request(
            f"/config/config_entries/flow/{flow_id}",
            method="POST",
            payload={},
        )
        if not isinstance(finish, dict):
            raise RuntimeError("Home Assistant returned an invalid Switch Vision config-flow completion.")
        finish_type = str(finish.get("type") or "")
        if finish_type == "abort":
            reason = str(finish.get("reason") or "")
            if reason not in {"already_configured", "single_instance_allowed"}:
                raise RuntimeError(
                    f"Switch Vision config flow aborted unexpectedly: {reason or 'unknown'}"
                )
        elif finish_type != "create_entry":
            raise RuntimeError(
                "Switch Vision config flow did not create the integration entry "
                f"(result={finish_type or 'unknown'})."
            )
    elif flow_type != "create_entry":
        raise RuntimeError(
            "Switch Vision config flow returned an unexpected result: "
            + (flow_type or "unknown")
        )

    verified = switch_vision_config_entry_status()
    if not verified["present"]:
        raise RuntimeError(
            "Home Assistant accepted the Switch Vision config flow but no config entry is present."
        )
    return {
        **verified,
        "created": True,
        "restart_required": False,
    }


def find_discovery_slug(include_store: bool = False) -> str:
    addon = _find_addon(
        lambda slug, name: (
            slug.endswith("switch_vision_discovery")
            or "switch-vision-discovery" in slug
            or name == "switch vision discovery"
        ),
        include_store=include_store,
        fail_on_unavailable=True,
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

def set_discovery_options(options: dict[str, Any], slug: str | None = None) -> None:
    target_slug = slug or find_discovery_slug()
    supervisor_request(f"/addons/{target_slug}/options", method="POST", payload={"options": options})



def normalise_version(value: Any) -> str:
    return str(value or "").strip().lstrip("v")


TRANSIENT_STORE_HTTP_CODES = {404, 409, 423, 429, 500, 502, 503, 504}


def supervisor_store_request(
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    attempts: int = 6,
    delay: float = 5.0,
    progress: Progress | None = None,
) -> dict[str, Any]:
    # Retry transient Supervisor App Store publication/image races.
    last_error: Exception | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return supervisor_request(path, method="POST", payload=payload)
        except Exception as exc:
            last_error = exc
            match = re.search(r"\bHTTP\s+(\d{3})\b", str(exc))
            code = int(match.group(1)) if match else None
            if code not in TRANSIENT_STORE_HTTP_CODES or attempt >= attempts:
                break
            if progress:
                progress(
                    f"Home Assistant App Store metadata is ahead of the published image; "
                    f"retrying ({attempt}/{attempts})…",
                    55,
                )
            time.sleep(delay * attempt)
    raise RuntimeError(
        "Home Assistant advertised the app version before the installable image "
        "became available, or the App Store remained temporarily unavailable. "
        "Wait about one minute and retry. Last error: "
        + str(last_error)
    ) from last_error


def addon_info(slug: str) -> dict[str, Any]:
    payload = supervisor_request(f"/addons/{slug}/info")
    data = payload.get("data", {})
    if not isinstance(data, dict):
        raise RuntimeError(f"Supervisor returned invalid app information for {slug}.")
    return data


def wait_for_addon(slug: str, *, expected_version: str | None = None, expected_state: str | None = None, timeout: int = 300) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        try:
            last = addon_info(slug)
            version_ok = expected_version is None or normalise_version(last.get("version")) == normalise_version(expected_version)
            state_ok = expected_state is None or str(last.get("state") or "").lower() == expected_state.lower()
            if version_ok and state_ok:
                return last
        except Exception:
            pass
        time.sleep(2)
    details = []
    if expected_version is not None:
        details.append(f"version {normalise_version(expected_version)}")
    if expected_state is not None:
        details.append(f"state {expected_state}")
    observed = f"last observed version={last.get('version')!r}, state={last.get('state')!r}" if last else "no app information was returned"
    raise RuntimeError(f"Timed out waiting for {slug} to reach {' and '.join(details)} ({observed}).")


def reconcile_discovery_repository_app(
    store_slug: str,
    progress: Progress | None = None,
) -> dict[str, Any]:
    """Migrate/update Discovery to the repository-backed Supervisor app."""
    store_slug = str(store_slug or "").strip()
    if not store_slug:
        raise RuntimeError("Switch Vision Discovery repository did not return an app slug.")

    match = lambda slug, name: (
        slug.endswith("switch_vision_discovery")
        or "switch-vision-discovery" in slug
        or name == "switch vision discovery"
    )
    installed = _find_addon(match, include_store=False, fail_on_unavailable=True)
    installed_slug = str(installed.get("slug") or "") if installed else ""
    preserved_options = get_discovery_options() if installed else None
    migrated = bool(installed_slug and installed_slug != store_slug)
    installed_now = False
    updated = False

    if migrated:
        try:
            current = addon_info(installed_slug)
        except Exception:
            current = installed or {}
        if str(current.get("state") or "").lower() == "started":
            if progress:
                progress("Stopping legacy local Discovery…", 92)
            supervisor_request(f"/addons/{installed_slug}/stop", method="POST")
            wait_for_addon(installed_slug, expected_state="stopped", timeout=120)
        if progress:
            progress("Removing legacy local Discovery runtime…", 93)
        supervisor_request(
            f"/addons/{installed_slug}/uninstall",
            method="POST",
            payload={"remove_config": False},
        )

    # Keep the old local source in place until the repository-backed app has
    # installed and started successfully. We address the repository app by its
    # explicit store slug, so the temporary duplicate does not affect migration.
    installed_store = _find_addon(
        lambda slug, name: slug == store_slug.lower(),
        include_store=False,
        fail_on_unavailable=True,
    )
    if not installed_store:
        if progress:
            progress("Installing repository-backed Switch Vision Discovery…", 95)
        supervisor_store_request(
            f"/store/addons/{store_slug}/install",
            payload={"background": False},
            progress=progress,
        )
        installed_now = True
        current = wait_for_addon(store_slug, timeout=300)
    else:
        current = addon_info(store_slug)
        current_version = normalise_version(current.get("version"))
        latest_version = normalise_version(current.get("version_latest"))
        if bool(current.get("update_available")) or (
            latest_version and current_version and latest_version != current_version
        ):
            if progress:
                progress(f"Updating Switch Vision Discovery to v{latest_version or 'latest'}…", 96)
            supervisor_store_request(
                f"/store/addons/{store_slug}/update",
                payload={"backup": False, "background": False},
                progress=progress,
            )
            updated = True
            current = wait_for_addon(
                store_slug,
                expected_version=latest_version or None,
                timeout=300,
            )

    if preserved_options is not None:
        if progress:
            progress("Restoring Discovery configuration…", 97)
        set_discovery_options(preserved_options, slug=store_slug)

    if str(current.get("state") or "").lower() != "started":
        if progress:
            progress("Starting Switch Vision Discovery…", 98)
        supervisor_request(f"/addons/{store_slug}/start", method="POST")

    final = wait_for_addon(store_slug, expected_state="started", timeout=180)

    # Only retire legacy local Discovery source files after the repository-backed
    # runtime has been verified as started. Supervisor 2026.07 renamed the
    # writable local-app mount from /addons to /local_apps, so check both.
    legacy_sources = [
        path for path in legacy_discovery_source_paths() if path.is_dir()
    ]
    try:
        local_store_entry = local_discovery_store_present()
    except Exception:
        local_store_entry = True

    if legacy_sources or local_store_entry:
        if progress:
            progress("Retiring legacy local Discovery files…", 99)
        for path in legacy_sources:
            shutil.rmtree(path)

        if progress:
            progress("Refreshing Home Assistant local app metadata…", 99)
        reload_local_app_metadata()
        wait_for_legacy_discovery_absent(timeout=60)

        # The repository-backed app must remain healthy after local metadata
        # is reloaded and the old source has disappeared.
        final = wait_for_addon(
            store_slug,
            expected_state="started",
            timeout=120,
        )

    # Never report a completed migration while Supervisor still advertises
    # local_switch_vision_discovery.
    if local_discovery_store_present():
        raise RuntimeError(
            "Repository-backed Discovery is running, but Home Assistant still "
            "advertises legacy local_switch_vision_discovery."
        )

    return {
        "installed": True,
        "installed_now": installed_now,
        "migrated": migrated,
        "updated": updated,
        "slug": store_slug,
        "version": normalise_version(final.get("version")),
        "state": final.get("state"),
    }


def legacy_discovery_source_paths() -> tuple[Path, ...]:
    """Return current and legacy local Discovery source locations."""
    paths = (DISCOVERY_DIR, LEGACY_DISCOVERY_DIR)
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key not in seen:
            seen.add(key)
            result.append(path)
    return tuple(result)


def local_discovery_store_present() -> bool:
    """Return True when Supervisor still advertises legacy local Discovery."""
    payload = supervisor_request("/store")
    data: Any = payload.get("data", payload) if isinstance(payload, dict) else payload
    addons = data.get("addons", []) if isinstance(data, dict) else []
    if not isinstance(addons, list):
        return False

    for item in addons:
        if not isinstance(item, dict):
            continue
        slug = str(item.get("slug") or "").strip().lower()
        name = str(item.get("name") or "").strip().lower()
        repository = str(item.get("repository") or "").strip().lower()
        if slug == "local_switch_vision_discovery":
            return True
        if (
            repository == "local"
            and name == "switch vision discovery"
            and slug.endswith("switch_vision_discovery")
        ):
            return True
    return False


def reload_local_app_metadata() -> None:
    """Refresh both installed/local app metadata and App Store metadata."""
    errors: list[str] = []
    for endpoint in ("/addons/reload", "/store/reload"):
        try:
            supervisor_request(endpoint, method="POST")
        except Exception as exc:
            errors.append(f"{endpoint}: {exc}")
    if len(errors) == 2:
        raise RuntimeError(
            "Home Assistant could not reload local app or App Store metadata: "
            + "; ".join(errors)
        )


def wait_for_legacy_discovery_absent(timeout: int = 60) -> None:
    """Wait until local Discovery files and Supervisor store entry are gone."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        paths_present = [path for path in legacy_discovery_source_paths() if path.is_dir()]
        try:
            store_present = local_discovery_store_present()
        except Exception:
            store_present = True
        if not paths_present and not store_present:
            return
        time.sleep(2)

    paths_present = [
        str(path) for path in legacy_discovery_source_paths() if path.is_dir()
    ]
    try:
        store_present = local_discovery_store_present()
    except Exception:
        store_present = True
    raise RuntimeError(
        "Legacy local Discovery cleanup did not complete within 60 seconds "
        f"(paths_present={paths_present!r}, supervisor_local_entry={store_present!r})."
    )


def configured_switch_count(options: dict[str, Any] | None) -> int:
    if not isinstance(options, dict):
        return 0
    for key in ("switches", "devices", "targets"):
        value = options.get(key)
        if not isinstance(value, list):
            continue
        if key != "switches":
            return len(value)

        count = 0
        for row in value:
            if isinstance(row, dict):
                if any(
                    str(row.get(field) or "").strip()
                    for field in ("switch_name", "switch_host")
                ):
                    count += 1
            elif str(row or "").strip():
                count += 1
        return count
    return 0


def _find_addon(
    predicate: Callable[[str, str], bool],
    include_store: bool = False,
    *,
    fail_on_unavailable: bool = False,
) -> dict[str, Any] | None:
    endpoints = ["/addons"]
    if include_store:
        endpoints.append("/store")
    successful_queries = 0
    last_error: Exception | None = None
    for endpoint in endpoints:
        try:
            payload = supervisor_request(endpoint)
        except Exception as exc:
            last_error = exc
            continue
        successful_queries += 1
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
    if fail_on_unavailable and successful_queries == 0:
        raise RuntimeError("Home Assistant Supervisor app status is unavailable.") from last_error
    return None


def discovery_status() -> dict[str, Any]:
    installed_addon = _find_addon(
        lambda slug, name: (
            slug.endswith("switch_vision_discovery")
            or "switch-vision-discovery" in slug
            or name == "switch vision discovery"
        ),
        include_store=False,
        fail_on_unavailable=True,
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
        fail_on_unavailable=True,
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
        fail_on_unavailable=True,
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


def find_unifi2mqtt_slug(include_store: bool = False) -> str:
    addon = _find_addon(
        lambda slug, name: (
            "switch_vision_unifi2mqtt" in slug
            or "switch-vision-unifi2mqtt" in slug
            or name == "switch vision unifi2mqtt"
            or ("switch vision" in name and "unifi2mqtt" in name)
        ),
        include_store=include_store,
        fail_on_unavailable=True,
    )
    if addon:
        return str(addon.get("slug", ""))
    raise RuntimeError("Switch Vision UniFi2MQTT add-on was not found by Supervisor.")


def get_unifi2mqtt_info() -> dict[str, Any] | None:
    try:
        slug = find_unifi2mqtt_slug()
        info = supervisor_request(f"/addons/{slug}/info")
        data = info.get("data", {})
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def get_unifi2mqtt_options() -> dict[str, Any] | None:
    info = get_unifi2mqtt_info()
    options = info.get("options") if isinstance(info, dict) else None
    return options if isinstance(options, dict) else None


def unifi2mqtt_options_configured(options: dict[str, Any] | None) -> bool:
    # Only save/restore UniFi options when every required Supervisor field is populated.
    if not isinstance(options, dict):
        return False
    required = (
        "controller_url",
        "site_id",
        "api_key",
        "verify_ssl",
        "poll_interval",
        "mqtt_host",
        "mqtt_port",
        "mqtt_topic_prefix",
        "mqtt_discovery_prefix",
    )
    return all(str(options.get(key) if options.get(key) is not None else "").strip() for key in required)


def set_unifi2mqtt_options(options: dict[str, Any]) -> None:
    slug = find_unifi2mqtt_slug()
    supervisor_request(f"/addons/{slug}/options", method="POST", payload={"options": options})


def unifi2mqtt_status() -> dict[str, Any]:
    match = lambda slug, name: (
        "switch_vision_unifi2mqtt" in slug
        or "switch-vision-unifi2mqtt" in slug
        or name == "switch vision unifi2mqtt"
        or ("switch vision" in name and "unifi2mqtt" in name)
    )
    installed_addon = _find_addon(match, include_store=False, fail_on_unavailable=True)
    store_addon = _find_addon(match, include_store=True)
    if installed_addon:
        slug = str(installed_addon.get("slug", ""))
        try:
            info_payload = supervisor_request(f"/addons/{slug}/info")
            info = info_payload.get("data", {})
        except Exception:
            info = installed_addon
        return {
            "present": UNIFI2MQTT_DIR.is_dir(),
            "available": True,
            "installed": True,
            "slug": slug,
            "version": info.get("version") or info.get("version_latest") or installed_addon.get("version"),
            "state": info.get("state") or installed_addon.get("state") or "unknown",
            "ingress_entry": info.get("ingress_entry") or installed_addon.get("ingress_entry"),
            "webui": info.get("webui") or installed_addon.get("webui"),
        }
    return {
        "present": UNIFI2MQTT_DIR.is_dir(),
        "available": bool(store_addon) or UNIFI2MQTT_DIR.is_dir(),
        "installed": False,
        "slug": str(store_addon.get("slug", "")) if store_addon else None,
        "version": (store_addon.get("version") or store_addon.get("version_latest")) if store_addon else None,
        "state": "not_installed",
        "ingress_entry": None,
        "webui": None,
    }


def reload_addon_store() -> None:
    """Refresh Supervisor App Store metadata once, with bounded serialization.

    Current Supervisor versions make both /addons/reload and /store/reload
    perform repository updates. Calling them back-to-back can overlap long
    refresh tasks after a client-side timeout. One serialized /store/reload is
    the authoritative refresh for Installer update decisions.
    """
    with _STORE_RELOAD_LOCK:
        try:
            supervisor_request("/store/reload", method="POST", timeout=180.0)
        except Exception as store_exc:
            raise RuntimeError(
                f"Home Assistant App Store refresh failed: {store_exc}"
            ) from store_exc


def install_supervisor_addon(kind: str) -> dict[str, Any]:
    reload_addon_store()
    if kind == "snmp2mqtt":
        slug = find_snmp2mqtt_slug(include_store=True)
    elif kind == "unifi2mqtt":
        slug = find_unifi2mqtt_slug(include_store=True)
    else:
        raise RuntimeError(f"Unsupported add-on kind: {kind}")
    try:
        result = supervisor_store_request(
            f"/store/addons/{slug}/install",
            payload={"background": False},
        )
    except Exception as store_exc:
        # Compatibility endpoint for Supervisor builds without the store endpoint.
        # If it also fails, preserve the useful publication-race error from the
        # primary App Store request instead of hiding it behind the fallback.
        try:
            result = supervisor_request(f"/addons/{slug}/install", method="POST")
        except Exception as compatibility_exc:
            raise RuntimeError(
                f"{store_exc} Compatibility install endpoint also failed: "
                f"{compatibility_exc}"
            ) from store_exc
    return {"slug": slug, "supervisor": result}

def find_release_snmp2mqtt_dir(root: Path) -> Path | None:
    candidates = [
        root / "local_apps" / "switch_vision_snmp2mqtt",
        root / "local_apps" / "switch-vision-snmp2mqtt-addon",
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
    faceplate_changes: dict[str, Any] | None = None


def load_options() -> dict[str, Any]:
    defaults = {
        "release_api_url": OFFICIAL_RELEASE_API_URL,
        "allow_custom_release_source": False,
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


def validated_release_api_url(options: dict[str, Any]) -> str:
    url = str(options.get("release_api_url") or OFFICIAL_RELEASE_API_URL).strip()
    if url == OFFICIAL_RELEASE_API_URL:
        return url
    if not bool(options.get("allow_custom_release_source", False)):
        raise RuntimeError(
            "Custom Core release sources are disabled. Switch Vision Installer "
            "only trusts the official switch-vision-releases GitHub API endpoint "
            "unless allow_custom_release_source is explicitly enabled."
        )
    return url


def request_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": f"Switch-Vision-Installer/{INSTALLER_VERSION}"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def official_latest_release_version() -> str:
    """Resolve the latest public Core tag without consuming GitHub REST quota."""
    request = urllib.request.Request(
        OFFICIAL_RELEASE_LATEST_URL,
        method="HEAD",
        headers={"User-Agent": f"Switch-Vision-Installer/{INSTALLER_VERSION}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        final_url = str(response.geturl() or "")
    match = re.search(r"/releases/tag/v?(\d+\.\d+\.\d+)(?:$|[/?#])", final_url)
    if not match:
        raise RuntimeError(
            "GitHub latest-release redirect did not resolve to a semantic Core tag."
        )
    return normalise_version(match.group(1))


def _official_release_notes(version: str) -> str:
    url = f"{OFFICIAL_RELEASE_RAW_BASE}/{version}/RELEASE_NOTES.md"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": f"Switch-Vision-Installer/{INSTALLER_VERSION}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def _official_release_asset_metadata(url: str) -> dict[str, Any]:
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


def latest_release() -> dict[str, Any]:
    options = load_options()
    release_api_url = validated_release_api_url(options)
    if release_api_url == OFFICIAL_RELEASE_API_URL:
        return official_latest_release()

    # Explicitly opted-in custom release APIs retain the structured API path.
    payload = request_json(release_api_url)
    if payload.get("prerelease") and not options.get("allow_prerelease"):
        raise RuntimeError("Latest GitHub release is marked as a prerelease.")

    version = normalise_version(payload.get("tag_name") or payload.get("name"))
    if not version:
        raise RuntimeError("Latest GitHub release does not contain a usable version tag.")

    pattern = str(options.get("release_asset_pattern") or "switch-vision-*.zip")
    matched = [
        a for a in payload.get("assets", [])
        if isinstance(a, dict)
        and fnmatch(str(a.get("name", "")), pattern)
        and "source" not in str(a.get("name", "")).lower()
    ]
    expected_name = f"switch-vision-{version}.zip"
    exact = [a for a in matched if str(a.get("name") or "") == expected_name]
    if len(exact) != 1:
        names = ", ".join(sorted(str(a.get("name") or "") for a in matched)) or "none"
        raise RuntimeError(
            f"Release v{version} must contain exactly one installable asset named "
            f"{expected_name!r}; matched assets: {names}."
        )
    asset = exact[0]

    digest_text = str(asset.get("digest") or "").strip()
    asset_digest = None
    if digest_text:
        match = re.fullmatch(r"sha256:([a-fA-F0-9]{64})", digest_text)
        if not match:
            raise RuntimeError(
                f"Release asset {expected_name} published an unsupported digest {digest_text!r}."
            )
        asset_digest = match.group(1).lower()

    asset_name_lower = expected_name.lower()
    checksum_names = {
        "sha256sums.txt",
        "sha256sum.txt",
        "checksums.txt",
        f"{asset_name_lower}.sha256",
        f"{asset_name_lower}.sha256sum",
    }
    checksum_assets = [
        a for a in payload.get("assets", [])
        if isinstance(a, dict)
        and str(a.get("name", "")).lower() in checksum_names
    ]
    checksum_asset = checksum_assets[0] if checksum_assets else None
    return {
        "version": version,
        "name": payload.get("name") or payload.get("tag_name"),
        "published_at": payload.get("published_at"),
        "asset_name": asset.get("name"),
        "asset_url": asset.get("browser_download_url"),
        "asset_size": asset.get("size"),
        "asset_digest": asset_digest,
        "html_url": payload.get("html_url"),
        "changelog": payload.get("body") or "",
        "checksum_asset_name": checksum_asset.get("name") if checksum_asset else None,
        "checksum_asset_url": checksum_asset.get("browser_download_url") if checksum_asset else None,
    }

def download_file(url: str, destination: Path, timeout: int = 120) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": f"Switch-Vision-Installer/{INSTALLER_VERSION}"})
    with urllib.request.urlopen(request, timeout=timeout) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def expected_release_checksum(release: dict[str, Any], work_dir: Path) -> str:
    github_digest = str(release.get("asset_digest") or "").strip().lower() or None
    checksum_digest: str | None = None
    url = release.get("checksum_asset_url")
    if url:
        checksum_file = work_dir / str(
            release.get("checksum_asset_name") or "SHA256SUMS.txt"
        )
        download_file(str(url), checksum_file, timeout=30)
        text = checksum_file.read_text(encoding="utf-8", errors="replace")
        asset_name = str(release.get("asset_name") or "")
        for line in text.splitlines():
            # GNU sha256sum format: <digest> [* ]<filename>
            match = re.match(
                r"^\s*([a-fA-F0-9]{64})\s+[* ]?(.+?)\s*$", line
            )
            if match and Path(match.group(2).strip()).name == asset_name:
                checksum_digest = match.group(1).lower()
                break
            # BSD/OpenSSL format: SHA256 (<filename>) = <digest>
            match = re.match(
                r"^\s*SHA256\s*\((.+)\)\s*=\s*([a-fA-F0-9]{64})\s*$",
                line,
                flags=re.IGNORECASE,
            )
            if match and Path(match.group(1).strip()).name == asset_name:
                checksum_digest = match.group(2).lower()
                break
        if (
            checksum_digest is None
            and str(release.get("checksum_asset_name", "")).lower().endswith(
                (".sha256", ".sha256sum")
            )
        ):
            match = re.search(r"\b([a-fA-F0-9]{64})\b", text)
            if match:
                checksum_digest = match.group(1).lower()
        if checksum_digest is None:
            raise RuntimeError(
                f"Checksum file does not contain an entry for {asset_name}."
            )

    if github_digest and checksum_digest and github_digest != checksum_digest:
        raise RuntimeError(
            "Release checksum sources disagree: GitHub asset digest "
            f"{github_digest} != checksum asset {checksum_digest}."
        )
    expected = github_digest or checksum_digest
    if not expected:
        raise RuntimeError(
            "Release does not publish a trusted SHA-256 digest. "
            "Refusing to install an unverified asset."
        )
    return expected

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
    add(
        "Supervisor API",
        bool(SUPERVISOR_TOKEN),
        "Supervisor token available" if SUPERVISOR_TOKEN else "Supervisor token unavailable",
    )
    if SUPERVISOR_TOKEN:
        try:
            supervisor_request("/info")
            checks[-1] = {
                "name": "Supervisor API",
                "ok": True,
                "detail": "Supervisor API responded successfully",
            }
        except Exception as exc:
            checks[-1] = {"name": "Supervisor API", "ok": False, "detail": str(exc)}
    for label, path in (
        ("Home Assistant configuration", HA_CONFIG),
        ("Local add-ons", ADDONS_DIR),
        ("Shared storage", SHARE_DIR),
        ("Installer work directory", WORK_DIR),
    ):
        add(f"Writable: {label}", path_writable(path), str(path))
    usage = shutil.disk_usage(SHARE_DIR if SHARE_DIR.exists() else Path("/"))
    asset_size = int(release.get("asset_size") or 0)
    required = max(128 * 1024 * 1024, asset_size * 4)
    add(
        "Available disk space",
        usage.free >= required,
        f"{usage.free // (1024*1024)} MB free; {required // (1024*1024)} MB required",
    )
    expected_name = f"switch-vision-{normalise_version(release.get('version'))}.zip"
    add(
        "Release asset identity",
        bool(release.get("asset_url") and release.get("asset_name") == expected_name),
        str(release.get("asset_name") or "Missing"),
    )
    trusted = bool(release.get("asset_digest") or release.get("checksum_asset_url"))
    add(
        "Trusted SHA-256",
        trusted,
        (
            "GitHub release asset digest"
            if release.get("asset_digest")
            else str(release.get("checksum_asset_name") or "No trusted checksum published")
        ),
    )
    blocking = [c for c in checks if not c["ok"]]
    return {"ok": not blocking, "checks": checks, "release": release}

def installed_version() -> str | None:
    # Return Core's version only; Discovery has an independent version stream.
    manifest = COMPONENT_DIR / "manifest.json"
    if manifest.exists():
        try:
            value = str(
                json.loads(manifest.read_text(encoding="utf-8")).get("version") or ""
            ).strip()
            return value or None
        except (OSError, json.JSONDecodeError):
            pass
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
        relative = file.relative_to(path)
        if "__pycache__" in relative.parts or file.suffix in {".pyc", ".pyo"}:
            continue
        digest.update(relative.as_posix().encode("utf-8")); digest.update(b"\0")
        with file.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def safe_extract(archive: Path, destination: Path) -> None:
    """Extract a release ZIP with path and resource-exhaustion limits."""
    destination = destination.resolve()
    with zipfile.ZipFile(archive) as zf:
        members = zf.infolist()
        if len(members) > MAX_ARCHIVE_ENTRIES:
            raise RuntimeError(
                "Release archive contains too many entries: "
                f"{len(members)} > {MAX_ARCHIVE_ENTRIES}."
            )

        total_uncompressed = 0
        for info in members:
            member = PurePosixPath(info.filename)
            if member.is_absolute() or ".." in member.parts:
                raise RuntimeError(f"Unsafe archive member: {info.filename}")

            target = (destination / Path(*member.parts)).resolve()
            if destination not in target.parents and target != destination:
                raise RuntimeError(f"Archive path escapes staging: {info.filename}")

            file_size = max(0, int(info.file_size))
            compressed_size = max(0, int(info.compress_size))

            if file_size > MAX_ARCHIVE_MEMBER_UNCOMPRESSED_BYTES:
                raise RuntimeError(
                    "Release archive member is too large after decompression: "
                    f"{info.filename} ({file_size} bytes)."
                )

            total_uncompressed += file_size
            if total_uncompressed > MAX_ARCHIVE_TOTAL_UNCOMPRESSED_BYTES:
                raise RuntimeError(
                    "Release archive exceeds the total uncompressed size limit: "
                    f"{total_uncompressed} bytes."
                )

            if file_size > 0:
                if compressed_size == 0:
                    raise RuntimeError(
                        "Release archive member has an invalid compression ratio: "
                        f"{info.filename}."
                    )
                ratio = file_size / compressed_size
                if ratio > MAX_ARCHIVE_COMPRESSION_RATIO:
                    raise RuntimeError(
                        "Release archive member exceeds the compression-ratio limit: "
                        f"{info.filename} ({ratio:.1f}:1)."
                    )

        zf.extractall(destination)


def find_release_root(extracted: Path) -> Path:
    candidates = [extracted, *(p for p in extracted.iterdir() if p.is_dir())]
    for candidate in candidates:
        if (candidate / "custom_components" / "switch_vision").is_dir():
            return candidate
    raise RuntimeError("Release ZIP does not contain the expected Switch Vision custom component.")


def _backup_runtime() -> _backup_manager.BackupRuntime:
    return _backup_manager.BackupRuntime(
        backup_dir=BACKUP_DIR,
        backup_policy_path=BACKUP_POLICY_PATH,
        legacy_backup_dir=LEGACY_BACKUP_DIR,
        work_dir=WORK_DIR,
        ha_config=HA_CONFIG,
        component_dir=COMPONENT_DIR,
        frontend_dir=FRONTEND_DIR,
        generated_snmp2mqtt_yaml=GENERATED_SNMP2MQTT_YAML,
        installer_version=INSTALLER_VERSION,
        load_options=load_options,
        get_discovery_options=get_discovery_options,
        get_snmp2mqtt_options=get_snmp2mqtt_options,
        get_unifi2mqtt_options=get_unifi2mqtt_options,
        set_discovery_options=set_discovery_options,
        set_snmp2mqtt_options=set_snmp2mqtt_options,
        set_unifi2mqtt_options=set_unifi2mqtt_options,
        discovery_status=discovery_status,
        snmp2mqtt_status=snmp2mqtt_status,
        unifi2mqtt_status=unifi2mqtt_status,
        installed_version=installed_version,
        configured_switch_count=configured_switch_count,
        unifi2mqtt_options_configured=unifi2mqtt_options_configured,
        sha256=sha256,
        replace_tree=replace_tree,
        copy_backup=copy_backup,
        backup_contents=backup_contents,
        backup_file_hashes=backup_file_hashes,
        secure_backup_permissions=secure_backup_permissions,
        validate_backup=validate_backup,
        backup_policy=backup_policy,
        prune_backups=prune_backups,
        create_backup=create_backup,
        backup_roots=_backup_roots,
        safe_backup_path=_safe_backup_path,
        restore_backup_contents=_restore_backup_contents,
        capture_restore_snapshot=_capture_restore_snapshot,
        rollback_restore_snapshot=_rollback_restore_snapshot,
    )


def copy_backup(source: Path, root: Path, label: str) -> None:
    return _backup_manager.copy_backup(source, root, label)


def backup_contents(path: Path) -> list[str]:
    return _backup_manager.backup_contents(path)


def backup_file_hashes(path: Path) -> dict[str, str]:
    return _backup_manager.backup_file_hashes(_backup_runtime(), path)


def secure_backup_permissions(path: Path) -> None:
    return _backup_manager.secure_backup_permissions(path)


def validate_backup(path: Path) -> dict[str, Any]:
    return _backup_manager.validate_backup(_backup_runtime(), path)


def backup_policy() -> dict[str, Any]:
    return _backup_manager.backup_policy(_backup_runtime())


def save_backup_policy(
    automatic_retention: Any,
    retention_count: Any,
) -> dict[str, Any]:
    return _backup_manager.save_backup_policy(
        _backup_runtime(),
        automatic_retention,
        retention_count,
    )


def prune_backups(*, force: bool = False) -> dict[str, Any]:
    return _backup_manager.prune_backups(
        _backup_runtime(),
        force=force,
    )


def apply_backup_retention() -> dict[str, Any]:
    return _backup_manager.apply_backup_retention(_backup_runtime())


def create_backup(force: bool = False) -> Path | None:
    return _backup_manager.create_backup(
        _backup_runtime(),
        force=force,
    )


def create_manual_backup(
    progress: Progress | None = None,
) -> dict[str, Any]:
    return _backup_manager.create_manual_backup(
        _backup_runtime(),
        progress,
    )


def validate_named_backup(
    name: str,
    progress: Progress | None = None,
) -> dict[str, Any]:
    return _backup_manager.validate_named_backup(
        _backup_runtime(),
        name,
        progress,
    )


def _backup_roots() -> list[Path]:
    return _backup_manager.backup_roots(_backup_runtime())


def list_backups() -> list[dict[str, Any]]:
    return _backup_manager.list_backups(_backup_runtime())


def _safe_backup_path(name: str) -> Path:
    return _backup_manager.safe_backup_path(_backup_runtime(), name)


def delete_backup(name: str) -> dict[str, Any]:
    return _backup_manager.delete_backup(_backup_runtime(), name)


REPLACE_TRANSACTION_SUFFIX = _tree_transaction.REPLACE_TRANSACTION_SUFFIX


def _remove_tree_path(path: Path) -> None:
    return _tree_transaction.remove_tree_path(path)


def _fsync_directory(path: Path) -> None:
    return _tree_transaction.fsync_directory(path)


def _replacement_marker_path(destination: Path) -> Path:
    return _tree_transaction.replacement_marker_path(destination)


def _validated_transaction_path(
    destination: Path,
    value: Any,
    kind: str,
) -> Path:
    return _tree_transaction.validated_transaction_path(
        destination,
        value,
        kind,
    )


def _write_replace_transaction(
    destination: Path,
    stage: Path,
    previous: Path,
    had_destination: bool,
) -> Path:
    return _tree_transaction.write_replace_transaction(
        destination,
        stage,
        previous,
        had_destination,
        marker_path_func=_replacement_marker_path,
        fsync_func=_fsync_directory,
    )


def _load_replace_transaction(
    destination: Path,
) -> tuple[Path, Path, Path, bool] | None:
    return _tree_transaction.load_replace_transaction(
        destination,
        marker_path_func=_replacement_marker_path,
        validate_path_func=_validated_transaction_path,
    )


def recover_interrupted_tree_replacement(destination: Path) -> bool:
    return _tree_transaction.recover_interrupted_tree_replacement(
        destination,
        load_transaction_func=_load_replace_transaction,
        remove_tree_func=_remove_tree_path,
        fsync_func=_fsync_directory,
    )


def recover_interrupted_tree_replacements() -> list[str]:
    return _tree_transaction.recover_interrupted_tree_replacements(
        (COMPONENT_DIR, FRONTEND_DIR),
        recover_func=recover_interrupted_tree_replacement,
    )


def _rollback_tree_replacement(
    destination: Path,
    stage: Path,
    previous: Path,
    had_destination: bool,
) -> None:
    return _tree_transaction.rollback_tree_replacement(
        destination,
        stage,
        previous,
        had_destination,
        remove_tree_func=_remove_tree_path,
        marker_path_func=_replacement_marker_path,
        fsync_func=_fsync_directory,
    )


def replace_tree(source: Path, destination: Path) -> None:
    return _tree_transaction.replace_tree(
        source,
        destination,
        recover_func=recover_interrupted_tree_replacement,
        remove_tree_func=_remove_tree_path,
        write_transaction_func=_write_replace_transaction,
        rollback_func=_rollback_tree_replacement,
        fsync_func=_fsync_directory,
    )


def _restore_backup_contents(
    name: str,
    progress: Progress | None = None,
) -> dict[str, Any]:
    return _backup_manager.restore_backup_contents(
        _backup_runtime(),
        name,
        progress,
    )


def _capture_restore_snapshot(path: Path) -> dict[str, Any]:
    return _backup_manager.capture_restore_snapshot(
        _backup_runtime(),
        path,
    )


def _rollback_restore_snapshot(
    path: Path,
    meta: dict[str, Any],
) -> None:
    return _backup_manager.rollback_restore_snapshot(
        _backup_runtime(),
        path,
        meta,
    )


def restore_backup(
    name: str,
    progress: Progress | None = None,
) -> dict[str, Any]:
    return _backup_manager.restore_backup(
        _backup_runtime(),
        name,
        progress,
    )


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
    # Preserve image revisions before atomic frontend replacement. An artwork
    # correction keeps its canonical filename and existing Calibration geometry.
    _faceplate_history.stage_history(root, COMPONENT_DIR, FRONTEND_DIR, target, HA_CONFIG / ".storage/switch_vision_calibrations")


def component_plan(root: Path, *, force: bool = False) -> tuple[list[tuple[Path, Path, str]], list[str], list[str]]:
    with tempfile.TemporaryDirectory(dir=WORK_DIR) as td:
        frontend_stage = Path(td) / "frontend"
        build_frontend_stage(root, frontend_stage)
        mappings = [
            (root / "custom_components" / "switch_vision", COMPONENT_DIR, "Custom component"),
            (frontend_stage, FRONTEND_DIR, "Dashboard frontend and visual assets"),
        ]
        # Frontend stage is temporary, so return copied source paths only from a persistent temp clone.
        persistent = WORK_DIR / "plan-frontend"
        if persistent.exists(): shutil.rmtree(persistent)
        shutil.copytree(frontend_stage, persistent)
        mappings = [(persistent if label == "Dashboard frontend and visual assets" else src, dst, label) for src, dst, label in mappings]
    changed = list(mappings) if force else [(src, dst, label) for src, dst, label in mappings if tree_digest(src) != tree_digest(dst)]
    unchanged = [] if force else [label for src, dst, label in mappings if tree_digest(src) == tree_digest(dst)]
    missing = [label for src, dst, label in mappings if not dst.exists()]
    return changed, unchanged, missing


def install_release(root: Path, version: str, checksum: str, progress: Progress | None = None, *, force: bool = False) -> InstallResult:
    if progress: progress("Preparing forced Core reinstall…" if force else "Comparing installed components…", 48)
    artwork_changes = _faceplate_history.faceplate_change_summary(
        root, COMPONENT_DIR, FRONTEND_DIR
    )
    changed, unchanged, _ = component_plan(root, force=force)
    backup = create_backup() if changed else None
    if backup is not None:
        validate_backup(backup)
    if progress: progress("Backup verified. Installing changed components…", 62)
    custom_assets = collect_custom_assets(); installed=[]; preserved=[]; warnings=[]
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
    except Exception as exc:
        rollback_note = ""
        if backup is not None:
            try:
                restore_backup(backup.name)
                rollback_note = " Previous files were restored from the verified backup."
            except Exception as rollback_exc:
                rollback_note = f" Automatic rollback also failed: {rollback_exc}"
        raise RuntimeError(f"Installation failed: {exc}.{rollback_note}") from exc
    if not GENERATED_SNMP2MQTT_YAML.is_file():
        warnings.append("Generated SNMP2MQTT YAML was not found at /share/switch_vision/generated-snmp2mqtt.yaml.")
    actions=[]
    if "Custom component" in installed: actions.append("Restart Home Assistant Core")
    if "Dashboard frontend and visual assets" in installed: actions.append("Hard-refresh the browser if older frontend content remains")
    result = InstallResult(
        True, version, str(backup) if backup else None, installed, unchanged,
        preserved, warnings, actions, checksum, datetime.now(timezone.utc).isoformat(),
        faceplate_changes=artwork_changes,
    )
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8")
    return result


def prepare_release(progress: Progress | None = None) -> tuple[dict[str, Any], Path, Path, str, bool]:
    if progress:
        progress("Checking the latest public release…", 5)
    release = latest_release()
    report = preflight_checks(release)
    if not report["ok"]:
        failed = "; ".join(
            c["name"] + ": " + c["detail"] for c in report["checks"] if not c["ok"]
        )
        raise RuntimeError("Preflight checks failed: " + failed)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = Path(tempfile.mkdtemp(dir=WORK_DIR))
    archive = tmp_path / str(release["asset_name"])
    if progress:
        progress(f"Downloading {release['asset_name']}…", 18)
    download_file(str(release["asset_url"]), archive)

    expected_size = int(release.get("asset_size") or 0)
    actual_size = archive.stat().st_size
    if actual_size <= 0:
        raise RuntimeError("Downloaded release archive is empty.")
    if expected_size and actual_size != expected_size:
        raise RuntimeError(
            f"Release asset size mismatch: expected {expected_size} bytes, "
            f"received {actual_size} bytes."
        )

    if progress:
        progress("Verifying trusted SHA-256 and release identity…", 35)
    actual = sha256(archive)
    expected = expected_release_checksum(release, tmp_path)
    if actual != expected:
        raise RuntimeError(
            f"Release checksum mismatch: expected {expected}, received {actual}."
        )

    extracted = tmp_path / "extracted"
    extracted.mkdir()
    safe_extract(archive, extracted)
    root = find_release_root(extracted)

    manifest = root / "custom_components" / "switch_vision" / "manifest.json"
    if not manifest.is_file():
        raise RuntimeError("Release ZIP is missing the Switch Vision Core manifest.")
    try:
        payload_version = normalise_version(
            json.loads(manifest.read_text(encoding="utf-8")).get("version")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Release Core manifest is unreadable.") from exc
    expected_version = normalise_version(release.get("version"))
    if payload_version != expected_version:
        raise RuntimeError(
            f"Release identity mismatch: GitHub tag is v{expected_version}, "
            f"but the packaged Core manifest is v{payload_version or 'unknown'}."
        )
    return release, tmp_path, root, actual, True

def dry_run(progress: Progress | None = None) -> dict[str, Any]:
    release, tmp_path, root, checksum, checksum_verified = prepare_release(progress)
    try:
        changed, unchanged, missing = component_plan(root)
        custom_assets = collect_custom_assets()
        artwork_changes = _faceplate_history.faceplate_change_summary(
            root, COMPONENT_DIR, FRONTEND_DIR
        )
        preview_sha = _faceplate_history.stage_preflight_previews(
            root, WORK_DIR / "faceplate-previews", artwork_changes
        )
        plan = {
            "ok": True, "dry_run": True, "version": str(release["version"]),
            "faceplate_preview_sha256": preview_sha,
            "faceplate_changes": artwork_changes,
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


def download_and_install(progress: Progress | None = None, *, force: bool = False) -> InstallResult:
    release, tmp_path, root, checksum, _ = prepare_release(progress)
    try:
        result = install_release(root, str(release["version"]), checksum, progress, force=force)
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
    unifi = unifi2mqtt_status()
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
        # Home Assistant app routes resolve fresh ingress sessions; never
        # navigate to a Supervisor /api/hassio_ingress token in a new tab.
        "discovery_hub_path": f"/app/{discovery.get('slug')}" if discovery.get("slug") else None,
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
        "unifi2mqtt_present": bool(unifi.get("present")),
        "unifi2mqtt_available": bool(unifi.get("available")),
        "unifi2mqtt_slug": unifi.get("slug"),
        "unifi2mqtt_installed": bool(unifi.get("installed")),
        "unifi2mqtt_version": unifi.get("version"),
        "unifi2mqtt_state": unifi.get("state"),
        "unifi2mqtt_ingress_entry": unifi.get("ingress_entry"),
        "unifi2mqtt_webui": unifi.get("webui"),
        "unifi2mqtt_details_path": f"/config/app/{unifi.get('slug')}/info" if unifi.get("slug") else None,
        "backup_path": str(BACKUP_DIR),
        "backup_retention": int(backup_policy()["retention_count"]),
        "backup_retention_automatic": bool(backup_policy()["automatic_retention"]),
        "last_result": state,
    }
