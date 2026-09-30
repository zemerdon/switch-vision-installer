from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import json
import os
import shutil
import stat
import tempfile


Progress = Callable[[str, int], None]


@dataclass(frozen=True)
class BackupRuntime:
    backup_dir: Path
    backup_policy_path: Path
    legacy_backup_dir: Path
    work_dir: Path
    ha_config: Path
    component_dir: Path
    frontend_dir: Path
    generated_snmp2mqtt_yaml: Path
    installer_version: str
    load_options: Callable[[], dict[str, Any]]
    get_discovery_options: Callable[[], dict[str, Any] | None]
    get_snmp2mqtt_options: Callable[[], dict[str, Any] | None]
    get_unifi2mqtt_options: Callable[[], dict[str, Any] | None]
    set_discovery_options: Callable[..., Any]
    set_snmp2mqtt_options: Callable[[dict[str, Any]], Any]
    set_unifi2mqtt_options: Callable[[dict[str, Any]], Any]
    discovery_status: Callable[[], dict[str, Any]]
    snmp2mqtt_status: Callable[[], dict[str, Any]]
    unifi2mqtt_status: Callable[[], dict[str, Any]]
    installed_version: Callable[[], str | None]
    configured_switch_count: Callable[[dict[str, Any] | None], int]
    unifi2mqtt_options_configured: Callable[[dict[str, Any] | None], bool]
    sha256: Callable[[Path], str]
    replace_tree: Callable[[Path, Path], None]
    copy_backup: Callable[[Path, Path, str], None]
    backup_contents: Callable[[Path], list[str]]
    backup_file_hashes: Callable[[Path], dict[str, str]]
    secure_backup_permissions: Callable[[Path], None]
    validate_backup: Callable[[Path], dict[str, Any]]
    backup_policy: Callable[[], dict[str, Any]]
    prune_backups: Callable[..., dict[str, Any]]
    create_backup: Callable[..., Path | None]
    backup_roots: Callable[[], list[Path]]
    safe_backup_path: Callable[[str], Path]
    restore_backup_contents: Callable[..., dict[str, Any]]
    capture_restore_snapshot: Callable[[Path], dict[str, Any]]
    rollback_restore_snapshot: Callable[[Path, dict[str, Any]], None]


def copy_backup(source: Path, root: Path, label: str) -> None:
    if source.exists():
        shutil.copytree(source, root / label, dirs_exist_ok=True)


def backup_contents(path: Path) -> list[str]:
    entries: list[str] = []
    if (path / "custom_components/switch_vision").is_dir():
        entries.append("Custom component")
    if (path / "www/switch-vision").is_dir():
        entries.append("Dashboard frontend")
    if (path / ".storage/switch_vision_calibrations").is_file():
        entries.append("Calibration storage")
    if (path / "discovery-options.json").is_file():
        entries.append("Discovery configuration")
    if (path / "snmp2mqtt-options.json").is_file():
        entries.append("SNMP2MQTT configuration")
    if (path / "unifi2mqtt-options.json").is_file():
        entries.append("UniFi2MQTT configuration")
    if (path / "share/switch_vision/generated-snmp2mqtt.yaml").is_file():
        entries.append("Generated SNMP2MQTT YAML")
    return entries


def backup_file_hashes(runtime: BackupRuntime, path: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for file in sorted(
        p
        for p in path.rglob("*")
        if p.is_file()
        and p.name not in {"backup.json", "backup-manifest.json"}
    ):
        hashes[file.relative_to(path).as_posix()] = runtime.sha256(file)
    return hashes


def secure_backup_permissions(path: Path) -> None:
    # Supervisor option files inside backups may contain credentials. Fail closed
    # if owner-only permissions cannot be applied and verified.
    entries = [path, *path.rglob("*")]
    for entry in entries:
        if entry.is_symlink():
            raise RuntimeError(f"Backup contains unsupported symbolic link: {entry}")
        mode = 0o700 if entry.is_dir() else 0o600
        try:
            entry.chmod(mode)
            observed = stat.S_IMODE(entry.stat().st_mode)
        except OSError as exc:
            raise RuntimeError(
                f"Could not secure backup permissions for {entry}: {exc}"
            ) from exc
        if observed != mode:
            raise RuntimeError(
                f"Backup permission verification failed for {entry}: "
                f"expected {oct(mode)}, observed {oct(observed)}."
            )


def validate_backup(runtime: BackupRuntime, path: Path) -> dict[str, Any]:
    manifest_path = path / "backup-manifest.json"
    if not manifest_path.is_file():
        # Upgrade older installer backups in place so v1.8.3 and earlier remain restorable.
        manifest = {
            "schema": 1,
            "installer_version": "legacy",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "installed_version": None,
            "files": runtime.backup_file_hashes(path),
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = manifest.get("files")
    if not isinstance(expected, dict):
        raise RuntimeError(
            "Backup validation failed: manifest file list is invalid."
        )
    missing: list[str] = []
    mismatched: list[str] = []
    for relative, digest in expected.items():
        file = path / relative
        if not file.is_file():
            missing.append(relative)
        elif runtime.sha256(file) != digest:
            mismatched.append(relative)
    if missing or mismatched:
        detail: list[str] = []
        if missing:
            detail.append("missing: " + ", ".join(missing[:10]))
        if mismatched:
            detail.append("checksum mismatch: " + ", ".join(mismatched[:10]))
        raise RuntimeError(
            "Backup validation failed (" + "; ".join(detail) + ")."
        )
    runtime.secure_backup_permissions(path)
    return {"ok": True, "file_count": len(expected), "manifest": manifest}


def backup_policy(runtime: BackupRuntime) -> dict[str, Any]:
    """Return the Installer-owned retention policy without exposing backups."""
    path = runtime.backup_policy_path
    if path.exists():
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("Installer backup policy is not a regular file.")
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Installer backup policy is unreadable: {exc}"
            ) from exc
        if (
            not isinstance(document, dict)
            or document.get("schema") != "switch-vision-installer-backup-policy-v1"
        ):
            raise RuntimeError(
                "Installer backup policy has an unsupported schema."
            )
        automatic = document.get("automatic_retention")
        retention = document.get("retention_count")
        if not isinstance(automatic, bool):
            raise RuntimeError(
                "Installer backup policy automatic_retention is invalid."
            )
        if (
            isinstance(retention, bool)
            or not isinstance(retention, int)
            or not 1 <= retention <= 10
        ):
            raise RuntimeError(
                "Installer backup policy retention_count must be 1 through 10."
            )
        return {
            "automatic_retention": automatic,
            "retention_count": retention,
        }

    # Pre-v2.1.31 retention was always automatic. Preserve the previous count
    # as the first Maintenance default, clamped to the new 1-10 contract.
    try:
        legacy_retention = int(
            runtime.load_options().get("backup_retention", 5)
        )
    except (TypeError, ValueError):
        legacy_retention = 5
    return {
        "automatic_retention": True,
        "retention_count": max(1, min(10, legacy_retention)),
    }


def save_backup_policy(
    runtime: BackupRuntime,
    automatic_retention: Any,
    retention_count: Any,
) -> dict[str, Any]:
    if not isinstance(automatic_retention, bool):
        raise ValueError("Automatic backup retention must be true or false.")
    if (
        isinstance(retention_count, bool)
        or not isinstance(retention_count, int)
        or not 1 <= retention_count <= 10
    ):
        raise ValueError("Retained backup count must be between 1 and 10.")

    payload = {
        "schema": "switch-vision-installer-backup-policy-v1",
        "automatic_retention": automatic_retention,
        "retention_count": retention_count,
    }
    path = runtime.backup_policy_path
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / f".{path.name}.{os.getpid()}.tmp"
    try:
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temp.chmod(0o600)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()
    return {
        "automatic_retention": automatic_retention,
        "retention_count": retention_count,
    }


def prune_backups(
    runtime: BackupRuntime,
    *,
    force: bool = False,
) -> dict[str, Any]:
    policy = runtime.backup_policy()
    keep = int(policy["retention_count"])
    paths = sorted(
        (p for p in runtime.backup_dir.iterdir() if p.is_dir()),
        reverse=True,
    )
    if not force and not policy["automatic_retention"]:
        return {
            "ok": True,
            "automatic_retention": False,
            "retention": keep,
            "retention_skipped": True,
            "removed": [],
            "remaining": len(paths),
        }

    removed: list[str] = []
    for old in paths[keep:]:
        removed.append(old.name)
        shutil.rmtree(old, ignore_errors=True)
    return {
        "ok": True,
        "automatic_retention": bool(policy["automatic_retention"]),
        "retention": keep,
        "retention_skipped": False,
        "removed": removed,
        "remaining": max(0, len(paths) - len(removed)),
    }


def apply_backup_retention(runtime: BackupRuntime) -> dict[str, Any]:
    runtime.backup_dir.mkdir(parents=True, exist_ok=True)
    result = runtime.prune_backups(force=True)
    result["backup_path"] = str(runtime.backup_dir)
    return result


def create_backup(
    runtime: BackupRuntime,
    force: bool = False,
) -> Path | None:
    if not force and not runtime.load_options().get("create_backup", True):
        return None
    runtime.backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    target = runtime.backup_dir / f"switch-vision-{stamp}"
    target.mkdir(parents=True, exist_ok=False)
    target.chmod(0o700)
    runtime.copy_backup(
        runtime.component_dir,
        target,
        "custom_components/switch_vision",
    )
    runtime.copy_backup(
        runtime.frontend_dir,
        target,
        "www/switch-vision",
    )
    discovery_options = runtime.get_discovery_options()
    if discovery_options is not None:
        (target / "discovery-options.json").write_text(
            json.dumps(discovery_options, indent=2) + "\n",
            encoding="utf-8",
        )
    snmp2mqtt_options = runtime.get_snmp2mqtt_options()
    if snmp2mqtt_options is not None:
        (target / "snmp2mqtt-options.json").write_text(
            json.dumps(snmp2mqtt_options, indent=2) + "\n",
            encoding="utf-8",
        )
    unifi2mqtt_options = runtime.get_unifi2mqtt_options()
    unifi2mqtt_configuration_saved = runtime.unifi2mqtt_options_configured(
        unifi2mqtt_options
    )
    unifi2mqtt_configuration_skipped_unconfigured = (
        unifi2mqtt_options is not None
        and not unifi2mqtt_configuration_saved
    )
    if unifi2mqtt_configuration_saved:
        (target / "unifi2mqtt-options.json").write_text(
            json.dumps(unifi2mqtt_options, indent=2) + "\n",
            encoding="utf-8",
        )
    if runtime.generated_snmp2mqtt_yaml.is_file():
        yaml_target = (
            target
            / "share"
            / "switch_vision"
            / runtime.generated_snmp2mqtt_yaml.name
        )
        yaml_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(runtime.generated_snmp2mqtt_yaml, yaml_target)
    storage = (
        runtime.ha_config / ".storage" / "switch_vision_calibrations"
    )
    if storage.exists():
        (target / ".storage").mkdir(parents=True, exist_ok=True)
        shutil.copy2(storage, target / ".storage" / storage.name)
    meta = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "installed_version": runtime.installed_version(),
        "contents": runtime.backup_contents(target),
        "discovery_configuration_saved": discovery_options is not None,
        "configured_switches": runtime.configured_switch_count(
            discovery_options
        ),
        "snmp2mqtt_configuration_saved": snmp2mqtt_options is not None,
        "unifi2mqtt_configuration_saved": unifi2mqtt_configuration_saved,
        "unifi2mqtt_configuration_skipped_unconfigured": (
            unifi2mqtt_configuration_skipped_unconfigured
        ),
        "snmp2mqtt_generated_yaml_saved": (
            runtime.generated_snmp2mqtt_yaml.is_file()
        ),
    }
    (target / "backup.json").write_text(
        json.dumps(meta, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema": 1,
        "installer_version": runtime.installer_version,
        "created_at": meta["created_at"],
        "installed_version": meta["installed_version"],
        "files": runtime.backup_file_hashes(target),
    }
    (target / "backup-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    runtime.validate_backup(target)
    runtime.prune_backups()
    return target


def create_manual_backup(
    runtime: BackupRuntime,
    progress: Progress | None = None,
) -> dict[str, Any]:
    if progress:
        progress("Collecting Switch Vision files and settings…", 15)
    target = runtime.create_backup(force=True)
    if target is None:
        raise RuntimeError("Backup creation did not return a backup path.")
    if progress:
        progress("Validating backup checksums…", 80)
    validation = runtime.validate_backup(target)
    meta: dict[str, Any] = {}
    try:
        meta = json.loads(
            (target / "backup.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        pass
    if progress:
        progress("Backup created and verified.", 100)
    return {
        "ok": True,
        "backup_created": True,
        "backup": target.name,
        "backup_path": str(target),
        "verified": True,
        "file_count": validation.get("file_count", 0),
        "version": meta.get("installed_version"),
        "contents": meta.get("contents")
        or runtime.backup_contents(target),
        "configured_switches": int(
            meta.get("configured_switches") or 0
        ),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


def validate_named_backup(
    runtime: BackupRuntime,
    name: str,
    progress: Progress | None = None,
) -> dict[str, Any]:
    backup = runtime.safe_backup_path(name)
    if progress:
        progress(f"Validating {name}…", 25)
    validation = runtime.validate_backup(backup)
    if progress:
        progress("Backup validation completed.", 100)
    return {
        "ok": True,
        "backup_validated": True,
        "backup": name,
        "verified": True,
        "file_count": validation.get("file_count", 0),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


def backup_roots(runtime: BackupRuntime) -> list[Path]:
    # Only Installer-private /data backups are trusted for validation, restore,
    # retention, and deletion. Historical shared backups are intentionally left
    # untouched but are not a privileged restore source.
    return [runtime.backup_dir]


def list_backups(runtime: BackupRuntime) -> list[dict[str, Any]]:
    runtime.backup_dir.mkdir(parents=True, exist_ok=True)
    result: list[dict[str, Any]] = []
    paths: list[Path] = []
    for root in runtime.backup_roots():
        paths.extend(p for p in root.iterdir() if p.is_dir())
    for path in sorted(paths, key=lambda p: p.name, reverse=True):
        meta: dict[str, Any] = {}
        try:
            meta = json.loads(
                (path / "backup.json").read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            pass
        result.append(
            {
                "name": path.name,
                "path": str(path),
                "legacy_location": path.parent == runtime.legacy_backup_dir,
                "created_at": meta.get("created_at"),
                "version": meta.get("installed_version"),
                "contents": meta.get("contents")
                or runtime.backup_contents(path),
                "discovery_configuration_saved": bool(
                    meta.get("discovery_configuration_saved")
                ),
                "configured_switches": int(
                    meta.get("configured_switches") or 0
                ),
                "snmp2mqtt_configuration_saved": bool(
                    meta.get("snmp2mqtt_configuration_saved")
                ),
                "unifi2mqtt_configuration_saved": bool(
                    meta.get("unifi2mqtt_configuration_saved")
                ),
                "unifi2mqtt_configuration_skipped_unconfigured": bool(
                    meta.get(
                        "unifi2mqtt_configuration_skipped_unconfigured"
                    )
                ),
                "snmp2mqtt_generated_yaml_saved": bool(
                    meta.get("snmp2mqtt_generated_yaml_saved")
                ),
            }
        )
    return result


def safe_backup_path(runtime: BackupRuntime, name: str) -> Path:
    if not name or Path(name).name != name:
        raise RuntimeError("Invalid backup name.")
    for root in runtime.backup_roots():
        path = (root / name).resolve()
        resolved_root = root.resolve()
        if resolved_root in path.parents and path.is_dir():
            return path
    raise RuntimeError("Backup not found.")


def delete_backup(runtime: BackupRuntime, name: str) -> dict[str, Any]:
    path = runtime.safe_backup_path(name)
    shutil.rmtree(path)
    return {"ok": True, "deleted": name}


def restore_backup_contents(
    runtime: BackupRuntime,
    name: str,
    progress: Progress | None = None,
) -> dict[str, Any]:
    backup = runtime.safe_backup_path(name)
    runtime.validate_backup(backup)
    restored: list[str] = []
    skipped: list[str] = []
    mappings = [
        (
            backup / "custom_components/switch_vision",
            runtime.component_dir,
            "Custom component",
        ),
        (
            backup / "www/switch-vision",
            runtime.frontend_dir,
            "Dashboard frontend",
        ),
    ]
    for idx, (source, destination, label) in enumerate(
        mappings, start=1
    ):
        if source.is_dir():
            if progress:
                progress(f"Restoring {label}…", 20 + idx * 18)
            runtime.replace_tree(source, destination)
            restored.append(label)
    discovery_options_file = backup / "discovery-options.json"
    if discovery_options_file.is_file():
        options = json.loads(
            discovery_options_file.read_text(encoding="utf-8")
        )
        if isinstance(options, dict):
            if progress:
                progress("Restoring Discovery configuration…", 82)
            runtime.set_discovery_options(options)
            restored.append(
                "Discovery configuration "
                f"({runtime.configured_switch_count(options)} switches)"
            )
    snmp2mqtt_options_file = backup / "snmp2mqtt-options.json"
    if snmp2mqtt_options_file.is_file():
        options = json.loads(
            snmp2mqtt_options_file.read_text(encoding="utf-8")
        )
        if isinstance(options, dict):
            if progress:
                progress("Restoring SNMP2MQTT configuration…", 86)
            runtime.set_snmp2mqtt_options(options)
            restored.append("SNMP2MQTT configuration")
    unifi2mqtt_options_file = backup / "unifi2mqtt-options.json"
    if unifi2mqtt_options_file.is_file():
        options = json.loads(
            unifi2mqtt_options_file.read_text(encoding="utf-8")
        )
        if isinstance(options, dict):
            if runtime.unifi2mqtt_options_configured(options):
                if progress:
                    progress("Restoring UniFi2MQTT configuration…", 90)
                runtime.set_unifi2mqtt_options(options)
                restored.append("UniFi2MQTT configuration")
            else:
                skipped.append(
                    "UniFi2MQTT configuration "
                    "(backup contains unconfigured defaults)"
                )
    generated_yaml = (
        backup / "share" / "switch_vision" / "generated-snmp2mqtt.yaml"
    )
    if generated_yaml.is_file():
        runtime.generated_snmp2mqtt_yaml.parent.mkdir(
            parents=True, exist_ok=True
        )
        shutil.copy2(
            generated_yaml,
            runtime.generated_snmp2mqtt_yaml,
        )
        restored.append("Generated SNMP2MQTT YAML")
    storage = backup / ".storage" / "switch_vision_calibrations"
    if storage.is_file():
        target = runtime.ha_config / ".storage" / storage.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(storage, target)
        restored.append("Calibration storage")
    if not restored:
        raise RuntimeError(
            "The selected backup contains no restorable Switch Vision components."
        )
    actions: list[str] = []
    if "Custom component" in restored:
        actions.append("Restart Home Assistant Core")
    if any(
        item.startswith("Discovery configuration") for item in restored
    ):
        actions.append("Restart Switch Vision Discovery")
    if (
        "SNMP2MQTT configuration" in restored
        or "Generated SNMP2MQTT YAML" in restored
    ):
        actions.append("Restart Switch Vision SNMP2MQTT")
    if "UniFi2MQTT configuration" in restored:
        actions.append(
            "Restart Switch Vision UniFi2MQTT if it is running"
        )
    if "Dashboard frontend" in restored:
        actions.append("Hard-refresh the browser")
    return {
        "ok": True,
        "backup": name,
        "restored": restored,
        "skipped": skipped,
        "required_actions": actions,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


def capture_restore_snapshot(
    runtime: BackupRuntime,
    path: Path,
) -> dict[str, Any]:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    meta = {
        "component_present": runtime.component_dir.is_dir(),
        "frontend_present": runtime.frontend_dir.is_dir(),
        "generated_yaml_present": (
            runtime.generated_snmp2mqtt_yaml.is_file()
        ),
        "calibration_present": (
            runtime.ha_config
            / ".storage"
            / "switch_vision_calibrations"
        ).is_file(),
    }
    runtime.copy_backup(
        runtime.component_dir,
        path,
        "custom_components/switch_vision",
    )
    runtime.copy_backup(
        runtime.frontend_dir,
        path,
        "www/switch-vision",
    )

    for filename, getter, status_getter, label in (
        (
            "discovery-options.json",
            runtime.get_discovery_options,
            runtime.discovery_status,
            "Discovery",
        ),
        (
            "snmp2mqtt-options.json",
            runtime.get_snmp2mqtt_options,
            runtime.snmp2mqtt_status,
            "SNMP2MQTT",
        ),
        (
            "unifi2mqtt-options.json",
            runtime.get_unifi2mqtt_options,
            runtime.unifi2mqtt_status,
            "UniFi2MQTT",
        ),
    ):
        status = status_getter()
        installed = (
            bool(status.get("installed"))
            if isinstance(status, dict)
            else False
        )
        options = getter()
        if installed and not isinstance(options, dict):
            raise RuntimeError(
                f"Cannot start transactional restore because current {label} "
                "options could not be captured safely."
            )
        if isinstance(options, dict):
            (path / filename).write_text(
                json.dumps(options, indent=2) + "\n",
                encoding="utf-8",
            )

    if runtime.generated_snmp2mqtt_yaml.is_file():
        target = (
            path
            / "share"
            / "switch_vision"
            / runtime.generated_snmp2mqtt_yaml.name
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(runtime.generated_snmp2mqtt_yaml, target)

    calibration = (
        runtime.ha_config / ".storage" / "switch_vision_calibrations"
    )
    if calibration.is_file():
        target = path / ".storage" / calibration.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(calibration, target)

    runtime.secure_backup_permissions(path)
    return meta


def rollback_restore_snapshot(
    runtime: BackupRuntime,
    path: Path,
    meta: dict[str, Any],
) -> None:
    for present_key, source, destination in (
        (
            "component_present",
            path / "custom_components" / "switch_vision",
            runtime.component_dir,
        ),
        (
            "frontend_present",
            path / "www" / "switch-vision",
            runtime.frontend_dir,
        ),
    ):
        if meta.get(present_key) and source.is_dir():
            runtime.replace_tree(source, destination)
        elif not meta.get(present_key) and destination.exists():
            shutil.rmtree(destination)

    for filename, setter in (
        (
            "discovery-options.json",
            lambda value: runtime.set_discovery_options(value),
        ),
        ("snmp2mqtt-options.json", runtime.set_snmp2mqtt_options),
        ("unifi2mqtt-options.json", runtime.set_unifi2mqtt_options),
    ):
        source = path / filename
        if source.is_file():
            value = json.loads(source.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                setter(value)

    snapshot_yaml = (
        path / "share" / "switch_vision" / "generated-snmp2mqtt.yaml"
    )
    if (
        meta.get("generated_yaml_present")
        and snapshot_yaml.is_file()
    ):
        runtime.generated_snmp2mqtt_yaml.parent.mkdir(
            parents=True, exist_ok=True
        )
        shutil.copy2(
            snapshot_yaml,
            runtime.generated_snmp2mqtt_yaml,
        )
    elif (
        not meta.get("generated_yaml_present")
        and runtime.generated_snmp2mqtt_yaml.exists()
    ):
        runtime.generated_snmp2mqtt_yaml.unlink()

    calibration = (
        runtime.ha_config / ".storage" / "switch_vision_calibrations"
    )
    snapshot_calibration = (
        path / ".storage" / "switch_vision_calibrations"
    )
    if (
        meta.get("calibration_present")
        and snapshot_calibration.is_file()
    ):
        calibration.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(snapshot_calibration, calibration)
    elif (
        not meta.get("calibration_present")
        and calibration.exists()
    ):
        calibration.unlink()


def restore_backup(
    runtime: BackupRuntime,
    name: str,
    progress: Progress | None = None,
) -> dict[str, Any]:
    backup = runtime.safe_backup_path(name)
    runtime.validate_backup(backup)
    runtime.work_dir.mkdir(parents=True, exist_ok=True)
    safety = Path(
        tempfile.mkdtemp(
            prefix="restore-safety-",
            dir=runtime.work_dir,
        )
    )
    meta = runtime.capture_restore_snapshot(safety)
    try:
        result = runtime.restore_backup_contents(name, progress)
        result["transactional_restore"] = True
        return result
    except Exception as exc:
        try:
            runtime.rollback_restore_snapshot(safety, meta)
        except Exception as rollback_exc:
            raise RuntimeError(
                f"Restore failed: {exc}. "
                "Automatic safety rollback also failed: "
                f"{rollback_exc}"
            ) from exc
        raise RuntimeError(
            f"Restore failed: {exc}. Previous files/settings were restored "
            "from the temporary safety snapshot."
        ) from exc
    finally:
        shutil.rmtree(safety, ignore_errors=True)
