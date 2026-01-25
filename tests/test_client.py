"""
Tests for PerplexityClient class.

Covers all acceptance criteria from plan lines 1235-1248:
- Chrome impersonation
- Default headers (20 entries)
- Auto-refresh on 401/403
- SSE parsing with FINAL step extraction
- Citations extraction (max 10)
- Random delay before requests
- Rate limit and error handling
- Mode/model mapping
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from perplexity_deep_research.client import PerplexityClient
from perplexity_deep_research.config import DEFAULT_HEADERS
from perplexity_deep_research.exceptions import (
    AuthenticationError,
    PerplexityError,
    RateLimitError,
)


# Test fixtures
@pytest.fixture
def mock_cookies():
    """Return test cookies with session_token_name."""
    return {
        "session_token": "test-session-token",
        "session_token_name": "__Secure-next-auth.session-token",
        "csrf_token": "test-csrf-token",
        "csrf_token_name": "__Secure-next-auth.csrf-token",
    }


@pytest.fixture
def mock_http_cookies():
    """Return HTTP format cookies."""
    return {
        "__Secure-next-auth.session-token": "test-session-token",
        "__Secure-next-auth.csrf-token": "test-csrf-token",
    }


@pytest.fixture
def mock_sse_response_success():
    """Return mock SSE response with FINAL step containing answer."""
    text_content = json.dumps(
        [
            {
                "step_type": "SEARCH_RESULTS",
                "content": {
                    "web_results": [
                        {"url": "https://example.com/1"},
                        {"url": "https://example.com/2"},
                        {"url": "https://example.com/3"},
                    ]
                },
            },
            {
                "step_type": "FINAL",
                "content": {
                    "answer": json.dumps({"answer": "This is the test answer."})
                },
            },
        ]
    )
    return {
        "backend_uuid": "test-backend-uuid",
        "text": text_content,
    }


@pytest.fixture
def mock_sse_chunks(mock_sse_response_success):
    """Return mock SSE chunks as bytes."""
    data = json.dumps(mock_sse_response_success)
    return [
        f"event: message\r\ndata: {data}".encode("utf-8"),
        b"event: end_of_stream\r\n",
    ]


class TestClientUsesChromImpersonation:
    """Test that client uses Chrome impersonation."""

    def test_client_uses_chrome_impersonation(self, mock_cookies):
        """Mock Session constructor, assert impersonate='chrome'."""
        with (
            patch(
                "perplexity_deep_research.client.get_cookies", return_value=mock_cookies
            ),
            patch(
                "perplexity_deep_research.client.to_http_cookies",
                return_value={"test": "cookie"},
            ),
            patch("perplexity_deep_research.client.requests.Session") as mock_session,
        ):
            mock_session.return_value.get = MagicMock()

            PerplexityClient()

            mock_session.assert_called_once()
            call_kwargs = mock_session.call_args[1]
            assert call_kwargs["impersonate"] == "chrome"


class TestClientUsesDefaultHeaders:
    """Test that client uses 20 default headers."""

    def test_client_uses_default_headers(self, mock_cookies):
        """Assert headers contains 20 entries."""
        with (
            patch(
                "perplexity_deep_research.client.get_cookies", return_value=mock_cookies
            ),
            patch(
                "perplexity_deep_research.client.to_http_cookies",
                return_value={"test": "cookie"},
            ),
            patch("perplexity_deep_research.client.requests.Session") as mock_session,
        ):
            mock_session.return_value.get = MagicMock()

            PerplexityClient()

            call_kwargs = mock_session.call_args[1]
            assert len(call_kwargs["headers"]) == 20
            assert call_kwargs["headers"] == DEFAULT_HEADERS


class TestAutoRefreshOn401:
    """Test auto-refresh on 401/403 errors."""

    def test_auto_refresh_on_401(self, mock_cookies):
        """Mock 401, verify _refresh_cookies called, verify retry."""
        with (
            patch(
                "perplexity_deep_research.client.get_cookies", return_value=mock_cookies
            ),
            patch(
                "perplexity_deep_research.client.to_http_cookies",
                return_value={"test": "cookie"},
            ),
            patch("perplexity_deep_research.client.requests.Session") as mock_session,
            patch(
                "perplexity_deep_research.client.extract_cookies_with_relaunch",
                return_value=mock_cookies,
            ),
            patch("perplexity_deep_research.client.save_cookies"),
            patch("perplexity_deep_research.client.time.sleep"),
        ):
            # First call returns 401, second returns 200
            mock_response_401 = MagicMock()
            mock_response_401.status_code = 401

            mock_response_200 = MagicMock()
            mock_response_200.status_code = 200

            session_instance = MagicMock()
            session_instance.request.side_effect = [
                mock_response_401,
                mock_response_200,
            ]
            mock_session.return_value = session_instance

            client = PerplexityClient()
            response = client._request_with_retry("GET", "https://test.com")

            assert response.status_code == 200
            # Session should be recreated (called twice: init + refresh)
            assert mock_session.call_count == 2


class TestSearchReturnsAnswerDict:
    """Test search returns proper answer dict."""

    def test_search_returns_answer_dict(self, mock_cookies, mock_sse_chunks):
        """Mock successful response, assert shape."""
        with (
            patch(
                "perplexity_deep_research.client.get_cookies", return_value=mock_cookies
            ),
            patch(
                "perplexity_deep_research.client.to_http_cookies",
                return_value={"test": "cookie"},
            ),
            patch("perplexity_deep_research.client.requests.Session") as mock_session,
            patch("perplexity_deep_research.client.time.sleep"),
        ):
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.iter_lines.return_value = iter(mock_sse_chunks)

            session_instance = MagicMock()
            session_instance.request.return_value = mock_response
            mock_session.return_value = session_instance

            client = PerplexityClient()
            result = client.search(
                query="test query",
                mode="auto",
                sources=["web"],
                language="en-US",
            )

            assert "answer" in result
            assert "citations" in result
            assert "backend_uuid" in result
            assert result["answer"] == "This is the test answer."
            assert result["backend_uuid"] == "test-backend-uuid"


class TestParseSSEResponse:
    """Test SSE response parsing."""

    def test_parse_sse_response_extracts_answer(self, mock_cookies, mock_sse_chunks):
        """Verify FINAL step parsing."""
        with (
            patch(
                "perplexity_deep_research.client.get_cookies", return_value=mock_cookies
            ),
            patch(
                "perplexity_deep_research.client.to_http_cookies",
                return_value={"test": "cookie"},
            ),
            patch("perplexity_deep_research.client.requests.Session") as mock_session,
        ):
            mock_session.return_value.get = MagicMock()

            client = PerplexityClient()

            mock_stream = MagicMock()
            mock_stream.iter_lines.return_value = iter(mock_sse_chunks)

            result = client.parse_sse_response(mock_stream)

            assert result["answer"] == "This is the test answer."
            assert result["backend_uuid"] == "test-backend-uuid"

    def test_parse_sse_response_raises_on_empty(self, mock_cookies):
        """Verify PerplexityError on no answer."""
        with (
            patch(
                "perplexity_deep_research.client.get_cookies", return_value=mock_cookies
            ),
            patch(
                "perplexity_deep_research.client.to_http_cookies",
                return_value={"test": "cookie"},
            ),
            patch("perplexity_deep_research.client.requests.Session") as mock_session,
        ):
            mock_session.return_value.get = MagicMock()

            client = PerplexityClient()

            mock_stream = MagicMock()
            mock_stream.iter_lines.return_value = iter([])

            with pytest.raises(PerplexityError, match="No response received"):
                client.parse_sse_response(mock_stream)

    def test_parse_sse_response_raises_on_no_answer(self, mock_cookies):
        """Verify PerplexityError when no answer in response."""
        with (
            patch(
                "perplexity_deep_research.client.get_cookies", return_value=mock_cookies
            ),
            patch(
                "perplexity_deep_research.client.to_http_cookies",
                return_value={"test": "cookie"},
            ),
            patch("perplexity_deep_research.client.requests.Session") as mock_session,
        ):
            mock_session.return_value.get = MagicMock()

            client = PerplexityClient()

            # Response without FINAL step
            text_content = json.dumps([{"step_type": "SEARCH_RESULTS", "content": {}}])
            data = json.dumps({"backend_uuid": "test", "text": text_content})
            chunks = [f"event: message\r\ndata: {data}".encode("utf-8")]

            mock_stream = MagicMock()
            mock_stream.iter_lines.return_value = iter(chunks)

            with pytest.raises(PerplexityError, match="No answer found"):
                client.parse_sse_response(mock_stream)


class TestExtractCitations:
    """Test citations extraction."""

    def test_extract_citations_parsing(self, mock_cookies):
        """Verify web_results extraction and 10-item cap."""
        with (
            patch(
                "perplexity_deep_research.client.get_cookies", return_value=mock_cookies
            ),
            patch(
                "perplexity_deep_research.client.to_http_cookies",
                return_value={"test": "cookie"},
            ),
            patch("perplexity_deep_research.client.requests.Session") as mock_session,
        ):
            mock_session.return_value.get = MagicMock()

            client = PerplexityClient()

            # Create response with 15 URLs (should cap at 10)
            web_results = [{"url": f"https://example.com/{i}"} for i in range(15)]
            response = {
                "text": [
                    {
                        "step_type": "SEARCH_RESULTS",
                        "content": {"web_results": web_results},
                    }
                ]
            }

            citations = client.extract_citations(response)

            assert len(citations) == 10
            assert citations[0] == "https://example.com/0"
            assert citations[9] == "https://example.com/9"

    def test_extract_citations_deduplicates(self, mock_cookies):
        """Verify duplicate URLs are removed."""
        with (
            patch(
                "perplexity_deep_research.client.get_cookies", return_value=mock_cookies
            ),
            patch(
                "perplexity_deep_research.client.to_http_cookies",
                return_value={"test": "cookie"},
            ),
            patch("perplexity_deep_research.client.requests.Session") as mock_session,
        ):
            mock_session.return_value.get = MagicMock()

            client = PerplexityClient()

            response = {
                "text": [
                    {
                        "step_type": "SEARCH_RESULTS",
                        "content": {
                            "web_results": [
                                {"url": "https://example.com/1"},
                                {"url": "https://example.com/1"},  # Duplicate
                                {"url": "https://example.com/2"},
                            ]
                        },
                    }
                ]
            }

            citations = client.extract_citations(response)

            assert len(citations) == 2
            assert "https://example.com/1" in citations
            assert "https://example.com/2" in citations

    def test_extract_citations_from_widget_data(self, mock_cookies):
        """Verify widget_data fallback extraction."""
        with (
            patch(
                "perplexity_deep_research.client.get_cookies", return_value=mock_cookies
            ),
            patch(
                "perplexity_deep_research.client.to_http_cookies",
                return_value={"test": "cookie"},
            ),
            patch("perplexity_deep_research.client.requests.Session") as mock_session,
        ):
            mock_session.return_value.get = MagicMock()

            client = PerplexityClient()

            response = {
                "text": [],
                "widget_data": [
                    {"url": "https://widget.com/1"},
                    {"url": "https://widget.com/2"},
                ],
            }

            citations = client.extract_citations(response)

            assert len(citations) == 2
            assert "https://widget.com/1" in citations
            assert "https://widget.com/2" in citations


class TestRandomDelay:
    """Test random delay before requests."""

    def test_random_delay_called(self, mock_cookies):
        """Mock time.sleep, assert called with value in [1.0, 3.0]."""
        with (
            patch(
                "perplexity_deep_research.client.get_cookies", return_value=mock_cookies
            ),
            patch(
                "perplexity_deep_research.client.to_http_cookies",
                return_value={"test": "cookie"},
            ),
            patch("perplexity_deep_research.client.requests.Session") as mock_session,
            patch("perplexity_deep_research.client.time.sleep") as mock_sleep,
            patch(
                "perplexity_deep_research.client.random.uniform", return_value=2.0
            ) as mock_uniform,
        ):
            mock_response = MagicMock()
            mock_response.status_code = 200

            session_instance = MagicMock()
            session_instance.request.return_value = mock_response
            mock_session.return_value = session_instance

            client = PerplexityClient()
            client._request_with_retry("GET", "https://test.com")

            mock_uniform.assert_called_with(1.0, 3.0)
            mock_sleep.assert_called_with(2.0)


class TestErrorHandling:
    """Test error handling for various HTTP status codes."""

    def test_rate_limit_429_raises(self, mock_cookies):
        """Mock 429, assert RateLimitError."""
        with (
            patch(
                "perplexity_deep_research.client.get_cookies", return_value=mock_cookies
            ),
            patch(
                "perplexity_deep_research.client.to_http_cookies",
                return_value={"test": "cookie"},
            ),
            patch("perplexity_deep_research.client.requests.Session") as mock_session,
            patch("perplexity_deep_research.client.time.sleep"),
        ):
            mock_response = MagicMock()
            mock_response.status_code = 429

            session_instance = MagicMock()
            session_instance.request.return_value = mock_response
            mock_session.return_value = session_instance

            client = PerplexityClient()

            with pytest.raises(RateLimitError, match="Rate limit exceeded"):
                client._request_with_retry("GET", "https://test.com")

    def test_server_error_500_raises(self, mock_cookies):
        """Mock 500, assert PerplexityError."""
        with (
            patch(
                "perplexity_deep_research.client.get_cookies", return_value=mock_cookies
            ),
            patch(
                "perplexity_deep_research.client.to_http_cookies",
                return_value={"test": "cookie"},
            ),
            patch("perplexity_deep_research.client.requests.Session") as mock_session,
            patch("perplexity_deep_research.client.time.sleep"),
        ):
            mock_response = MagicMock()
            mock_response.status_code = 500

            session_instance = MagicMock()
            session_instance.request.return_value = mock_response
            mock_session.return_value = session_instance

            client = PerplexityClient()

            with pytest.raises(PerplexityError, match="API error: HTTP 500"):
                client._request_with_retry("GET", "https://test.com")

    def test_auth_error_after_retry_raises(self, mock_cookies):
        """Mock 401 twice, assert AuthenticationError."""
        with (
            patch(
                "perplexity_deep_research.client.get_cookies", return_value=mock_cookies
            ),
            patch(
                "perplexity_deep_research.client.to_http_cookies",
                return_value={"test": "cookie"},
            ),
            patch("perplexity_deep_research.client.requests.Session") as mock_session,
            patch(
                "perplexity_deep_research.client.extract_cookies_with_relaunch",
                return_value=mock_cookies,
            ),
            patch("perplexity_deep_research.client.save_cookies"),
            patch("perplexity_deep_research.client.time.sleep"),
        ):
            mock_response = MagicMock()
            mock_response.status_code = 401

            session_instance = MagicMock()
            session_instance.request.return_value = mock_response
            mock_session.return_value = session_instance

            client = PerplexityClient()

            with pytest.raises(
                AuthenticationError, match="Authentication failed after retry"
            ):
                client._request_with_retry("GET", "https://test.com")


class TestFollowUpPayload:
    """Test follow-up query payload."""

    def test_follow_up_payload_includes_uuid(self, mock_cookies, mock_sse_chunks):
        """Assert params.last_backend_uuid equals UUID."""
        with (
            patch(
                "perplexity_deep_research.client.get_cookies", return_value=mock_cookies
            ),
            patch(
                "perplexity_deep_research.client.to_http_cookies",
                return_value={"test": "cookie"},
            ),
            patch("perplexity_deep_research.client.requests.Session") as mock_session,
            patch("perplexity_deep_research.client.time.sleep"),
        ):
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.iter_lines.return_value = iter(mock_sse_chunks)

            session_instance = MagicMock()
            session_instance.request.return_value = mock_response
            mock_session.return_value = session_instance

            client = PerplexityClient()
            client.search(
                query="follow up query",
                mode="auto",
                sources=["web"],
                language="en-US",
                follow_up="previous-backend-uuid",
            )

            # Get the payload from the request call
            call_args = session_instance.request.call_args
            payload = call_args[1]["json"]

            assert payload["params"]["last_backend_uuid"] == "previous-backend-uuid"


class TestModeMapping:
    """Test mode/model mapping for different modes."""

    def test_payload_deep_research(self, mock_cookies, mock_sse_chunks):
        """Assert mode='copilot', model_preference='pplx_alpha'."""
        with (
            patch(
                "perplexity_deep_research.client.get_cookies", return_value=mock_cookies
            ),
            patch(
                "perplexity_deep_research.client.to_http_cookies",
                return_value={"test": "cookie"},
            ),
            patch("perplexity_deep_research.client.requests.Session") as mock_session,
            patch("perplexity_deep_research.client.time.sleep"),
        ):
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.iter_lines.return_value = iter(mock_sse_chunks)

            session_instance = MagicMock()
            session_instance.request.return_value = mock_response
            mock_session.return_value = session_instance

            client = PerplexityClient()
            client.search(
                query="test",
                mode="deep research",
                sources=["web"],
                language="en-US",
            )

            call_args = session_instance.request.call_args
            payload = call_args[1]["json"]

            assert payload["params"]["mode"] == "copilot"
            assert payload["params"]["model_preference"] == "pplx_alpha"

    def test_payload_pro(self, mock_cookies, mock_sse_chunks):
        """Assert mode='copilot', model_preference='pplx_pro'."""
        with (
            patch(
                "perplexity_deep_research.client.get_cookies", return_value=mock_cookies
            ),
            patch(
                "perplexity_deep_research.client.to_http_cookies",
                return_value={"test": "cookie"},
            ),
            patch("perplexity_deep_research.client.requests.Session") as mock_session,
            patch("perplexity_deep_research.client.time.sleep"),
        ):
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.iter_lines.return_value = iter(mock_sse_chunks)

            session_instance = MagicMock()
            session_instance.request.return_value = mock_response
            mock_session.return_value = session_instance

            client = PerplexityClient()
            client.search(
                query="test",
                mode="pro",
                sources=["web"],
                language="en-US",
            )

            call_args = session_instance.request.call_args
            payload = call_args[1]["json"]

            assert payload["params"]["mode"] == "copilot"
            assert payload["params"]["model_preference"] == "pplx_pro"

    def test_payload_auto(self, mock_cookies, mock_sse_chunks):
        """Assert mode='concise', model_preference='turbo'."""
        with (
            patch(
                "perplexity_deep_research.client.get_cookies", return_value=mock_cookies
            ),
            patch(
                "perplexity_deep_research.client.to_http_cookies",
                return_value={"test": "cookie"},
            ),
            patch("perplexity_deep_research.client.requests.Session") as mock_session,
            patch("perplexity_deep_research.client.time.sleep"),
        ):
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.iter_lines.return_value = iter(mock_sse_chunks)

            session_instance = MagicMock()
            session_instance.request.return_value = mock_response
            mock_session.return_value = session_instance

            client = PerplexityClient()
            client.search(
                query="test",
                mode="auto",
                sources=["web"],
                language="en-US",
            )

            call_args = session_instance.request.call_args
            payload = call_args[1]["json"]

            assert payload["params"]["mode"] == "concise"
            assert payload["params"]["model_preference"] == "turbo"
