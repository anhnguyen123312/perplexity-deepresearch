"""Extract grok.com cookies from local Chrome (macOS, Linux, Windows).

Reads cookies from the ONE Chrome profile the user onboarded for grok
(``profile_config`` chosen profile, or the ``CHROME_PROFILE`` env override).
When none is configured, auto-picks the single signed-in profile (and remembers
it) or the first signed-in one with a nudge to run ``deep-research-onboard`` —
it does NOT harvest every profile on the hot path. ``get_grok_cookies`` /
``extract_grok_cookies_all_profiles`` remain for the explicit
``deep-research-config rescan`` flow.

A profile is "signed in" when it has the grok.com ``sso`` cookie. On Windows,
delegates to rookiepy (Chrome 127+ App-Bound Encryption).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from pycookiecheat import BrowserType, chrome_cookies

from .. import profile_config
from ..cookies import (
    _extract_cookies_windows_rookiepy,
    _note_active_profile,
    _profile_cookie_db,
    list_chrome_profile_dirs,
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


def _harvest_grok_profile(profile_dir: Path) -> dict[str, str] | None:
    """Raw grok.com cookies from ONE profile, or None if not signed in."""
    db = _profile_cookie_db(profile_dir)
    if db is None:
        return None
    try:
        raw = chrome_cookies(
            url="https://grok.com/",
            browser=BrowserType.CHROME,
            cookie_file=str(db.resolve()),
        )
    except Exception:
        return None
    return raw if _has_grok_auth(raw) else None


def _resolve_grok_profile(chosen: str | None) -> tuple[str, dict[str, str]]:
    """Extract grok cookies from a SINGLE Chrome profile (no scan-all).

    ``chosen`` (onboarded value / ``CHROME_PROFILE`` env) → that profile only.
    When unset, auto-pick the first signed-in profile: remember it if it is the
    only one on disk, else use it once with a warning to run
    ``deep-research-onboard``.
    """
    if sys.platform == "win32":
        raw = _extract_cookies_windows_rookiepy("grok.com")
        if not _has_grok_auth(raw):
            raise RuntimeError("No Chrome profile is signed in to grok.com.")
        return "Default", raw

    all_dirs = list_chrome_profile_dirs()
    if not all_dirs:
        raise RuntimeError(
            "No Chrome profile found. Sign in to grok.com in Chrome, then run "
            "`deep-research-onboard`."
        )

    if chosen:
        target = next((p for p in all_dirs if p.name == chosen), None)
        if target is None:
            raise RuntimeError(
                f"Configured Chrome profile {chosen!r} not found. Available: "
                f"{[p.name for p in all_dirs]}. Re-run `deep-research-onboard`."
            )
        raw = _harvest_grok_profile(target)
        if raw is None:
            raise RuntimeError(
                f"Chrome profile {chosen!r} is not signed in to grok.com. Sign in "
                f"in Chrome, or re-run `deep-research-onboard`."
            )
        return chosen, raw

    for profile_dir in list_chrome_profiles_ordered():
        raw = _harvest_grok_profile(profile_dir)
        if raw is not None:
            if len(all_dirs) == 1:
                profile_config.set_chosen_profile(
                    profile_config.PROVIDER_GROK, profile_dir.name
                )
                _note_active_profile("grok", profile_dir.name, "remembered")
            else:
                _note_active_profile("grok", profile_dir.name, "temporary")
            return profile_dir.name, raw

    raise RuntimeError(
        "No Chrome profile is signed in to grok.com. Sign in in Chrome, then run "
        "`deep-research-onboard`."
    )


def get_grok_cookies_cached() -> dict[str, str]:
    """Return grok cookies from the user's chosen Chrome profile.

    Reads from a SINGLE profile (onboarded via ``deep-research-onboard`` or
    ``CHROME_PROFILE``) instead of scanning every profile; auto-picks + remembers
    the only signed-in profile on a fresh machine. Cached entries are reused
    until they expire.
    """
    chosen = os.environ.get("CHROME_PROFILE") or profile_config.get_chosen_profile(
        profile_config.PROVIDER_GROK
    )
    if chosen:
        # Pinned to one profile — only ITS own cache counts; never fall back to
        # a different profile's cookies.
        entry = profile_config.get_profile_entry(profile_config.PROVIDER_GROK, chosen)
        if entry is not None and not profile_config.is_expired(entry):
            return entry["cookies"]
        # Headless/server mode (GROK_PROXY set): there is NO Chrome to re-harvest
        # from. The cache entry's `expires_at` tracks the shortest cookie
        # (__cf_bm, ~30 min), but the `sso` login lasts months — so reuse the
        # stored login cookies even when the entry looks "expired". CloakBrowser
        # re-earns a fresh cf_clearance on the next 401/403 capture anyway.
        from .config import grok_proxy_url

        if entry is not None and grok_proxy_url():
            return entry["cookies"]
    else:
        found = profile_config.get_first_valid(
            profile_config.PROVIDER_GROK,
            preferred_order=_preferred_grok_profile_order(),
        )
        if found is not None:
            return found[1]["cookies"]

    name, cookies = _resolve_grok_profile(chosen)
    profile_config.save_profile_entry(profile_config.PROVIDER_GROK, name, cookies)
    return cookies


def invalidate_grok_cache() -> None:
    """Force-expire every stored grok entry. Call on persistent 401/403."""
    config = profile_config.load_config()
    profiles = config["providers"][profile_config.PROVIDER_GROK]["profiles"]
    for name in list(profiles.keys()):
        profile_config.invalidate_profile(profile_config.PROVIDER_GROK, name)
