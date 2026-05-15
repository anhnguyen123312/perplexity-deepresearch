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

from .. import profile_config
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


def _preferred_grok_profile_order() -> list[str]:
    """Preferred Chrome profile order for the grok provider."""
    if sys.platform == "win32":
        return ["Default"]
    return [p.name for p in list_chrome_profiles_ordered()]


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


def extract_grok_cookies_all_profiles() -> list[tuple[str, dict[str, str]]]:
    """Scan every Chrome profile and return all that are signed in to grok.com."""
    if sys.platform == "win32":
        raw = _extract_cookies_windows_rookiepy("grok.com")
        if _has_grok_auth(raw):
            return [("Default", raw)]
        return []

    profiles = list_chrome_profiles_ordered()
    out: list[tuple[str, dict[str, str]]] = []
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
        except Exception:
            continue
        if _has_grok_auth(raw):
            out.append((profile_dir.name, raw))
    return out


def get_grok_cookies_cached() -> dict[str, str]:
    """Config-store-backed accessor for grok cookies.

    Reuses a cached entry until expiry; on miss/expiry, harvests every
    signed-in profile and persists each one so future runs hit the cache.
    Falls through to :func:`get_grok_cookies` for diagnostics (single-profile
    error reporting) when harvest is empty.
    """
    preferred = _preferred_grok_profile_order()
    found = profile_config.get_first_valid(
        profile_config.PROVIDER_GROK, preferred_order=preferred
    )
    if found is not None:
        return found[1]["cookies"]

    harvested = extract_grok_cookies_all_profiles()
    if harvested:
        for name, cookies in harvested:
            profile_config.save_profile_entry(
                profile_config.PROVIDER_GROK, name, cookies
            )
        harvested_map = dict(harvested)
        for name in preferred:
            if name in harvested_map:
                return harvested_map[name]
        return harvested[0][1]

    # Empty harvest — invoke the diagnostic single-profile path so the caller
    # gets the same RuntimeError listing as before.
    fresh = get_grok_cookies()
    name = os.environ.get("CHROME_PROFILE_USED_GROK") or "Default"
    profile_config.save_profile_entry(profile_config.PROVIDER_GROK, name, fresh)
    return fresh


def invalidate_grok_cache() -> None:
    """Force-expire every stored grok entry. Call on persistent 401/403."""
    config = profile_config.load_config()
    profiles = config["providers"][profile_config.PROVIDER_GROK]["profiles"]
    for name in list(profiles.keys()):
        profile_config.invalidate_profile(profile_config.PROVIDER_GROK, name)
