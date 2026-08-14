from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WWW = ROOT / "switch_vision_installer" / "www"
APP = ROOT / "switch_vision_installer" / "app"

index = (WWW / "index.html").read_text(encoding="utf-8")
installer_js = (WWW / "installer.js").read_text(encoding="utf-8")
manager_js = (WWW / "component-manager.js").read_text(encoding="utf-8")
config = (ROOT / "switch_vision_installer" / "config.yaml").read_text(encoding="utf-8")
backend = (APP / "installer.py").read_text(encoding="utf-8")

assert 'version: "2.1.17"' in config
assert 'INSTALLER_VERSION = "2.1.17"' in backend

assert 'id="show-changelog"' not in index
assert 'changelog-history.js' not in index
assert not (WWW / "changelog-history.js").exists()
assert "legacyChangelog=$('show-changelog')" not in manager_js

assert 'id="install-unifi2mqtt" class="secondary hidden"' in index
assert "function syncSystemActions" in installer_js
assert "$('install-unifi2mqtt').classList.toggle('hidden',unifiInstalled||!s.unifi2mqtt_available)" in installer_js
assert "$('restart-unifi2mqtt').classList.toggle('hidden',!unifiInstalled)" in installer_js
assert "$('restart-discovery').classList.toggle('hidden',!discoveryInstalled)" in installer_js
assert "$('restart-snmp2mqtt').classList.toggle('hidden',!snmpInstalled)" in installer_js

assert "Restart Home Assistant Core required" in installer_js
assert 'id="result-restart-core"' in installer_js
assert "resultSummaryWithCoreRestart(op.result)" in installer_js

print("Installer v2.1.17 UI/state regressions: PASS")
