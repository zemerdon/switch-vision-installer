"""Placement, contrast, responsive layout and unchanged behavior of the update check."""
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
WWW = ROOT / "switch_vision_installer" / "www"
INDEX = (WWW / "index.html").read_text(encoding="utf-8")
CSS = (WWW / "installer.css").read_text(encoding="utf-8")
JS = (WWW / "installer.js").read_text(encoding="utf-8")
VERSION = (ROOT / "switch_vision_installer/config.yaml").read_text(encoding="utf-8")
assert 'version: "2.1.52"' in VERSION


class CheckPlacement(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.matches = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id") == "check":
            self.matches.append((tag, attrs, tuple(self.stack)))
        if tag not in {"meta", "link", "br", "img", "input", "hr"}:
            self.stack.append((tag, attrs.get("class", ""), attrs.get("id", "")))

    def handle_endtag(self, tag):
        if self.stack:
            assert self.stack[-1][0] == tag, (tag, self.stack[-1])
            self.stack.pop()


parser = CheckPlacement()
parser.feed(INDEX)
assert len(parser.matches) == 1
tag, attrs, ancestors = parser.matches[0]
assert tag == "button" and attrs.get("type") == "button"
assert attrs.get("class") == "check-updates"
assert any("details" in classes.split() for _, classes, _ in ancestors)
assert not any("components-heading" in classes.split() for _, classes, _ in ancestors)
assert not any(tag == "header" for tag, _, _ in ancestors)
assert INDEX.index('id="check"') > INDEX.index("<h2>Core release details</h2>")
assert INDEX.index('id="check"') > INDEX.index('id="published"')
assert INDEX.index('id="check"') < INDEX.index("<h2>Components</h2>")
assert INDEX.index('id="check"') < INDEX.index('id="components"')
assert '<svg class="check-updates-icon"' in INDEX
assert 'aria-hidden="true" focusable="false"' in INDEX
assert '<span>Check for updates</span>' in INDEX
assert INDEX.index('<svg class="check-updates-icon"') < INDEX.index('<span>Check for updates</span>')

for token in (
    "--check-updates-bg:#147a34",
    "--check-updates-bg-end:#08652b",
    "--check-updates-hover:#166e32",
    "--check-updates-border:#41b55c",
    "--check-updates-text:#fff",
    ".details{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr) minmax(0,1.5fr) auto;",
    ".details>.check-updates{display:inline-flex;",
    "justify-self:end;align-self:center;",
    "min-height:35px;padding:7px 12px;",
    "border-radius:9px;background:linear-gradient(180deg,var(--check-updates-bg),var(--check-updates-bg-end))",
    ".details .check-updates-icon{display:block;",
    ".details>.check-updates:focus-visible{",
    ".details>.check-updates:hover{",
    ".grid,.details{grid-template-columns:1fr}",
    ".details>.check-updates{justify-self:end;width:auto;max-width:100%}",
):
    assert token in CSS, token

# Ensure green foreground/background meet 4.5:1 WCAG text contrast.
def luminance(hex_color: str) -> float:
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
    return sum(a * b for a, b in zip(linear, (.2126, .7152, .0722)))


for background in ("#147a34", "#08652b", "#166e32"):
    ratio = 1.05 / (luminance(background) + .05)
    assert ratio >= 4.5, (background, ratio)

# Preserve the original check endpoint and its control's loading state.
assert "function setControls(on){$('check').disabled=on;}" in JS
assert "$('check').addEventListener('click'" in JS
assert "await json('api/check-components',{method:'POST'})" in JS
assert "await refresh(false)" in JS
assert re.search(r"button:disabled\{opacity:", CSS)
assert "id=\"system-actions-card\"" not in INDEX
assert "Core install or reinstall</h2>" not in INDEX
print("Installer v2.1.52 Core release update-check placement/color/routing: PASS")
