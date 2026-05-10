"""
Use Playwright with the user's real Chrome (channel="chrome") to compute
x-statsig-id for /rest/app-chat/conversations/new.

Approach:
  - Launch Chrome (channel="chrome") with user's cookies installed.
  - Navigate to https://grok.com/.
  - In page context, call the same statsig-id function the UI uses by
    constructing a fake fetch event and invoking the header injector.

Output: docs/grok-mcp/statsig_id.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from pycookiecheat import BrowserType, chrome_cookies


REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_DIR = REPO_ROOT / "docs" / "grok-mcp"
DOC_DIR.mkdir(parents=True, exist_ok=True)


def main() -> int:
    raw = chrome_cookies("https://grok.com/", browser=BrowserType.CHROME)
    cookies = [
        {"name": k, "value": v, "domain": ".grok.com",
         "path": "/", "secure": True, "httpOnly": False, "sameSite": "Lax"}
        for k, v in raw.items()
    ]
    print(f"[i] {len(cookies)} cookies", flush=True)

    captured = {"chat_send_headers": None, "chat_send_body": None}

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(
            channel="chrome",
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )
        ctx = browser.new_context(locale="en-US", timezone_id="Asia/Saigon")
        ctx.add_cookies(cookies)
        page = ctx.new_page()

        def on_request(req):
            if req.url.endswith("/rest/app-chat/conversations/new") and req.method == "POST":
                captured["chat_send_headers"] = dict(req.headers)
                captured["chat_send_body"] = req.post_data
                print(f"[i] CAPTURED request to {req.url}", flush=True)

        page.on("request", on_request)

        print("[i] navigating…", flush=True)
        page.goto("https://grok.com/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)

        # Diagnose: dump first 200 chars of body
        try:
            preview = page.locator("body").inner_text()[:300]
            print(f"[i] page body preview: {preview!r}", flush=True)
        except Exception:
            pass

        print("[i] submitting query…", flush=True)
        try:
            # Try multiple selectors for the chat input
            for sel in [
                'textarea[placeholder]',
                'textarea:visible',
                '[contenteditable="true"]',
                'textarea',
            ]:
                try:
                    box = page.locator(sel).first
                    box.wait_for(state="visible", timeout=5000)
                    box.click()
                    box.fill("What is 2+2? Answer briefly.")
                    page.wait_for_timeout(500)
                    box.press("Enter")
                    print(f"[i] submitted via selector {sel!r}", flush=True)
                    break
                except Exception as ee:
                    print(f"[warn] selector {sel!r} failed: {ee}", flush=True)
                    continue
        except Exception as e:
            print(f"[warn] auto-submit failed: {e}", flush=True)

        # Wait for the request to fire
        for _ in range(60):
            if captured["chat_send_headers"]:
                break
            page.wait_for_timeout(1000)

        ctx.close()
        browser.close()

    if captured["chat_send_headers"]:
        out = DOC_DIR / "statsig_id.json"
        out.write_text(json.dumps(captured, indent=2, default=str))
        print(f"[ok] saved → {out}", flush=True)
        sid = captured["chat_send_headers"].get("x-statsig-id")
        rid = captured["chat_send_headers"].get("x-xai-request-id")
        print(f"  x-statsig-id: {sid!r}")
        print(f"  x-xai-request-id: {rid!r}")
        return 0
    else:
        print("[err] no chat-send request captured", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
