from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
import json
import re
import time
import urllib.error
import urllib.request

import installer as installer_core
import repository_setup

Progress = Callable[[str, int], None]


@dataclass(frozen=True)
class ComponentSpec:
    component_id: str
    label: str
    kind: str
    repositories: tuple[str, ...]
    config_path: str | None = None
    changelog_path: str | None = None
    optional: bool = False
    min_core: str | None = None


# These are the permanent public repository identities used by Switch Vision.
# No GitHub repository rename is pending.
COMPONENTS: tuple[ComponentSpec, ...] = (
    ComponentSpec(
        "core",
        "Switch Vision Core",
        "core",
        ("switch-vision-releases",),
    ),
    ComponentSpec(
        "discovery",
        "Switch Vision Discovery",
        "addon",
        ("switch-vision-discovery",),
        "switch_vision_discovery/config.yaml",
        "switch_vision_discovery/CHANGELOG.md",
        min_core="2.1.5",
    ),
    ComponentSpec(
        "snmp2mqtt",
        "Switch Vision SNMP2MQTT",
        "addon",
        ("switch-vision-snmp2mqtt-addon",),
        "switch-vision-snmp2mqtt/config.yaml",
        "switch-vision-snmp2mqtt/CHANGELOG.md",
    ),
    ComponentSpec(
        "unifi2mqtt",
        "Switch Vision UniFi2MQTT",
        "addon",
        ("switch-vision-unifi2mqtt",),
        "switch-vision-unifi2mqtt/config.yaml",
        "switch-vision-unifi2mqtt/CHANGELOG.md",
        optional=True,
    ),
    ComponentSpec(
        "installer",
        "Switch Vision Installer",
        "installer",
        ("switch-vision-installer",),
        "switch_vision_installer/config.yaml",
        "switch_vision_installer/CHANGELOG.md",
    ),
)

_CACHE: dict[str, tuple[float, Any]] = {}
CACHE_SECONDS = 45


def _cached(key: str, loader):
    now = time.monotonic()
    item = _CACHE.get(key)
    if item and now - item[0] < CACHE_SECONDS:
        return item[1]
    value = loader()
    _CACHE[key] = (now, value)
    return value


def clear_cache() -> None:
    _CACHE.clear()


def _github_request(url: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"Switch-Vision-Installer/{installer_core.INSTALLER_VERSION}",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def _raw_text(repository: str, path: str) -> str:
    url = f"https://raw.githubusercontent.com/zemerdon/{repository}/main/{path}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": f"Switch-Vision-Installer/{installer_core.INSTALLER_VERSION}"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", errors="replace")


def _yaml_version(text: str) -> str:
    match = re.search(r"(?mi)^\s*version\s*:\s*[\"']?([^\"'\s#]+)", text)
    return installer_core.normalise_version(match.group(1)) if match else ""


def _spec(component_id: str) -> ComponentSpec:
    for spec in COMPONENTS:
        if spec.component_id == component_id:
            return spec
    raise RuntimeError(f"Unknown Switch Vision component: {component_id}")


def resolve_repository(spec: ComponentSpec) -> str:
    """Resolve the configured public repository for a component.

    Add-on repositories are validated by their expected Home Assistant app config
    path so an unrelated source repository cannot be selected accidentally.
    """
    def loader() -> str:
        for repository in spec.repositories:
            try:
                if spec.kind == "core":
                    _github_request(
                        f"https://api.github.com/repos/zemerdon/{repository}/releases/latest"
                    )
                elif spec.config_path:
                    text = _raw_text(repository, spec.config_path)
                    if not _yaml_version(text):
                        continue
                else:
                    _github_request(f"https://api.github.com/repos/zemerdon/{repository}")
                return repository
            except Exception:
                continue
        # Return the canonical name for display, but callers that need network
        # content will still surface the underlying lookup error.
        return spec.repositories[0]

    return _cached(f"repo:{spec.component_id}", loader)


def repository_url(spec: ComponentSpec) -> str:
    return f"https://github.com/zemerdon/{resolve_repository(spec)}"


def _remote_version(spec: ComponentSpec) -> str:
    repository = resolve_repository(spec)
    if spec.kind == "core":
        payload = _github_request(
            f"https://api.github.com/repos/zemerdon/{repository}/releases/latest"
        )
        return installer_core.normalise_version(payload.get("tag_name") or payload.get("name"))
    if not spec.config_path:
        return ""
    return _yaml_version(_raw_text(repository, spec.config_path))


def _installed_addon_status(component_id: str) -> dict[str, Any]:
    if component_id == "discovery":
        return installer_core.discovery_status()
    if component_id == "snmp2mqtt":
        return installer_core.snmp2mqtt_status()
    if component_id == "unifi2mqtt":
        return installer_core.unifi2mqtt_status()
    raise RuntimeError(f"Unsupported app component: {component_id}")


def _version_parts(value: str | None) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", installer_core.normalise_version(value))
    return tuple(int(number) for number in numbers) if numbers else ()


def compare_versions(left: str | None, right: str | None) -> int:
    a, b = list(_version_parts(left)), list(_version_parts(right))
    width = max(len(a), len(b))
    a += [0] * (width - len(a))
    b += [0] * (width - len(b))
    return (a > b) - (a < b)


def _component_status(spec: ComponentSpec) -> dict[str, Any]:
    latest = ""
    remote_error = None
    try:
        latest = _cached(f"latest:{spec.component_id}", lambda: _remote_version(spec))
    except Exception as exc:
        remote_error = str(exc)

    installed = False
    installed_version = ""
    state = "not_installed"
    slug = None

    if spec.kind == "core":
        installed_version = installer_core.normalise_version(installer_core.installed_version())
        installed = bool(installed_version or installer_core.COMPONENT_DIR.is_dir())
        state = "installed" if installed else "not_installed"
    elif spec.kind == "installer":
        installed = True
        installed_version = installer_core.normalise_version(installer_core.INSTALLER_VERSION)
        state = "started"
        try:
            addon = installer_core._find_addon(
                lambda candidate_slug, name: (
                    candidate_slug.endswith("switch_vision_installer")
                    or "switch-vision-installer" in candidate_slug
                    or name == "switch vision installer"
                ),
                include_store=False,
            )
            slug = str(addon.get("slug") or "") if addon else None
        except Exception:
            slug = None
    else:
        addon = _installed_addon_status(spec.component_id)
        installed = bool(addon.get("installed"))
        installed_version = installer_core.normalise_version(addon.get("version"))
        state = str(addon.get("state") or ("installed" if installed else "not_installed"))
        slug = addon.get("slug")

    update_available = bool(
        installed and latest and installed_version and compare_versions(installed_version, latest) < 0
    )
    newer_local = bool(
        installed and latest and installed_version and compare_versions(installed_version, latest) > 0
    )

    dependency_ok = True
    dependency_note = None
    if spec.min_core:
        core_version = installer_core.normalise_version(installer_core.installed_version())
        dependency_ok = bool(core_version and compare_versions(core_version, spec.min_core) >= 0)
        if not dependency_ok:
            installed_core = f"v{core_version}" if core_version else "not installed"
            dependency_note = (
                f"Requires Switch Vision Core v{spec.min_core}+ · "
                f"Installed Core: {installed_core}"
            )

    if remote_error:
        status = "unavailable"
    elif not installed:
        status = "optional" if spec.optional else "not_installed"
    elif not dependency_ok:
        status = "dependency_mismatch"
    elif update_available:
        status = "update_available"
    elif newer_local:
        status = "newer_local"
    else:
        status = "up_to_date"

    return {
        "id": spec.component_id,
        "label": spec.label,
        "kind": spec.kind,
        "installed": installed,
        "installed_version": installed_version or None,
        "latest_version": latest or None,
        "state": state,
        "status": status,
        "update_available": update_available,
        "newer_local": newer_local,
        "optional": spec.optional,
        "slug": slug,
        "canonical_repository": f"https://github.com/zemerdon/{spec.repositories[0]}",
        "active_repository": repository_url(spec),
        "dependency_ok": dependency_ok,
        "dependency_note": dependency_note,
        "remote_error": remote_error,
        "external_update": spec.kind == "installer",
        "update_hint": (
            "Update from Home Assistant Settings → Apps"
            if spec.kind == "installer" else None
        ),
    }


def component_status() -> dict[str, Any]:
    rows = [_component_status(spec) for spec in COMPONENTS]
    by_id = {row["id"]: row for row in rows}
    actionable = [
        row for row in rows
        if (row["update_available"] and row["id"] != "installer")
        or (not row["installed"] and not row["optional"] and row["id"] != "installer")
    ]
    blocked_reason = None
    discovery = by_id.get("discovery", {})
    core = by_id.get("core", {})
    discovery_needs_action = bool(
        discovery.get("update_available")
        or not discovery.get("installed", True)
        or not discovery.get("dependency_ok", True)
    )
    if discovery_needs_action and not discovery.get("dependency_ok", True):
        requirement = _spec("discovery").min_core or ""
        core_latest = core.get("latest_version")
        if not core_latest or compare_versions(core_latest, requirement) < 0:
            blocked_reason = (
                f"Discovery requires Switch Vision Core v{requirement}+, but the latest "
                f"published Core is v{core_latest or 'unavailable'}. Publish/update Core first."
            )
    # Optional UniFi2MQTT is never installed by Update All when the user has not
    # opted into it. The running Installer cannot safely replace itself; its
    # update remains visible but Home Assistant must perform that app update.
    return {
        "components": rows,
        "updates_available": len([row for row in rows if row["update_available"]]),
        "actions_available": len(actionable),
        "update_all_blocked": bool(blocked_reason),
        "update_all_blocked_reason": blocked_reason,
        "update_order": ["core", "discovery", "snmp2mqtt", "unifi2mqtt"],
        "installer_update_external": True,
    }


def component_changelog(component_id: str) -> dict[str, Any]:
    spec = _spec(component_id)
    repository = resolve_repository(spec)
    if spec.kind == "core":
        payload = _github_request(
            f"https://api.github.com/repos/zemerdon/{repository}/releases?per_page=100"
        )
        if not isinstance(payload, list):
            raise RuntimeError("Core release history returned an unexpected response.")
        sections: list[str] = []
        for release in payload:
            if not isinstance(release, dict) or release.get("draft"):
                continue
            if release.get("prerelease") and not installer_core.load_options().get("allow_prerelease"):
                continue
            version = installer_core.normalise_version(
                release.get("tag_name") or release.get("name")
            )
            if not version:
                continue
            body = str(release.get("body") or "").strip()
            sections.append(f"## v{version}\n\n{body or 'No release notes published.'}")
        text = "\n\n".join(sections)
    else:
        if not spec.changelog_path:
            text = "No changelog source is configured for this component."
        else:
            text = _raw_text(repository, spec.changelog_path)
    return {
        "id": spec.component_id,
        "label": spec.label,
        "repository": f"https://github.com/zemerdon/{repository}",
        "changelog": text,
        "latest_version": _component_status(spec).get("latest_version"),
        "installed_version": _component_status(spec).get("installed_version"),
    }


def _registered_repository_url(spec: ComponentSpec) -> str | None:
    """Prefer an already-registered matching repository URL to avoid duplicates."""
    try:
        entries = repository_setup._repository_list()
        normalise = repository_setup._normalise_repo_url
    except Exception:
        return None
    accepted = {
        normalise(f"https://github.com/zemerdon/{name}")
        for name in spec.repositories
    }
    for item in entries:
        if not isinstance(item, dict):
            continue
        for key in ("source", "url"):
            value = str(item.get(key) or "").strip()
            if value and normalise(value) in accepted:
                return value.rstrip("/")
    return None


def _set_repository_compatibility() -> None:
    """Point installer repository helpers at registered or configured URLs."""
    for component_id, attribute in (
        ("snmp2mqtt", "SNMP2MQTT_REPOSITORY"),
        ("discovery", "DISCOVERY_REPOSITORY"),
        ("unifi2mqtt", "UNIFI2MQTT_REPOSITORY"),
    ):
        try:
            spec = _spec(component_id)
            selected = _registered_repository_url(spec) or repository_url(spec)
            setattr(repository_setup, attribute, selected)
        except Exception:
            pass


def _addon_update(component_id: str, progress: Progress | None = None) -> dict[str, Any]:
    _set_repository_compatibility()
    spec = _spec(component_id)
    expected_version = installer_core.normalise_version(_remote_version(spec))

    if component_id == "discovery":
        if progress:
            progress("Checking the Discovery repository…", 15)
        repo = repository_setup.ensure_discovery_repository(progress)
        result = installer_core.reconcile_discovery_repository_app(
            str(repo.get("slug") or ""), progress
        )
        actual = installer_core.normalise_version(result.get("version"))
        if expected_version and actual != expected_version:
            raise RuntimeError(
                f"Discovery repository advertises v{expected_version}, but Supervisor "
                f"started v{actual or 'unknown'}. The new app image may still be publishing; "
                "wait about one minute and retry."
            )
        return {
            "ok": True,
            "version": actual,
            "installed": ["Switch Vision Discovery"],
            "unchanged": (
                [] if result.get("updated") or result.get("installed_now")
                else ["Switch Vision Discovery"]
            ),
            "required_actions": [],
            "component_update": component_id,
        }

    if component_id == "snmp2mqtt":
        if progress:
            progress("Checking the SNMP2MQTT repository…", 15)
        repository_setup.ensure_snmp2mqtt_repository(progress)
        installer_core.reload_addon_store()
        find_slug = installer_core.find_snmp2mqtt_slug
        install_kind = "snmp2mqtt"
    elif component_id == "unifi2mqtt":
        if progress:
            progress("Checking the UniFi2MQTT repository…", 15)
        repository_setup.ensure_unifi2mqtt_repository(progress)
        installer_core.reload_addon_store()
        find_slug = installer_core.find_unifi2mqtt_slug
        install_kind = "unifi2mqtt"
    else:
        raise RuntimeError(f"Unsupported repository app: {component_id}")

    try:
        slug = find_slug(include_store=False)
        info = installer_core.addon_info(slug)
        installed = True
    except Exception:
        slug = find_slug(include_store=True)
        info = {}
        installed = False

    if not installed:
        if progress:
            progress(f"Installing {component_id} v{expected_version or 'latest'}…", 45)
        installer_core.install_supervisor_addon(install_kind)
        info = installer_core.wait_for_addon(
            slug, expected_version=expected_version or None, timeout=300
        )
    else:
        current = installer_core.normalise_version(info.get("version"))
        should_update = bool(
            expected_version and current and compare_versions(current, expected_version) < 0
        ) or bool(info.get("update_available"))
        if should_update:
            was_started = str(info.get("state") or "").lower() == "started"
            if progress:
                progress(f"Updating {component_id} to v{expected_version or 'latest'}…", 55)
            installer_core.supervisor_store_request(
                f"/store/addons/{slug}/update",
                payload={"backup": False, "background": False},
                progress=progress,
            )
            info = installer_core.wait_for_addon(
                slug, expected_version=expected_version or None, timeout=300
            )
            if was_started and str(info.get("state") or "").lower() != "started":
                installer_core.supervisor_request(
                    f"/addons/{slug}/start", method="POST"
                )
                info = installer_core.wait_for_addon(
                    slug, expected_state="started", timeout=180
                )

    actual_version = installer_core.normalise_version(info.get("version"))
    if expected_version and actual_version != expected_version:
        raise RuntimeError(
            f"{spec.label} repository advertises v{expected_version}, but Supervisor "
            f"has v{actual_version or 'unknown'}. The new app image may still be "
            "publishing; wait about one minute and retry."
        )

    clear_cache()
    return {
        "ok": True,
        "version": actual_version,
        "installed": [spec.label],
        "unchanged": [],
        "required_actions": [],
        "component_update": component_id,
    }

def _installer_slug() -> str:
    addon = installer_core._find_addon(
        lambda slug, name: (
            slug.endswith("switch_vision_installer")
            or "switch-vision-installer" in slug
            or name == "switch vision installer"
        ),
        include_store=False,
    )
    if not addon:
        raise RuntimeError("Switch Vision Installer could not locate its Supervisor app slug.")
    return str(addon.get("slug") or "")


def _installer_update(progress: Progress | None = None) -> dict[str, Any]:
    status = _component_status(_spec("installer"))
    current = installer_core.normalise_version(status.get("installed_version"))
    latest = installer_core.normalise_version(status.get("latest_version"))
    if progress:
        progress("Installer update must be completed from Home Assistant Apps.", 100)
    return {
        "ok": True,
        "version": current,
        "installed": [],
        "unchanged": ["Switch Vision Installer"],
        "required_actions": (
            [f"Update Switch Vision Installer to v{latest} from Home Assistant Settings → Apps."]
            if latest and compare_versions(current, latest) < 0
            else []
        ),
        "component_update": "installer",
        "self_update_external": True,
    }


def update_component(component_id: str, progress: Progress | None = None) -> dict[str, Any]:
    spec = _spec(component_id)
    status = _component_status(spec)

    if spec.min_core and not status.get("dependency_ok"):
        raise RuntimeError(
            f"{spec.label} cannot be updated yet. {status.get('dependency_note')}. "
            "Update Switch Vision Core first or use Update All."
        )

    if spec.kind == "core":
        if progress:
            progress("Updating Switch Vision Core…", 10)
        result = installer_core.download_and_install(progress)
        clear_cache()
        payload = result.__dict__.copy()
        payload["component_update"] = "core"
        return payload
    if spec.kind == "installer":
        return _installer_update(progress)
    return _addon_update(component_id, progress)


def update_all(progress: Progress | None = None) -> dict[str, Any]:
    snapshot = component_status()
    rows = {row["id"]: row for row in snapshot["components"]}
    changed: list[str] = []
    unchanged: list[str] = []
    warnings: list[str] = []
    required_actions: list[str] = []

    ordered = ["core", "discovery", "snmp2mqtt", "unifi2mqtt"]
    for index, component_id in enumerate(ordered):
        row = rows[component_id]
        # Optional UniFi2MQTT is not implicitly installed by Update All.
        if component_id == "unifi2mqtt" and not row["installed"]:
            unchanged.append("Switch Vision UniFi2MQTT (optional, not installed)")
            continue
        needs_action = bool(row["update_available"])
        if not row["installed"] and component_id not in {"installer", "unifi2mqtt"}:
            needs_action = True
        if not needs_action:
            unchanged.append(row["label"])
            continue

        if progress:
            base = 5 + int(index * 18)
            progress(f"Updating {row['label']}…", min(base, 95))

        # Refresh dependency state after Core changes.
        if component_id == "discovery":
            fresh = _component_status(_spec("discovery"))
            if not fresh.get("dependency_ok"):
                raise RuntimeError(
                    f"Discovery update is blocked after the Core step: {fresh.get('dependency_note')}."
                )

        result = update_component(component_id, progress)
        if result.get("installed"):
            changed.extend(result.get("installed") or [])
        else:
            unchanged.append(row["label"])
        warnings.extend(result.get("warnings") or [])
        required_actions.extend(result.get("required_actions") or [])

    installer_row = rows.get("installer", {})
    if installer_row.get("update_available"):
        latest_installer = installer_row.get("latest_version")
        required_actions.append(
            f"Update Switch Vision Installer to v{latest_installer} from Home Assistant Settings → Apps."
        )
        unchanged.append("Switch Vision Installer (update available in Home Assistant)")

    clear_cache()
    return {
        "ok": True,
        "installed": changed,
        "unchanged": unchanged,
        "warnings": warnings,
        "required_actions": list(dict.fromkeys(required_actions)),
        "component_update": "all",
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


