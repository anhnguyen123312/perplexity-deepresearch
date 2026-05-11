"""MCP server for Perplexity Deep Research + Grok chat tools."""

from mcp.server.fastmcp import FastMCP

from .client import PerplexityClient
from .grok.client import GrokClient
from .grok.config import (
    MODE_AUTO as GROK_MODE_AUTO,
    MODE_EXPERT as GROK_MODE_EXPERT,
    MODE_FAST as GROK_MODE_FAST,
    MODE_GROK_4_3_BETA,
    MODE_HEAVY as GROK_MODE_HEAVY,
)
from .grok.statsig import capture_statsig_id_via_chrome

# Initialize FastMCP server
mcp = FastMCP("Perplexity Deep Research")

# Lazy singletons
_client: PerplexityClient | None = None
_grok: GrokClient | None = None


def get_client() -> PerplexityClient:
    """Get or create PerplexityClient singleton."""
    global _client
    if _client is None:
        _client = PerplexityClient()
    return _client


def get_grok_client() -> GrokClient:
    """Get or create GrokClient singleton."""
    global _grok
    if _grok is None:
        _grok = GrokClient()
    return _grok


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
        sources: List of sources to search (default: ["web"]). Valid values
            include built-in sources ("web", "scholar", "social") and any
            OAuth connector source_id you have linked to your perplexity.ai
            account (e.g. "github_mcp_direct", "notion_mcp", "slack_direct",
            "google_drive"). See ``config.SUPPORTED_SOURCES`` for the full
            list captured on 2026-05-11.
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
        sources: List of sources to search (default: ["web"]). Valid values
            include built-in sources ("web", "scholar", "social") and any
            OAuth connector source_id you have linked to your perplexity.ai
            account (e.g. "github_mcp_direct", "notion_mcp", "slack_direct",
            "google_drive"). See ``config.SUPPORTED_SOURCES`` for the full
            list captured on 2026-05-11.
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
        sources: List of sources to search (default: ["web"]). Valid values
            include built-in sources ("web", "scholar", "social") and any
            OAuth connector source_id you have linked to your perplexity.ai
            account (e.g. "github_mcp_direct", "notion_mcp", "slack_direct",
            "google_drive"). See ``config.SUPPORTED_SOURCES`` for the full
            list captured on 2026-05-11.
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
        sources: List of sources to search (default: ["web"]). Valid values
            include built-in sources ("web", "scholar", "social") and any
            OAuth connector source_id you have linked to your perplexity.ai
            account (e.g. "github_mcp_direct", "notion_mcp", "slack_direct",
            "google_drive"). See ``config.SUPPORTED_SOURCES`` for the full
            list captured on 2026-05-11.
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


@mcp.tool()
def grok_search(
    query: str,
    mode: str = MODE_GROK_4_3_BETA,
    include_thinking: bool = False,
) -> dict:
    """Send `query` to grok.com using the requested mode and return the answer.

    Args:
        query: The user prompt.
        mode: One of "auto", "fast", "expert", "heavy",
            or "grok-420-computer-use-sa" (Grok 4.3 beta — default).
        include_thinking: If False (default), strip chain-of-thought and tool-
            usage trace tokens (``isThinking == True``) from the answer.
            Set True to see the full reasoning chain (debugging).

    Returns:
        dict with `answer`, `conversation_id`, `response_id`, `mode`,
        `elapsed_secs`, `stream_lines`. On failure: `{"error": ...}`.
    """
    try:
        return get_grok_client().search(
            query=query, mode=mode, include_thinking=include_thinking
        )
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


@mcp.tool()
def grok_4_3(query: str, include_thinking: bool = False) -> dict:
    """Shortcut: ask Grok 4.3 (beta) directly.

    Equivalent to ``grok_search(query, mode="grok-420-computer-use-sa")``.
    Thinking trace is stripped by default; set ``include_thinking=True`` to
    keep it.
    """
    try:
        return get_grok_client().search(
            query=query,
            mode=MODE_GROK_4_3_BETA,
            include_thinking=include_thinking,
        )
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


@mcp.tool()
def grok_expert(query: str, include_thinking: bool = False) -> dict:
    """Shortcut: ask Grok Expert mode (UI: "Chuyên gia / Suy nghĩ sâu").

    Expert thinks longer before answering. Equivalent to
    ``grok_search(query, mode="expert")``. Thinking trace is stripped by
    default; set ``include_thinking=True`` to keep it.
    """
    try:
        return get_grok_client().search(
            query=query,
            mode=GROK_MODE_EXPERT,
            include_thinking=include_thinking,
        )
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


@mcp.tool()
def grok_refresh_statsig() -> dict:
    """Force-refresh the cached x-statsig-id by opening Chrome via Playwright.

    The cached id is reused indefinitely; only call this when grok_search
    returns a 403 anti-bot error or after a long idle period.
    """
    try:
        sid = capture_statsig_id_via_chrome()
        return {"status": "ok", "statsig_id_prefix": sid[:24] + "…"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


@mcp.tool()
def grok_modes() -> dict:
    """List the supported grok.com mode IDs and their UI titles."""
    return {
        "modes": {
            GROK_MODE_AUTO: "Auto (Chooses Fast or Expert)",
            GROK_MODE_FAST: "Fast (Quick responses)",
            GROK_MODE_EXPERT: "Expert / Chuyên gia (Suy nghĩ sâu — thinks hard)",
            GROK_MODE_HEAVY: "Heavy (requires SuperGrok Heavy tier)",
            MODE_GROK_4_3_BETA: "Grok 4.3 (beta — early access)",
        },
        "default": MODE_GROK_4_3_BETA,
    }


def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
