"""
Browser cookie extraction and management for Perplexity API authentication.

Provides functions to extract cookies from Chrome, normalize them to a canonical
shape, persist them to disk, and retrieve them with caching and expiry detection.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from sqlite3 import OperationalError

from pycookiecheat import BrowserType, chrome_cookies

from .browser_control import ensure_chrome_accessible, relaunch_chrome
from .config import (
    COOKIE_MAX_AGE,
    CSRF_TOKEN_VARIANTS,
    SESSION_TOKEN_VARIANTS,
    get_cookies_file_path,
    is_database_locked_error,
)
from .exceptions import CookieExtractionError


def get_chrome_cookie_path(profile: str = None) -> str:
    """
    Resolve Chrome cookie database path on macOS.

    Resolves the absolute path to Chrome's Cookies SQLite database file.
    Uses CHROME_PROFILE env var or parameter (default: "Default").

    Args:
        profile: Chrome profile name (e.g., "Default", "Profile 1")

    Returns:
        str: Absolute path to Chrome Cookies database file

    Raises:
        CookieExtractionError: If Chrome cookie file not found
    """
    base = Path.home() / "Library/Application Support/Google/Chrome"
    profile = os.environ.get("CHROME_PROFILE", profile or "Default")
    cookie_path = base / profile / "Cookies"
    if not cookie_path.exists():
        raise CookieExtractionError(f"Chrome cookie file not found: {cookie_path}")
    return str(cookie_path.resolve())  # Absolute path string


def normalize_cookies(raw_cookies: dict) -> dict:
    """
    Convert browser cookie names to canonical internal shape.

    Matches cookie variants (e.g., __Secure-, plain, __Host- prefixes) and
    preserves the original cookie name for HTTP reconstruction.

    Args:
        raw_cookies: Raw cookie dict from pycookiecheat

    Returns:
        dict: Canonical shape with keys:
            - "session_token": The session token value
            - "session_token_name": Original cookie name (for HTTP)
            - "csrf_token": CSRF token value (optional)
            - "csrf_token_name": Original CSRF cookie name (optional)

    Raises:
        CookieExtractionError: If no session token variant found
    """
    result = {}

    # Find session token (required)
    for variant in SESSION_TOKEN_VARIANTS:
        if variant in raw_cookies:
            result["session_token"] = raw_cookies[variant]
            result["session_token_name"] = variant  # Preserve for HTTP!
            break

    if "session_token" not in result:
        raise CookieExtractionError("No session token found in Chrome cookies")

    # Find CSRF token (optional)
    for variant in CSRF_TOKEN_VARIANTS:
        if variant in raw_cookies:
            result["csrf_token"] = raw_cookies[variant]
            result["csrf_token_name"] = variant
            break

    return result


def to_http_cookies(normalized: dict) -> dict:
    """
    Convert canonical shape back to HTTP cookie dict for curl_cffi.

    Uses the preserved original cookie names to reconstruct the HTTP format.

    Args:
        normalized: Canonical cookie dict from normalize_cookies()

    Returns:
        dict: HTTP cookie dict with original names as keys
            e.g., {"__Secure-next-auth.session-token": "eyJ...", ...}
    """
    http_cookies = {}
    http_cookies[normalized["session_token_name"]] = normalized["session_token"]
    if "csrf_token" in normalized and "csrf_token_name" in normalized:
        http_cookies[normalized["csrf_token_name"]] = normalized["csrf_token"]
    return http_cookies


def extract_cookies_raw() -> dict:
    """
    Extract cookies from Chrome using pycookiecheat.

    Low-level function that directly calls pycookiecheat.chrome_cookies().
    May raise sqlite3.OperationalError if Chrome is locking the database.

    Returns:
        dict: Raw cookie dict from pycookiecheat

    Raises:
        sqlite3.OperationalError: If Chrome is blocking database access
        Other exceptions from pycookiecheat
    """
    return chrome_cookies(
        url="https://www.perplexity.ai",
        browser=BrowserType.CHROME,
        cookie_file=get_chrome_cookie_path(),
    )


def extract_cookies_with_relaunch() -> dict:
    """
    Extract cookies with guaranteed Chrome relaunch on quit.

    Implements TRY-FIRST flow: attempts extraction without prompting first.
    Only handles Chrome if database is actually locked.

    Flow:
    1. Try extraction first (works if Chrome not locking)
    2. If locked: prompt user and quit Chrome if approved
    3. Extract again with relaunch guarantee

    Returns:
        dict: Normalized cookie dict

    Raises:
        CookieExtractionError: If extraction fails or Chrome can't be accessed
    """
    # Step 1: Try extraction first (works if Chrome not locking)
    try:
        raw = extract_cookies_raw()
        return normalize_cookies(raw)  # Success! No Chrome prompt needed
    except Exception as e:
        if not is_database_locked_error(e):
            raise  # Not a lock error, propagate

    # Step 2: Locked - need to handle Chrome
    result = ensure_chrome_accessible()
    if not result.accessible:
        raise CookieExtractionError(
            "Chrome is blocking cookie access and could not be closed. "
            "Please close Chrome manually and retry, or set PERPLEXITY_ALLOW_CHROME_QUIT=1."
        )

    # Step 3: Chrome handled, extract with relaunch guarantee
    try:
        raw = extract_cookies_raw()
        return normalize_cookies(raw)
    finally:
        if result.was_quit:
            relaunch_chrome()


def save_cookies(cookies: dict, path: Path | None = None) -> None:
    """
    Save cookies to JSON file.

    Creates parent directory if needed (mkdir -p behavior).

    Args:
        cookies: Canonical cookie dict to save
        path: Path to cookies file (default: from get_cookies_file_path())
    """
    path = path or get_cookies_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)  # mkdir -p

    data = {"cookies": cookies, "extracted_at": datetime.now().isoformat()}
    path.write_text(json.dumps(data, indent=2))


def load_cookies(path: Path | None = None) -> dict | None:
    """
    Load cookies from JSON file.

    Returns None if file missing or cookies have expired (age > COOKIE_MAX_AGE).

    Args:
        path: Path to cookies file (default: from get_cookies_file_path())

    Returns:
        dict: Canonical cookie dict if valid, None if missing or expired
    """
    path = path or get_cookies_file_path()

    if not path.exists():
        return None

    data = json.loads(path.read_text())
    extracted_at = datetime.fromisoformat(data["extracted_at"])
    age = (datetime.now() - extracted_at).total_seconds()

    if age > COOKIE_MAX_AGE:
        return None

    return data["cookies"]


def get_cookies() -> dict:
    """
    Get cookies (cached or fresh).

    Main public API entry point for cookie acquisition.
    Returns cached cookies if valid, otherwise extracts fresh cookies
    and caches them.

    Returns:
        dict: Canonical cookie dict with session_token and optional csrf_token

    Raises:
        CookieExtractionError: If cookie extraction fails
    """
    cached = load_cookies()
    if cached:
        return cached

    fresh = extract_cookies_with_relaunch()
    save_cookies(fresh)
    return fresh
