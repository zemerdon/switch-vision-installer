"""Permanent restart UI / Supervisor safety regression for Installer v2.1.48."""
from __future__ import annotations

import ast
from html.parser import HTMLParser
from pathlib import Path
import subprocess
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
WWW = ROOT / "switch_vision_installer" / "www"
APP = ROOT / "switch_vision_installer" / "app"
index = (WWW / "index.html").read_text(encoding="utf-8")
manager_js = (WWW / "component-manager.js").read_text(encoding="utf-8")
installer_js = (WWW / "installer.js").read_text(encoding="utf-8")
css = (WWW / "component-manager.css").read_text(encoding="utf-8")
web = (APP / "web.py").read_text(encoding="utf-8")


class IdCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []

    def handle_starttag(self, tag, attrs):
        self.ids.extend(value for name, value in attrs if name == "id")


parser = IdCollector()
parser.feed(index)
assert len(parser.ids) == len(set(parser.ids)), "Duplicate page control ID"
assert "system-actions-card" not in parser.ids
assert "System actions</h2>" not in index
assert {"check", "components", "result"}.issubset(parser.ids)
assert "install" not in parser.ids
assert index.count('id="check"') == 1
assert index.index('id="check"') < index.index('<section class="grid">')
assert "Core install or reinstall</h2>" not in index
assert "check-updates" in index
assert "$('install')" not in installer_js
assert "function setControls(on){$('check').disabled=on;}" in installer_js
for old in ("restart-core", "restart-discovery", "restart-snmp2mqtt", "restart-unifi2mqtt"):
    assert old not in parser.ids
assert "id=\"result-restart-core\"" in installer_js
assert "requestComponentRestart('core','Home Assistant Core')" in installer_js
assert "function syncSystemActions" not in installer_js
assert "api/reinstall-component" in manager_js
assert "api/component-changelog" in manager_js
assert "api/restart-installer" not in manager_js + web
assert "@media(max-width:1150px)" in css and "@media(max-width:560px)" in css

# Exercise the exact live backend restart gate with a fake Supervisor. No network.
tree = ast.parse(web)
restart = next(
    node for node in tree.body
    if isinstance(node, ast.FunctionDef) and node.name == "restart_running_addon"
)
ns = {}
exec(compile(ast.Module(body=[restart], type_ignores=[]), "<restart-gate>", "exec"), ns)
calls = []
state = {"value": "started", "payload": True, "unavailable": False}


def get_info(path):
    calls.append(("get", path))
    if state["unavailable"]:
        raise RuntimeError("Supervisor unavailable")
    return {"data": {"state": state["value"]}} if state["payload"] else {"data": None}


def post_restart(path):
    calls.append(("post", path))
    return {"data": {"result": "ok"}}


ns.update(
    find_discovery_slug=lambda: "repo_discovery",
    find_snmp2mqtt_slug=lambda: "repo_snmp",
    find_unifi2mqtt_slug=lambda: "repo_unifi",
    installer_core=SimpleNamespace(supervisor_request=get_info),
    supervisor_request=post_restart,
)
for component, slug in (("discovery", "repo_discovery"), ("snmp2mqtt", "repo_snmp"), ("unifi2mqtt", "repo_unifi")):
    calls.clear()
    result = ns["restart_running_addon"](component)
    assert result["requested"] and result["ok"]
    assert calls == [
        ("get", f"/addons/{slug}/info"),
        ("post", f"/addons/{slug}/restart"),
    ], (component, calls)

for variant in ("stopped", "unknown", "missing", "unavailable"):
    calls.clear()
    state.update(value=variant, payload=variant != "missing", unavailable=variant == "unavailable")
    try:
        ns["restart_running_addon"]("discovery")
    except RuntimeError:
        pass
    else:
        raise AssertionError(f"Unsafe restart allowed for state={variant}")
    assert all(kind != "post" for kind, _ in calls), (variant, calls)
state.update(value="running", payload=True, unavailable=False)
calls.clear()
try:
    ns["restart_running_addon"]("installer")
except RuntimeError:
    pass
else:
    raise AssertionError("Installer self-restart must be unsupported")
assert calls == []

for component in ("discovery", "snmp2mqtt", "unifi2mqtt"):
    assert f'lambda: restart_running_addon("{component}")' in web

subprocess.run(
    ["node", "tests/ui_component_restarts.js"],
    cwd=ROOT, check=True, timeout=20,
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
)
print("Installer v2.1.48 component-local restarts and Supervisor safety: PASS")
