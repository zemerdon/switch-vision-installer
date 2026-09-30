#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "switch_vision_installer" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import installer  # noqa: E402
import tree_transaction  # noqa: E402


installer_source = (APP / "installer.py").read_text(encoding="utf-8")
transaction_source = (APP / "tree_transaction.py").read_text(encoding="utf-8")

assert "import tree_transaction as _tree_transaction" in installer_source
for name in (
    "write_replace_transaction",
    "load_replace_transaction",
    "recover_interrupted_tree_replacement",
    "recover_interrupted_tree_replacements",
    "rollback_tree_replacement",
    "replace_tree",
):
    assert f"def {name}(" in transaction_source

for marker in (
    "The durable recovery marker was preserved",
    "outside the expected ",
    "Refusing to recover replacement over symbolic link",
):
    assert marker in transaction_source
    assert marker not in installer_source


def write_tree(path: Path, marker: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "state.txt").write_text(marker + "\n", encoding="utf-8")


with tempfile.TemporaryDirectory() as td:
    base = Path(td)
    source = base / "source"
    destination = base / "live"
    write_tree(source, "new")
    write_tree(destination, "old")

    tree_transaction.replace_tree(source, destination)
    assert (destination / "state.txt").read_text(encoding="utf-8") == "new\n"
    assert not tree_transaction.replacement_marker_path(destination).exists()

with tempfile.TemporaryDirectory() as td:
    base = Path(td)
    destination = base / "live"
    destination.parent.mkdir(parents=True, exist_ok=True)
    marker = tree_transaction.replacement_marker_path(destination)
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
        tree_transaction.recover_interrupted_tree_replacement(destination)
    except RuntimeError as exc:
        assert "outside the expected destination directory" in str(exc)
    else:
        raise AssertionError("unsafe transaction marker was accepted")

print("Switch Vision Installer tree-transaction modularity regression: PASS")
