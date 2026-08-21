#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import importlib.util
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "switch_vision_installer" / "app" / "installer.py"

spec = importlib.util.spec_from_file_location(
    "sv_installer_v220_atomic_test",
    INSTALLER,
)
if spec is None or spec.loader is None:
    raise SystemExit("Unable to import installer.py")
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

assert mod.INSTALLER_VERSION == "2.1.24"


def write_tree(path: Path, marker: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "state.txt").write_text(marker + "\n", encoding="utf-8")
    nested = path / "nested"
    nested.mkdir()
    (nested / "value.txt").write_text(marker + "-nested\n", encoding="utf-8")


def assert_tree(path: Path, marker: str) -> None:
    assert (path / "state.txt").read_text(encoding="utf-8") == marker + "\n"
    assert (
        path / "nested" / "value.txt"
    ).read_text(encoding="utf-8") == marker + "-nested\n"


def transaction_paths(destination: Path, token: str) -> tuple[Path, Path, Path]:
    stage = destination.parent / (
        f".{destination.name}.switch-vision-stage-{token}"
    )
    previous = destination.parent / (
        f".{destination.name}.switch-vision-previous-{token}"
    )
    marker = mod._replacement_marker_path(destination)
    return stage, previous, marker


with tempfile.TemporaryDirectory() as td:
    base = Path(td)
    source = base / "source"
    destination = base / "live"
    write_tree(source, "new")
    write_tree(destination, "old")

    mod.replace_tree(source, destination)
    assert_tree(destination, "new")
    assert not mod._replacement_marker_path(destination).exists()
    assert not list(base.glob(".live.switch-vision-stage-*"))
    assert not list(base.glob(".live.switch-vision-previous-*"))


with tempfile.TemporaryDirectory() as td:
    base = Path(td)
    source = base / "source"
    destination = base / "live"
    write_tree(source, "new")
    write_tree(destination, "old")

    original_copytree = mod.shutil.copytree

    def fail_copytree(src, dst, *args, **kwargs):
        Path(dst).mkdir(parents=True)
        (Path(dst) / "partial.txt").write_text("partial\n", encoding="utf-8")
        raise RuntimeError("synthetic staging failure")

    mod.shutil.copytree = fail_copytree
    try:
        try:
            mod.replace_tree(source, destination)
        except RuntimeError as exc:
            assert "synthetic staging failure" in str(exc)
        else:
            raise AssertionError("staging failure unexpectedly succeeded")
    finally:
        mod.shutil.copytree = original_copytree

    assert_tree(destination, "old")
    assert not mod._replacement_marker_path(destination).exists()
    assert not list(base.glob(".live.switch-vision-stage-*"))


with tempfile.TemporaryDirectory() as td:
    base = Path(td)
    destination = base / "live"
    stage, previous, marker = transaction_paths(destination, "crash-old-moved")
    write_tree(stage, "new")
    write_tree(previous, "old")
    mod._write_replace_transaction(destination, stage, previous, True)

    assert not destination.exists()
    assert mod.recover_interrupted_tree_replacement(destination) is True
    assert_tree(destination, "old")
    assert not stage.exists()
    assert not previous.exists()
    assert not marker.exists()


with tempfile.TemporaryDirectory() as td:
    base = Path(td)
    destination = base / "live"
    stage, previous, marker = transaction_paths(destination, "crash-new-live")
    write_tree(destination, "new")
    write_tree(previous, "old")
    mod._write_replace_transaction(destination, stage, previous, True)

    assert mod.recover_interrupted_tree_replacement(destination) is True
    assert_tree(destination, "new")
    assert not previous.exists()
    assert not marker.exists()


with tempfile.TemporaryDirectory() as td:
    base = Path(td)
    destination = base / "live"
    stage, previous, marker = transaction_paths(destination, "crash-first-install")
    write_tree(stage, "new")
    mod._write_replace_transaction(destination, stage, previous, False)

    assert mod.recover_interrupted_tree_replacement(destination) is True
    assert_tree(destination, "new")
    assert not stage.exists()
    assert not marker.exists()


with tempfile.TemporaryDirectory() as td:
    base = Path(td)
    destination = base / "live"
    destination.parent.mkdir(parents=True, exist_ok=True)
    marker = mod._replacement_marker_path(destination)
    marker.write_text(
        json.dumps(
            {
                "schema": 1,
                "destination": str(destination),
                "stage": str(base.parent / "outside-stage"),
                "previous": str(base.parent / "outside-previous"),
                "had_destination": True,
            }
        ),
        encoding="utf-8",
    )
    try:
        mod.recover_interrupted_tree_replacement(destination)
    except RuntimeError as exc:
        assert "outside the expected destination directory" in str(exc)
    else:
        raise AssertionError("unsafe transaction marker was accepted")


with tempfile.TemporaryDirectory() as td:
    base = Path(td)
    mod.COMPONENT_DIR = base / "custom_components" / "switch_vision"
    mod.FRONTEND_DIR = base / "www" / "switch-vision"

    stage, previous, marker = transaction_paths(
        mod.COMPONENT_DIR, "startup-component"
    )
    write_tree(stage, "component-new")
    mod._write_replace_transaction(mod.COMPONENT_DIR, stage, previous, False)

    recovered = mod.recover_interrupted_tree_replacements()
    assert str(mod.COMPONENT_DIR) in recovered
    assert_tree(mod.COMPONENT_DIR, "component-new")


source = INSTALLER.read_text(encoding="utf-8")
replace_start = source.index("def replace_tree(")
replace_end = source.index("\n\ndef _restore_backup_contents", replace_start)
replace_source = source[replace_start:replace_end]

assert "shutil.rmtree(destination)" not in replace_source
assert "recover_interrupted_tree_replacement(destination)" in replace_source
assert "_write_replace_transaction" in source
assert "os.replace(stage, destination)" in replace_source
assert "recover_interrupted_tree_replacements" in source

print("Switch Vision Installer v2.1.20 crash-atomic replacement regression: PASS")
