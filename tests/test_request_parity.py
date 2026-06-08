"""Request-parity regression: our Perplexity request == the real web app's.

Two levels of proof:

* **Wire-level headers** — fire a REAL curl_cffi request through the exact
  client header-merge path (session ``DEFAULT_HEADERS`` + cloak overrides +
  per-request ``SSE_REQUEST_HEADERS``) at a local echo server, and assert the
  bytes that actually leave the socket reproduce the real Chrome XHR header set.
  This catches the libcurl ``None``-suppression behaviour that a dict-level
  diff cannot (a stray nav header that fails to suppress only shows up on the
  wire).
* **Body params** — assert the JSON body key-set + static values match a
  checked-in capture of the real web app (``fixtures/perplexity_pro_capture.json``).

Ground truth for the header set: a live Playwright ``request.all_headers()``
capture of perplexity.ai's ``/rest/sse/perplexity_ask`` POST (2026-06-08).
``request.all_headers()`` — unlike the older ``request.headers`` — exposes the
browser-auto headers (sec-fetch-*, accept-language, priority, origin), so it is
the authoritative reference. See docs/web-parity-audit/exp.md.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from curl_cffi import requests as cffi_requests

from deep_research import cloak
from deep_research.config import DEFAULT_HEADERS, ENDPOINT_SSE_ASK, SSE_REQUEST_HEADERS

_FIXTURE = Path(__file__).parent / "fixtures" / "perplexity_pro_capture.json"


# The COMPLETE app-relevant low-entropy header set a real Chrome XHR sends to
# /rest/sse/perplexity_ask (from request.all_headers()). Transport/auto headers
# (host, content-length, accept-encoding, cookie, the h2 pseudo-headers, and the
# h2c upgrade pair an http:// test adds) are excluded — curl/libcurl manage them.
# High-entropy client hints (sec-ch-ua-arch/bitness/full-version[-list]/model/
# platform-version) are intentionally NOT reproduced: the server does not require
# them and a fresh client that has not been granted Accept-CH does not send them.
EXPECTED_WIRE_HEADERS = {
    "accept",
    "accept-language",
    "content-type",
    "origin",
    "priority",
    "referer",
    "sec-ch-ua",
    "sec-ch-ua-mobile",
    "sec-ch-ua-platform",
    "sec-fetch-dest",
    "sec-fetch-mode",
    "sec-fetch-site",
    "user-agent",
    "x-perplexity-request-endpoint",
    "x-perplexity-request-reason",
    "x-perplexity-request-try-number",
    "x-request-id",
}

# Auto/transport headers that are NOT part of app-level parity.
_AUTO_HEADERS = {
    "host",
    "content-length",
    "accept-encoding",
    "connection",
    "http2-settings",
    "upgrade",
    "cookie",
}

# Nav-only headers that MUST NOT appear on the XHR (they leak from DEFAULT_HEADERS
# and the per-request None entries must strip them).
_FORBIDDEN_NAV_HEADERS = {
    "sec-fetch-user",
    "upgrade-insecure-requests",
    "cache-control",
    "dnt",
}


@pytest.fixture(scope="module")
def capture() -> dict:
    with open(_FIXTURE) as f:
        return json.load(f)


# --------------------------------------------------------------------------- #
# Wire-level header capture (real curl_cffi -> local echo server)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def wire_headers() -> dict:
    """Headers that ACTUALLY leave the socket for our mode='pro' SSE POST."""
    received: dict[str, str] = {}

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            received.update({k.lower(): v for k, v in self.headers.items()})
            length = int(self.headers.get("content-length", 0))
            self.rfile.read(length)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *a):  # silence
            pass

    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.handle_request, daemon=True).start()

    # Build the session EXACTLY like PerplexityClient._create_session.
    c = cloak.perplexity_cloak()
    session_headers = DEFAULT_HEADERS.copy()
    session_headers["user-agent"] = c["user_agent"]
    session_headers["sec-ch-ua"] = c["sec_ch_ua"]
    session_headers["sec-ch-ua-platform"] = c["sec_ch_ua_platform"]
    sess = cffi_requests.Session(
        headers=session_headers, impersonate=c["impersonate"]
    )

    # Per-request headers EXACTLY like search().
    per_request = dict(SSE_REQUEST_HEADERS)
    per_request["x-request-id"] = "test-uuid"

    sess.post(
        f"http://127.0.0.1:{port}/rest/sse/perplexity_ask",
        json={"q": 1},
        headers=per_request,
    )
    return received


def test_wire_header_key_set_matches_real_browser(wire_headers):
    """On-wire app-relevant header key-set == the real Chrome XHR set."""
    app_headers = {k: v for k, v in wire_headers.items() if k not in _AUTO_HEADERS}
    got = set(app_headers)

    missing = EXPECTED_WIRE_HEADERS - got
    extra = got - EXPECTED_WIRE_HEADERS
    assert not missing, f"Headers the real browser sends but we DON'T: {sorted(missing)}"
    assert not extra, f"Headers we send that the real browser does NOT: {sorted(extra)}"


def test_no_nav_headers_leak_onto_wire(wire_headers):
    """The nav-only headers from DEFAULT_HEADERS must be suppressed (None works)."""
    leaked = _FORBIDDEN_NAV_HEADERS & set(wire_headers)
    assert not leaked, f"Nav-only headers leaked onto the XHR (None-suppression broke): {sorted(leaked)}"


def test_no_literal_none_header_values(wire_headers):
    """A failed None-suppression would send the literal string 'None' — guard it."""
    literal = {k: v for k, v in wire_headers.items() if v == "None" or v is None}
    assert not literal, f"Header(s) sent with literal None value: {literal}"


def test_xhr_sec_fetch_values(wire_headers):
    """sec-fetch-* must carry XHR values, not the leaked nav values."""
    assert wire_headers.get("sec-fetch-dest") == "empty"
    assert wire_headers.get("sec-fetch-mode") == "cors"
    assert wire_headers.get("sec-fetch-site") == "same-origin"
    assert wire_headers.get("priority") == "u=1, i"


# --------------------------------------------------------------------------- #
# Body params parity (dict-level vs checked-in web capture)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def our_body(tmp_path_factory) -> dict:
    tmp = tmp_path_factory.mktemp("parity")
    fake_cookies = {
        "session_token": "stub",
        "session_token_name": "__Secure-next-auth.session-token",
        "csrf_token": "stub-csrf",
        "csrf_token_name": "__Secure-next-auth.csrf-token",
    }
    fake_http_cookies = {"__Secure-next-auth.session-token": "stub"}
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with (
        patch("deep_research.perplexity.client.get_cookies", return_value=fake_cookies),
        patch("deep_research.cookies.to_http_cookies", return_value=fake_http_cookies),
        patch("deep_research.perplexity.client.to_http_cookies", return_value=fake_http_cookies),
        patch("curl_cffi.requests.Session.get", return_value=mock_resp),
        patch.dict("os.environ", {
            "PERPLEXITY_CONFIG_FILE": str(tmp / "config.json"),
            "PERPLEXITY_COOKIES_FILE": str(tmp / "cookies.json"),
        }),
    ):
        from deep_research.perplexity.client import PerplexityClient
        client = PerplexityClient()

    payload = client._build_payload(
        query="What is the capital of France?",
        payload_mode="copilot",
        model_preference="pplx_pro",
        sources=["web"],
        language="en-US",
        follow_up=None,
    )
    return payload


def test_body_top_level_keys(capture, our_body):
    assert set(our_body.keys()) == set(capture["post_data"].keys()) == {"query_str", "params"}


def test_body_params_key_set_matches_web(capture, our_body):
    web = set(capture["post_data"]["params"].keys())
    ours = set(our_body["params"].keys())
    assert ours == web, f"only-web={sorted(web - ours)} only-ours={sorted(ours - web)}"


def test_static_param_values_match(capture, our_body):
    dynamic = {
        "frontend_uuid", "frontend_context_uuid", "rum_session_id",
        "time_from_first_type", "timezone",
        "dsl_query", "query_str", "language", "sources", "mode", "model_preference",
    }
    web = capture["post_data"]["params"]
    ours = our_body["params"]
    mism = {
        k: {"web": web[k], "ours": ours[k]}
        for k in (set(web) & set(ours)) - dynamic
        if web[k] != ours[k]
    }
    assert not mism, f"static param value mismatches: {json.dumps(mism, indent=2)}"


def test_pro_mode_mapping_matches_capture(capture):
    web_mode = capture["post_data"]["params"]["mode"]
    web_model = capture["post_data"]["params"]["model_preference"]
    assert (web_mode, web_model) == ("copilot", "pplx_pro")
