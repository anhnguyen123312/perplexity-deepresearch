"""Capture and cache x-statsig-id required by grok.com chat endpoint.

Strategy: capture once, use forever (until server returns 403 anti-bot).

The UI generates `x-statsig-id` via a heavily obfuscated Statsig webpack
module that no public client has reverse-engineered to pure code. Confirmed
by reviewing 10+ OSS grok clients (Grok3-Proxy, chenyme/grok2api, boykopovar
/Grok3API, …) — all harvest via browser. Empirically the same captured id
is reusable for hours/days across many requests, so it behaves as a session
fingerprint, not a per-request signature.

Capture flow:
  1. Launch the user's real Chrome via Playwright (channel="chrome", headless).
  2. Submit a tiny chat in grok.com and intercept the request headers.
  3. Cache the captured x-statsig-id keyed by (pathname, method).

Refresh policy: cache is trusted for 1 year. The client also auto-refreshes
on a 403 anti-bot response. Users can force-refresh via
`get_statsig_id(refresh=True)` or the MCP tool `grok_refresh_statsig`.
"""

from __future__ import annotations

import time

from .. import profile_config
from .cookies import get_grok_cookies


# Effectively "forever" — captured ids are session fingerprints, not
# per-request signatures, so reuse is safe until the server invalidates.
CACHE_TTL_SECS = 365 * 24 * 60 * 60  # 1 year


def _cache_key(path: str, method: str) -> str:
    return f"{method.upper()} {path}"


def get_cached_statsig_id(path: str, method: str = "POST") -> str | None:
    """Return cached x-statsig-id for (path, method) or None if missing/stale."""
    entry = profile_config.get_provider_statsig(
        profile_config.PROVIDER_GROK, _cache_key(path, method)
    )
    if not entry:
        return None
    if time.time() - entry.get("ts", 0) > CACHE_TTL_SECS:
        return None
    return entry.get("statsig_id")


def store_statsig_id(path: str, method: str, statsig_id: str) -> None:
    profile_config.set_provider_statsig(
        profile_config.PROVIDER_GROK,
        _cache_key(path, method),
        {"statsig_id": statsig_id, "ts": int(time.time())},
    )


def capture_statsig_id_via_chrome(
    target_path: str = "/rest/app-chat/conversations/new",
    method: str = "POST",
    headless: bool = True,
    timeout_secs: int = 90,
) -> str:
    """Capture x-statsig-id by driving CloakBrowser (stealth Chromium 146).

    CloakBrowser ships a custom Chromium binary with 49 source-level C++
    fingerprint patches (canvas, WebGL, audio, GPU, screen, WebRTC, CDP
    input). It clears Cloudflare's managed challenge on grok.com where
    Patchright + the user's local Chrome started returning 403 in 2026-Q2.

    Runs in a worker thread so it stays usable from code paths that already
    have a running asyncio loop (e.g. the FastMCP tool handler). Sync
    Playwright refuses to run when ``asyncio.get_running_loop()`` returns a
    live loop, and worker threads spawned from a loop do not inherit it.
    """
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(
            _do_capture_statsig_id_via_chrome,
            target_path,
            method,
            headless,
            timeout_secs,
        ).result()


def _do_capture_statsig_id_via_chrome(
    target_path: str,
    method: str,
    headless: bool,
    timeout_secs: int,
) -> str:
    import os
    import tempfile

    from cloakbrowser import launch_persistent_context

    from .. import profile_config

    raw_cookies = get_grok_cookies()
    profile_name = os.environ.get("CHROME_PROFILE_USED_GROK") or "Default"
    cookies = [
        {"name": k, "value": v, "domain": ".grok.com",
         "path": "/", "secure": True, "httpOnly": False, "sameSite": "Lax"}
        for k, v in raw_cookies.items()
    ]

    captured: dict[str, str | None] = {"id": None}
    fresh_cookies: dict[str, str] = {}

    udd = tempfile.mkdtemp(prefix="grok_statsig_")
    # CloakBrowser bundles its own stealth Chromium — no ``channel="chrome"``.
    # ``humanize=True`` adds Bézier mouse curves and per-character typing so
    # Cloudflare's behavioural checks don't flag the automated submit.
    ctx = launch_persistent_context(
        udd,
        headless=headless,
        no_viewport=True,
        locale="en-US",
        humanize=True,
    )
    try:
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

        for sel in ['[contenteditable="true"]', "textarea"]:
            try:
                box = page.locator(sel).first
                box.wait_for(state="visible", timeout=8000)
                box.click()
                box.fill(".")
                page.wait_for_timeout(300)
                box.press("Enter")
                break
            except Exception:
                continue

        deadline = time.time() + timeout_secs
        while time.time() < deadline and captured["id"] is None:
            page.wait_for_timeout(500)

        # Harvest fresh cookies (cf_clearance, __cf_bm, etc.) from the
        # CloakBrowser context so the curl_cffi session can reuse them.
        try:
            for c in ctx.cookies():
                name = c.get("name")
                value = c.get("value")
                if isinstance(name, str) and isinstance(value, str):
                    fresh_cookies[name] = value
        except Exception:
            pass
    finally:
        try:
            ctx.close()
        except Exception:
            pass

    if not captured["id"]:
        raise RuntimeError(
            "Failed to capture x-statsig-id from grok.com. Verify Chrome is "
            "logged in to grok.com and you have a working internet connection."
        )

    if fresh_cookies:
        merged = {**raw_cookies, **fresh_cookies}
        try:
            profile_config.save_profile_entry(
                profile_config.PROVIDER_GROK, profile_name, merged
            )
        except Exception:
            pass

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
