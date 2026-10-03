#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
GENERATED_ROOTS = ("switch_vision_installer", "tests", "tools")


def release_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def run(args: list[str], cwd: Path) -> str:
    proc = subprocess.run(
        args,
        cwd=cwd,
        env=release_env(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
    if proc.returncode:
        raise SystemExit(
            f"Installer release check command failed ({proc.returncode}): "
            + " ".join(args)
        )
    return proc.stdout or ""


def git_status(root: Path) -> str:
    proc = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={root}",
            "-C",
            str(root),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode:
        raise SystemExit(
            "Installer git status failed: "
            + (proc.stderr or proc.stdout or "").strip()
        )
    return proc.stdout or ""


def resolve_version(root: Path) -> str:
    text = (
        root / "switch_vision_installer/config.yaml"
    ).read_text(encoding="utf-8")
    match = re.search(
        r'^version:\s*["\']?(\d+\.\d+\.\d+)["\']?\s*$',
        text,
        flags=re.MULTILINE,
    )
    version = match.group(1) if match else ""
    if not SEMVER_RE.fullmatch(version):
        raise SystemExit(
            f"Installer config version is not exact semantic version: {version!r}"
        )
    return version


def validate_version_contract(root: Path, version: str) -> None:
    changelog = (
        root / "switch_vision_installer/CHANGELOG.md"
    ).read_text(encoding="utf-8")
    if not changelog.startswith(f"## v{version} "):
        raise SystemExit(
            "Installer changelog does not start with the current config version"
        )
    dockerfile = (
        root / "switch_vision_installer/Dockerfile"
    ).read_text(encoding="utf-8")
    web = (
        root / "switch_vision_installer/app/web.py"
    ).read_text(encoding="utf-8")
    if "ENV SV_INSTALLER_VERSION=${BUILD_VERSION}" not in dockerfile:
        raise SystemExit(
            "Installer Docker BUILD_VERSION runtime projection is missing"
        )
    if 'os.environ.get("SV_INSTALLER_VERSION")' not in web:
        raise SystemExit(
            "Installer runtime does not consume SV_INSTALLER_VERSION"
        )
    print(f"Installer {version} version metadata contract: PASS")


def generated_junk(root: Path) -> list[Path]:
    problems: list[Path] = []
    for relative in GENERATED_ROOTS:
        base = root / relative
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_dir() and path.name == "__pycache__":
                problems.append(path)
            elif path.is_file() and (
                path.suffix in {".pyc", ".pyo"}
                or path.name == ".DS_Store"
            ):
                problems.append(path)
    return problems


def reject_generated_junk(root: Path) -> None:
    problems = generated_junk(root)
    if problems:
        shown = ", ".join(
            str(path.relative_to(root)) for path in problems[:20]
        )
        raise SystemExit(
            "Installer generated cache/junk material present: " + shown
        )
    print("Installer source hygiene: PASS")


def compile_python_sources(root: Path) -> None:
    paths = sorted(
        path
        for base in (
            root / "switch_vision_installer/app",
            root / "tests",
            root / "tools",
        )
        if base.exists()
        for path in base.glob("*.py")
    )
    if not paths:
        raise SystemExit("Installer Python source inventory is empty")
    for path in paths:
        source = path.read_text(encoding="utf-8")
        compile(source, str(path), "exec")
    print(f"Installer Python syntax: PASS ({len(paths)} files)")


def validate_dockerfile_contract(root: Path) -> None:
    text = (
        root / "switch_vision_installer/Dockerfile"
    ).read_text(encoding="utf-8")
    required = (
        "FROM ghcr.io/home-assistant/base@sha256:",
        "ARG BUILD_VERSION",
        "ARG BUILD_ARCH",
        "ENV SV_INSTALLER_VERSION=${BUILD_VERSION}",
        'CMD [ "/run.sh" ]',
    )
    missing = [token for token in required if token not in text]
    if missing:
        raise SystemExit(
            "Installer Dockerfile release contract missing: "
            + ", ".join(missing)
        )
    print("Installer Dockerfile release contract: PASS")


def permanent_checks(root: Path) -> tuple[Path, ...]:
    tests = tuple(sorted((root / "tests").glob("test_*.py")))
    own = root / "tools/test_sv_release_check.py"
    if not tests:
        raise SystemExit("Installer permanent regression inventory is empty")
    if not own.is_file():
        raise SystemExit("Installer release-check regression is missing")
    return tests + (own,)


def run_permanent_checks(root: Path) -> None:
    checks = permanent_checks(root)
    for path in checks:
        print(f"=== {path.relative_to(root)} ===")
        run([sys.executable, str(path)], root)
    print(
        f"Installer permanent regression suite: PASS ({len(checks)} checks)"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the product-owned Switch Vision Installer release validation."
        )
    )
    parser.add_argument("--mode", choices=("release",), required=True)
    args = parser.parse_args()
    if args.mode != "release":
        raise SystemExit("unsupported release-check mode")

    root = ROOT
    baseline_status = git_status(root)
    version = resolve_version(root)

    reject_generated_junk(root)
    compile_python_sources(root)
    run(["bash", "-n", "switch_vision_installer/run.sh"], root)
    validate_version_contract(root, version)
    validate_dockerfile_contract(root)
    run_permanent_checks(root)
    reject_generated_junk(root)
    validate_version_contract(root, version)

    final_status = git_status(root)
    if final_status != baseline_status:
        print(
            "Installer release check changed repository state.",
            file=sys.stderr,
        )
        print("--- baseline status ---", file=sys.stderr)
        print(
            baseline_status,
            end="" if baseline_status.endswith("\n") else "\n",
            file=sys.stderr,
        )
        print("--- final status ---", file=sys.stderr)
        print(
            final_status,
            end="" if final_status.endswith("\n") else "\n",
            file=sys.stderr,
        )
        return 1

    print(f"Installer {version} deterministic release validation: PASS")
    print("SV_RELEASE_CHECK_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
