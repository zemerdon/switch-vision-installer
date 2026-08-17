#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import importlib.util
import io
import json
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "switch_vision_installer" / "app"
INSTALLER = APP / "installer.py"
WEB = APP / "web.py"
sys.path.insert(0, str(APP))

spec = importlib.util.spec_from_file_location("sv_installer_v221", INSTALLER)
assert spec and spec.loader
installer = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = installer
spec.loader.exec_module(installer)
assert installer.INSTALLER_VERSION == "2.1.21"

def make_zip(path: Path, entries):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, payload in entries:
            zf.writestr(name, payload)

with tempfile.TemporaryDirectory() as td:
    base = Path(td)
    archive = base / "ok.zip"
    dest = base / "out"
    make_zip(archive, [("root/file.txt", b"hello")])
    installer.safe_extract(archive, dest)
    assert (dest / "root/file.txt").read_bytes() == b"hello"

with tempfile.TemporaryDirectory() as td:
    base = Path(td)
    archive = base / "traversal.zip"
    make_zip(archive, [("../escape.txt", b"x")])
    try:
        installer.safe_extract(archive, base / "out")
    except RuntimeError as exc:
        assert "Unsafe archive member" in str(exc)
    else:
        raise AssertionError("path traversal archive was accepted")

original = (
    installer.MAX_ARCHIVE_ENTRIES,
    installer.MAX_ARCHIVE_MEMBER_UNCOMPRESSED_BYTES,
    installer.MAX_ARCHIVE_TOTAL_UNCOMPRESSED_BYTES,
    installer.MAX_ARCHIVE_COMPRESSION_RATIO,
)
try:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        archive = base / "entries.zip"
        make_zip(archive, [("a", b"1"), ("b", b"2")])
        installer.MAX_ARCHIVE_ENTRIES = 1
        try:
            installer.safe_extract(archive, base / "out")
        except RuntimeError as exc:
            assert "too many entries" in str(exc)
        else:
            raise AssertionError("entry-count limit was not enforced")
    installer.MAX_ARCHIVE_ENTRIES = original[0]

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        archive = base / "member.zip"
        make_zip(archive, [("big.bin", b"x" * 64)])
        installer.MAX_ARCHIVE_MEMBER_UNCOMPRESSED_BYTES = 32
        try:
            installer.safe_extract(archive, base / "out")
        except RuntimeError as exc:
            assert "too large after decompression" in str(exc)
        else:
            raise AssertionError("member-size limit was not enforced")
    installer.MAX_ARCHIVE_MEMBER_UNCOMPRESSED_BYTES = original[1]

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        archive = base / "total.zip"
        make_zip(archive, [("a.bin", b"a" * 32), ("b.bin", b"b" * 32)])
        installer.MAX_ARCHIVE_TOTAL_UNCOMPRESSED_BYTES = 48
        try:
            installer.safe_extract(archive, base / "out")
        except RuntimeError as exc:
            assert "total uncompressed size limit" in str(exc)
        else:
            raise AssertionError("total-size limit was not enforced")
    installer.MAX_ARCHIVE_TOTAL_UNCOMPRESSED_BYTES = original[2]

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        archive = base / "ratio.zip"
        make_zip(archive, [("ratio.bin", b"A" * 4096)])
        installer.MAX_ARCHIVE_COMPRESSION_RATIO = 2.0
        try:
            installer.safe_extract(archive, base / "out")
        except RuntimeError as exc:
            assert "compression-ratio limit" in str(exc)
        else:
            raise AssertionError("compression-ratio limit was not enforced")
finally:
    (
        installer.MAX_ARCHIVE_ENTRIES,
        installer.MAX_ARCHIVE_MEMBER_UNCOMPRESSED_BYTES,
        installer.MAX_ARCHIVE_TOTAL_UNCOMPRESSED_BYTES,
        installer.MAX_ARCHIVE_COMPRESSION_RATIO,
    ) = original

web_spec = importlib.util.spec_from_file_location("sv_installer_web_v221", WEB)
assert web_spec and web_spec.loader
web = importlib.util.module_from_spec(web_spec)
sys.modules[web_spec.name] = web
web_spec.loader.exec_module(web)
assert web.MAX_POST_BODY_BYTES == 64 * 1024

def fake_handler(body: bytes, content_length: str | None = None):
    handler = object.__new__(web.Handler)
    handler.headers = {"Content-Length": content_length if content_length is not None else str(len(body))}
    handler.rfile = io.BytesIO(body)
    return handler

assert web.Handler.body(fake_handler(b'{"name":"backup"}')) == {"name": "backup"}

for bad in ("abc", "-1"):
    try:
        web.Handler.body(fake_handler(b"", bad))
    except web.RequestBodyError as exc:
        assert exc.status == 400
    else:
        raise AssertionError("invalid Content-Length accepted")

try:
    web.Handler.body(fake_handler(b"", str(web.MAX_POST_BODY_BYTES + 1)))
except web.RequestBodyError as exc:
    assert exc.status == 413
else:
    raise AssertionError("oversized POST body accepted")

for payload in (b"not-json", json.dumps([1, 2, 3]).encode()):
    try:
        web.Handler.body(fake_handler(payload))
    except web.RequestBodyError as exc:
        assert exc.status == 400
    else:
        raise AssertionError("invalid JSON body accepted")

print("Switch Vision Installer v2.1.21 archive/HTTP hardening regression: PASS")
