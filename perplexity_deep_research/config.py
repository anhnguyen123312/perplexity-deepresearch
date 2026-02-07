"""
Configuration constants for Perplexity Deep Research MCP Server.

This module contains all configurable constants used throughout the library.
Modify these values to customize behavior without changing core code.
"""

import os
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

# HTTP Headers Template (exactly 20 headers)
DEFAULT_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",  # noqa: E501
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "max-age=0",
    "dnt": "1",
    "priority": "u=0, i",
    "sec-ch-ua": '"Not;A=Brand";v="24", "Chromium";v="128"',
    "sec-ch-ua-arch": '"x86"',
    "sec-ch-ua-bitness": '"64"',
    "sec-ch-ua-full-version": '"128.0.6613.120"',
    "sec-ch-ua-full-version-list": '"Not;A=Brand";v="24.0.0.0", "Chromium";v="128.0.6613.120"',  # noqa: E501
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-model": '""',
    "sec-ch-ua-platform": '"Windows"',
    "sec-ch-ua-platform-version": '"19.0.0"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",  # noqa: E501
}

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
    2. XDG_DATA_HOME/perplexity-deep-research/cookies.json (Linux/macOS standard)
    3. ~/.local/share/perplexity-deep-research/cookies.json (fallback)

    This ensures consistent location regardless of working directory.
    Critical for test isolation - pytest fixtures set env vars before calls.

    Returns:
        Path: Resolved path to cookies.json file
    """
    # 1. Explicit env var override
    if env_path := os.environ.get("PERPLEXITY_COOKIES_FILE"):
        return Path(env_path)

    # 2. XDG standard location (works for MCP stdio mode)
    xdg_data = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))
    return Path(xdg_data) / "perplexity-deep-research" / "cookies.json"


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
