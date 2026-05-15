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


def _resolve_gemini_args(
    authuser: int | None,
    chrome_profile: str | None,
    language: str | None,
    model: str | None,
) -> dict:
    """Merge explicit MCP-tool args with saved defaults.

    Resolution order per field: explicit arg → saved setting → built-in default.
    Returns a flat dict with ``authuser``, ``chrome_profile``, ``language``,
    ``model`` keys ready to splat into the client call.
    """
    saved = profile_config.get_provider_settings(profile_config.PROVIDER_GEMINI)
    return {
        "authuser": authuser if authuser is not None else saved.get("authuser", 0),
        "chrome_profile": chrome_profile or saved.get("chrome_profile"),
        "language": language or saved.get("language", "en"),
        "model": model or saved.get("model"),
    }


def _persist_gemini_args(
    result: dict, *, authuser, chrome_profile, language, model
) -> None:
    """Save the args from a successful call so the next call can omit them."""
    if not result.get("ok"):
        return
    profile_config.set_provider_settings(
        profile_config.PROVIDER_GEMINI,
        {
            "authuser": authuser,
            "chrome_profile": chrome_profile,
            "language": language,
            "model": model,
        },
    )


@mcp.tool()
def gemini_deep_research(
    query: str,
    authuser: int | None = None,
    chrome_profile: str | None = None,
    language: str | None = None,
    model: str | None = None,
) -> dict:
    """Submit a Deep Research request to gemini.google.com (Google One AI Premium).

    Stage-1 of Gemini's DR flow: returns the **research plan** Gemini drafts
    before it commits to the long-running research run (5-15 min). Call
    ``gemini_start_research`` afterwards with the returned ``conversation_id``
    to trigger the actual investigation.

    All optional args fall back to values saved via ``gemini_set_defaults``;
    after a successful call the args used are persisted as the new defaults.

    Args:
        query: The research question (give detailed context for best plans).
        authuser: Google account index inside the Chrome profile (``/u/N/``).
            ``None`` → use saved default or ``0``.
        chrome_profile: Chrome OS profile name. ``None`` → use saved default
            or auto-pick first signed-in profile.
        language: Locale code (``en``, ``vi``, …). ``None`` → saved default
            or ``en``.
        model: Optional model override. ``"pro"`` selects Gemini 3.1 Pro
            (verified live 2026-05-15). ``None`` → saved default (default
            account model = 2.5 Flash).

    Returns:
        ``{"ok": True, "conversation_id", "response_id", "title",
        "plan_title", "plan_steps", "text", ...}`` on success;
        ``{"error": str}`` on failure.
    """
    args = _resolve_gemini_args(authuser, chrome_profile, language, model)
    try:
        result = get_gemini_client().deep_research(query=query, **args)
        _persist_gemini_args(result, **args)
        return result
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


@mcp.tool()
def gemini_start_research(
    conversation_id: str,
    response_id: str,
    choice_id: str,
    authuser: int | None = None,
    chrome_profile: str | None = None,
    confirm_prompt: str = "Start research",
    language: str | None = None,
    model: str | None = None,
    wait: bool = False,
    poll_interval: float = 30.0,
    timeout: float = 1800.0,
) -> dict:
    """Stage-2 of Gemini Deep Research — confirm a plan returned by
    ``gemini_deep_research`` and trigger the long run (5-15 min).

    Pass the ``conversation_id``, ``response_id``, and one of the
    ``candidate_ids`` (the ``choice_id``) from the plan response so the
    confirmation lands inside the same Gemini conversation.

    By default this returns as soon as the confirmation request is
    acknowledged (~30 s). Pass ``wait=True`` to additionally poll
    ``batchexecute(READ_CHAT)`` every ``poll_interval`` seconds (up to
    ``timeout`` seconds) and return the finished report under
    ``poll.text``.
    """
    args = _resolve_gemini_args(authuser, chrome_profile, language, model)
    try:
        result = get_gemini_client().start_research(
            conversation_id=conversation_id,
            response_id=response_id,
            choice_id=choice_id,
            confirm_prompt=confirm_prompt,
            wait=wait,
            poll_interval=poll_interval,
            timeout=timeout,
            **args,
        )
        _persist_gemini_args(result, **args)
        return result
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


@mcp.tool()
def gemini_poll_research(
    conversation_id: str,
    authuser: int | None = None,
    chrome_profile: str | None = None,
    language: str | None = None,
    poll_interval: float = 30.0,
    timeout: float = 1800.0,
) -> dict:
    """Stage-3 of Gemini Deep Research — poll an already-running research
    conversation until the report finalises.

    After ``gemini_start_research`` triggers the long run (5-15 min), call
    this with the returned ``conversation_id`` to block until the report is
    ready and receive the final markdown in ``text``.

    Returns ``{"ok", "done", "conversation_id", "rcid", "text",
    "elapsed_secs", "polls", "reason", "timed_out"}``.
    """
    args = _resolve_gemini_args(authuser, chrome_profile, language, None)
    try:
        return get_gemini_client().poll_research(
            conversation_id=conversation_id,
            authuser=args["authuser"],
            chrome_profile=args["chrome_profile"],
            language=args["language"],
            poll_interval=poll_interval,
            timeout=timeout,
        )
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


@mcp.tool()
def gemini_refresh_csrf(
    authuser: int | None = None,
    chrome_profile: str | None = None,
) -> dict:
    """Force-refresh the cached SNlM0e CSRF token for one Google account.

    ``SNlM0e`` is per-Google-account (different value at ``/u/0/`` vs
    ``/u/6/``) and is harvested from the Gemini homepage HTML. Cookies must
    be valid; if they have rotated, this call also pulls a fresh cookie set
    from Chrome. Call after persistent 401/403 errors or after a long idle
    period.

    Returns ``{"ok": True, "chrome_profile", "authuser", "snlm0e_prefix",
    "bl", "email"}`` or ``{"error": str}``.
    """
    args = _resolve_gemini_args(authuser, chrome_profile, None, None)
    try:
        return get_gemini_client().refresh_csrf(
            authuser=args["authuser"],
            chrome_profile=args["chrome_profile"],
        )
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


@mcp.tool()
def gemini_set_defaults(
    authuser: int | None = None,
    chrome_profile: str | None = None,
    language: str | None = None,
    model: str | None = None,
) -> dict:
    """Persist default args for the gemini tools.

    Saved values are auto-applied to ``gemini_deep_research`` /
    ``gemini_start_research`` / ``gemini_refresh_csrf`` whenever the matching
    tool arg is omitted. Pass ``""`` (empty string) for a string field to
    clear that single key, or call ``gemini_clear_defaults`` to wipe all.

    Defaults are also auto-updated on every successful gemini DR call, so the
    normal workflow is: run the tool once with explicit ``authuser``/
    ``chrome_profile``/``model``, and subsequent calls inherit them.
    """
    updates: dict = {}
    if authuser is not None:
        updates["authuser"] = authuser
    if chrome_profile is not None:
        updates["chrome_profile"] = chrome_profile or None
    if language is not None:
        updates["language"] = language or None
    if model is not None:
        updates["model"] = model or None
    saved = profile_config.set_provider_settings(
        profile_config.PROVIDER_GEMINI, updates
    )
    return {"ok": True, "settings": saved}


@mcp.tool()
def gemini_get_defaults() -> dict:
    """Return the saved default args for the gemini tools (may be empty)."""
    return {
        "ok": True,
        "settings": profile_config.get_provider_settings(
            profile_config.PROVIDER_GEMINI
        ),
    }


@mcp.tool()
def gemini_clear_defaults() -> dict:
    """Wipe all saved default args for the gemini tools."""
    profile_config.clear_provider_settings(profile_config.PROVIDER_GEMINI)
    return {"ok": True, "settings": {}}


def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
