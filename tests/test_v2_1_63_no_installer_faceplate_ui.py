"""Installer updates normally; faceplate approval exists only in Discovery Hub."""
from pathlib import Path
from html.parser import HTMLParser

root = Path(__file__).resolve().parents[1]
www = root / "switch_vision_installer/www"
html = (www / "index.html").read_text()
css = (www / "component-manager.css").read_text()
theme = (www / "installer.css").read_text()
js = (www / "installer.js").read_text()
mgr = (www / "component-manager.js").read_text()

class IdCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
    def handle_starttag(self, tag, attrs):
        name = dict(attrs).get("id")
        if name:
            self.ids.append(name)

doc = IdCollector()
doc.feed(html)
assert len(doc.ids) == len(set(doc.ids))
assert "activity-section" in doc.ids
assert "faceplate-review-section" not in doc.ids
assert "faceplate-review-content" not in doc.ids
assert "faceplate-upgrade-keep" not in js
for forbidden in ("faceplateReviewCard", "renderFaceplateReview",
                  "faceplate-review", "faceplate-upgrade",
                  "svCoreUpgradePreflight", "startPendingCoreUpdate",
                  "corePreflightDecision", "faceplate-preview"):
    assert forbidden not in js + mgr + css + html + theme, forbidden
assert "api/dry-run" not in js + mgr
assert "api/update-component" in mgr
assert "api/update-all" in mgr
assert "resultSummaryWithCoreRestart" in js
assert "Restart Home Assistant Core required" in js
assert 'class="preserve-columns"' in js
assert ".result .preserve-columns{columns:2;" in theme
assert 'id="update-all-components"' in html
# The backend retains its protected-file and history safeguards independently
# of the user-facing artwork review removal.
backend = (root / "switch_vision_installer/app/installer.py").read_text()
assert "faceplate" in backend.lower()
print("Installer 2.1.63 Hub-only faceplate UI and preservation contract: PASS")
