from __future__ import annotations

from typing import Any, Callable
import time

import installer as installer_core

SNMP2MQTT_REPOSITORY = "https://github.com/zemerdon/switch-vision-snmp2mqtt-addon"
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

