"""Extract gemini.google.com cookies from local Chrome.

Cookies live in the Chrome OS profile cookie jar (per-profile, NOT per Google
account). All Google accounts inside a single Chrome profile share the same
``.google.com`` cookie set; account selection is done with the ``/u/{N}/``
URL prefix and the per-account ``SNlM0e`` CSRF token (see ``csrf.py``).
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
from .config import GEMINI_AUTH_COOKIES


def _has_gemini_auth(raw: dict[str, str]) -> bool:
    return all(k in raw for k in GEMINI_AUTH_COOKIES)


def _preferred_gemini_profile_order() -> list[str]:
    if sys.platform == "win32":
        return ["Default"]
    return [p.name for p in list_chrome_profiles_ordered()]


def get_gemini_cookies() -> dict[str, str]:
    """Return raw cookie dict for ``.google.com`` from the first signed-in
    Chrome profile. Raises if none of them have the required Google auth
    cookies.
    """
    if sys.platform == "win32":
        return _extract_cookies_windows_rookiepy("gemini.google.com")

    profiles = list_chrome_profiles_ordered()
    if not profiles:
        return chrome_cookies("https://gemini.google.com/", browser=BrowserType.CHROME)

    last_error: Exception | None = None
    last_raw: dict[str, str] | None = None

    for profile_dir in profiles:
        db = _profile_cookie_db(profile_dir)
        if db is None:
            continue
        try:
            raw = chrome_cookies(
                url="https://gemini.google.com/",
                browser=BrowserType.CHROME,
                cookie_file=str(db.resolve()),
            )
        except Exception as e:
            last_error = e
            continue

        last_raw = raw
        if _has_gemini_auth(raw):
            os.environ.setdefault("CHROME_PROFILE_USED_GEMINI", profile_dir.name)
            return raw

    if last_raw is not None:
        return last_raw
    if last_error is not None:
        raise last_error
    raise RuntimeError(
        f"No Chrome profile is signed in to google.com. Tried: "
        f"{[p.name for p in profiles]}"
    )


def extract_gemini_cookies_all_profiles() -> list[tuple[str, dict[str, str]]]:
    """Every Chrome profile that has a signed-in Google session."""
    if sys.platform == "win32":
        raw = _extract_cookies_windows_rookiepy("gemini.google.com")
        if _has_gemini_auth(raw):
            return [("Default", raw)]
        return []

    profiles = list_chrome_profiles_ordered()
    out: list[tuple[str, dict[str, str]]] = []
    for profile_dir in profiles:
        db = _profile_cookie_db(profile_dir)
        if db is None:
            continue
        try:
            raw = chrome_cookies(
                url="https://gemini.google.com/",
                browser=BrowserType.CHROME,
                cookie_file=str(db.resolve()),
            )
        except Exception:
            continue
        if _has_gemini_auth(raw):
            out.append((profile_dir.name, raw))
    return out


def get_gemini_cookies_cached(chrome_profile: str | None = None) -> tuple[str, dict[str, str]]:
    """Config-store-backed accessor.

    Returns ``(chrome_profile_name, cookies_dict)``. ``chrome_profile`` pins the
    Chrome OS profile to read from (None = first valid in scan order).
    """
    if chrome_profile is not None:
        entry = profile_config.get_profile_entry(
            profile_config.PROVIDER_GEMINI, chrome_profile
        )
        if entry is not None and not profile_config.is_expired(entry):
            return chrome_profile, entry["cookies"]
        # Cache miss/expired: harvest just this profile if possible.
        harvested = extract_gemini_cookies_all_profiles()
        for name, cookies in harvested:
            profile_config.save_profile_entry(
                profile_config.PROVIDER_GEMINI, name, cookies
            )
        match = next(((n, c) for n, c in harvested if n == chrome_profile), None)
        if match is not None:
            return match
        raise RuntimeError(
            f"Chrome profile {chrome_profile!r} is not signed in to google.com"
        )

    preferred = _preferred_gemini_profile_order()
    found = profile_config.get_first_valid(
        profile_config.PROVIDER_GEMINI, preferred_order=preferred
    )
    if found is not None:
        name, entry = found
        return name, entry["cookies"]

    harvested = extract_gemini_cookies_all_profiles()
    if harvested:
        for name, cookies in harvested:
            profile_config.save_profile_entry(
                profile_config.PROVIDER_GEMINI, name, cookies
            )
        harvested_map = dict(harvested)
        for name in preferred:
            if name in harvested_map:
                return name, harvested_map[name]
        return harvested[0]

    # Diagnostic path
    fresh = get_gemini_cookies()
    name = os.environ.get("CHROME_PROFILE_USED_GEMINI") or "Default"
    profile_config.save_profile_entry(profile_config.PROVIDER_GEMINI, name, fresh)
    return name, fresh


def invalidate_gemini_cache() -> None:
    """Force-expire every stored gemini entry. Call on persistent 401/403."""
    config = profile_config.load_config()
    profiles = config["providers"][profile_config.PROVIDER_GEMINI]["profiles"]
    for name in list(profiles.keys()):
        profile_config.invalidate_profile(profile_config.PROVIDER_GEMINI, name)
