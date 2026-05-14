"""Verify GrokClient.search opens Chrome only when statsig cache misses or
the server returns 403 anti-bot — never on the happy path with hot cache.
"""

from __future__ import annotations

import io
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from perplexity_deep_research.grok.client import GrokClient


def _fake_stream_lines() -> list[bytes]:
    return [
        (
            b'{"result":{"conversation":{"conversationId":"c1"},'
            b'"response":{"responseId":"r1","token":"4"}}}'
        ),
    ]


def _fake_response(status: int = 200, body: bytes = b"") -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.iter_lines = MagicMock(return_value=iter(_fake_stream_lines()))
    r.iter_content = MagicMock(return_value=iter([body]))
    return r


@pytest.fixture
def fake_cookies() -> dict[str, str]:
    return {"sso": "x", "cf_clearance": "y", "x-userid": "z"}


def test_no_chrome_when_statsig_and_cookies_cached(fake_cookies):
    """Happy path: both caches hot ⇒ Chrome capture must NOT be invoked."""
    with patch(
        "perplexity_deep_research.grok.client.get_grok_cookies_cached",
        return_value=fake_cookies,
    ), patch(
        "perplexity_deep_research.grok.statsig.get_cached_statsig_id",
        return_value="CACHED_SID",
    ) as get_cached, patch(
        "perplexity_deep_research.grok.statsig.capture_statsig_id_via_chrome"
    ) as capture, patch(
        "curl_cffi.requests.Session.post",
        return_value=_fake_response(200),
    ) as post:
        client = GrokClient()
        result = client.search("2+2?", mode="auto")

        assert "error" not in result, result
        assert result["answer"] == "4"
        capture.assert_not_called()
        assert get_cached.called
        assert post.call_count == 1


def test_chrome_capture_when_statsig_missing(fake_cookies):
    """Cold statsig cache ⇒ capture invoked once."""
    with patch(
        "perplexity_deep_research.grok.client.get_grok_cookies_cached",
        return_value=fake_cookies,
    ), patch(
        "perplexity_deep_research.grok.statsig.get_cached_statsig_id",
        return_value=None,
    ), patch(
        "perplexity_deep_research.grok.statsig.capture_statsig_id_via_chrome",
        return_value="FRESH_SID",
    ) as capture, patch(
        "curl_cffi.requests.Session.post",
        return_value=_fake_response(200),
    ):
        client = GrokClient()
        result = client.search("2+2?", mode="auto")

        assert "error" not in result, result
        assert capture.call_count == 1


def test_chrome_capture_on_403_anti_bot(fake_cookies):
    """403 anti-bot on attempt 0 ⇒ capture refresh on attempt 1, then 200."""
    err_body = b'{"error":{"code":7,"message":"Request rejected by anti-bot rules."}}'
    responses = [_fake_response(403, body=err_body), _fake_response(200)]

    with patch(
        "perplexity_deep_research.grok.client.get_grok_cookies_cached",
        return_value=fake_cookies,
    ), patch(
        "perplexity_deep_research.grok.statsig.get_cached_statsig_id",
        return_value="STALE_SID",
    ), patch(
        "perplexity_deep_research.grok.statsig.capture_statsig_id_via_chrome",
        return_value="FRESH_SID",
    ) as capture, patch(
        "curl_cffi.requests.Session.post",
        side_effect=responses,
    ) as post:
        client = GrokClient()
        result = client.search("2+2?", mode="auto")

        assert "error" not in result, result
        assert post.call_count == 2
        assert capture.call_count == 1


def test_no_chrome_on_401(fake_cookies):
    """401 ⇒ invalidate cookies + return error, no Chrome capture."""
    with patch(
        "perplexity_deep_research.grok.client.get_grok_cookies_cached",
        return_value=fake_cookies,
    ), patch(
        "perplexity_deep_research.grok.statsig.get_cached_statsig_id",
        return_value="CACHED_SID",
    ), patch(
        "perplexity_deep_research.grok.statsig.capture_statsig_id_via_chrome"
    ) as capture, patch(
        "perplexity_deep_research.grok.client.invalidate_grok_cache"
    ) as inval, patch(
        "curl_cffi.requests.Session.post",
        return_value=_fake_response(401, body=b"unauthorized"),
    ):
        client = GrokClient()
        result = client.search("2+2?", mode="auto")

        assert result.get("status") == 401
        capture.assert_not_called()
        inval.assert_called_once()
