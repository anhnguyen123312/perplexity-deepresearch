"""Extract per-account SNlM0e + global cfb2h build label from gemini homepage.

A single Chrome profile can have multiple Google accounts; ``SNlM0e`` is
PER-ACCOUNT (different value at ``/u/0/app`` vs ``/u/6/app``) while ``cfb2h``
(the ``bl`` query param) is global and only ships ~once per week.

Cached per ``(chrome_profile, authuser)`` inside ``profile_config`` under the
gemini provider's ``statsig`` slot (already part of the schema; we reuse the
key namespace instead of introducing a new one).
"""

from __future__ import annotations

import re
import time
from typing import Optional

from curl_cffi import requests

from .. import profile_config
from .config import CHROME_UA, IMPERSONATE_TARGET, app_url


# Cache lifetime — SNlM0e itself is good for days, but rotating cookies may
# make older fetches stale. 30 min is a balanced default.
CSRF_TTL_SECS = 30 * 60


_SNLM0E_RE = re.compile(r'"SNlM0e":"([^"]+)"')
_CFB2H_RE = re.compile(r'"cfb2h":"([^"]+)"')
# Best-effort email parse — the first email in the homepage HTML belongs to
# the active account (the one matching /u/{N}/).
_EMAIL_RE = re.compile(r'"([^"]+@[^"\\]+\.[a-zA-Z]{2,})"')


class GeminiCsrfError(RuntimeError):
    pass


def _statsig_key(chrome_profile: str, authuser: int) -> str:
    return f"{chrome_profile}::u{authuser}"


def _fetch_homepage(cookies: dict[str, str], authuser: int) -> str:
    sess = requests.Session(impersonate=IMPERSONATE_TARGET)
    for k, v in cookies.items():
        sess.cookies.set(k, v, domain=".google.com")
    sess.headers.update({"user-agent": CHROME_UA})
    r = sess.get(app_url(authuser), timeout=30)
    if r.status_code != 200:
        raise GeminiCsrfError(
            f"GET {app_url(authuser)} returned HTTP {r.status_code}"
        )
    body = r.text
    if "accounts.google.com" in r.url or "ServiceLogin" in body[:5000]:
        raise GeminiCsrfError(
            f"Homepage for u/{authuser} redirected to login — account not signed in"
        )
    return body


def extract_tokens_from_html(html: str) -> tuple[str, str, Optional[str]]:
    """Pull (SNlM0e, cfb2h, first_email) out of homepage HTML.

    Raises :class:`GeminiCsrfError` when SNlM0e or cfb2h are missing.
    """
    snlm = _SNLM0E_RE.search(html)
    cfb2h = _CFB2H_RE.search(html)
    if not snlm or not cfb2h:
        raise GeminiCsrfError(
            "SNlM0e or cfb2h not found in homepage HTML — page shape changed?"
        )
    email = _EMAIL_RE.search(html)
    return snlm.group(1), cfb2h.group(1), (email.group(1) if email else None)


def get_csrf(
    chrome_profile: str,
    authuser: int,
    cookies: dict[str, str],
    refresh: bool = False,
) -> dict:
    """Return ``{"at": SNlM0e, "bl": cfb2h, "email": <best-effort>}`` for the
    given Chrome profile + Google account index. Cached up to
    :data:`CSRF_TTL_SECS` seconds.
    """
    key = _statsig_key(chrome_profile, authuser)
    if not refresh:
        cached = profile_config.get_provider_statsig(
            profile_config.PROVIDER_GEMINI, key
        )
        if cached and (time.time() - cached.get("fetched_at", 0) < CSRF_TTL_SECS):
            return cached

    html = _fetch_homepage(cookies, authuser)
    at, bl, email = extract_tokens_from_html(html)
    entry = {
        "at": at,
        "bl": bl,
        "email": email,
        "fetched_at": time.time(),
    }
    profile_config.set_provider_statsig(
        profile_config.PROVIDER_GEMINI, key, entry
    )
    return entry


def invalidate_csrf(chrome_profile: str, authuser: int) -> None:
    """Wipe the cached CSRF entry — next ``get_csrf`` will hit Gemini again."""
    key = _statsig_key(chrome_profile, authuser)
    config = profile_config.load_config()
    statsig = config["providers"][profile_config.PROVIDER_GEMINI].get("statsig", {})
    if key in statsig:
        statsig.pop(key)
        profile_config.save_config(config)
