"""Extract grok.com cookies from local Chrome (macOS / Linux)."""

from __future__ import annotations

from pycookiecheat import BrowserType, chrome_cookies


def get_grok_cookies() -> dict[str, str]:
    """Return raw cookie dict for grok.com from the user's Chrome profile.

    Required cookies for authenticated requests include cf_clearance,
    __cf_bm, sso, sso-rw, x-userid (set by xAI/X SSO and Cloudflare).
    """
    return chrome_cookies("https://grok.com/", browser=BrowserType.CHROME)
