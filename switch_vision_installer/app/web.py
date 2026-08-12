from __future__ import annotations
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from dataclasses import asdict, is_dataclass
import json, os, threading, time, traceback, urllib.request
import installer as installer_core

INSTALLER_VERSION = str(os.environ.get("SV_INSTALLER_VERSION") or installer_core.INSTALLER_VERSION).strip()
installer_core.INSTALLER_VERSION = INSTALLER_VERSION

from installer import apply_backup_retention, create_manual_backup, delete_backup, discovery_status, download_and_install, dry_run, find_discovery_slug, find_snmp2mqtt_slug, find_unifi2mqtt_slug, get_unifi2mqtt_options, install_supervisor_addon, latest_release, list_backups, load_options, restore_backup, set_unifi2mqtt_options, snmp2mqtt_status, status, unifi2mqtt_status, validate_named_backup
from repository_setup import ensure_snmp2mqtt_repository, ensure_unifi2mqtt_repository

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
    repository_warning = None
    try:
        ensure_snmp2mqtt_repository(set_progress)
    except Exception as exc:
        repository_warning = str(exc)

    result = download_and_install(set_progress)

    # Fresh-install convenience: only install Supervisor apps that are missing.
    try:
        discovery = discovery_status()
        if not discovery.get("installed"):
            set_progress("Installing Switch Vision Discovery…", 96)
            install_supervisor_addon("discovery")
    except Exception as exc:
        result.warnings.append(
            "Switch Vision installed, but Discovery could not be installed automatically: "
            + str(exc)
        )

    try:
        snmp = snmp2mqtt_status()
        if not snmp.get("installed"):
            set_progress("Installing Switch Vision SNMP2MQTT…", 98)
            install_supervisor_addon("snmp2mqtt")
    except Exception as exc:
        result.warnings.append(
            "Switch Vision installed, but SNMP2MQTT could not be installed automatically: "
            + str(exc)
        )

    if repository_warning:
        result.warnings.append(
            "Switch Vision installed, but the SNMP2MQTT App repository could not be registered automatically: "
            + repository_warning
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


def _bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def unifi2mqtt_public_config() -> dict[str, object]:
    state = unifi2mqtt_status()
    if not state.get("installed"):
        return {
            "installed": False,
            "state": state.get("state"),
            "options": {},
            "api_key_set": False,
            "mqtt_password_set": False,
        }

    options = get_unifi2mqtt_options() or {}
    public = {
        "controller_url": str(options.get("controller_url") or ""),
        "site_id": str(options.get("site_id") or ""),
        "verify_ssl": _bool_value(options.get("verify_ssl")),
        "poll_interval": int(options.get("poll_interval") or 30),
        "mqtt_host": str(options.get("mqtt_host") or "core-mosquitto"),
        "mqtt_port": int(options.get("mqtt_port") or 1883),
        "mqtt_username": str(options.get("mqtt_username") or ""),
        "mqtt_topic_prefix": str(options.get("mqtt_topic_prefix") or "switch_vision/unifi"),
        "mqtt_discovery_prefix": str(options.get("mqtt_discovery_prefix") or "homeassistant"),
    }
    return {
        "installed": True,
        "state": state.get("state"),
        "options": public,
        "api_key_set": bool(str(options.get("api_key") or "").strip()),
        "mqtt_password_set": bool(str(options.get("mqtt_password") or "").strip()),
    }


def configure_and_start_unifi2mqtt(payload: dict[str, object]) -> dict[str, object]:
    state = unifi2mqtt_status()
    if not state.get("installed"):
        raise RuntimeError("Install Switch Vision UniFi2MQTT before configuring it.")

    current = get_unifi2mqtt_options() or {}
    controller_url = str(payload.get("controller_url") or "").strip().rstrip("/")
    site_id = str(payload.get("site_id") or "").strip()
    api_key_new = str(payload.get("api_key") or "").strip()
    api_key = api_key_new or str(current.get("api_key") or "").strip()
    mqtt_host = str(payload.get("mqtt_host") or "").strip()
    mqtt_username = str(payload.get("mqtt_username") or "").strip()
    mqtt_password_new = str(payload.get("mqtt_password") or "")
    mqtt_password = mqtt_password_new if mqtt_password_new else str(current.get("mqtt_password") or "")
    mqtt_topic_prefix = str(payload.get("mqtt_topic_prefix") or "").strip().strip("/")
    mqtt_discovery_prefix = str(payload.get("mqtt_discovery_prefix") or "").strip().strip("/")

    if not controller_url:
        raise RuntimeError("Controller URL is required.")
    if not controller_url.lower().startswith(("http://", "https://")):
        raise RuntimeError("Controller URL must begin with http:// or https://.")
    if not site_id:
        raise RuntimeError("Site ID is required.")
    if not api_key:
        raise RuntimeError("API key is required.")
    if not mqtt_host:
        raise RuntimeError("MQTT host is required.")
    if not mqtt_topic_prefix:
        raise RuntimeError("MQTT topic prefix is required.")
    if not mqtt_discovery_prefix:
        raise RuntimeError("MQTT discovery prefix is required.")

    try:
        poll_interval = int(payload.get("poll_interval") or 30)
    except (TypeError, ValueError):
        raise RuntimeError("Poll interval must be a number.")
    if not 10 <= poll_interval <= 300:
        raise RuntimeError("Poll interval must be between 10 and 300 seconds.")

    try:
        mqtt_port = int(payload.get("mqtt_port") or 1883)
    except (TypeError, ValueError):
        raise RuntimeError("MQTT port must be a number.")
    if not 1 <= mqtt_port <= 65535:
        raise RuntimeError("MQTT port must be between 1 and 65535.")

    options = {
        "controller_url": controller_url,
        "site_id": site_id,
        "api_key": api_key,
        "verify_ssl": "true" if _bool_value(payload.get("verify_ssl")) else "false",
        "poll_interval": str(poll_interval),
        "mqtt_host": mqtt_host,
        "mqtt_port": str(mqtt_port),
        "mqtt_username": mqtt_username,
        "mqtt_password": mqtt_password,
        "mqtt_topic_prefix": mqtt_topic_prefix,
        "mqtt_discovery_prefix": mqtt_discovery_prefix,
    }
    set_unifi2mqtt_options(options)

    slug = find_unifi2mqtt_slug()
    if str(state.get("state") or "").lower() == "started":
        installer_core.supervisor_request(f"/addons/{slug}/restart", method="POST")
    else:
        installer_core.supervisor_request(f"/addons/{slug}/start", method="POST")

    final = installer_core.wait_for_addon(slug, expected_state="started", timeout=120)
    return {
        "ok": True,
        "slug": slug,
        "state": final.get("state"),
        "version": final.get("version"),
        "api_key_set": True,
        "mqtt_password_set": bool(mqtt_password),
        "message": "UniFi2MQTT configuration saved and the add-on is running.",
    }


def request_core_restart_async() -> None:
    # Return the ingress response before Core restarts and interrupts the connection.
    time.sleep(0.75)
    try:
        supervisor_request("/core/restart")
    except Exception:
        traceback.print_exc()


def run_job(kind: str, fn) -> None:
    if not operation_lock.acquire(blocking=False): return
    operation.update(active=True, kind=kind, message="Starting…", percent=1, result=None, error=None)
    try:
        result = fn()
        operation["result"] = asdict(result) if is_dataclass(result) else result
        operation["percent"] = 100
    except Exception as exc: traceback.print_exc(); operation["error"] = str(exc); operation["message"] = f"{kind.title()} failed."
    finally: operation["active"] = False; operation_lock.release()


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
            if path=="/api/unifi2mqtt-config": return self.send_json(unifi2mqtt_public_config())
            filename="index.html" if path in {"/",""} else path.lstrip("/"); target=(WEB_ROOT/filename).resolve(); root=WEB_ROOT.resolve()
            if root not in target.parents and target!=root: return self.send_error(403)
            if not target.is_file(): return self.send_error(404)
            types={".html":"text/html; charset=utf-8",".js":"application/javascript; charset=utf-8",".css":"text/css; charset=utf-8"}; data=target.read_bytes(); self.send_response(200); self.send_header("Content-Type",types.get(target.suffix,"text/plain")); self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
        except Exception as exc: self.send_json({"ok":False,"error":str(exc)},500)
    def do_POST(self) -> None:
        path=self.path.split("?",1)[0]
        try:
            if path=="/api/install":
                if operation["active"]: return self.send_json({"ok":False,"error":"Another installer operation is already running."},409)
                threading.Thread(target=run_job,args=("install",install_switch_vision),daemon=True).start(); return self.send_json({"ok":True,"started":True},202)
            if path=="/api/dry-run":
                if operation["active"]: return self.send_json({"ok":False,"error":"Another installer operation is already running."},409)
                threading.Thread(target=run_job,args=("dry run",lambda:dry_run(set_progress)),daemon=True).start(); return self.send_json({"ok":True,"started":True},202)
            if path=="/api/create-backup":
                if operation["active"]: return self.send_json({"ok":False,"error":"Another installer operation is already running."},409)
                threading.Thread(target=run_job,args=("backup",lambda:create_manual_backup(set_progress)),daemon=True).start(); return self.send_json({"ok":True,"started":True},202)
            if path=="/api/validate-backup":
                payload=self.body(); name=str(payload.get("name") or "")
                if operation["active"]: return self.send_json({"ok":False,"error":"Another installer operation is already running."},409)
                threading.Thread(target=run_job,args=("backup validation",lambda:validate_named_backup(name,set_progress)),daemon=True).start(); return self.send_json({"ok":True,"started":True},202)
            if path=="/api/restore":
                payload=self.body(); name=str(payload.get("name") or "")
                if operation["active"]: return self.send_json({"ok":False,"error":"Another installer operation is already running."},409)
                threading.Thread(target=run_job,args=("restore",lambda:restore_backup(name,set_progress)),daemon=True).start(); return self.send_json({"ok":True,"started":True},202)
            if path=="/api/delete-backup": return self.send_json(delete_backup(str(self.body().get("name") or "")))
            if path=="/api/prune-backups": return self.send_json(apply_backup_retention())
            if path=="/api/restart-core":
                threading.Thread(target=request_core_restart_async, daemon=True).start()
                return self.send_json({"ok":True,"requested":True,"message":"Home Assistant Core restart requested."},202)
            if path=="/api/install-discovery":
                result = install_supervisor_addon("discovery")
                return self.send_json({"ok":True,"requested":True,**result})
            if path=="/api/restart-discovery":
                result = supervisor_request(f"/addons/{find_discovery_slug()}/restart")
                return self.send_json({"ok":True,"requested":True,"supervisor":result})
            if path=="/api/install-snmp2mqtt":
                ensure_snmp2mqtt_repository()
                result = install_supervisor_addon("snmp2mqtt")
                return self.send_json({"ok":True,"requested":True,**result})
            if path=="/api/restart-snmp2mqtt":
                result = supervisor_request(f"/addons/{find_snmp2mqtt_slug()}/restart")
                return self.send_json({"ok":True,"requested":True,"supervisor":result})
            if path=="/api/install-unifi2mqtt":
                ensure_unifi2mqtt_repository()
                result = install_supervisor_addon("unifi2mqtt")
                return self.send_json({"ok":True,"requested":True,**result})
            if path=="/api/restart-unifi2mqtt":
                result = supervisor_request(f"/addons/{find_unifi2mqtt_slug()}/restart")
                return self.send_json({"ok":True,"requested":True,"supervisor":result})
            if path=="/api/configure-unifi2mqtt":
                payload = self.body()
                result = configure_and_start_unifi2mqtt(payload)
                return self.send_json(result)
            self.send_error(404)
        except Exception as exc: traceback.print_exc(); self.send_json({"ok":False,"error":str(exc)},500)


if __name__=="__main__":
    print(f"Switch Vision Installer {INSTALLER_VERSION} listening on 0.0.0.0:8099",flush=True); ThreadingHTTPServer(("0.0.0.0",8099),Handler).serve_forever()
