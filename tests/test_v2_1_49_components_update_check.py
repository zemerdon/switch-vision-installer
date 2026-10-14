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
assert 'version: "2.1.50"' in VERSION


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
assert any("components-heading" in classes.split() for _, classes, _ in ancestors)
assert not any(tag == "header" for tag, _, _ in ancestors)
assert INDEX.index('id="check"') > INDEX.index("<h2>Components</h2>")
assert INDEX.index('id="check"') < INDEX.index('id="components"')
assert INDEX.index('class="components-heading"') < INDEX.index('id="check"')

for token in (
    "--check-updates-bg:#673ab7",
    "--check-updates-hover:#7e57c2",
    "--check-updates-border:#b39ddb",
    "--check-updates-text:#fff",
    ".components-heading{display:flex;justify-content:space-between",
    ".components-heading .check-updates{flex:0 0 auto;",
    ".components-heading .check-updates:hover{",
    ".components-heading{align-items:flex-start;flex-direction:column}",
    ".components-heading .check-updates{align-self:flex-end;width:auto;min-width:0}",
):
    assert token in CSS, token

# Ensure purple foreground/background meet 4.5:1 WCAG text contrast.
def luminance(hex_color: str) -> float:
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
    return sum(a * b for a, b in zip(linear, (.2126, .7152, .0722)))


for background in ("#673ab7", "#7e57c2"):
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
print("Installer v2.1.50 Components check-update placement/color/routing: PASS")
