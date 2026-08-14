from __future__ import annotations
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from dataclasses import asdict, is_dataclass
import json, os, threading, time, traceback, urllib.request
import installer as installer_core

INSTALLER_VERSION = str(os.environ.get("SV_INSTALLER_VERSION") or installer_core.INSTALLER_VERSION).strip()
installer_core.INSTALLER_VERSION = INSTALLER_VERSION

from installer import apply_backup_retention, create_manual_backup, delete_backup, discovery_status, download_and_install, dry_run, find_discovery_slug, find_snmp2mqtt_slug, find_unifi2mqtt_slug, install_supervisor_addon, latest_release, list_backups, load_options, reconcile_discovery_repository_app, restore_backup, snmp2mqtt_status, status, unifi2mqtt_status, validate_named_backup
from repository_setup import ensure_discovery_repository, ensure_snmp2mqtt_repository, ensure_unifi2mqtt_repository

WEB_ROOT = Path(os.environ.get("SV_INSTALLER_WEB", "/opt/switch-vision-installer/www"))
UI_PREFERENCES_PATH = Path(os.environ.get("SV_UI_PREFERENCES", "/share/switch_vision/ui-preferences.json"))
UI_DEFAULTS = {"density": "comfortable", "text_size": "normal", "content_width": "standard"}
UI_ALLOWED = {
    "density": {"comfortable", "compact", "dense"},
    "text_size": {"normal", "small"},
    "content_width": {"standard", "wide", "full"},
}
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
operation_lock = threading.Lock()
operation = {"active": False, "kind": None, "message": "Ready.", "percent": 0, "result": None, "error": None}


def installer_ui_preferences() -> dict[str, str]:
    """Read and validate shared Switch Vision Installer UI preferences."""
    values = dict(UI_DEFAULTS)
    try:
        document = json.loads(UI_PREFERENCES_PATH.read_text(encoding="utf-8"))
        installer = document.get("installer", {}) if isinstance(document, dict) else {}
        if isinstance(installer, dict):
            for key, allowed in UI_ALLOWED.items():
                candidate = str(installer.get(key, values[key])).strip().lower()
                if candidate in allowed:
                    values[key] = candidate
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        pass
    return values


def release_history() -> dict[str, object]:
    """Return public Switch Vision GitHub releases newest-first for changelog browsing."""
    options = load_options()
    latest_url = str(options.get("release_api_url") or "").strip()
    base_url = latest_url.split("?", 1)[0].rstrip("/")
    if base_url.endswith("/latest"):
        base_url = base_url[:-len("/latest")]
    if not base_url.endswith("/releases"):
        raise RuntimeError("Configured release API URL does not identify a GitHub releases endpoint.")

    request = urllib.request.Request(
        f"{base_url}?per_page=100",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"Switch-Vision-Installer/{INSTALLER_VERSION}",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if not isinstance(payload, list):
        raise RuntimeError("GitHub release history returned an unexpected response.")

    allow_prerelease = bool(options.get("allow_prerelease"))
    releases: list[dict[str, object]] = []
    for item in payload:
        if not isinstance(item, dict) or item.get("draft"):
            continue
        if item.get("prerelease") and not allow_prerelease:
            continue
        version = str(item.get("tag_name") or item.get("name") or "").strip().lstrip("v")
        if not version:
            continue
        releases.append({
            "version": version,
            "name": item.get("name") or item.get("tag_name"),
            "published_at": item.get("published_at"),
            "html_url": item.get("html_url"),
            "changelog": item.get("body") or "",
        })
    return {"releases": releases}


def set_progress(message: str, percent: int) -> None:
    operation.update(message=message, percent=max(0, min(100, int(percent))))


def install_switch_vision():
    repository_warnings: list[str] = []

    # Discovery is required. Repository setup must succeed before we can
    # report a successful Switch Vision installation.
    try:
        discovery_repository = ensure_discovery_repository(set_progress)
    except Exception as exc:
        raise RuntimeError(
            "Switch Vision Discovery repository setup failed: " + str(exc)
        ) from exc

    try:
        ensure_snmp2mqtt_repository(set_progress)
    except Exception as exc:
        repository_warnings.append(
            "The SNMP2MQTT App repository could not be registered automatically: " + str(exc)
        )

    # Reserve the final 10% for Supervisor-managed app reconciliation.
    result = download_and_install(
        lambda message, percent: set_progress(message, min(90, max(5, int(percent * 0.9))))
    )

    set_progress("Reconciling Switch Vision Discovery…", 91)
    try:
        discovery_result = reconcile_discovery_repository_app(
            str(discovery_repository.get("slug") or ""),
            set_progress,
        )
    except Exception as exc:
        raise RuntimeError(
            "Switch Vision files were installed, but Discovery migration failed. "
            "The Installer will not report success until repository-backed Discovery "
            "is installed and started. "
            "This can be temporary while Home Assistant refreshes the App store or "
            "a new Discovery image becomes available. "
            "Wait about one minute, then click Reinstall to retry Discovery. "
            "Components that are already current will be left unchanged. "
            "If Discovery still fails after another attempt, check Home Assistant "
            "Supervisor logs for details. "
            "Original error: " + str(exc)
        ) from exc

    expected_slug = str(discovery_repository.get("slug") or "").strip()
    actual_slug = str(discovery_result.get("slug") or "").strip()
    actual_state = str(discovery_result.get("state") or "").strip().lower()
    if (
        not discovery_result.get("installed")
        or actual_slug != expected_slug
        or actual_state != "started"
    ):
        raise RuntimeError(
            "Discovery migration verification failed: "
            f"expected repository app {expected_slug!r} in state 'started', "
            f"received slug={actual_slug!r}, state={actual_state!r}."
        )

    expected_version = installer_core.normalise_version(
        discovery_repository.get("version")
    )
    actual_version = installer_core.normalise_version(
        discovery_result.get("version")
    )
    if expected_version and actual_version != expected_version:
        raise RuntimeError(
            "Discovery migration version verification failed: "
            f"expected v{expected_version}, received v{actual_version or 'unknown'}."
        )

    if discovery_result.get("migrated"):
        result.installed.append("Discovery app (migrated to repository)")
    elif discovery_result.get("installed_now"):
        result.installed.append("Discovery app")
    elif discovery_result.get("updated"):
        result.installed.append("Discovery app update")
    else:
        result.unchanged.append("Discovery app")

    try:
        snmp = snmp2mqtt_status()
        if not snmp.get("installed"):
            set_progress("Installing Switch Vision SNMP2MQTT…", 99)
            install_supervisor_addon("snmp2mqtt")
    except Exception as exc:
        result.warnings.append(
            "Switch Vision installed, but SNMP2MQTT could not be installed automatically: "
            + str(exc)
        )

    result.warnings.extend(repository_warnings)
    installer_core.STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    installer_core.STATE_PATH.write_text(
        json.dumps(asdict(result), indent=2) + "\n",
        encoding="utf-8",
    )
    return result

def supervisor_request(path: str, method: str = "POST") -> dict:
    if not SUPERVISOR_TOKEN:
        raise RuntimeError("Supervisor API token is unavailable.")
    request = urllib.request.Request(
        f"http://supervisor{path}",
        method=method,
        headers={
            "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
        if not raw:
            return {"ok": True, "status": response.status}
        content_type = response.headers.get("Content-Type", "")
        if "json" in content_type.lower():
            return json.loads(raw.decode("utf-8"))
        text = raw.decode("utf-8", errors="replace").strip()
        return {"ok": True, "status": response.status, "message": text[:500]}


def request_core_restart_async() -> None:
    # Return the ingress response before Core restarts and interrupts the connection.
    time.sleep(0.75)
    try:
        supervisor_request("/core/restart")
    except Exception:
        traceback.print_exc()


class OperationBusyError(RuntimeError):
    pass


def _reserve_operation(kind: str) -> bool:
    if not operation_lock.acquire(blocking=False):
        return False
    operation.update(
        active=True, kind=kind, message="Starting…", percent=1, result=None, error=None
    )
    return True


def _finish_operation() -> None:
    operation["active"] = False
    operation_lock.release()


def _run_reserved_job(kind: str, fn) -> None:
    try:
        result = fn()
        operation["result"] = asdict(result) if is_dataclass(result) else result
        operation["percent"] = 100
    except Exception as exc:
        traceback.print_exc()
        operation["error"] = str(exc)
        operation["message"] = f"{kind.title()} failed."
    finally:
        _finish_operation()


def start_job(kind: str, fn) -> bool:
    # Reserve the mutation slot before returning HTTP 202.
    if not _reserve_operation(kind):
        return False
    try:
        threading.Thread(
            target=_run_reserved_job, args=(kind, fn), daemon=True
        ).start()
    except Exception:
        _finish_operation()
        raise
    return True


def run_job(kind: str, fn) -> None:
    # Compatibility entry point used by older callers.
    if not _reserve_operation(kind):
        return
    _run_reserved_job(kind, fn)


def run_locked(kind: str, fn):
    if not _reserve_operation(kind):
        raise OperationBusyError("Another installer operation is already running.")
    try:
        result = fn()
        operation["result"] = asdict(result) if is_dataclass(result) else result
        operation["percent"] = 100
        return result
    except Exception as exc:
        operation["error"] = str(exc)
        operation["message"] = f"{kind.title()} failed."
        raise
    finally:
        _finish_operation()


class Handler(BaseHTTPRequestHandler):
    server_version = f"SwitchVisionInstaller/{INSTALLER_VERSION}"
    def log_message(self, fmt: str, *args: object) -> None: print(f"[web] {self.address_string()} {fmt % args}", flush=True)
    def send_json(self, payload: object, code: int = 200) -> None:
        data=json.dumps(payload,indent=2).encode(); self.send_response(code); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
    def body(self) -> dict:
        length=int(self.headers.get("Content-Length","0")); return json.loads(self.rfile.read(length).decode() or "{}")
    def do_GET(self) -> None:
        path=self.path.split("?",1)[0]
        try:
            if path=="/api/status": return self.send_json(status())
            if path=="/api/latest": return self.send_json(latest_release())
            if path=="/api/releases": return self.send_json(release_history())
            if path=="/api/backups": return self.send_json({"backups":list_backups()})
            if path=="/api/operation": return self.send_json(dict(operation))
            if path=="/api/ui-preferences": return self.send_json(installer_ui_preferences())
            filename="index.html" if path in {"/",""} else path.lstrip("/"); target=(WEB_ROOT/filename).resolve(); root=WEB_ROOT.resolve()
            if root not in target.parents and target!=root: return self.send_error(403)
            if not target.is_file(): return self.send_error(404)
            types={".html":"text/html; charset=utf-8",".js":"application/javascript; charset=utf-8",".css":"text/css; charset=utf-8"}; data=target.read_bytes(); self.send_response(200); self.send_header("Content-Type",types.get(target.suffix,"text/plain")); self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
        except Exception as exc: self.send_json({"ok":False,"error":str(exc)},500)
    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        try:
            if path == "/api/install":
                if not start_job("install", install_switch_vision):
                    return self.send_json({"ok": False, "error": "Another installer operation is already running."}, 409)
                return self.send_json({"ok": True, "started": True}, 202)
            if path == "/api/dry-run":
                if not start_job("dry run", lambda: dry_run(set_progress)):
                    return self.send_json({"ok": False, "error": "Another installer operation is already running."}, 409)
                return self.send_json({"ok": True, "started": True}, 202)
            if path == "/api/create-backup":
                if not start_job("backup", lambda: create_manual_backup(set_progress)):
                    return self.send_json({"ok": False, "error": "Another installer operation is already running."}, 409)
                return self.send_json({"ok": True, "started": True}, 202)
            if path == "/api/validate-backup":
                payload = self.body()
                name = str(payload.get("name") or "")
                if not start_job("backup validation", lambda: validate_named_backup(name, set_progress)):
                    return self.send_json({"ok": False, "error": "Another installer operation is already running."}, 409)
                return self.send_json({"ok": True, "started": True}, 202)
            if path == "/api/restore":
                payload = self.body()
                name = str(payload.get("name") or "")
                if not start_job("restore", lambda: restore_backup(name, set_progress)):
                    return self.send_json({"ok": False, "error": "Another installer operation is already running."}, 409)
                return self.send_json({"ok": True, "started": True}, 202)
            if path == "/api/delete-backup":
                name = str(self.body().get("name") or "")
                return self.send_json(run_locked("delete backup", lambda: delete_backup(name)))
            if path == "/api/prune-backups":
                return self.send_json(run_locked("prune backups", apply_backup_retention))
            if path == "/api/restart-core":
                if not start_job("restart core", request_core_restart_async):
                    return self.send_json({"ok": False, "error": "Another installer operation is already running."}, 409)
                return self.send_json({"ok": True, "requested": True, "message": "Home Assistant Core restart requested."}, 202)
            if path == "/api/install-discovery":
                def install_discovery_action():
                    repository = ensure_discovery_repository()
                    result = reconcile_discovery_repository_app(str(repository.get("slug") or ""))
                    return {"ok": True, "requested": True, **result}
                return self.send_json(run_locked("install discovery", install_discovery_action))
            if path == "/api/restart-discovery":
                return self.send_json(run_locked("restart discovery", lambda: {"ok": True, "requested": True, "supervisor": supervisor_request(f"/addons/{find_discovery_slug()}/restart")}))
            if path == "/api/install-snmp2mqtt":
                def install_snmp_action():
                    ensure_snmp2mqtt_repository()
                    result = install_supervisor_addon("snmp2mqtt")
                    return {"ok": True, "requested": True, **result}
                return self.send_json(run_locked("install snmp2mqtt", install_snmp_action))
            if path == "/api/restart-snmp2mqtt":
                return self.send_json(run_locked("restart snmp2mqtt", lambda: {"ok": True, "requested": True, "supervisor": supervisor_request(f"/addons/{find_snmp2mqtt_slug()}/restart")}))
            if path == "/api/install-unifi2mqtt":
                def install_unifi_action():
                    ensure_unifi2mqtt_repository()
                    result = install_supervisor_addon("unifi2mqtt")
                    return {"ok": True, "requested": True, **result}
                return self.send_json(run_locked("install unifi2mqtt", install_unifi_action))
            if path == "/api/restart-unifi2mqtt":
                return self.send_json(run_locked("restart unifi2mqtt", lambda: {"ok": True, "requested": True, "supervisor": supervisor_request(f"/addons/{find_unifi2mqtt_slug()}/restart")}))
            self.send_error(404)
        except OperationBusyError as exc:
            self.send_json({"ok": False, "error": str(exc)}, 409)
        except Exception as exc:
            traceback.print_exc()
            self.send_json({"ok": False, "error": str(exc)}, 500)
if __name__=="__main__":
    print(f"Switch Vision Installer {INSTALLER_VERSION} listening on 0.0.0.0:8099",flush=True); ThreadingHTTPServer(("0.0.0.0",8099),Handler).serve_forever()
