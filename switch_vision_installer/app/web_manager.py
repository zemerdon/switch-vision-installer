from __future__ import annotations

from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
import web as legacy_web
from component_manager import _set_repository_compatibility, component_changelog, component_status, update_all, update_component


class Handler(legacy_web.Handler):
    server_version = f"SwitchVisionInstaller/{legacy_web.INSTALLER_VERSION}"

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        try:
            if parsed.path == "/api/components":
                return self.send_json(component_status())
            if parsed.path == "/api/component-changelog":
                component = str(parse_qs(parsed.query).get("component", [""])[0]).strip()
                return self.send_json(component_changelog(component))
        except Exception as exc:
            return self.send_json({"ok": False, "error": str(exc)}, 500)
        return super().do_GET()

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        try:
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
    print(f"Switch Vision Installer v{legacy_web.INSTALLER_VERSION} component manager listening on 0.0.0.0:8099", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8099), Handler).serve_forever()
