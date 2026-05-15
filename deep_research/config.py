"""
Configuration constants for Perplexity Deep Research MCP Server.

This module contains all configurable constants used throughout the library.
Modify these values to customize behavior without changing core code.
"""

import os
import sys
from pathlib import Path
from sqlite3 import OperationalError


# API Configuration
API_BASE_URL = "https://www.perplexity.ai"
API_VERSION = "2.18"

# Endpoints
ENDPOINT_AUTH_SESSION = f"{API_BASE_URL}/api/auth/session"
ENDPOINT_SSE_ASK = f"{API_BASE_URL}/rest/sse/perplexity_ask"

# Timeouts (configurable via environment variables)
REQUEST_TIMEOUT = int(os.environ.get("PERPLEXITY_TIMEOUT", "900"))  # 15 min default
COOKIE_MAX_AGE = 86400  # 24 hours

# Retry configuration
MAX_RETRIES = int(os.environ.get("PERPLEXITY_MAX_RETRIES", "2"))

# HTTP Headers Template (browser-like baseline, used for navigation/auth)
DEFAULT_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",  # noqa: E501
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "max-age=0",
    "dnt": "1",
    "priority": "u=0, i",
    "sec-ch-ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",  # noqa: E501
}

# Headers attached to the SSE ask request (matches what perplexity.ai web app sends)
SSE_REQUEST_HEADERS = {
    "accept": "text/event-stream",
    "content-type": "application/json",
    "x-perplexity-request-endpoint": ENDPOINT_SSE_ASK,
    "x-perplexity-request-reason": "ask-query-state-provider",
    "x-perplexity-request-try-number": "1",
    "referer": f"{API_BASE_URL}/",
}

# Block use cases declared as supported by the perplexity.ai web client.
# Captured from a live request on 2026-05-11; controls what answer block
# types the server may return.
SUPPORTED_BLOCK_USE_CASES = [
    "answer_modes",
    "media_items",
    "knowledge_cards",
    "inline_entity_cards",
    "place_widgets",
    "finance_widgets",
    "prediction_market_widgets",
    "sports_widgets",
    "flight_status_widgets",
    "news_widgets",
    "shopping_widgets",
    "jobs_widgets",
    "search_result_widgets",
    "inline_images",
    "inline_assets",
    "placeholder_cards",
    "diff_blocks",
    "inline_knowledge_cards",
    "entity_group_v2",
    "refinement_filters",
    "canvas_mode",
    "maps_preview",
    "answer_tabs",
    "price_comparison_widgets",
    "preserve_latex",
    "generic_onboarding_widgets",
    "in_context_suggestions",
    "pending_followups",
    "inline_claims",
    "unified_assets",
    "workflow_steps",
    "background_agents",
]

SUPPORTED_FEATURES = ["browser_agent_permission_banner_v1.1"]

# Sources / connectors recognised by the perplexity_ask `params.sources[]` field.
# Captured from a live `/rest/user/settings` response on 2026-05-11. The MCP
# does not enforce this list at request time (Perplexity will reject unknown
# values itself); it is exposed so callers know what to pass.
BUILTIN_SOURCES = ["web", "scholar", "social"]

OAUTH_CONNECTOR_SOURCES = [
    "google_drive",
    "gcal",
    "onedrive",
    "sharepoint",
    "dropbox",
    "box",
    "edgar",
    "outlook",
    "linear_alt",
    "notion_mcp",
    "github_mcp_direct",
    "asana_mcp_merge",
    "slack_direct",
    "jira_mcp_merge",
    "confluence_mcp_merge",
    "microsoft_teams_mcp_merge",
    "apple_healthkit",
    "plaid",
]

PREMIUM_DATA_SOURCES = [
    "ahrefs_premium_data",
    "apollo_premium_data",
    "bmj",
    "cbinsights_mcp_cashmere",
    "ebsco",
    "midpage",
    "nejm",
    "pitchbook_mcp_cashmere",
    "semrush_premium_data",
    "similarweb_premium_data",
    "statista_mcp_cashmere",
    "visualdx",
    "wiley_mcp_cashmere",
]

SUPPORTED_SOURCES = BUILTIN_SOURCES + OAUTH_CONNECTOR_SOURCES + PREMIUM_DATA_SOURCES

# Cookie Token Variants (in order of preference)
SESSION_TOKEN_VARIANTS = [
    "__Secure-next-auth.session-token",
    "next-auth.session-token",
    "__Host-next-auth.session-token",
]

CSRF_TOKEN_VARIANTS = [
    "__Secure-next-auth.csrf-token",
    "next-auth.csrf-token",
    "__Host-next-auth.csrf-token",
]

# SQLite Lock Error Patterns
LOCK_ERROR_PATTERNS = [
    "database is locked",
    "database is busy",
    "unable to open database",
    "disk i/o error",
]


def get_cookies_file_path() -> Path:
    """
    Resolve cookies.json path AT CALL TIME (not import time).

    Resolution order:
    1. PERPLEXITY_COOKIES_FILE env var (absolute path)
    2. Platform-appropriate data directory:
       - Windows: %LOCALAPPDATA%/perplexity-deep-research/cookies.json
       - macOS/Linux: XDG_DATA_HOME or ~/.local/share

    This ensures consistent location regardless of working directory.
    Critical for test isolation - pytest fixtures set env vars before calls.

    Returns:
        Path: Resolved path to cookies.json file
    """
    # 1. Explicit env var override
    if env_path := os.environ.get("PERPLEXITY_COOKIES_FILE"):
        return Path(env_path)

    # 2. Platform-appropriate data directory
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
    else:
        base = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))
    return Path(base) / "perplexity-deep-research" / "cookies.json"


def is_database_locked_error(error: Exception) -> bool:
    """
    Check if an exception indicates Chrome is blocking cookie DB access.

    Detects various SQLite lock-related error messages that occur when
    Chrome is running with WAL (Write-Ahead Logging) mode enabled.

    Args:
        error: Exception to check

    Returns:
        bool: True if error indicates database lock, False otherwise
    """
    if not isinstance(error, OperationalError):
        return False

    error_msg = str(error).lower()
    return any(pattern in error_msg for pattern in LOCK_ERROR_PATTERNS)
