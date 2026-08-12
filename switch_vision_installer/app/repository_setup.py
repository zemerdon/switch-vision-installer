from __future__ import annotations

from typing import Any, Callable
import time

import installer as installer_core

DISCOVERY_REPOSITORY = "https://github.com/zemerdon/switch-vision-discovery"
SNMP2MQTT_REPOSITORY = "https://github.com/zemerdon/switch-vision-snmp2mqtt-addon"
UNIFI2MQTT_REPOSITORY = "https://github.com/zemerdon/switch-vision-unifi2mqtt"
Progress = Callable[[str, int], None]


def _normalise_repo_url(value: Any) -> str:
    text = str(value or "").strip().rstrip("/")
    if text.endswith(".git"):
        text = text[:-4]
    return text.lower()


def _repository_list() -> list[dict[str, Any]]:
    payload = installer_core.supervisor_request("/store/repositories")
    data: Any = payload.get("data", payload) if isinstance(payload, dict) else payload
    if isinstance(data, dict):
        data = data.get("repositories", [])
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _repository_entry() -> dict[str, Any] | None:
    expected = _normalise_repo_url(SNMP2MQTT_REPOSITORY)
    for item in _repository_list():
        for key in ("source", "url"):
            if _normalise_repo_url(item.get(key)) == expected:
                return item
    return None


def _wait_for_snmp2mqtt(timeout: int = 120) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return installer_core.find_snmp2mqtt_slug(include_store=True)
        except Exception:
            time.sleep(2)
    raise RuntimeError(
        "Switch Vision SNMP2MQTT repository is registered, but the app did not become available "
        "in the Home Assistant store within 120 seconds."
    )


def ensure_snmp2mqtt_repository(progress: Progress | None = None) -> dict[str, Any]:
    """Ensure the official Switch Vision SNMP2MQTT App repository is registered."""
    try:
        slug = installer_core.find_snmp2mqtt_slug(include_store=True)
        return {"added": False, "available": True, "slug": slug, "repository": SNMP2MQTT_REPOSITORY}
    except Exception:
        pass

    existing = _repository_entry()
    added = False
    if existing is None:
        if progress:
            progress("Adding the Switch Vision SNMP2MQTT App repository…", 3)
        try:
            installer_core.supervisor_request(
                "/store/repositories",
                method="POST",
                payload={"repository": SNMP2MQTT_REPOSITORY},
            )
            added = True
        except Exception:
            # A duplicate can be returned if another request registered the repo first.
            if _repository_entry() is None:
                raise

    if progress:
        progress("Refreshing the Home Assistant App store…", 4)
    installer_core.reload_addon_store()
    slug = _wait_for_snmp2mqtt()
    return {
        "added": added,
        "available": True,
        "slug": slug,
        "repository": SNMP2MQTT_REPOSITORY,
    }

def _repository_entry_for(repository: str) -> dict[str, Any] | None:
    expected = _normalise_repo_url(repository)
    for item in _repository_list():
        for key in ("source", "url"):
            if _normalise_repo_url(item.get(key)) == expected:
                return item
    return None


def _wait_for_unifi2mqtt(timeout: int = 120) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return installer_core.find_unifi2mqtt_slug(include_store=True)
        except Exception:
            time.sleep(2)
    raise RuntimeError(
        "Switch Vision UniFi2MQTT repository is registered, but the app did not become available "
        "in the Home Assistant store within 120 seconds."
    )


def ensure_unifi2mqtt_repository(progress: Progress | None = None) -> dict[str, Any]:
    try:
        slug = installer_core.find_unifi2mqtt_slug(include_store=True)
        return {"added": False, "available": True, "slug": slug, "repository": UNIFI2MQTT_REPOSITORY}
    except Exception:
        pass

    existing = _repository_entry_for(UNIFI2MQTT_REPOSITORY)
    added = False
    if existing is None:
        if progress:
            progress("Adding the Switch Vision UniFi2MQTT App repository…", 3)
        try:
            installer_core.supervisor_request(
                "/store/repositories",
                method="POST",
                payload={"repository": UNIFI2MQTT_REPOSITORY},
            )
            added = True
        except Exception:
            if _repository_entry_for(UNIFI2MQTT_REPOSITORY) is None:
                raise

    if progress:
        progress("Refreshing the Home Assistant App store…", 4)
    installer_core.reload_addon_store()
    slug = _wait_for_unifi2mqtt()
    return {
        "added": added,
        "available": True,
        "slug": slug,
        "repository": UNIFI2MQTT_REPOSITORY,
    }

def _store_addons() -> list[dict[str, Any]]:
    payload = installer_core.supervisor_request("/store")
    data: Any = payload.get("data", payload) if isinstance(payload, dict) else payload
    if isinstance(data, dict):
        data = data.get("addons", [])
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _repository_slug_for(repository: str) -> str:
    """Return Supervisor's repository identity for a registered repository."""
    entry = _repository_entry_for(repository)
    if not entry:
        return ""
    return str(entry.get("slug") or "").strip()


def _discovery_store_entry(repository_slug: str | None = None) -> dict[str, Any] | None:
    """Find Discovery in the store using Supervisor repository identity."""
    expected_url = _normalise_repo_url(DISCOVERY_REPOSITORY)
    expected_repo_slug = str(
        repository_slug or _repository_slug_for(DISCOVERY_REPOSITORY)
    ).strip().lower()

    for item in _store_addons():
        slug = str(item.get("slug") or "").strip().lower()
        name = str(item.get("name") or "").strip().lower()
        item_repository = str(item.get("repository") or "").strip().lower()
        item_repository_url = _normalise_repo_url(item.get("repository"))

        matches_app = (
            slug.endswith("switch_vision_discovery")
            or "switch-vision-discovery" in slug
            or name == "switch vision discovery"
        )
        belongs_to_repository = (
            bool(expected_repo_slug)
            and (
                item_repository == expected_repo_slug
                or slug.startswith(expected_repo_slug + "_")
            )
        ) or item_repository_url == expected_url

        if matches_app and belongs_to_repository:
            return item
    return None


def _wait_for_discovery(repository_slug: str, timeout: int = 60) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        entry = _discovery_store_entry(repository_slug)
        if entry and str(entry.get("slug") or "").strip():
            return entry
        time.sleep(2)
    raise RuntimeError(
        "Switch Vision Discovery repository is registered, but its repository-backed app "
        "did not become available in the Home Assistant store within 60 seconds."
    )


def ensure_discovery_repository(progress: Progress | None = None) -> dict[str, Any]:
    """Ensure the official repository-backed Discovery app is available."""
    existing = _repository_entry_for(DISCOVERY_REPOSITORY)
    added = False

    if existing is None:
        if progress:
            progress("Adding the Switch Vision Discovery App repository…", 2)
        try:
            installer_core.supervisor_request(
                "/store/repositories",
                method="POST",
                payload={"repository": DISCOVERY_REPOSITORY},
            )
            added = True
        except Exception:
            if _repository_entry_for(DISCOVERY_REPOSITORY) is None:
                raise

    if progress:
        progress("Refreshing the Home Assistant App store…", 4)
    installer_core.reload_addon_store()

    repository_entry = _repository_entry_for(DISCOVERY_REPOSITORY)
    if repository_entry is None:
        raise RuntimeError(
            "Home Assistant did not retain the Switch Vision Discovery App repository "
            "after the App store reload."
        )

    repository_slug = str(repository_entry.get("slug") or "").strip()
    if not repository_slug:
        raise RuntimeError(
            "Home Assistant registered the Switch Vision Discovery repository without "
            "a Supervisor repository slug."
        )

    entry = _discovery_store_entry(repository_slug)
    if entry is None:
        entry = _wait_for_discovery(repository_slug)

    store_slug = str(entry.get("slug") or "").strip()
    if not store_slug:
        raise RuntimeError(
            "Home Assistant returned the Discovery store app without an app slug."
        )

    return {
        "added": added,
        "available": True,
        "slug": store_slug,
        "repository_slug": repository_slug,
        "repository": DISCOVERY_REPOSITORY,
        "version": entry.get("version_latest") or entry.get("version"),
    }

