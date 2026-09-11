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

# v2.1.33: the visual readiness checklist is intentionally removed. The
# underlying state data remains available to Installer logic; rendering simply
# becomes a no-op when the old checklist element is absent.
assert 'id="readiness-section"' not in index
assert 'id="checklist"' not in index
assert "const COLLAPSIBLE_SECTIONS=['activity-section','backups-section'];" in installer_js
assert "function renderChecklist(){const target=$('checklist');if(!target)return;" in installer_js

# Explicit 10-20 px shared UI font contract, including legacy migration.
import ast
web_tree = ast.parse(web)
helper = next(node for node in web_tree.body if isinstance(node, ast.FunctionDef) and node.name == 'normalise_ui_text_size')
ns = {
    'UI_TEXT_SIZE_MIN_PX': 10,
    'UI_TEXT_SIZE_MAX_PX': 20,
    'UI_TEXT_SIZE_DEFAULT_PX': 16,
    'UI_TEXT_SIZE_LEGACY': {'normal': 16, 'small': 14},
}
exec(compile(ast.Module(body=[helper], type_ignores=[]), '<installer-ui-font>', 'exec'), ns)
normalise = ns['normalise_ui_text_size']
assert normalise('normal') == 16
assert normalise('small') == 14
for pixels in range(10, 21):
    assert normalise(pixels) == pixels
    assert normalise(str(pixels)) == pixels
for invalid in (9, 21, 'giant', None, True, 14.5):
    assert normalise(invalid) == 16
assert "function normaliseUiTextSize(raw)" in installer_js
assert "document.body.style.setProperty('--sv-body',`${values.text_size}px`)" in installer_js
assert 'body.text-small{' not in (WWW / 'installer.css').read_text(encoding='utf-8')


# Shared 5-point density and 10-point width contract consumed from Core.
for marker in (
    "density:new Set(['spacious','comfortable','compact','dense','ultra_dense'])",
    "content_width:new Set(['standard','standard_plus','wide','wide_plus','extra_wide','extra_wide_plus','ultra_wide','ultra_wide_plus','max_wide','full'])",
    'body.width-standard_plus main{max-width:1140px}',
    'body.width-extra_wide main{max-width:1520px}',
    'body.width-max_wide main{max-width:2000px}',
    'body.density-spacious main{padding:30px 22px 54px}',
    'body.density-ultra_dense main{padding:4px 4px 12px}',
):
    assert marker in installer_js or marker in (WWW / 'installer.css').read_text(encoding='utf-8') or marker in web, marker

print(f"Installer UI/state regressions: PASS (v{config_version})")
