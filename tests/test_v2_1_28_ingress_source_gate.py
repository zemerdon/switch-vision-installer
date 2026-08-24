#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "switch_vision_installer" / "app"
sys.path.insert(0, str(APP))

import web_manager  # noqa: E402


def make_handler(source_ip: str):
    handler = web_manager.Handler.__new__(web_manager.Handler)
    handler.client_address = (source_ip, 12345)
    responses = []
    handler.send_json = lambda payload, status=200: responses.append((status, payload))
    return handler, responses


allowed, allowed_responses = make_handler(web_manager.SUPERVISOR_INGRESS_IP)
assert allowed._allow_ingress_request() is True
assert allowed_responses == []

denied, denied_responses = make_handler("172.30.32.3")
assert denied._allow_ingress_request() is False
assert denied_responses == [(403, {"ok": False, "error": "Forbidden"})]

# A rejected GET must stop before route dispatch.
denied_get, denied_get_responses = make_handler("172.30.33.8")
denied_get.path = "/api/components"
web_manager.component_status = lambda: (_ for _ in ()).throw(
    AssertionError("rejected GET reached route dispatch")
)
denied_get.do_GET()
assert denied_get_responses == [(403, {"ok": False, "error": "Forbidden"})]

# A rejected POST must stop before request-body parsing or mutation dispatch.
denied_post, denied_post_responses = make_handler("172.30.33.9")
denied_post.path = "/api/update-component"
denied_post.body = lambda: (_ for _ in ()).throw(
    AssertionError("rejected POST parsed the request body")
)
denied_post.do_POST()
assert denied_post_responses == [(403, {"ok": False, "error": "Forbidden"})]

print("Switch Vision Installer v2.1.28 Supervisor ingress source gate: PASS")
