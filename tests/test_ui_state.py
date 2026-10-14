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

assert 'id="system-actions-card"' not in index
assert 'System actions</h2>' not in index
assert 'id="install"' not in index and index.count('id="check"') == 1
assert index.index('id="check"') > index.index('<h2>Core release details</h2>')
assert index.index('id="check"') > index.index('id="published"')
assert index.index('id="check"') < index.index('<h2>Components</h2>')
assert "Core install or reinstall</h2>" not in index
assert "function syncSystemActions" not in installer_js
for obsolete_id in ('restart-core','restart-discovery','restart-snmp2mqtt','restart-unifi2mqtt','install-discovery','install-snmp2mqtt','install-unifi2mqtt'):
    assert f'id="{obsolete_id}"' not in index

assert "Restart Home Assistant Core required" in installer_js
assert 'id="result-restart-core"' in installer_js
assert "resultSummaryWithCoreRestart(op.result)" in installer_js

# v2.1.33: the visual readiness checklist is intentionally removed. The
# underlying state data remains available to Installer logic; rendering simply
# becomes a no-op when the old checklist element is absent.
assert 'id="readiness-section"' not in index
assert 'id="checklist"' not in index
assert "const COLLAPSIBLE_SECTIONS=['activity-section'];" in installer_js
assert 'id="dry-run"' not in index
assert 'id="backups-section"' not in index
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

# Shared management-theme contract is read from Core's ui-preferences.json and
# applied to every Installer colour surface through role-based CSS variables.
css = (WWW / 'installer.css').read_text(encoding='utf-8')
for marker in (
    'MANAGEMENT_THEME_COLOR_KEYS = (',
    'def _safe_management_theme(document: object)',
    'values["management_theme"] = _safe_management_theme(document)',
    'const MANAGEMENT_THEME_KEYS=',
    'const BUILTIN_THEME_PALETTES=',
    'function applyManagementTheme(raw={})',
    'applyManagementTheme(raw?.management_theme||{})',
    "window.addEventListener('focus',()=>loadUiPreferences())",
    "document.addEventListener('visibilitychange',()=>{if(!document.hidden)loadUiPreferences();})",
):
    assert marker in web or marker in installer_js, marker

theme_roles = (
    '--page:', '--card:', '--surface-input:', '--surface-button:', '--text:',
    '--muted:', '--field-label:', '--line:', '--accent:', '--heading:',
    '--warn:', '--ok:', '--bad:', '--link:', '--button-primary-bg:',
    '--button-secondary-bg:', '--button-danger-bg:',
)
for marker in theme_roles:
    assert marker in css, marker

# UI rules outside the root default palette must use variables instead of
# retaining fixed colours that would ignore the selected shared theme.
css_without_root = re.sub(r':root\{.*?\}\n', '', css, count=1, flags=re.S)
assert not re.search(r'#[0-9a-fA-F]{3,8}', css_without_root)
component_css = (WWW / 'component-manager.css').read_text(encoding='utf-8')
assert not re.search(r'#[0-9a-fA-F]{3,8}', component_css)

theme_key_node = next(
    node for node in web_tree.body
    if isinstance(node, ast.Assign)
    and any(isinstance(target, ast.Name) and target.id == 'MANAGEMENT_THEME_COLOR_KEYS' for target in node.targets)
)
theme_keys = ast.literal_eval(theme_key_node.value)
safe_theme_helper = next(
    node for node in web_tree.body
    if isinstance(node, ast.FunctionDef) and node.name == '_safe_management_theme'
)
theme_ns = {
    'MANAGEMENT_THEME_COLOR_KEYS': theme_keys,
    'MANAGEMENT_BUILTIN_THEME_IDS': {'switch-vision','cisco-classic','cisco-nexus','unifi'},
}
exec(compile(ast.Module(body=[safe_theme_helper], type_ignores=[]), '<installer-theme>', 'exec'), theme_ns)
safe_theme = theme_ns['_safe_management_theme']
colors = {key:'#123456' for key in theme_keys}
document = {'management_theme': {'selected':'custom:lab', 'custom_themes':[{'id':'lab','name':'Lab Theme','colors':colors}]}}
assert safe_theme(document) == document['management_theme']
assert safe_theme({'management_theme': {'selected':'custom:missing','custom_themes':[]}})['selected'] == 'switch-vision'
assert safe_theme({'management_theme': {'selected':'custom:lab','custom_themes':[{'id':'bad/id','name':'Bad','colors':colors}]}}) == {'selected':'switch-vision','custom_themes':[]}


# Shared 5-point density and 10-point width contract consumed from Core.
css = (WWW / 'installer.css').read_text(encoding='utf-8')
width_steps = [
    ('standard', 64), ('standard_plus', 68), ('wide', 72), ('wide_plus', 76),
    ('extra_wide', 80), ('extra_wide_plus', 84), ('ultra_wide', 88),
    ('ultra_wide_plus', 92), ('max_wide', 96), ('full', 100),
]
for name, pct in width_steps:
    assert f'body.width-{name} main{{max-width:none;width:{pct}%}}' in css
assert [pct for _, pct in width_steps] == list(range(64, 101, 4))
assert sum(pct == 100 for _, pct in width_steps) == 1
for name, legacy in (
    ('standard', 1040), ('standard_plus', 1140), ('wide', 1280),
    ('wide_plus', 1400), ('extra_wide', 1520), ('extra_wide_plus', 1640),
    ('ultra_wide', 1760), ('ultra_wide_plus', 1880), ('max_wide', 2000),
):
    assert f'body.width-{name} main{{max-width:{legacy}px}}' not in css

for marker in (
    "density:new Set(['spacious','comfortable','compact','dense','ultra_dense'])",
    "content_width:new Set(['standard','standard_plus','wide','wide_plus','extra_wide','extra_wide_plus','ultra_wide','ultra_wide_plus','max_wide','full'])",
    'body.width-standard_plus main{max-width:none;width:68%}',
    'body.width-extra_wide main{max-width:none;width:80%}',
    'body.width-max_wide main{max-width:none;width:96%}',
    'body.density-spacious main{padding:30px 22px 54px}',
    'body.density-ultra_dense main{padding:4px 4px 12px}',
):
    assert marker in installer_js or marker in (WWW / 'installer.css').read_text(encoding='utf-8') or marker in web, marker

print(f"Installer UI/state regressions: PASS (v{config_version})")
