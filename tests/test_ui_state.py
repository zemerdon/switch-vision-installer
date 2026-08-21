from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
WWW = ROOT / "switch_vision_installer" / "www"
APP = ROOT / "switch_vision_installer" / "app"

index = (WWW / "index.html").read_text(encoding="utf-8")
installer_js = (WWW / "installer.js").read_text(encoding="utf-8")
manager_js = (WWW / "component-manager.js").read_text(encoding="utf-8")
config = (ROOT / "switch_vision_installer" / "config.yaml").read_text(encoding="utf-8")
dockerfile = (ROOT / "switch_vision_installer" / "Dockerfile").read_text(encoding="utf-8")
web = (APP / "web.py").read_text(encoding="utf-8")

config_version = re.search(r'(?m)^version:\s*["\']?([^"\'\s#]+)', config).group(1)
assert 'ENV SV_INSTALLER_VERSION=${BUILD_VERSION}' in dockerfile
assert 'os.environ.get("SV_INSTALLER_VERSION")' in web
assert 'installer_core.INSTALLER_VERSION = INSTALLER_VERSION' in web

assert 'id="show-changelog"' not in index
assert 'changelog-history.js' not in index
assert not (WWW / "changelog-history.js").exists()
assert "legacyChangelog=$('show-changelog')" not in manager_js
assert "legacy repo alias active" not in manager_js

assert 'id="install-unifi2mqtt" class="secondary hidden"' in index
assert "function syncSystemActions" in installer_js
assert "$('install-unifi2mqtt').classList.toggle('hidden',unifiInstalled||!s.unifi2mqtt_available)" in installer_js
assert "$('restart-unifi2mqtt').classList.toggle('hidden',!unifiInstalled)" in installer_js
assert "$('restart-discovery').classList.toggle('hidden',!discoveryInstalled)" in installer_js
assert "$('restart-snmp2mqtt').classList.toggle('hidden',!snmpInstalled)" in installer_js

assert "Restart Home Assistant Core required" in installer_js
assert 'id="result-restart-core"' in installer_js
assert "resultSummaryWithCoreRestart(op.result)" in installer_js

print(f"Installer UI/state regressions: PASS (v{config_version})")
