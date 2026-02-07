"""MCP server for Perplexity Deep Research with 5 tools."""

from mcp.server.fastmcp import FastMCP

from .client import PerplexityClient

# Initialize FastMCP server
mcp = FastMCP("Perplexity Deep Research")

# Lazy singleton for client
_client: PerplexityClient | None = None


def get_client() -> PerplexityClient:
    """Get or create PerplexityClient singleton."""
    global _client
    if _client is None:
        _client = PerplexityClient()
    return _client


@mcp.tool()
def deep_research(
    query: str, sources: list[str] = ["web"], language: str = "en-US"
) -> dict:
    """
    Perform exhaustive multi-step research on a query.

    Uses Perplexity's deep research mode (pplx_alpha model) for comprehensive
    analysis with multiple search steps and detailed citations.

    Args:
        query: The research question
        sources: List of sources to search (default: ["web"])
        language: Language code (default: "en-US")

    Returns:
        dict: Response with 'answer', 'citations', 'backend_uuid' keys
              OR {'error': str} on failure
    """
    try:
        client = get_client()
        return client.search(
            query=query,
            mode="deep research",
            sources=sources,
            language=language,
            follow_up=None,
        )
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def ask(query: str, sources: list[str] = ["web"], language: str = "en-US") -> dict:
    """
    Ask a question using Perplexity Pro mode.

    Uses pplx_pro model for high-quality answers with citations.

    Args:
        query: The question to ask
        sources: List of sources to search (default: ["web"])
        language: Language code (default: "en-US")

    Returns:
        dict: Response with 'answer', 'citations', 'backend_uuid' keys
              OR {'error': str} on failure
    """
    try:
        client = get_client()
        return client.search(
            query=query, mode="pro", sources=sources, language=language, follow_up=None
        )
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def reason(query: str, sources: list[str] = ["web"], language: str = "en-US") -> dict:
    """
    Reasoning-focused analysis for questions requiring step-by-step thinking.

    Uses Perplexity's reasoning mode for comparisons, trade-off analysis,
    and decisions that benefit from systematic evaluation. Provide your specific
    situation and constraints for best results.

    Args:
        query: Analytical question with context and constraints
        sources: List of sources to search (default: ["web"])
        language: Language code (default: "en-US")

    Returns:
        dict: Response with 'answer', 'citations', 'backend_uuid' keys
              OR {'error': str} on failure
    """
    try:
        client = get_client()
        return client.search(
            query=query,
            mode="reasoning",
            sources=sources,
            language=language,
            follow_up=None,
        )
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def search(query: str, sources: list[str] = ["web"], language: str = "en-US") -> dict:
    """
    Perform a quick basic search.

    Uses turbo model for fast responses.

    Args:
        query: The search query
        sources: List of sources to search (default: ["web"])
        language: Language code (default: "en-US")

    Returns:
        dict: Response with 'answer', 'citations', 'backend_uuid' keys
              OR {'error': str} on failure
    """
    try:
        client = get_client()
        return client.search(
            query=query, mode="auto", sources=sources, language=language, follow_up=None
        )
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def follow_up(query: str, backend_uuid: str) -> dict:
    """
    Continue a previous conversation with a follow-up question.

    Uses the backend_uuid from a previous query to maintain conversation context.
    Always uses turbo model (auto mode) for follow-ups.

    Args:
        query: The follow-up question
        backend_uuid: UUID from previous query's response

    Returns:
        dict: Response with 'answer', 'citations', 'backend_uuid' keys
              OR {'error': str} on failure
    """
    try:
        client = get_client()
        return client.search(
            query=query,
            mode="auto",
            sources=["web"],
            language="en-US",
            follow_up=backend_uuid,
        )
    except Exception as e:
        return {"error": str(e)}


def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
