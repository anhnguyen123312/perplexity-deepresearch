"""Tests for deep_research.cloak — dynamic fingerprint alignment + CF detection.

All pure / mocked: no Chrome, no network, no cloakbrowser binary required.
"""

from __future__ import annotations

import pytest

from deep_research import cloak


# --------------------------------------------------------------------------- #
# parse_major
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "text,expected",
    [
        ("148.0.7778.215", 148),
        ("Google Chrome 148.0.7778.215", 148),
        ("Chromium 145.0.7632.109.2", 145),
        ("Google Chrome 130.0.0.0 ", 130),
        ("", None),
        (None, None),
        ("not a version", None),
    ],
)
def test_parse_major(text, expected):
    assert cloak.parse_major(text) == expected


# --------------------------------------------------------------------------- #
# pick_curl_cffi_target — nearest-lower invariant
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "major,expected",
    [
        (148, "chrome146"),   # local newer than newest target → newest
        (146, "chrome146"),   # exact
        (145, "chrome145"),   # exact
        (144, "chrome142"),   # nearest lower
        (137, "chrome136"),
        (98, "chrome146"),    # older than every target → newest fallback (per docstring)
        (None, "chrome146"),  # unknown → newest
    ],
)
def test_pick_curl_cffi_target(major, expected):
    assert cloak.pick_curl_cffi_target(major) == expected


def test_pick_curl_cffi_target_custom_available():
    assert cloak.pick_curl_cffi_target(148, available=(120, 110)) == "chrome120"


# --------------------------------------------------------------------------- #
# pick_rnet_emulation_name — nearest-lower over actually-present members
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "major,available,expected",
    [
        (145, [130, 145], "Chrome145"),       # exact
        (148, [130, 145], "Chrome145"),       # above all → highest
        (146, [130, 145], "Chrome145"),       # nearest lower
        (120, [130, 145], "Chrome130"),       # below all → lowest available
        (135, [130, 137, 145], "Chrome130"),  # nearest lower
    ],
)
def test_pick_rnet_emulation_name(major, available, expected):
    assert cloak.pick_rnet_emulation_name(major, available_majors=available) == expected


def test_pick_rnet_emulation_name_no_introspection_echoes():
    # Empty availability → echo requested major for caller getattr fallback.
    assert cloak.pick_rnet_emulation_name(145, available_majors=[]) == "Chrome145"


# --------------------------------------------------------------------------- #
# UA / sec-ch-ua construction — major must appear, format sane
# --------------------------------------------------------------------------- #
def test_build_ua_contains_major():
    ua = cloak.build_ua(146)
    assert "Chrome/146.0.0.0" in ua
    assert ua.startswith("Mozilla/5.0")
    assert "Safari/537.36" in ua


def test_build_sec_ch_ua_contains_major():
    sec = cloak.build_sec_ch_ua(146)
    assert 'v="146"' in sec
    assert "Google Chrome" in sec and "Chromium" in sec


# --------------------------------------------------------------------------- #
# detect_chrome_major — success + failure (fallback) paths
# --------------------------------------------------------------------------- #
def test_detect_chrome_major_success(monkeypatch):
    monkeypatch.setattr(cloak, "_detect_chrome_version_text", lambda: "148.0.7778.215")
    cloak.detect_chrome_major.cache_clear()
    assert cloak.detect_chrome_major() == 148
    cloak.detect_chrome_major.cache_clear()


def test_detect_chrome_major_failure_returns_none(monkeypatch):
    monkeypatch.setattr(cloak, "_detect_chrome_version_text", lambda: None)
    cloak.detect_chrome_major.cache_clear()
    assert cloak.detect_chrome_major() is None
    cloak.detect_chrome_major.cache_clear()


# --------------------------------------------------------------------------- #
# Composers — the alignment invariant (UA major == impersonation target major)
# --------------------------------------------------------------------------- #
def test_perplexity_cloak_alignment(monkeypatch):
    monkeypatch.setattr(cloak, "_detect_chrome_version_text", lambda: "148.0.7778.215")
    cloak.detect_chrome_major.cache_clear()
    c = cloak.perplexity_cloak()
    # local Chrome 148 → curl_cffi nearest = chrome146, and UA/sec-ch-ua MUST be 146.
    assert c["impersonate"] == "chrome146"
    assert "Chrome/146.0.0.0" in c["user_agent"]
    assert 'v="146"' in c["sec_ch_ua"]
    cloak.detect_chrome_major.cache_clear()


def test_perplexity_cloak_fallback_when_undetected(monkeypatch):
    monkeypatch.setattr(cloak, "_detect_chrome_version_text", lambda: None)
    cloak.detect_chrome_major.cache_clear()
    c = cloak.perplexity_cloak()
    assert c["impersonate"] == f"chrome{cloak.FALLBACK_LOCAL_MAJOR}"
    assert f"Chrome/{cloak.FALLBACK_LOCAL_MAJOR}.0.0.0" in c["user_agent"]
    cloak.detect_chrome_major.cache_clear()


def test_grok_major_follows_cloakbrowser(monkeypatch):
    monkeypatch.setattr(cloak, "cloakbrowser_binary_major", lambda: 145)
    assert cloak.grok_major() == 145
    monkeypatch.setattr(cloak, "cloakbrowser_binary_major", lambda: None)
    assert cloak.grok_major() == cloak.FALLBACK_CLOAKBROWSER_MAJOR


# --------------------------------------------------------------------------- #
# is_cloudflare_challenge — every tier + true negatives
# --------------------------------------------------------------------------- #
def test_cf_mitigated_header_definitive():
    assert cloak.is_cloudflare_challenge(403, {"cf-mitigated": "challenge"}, "")


def test_cf_503_with_cf_server():
    assert cloak.is_cloudflare_challenge(503, {"server": "cloudflare", "cf-ray": "abc"}, "")


def test_not_cf_genuine_403_behind_cloudflare():
    # perplexity.ai / grok.com sit behind Cloudflare, so a genuine auth 403 also
    # carries cf-ray/server:cloudflare. Without cf-mitigated or challenge body
    # tokens it must NOT be flagged (else real auth failures misroute to the
    # browser-solve path).
    assert not cloak.is_cloudflare_challenge(
        403,
        {"server": "cloudflare", "cf-ray": "x", "content-type": "application/json"},
        '{"error":"unauthorized"}',
    )


def test_cf_403_with_cf_mitigated_header():
    # The reliable signal for a 403 challenge is the cf-mitigated header.
    assert cloak.is_cloudflare_challenge(
        403, {"server": "cloudflare", "cf-mitigated": "challenge"}, ""
    )


def test_cf_body_interstitial_on_200():
    body = "<html><head><title>Just a moment...</title></head><body>window._cf_chl_opt={}</body></html>"
    assert cloak.is_cloudflare_challenge(
        200, {"server": "cloudflare", "cf-ray": "abc", "content-type": "text/html"}, body
    )


def test_not_cf_200_answer_mentions_cloudflare():
    # A Grok 200 NDJSON answer that talks ABOUT Cloudflare must NOT be flagged
    # (no CF server header → a clean app 200 is never a challenge).
    body = (
        "Cloudflare protects sites with challenges.cloudflare.com and the "
        '__cf_chl / cf_chl_opt tokens; the page shows "Just a moment...".'
    )
    assert not cloak.is_cloudflare_challenge(200, {}, body)


def test_cf_grok_403_html_strict_marker():
    # Grok client passes empty headers; a real CF 403 HTML body is still caught
    # via the unambiguous strict token even without a server header.
    body = "<html><body><script>window._cf_chl_opt = {cvId:'3'}</script></body></html>"
    assert cloak.is_cloudflare_challenge(403, {}, body)


def test_cf_hidden_200_interstitial():
    body = "<html><title>Attention Required! | Cloudflare</title></html>"
    assert cloak.is_cloudflare_challenge(200, {"server": "cloudflare", "content-type": "text/html"}, body)


def test_not_cf_normal_app_200():
    assert not cloak.is_cloudflare_challenge(200, {"content-type": "text/event-stream"}, "")


def test_not_cf_plain_app_401():
    # App-level auth failure (no CF markers) must NOT be treated as a CF wall.
    assert not cloak.is_cloudflare_challenge(401, {"content-type": "application/json"}, "unauthorized")


def test_not_cf_plain_app_403_json():
    assert not cloak.is_cloudflare_challenge(
        403, {"content-type": "application/json", "server": "envoy"}, '{"error":"forbidden"}'
    )
