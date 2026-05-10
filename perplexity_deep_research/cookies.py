"""
Browser cookie extraction and management for Perplexity API authentication.

Provides functions to extract cookies from Chrome, normalize them to a canonical
shape, persist them to disk, and retrieve them with caching and expiry detection.
"""

import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from sqlite3 import OperationalError

from pycookiecheat import BrowserType, chrome_cookies

from .browser_control import (
    check_full_disk_access,
    ensure_chrome_accessible,
    prompt_keychain_password,
    relaunch_chrome,
    show_full_disk_access_dialog,
)
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
    Resolve Chrome cookie database path (macOS and Linux).

    Resolves the absolute path to Chrome's Cookies SQLite database file.
    Uses CHROME_PROFILE env var or parameter (default: "Default").

    On macOS:   ~/Library/Application Support/Google/Chrome/<profile>/Cookies
    On Windows: %LOCALAPPDATA%\\Google\\Chrome\\User Data\\<profile>\\[Network\\]Cookies
    On Linux:   ~/.config/google-chrome/<profile>/Cookies
                or ~/.config/chromium/<profile>/Cookies

    Args:
        profile: Chrome profile name (e.g., "Default", "Profile 1")

    Returns:
        str: Absolute path to Chrome Cookies database file

    Raises:
        CookieExtractionError: If Chrome cookie file not found
    """
    import sys

    profile = os.environ.get("CHROME_PROFILE", profile or "Default")

    if sys.platform == "darwin":
        bases = [Path.home() / "Library/Application Support/Google/Chrome"]
    elif sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        bases = [Path(local_app_data) / "Google" / "Chrome" / "User Data"]
    elif sys.platform.startswith("linux"):
        bases = [
            Path.home() / ".config/google-chrome",
            Path.home() / ".config/chromium",
        ]
    else:
        bases = [Path.home() / "Library/Application Support/Google/Chrome"]

    for base in bases:
        # Newer Chrome stores cookies under Network/ subdirectory
        for subpath in [base / profile / "Network" / "Cookies", base / profile / "Cookies"]:
            if subpath.exists():
                return str(subpath.resolve())

    # Build helpful error message with all paths checked
    checked = [str(base / profile / "Cookies") for base in bases]
    raise CookieExtractionError(
        f"Chrome cookie file not found. Checked: {', '.join(checked)}"
    )


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


def _decrypt_v11_cookie(encrypted_value: bytes, key: bytes) -> str:
    """
    Decrypt a Chrome v11 encrypted cookie value on Linux.

    v11 uses AES-128-CBC with a 16-byte key derived via PBKDF2-SHA1
    from the Chrome Safe Storage password in the system keyring.
    IV is 16 space bytes (0x20). Cookie DB version >= 24 prepends a
    32-byte SHA-256 domain hash to the plaintext before encryption.

    Args:
        encrypted_value: Raw encrypted bytes (with 'v11' prefix stripped)
        key: 16-byte AES key from PBKDF2

    Returns:
        str: Decrypted cookie value
    """
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    iv = b' ' * 16
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    decrypted = decryptor.update(encrypted_value) + decryptor.finalize()

    # Strip PKCS7 padding
    pad_len = decrypted[-1]
    if 0 < pad_len <= 16:
        decrypted = decrypted[:-pad_len]

    # DB version >= 24: strip 32-byte SHA-256 domain hash prefix
    if len(decrypted) > 32:
        decrypted = decrypted[32:]

    return decrypted.decode("utf-8")


def _extract_cookies_linux_native(cookie_db_path: str) -> dict:
    """
    Extract and decrypt cookies directly on Linux using native decryption.

    Bypasses pycookiecheat to handle Chrome v11 encryption and cookie DB
    version 24+ (with domain hash prefix) that pycookiecheat doesn't support.

    Args:
        cookie_db_path: Path to Chrome Cookies SQLite database

    Returns:
        dict: Raw cookie dict {name: value} for perplexity.ai

    Raises:
        CookieExtractionError: If decryption key cannot be obtained
        sqlite3.OperationalError: If database is locked
    """
    import secretstorage

    # Get Chrome Safe Storage password from keyring
    conn = secretstorage.dbus_init()
    collection = secretstorage.get_default_collection(conn)
    password = None
    for item in collection.get_all_items():
        attrs = item.get_attributes()
        if attrs.get("application") == "chrome" and "v2" in attrs.get(
            "xdg:schema", ""
        ):
            password = item.get_secret()
            break
    if password is None:
        # Fallback: try any Chrome Safe Storage entry
        for item in collection.get_all_items():
            if item.get_label() == "Chrome Safe Storage":
                password = item.get_secret()
                break
    if password is None:
        raise CookieExtractionError(
            "Chrome Safe Storage key not found in system keyring. "
            "Ensure Chrome has been run at least once and the keyring is unlocked."
        )

    # Derive AES key: PBKDF2-SHA1, salt='saltysalt', 1 iteration, 16-byte key
    # Password is used as-is (ASCII bytes), NOT base64-decoded
    key = hashlib.pbkdf2_hmac("sha1", password, b"saltysalt", 1, dklen=16)

    # Query cookies from SQLite
    db = sqlite3.connect(cookie_db_path)
    cursor = db.cursor()
    cursor.execute(
        "SELECT name, encrypted_value, value FROM cookies "
        "WHERE host_key LIKE '%perplexity.ai%'"
    )
    cookies = {}
    for name, encrypted_value, plain_value in cursor.fetchall():
        if plain_value:
            cookies[name] = plain_value
        elif encrypted_value:
            prefix = encrypted_value[:3]
            if prefix == b"v11" or prefix == b"v10":
                try:
                    cookies[name] = _decrypt_v11_cookie(encrypted_value[3:], key)
                except Exception:
                    pass  # Skip cookies that fail to decrypt
    db.close()
    return cookies


def _extract_cookies_windows_native(cookie_db_path: str) -> dict:
    """
    Extract cookies on Windows.

    Chrome 127+ uses App-Bound Encryption (v20) that blocks direct
    decryption. On Windows the cookies are obtained via setup_cookies.py
    (interactive) which saves a normalized cookies.json that get_cookies()
    reads through the standard load_cookies() path.

    This function tries rookiepy as a best-effort fallback (requires admin).

    Raises:
        CookieExtractionError: If no cookies available
    """
    try:
        import rookiepy

        raw_cookies = rookiepy.chrome(domains=["perplexity.ai"])
        return {c["name"]: c["value"] for c in raw_cookies}
    except (RuntimeError, ImportError, Exception) as e:
        raise CookieExtractionError(
            "Chrome 127+ on Windows uses App-Bound Encryption.\n"
            "Run the interactive setup to provide your session cookie:\n"
            "  python setup_cookies.py\n"
            "(Located in the perplexity-deepresearch directory)"
        )


def extract_cookies_raw(password: str | None = None) -> dict:
    """
    Extract cookies from Chrome.

    On Linux with v11 encryption, uses native decryption to handle Chrome 130+
    cookie format. Falls back to pycookiecheat on macOS or when native
    extraction fails.

    Args:
        password: Optional keychain password for decryption (macOS only)

    Returns:
        dict: Raw cookie dict

    Raises:
        sqlite3.OperationalError: If Chrome is blocking database access
        CookieExtractionError: If cookie extraction fails
    """
    cookie_path = get_chrome_cookie_path()

    # On Windows, use native DPAPI decryption (pycookiecheat doesn't support Windows)
    if sys.platform == "win32":
        return _extract_cookies_windows_native(cookie_path)

    # On Linux, try native decryption first (handles v11 + DB v24)
    if sys.platform.startswith("linux"):
        try:
            return _extract_cookies_linux_native(cookie_path)
        except OperationalError:
            raise  # Re-raise DB lock errors for relaunch handling
        except CookieExtractionError:
            raise
        except Exception:
            pass  # Fall through to pycookiecheat

    return chrome_cookies(
        url="https://www.perplexity.ai",
        browser=BrowserType.CHROME,
        cookie_file=cookie_path,
        password=password,
    )


def extract_cookies_with_relaunch() -> dict:
    """
    Extract cookies with permission handling and Chrome relaunch.

    Handles:
    1. Cookie file access permission errors (Full Disk Access on macOS)
    2. Keychain/secret storage password prompts
    3. Chrome database locking

    Returns:
        dict: Normalized cookie dict

    Raises:
        CookieExtractionError: If extraction fails or Chrome can't be accessed
    """
    if not check_full_disk_access():
        show_full_disk_access_dialog()
        raise CookieExtractionError(
            "Cannot read Chrome cookie database. Please check file permissions and ensure Chrome is installed."
        )

    password = None
    max_attempts = 2

    for attempt in range(max_attempts):
        try:
            raw = extract_cookies_raw(password=password)
            return normalize_cookies(raw)
        except Exception as e:
            error_str = str(e).lower()

            if (
                "keychain" in error_str
                or "password" in error_str
                or "security" in error_str
            ):
                if attempt == 0:
                    password = prompt_keychain_password()
                    if password is None:
                        raise CookieExtractionError(
                            "Keychain access cancelled. Cannot extract cookies without password."
                        )
                    continue
                else:
                    raise CookieExtractionError(
                        "Keychain access denied. Please check your password and try again."
                    )

            if is_database_locked_error(e):
                break

            raise

    result = ensure_chrome_accessible()
    if not result.accessible:
        raise CookieExtractionError(
            "Chrome is blocking cookie access and could not be closed. "
            "Please close Chrome manually and retry, or set PERPLEXITY_ALLOW_CHROME_QUIT=1."
        )

    try:
        raw = extract_cookies_raw(password=password)
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
