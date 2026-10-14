from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/publish-release.yml").read_text(
    encoding="utf-8"
)
CONFIG = (ROOT / "switch_vision_installer/config.yaml").read_text(
    encoding="utf-8"
)

assert 'version: "2.1.48"' in CONFIG
assert "pull_request:" in WORKFLOW
assert "types:" in WORKFLOW
assert "- opened" in WORKFLOW
assert "synchronize" not in WORKFLOW
assert "reopened" not in WORKFLOW
assert "pull_request_target" not in WORKFLOW
assert "contents: read" in WORKFLOW
assert "release/installer-" in WORKFLOW
assert ".sv-release-request.json" in WORKFLOW
assert "release request must contain exactly version,target_sha,publish" in WORKFLOW
assert "publish requests must target the exact projected public main SHA" in WORKFLOW
assert "python3 tools/sv_release_check.py --mode release" in WORKFLOW
assert "switch_vision_installer/config.yaml" in WORKFLOW
assert (
    "actions/checkout@11d5960a326750d5838078e36cf38b85af677262"
    in WORKFLOW
)
assert "persist-credentials: false" in WORKFLOW
assert "cancel-in-progress: false" in WORKFLOW
assert "packages: write" not in WORKFLOW
assert "contents: write" not in WORKFLOW

print("Installer v2.1.46 guarded source publisher contract: PASS")
