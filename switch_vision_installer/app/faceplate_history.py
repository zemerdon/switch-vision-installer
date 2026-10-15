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
                  installed_frontend: Path, frontend_stage: Path,
                  selected_storage: Path | None = None) -> int:
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
    preserve_selected_pairs(release_root, installed_frontend, frontend_stage, selected_storage)
    return changed


def _versioned_pairs(frontend: Path, *, retained: bool = False) -> list[dict]:
    """Read only the installer/Core-owned manifest, not guessed image paths."""
    prefix = "faceplate-history/revisions" if retained else "faceplates-old"
    path = frontend / prefix / "manifest.json"
    if not path.exists():
        return []
    if path.is_symlink() or path.stat().st_size > 1024 * 1024:
        raise RuntimeError("Untrusted faceplate revision manifest.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") != 1 or not isinstance(data.get("faceplates"), dict):
            raise ValueError("Invalid revision manifest schema")
        if len(data["faceplates"]) > 256:
            raise ValueError("Oversized revision manifest")
        result = []
        for name, entries in data["faceplates"].items():
            if not isinstance(name, str) or not _NAME.fullmatch(name):
                raise ValueError("Invalid versioned faceplate filename")
            if not isinstance(entries, list) or len(entries) > 256:
                raise ValueError("Invalid revision inventory")
            for item in entries:
                if not isinstance(item, dict) or item.get("filename") != name:
                    raise ValueError("Invalid revision record")
                version = str(item.get("version", ""))
                sha = str(item.get("sha256", ""))
                geo = str(item.get("geometry_sha256", ""))
                if (not re.fullmatch(r"\d+\.\d+\.\d+", version)
                        or not _DIGEST.fullmatch(sha) or not _DIGEST.fullmatch(geo)):
                    raise ValueError("Invalid revision provenance")
                old = f"{prefix}/{version}/{name}"
                old_geo = f"{prefix}/{version}/{name[:-4]}.json"
                is_latest = not retained and item.get("path") == f"faceplates/{name}"
                if is_latest:
                    old = f"faceplates/{name}"
                    old_geo = str(item.get("geometry_path", ""))
                    if (not old_geo.startswith("calibration/")
                            or not re.fullmatch(r"calibration/faceplate-[A-Za-z0-9_.-]+\.json", old_geo)):
                        raise ValueError("Invalid current geometry path")
                if item.get("path") != old or item.get("geometry_path") != old_geo:
                    raise ValueError("Revision path mismatch")
                result.append(item)
        return result
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise RuntimeError("Invalid versioned faceplate manifest.") from exc


def _verified_pair(frontend: Path, record: dict) -> tuple[bytes, bytes] | None:
    image = frontend / record["path"]
    geometry = frontend / record["geometry_path"]
    for parent in (image.parent, geometry.parent, frontend / "faceplate-history",
                   frontend / "faceplate-history/revisions"):
        if parent.is_symlink():
            return None
    if (not _verified_image(image, record["sha256"])
            or not _verified_image(geometry, record["geometry_sha256"])):
        return None
    try:
        data = json.loads(geometry.read_text(encoding="utf-8"))
        if (not isinstance(data, dict)
                or data.get("schema") != "switch-vision-interactive-calibration-v1"
                or data.get("image", {}).get("file") != "faceplates/" + record["filename"]
                or not isinstance(data.get("ports"), dict)
                or not isinstance(data.get("sfp"), dict)):
            return None
    except (OSError, ValueError, AttributeError):
        return None
    return image.read_bytes(), geometry.read_bytes()


def _selected_pair_pins(storage: Path | None) -> set[tuple[str, str, str, str]]:
    """Read HA's existing approval metadata, never modify Calibration storage."""
    if storage is None or not storage.exists():
        return set()
    if storage.is_symlink() or storage.stat().st_size > 8 * 1024 * 1024:
        raise RuntimeError("Faceplate selection storage is unreadable or unsafe.")
    try:
        wrapper = json.loads(storage.read_text(encoding="utf-8"))
        choices = wrapper["data"].get("stock_artwork_choices", {})
        if not isinstance(choices, dict) or len(choices) > 256:
            raise ValueError("Invalid switch selection inventory")
        pins = set()
        for selected in choices.values():
            if not isinstance(selected, dict):
                continue
            name = selected.get("filename")
            sha = selected.get("sha256")
            version = selected.get("version")
            geometry_sha = selected.get("geometry_sha256")
            # Legacy image-only pins remain protected by the existing artwork
            # history; never invent a factory geometry for such a pin.
            if not version and not geometry_sha:
                continue
            if (not isinstance(name, str) or not _NAME.fullmatch(name)
                    or not isinstance(sha, str) or not _DIGEST.fullmatch(sha)
                    or not isinstance(version, str)
                    or not re.fullmatch(r"\d+\.\d+\.\d+", version)
                    or not isinstance(geometry_sha, str)
                    or not _DIGEST.fullmatch(geometry_sha)):
                raise ValueError("Invalid approved revision identity")
            pins.add((name, sha, version, geometry_sha))
        return pins
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("Cannot verify previously selected faceplate revisions.") from exc


def preserve_selected_pairs(release: Path, installed: Path, stage: Path,
                            storage: Path | None) -> int:
    """Retain only aged-out, still-selected verified pairs locally.

    This reuses Installer's managed faceplate-history area; unchanged releases
    do not create another backup, and deselected revisions naturally expire.
    """
    pins = _selected_pair_pins(storage)
    if not pins:
        return 0
    incoming = _versioned_pairs(release)
    previous = (_versioned_pairs(installed)
                + _versioned_pairs(installed, retained=True))
    retained: dict[str, list[dict]] = {}
    for name, sha, version, geometry_sha in sorted(pins):
        def match(item: dict) -> bool:
            return (item["filename"] == name and item["sha256"] == sha
                    and item["version"] == version
                    and item["geometry_sha256"] == geometry_sha)

        shipped = next((row for row in incoming if match(row)), None)
        if shipped:
            if _verified_pair(release, shipped) is None:
                raise RuntimeError("Selected incoming faceplate pair failed verification.")
            continue
        source = next((row for row in previous if match(row)), None)
        if source is None:
            raise RuntimeError("Selected old faceplate pair cannot be preserved.")
        pair = _verified_pair(installed, source)
        if pair is None:
            raise RuntimeError("Selected old faceplate bytes or geometry are corrupt/missing.")
        folder = stage / "faceplate-history/revisions" / version
        folder.mkdir(parents=True, exist_ok=True)
        image = folder / name
        geometry = folder / f"{name[:-4]}.json"
        for destination, content in ((image, pair[0]), (geometry, pair[1])):
            if destination.exists() and destination.read_bytes() != content:
                raise RuntimeError("Conflicting selected factory revision.")
            destination.write_bytes(content)
        retained.setdefault(name, []).append({
            "version": version, "filename": name, "sha256": sha,
            "geometry_sha256": geometry_sha,
            "path": f"faceplate-history/revisions/{version}/{name}",
            "geometry_path": f"faceplate-history/revisions/{version}/{name[:-4]}.json",
        })
    if retained:
        target = stage / "faceplate-history/revisions/manifest.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"schema": 1, "faceplates": retained},
                                     sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return sum(map(len, retained.values()))
