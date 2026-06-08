#!/usr/bin/env python3
"""Intercept + diff: prove the Perplexity MCP request matches the real web app.

Fires a REAL curl_cffi request (mode='pro') through the exact client header-merge
path at a local echo server, and diffs the bytes that actually leave the socket
against the real-browser ground truth (Playwright ``request.all_headers()``
capture, 2026-06-08). Also diffs the JSON body params against the checked-in
web capture fixture.

Usage:  python tools/verify_request_parity.py
Exit 0 = PARITY OK, 1 = DIFF FOUND. No network, no cookies.
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import MagicMock, patch

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from curl_cffi import requests as cffi_requests  # noqa: E402

from deep_research import cloak  # noqa: E402
from deep_research.config import (  # noqa: E402
    DEFAULT_HEADERS,
    ENDPOINT_SSE_ASK,
    SSE_REQUEST_HEADERS,
)

_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "perplexity_pro_capture.json"

# Complete app-relevant header set a real Chrome XHR sends to the SSE ask POST
# (from request.all_headers()). See tests/test_request_parity.py for provenance.
EXPECTED_WIRE_HEADERS = {
    "accept", "accept-language", "content-type", "origin", "priority", "referer",
    "sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform",
    "sec-fetch-dest", "sec-fetch-mode", "sec-fetch-site", "user-agent",
    "x-perplexity-request-endpoint", "x-perplexity-request-reason",
    "x-perplexity-request-try-number", "x-request-id",
}
_AUTO = {"host", "content-length", "accept-encoding", "connection",
         "http2-settings", "upgrade", "cookie"}
_FORBIDDEN_NAV = {"sec-fetch-user", "upgrade-insecure-requests", "cache-control", "dnt"}
_DYNAMIC_PARAMS = {
    "frontend_uuid", "frontend_context_uuid", "rum_session_id",
    "time_from_first_type", "timezone",
    "dsl_query", "query_str", "language", "sources", "mode", "model_preference",
}


def capture_wire_headers() -> dict:
    received: dict[str, str] = {}

    class _H(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            received.update({k.lower(): v for k, v in self.headers.items()})
            self.rfile.read(int(self.headers.get("content-length", 0)))
            self.send_response(200); self.end_headers(); self.wfile.write(b"{}")

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), _H)
    port = srv.server_address[1]
    threading.Thread(target=srv.handle_request, daemon=True).start()

    c = cloak.perplexity_cloak()
    sh = DEFAULT_HEADERS.copy()
    sh["user-agent"] = c["user_agent"]
    sh["sec-ch-ua"] = c["sec_ch_ua"]
    sh["sec-ch-ua-platform"] = c["sec_ch_ua_platform"]
    sess = cffi_requests.Session(headers=sh, impersonate=c["impersonate"])
    per = dict(SSE_REQUEST_HEADERS)
    per["x-request-id"] = "verify-uuid"
    sess.post(f"http://127.0.0.1:{port}/rest/sse/perplexity_ask", json={"q": 1}, headers=per)
    return received


def build_body() -> dict:
    fake = {
        "session_token": "stub", "session_token_name": "__Secure-next-auth.session-token",
        "csrf_token": "stub", "csrf_token_name": "__Secure-next-auth.csrf-token",
    }
    resp = MagicMock(); resp.status_code = 200
    with (
        patch("deep_research.perplexity.client.get_cookies", return_value=fake),
        patch("deep_research.cookies.to_http_cookies", return_value={"x": "y"}),
        patch("deep_research.perplexity.client.to_http_cookies", return_value={"x": "y"}),
        patch("curl_cffi.requests.Session.get", return_value=resp),
    ):
        from deep_research.perplexity.client import PerplexityClient
        client = PerplexityClient()
    return client._build_payload(
        query="What is the capital of France?", payload_mode="copilot",
        model_preference="pplx_pro", sources=["web"], language="en-US", follow_up=None,
    )


def main() -> int:
    capture = json.loads(_FIXTURE.read_text())
    wire = capture_wire_headers()
    app_headers = {k: v for k, v in wire.items() if k not in _AUTO}
    got = set(app_headers)

    print("=" * 70)
    print("PERPLEXITY REQUEST PARITY (wire-level intercept vs real browser)")
    print("=" * 70)

    print("\n--- ON-WIRE HEADERS (app-relevant) ---")
    for k in sorted(app_headers):
        print(f"  {k}: {app_headers[k]}")

    missing = EXPECTED_WIRE_HEADERS - got
    extra = got - EXPECTED_WIRE_HEADERS
    leaked = _FORBIDDEN_NAV & set(wire)
    literal_none = {k: v for k, v in wire.items() if v == "None" or v is None}

    print("\n--- HEADER VERDICT ---")
    print(f"  missing (web has, we don't): {sorted(missing) or 'NONE'}")
    print(f"  extra   (we send, web doesn't): {sorted(extra) or 'NONE'}")
    print(f"  nav headers leaked:           {sorted(leaked) or 'NONE'}")
    print(f"  literal 'None' values:        {literal_none or 'NONE'}")

    body = build_body()
    web_params = capture["post_data"]["params"]
    our_params = body["params"]
    p_missing = set(web_params) - set(our_params)
    p_extra = set(our_params) - set(web_params)
    static_mism = {
        k: (web_params[k], our_params[k])
        for k in (set(web_params) & set(our_params)) - _DYNAMIC_PARAMS
        if web_params[k] != our_params[k]
    }
    print("\n--- BODY VERDICT ---")
    print(f"  params missing: {sorted(p_missing) or 'NONE'}")
    print(f"  params extra:   {sorted(p_extra) or 'NONE'}")
    print(f"  static value mismatches: {static_mism or 'NONE'}")

    ok = not any([missing, extra, leaked, literal_none, p_missing, p_extra, static_mism])
    print("\n" + "=" * 70)
    if ok:
        print("FINAL VERDICT: PARITY OK  ✅")
        print("  (sec-ch-ua / user-agent major may read 146 vs real 147/148 — curl_cffi")
        print("   ceiling; internally consistent, not a key-set deviation.)")
    else:
        print("FINAL VERDICT: DIFF FOUND  ❌")
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
