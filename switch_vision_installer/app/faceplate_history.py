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
    # SHA-owned history is independent of component release numbers.
    preserve_sha_pairs(release_root, installed_component, installed_frontend,
                       frontend_stage, selected_storage)
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
                   frontend / "faceplate-history/revisions",
                   frontend / _SHA_PAIR_DIR):
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
            # The new SHA-pair catalogue is owned by preserve_sha_pairs(),
            # not the previous release-version-based compatibility reader.
            if isinstance(version, str) and version.startswith("sha-"):
                continue
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
            # New installations have no Core-versioned history. A verified
            # SHA-addressed pair in the staged inventory is sufficient.
            pairs = _read_sha_inventory(stage)
            verified = next((row for row in pairs.get(name, [])
                             if row.get("sha256") == sha
                             and row.get("geometry_sha256") == geometry_sha
                             and _verified_pair(stage, row) is not None), None)
            if verified:
                continue
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


# Content-identified, installation-local faceplate+factory geometry history.
# This deliberately coexists with the older versioned migration inventory;
# no new Core build needs to ship historical images.
_SHA_PAIR_DIR = "faceplate-history/revisions/sha"
_GEOMETRY_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,140}\.json$")


def _factory_geometries(frontend: Path) -> dict[str, dict[str, tuple[str, bytes]]]:
    """Index every valid factory geometry, including shared-PNG model aliases."""
    result: dict[str, dict[str, tuple[str, bytes]]] = {}
    folder = frontend / "calibration"
    if not folder.is_dir() or folder.is_symlink():
        return result
    for path in sorted(folder.glob("*.json")):
        if not _GEOMETRY_NAME.fullmatch(path.name) or path.is_symlink():
            continue
        if path.stat().st_size > _MAX_SIZE:
            raise RuntimeError("Oversize factory geometry.")
        contents = path.read_bytes()
        try:
            data = json.loads(contents)
        except (ValueError, UnicodeError):
            continue  # Not every calibration JSON is a factory profile.
        if not isinstance(data, dict) or data.get("schema") != "switch-vision-interactive-calibration-v1":
            continue
        image = data.get("image", {})
        name = image.get("file", "") if isinstance(image, dict) else ""
        if (not isinstance(name, str) or not name.startswith("faceplates/")
                or not _NAME.fullmatch(name.split("/", 1)[-1])
                or not isinstance(data.get("ports"), dict)
                or not isinstance(data.get("sfp"), dict)):
            continue
        filename = name.split("/", 1)[-1]
        result.setdefault(filename, {})[path.name] = (
            hashlib.sha256(contents).hexdigest(), contents
        )
    # Several old model-specific calibrations can reuse one generic stock PNG.
    # They are NOT alternate factory revisions. Use precisely the canonical
    # per-faceplate geometry chosen by Core's factory faceplate builder.
    canonical: dict[str, dict[str, tuple[str, bytes]]] = {}
    for name, profiles in result.items():
        stem = name[:-4]
        chosen = next((candidate for candidate in
                       (f"faceplate-{stem}.json", f"faceplate-stock-{stem}.json")
                       if candidate in profiles), None)
        if chosen:
            canonical[name] = {chosen: profiles[chosen]}
    return canonical


def compare_sha_pairs(release_root: Path, installed_component: Path,
                      installed_frontend: Path) -> list[dict]:
    """Read-only preflight of installed-vs-incoming VERIFIED stock bytes.

    The identity is image + factory geometry, independently of Core version.
    A faceplate can have several legitimate model-specific factory profiles.
    """
    installed = _stock_images(installed_component)
    incoming = _stock_images(release_root / "custom_components/switch_vision")
    before_geometries = _factory_geometries(installed_frontend)
    after_geometries = _factory_geometries(release_root)
    changed = []
    for name in sorted(installed):
        before, after = installed[name], incoming.get(name, "")
        old_geos = before_geometries.get(name, {})
        if not old_geos:
            # Legacy image-only installs are covered by stage_history's PNG
            # compatibility path; never invent an old geometry SHA.
            continue
        new_geos = after_geometries.get(name, {})
        old_png = installed_frontend / "faceplates" / name
        new_png = release_root / "faceplates" / name
        if not _verified_image(old_png, before):
            raise RuntimeError(f"Cannot verify installed stock faceplate: {name}")
        if after and not _verified_image(new_png, after):
            raise RuntimeError(f"Cannot verify incoming stock faceplate: {name}")
        if after and not new_geos:
            raise RuntimeError(f"Incoming stock faceplate lacks factory geometry: {name}")
        for geo_file, (old_sha, _) in sorted(old_geos.items()):
            incoming_geo = new_geos.get(geo_file)
            if not incoming_geo:
                # Retired factory profile must still be retainable.
                incoming_sha = ""
            else:
                incoming_sha = incoming_geo[0]
            if before == after and old_sha == incoming_sha:
                continue
            identity = hashlib.sha256(
                (before + ":" + old_sha).encode("ascii")
            ).hexdigest()
            changed.append({
                "filename": name, "geometry_file": geo_file,
                "sha256": before, "geometry_sha256": old_sha,
                "incoming_sha256": after,
                "incoming_geometry_sha256": incoming_sha,
                "identity": identity,
                "path": f"{_SHA_PAIR_DIR}/{identity}/{name}",
                "geometry_path": f"{_SHA_PAIR_DIR}/{identity}/{name[:-4]}.json",
            })
    return changed


def _read_sha_inventory(stage: Path) -> dict[str, list[dict]]:
    manifest = stage / _SHA_PAIR_DIR / "manifest.json"
    if not manifest.exists():
        return {}
    if manifest.is_symlink() or manifest.stat().st_size > 1024 * 1024:
        raise RuntimeError("Unsafe SHA faceplate history inventory.")
    try:
        data = json.loads(manifest.read_text())
        if data.get("schema") != 2 or not isinstance(data.get("faceplates"), dict):
            raise ValueError("Bad SHA history schema")
        return data["faceplates"]
    except (OSError, TypeError, ValueError) as exc:
        raise RuntimeError("Invalid SHA faceplate history inventory.") from exc


def _selected_sha_pairs(storage: Path | None) -> set[tuple[str, str, str]]:
    if storage is None or not storage.exists():
        return set()
    if storage.is_symlink() or storage.stat().st_size > 8 * 1024 * 1024:
        raise RuntimeError("Unsafe stock artwork selection storage.")
    try:
        pins = json.loads(storage.read_text())["data"].get("stock_artwork_choices", {})
        if not isinstance(pins, dict) or len(pins) > 256:
            raise ValueError("Invalid stored stock choices")
        return {(str(row.get("filename")), str(row.get("sha256")),
                 str(row.get("geometry_sha256") or ""))
                for row in pins.values() if isinstance(row, dict)
                and _NAME.fullmatch(str(row.get("filename", "")))
                and _DIGEST.fullmatch(str(row.get("sha256", "")))
                and (not row.get("geometry_sha256")
                     or _DIGEST.fullmatch(str(row.get("geometry_sha256"))))}
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise RuntimeError("Unable to read approved stock artwork selections.") from exc


def preserve_sha_pairs(release_root: Path, installed_component: Path,
                       installed_frontend: Path, stage: Path,
                       selected_storage: Path | None = None) -> list[dict]:
    """Archive changed verified pairs only; retain at most two unselected
    previous pairs per factory profile, plus any actively selected pair.
    No HA storage or user Calibration is modified.
    """
    changes = compare_sha_pairs(release_root, installed_component, installed_frontend)
    directory = stage / _SHA_PAIR_DIR
    original = installed_frontend / _SHA_PAIR_DIR
    if original.is_symlink():
        raise RuntimeError("Unsafe local SHA faceplate history.")
    if original.is_dir():
        existing = list(original.rglob("*"))
        if len(existing) > 1024 or any(p.is_symlink() for p in existing):
            raise RuntimeError("Unsafe or oversized local SHA faceplate inventory.")
        if directory.exists():
            raise RuntimeError("Duplicate SHA faceplate history stage.")
        shutil.copytree(original, directory, symlinks=False)
    inventory = _read_sha_inventory(stage)
    before_geo = _factory_geometries(installed_frontend)
    protected = _selected_sha_pairs(selected_storage)
    for record in changes:
        name, source_geo, identity = (record["filename"],
                                      record["geometry_file"], record["identity"])
        source_img = installed_frontend / "faceplates" / name
        png = source_img.read_bytes()
        geometry = before_geo[name][source_geo][1]
        folder = directory / identity
        if folder.is_symlink():
            raise RuntimeError("Unsafe preserved faceplate directory.")
        folder.mkdir(parents=True, exist_ok=True)
        for target, content in ((folder / name, png),
                                (folder / f"{name[:-4]}.json", geometry)):
            if target.is_symlink() or (target.exists() and target.read_bytes() != content):
                raise RuntimeError("Conflicting saved SHA faceplate pair.")
            target.write_bytes(content)
        rows = inventory.setdefault(name, [])
        if not any(row.get("identity") == identity
                   and row.get("geometry_file") == source_geo for row in rows):
            rows.append({k: record[k] for k in (
                "filename", "geometry_file", "sha256", "geometry_sha256",
                "identity", "path", "geometry_path"
            )})
    if inventory:
        # Remove only previously saved, unselected revisions outside the cap.
        kept: dict[str, list[dict]] = {}
        referenced: set[str] = set()
        for name, rows in sorted(inventory.items()):
            if not _NAME.fullmatch(str(name)) or not isinstance(rows, list) or len(rows) > 256:
                raise RuntimeError("Invalid saved SHA revision inventory.")
            by_geo: dict[str, list[dict]] = {}
            for row in rows:
                if not isinstance(row, dict) or not _GEOMETRY_NAME.fullmatch(str(row.get("geometry_file", ""))):
                    raise RuntimeError("Invalid saved SHA geometry profile.")
                identity = str(row.get("identity", ""))
                if not _DIGEST.fullmatch(identity):
                    raise RuntimeError("Invalid SHA revision identity.")
                expected_identity = hashlib.sha256(
                    (str(row.get("sha256")) + ":" + str(row.get("geometry_sha256"))).encode("ascii")
                ).hexdigest()
                if identity != expected_identity:
                    raise RuntimeError("SHA revision identity mismatch.")
                if (row.get("filename") != name
                        or row.get("path") != f"{_SHA_PAIR_DIR}/{identity}/{name}"
                        or row.get("geometry_path") != f"{_SHA_PAIR_DIR}/{identity}/{name[:-4]}.json"):
                    raise RuntimeError("Unsafe SHA revision paths.")
                pair = _verified_pair(stage, row)
                if pair is None:
                    raise RuntimeError("Historical faceplate/geometry bytes are missing or tampered.")
                by_geo.setdefault(row["geometry_file"], []).append(row)
            for geo, group in by_geo.items():
                for row in group[-2:]:
                    kept.setdefault(name, []).append(row)
                    referenced.add(row["identity"])
                for row in group[:-2]:
                    if ((name, row["sha256"], row["geometry_sha256"]) in protected
                            or (name, row["sha256"], "None") in protected
                            or (name, row["sha256"], "") in protected):
                        kept.setdefault(name, []).append(row)
                        referenced.add(row["identity"])
        inventory = kept
        for folder in directory.iterdir():
            if folder.is_dir() and not folder.is_symlink() and folder.name not in referenced:
                shutil.rmtree(folder)
        manifest = directory / "manifest.json"
        manifest.write_text(json.dumps({"schema": 2, "faceplates": inventory},
                                       sort_keys=True, indent=2) + "\n")
    return changes


def faceplate_change_summary(release_root: Path, installed_component: Path,
                             installed_frontend: Path) -> dict:
    """Read-only image+canonical-geometry preflight for Installer's upgrade card.

    New dedicated artwork is only a *candidate*. Discovery/Core decides which
    configured switch model the new faceplate belongs to; Installer must never
    guess that model or mutate a per-switch artwork selection on its behalf.
    """
    old = _stock_images(installed_component)
    new = _stock_images(release_root / "custom_components/switch_vision")
    if not old:
        return {"new": [], "changed": []}  # first installation is not an upgrade
    introduced = []
    factory = _factory_geometries(release_root)
    for name in sorted(new.keys() - old.keys()):
        if not _verified_image(release_root / "faceplates" / name, new[name]):
            raise RuntimeError("Invalid incoming dedicated stock image: " + name)
        if not factory.get(name):
            raise RuntimeError("New stock faceplate lacks matching geometry: " + name)
        introduced.append(name)
    changed = compare_sha_pairs(release_root, installed_component, installed_frontend)
    return {"new": introduced, "changed": [
        {"filename": row["filename"], "geometry_only":
            row["sha256"] == row["incoming_sha256"],
         "previous_preview": row["path"],
         "previous_sha256": row["sha256"],
         "incoming_sha256": row["incoming_sha256"],
         "previous_geometry_sha256": row["geometry_sha256"],
         "incoming_geometry_sha256": row["incoming_geometry_sha256"]}
        for row in changed]}


def stage_preflight_previews(release: Path, preview_root: Path,
                             changes: dict) -> dict:
    """Cache only verified *incoming* stock PNGs for a read-only upgrade card.

    Preflight owns this disposable cache. It contains no device, credential,
    Calibration or protected private data and is rebuilt from each verified ZIP.
    """
    incoming = _stock_images(release / "custom_components/switch_vision")
    names = set(changes.get("new", []))
    names.update(item["filename"] for item in changes.get("changed", []))
    if len(names) > 256:
        raise RuntimeError("Oversized faceplate preview request.")
    if preview_root.is_symlink():
        raise RuntimeError("Unsafe faceplate preview directory.")
    if preview_root.exists():
        shutil.rmtree(preview_root)
    if not names:
        return {}
    result = {}
    total = 0
    for name in sorted(names):
        digest = incoming.get(name)
        if not digest or not _NAME.fullmatch(name):
            continue  # An outgoing removed stock image has no new preview.
        source = release / "faceplates" / name
        if not _verified_image(source, digest):
            raise RuntimeError("Cannot verify faceplate preview: " + name)
        total += source.stat().st_size
        if total > 64 * 1024 * 1024:
            raise RuntimeError("Oversized faceplate preview cache.")
        destination = preview_root / digest / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        result[name] = digest
    return result
