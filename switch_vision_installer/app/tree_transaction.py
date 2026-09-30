from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import json
import os
import shutil
import time


REPLACE_TRANSACTION_SUFFIX = ".switch-vision-replace.json"

RemoveTreePath = Callable[[Path], None]
FsyncDirectory = Callable[[Path], None]
MarkerPath = Callable[[Path], Path]
ValidateTransactionPath = Callable[[Path, Any, str], Path]
LoadTransaction = Callable[[Path], tuple[Path, Path, Path, bool] | None]
RecoverReplacement = Callable[[Path], bool]
WriteTransaction = Callable[[Path, Path, Path, bool], Path]
RollbackReplacement = Callable[[Path, Path, Path, bool], None]


def remove_tree_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        fd = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def replacement_marker_path(destination: Path) -> Path:
    return destination.parent / (
        f".{destination.name}{REPLACE_TRANSACTION_SUFFIX}"
    )


def validated_transaction_path(
    destination: Path,
    value: Any,
    kind: str,
) -> Path:
    parent = destination.parent.resolve()
    candidate = Path(str(value or ""))
    if not candidate.is_absolute():
        candidate = destination.parent / candidate
    try:
        candidate_parent = candidate.parent.resolve()
    except OSError as exc:
        raise RuntimeError(
            f"Interrupted replacement {kind} path is invalid: {candidate}"
        ) from exc
    expected_prefix = f".{destination.name}.switch-vision-{kind}-"
    if (
        candidate_parent != parent
        or not candidate.name.startswith(expected_prefix)
    ):
        raise RuntimeError(
            f"Interrupted replacement {kind} path is outside the expected "
            f"destination directory: {candidate}"
        )
    return candidate


def write_replace_transaction(
    destination: Path,
    stage: Path,
    previous: Path,
    had_destination: bool,
    *,
    marker_path_func: MarkerPath = replacement_marker_path,
    fsync_func: FsyncDirectory = fsync_directory,
) -> Path:
    marker = marker_path_func(destination)
    payload = {
        "schema": 1,
        "destination": str(destination),
        "stage": str(stage),
        "previous": str(previous),
        "had_destination": bool(had_destination),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    temp = marker.parent / f".{marker.name}.{os.getpid()}.tmp"
    try:
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temp.chmod(0o600)
        os.replace(temp, marker)
        fsync_func(marker.parent)
    finally:
        if temp.exists():
            temp.unlink()
    return marker


def load_replace_transaction(
    destination: Path,
    *,
    marker_path_func: MarkerPath = replacement_marker_path,
    validate_path_func: ValidateTransactionPath = validated_transaction_path,
) -> tuple[Path, Path, Path, bool] | None:
    marker = marker_path_func(destination)
    if not marker.exists():
        return None
    if marker.is_symlink() or not marker.is_file():
        raise RuntimeError(
            f"Interrupted replacement marker is not a regular file: {marker}"
        )
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Interrupted replacement marker is unreadable: {marker}"
        ) from exc
    if not isinstance(payload, dict) or payload.get("schema") != 1:
        raise RuntimeError(
            f"Interrupted replacement marker has an unsupported schema: {marker}"
        )
    recorded_destination = Path(str(payload.get("destination") or ""))
    if recorded_destination != destination:
        raise RuntimeError(
            "Interrupted replacement marker destination does not match "
            f"{destination}: {recorded_destination}"
        )
    stage = validate_path_func(destination, payload.get("stage"), "stage")
    previous = validate_path_func(
        destination, payload.get("previous"), "previous"
    )
    return marker, stage, previous, bool(payload.get("had_destination"))


def recover_interrupted_tree_replacement(
    destination: Path,
    *,
    load_transaction_func: LoadTransaction = load_replace_transaction,
    remove_tree_func: RemoveTreePath = remove_tree_path,
    fsync_func: FsyncDirectory = fsync_directory,
) -> bool:
    transaction = load_transaction_func(destination)
    if transaction is None:
        return False
    marker, stage, previous, had_destination = transaction

    if destination.is_symlink():
        raise RuntimeError(
            f"Refusing to recover replacement over symbolic link: {destination}"
        )
    if stage.is_symlink() or previous.is_symlink():
        raise RuntimeError(
            "Interrupted replacement contains an unexpected symbolic link."
        )

    if destination.exists():
        remove_tree_func(previous)
        remove_tree_func(stage)
    elif previous.exists():
        os.replace(previous, destination)
        fsync_func(destination.parent)
        remove_tree_func(stage)
    elif stage.exists() and not had_destination:
        os.replace(stage, destination)
        fsync_func(destination.parent)
    elif stage.exists():
        raise RuntimeError(
            f"Interrupted replacement for {destination} lost its previous tree."
        )
    elif had_destination:
        raise RuntimeError(
            f"Interrupted replacement for {destination} cannot recover the "
            "previous installation."
        )

    marker.unlink(missing_ok=True)
    fsync_func(destination.parent)
    return True


def recover_interrupted_tree_replacements(
    destinations: tuple[Path, ...],
    *,
    recover_func: RecoverReplacement = recover_interrupted_tree_replacement,
) -> list[str]:
    recovered: list[str] = []
    for destination in destinations:
        if recover_func(destination):
            recovered.append(str(destination))
    return recovered


def rollback_tree_replacement(
    destination: Path,
    stage: Path,
    previous: Path,
    had_destination: bool,
    *,
    remove_tree_func: RemoveTreePath = remove_tree_path,
    marker_path_func: MarkerPath = replacement_marker_path,
    fsync_func: FsyncDirectory = fsync_directory,
) -> None:
    if previous.exists():
        if destination.exists():
            if stage.exists():
                remove_tree_func(stage)
            os.replace(destination, stage)
            fsync_func(destination.parent)
        os.replace(previous, destination)
        fsync_func(destination.parent)
        remove_tree_func(stage)
    elif not had_destination and destination.exists():
        if stage.exists():
            remove_tree_func(stage)
        os.replace(destination, stage)
        fsync_func(destination.parent)
        remove_tree_func(stage)
    else:
        remove_tree_func(stage)

    marker = marker_path_func(destination)
    marker.unlink(missing_ok=True)
    fsync_func(destination.parent)


def replace_tree(
    source: Path,
    destination: Path,
    *,
    recover_func: RecoverReplacement = recover_interrupted_tree_replacement,
    remove_tree_func: RemoveTreePath = remove_tree_path,
    write_transaction_func: WriteTransaction = write_replace_transaction,
    rollback_func: RollbackReplacement = rollback_tree_replacement,
    fsync_func: FsyncDirectory = fsync_directory,
) -> None:
    if not source.is_dir():
        raise RuntimeError(f"Replacement source is not a directory: {source}")
    if destination.is_symlink():
        raise RuntimeError(
            f"Refusing to replace symbolic-link destination: {destination}"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    recover_func(destination)

    token = f"{os.getpid()}-{time.monotonic_ns()}"
    stage = destination.parent / (
        f".{destination.name}.switch-vision-stage-{token}"
    )
    previous = destination.parent / (
        f".{destination.name}.switch-vision-previous-{token}"
    )
    had_destination = destination.exists()

    try:
        shutil.copytree(source, stage)
    except Exception:
        remove_tree_func(stage)
        raise

    marker = write_transaction_func(
        destination,
        stage,
        previous,
        had_destination,
    )

    try:
        if had_destination:
            os.replace(destination, previous)
            fsync_func(destination.parent)

        os.replace(stage, destination)
        fsync_func(destination.parent)

        remove_tree_func(previous)
        marker.unlink(missing_ok=True)
        fsync_func(destination.parent)
    except Exception as exc:
        try:
            rollback_func(
                destination,
                stage,
                previous,
                had_destination,
            )
        except Exception as rollback_exc:
            raise RuntimeError(
                f"Atomic replacement failed for {destination}: {exc}. "
                "The durable recovery marker was preserved because automatic "
                f"rollback also failed: {rollback_exc}"
            ) from exc
        raise
