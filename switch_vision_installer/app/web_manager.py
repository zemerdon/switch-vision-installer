from __future__ import annotations

from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit
import json
import os
import re
import sys
import threading

import web as legacy_web
from component_manager import _set_repository_compatibility, component_changelog, component_status_with_releases, refresh_component_sources, reinstall_component, update_all, update_component


SUPERVISOR_INGRESS_IP = "172.30.32.2"
MAINTENANCE_SCHEMA = "switch-vision-installer-maintenance-v1"
MAINTENANCE_RESPONSE_PATH = Path(
    os.environ.get(
        "SV_INSTALLER_MAINTENANCE_RESPONSE",
        "/share/switch_vision/installer-maintenance-response.json",
    )
)
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,79}$")
MAINTENANCE_ACTIONS = {
    "status",
    "set_policy",
    "create_backup",
    "validate_backup",
    "restore_backup",
    "delete_backup",
    "apply_retention",
}
BACKUP_METADATA_FIELDS = {
    "name",
    "created_at",
    "version",
    "contents",
    "discovery_configuration_saved",
    "configured_switches",
    "snmp2mqtt_configuration_saved",
    "unifi2mqtt_configuration_saved",
    "unifi2mqtt_configuration_skipped_unconfigured",
    "snmp2mqtt_generated_yaml_saved",
}
OPERATION_RESULT_FIELDS = {
    "ok",
    "backup_created",
    "backup_validated",
    "backup",
    "verified",
    "file_count",
    "version",
    "contents",
    "configured_switches",
    "completed_at",
    "restored",
    "skipped",
    "required_actions",
    "deleted",
    "retention",
    "automatic_retention",
    "removed",
    "remaining",
    "retention_skipped",
}


def _sanitized_backup(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    return {key: item[key] for key in BACKUP_METADATA_FIELDS if key in item}


def _sanitized_operation_result(result: Any) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    return {key: result[key] for key in OPERATION_RESULT_FIELDS if key in result}


def maintenance_snapshot() -> dict[str, Any]:
    policy = legacy_web.installer_core.backup_policy()
    operation = dict(legacy_web.operation)
    operation["result"] = _sanitized_operation_result(operation.get("result"))
    return {
        "ok": True,
        "installer_version": legacy_web.INSTALLER_VERSION,
        "automatic_retention": bool(policy["automatic_retention"]),
        "retention_count": int(policy["retention_count"]),
        "backups": [
            _sanitized_backup(item)
            for item in legacy_web.installer_core.list_backups()
        ],
        "operation": operation,
    }


def _write_maintenance_response(request_id: str, payload: dict[str, Any]) -> None:
    MAINTENANCE_RESPONSE_PATH.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "schema": MAINTENANCE_SCHEMA,
        "request_id": request_id,
        **payload,
    }
    temp = MAINTENANCE_RESPONSE_PATH.parent / (
        f".{MAINTENANCE_RESPONSE_PATH.name}.{os.getpid()}.tmp"
    )
    try:
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temp.chmod(0o600)
        os.replace(temp, MAINTENANCE_RESPONSE_PATH)
    finally:
        if temp.exists():
            temp.unlink()


def _parse_maintenance_request(raw: bytes) -> dict[str, Any]:
    if not raw or len(raw) > 64 * 1024:
        raise ValueError("Maintenance request size is invalid.")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Maintenance request must contain valid JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Maintenance request must be a JSON object.")
    if payload.get("schema") != MAINTENANCE_SCHEMA:
        raise ValueError("Unsupported maintenance request schema.")
    request_id = str(payload.get("request_id") or "").strip()
    if not REQUEST_ID_RE.fullmatch(request_id):
        raise ValueError("Maintenance request ID is invalid.")
    action = str(payload.get("action") or "").strip()
    if action not in MAINTENANCE_ACTIONS:
        raise ValueError("Unsupported maintenance action.")
    return payload


def _require_backup_name(payload: dict[str, Any]) -> str:
    name = payload.get("name")
    if not isinstance(name, str) or not name or len(name) > 160:
        raise ValueError("Backup name is invalid.")
    if Path(name).name != name:
        raise ValueError("Backup name is invalid.")
    return name


def _save_policy(payload: dict[str, Any]) -> dict[str, Any]:
    automatic = payload.get("automatic_retention")
    retention = payload.get("retention_count")
    policy = legacy_web.installer_core.save_backup_policy(automatic, retention)
    cleanup = None
    if policy["automatic_retention"]:
        cleanup = legacy_web.installer_core.apply_backup_retention()
    return {
        "ok": True,
        "automatic_retention": policy["automatic_retention"],
        "retention": policy["retention_count"],
        "removed": list((cleanup or {}).get("removed") or []),
        "remaining": (cleanup or {}).get("remaining"),
    }


def _handle_maintenance_request(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload["action"])
    if action == "status":
        return maintenance_snapshot()
    if action == "set_policy":
        legacy_web.run_locked("backup policy", lambda: _save_policy(payload))
        return maintenance_snapshot()
    if action == "create_backup":
        if not legacy_web.start_job(
            "backup", lambda: legacy_web.create_manual_backup(legacy_web.set_progress)
        ):
            raise RuntimeError("Another installer operation is already running.")
        return maintenance_snapshot()
    if action == "validate_backup":
        name = _require_backup_name(payload)
        if not legacy_web.start_job(
            "backup validation",
            lambda: legacy_web.validate_named_backup(name, legacy_web.set_progress),
        ):
            raise RuntimeError("Another installer operation is already running.")
        return maintenance_snapshot()
    if action == "restore_backup":
        name = _require_backup_name(payload)
        if not legacy_web.start_job(
            "restore", lambda: legacy_web.restore_backup(name, legacy_web.set_progress)
        ):
            raise RuntimeError("Another installer operation is already running.")
        return maintenance_snapshot()
    if action == "delete_backup":
        name = _require_backup_name(payload)
        legacy_web.run_locked(
            "delete backup", lambda: legacy_web.delete_backup(name)
        )
        return maintenance_snapshot()
    if action == "apply_retention":
        legacy_web.run_locked(
            "backup retention", legacy_web.apply_backup_retention
        )
        return maintenance_snapshot()
    raise ValueError("Unsupported maintenance action.")


def _stdin_maintenance_loop(stream=None) -> None:
    source = stream if stream is not None else sys.stdin.buffer
    for raw_line in source:
        raw = raw_line.strip()
        if not raw:
            continue
        request_id = "invalid"
        try:
            payload = _parse_maintenance_request(raw)
            request_id = str(payload["request_id"])
            response = _handle_maintenance_request(payload)
        except Exception as exc:
            response = {"ok": False, "error": str(exc)}
        try:
            _write_maintenance_response(request_id, response)
        except Exception as exc:
            print(
                f"Switch Vision Installer maintenance response failed: {exc}",
                file=sys.stderr,
                flush=True,
            )


class Handler(legacy_web.Handler):
    server_version = f"SwitchVisionInstaller/{legacy_web.INSTALLER_VERSION}"

    def _allow_ingress_request(self) -> bool:
        if self.client_address[0] == SUPERVISOR_INGRESS_IP:
            return True
        self.send_json({"ok": False, "error": "Forbidden"}, 403)
        return False

    def do_GET(self) -> None:
        if not self._allow_ingress_request():
            return
        parsed = urlsplit(self.path)
        try:
            if parsed.path == "/api/components":
                return self.send_json(component_status_with_releases())
            if parsed.path == "/api/component-changelog":
                component = str(parse_qs(parsed.query).get("component", [""])[0]).strip()
                return self.send_json(component_changelog(component))
        except Exception as exc:
            return self.send_json({"ok": False, "error": str(exc)}, 500)
        return super().do_GET()

    def do_POST(self) -> None:
        if not self._allow_ingress_request():
            return
        parsed = urlsplit(self.path)
        try:
            if parsed.path == "/api/check-components":
                return self.send_json(refresh_component_sources())
            if parsed.path in {
                "/api/install",
                "/api/install-discovery",
                "/api/install-snmp2mqtt",
                "/api/install-unifi2mqtt",
            }:
                _set_repository_compatibility()
            if parsed.path == "/api/update-component":
                payload = self.body()
                component = str(payload.get("component") or "").strip()
                if not legacy_web.start_job(
                    f"update {component}",
                    lambda: update_component(component, legacy_web.set_progress),
                ):
                    return self.send_json(
                        {"ok": False, "error": "Another installer operation is already running."},
                        409,
                    )
                return self.send_json({"ok": True, "started": True, "component": component}, 202)
            if parsed.path == "/api/reinstall-component":
                payload = self.body()
                component = str(payload.get("component") or "").strip()
                if not legacy_web.start_job(
                    f"reinstall {component}",
                    lambda: reinstall_component(component, legacy_web.set_progress),
                ):
                    return self.send_json(
                        {"ok": False, "error": "Another installer operation is already running."},
                        409,
                    )
                return self.send_json({"ok": True, "started": True, "component": component}, 202)
            if parsed.path == "/api/update-all":
                if not legacy_web.start_job(
                    "update all",
                    lambda: update_all(legacy_web.set_progress),
                ):
                    return self.send_json(
                        {"ok": False, "error": "Another installer operation is already running."},
                        409,
                    )
                return self.send_json({"ok": True, "started": True}, 202)
        except Exception as exc:
            return self.send_json({"ok": False, "error": str(exc)}, 500)
        return super().do_POST()


if __name__ == "__main__":
    recovered = legacy_web.installer_core.recover_interrupted_tree_replacements()
    if recovered:
        print(
            "Recovered interrupted Switch Vision filesystem replacement(s): "
            + ", ".join(recovered),
            flush=True,
        )
    threading.Thread(
        target=_stdin_maintenance_loop,
        name="switch-vision-installer-maintenance",
        daemon=True,
    ).start()
    print(
        f"Switch Vision Installer v{legacy_web.INSTALLER_VERSION} component manager listening on 0.0.0.0:8099",
        flush=True,
    )
    ThreadingHTTPServer(("0.0.0.0", 8099), Handler).serve_forever()
