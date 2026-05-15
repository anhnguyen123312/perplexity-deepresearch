"""Interactive onboarding CLI: pick Chrome profile + Google account, save cookies.

Run via the ``deep-research-onboard`` console script. Walks the user through:

  1. Pick a Chrome profile (friendly name + signed-in Google emails shown).
  2. Extract Perplexity / Grok / Gemini cookies from that profile.
  3. For Gemini: probe ``/u/N/`` to discover which Google accounts work and
     persist the chosen one as the default ``authuser``.

All state lands in the shared config store (``profile_config``); after a
successful run the MCP server can pick everything up without further prompts.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from . import profile_config
from .cookies import (
    _extract_one_profile,
    _has_perplexity_session,
    _profile_cookie_db,
    list_chrome_profile_dirs,
    normalize_cookies,
)
from .gemini.config import GEMINI_AUTH_COOKIES
from .gemini.csrf import GeminiCsrfError, extract_tokens_from_html, _fetch_homepage
from .grok.cookies import GROK_AUTH_COOKIES


@dataclass
class ChromeProfile:
    dir_name: str
    display_name: str
    emails: list[str]
    path: Path


# ---------------------------------------------------------------------------
# Step 1 — list Chrome profiles with friendly names + emails
# ---------------------------------------------------------------------------


def _read_profile_metadata(profile_dir: Path) -> tuple[str, list[str]]:
    """Return ``(display_name, [emails])`` parsed from ``Preferences`` JSON.

    Falls back to the dir name and an empty email list when ``Preferences`` is
    missing or unparseable.
    """
    pref = profile_dir / "Preferences"
    if not pref.exists():
        return profile_dir.name, []
    try:
        data = json.loads(pref.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return profile_dir.name, []

    name = (
        (data.get("profile") or {}).get("name")
        or (data.get("profile") or {}).get("gaia_name")
        or profile_dir.name
    )
    emails: list[str] = []
    for acc in data.get("account_info") or []:
        email = acc.get("email")
        if email and email not in emails:
            emails.append(email)
    return name, emails


def list_chrome_profiles_with_names() -> list[ChromeProfile]:
    out: list[ChromeProfile] = []
    for path in list_chrome_profile_dirs():
        display, emails = _read_profile_metadata(path)
        out.append(
            ChromeProfile(
                dir_name=path.name,
                display_name=display,
                emails=emails,
                path=path,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Step 2 — interactive picker helpers
# ---------------------------------------------------------------------------


def _prompt_index(prompt: str, count: int) -> int:
    while True:
        raw = input(prompt).strip()
        if not raw:
            continue
        try:
            idx = int(raw)
        except ValueError:
            print(f"  ! Enter a number 0-{count - 1}")
            continue
        if 0 <= idx < count:
            return idx
        print(f"  ! Out of range 0-{count - 1}")


def _print_profile_table(profiles: list[ChromeProfile]) -> None:
    print()
    print("Chrome profiles found:")
    for i, p in enumerate(profiles):
        emails = ", ".join(p.emails) if p.emails else "(no signed-in accounts)"
        print(f"  [{i}] {p.dir_name:<12} {p.display_name}  —  {emails}")
    print()


# ---------------------------------------------------------------------------
# Step 3 — per-profile cookie harvest
# ---------------------------------------------------------------------------


def _chrome_cookies_for_profile(profile_dir: Path, url: str) -> dict[str, str]:
    """Read cookies for ``url`` from a specific profile's cookie DB.

    Returns an empty dict on any failure (e.g. profile not signed in).
    """
    from pycookiecheat import BrowserType, chrome_cookies

    db = _profile_cookie_db(profile_dir)
    if db is None:
        return {}
    try:
        return chrome_cookies(
            url=url,
            browser=BrowserType.CHROME,
            cookie_file=str(db.resolve()),
        )
    except Exception:
        return {}


def _harvest_perplexity(profile_dir: Path) -> dict | None:
    """Try to pull a Perplexity session out of the given profile."""
    db = _profile_cookie_db(profile_dir)
    if db is None:
        return None
    try:
        raw = _extract_one_profile(str(db.resolve()), None)
    except Exception:
        return None
    if not _has_perplexity_session(raw):
        return None
    try:
        return normalize_cookies(raw)
    except Exception:
        return None


def _harvest_grok(profile_dir: Path) -> dict | None:
    raw = _chrome_cookies_for_profile(profile_dir, "https://grok.com/")
    if not raw or not all(k in raw for k in GROK_AUTH_COOKIES):
        return None
    return raw


def _harvest_gemini(profile_dir: Path) -> dict | None:
    raw = _chrome_cookies_for_profile(profile_dir, "https://gemini.google.com/")
    if not raw or not all(k in raw for k in GEMINI_AUTH_COOKIES):
        return None
    return raw


# ---------------------------------------------------------------------------
# Step 4 — Gemini Google-account probe
# ---------------------------------------------------------------------------


def _probe_gemini_accounts(
    cookies: dict[str, str], max_index: int = 6
) -> list[tuple[int, str | None]]:
    """For each ``/u/N/`` (0..max_index), report whether the account loads
    and what email it surfaces. Stops scanning after two consecutive failures.
    """
    accounts: list[tuple[int, str | None]] = []
    misses = 0
    for n in range(max_index + 1):
        try:
            html = _fetch_homepage(cookies, n)
        except GeminiCsrfError:
            misses += 1
            if misses >= 2 and accounts:
                break
            continue
        misses = 0
        try:
            _, _, email = extract_tokens_from_html(html)
        except GeminiCsrfError:
            email = None
        accounts.append((n, email))
    return accounts


# ---------------------------------------------------------------------------
# Step 5 — top-level flow
# ---------------------------------------------------------------------------


def _save_cookies(provider: str, profile_name: str, cookies: dict) -> None:
    profile_config.save_profile_entry(provider, profile_name, cookies)


def _run(argv: Iterable[str]) -> int:
    profiles = list_chrome_profiles_with_names()
    if not profiles:
        print(
            "No Chrome profiles with a Cookies database were found.\n"
            "Open Chrome at least once and sign in to the provider(s) you want to use,\n"
            "then re-run `deep-research-onboard`."
        )
        return 1

    _print_profile_table(profiles)
    if len(profiles) == 1:
        idx = 0
        print(f"Only one profile — auto-selecting [{idx}] {profiles[idx].dir_name}\n")
    else:
        idx = _prompt_index("Pick a Chrome profile [0-{}]: ".format(len(profiles) - 1), len(profiles))
    chosen = profiles[idx]
    print(f"→ Using Chrome profile: {chosen.dir_name} ({chosen.display_name})")

    harvested: dict[str, bool] = {}

    pplx = _harvest_perplexity(chosen.path)
    if pplx is not None:
        _save_cookies(profile_config.PROVIDER_PERPLEXITY, chosen.dir_name, pplx)
        harvested["perplexity"] = True
    else:
        harvested["perplexity"] = False

    grok = _harvest_grok(chosen.path)
    if grok is not None:
        _save_cookies(profile_config.PROVIDER_GROK, chosen.dir_name, grok)
        harvested["grok"] = True
    else:
        harvested["grok"] = False

    gemini = _harvest_gemini(chosen.path)
    if gemini is not None:
        _save_cookies(profile_config.PROVIDER_GEMINI, chosen.dir_name, gemini)
        harvested["gemini"] = True
    else:
        harvested["gemini"] = False

    print()
    print("Cookies extracted:")
    for prov in ("perplexity", "grok", "gemini"):
        mark = "✓" if harvested[prov] else "✗ (profile not signed in)"
        print(f"  {prov:<11} {mark}")

    chosen_authuser: int | None = None
    chosen_email: str | None = None
    if harvested["gemini"]:
        print()
        print("Probing Google accounts available to Gemini (/u/N/) …")
        accounts = _probe_gemini_accounts(gemini)
        if not accounts:
            print(
                "  No Google account responded for this profile.\n"
                "  You can still use Gemini by passing `authuser=N` manually."
            )
        else:
            print()
            print("Google accounts found:")
            for i, (n, email) in enumerate(accounts):
                label = email or "(email not detected)"
                print(f"  [{i}] /u/{n}/  —  {label}")
            print()
            pick = _prompt_index(
                "Pick a Google account [0-{}]: ".format(len(accounts) - 1),
                len(accounts),
            )
            chosen_authuser, chosen_email = accounts[pick]
            profile_config.set_provider_settings(
                profile_config.PROVIDER_GEMINI,
                {
                    "authuser": chosen_authuser,
                    "chrome_profile": chosen.dir_name,
                },
            )

    print()
    print("Saved to:", profile_config.get_config_path())
    if chosen_authuser is not None:
        print(
            f"  default gemini → chrome_profile={chosen.dir_name!r} "
            f"authuser={chosen_authuser} ({chosen_email or 'unknown email'})"
        )
    print()
    print("Next step: configure your MCP client to launch `deep-research`.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    try:
        return _run(args)
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
