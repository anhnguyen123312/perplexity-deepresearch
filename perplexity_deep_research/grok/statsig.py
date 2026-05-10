"""Capture and cache x-statsig-id required by grok.com chat endpoint.

The UI generates `x-statsig-id` from a heavily obfuscated webpack module that
takes (URL pathname, HTTP method) and returns a base64 string. We bypass the
JS by:
  1. Launching the user's real Chrome via Playwright (channel="chrome").
  2. Submitting a tiny chat in grok.com and intercepting the request headers.
  3. Caching the captured x-statsig-id keyed by (pathname, method).

The id is path+method-bound and stable across requests. Reuse from curl_cffi.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .config import get_statsig_cache_path
from .cookies import get_grok_cookies


# How long a captured id is trusted before re-capturing.
CACHE_TTL_SECS = 24 * 60 * 60  # 24h


def _read_cache() -> dict:
    p = get_statsig_cache_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _write_cache(data: dict) -> None:
    p = get_statsig_cache_path()
    p.write_text(json.dumps(data, indent=2))


def _cache_key(path: str, method: str) -> str:
    return f"{method.upper()} {path}"


def get_cached_statsig_id(path: str, method: str = "POST") -> str | None:
    """Return cached x-statsig-id for (path, method) or None if missing/stale."""
    cache = _read_cache()
    entry = cache.get(_cache_key(path, method))
    if not entry:
        return None
    if time.time() - entry.get("ts", 0) > CACHE_TTL_SECS:
        return None
    return entry.get("statsig_id")


def store_statsig_id(path: str, method: str, statsig_id: str) -> None:
    cache = _read_cache()
    cache[_cache_key(path, method)] = {
        "statsig_id": statsig_id,
        "ts": int(time.time()),
    }
    _write_cache(cache)


def capture_statsig_id_via_chrome(
    target_path: str = "/rest/app-chat/conversations/new",
    method: str = "POST",
    headless: bool = False,
    timeout_secs: int = 90,
) -> str:
    """Drive the user's Chrome via Playwright to capture x-statsig-id.

    Submits a minimal chat in grok.com so the browser fires a real request
    with all anti-bot headers, then intercepts headers via page.on("request").
    """
    # Imported lazily so the MCP doesn't pay Playwright's startup cost
    # for every call when the cache is hot.
    from playwright.sync_api import sync_playwright
    try:
        from playwright_stealth import Stealth
        stealth = True
    except ImportError:
        stealth = False

    raw_cookies = get_grok_cookies()
    cookies = [
        {"name": k, "value": v, "domain": ".grok.com",
         "path": "/", "secure": True, "httpOnly": False, "sameSite": "Lax"}
        for k, v in raw_cookies.items()
    ]

    captured: dict[str, str | None] = {"id": None}

    def run(p):
        browser = p.chromium.launch(
            channel="chrome",
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )
        ctx = browser.new_context(locale="en-US")
        ctx.add_cookies(cookies)
        page = ctx.new_page()

        def on_request(req):
            if not (req.method == method.upper()
                    and req.url.endswith(target_path)):
                return
            sid = req.headers.get("x-statsig-id")
            if sid:
                captured["id"] = sid

        page.on("request", on_request)
        page.goto("https://grok.com/", wait_until="domcontentloaded",
                  timeout=60000)
        page.wait_for_timeout(4000)

        # Find a visible chat input and submit a tiny message
        for sel in ['[contenteditable="true"]', "textarea"]:
            try:
                box = page.locator(sel).first
                box.wait_for(state="visible", timeout=8000)
                box.click()
                box.fill(".")  # smallest possible
                page.wait_for_timeout(300)
                box.press("Enter")
                break
            except Exception:
                continue

        # Wait up to timeout_secs for the request to fire
        deadline = time.time() + timeout_secs
        while time.time() < deadline and captured["id"] is None:
            page.wait_for_timeout(500)

        ctx.close()
        browser.close()

    if stealth:
        with Stealth().use_sync(sync_playwright()) as p:
            run(p)
    else:
        with sync_playwright() as p:
            run(p)

    if not captured["id"]:
        raise RuntimeError(
            "Failed to capture x-statsig-id from grok.com. Verify Chrome is "
            "logged in to grok.com and you have a working internet connection."
        )

    store_statsig_id(target_path, method, captured["id"])
    return captured["id"]


def get_statsig_id(
    path: str = "/rest/app-chat/conversations/new",
    method: str = "POST",
    refresh: bool = False,
) -> str:
    """Return a valid x-statsig-id, capturing fresh via Playwright if needed."""
    if not refresh:
        cached = get_cached_statsig_id(path, method)
        if cached:
            return cached
    return capture_statsig_id_via_chrome(path, method)
