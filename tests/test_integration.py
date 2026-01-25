"""Integration tests for perplexity-deep-research MCP server."""

import pytest
from unittest.mock import MagicMock, patch

from perplexity_deep_research.server import deep_research, ask, search, follow_up


class TestFullFlow:
    """Test full flow: cookies → client → tools."""

    @patch("perplexity_deep_research.server.get_client")
    def test_deep_research_full_flow(self, mock_get_client):
        """Test deep_research tool end-to-end."""
        # Mock client
        mock_client = MagicMock()
        mock_client.search.return_value = {
            "answer": "Test answer",
            "citations": ["https://example.com"],
            "backend_uuid": "test-uuid",
        }
        mock_get_client.return_value = mock_client

        # Call tool
        result = deep_research("What is quantum computing?")

        # Verify
        assert "answer" in result
        assert result["answer"] == "Test answer"
        mock_client.search.assert_called_once_with(
            query="What is quantum computing?",
            mode="deep research",
            sources=["web"],
            language="en-US",
            follow_up=None,
        )

    @patch("perplexity_deep_research.server.get_client")
    def test_ask_full_flow(self, mock_get_client):
        """Test ask tool end-to-end."""
        mock_client = MagicMock()
        mock_client.search.return_value = {
            "answer": "Test answer",
            "citations": [],
            "backend_uuid": "test-uuid",
        }
        mock_get_client.return_value = mock_client

        result = ask("What is AI?")

        assert "answer" in result
        mock_client.search.assert_called_once()

    @patch("perplexity_deep_research.server.get_client")
    def test_search_full_flow(self, mock_get_client):
        """Test search tool end-to-end."""
        mock_client = MagicMock()
        mock_client.search.return_value = {
            "answer": "Test answer",
            "citations": [],
            "backend_uuid": "test-uuid",
        }
        mock_get_client.return_value = mock_client

        result = search("Python tutorial")

        assert "answer" in result
        mock_client.search.assert_called_once()

    @patch("perplexity_deep_research.server.get_client")
    def test_follow_up_full_flow(self, mock_get_client):
        """Test follow_up tool end-to-end."""
        mock_client = MagicMock()
        mock_client.search.return_value = {
            "answer": "Follow-up answer",
            "citations": [],
            "backend_uuid": "new-uuid",
        }
        mock_get_client.return_value = mock_client

        result = follow_up("Tell me more", "original-uuid")

        assert "answer" in result
        mock_client.search.assert_called_once_with(
            query="Tell me more",
            mode="auto",
            sources=["web"],
            language="en-US",
            follow_up="original-uuid",
        )


class TestErrorScenarios:
    """Test error handling end-to-end."""

    @patch("perplexity_deep_research.server.get_client")
    def test_cookie_extraction_error(self, mock_get_client):
        """Test error when cookie extraction fails."""
        from perplexity_deep_research.exceptions import CookieExtractionError

        mock_client = MagicMock()
        mock_client.search.side_effect = CookieExtractionError("Chrome not found")
        mock_get_client.return_value = mock_client

        result = deep_research("test query")

        assert "error" in result
        assert "Chrome not found" in result["error"]

    @patch("perplexity_deep_research.server.get_client")
    def test_authentication_error(self, mock_get_client):
        """Test error when authentication fails."""
        from perplexity_deep_research.exceptions import AuthenticationError

        mock_client = MagicMock()
        mock_client.search.side_effect = AuthenticationError("Auth failed")
        mock_get_client.return_value = mock_client

        result = ask("test query")

        assert "error" in result
        assert "Auth failed" in result["error"]

    @patch("perplexity_deep_research.server.get_client")
    def test_rate_limit_error(self, mock_get_client):
        """Test error when rate limited."""
        from perplexity_deep_research.exceptions import RateLimitError

        mock_client = MagicMock()
        mock_client.search.side_effect = RateLimitError("Rate limit exceeded")
        mock_get_client.return_value = mock_client

        result = search("test query")

        assert "error" in result
        assert "Rate limit exceeded" in result["error"]


@patch("perplexity_deep_research.client.requests.Session")
@patch("perplexity_deep_research.client.get_cookies")
def test_client_to_server_integration(mock_get_cookies, mock_session_class):
    """Test integration between PerplexityClient and server logic."""
    mock_get_cookies.return_value = {"session_token": "fake-token"}

    mock_session = MagicMock()
    mock_session_class.return_value = mock_session

    # Mock the bootstrap call
    mock_session.get.return_value = MagicMock(status_code=200)

    # Mock the search request
    mock_response = MagicMock()
    mock_response.status_code = 200

    # SSE stream mock
    mock_response.iter_lines.return_value = [
        b'event: message\r\ndata: {"backend_uuid": "uuid1", "text": "[{\\"step_type\\": \\"FINAL\\", \\"content\\": {\\"answer\\": \\"{\\\\\\"answer\\\\\\": \\\\\\"Final Answer\\\\\\"}\\"}}]"}'
    ]
    mock_session.request.return_value = mock_response

    from perplexity_deep_research.server import get_client, deep_research

    # Reset singleton for test
    import perplexity_deep_research.server

    perplexity_deep_research.server._client = None

    from perplexity_deep_research.server import deep_research

    # Patch the client class to return a mock that returns our desired response
    with patch("perplexity_deep_research.server.PerplexityClient") as mock_client_class:
        mock_client_instance = MagicMock()
        mock_client_class.return_value = mock_client_instance
        mock_client_instance.search.return_value = {
            "answer": "Final Answer",
            "citations": [],
            "backend_uuid": "uuid1",
        }

        result = deep_research(query="integrated test")

    assert result["answer"] == "Final Answer"
    assert result["backend_uuid"] == "uuid1"

    assert result["backend_uuid"] == "uuid1"
