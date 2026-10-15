"""Pre-install artwork provenance for already configured switches (private config)."""
from __future__ import annotations
import json, os, re, tempfile
from pathlib import Path
from typing import Any
import faceplate_history as history

SCHEMA = "switch-vision-faceplate-upgrade-record-v1"
SHA = re.compile(r"^[a-f0-9]{64}$")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,140}\.png$")
BASE = re.compile(r"^(?:native|custom)_[A-Za-z0-9_-]{1,96}$")


def existing_switches(options: Any) -> dict[str, str]:
    rows = options.get("switches") if isinstance(options, dict) else None
    if not isinstance(rows, list):
        return {}
    found, duplicate = {}, set()
    for row in rows[:256]:
        if not isinstance(row, dict):
            continue
        compact = re.sub(r"[^A-Za-z0-9_-]+", "_",
                         str(row.get("switch_name") or "").strip()).strip("_")[:96]
        if not compact:
            continue
        if compact in found:
            duplicate.add(compact)
        else:
            found[compact] = str(row.get("switch_model") or "auto").strip()
    for key in duplicate:
        found.pop(key, None)
    return found


def model_defaults(root: Path) -> dict[str, str]:
    try:
        devices = json.loads((root / "devices/supported_devices.json").read_text())["devices"]
    except (OSError, KeyError, ValueError, TypeError):
        return {}
    found = {}
    for row in devices if isinstance(devices, list) else []:
        if not isinstance(row, dict) or not row.get("dashboard_support"):
            continue
        image = str(row.get("default_faceplate") or "")
        name = image[11:] if image.startswith("faceplates/") else ""
        if NAME.fullmatch(name):
            found[str(row.get("model") or "")] = name
    return found

def prepare_record(release: Path, component: Path, frontend: Path, stage: Path, options: Any) -> dict:
    devices = existing_switches(options)
    if not devices:
        return {}
    before = history._stock_images(component)
    after = history._stock_images(release / "custom_components/switch_vision")
    changed = {}
    for name in sorted(set(before) & set(after)):
        old, new = before[name], after[name]
        if old == new:
            continue
        if all((history._verified_image(frontend / "faceplates" / name, old),
                history._verified_image(release / "faceplates" / name, new),
                history._verified_image(stage / "faceplate-history" / old / name, old))):
            changed[name] = {"before": old, "after": new}
    defaults = model_defaults(release)
    result = {}
    for switch, model in devices.items():
        names = [defaults[model]] if model in defaults else (
            list(changed) if model in ("auto", "") else []
        )
        selection = {name: changed[name] for name in names if name in changed}
        if selection:
            result["native_" + switch] = selection
            result["custom_" + switch] = selection
    return result

def read_record(path: Path) -> dict:
    try:
        if path.is_symlink() or path.stat().st_size > 512 * 1024:
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload.get("choices", {}) if payload.get("schema") == SCHEMA else {}
    except (OSError, ValueError, AttributeError):
        return {}

def store_record(path: Path, new: dict) -> int:
    if not new:
        return 0
    if path.is_symlink():
        raise RuntimeError("Unsafe artwork record")
    current = read_record(path)
    if not isinstance(current, dict):
        raise RuntimeError("Invalid prior artwork record")
    count = 0
    for base, pairs in new.items():
        existing = current.setdefault(base, {})
        for name, revision in pairs.items():
            if name not in existing:
                existing[name] = revision
                count += 1
    if not count:
        return 0
    if len(current) > 512:
        raise RuntimeError("Too many artwork records")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".sv-artwork-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"schema": SCHEMA, "choices": current}, f, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)
    return count
