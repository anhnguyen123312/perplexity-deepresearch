"""Tests for MCP server with 5 tools."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from perplexity_deep_research.server import (
    mcp,
    get_client,
    deep_research,
    ask,
    reason,
    search,
    follow_up,
)


class TestExactly5ToolsRegistered:
    """Test that exactly 5 tools are registered."""

    def test_exactly_5_tools_registered(self):
        """Assert deep_research, ask, reason, search, follow_up are registered."""
        from perplexity_deep_research import server

        # Verify all 5 tools exist
        assert hasattr(server, "deep_research")
        assert hasattr(server, "ask")
        assert hasattr(server, "reason")
        assert hasattr(server, "search")
        assert hasattr(server, "follow_up")

        # Verify they are callable
        assert callable(server.deep_research)
        assert callable(server.ask)
        assert callable(server.reason)
        assert callable(server.search)
        assert callable(server.follow_up)

        # Verify they have @mcp.tool() decorator
        assert hasattr(mcp, "_tool_manager")
        tool_names = list(mcp._tool_manager._tools.keys())

        # Should have exactly 5 tools
        assert len(tool_names) == 5, (
            f"Expected 5 tools, got {len(tool_names)}: {tool_names}"
        )

        # Should have exactly these tools
        expected_tools = {"deep_research", "ask", "reason", "search", "follow_up"}
        actual_tools = set(tool_names)
        assert actual_tools == expected_tools, (
            f"Expected {expected_tools}, got {actual_tools}"
        )


class TestDeepResearchCallable:
    """Test deep_research tool is callable."""

    @patch("perplexity_deep_research.server.get_client")
    def test_deep_research_callable(self, mock_get_client):
        """Call deep_research, assert returns dict."""
        # Mock client
        mock_client = Mock()
        mock_client.search.return_value = {
            "answer": "Test answer",
            "citations": ["https://example.com"],
            "backend_uuid": "test-uuid-123",
        }
        mock_get_client.return_value = mock_client

        # Call tool
        result = deep_research(query="test query")

        # Verify result is dict
        assert isinstance(result, dict)
        assert "answer" in result or "error" in result

        # Verify client.search was called with correct mode
        mock_client.search.assert_called_once()
        call_kwargs = mock_client.search.call_args[1]
        assert call_kwargs["mode"] == "deep research"
        assert call_kwargs["query"] == "test query"
        assert call_kwargs["follow_up"] is None

    @patch("perplexity_deep_research.server.get_client")
    def test_deep_research_with_custom_sources(self, mock_get_client):
        """Test deep_research with custom sources."""
        mock_client = Mock()
        mock_client.search.return_value = {
            "answer": "Test answer",
            "citations": [],
            "backend_uuid": "uuid",
        }
        mock_get_client.return_value = mock_client

        result = deep_research(query="test", sources=["web", "scholar"])

        assert isinstance(result, dict)
        call_kwargs = mock_client.search.call_args[1]
        assert call_kwargs["sources"] == ["web", "scholar"]

    @patch("perplexity_deep_research.server.get_client")
    def test_deep_research_with_custom_language(self, mock_get_client):
        """Test deep_research with custom language."""
        mock_client = Mock()
        mock_client.search.return_value = {
            "answer": "Test answer",
            "citations": [],
            "backend_uuid": "uuid",
        }
        mock_get_client.return_value = mock_client

        result = deep_research(query="test", language="fr-FR")

        assert isinstance(result, dict)
        call_kwargs = mock_client.search.call_args[1]
        assert call_kwargs["language"] == "fr-FR"


class TestAskCallable:
    """Test ask tool is callable."""

    @patch("perplexity_deep_research.server.get_client")
    def test_ask_callable(self, mock_get_client):
        """Call ask, assert returns dict."""
        # Mock client
        mock_client = Mock()
        mock_client.search.return_value = {
            "answer": "Test answer",
            "citations": ["https://example.com"],
            "backend_uuid": "test-uuid-456",
        }
        mock_get_client.return_value = mock_client

        # Call tool
        result = ask(query="test query")

        # Verify result is dict
        assert isinstance(result, dict)
        assert "answer" in result or "error" in result

        # Verify client.search was called with correct mode
        mock_client.search.assert_called_once()
        call_kwargs = mock_client.search.call_args[1]
        assert call_kwargs["mode"] == "pro"
        assert call_kwargs["query"] == "test query"
        assert call_kwargs["follow_up"] is None

    @patch("perplexity_deep_research.server.get_client")
    def test_ask_with_custom_sources(self, mock_get_client):
        """Test ask with custom sources."""
        mock_client = Mock()
        mock_client.search.return_value = {
            "answer": "Test answer",
            "citations": [],
            "backend_uuid": "uuid",
        }
        mock_get_client.return_value = mock_client

        result = ask(query="test", sources=["web", "social"])

        assert isinstance(result, dict)
        call_kwargs = mock_client.search.call_args[1]
        assert call_kwargs["sources"] == ["web", "social"]


class TestSearchCallable:
    """Test search tool is callable."""

    @patch("perplexity_deep_research.server.get_client")
    def test_search_callable(self, mock_get_client):
        """Call search, assert returns dict."""
        # Mock client
        mock_client = Mock()
        mock_client.search.return_value = {
            "answer": "Test answer",
            "citations": ["https://example.com"],
            "backend_uuid": "test-uuid-789",
        }
        mock_get_client.return_value = mock_client

        # Call tool
        result = search(query="test query")

        # Verify result is dict
        assert isinstance(result, dict)
        assert "answer" in result or "error" in result

        # Verify client.search was called with correct mode
        mock_client.search.assert_called_once()
        call_kwargs = mock_client.search.call_args[1]
        assert call_kwargs["mode"] == "auto"
        assert call_kwargs["query"] == "test query"
        assert call_kwargs["follow_up"] is None

    @patch("perplexity_deep_research.server.get_client")
    def test_search_with_custom_language(self, mock_get_client):
        """Test search with custom language."""
        mock_client = Mock()
        mock_client.search.return_value = {
            "answer": "Test answer",
            "citations": [],
            "backend_uuid": "uuid",
        }
        mock_get_client.return_value = mock_client

        result = search(query="test", language="es-ES")

        assert isinstance(result, dict)
        call_kwargs = mock_client.search.call_args[1]
        assert call_kwargs["language"] == "es-ES"


class TestFollowUpCallable:
    """Test follow_up tool is callable."""

    @patch("perplexity_deep_research.server.get_client")
    def test_follow_up_callable(self, mock_get_client):
        """Call follow_up, assert returns dict."""
        # Mock client
        mock_client = Mock()
        mock_client.search.return_value = {
            "answer": "Follow-up answer",
            "citations": ["https://example.com"],
            "backend_uuid": "test-uuid-follow-up",
        }
        mock_get_client.return_value = mock_client

        # Call tool
        result = follow_up(query="follow-up question", backend_uuid="original-uuid-123")

        # Verify result is dict
        assert isinstance(result, dict)
        assert "answer" in result or "error" in result

        # Verify client.search was called with correct parameters
        mock_client.search.assert_called_once()
        call_kwargs = mock_client.search.call_args[1]
        assert call_kwargs["mode"] == "auto"
        assert call_kwargs["query"] == "follow-up question"
        assert call_kwargs["follow_up"] == "original-uuid-123"
        assert call_kwargs["sources"] == ["web"]
        assert call_kwargs["language"] == "en-US"

    @patch("perplexity_deep_research.server.get_client")
    def test_follow_up_payload_includes_uuid(self, mock_get_client):
        """Test follow_up passes backend_uuid correctly."""
        mock_client = Mock()
        mock_client.search.return_value = {
            "answer": "Answer",
            "citations": [],
            "backend_uuid": "new-uuid",
        }
        mock_get_client.return_value = mock_client

        backend_uuid = "test-backend-uuid-xyz"
        result = follow_up(query="test", backend_uuid=backend_uuid)

        # Verify the UUID was passed to search
        call_kwargs = mock_client.search.call_args[1]
        assert call_kwargs["follow_up"] == backend_uuid


class TestToolReturnsAnswerDict:
    """Test each tool returns dict with answer or error key."""

    @patch("perplexity_deep_research.server.get_client")
    def test_deep_research_returns_answer_dict(self, mock_get_client):
        """Test deep_research returns dict with answer key."""
        mock_client = Mock()
        mock_client.search.return_value = {
            "answer": "Research answer",
            "citations": ["https://example.com"],
            "backend_uuid": "uuid",
        }
        mock_get_client.return_value = mock_client

        result = deep_research(query="test")

        assert isinstance(result, dict)
        assert "answer" in result
        assert result["answer"] == "Research answer"

    @patch("perplexity_deep_research.server.get_client")
    def test_ask_returns_answer_dict(self, mock_get_client):
        """Test ask returns dict with answer key."""
        mock_client = Mock()
        mock_client.search.return_value = {
            "answer": "Pro answer",
            "citations": [],
            "backend_uuid": "uuid",
        }
        mock_get_client.return_value = mock_client

        result = ask(query="test")

        assert isinstance(result, dict)
        assert "answer" in result
        assert result["answer"] == "Pro answer"

    @patch("perplexity_deep_research.server.get_client")
    def test_search_returns_answer_dict(self, mock_get_client):
        """Test search returns dict with answer key."""
        mock_client = Mock()
        mock_client.search.return_value = {
            "answer": "Search answer",
            "citations": [],
            "backend_uuid": "uuid",
        }
        mock_get_client.return_value = mock_client

        result = search(query="test")

        assert isinstance(result, dict)
        assert "answer" in result
        assert result["answer"] == "Search answer"

    @patch("perplexity_deep_research.server.get_client")
    def test_follow_up_returns_answer_dict(self, mock_get_client):
        """Test follow_up returns dict with answer key."""
        mock_client = Mock()
        mock_client.search.return_value = {
            "answer": "Follow-up answer",
            "citations": [],
            "backend_uuid": "uuid",
        }
        mock_get_client.return_value = mock_client

        result = follow_up(query="test", backend_uuid="uuid")

        assert isinstance(result, dict)
        assert "answer" in result
        assert result["answer"] == "Follow-up answer"


class TestErrorHandling:
    """Test error handling in all tools."""

    @patch("perplexity_deep_research.server.get_client")
    def test_deep_research_error_handling(self, mock_get_client):
        """Test deep_research catches exceptions and returns error dict."""
        mock_client = Mock()
        mock_client.search.side_effect = Exception("Test error")
        mock_get_client.return_value = mock_client

        result = deep_research(query="test")

        assert isinstance(result, dict)
        assert "error" in result
        assert "Test error" in result["error"]

    @patch("perplexity_deep_research.server.get_client")
    def test_ask_error_handling(self, mock_get_client):
        """Test ask catches exceptions and returns error dict."""
        mock_client = Mock()
        mock_client.search.side_effect = Exception("Test error")
        mock_get_client.return_value = mock_client

        result = ask(query="test")

        assert isinstance(result, dict)
        assert "error" in result
        assert "Test error" in result["error"]

    @patch("perplexity_deep_research.server.get_client")
    def test_search_error_handling(self, mock_get_client):
        """Test search catches exceptions and returns error dict."""
        mock_client = Mock()
        mock_client.search.side_effect = Exception("Test error")
        mock_get_client.return_value = mock_client

        result = search(query="test")

        assert isinstance(result, dict)
        assert "error" in result
        assert "Test error" in result["error"]

    @patch("perplexity_deep_research.server.get_client")
    def test_follow_up_error_handling(self, mock_get_client):
        """Test follow_up catches exceptions and returns error dict."""
        mock_client = Mock()
        mock_client.search.side_effect = Exception("Test error")
        mock_get_client.return_value = mock_client

        result = follow_up(query="test", backend_uuid="uuid")

        assert isinstance(result, dict)
        assert "error" in result
        assert "Test error" in result["error"]

    @patch("perplexity_deep_research.server.get_client")
    def test_error_handling_with_different_exception_types(self, mock_get_client):
        """Test error handling with various exception types."""
        mock_client = Mock()

        # Test with ValueError
        mock_client.search.side_effect = ValueError("Value error")
        mock_get_client.return_value = mock_client
        result = deep_research(query="test")
        assert "error" in result
        assert "Value error" in result["error"]

        # Test with RuntimeError
        mock_client.search.side_effect = RuntimeError("Runtime error")
        result = ask(query="test")
        assert "error" in result
        assert "Runtime error" in result["error"]


class TestLazySingleton:
    """Test lazy singleton pattern for get_client."""

    @patch("perplexity_deep_research.server.PerplexityClient")
    def test_get_client_creates_client_once(self, mock_client_class):
        """Test get_client creates client only once."""
        # Reset the global _client
        import perplexity_deep_research.server as server_module

        server_module._client = None

        mock_instance = Mock()
        mock_client_class.return_value = mock_instance

        # First call should create client
        client1 = get_client()
        assert mock_client_class.call_count == 1

        # Second call should return same instance
        client2 = get_client()
        assert mock_client_class.call_count == 1

        # Both should be the same object
        assert client1 is client2

    @patch("perplexity_deep_research.server.PerplexityClient")
    def test_get_client_returns_perplexity_client(self, mock_client_class):
        """Test get_client returns PerplexityClient instance."""
        import perplexity_deep_research.server as server_module

        server_module._client = None

        mock_instance = Mock()
        mock_client_class.return_value = mock_instance

        client = get_client()

        assert client is mock_instance


class TestToolSignatures:
    """Test tool signatures match specification."""

    @patch("perplexity_deep_research.server.get_client")
    def test_deep_research_signature(self, mock_get_client):
        """Test deep_research has correct signature."""
        mock_client = Mock()
        mock_client.search.return_value = {
            "answer": "Test",
            "citations": [],
            "backend_uuid": "uuid",
        }
        mock_get_client.return_value = mock_client

        # Test with all parameters
        result = deep_research(
            query="test query", sources=["web", "scholar"], language="en-US"
        )

        assert isinstance(result, dict)
        call_kwargs = mock_client.search.call_args[1]
        assert call_kwargs["query"] == "test query"
        assert call_kwargs["sources"] == ["web", "scholar"]
        assert call_kwargs["language"] == "en-US"

    @patch("perplexity_deep_research.server.get_client")
    def test_ask_signature(self, mock_get_client):
        """Test ask has correct signature."""
        mock_client = Mock()
        mock_client.search.return_value = {
            "answer": "Test",
            "citations": [],
            "backend_uuid": "uuid",
        }
        mock_get_client.return_value = mock_client

        # Test with all parameters
        result = ask(query="test query", sources=["web"], language="fr-FR")

        assert isinstance(result, dict)
        call_kwargs = mock_client.search.call_args[1]
        assert call_kwargs["query"] == "test query"
        assert call_kwargs["sources"] == ["web"]
        assert call_kwargs["language"] == "fr-FR"

    @patch("perplexity_deep_research.server.get_client")
    def test_search_signature(self, mock_get_client):
        """Test search has correct signature."""
        mock_client = Mock()
        mock_client.search.return_value = {
            "answer": "Test",
            "citations": [],
            "backend_uuid": "uuid",
        }
        mock_get_client.return_value = mock_client

        # Test with all parameters
        result = search(query="test query", sources=["web"], language="en-US")

        assert isinstance(result, dict)
        call_kwargs = mock_client.search.call_args[1]
        assert call_kwargs["query"] == "test query"
        assert call_kwargs["sources"] == ["web"]
        assert call_kwargs["language"] == "en-US"

    @patch("perplexity_deep_research.server.get_client")
    def test_follow_up_signature(self, mock_get_client):
        """Test follow_up has correct signature."""
        mock_client = Mock()
        mock_client.search.return_value = {
            "answer": "Test",
            "citations": [],
            "backend_uuid": "uuid",
        }
        mock_get_client.return_value = mock_client

        # Test with required parameters
        result = follow_up(query="follow-up", backend_uuid="test-uuid")

        assert isinstance(result, dict)
        call_kwargs = mock_client.search.call_args[1]
        assert call_kwargs["query"] == "follow-up"
        assert call_kwargs["follow_up"] == "test-uuid"
