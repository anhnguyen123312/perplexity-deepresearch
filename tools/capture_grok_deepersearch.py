"""Playwright capture: real grok.com POST body when DeeperSearch is ON.

Approach:
  1. Launch real Chrome with logged-in cookies.
  2. Find and click the DeeperSearch toggle (under "Tools" / "Search" UI).
  3. Submit a tiny query.
  4. Capture the POST /rest/app-chat/conversations/new body.

Output: docs/grok-mcp/grok_deepersearch_body.json
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

    captured = {"headers": None, "body": None, "url": None}

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(
            channel="chrome",
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        ctx = browser.new_context(locale="en-US")
        ctx.add_cookies(cookies)
        page = ctx.new_page()

        def on_request(req):
            if req.url.endswith("/rest/app-chat/conversations/new") and req.method == "POST":
                captured["headers"] = dict(req.headers)
                captured["body"] = req.post_data
                captured["url"] = req.url
                print(f"[i] CAPTURED {req.url}", flush=True)

        page.on("request", on_request)

        print("[i] navigating…", flush=True)
        page.goto("https://grok.com/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)

        # Step 1: open the Tools popover (button next to chat input)
        print("[i] opening tools popover…", flush=True)
        try:
            tools_btn = page.get_by_role("button", name="Tools").first
            tools_btn.click(timeout=5000)
            page.wait_for_timeout(800)
            print("[i] tools popover opened", flush=True)
        except Exception as e:
            print(f"[warn] tools button: {e}", flush=True)

        # Step 2: click DeeperSearch
        print("[i] toggling DeeperSearch…", flush=True)
        clicked = False
        for label in ["DeeperSearch", "Deeper Search", "DeepSearch (deeper)"]:
            try:
                page.get_by_text(label, exact=True).first.click(timeout=4000)
                clicked = True
                print(f"[i] clicked {label!r}", flush=True)
                break
            except Exception:
                continue
        if not clicked:
            # Fallback: click any text containing "Deeper"
            try:
                page.locator("text=/Deeper/i").first.click(timeout=4000)
                clicked = True
                print("[i] clicked via regex /Deeper/i", flush=True)
            except Exception as e:
                print(f"[warn] couldn't find DeeperSearch toggle: {e}", flush=True)

        page.wait_for_timeout(800)

        # Step 3: type and send a tiny query
        print("[i] submitting query…", flush=True)
        for sel in ['[contenteditable="true"]', "textarea"]:
            try:
                box = page.locator(sel).first
                box.wait_for(state="visible", timeout=5000)
                box.click()
                box.fill("What is 2+2? Answer briefly.")
                page.wait_for_timeout(500)
                box.press("Enter")
                print(f"[i] submitted via {sel!r}", flush=True)
                break
            except Exception:
                continue

        # Wait for request
        for _ in range(60):
            if captured["headers"]:
                break
            page.wait_for_timeout(1000)

        ctx.close()
        browser.close()

    if not captured["headers"]:
        print("[err] no chat-send request captured", flush=True)
        return 1

    out = DOC_DIR / "grok_deepersearch_body.json"
    out.write_text(json.dumps(captured, indent=2, default=str))
    print(f"[ok] saved → {out}", flush=True)

    if captured["body"]:
        try:
            parsed = json.loads(captured["body"])
            print("[i] body keys:", sorted(parsed.keys()))
            for k in ("modeId", "deepsearchPreset", "isReasoning", "disableSearch"):
                if k in parsed:
                    print(f"     {k} = {parsed[k]!r}")
        except Exception as e:
            print(f"[warn] body parse: {e}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
