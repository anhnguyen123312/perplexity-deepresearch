"""MCP server for Perplexity Deep Research + Grok chat tools."""

from mcp.server.fastmcp import FastMCP

from . import profile_config
from .perplexity.client import PerplexityClient
from .gemini.client import GeminiClient
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
_gemini: GeminiClient | None = None


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


def get_gemini_client() -> GeminiClient:
    """Get or create GeminiClient singleton."""
    global _gemini
    if _gemini is None:
        _gemini = GeminiClient()
    return _gemini


@mcp.tool()
def perplexity_deep_research(
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
def perplexity_ask(query: str, sources: list[str] = ["web"], language: str = "en-US") -> dict:
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
def perplexity_search(query: str, sources: list[str] = ["web"], language: str = "en-US") -> dict:
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
def perplexity_follow_up(query: str, backend_uuid: str) -> dict:
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


def _get_gemini_config() -> dict:
    """Load Gemini settings from the unified profile_config store.

    Single source of truth: configure via ``deep-research-onboard`` CLI.
    Returns ``{authuser, chrome_profile, language, model}`` with built-in
    defaults filled in for missing fields.
    """
    saved = profile_config.get_provider_settings(profile_config.PROVIDER_GEMINI)
    return {
        "authuser": saved.get("authuser", 0),
        "chrome_profile": saved.get("chrome_profile"),
        "language": saved.get("language", "en"),
        "model": saved.get("model"),
    }


@mcp.tool()
def gemini_deep_research(
    query: str,
    poll_interval: float = 30.0,
    timeout: float = 1800.0,
) -> dict:
    """Run a full Deep Research on gemini.google.com and return the report.

    One-shot end-to-end: this tool internally drives Gemini's 3-stage DR
    flow (plan → confirm "Start research" → poll ``READ_CHAT``) and blocks
    until the final markdown report lands (typically 5-15 min) or ``timeout``
    elapses (default 30 min).

    Account / profile / language / model are **always** read from the unified
    config (``profile_config``). Run ``deep-research-onboard`` to configure
    them; this tool intentionally exposes no override args so there is one
    source of truth.

    Args:
        query: The research question (give detailed context for best plans).
        poll_interval: Seconds between poll attempts during stage 3 (default
            30s — matches the Gemini web UI cadence).
        timeout: Hard cap on the whole run in seconds (default 1800 = 30 min).

    Returns:
        ``{"ok": True, "done": bool, "text": <markdown report>, "title",
        "conversation_id", "plan_title", "plan_steps", "elapsed_secs",
        "stage_secs", "polls", "timed_out", ...}`` on success;
        ``{"ok": False, "error": str, "stage": "plan"|"confirm", ...}`` if a
        stage fails; ``{"error": str}`` on transport-level failure.
    """
    cfg = _get_gemini_config()
    try:
        return get_gemini_client().full_deep_research(
            query=query,
            poll_interval=poll_interval,
            timeout=timeout,
            **cfg,
        )
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


@mcp.tool()
def gemini_refresh_csrf() -> dict:
    """Force-refresh the cached SNlM0e CSRF token for the configured account.

    ``SNlM0e`` is per-Google-account (different value at ``/u/0/`` vs
    ``/u/6/``) and is harvested from the Gemini homepage HTML. Cookies must
    be valid; if they have rotated, this call also pulls a fresh cookie set
    from Chrome. Call after persistent 401/403 errors or after a long idle
    period.

    Account / profile are always read from config (``profile_config``).

    Returns ``{"ok": True, "chrome_profile", "authuser", "snlm0e_prefix",
    "bl", "email"}`` or ``{"error": str}``.
    """
    cfg = _get_gemini_config()
    try:
        return get_gemini_client().refresh_csrf(
            authuser=cfg["authuser"],
            chrome_profile=cfg["chrome_profile"],
        )
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
