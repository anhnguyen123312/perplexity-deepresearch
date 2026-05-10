"""Extract grok.com cookies from local Chrome (macOS, Linux, Windows).

Scans every Chrome profile (CHROME_PROFILE / CHROME_PROFILES env vars to
restrict) and returns cookies from the first profile that has a grok.com
``sso`` cookie set — i.e. a profile actually signed in to grok.

On Windows, delegates to rookiepy (which handles Chrome 127+ App-Bound
Encryption automatically and auto-scans every profile).
"""

from __future__ import annotations

import os
import sys

from pycookiecheat import BrowserType, chrome_cookies

from ..cookies import (
    _extract_cookies_windows_rookiepy,
    _profile_cookie_db,
    list_chrome_profiles_ordered,
)


# Minimum signal that a profile is signed in to grok.com.
# - ``sso`` is the xAI auth cookie (set by the X SSO flow).
GROK_AUTH_COOKIES: tuple[str, ...] = ("sso",)


def _has_grok_auth(raw: dict[str, str]) -> bool:
    return all(k in raw for k in GROK_AUTH_COOKIES)


def get_grok_cookies() -> dict[str, str]:
    """Return raw cookie dict for grok.com from the first signed-in Chrome profile.

    Required cookies for authenticated requests include cf_clearance,
    __cf_bm, sso, sso-rw, x-userid (set by xAI/X SSO and Cloudflare).
    """
    if sys.platform == "win32":
        return _extract_cookies_windows_rookiepy("grok.com")

    profiles = list_chrome_profiles_ordered()
    if not profiles:
        return chrome_cookies("https://grok.com/", browser=BrowserType.CHROME)

    last_error: Exception | None = None
    last_raw: dict[str, str] | None = None

    for profile_dir in profiles:
        db = _profile_cookie_db(profile_dir)
        if db is None:
            continue
        cookie_path = str(db.resolve())
        try:
            raw = chrome_cookies(
                url="https://grok.com/",
                browser=BrowserType.CHROME,
                cookie_file=cookie_path,
            )
        except Exception as e:
            last_error = e
            continue

        last_raw = raw
        if _has_grok_auth(raw):
            os.environ.setdefault("CHROME_PROFILE_USED_GROK", profile_dir.name)
            return raw

    if last_raw is not None:
        return last_raw

    if last_error is not None:
        raise last_error

    raise RuntimeError(
        f"No Chrome profile is signed in to grok.com. Tried: "
        f"{[p.name for p in profiles]}"
    )
