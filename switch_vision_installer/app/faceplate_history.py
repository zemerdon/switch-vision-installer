"""Preserve verified prior stock artwork across atomic Core frontend replacements.

The public filename stays stable. Prior image bytes are retained separately,
content-addressed, only when both installed and new stock manifests agree
with their actual image bytes. No private Calibration or device state is copied.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,140}\.png$")
_MAX_SIZE = 32 * 1024 * 1024


def _stock_images(component: Path) -> dict[str, str]:
    try:
        data = json.loads((component / "stock-assets.json").read_text(encoding="utf-8"))
        if data.get("schema") != "switch-vision-stock-assets-v1":
            return {}
        rows = data["assets"]["faceplates"]
        if not isinstance(rows, dict):
            return {}
        return {
            name: digest for name, digest in rows.items()
            if isinstance(name, str) and _NAME.fullmatch(name)
            and isinstance(digest, str) and _DIGEST.fullmatch(digest)
        }
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def _verified_image(path: Path, expected: str) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    try:
        if path.stat().st_size > _MAX_SIZE:
            return False
        return hashlib.sha256(path.read_bytes()).hexdigest() == expected
    except OSError:
        return False


def stage_history(release_root: Path, installed_component: Path,
                  installed_frontend: Path, frontend_stage: Path) -> int:
    """Copy managed art history and retain replaced original stock pixels.

    Lives outside the stock faceplates catalogue and cannot rename/re-map
    the owner's default model filename. Dry-run staging touches only scratch.
    """
    old_dir = installed_frontend / "faceplate-history"
    new_dir = frontend_stage / "faceplate-history"
    if old_dir.is_dir() and not old_dir.is_symlink():
        # Existing managed history must remain available on future upgrades.
        paths = sorted(old_dir.glob("*/*.png"))
        if len(paths) > 512:
            raise RuntimeError("Stock artwork history exceeds the bounded version inventory.")
        for old in paths:
            digest_dir = old.parent.name
            if digest_dir != "legacy" and not _DIGEST.fullmatch(digest_dir):
                continue
            if (not _NAME.fullmatch(old.name) or old.parent.is_symlink()
                    or old.is_symlink() or not old.is_file()):
                continue
            if old.stat().st_size > _MAX_SIZE:
                continue
            actual = hashlib.sha256(old.read_bytes()).hexdigest()
            if digest_dir != "legacy" and actual != digest_dir:
                continue
            dest = new_dir / digest_dir / old.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(old, dest)

    installed = _stock_images(installed_component)
    incoming = _stock_images(release_root / "custom_components" / "switch_vision")
    # Snapshot the entire outgoing verified stock catalogue, even unchanged
    # artwork. The content-addressed directory deduplicates across versions;
    # original names in the new stock folder remain untouched.
    for name, prior in sorted(installed.items()):
        old = installed_frontend / "faceplates" / name
        if not _verified_image(old, prior):
            continue
        archived = new_dir / prior / name
        if archived.exists():
            if not _verified_image(archived, prior):
                raise RuntimeError("Previous faceplate history failed integrity validation.")
            continue
        archived.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(old, archived)
    if len(list(new_dir.glob("*/*.png"))) > 512:
        raise RuntimeError("Stock artwork history exceeds the bounded version inventory.")

    changed = 0
    for name in sorted(set(installed) & set(incoming)):
        prior, next_sha = installed[name], incoming[name]
        if prior == next_sha:
            continue
        old = installed_frontend / "faceplates" / name
        new = release_root / "faceplates" / name
        if not (_verified_image(old, prior) and _verified_image(new, next_sha)):
            continue
        archive = new_dir / prior / name
        archive.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(old, archive)
        # Legacy saved profiles predate per-save artwork fingerprints. Preserve
        # the earliest available original art for their safe visual comparison.
        legacy = new_dir / "legacy" / name
        if not legacy.exists():
            legacy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(old, legacy)
        changed += 1
    return changed
