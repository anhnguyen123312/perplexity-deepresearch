"""Verify GrokClient.search opens Chrome only when statsig cache misses or
the server returns 401/403 — never on the happy path with hot cache.

The client now uses rnet (BoringSSL) instead of curl_cffi so the mocks patch
``deep_research.grok.client.BlockingClient`` and emit responses with the rnet
shape (``status`` stringifies like ``"200 OK"``; ``text()`` is a method).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from deep_research.grok.client import GrokClient


_NDJSON = (
    '{"result":{"conversation":{"conversationId":"c1"},'
    '"response":{"responseId":"r1","token":"4"}}}'
)


def _fake_response(status: int = 200, body: str | None = None) -> MagicMock:
    r = MagicMock()
    # rnet's ``Response.status`` is a StatusCode that stringifies as e.g.
    # ``"200 OK"``; ``client.py`` parses the leading int.
    r.status = f"{status} OK"
    r.text = MagicMock(return_value=body if body is not None else _NDJSON)
    return r


def _client_with_responses(responses) -> MagicMock:
    """Build a mock BlockingClient whose .post() returns the given responses
    (list ⇒ side_effect, single ⇒ return_value)."""
    mc = MagicMock()
    if isinstance(responses, list):
        mc.post.side_effect = responses
    else:
        mc.post.return_value = responses
    return mc


@pytest.fixture
def fake_cookies() -> dict[str, str]:
    return {"sso": "x", "cf_clearance": "y", "x-userid": "z"}


def test_no_chrome_when_statsig_and_cookies_cached(fake_cookies):
    """Happy path: both caches hot ⇒ Chrome capture must NOT be invoked."""
    mock_client = _client_with_responses(_fake_response(200))
    with patch(
        "deep_research.grok.client.get_grok_cookies_cached",
        return_value=fake_cookies,
    ), patch(
        "deep_research.grok.statsig.get_cached_statsig_id",
        return_value="CACHED_SID",
    ) as get_cached, patch(
        "deep_research.grok.statsig.capture_statsig_id_via_chrome"
    ) as capture, patch(
        "deep_research.grok.client.BlockingClient",
        return_value=mock_client,
    ):
        client = GrokClient()
        result = client.search("2+2?", mode="auto")

        assert "error" not in result, result
        assert result["answer"] == "4"
        capture.assert_not_called()
        assert get_cached.called
        assert mock_client.post.call_count == 1


def test_chrome_capture_when_statsig_missing(fake_cookies):
    """Cold statsig cache ⇒ capture invoked once."""
    mock_client = _client_with_responses(_fake_response(200))
    with patch(
        "deep_research.grok.client.get_grok_cookies_cached",
        return_value=fake_cookies,
    ), patch(
        "deep_research.grok.statsig.get_cached_statsig_id",
        return_value=None,
    ), patch(
        "deep_research.grok.statsig.capture_statsig_id_via_chrome",
        return_value="FRESH_SID",
    ) as capture, patch(
        "deep_research.grok.client.BlockingClient",
        return_value=mock_client,
    ):
        client = GrokClient()
        result = client.search("2+2?", mode="auto")

        assert "error" not in result, result
        assert capture.call_count == 1


def test_chrome_capture_on_403_anti_bot(fake_cookies):
    """403 anti-bot on attempt 0 ⇒ capture refresh on attempt 1, then 200."""
    err_body = '{"error":{"code":7,"message":"Request rejected by anti-bot rules."}}'
    mock_client = _client_with_responses(
        [_fake_response(403, body=err_body), _fake_response(200)]
    )
    with patch(
        "deep_research.grok.client.get_grok_cookies_cached",
        return_value=fake_cookies,
    ), patch(
        "deep_research.grok.statsig.get_cached_statsig_id",
        return_value="STALE_SID",
    ), patch(
        "deep_research.grok.statsig.capture_statsig_id_via_chrome",
        return_value="FRESH_SID",
    ) as capture, patch(
        "deep_research.grok.client.BlockingClient",
        return_value=mock_client,
    ):
        client = GrokClient()
        result = client.search("2+2?", mode="auto")

        assert "error" not in result, result
        assert mock_client.post.call_count == 2
        assert capture.call_count == 1


def test_persistent_401_returns_error_after_one_refresh(fake_cookies):
    """Persistent 401 ⇒ one Chrome refresh retry, then error with status=401.

    401 is now treated identically to 403: both indicate the cached
    cookies / statsig are dead, both trigger a single CloakBrowser refresh,
    both surface ``status`` in the error payload if the refresh doesn't help.
    """
    mock_client = _client_with_responses(
        [_fake_response(401, body="unauthorized"), _fake_response(401, body="unauthorized")]
    )
    with patch(
        "deep_research.grok.client.get_grok_cookies_cached",
        return_value=fake_cookies,
    ), patch(
        "deep_research.grok.statsig.get_cached_statsig_id",
        return_value="CACHED_SID",
    ), patch(
        "deep_research.grok.statsig.capture_statsig_id_via_chrome",
        return_value="FRESH_SID",
    ) as capture, patch(
        "deep_research.grok.client.invalidate_grok_cache"
    ) as inval, patch(
        "deep_research.grok.client.BlockingClient",
        return_value=mock_client,
    ):
        client = GrokClient()
        result = client.search("2+2?", mode="auto")

        assert result.get("status") == 401
        assert capture.call_count == 1
        inval.assert_called_once()
        assert mock_client.post.call_count == 2
