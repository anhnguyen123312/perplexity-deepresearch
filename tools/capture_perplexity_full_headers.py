"""Capture the COMPLETE on-wire header set of perplexity.ai's SSE ask request.

The older capture_perplexity_api.py used Playwright's `request.headers`, which
omits browser-auto headers (sec-fetch-*, accept-language, priority, ...). This
tool uses `request.all_headers()` to get the FULL set Chrome actually sends, so
we can prove byte-level header parity for the MCP client.

Usage:
    python tools/capture_perplexity_full_headers.py [--headless] [--wait 12]

Writes docs/perplexity-mcp-revert/captured_full_headers.json and prints the
complete header key/value set for the first /rest/sse/perplexity_ask POST.
"""

import argparse
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

COOKIES_FILE = Path.home() / ".local/share/perplexity-deep-research/cookies.json"
OUTPUT = Path("/Volumes/Data/Git/perlexity/docs/perplexity-mcp-revert/captured_full_headers.json")


def load_cookies():
    data = json.loads(COOKIES_FILE.read_text())
    c = data["cookies"]
    out = [{
        "name": c["session_token_name"], "value": c["session_token"],
        "domain": ".perplexity.ai", "path": "/", "secure": True,
        "httpOnly": True, "sameSite": "Lax",
    }]
    if c.get("csrf_token"):
        out.append({
            "name": c["csrf_token_name"], "value": c["csrf_token"],
            "domain": ".perplexity.ai", "path": "/", "secure": True,
            "httpOnly": False, "sameSite": "Lax",
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--wait", type=int, default=12)
    args = ap.parse_args()

    captured = []

    def on_request(request):
        if "/rest/sse/perplexity_ask" in request.url and request.method == "POST":
            try:
                full = request.all_headers()  # COMPLETE set, incl. browser-auto
            except Exception as e:
                full = {"_error": str(e)}
            body = request.post_data
            try:
                body = json.loads(body) if body else None
            except Exception:
                pass
            captured.append({
                "method": request.method, "url": request.url,
                "all_headers": full, "post_data": body,
            })
            print(f"[capture] {request.method} {request.url}", file=sys.stderr)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=args.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        ctx.add_cookies(load_cookies())
        page = ctx.new_page()
        page.on("request", on_request)
        page.goto("https://www.perplexity.ai", wait_until="domcontentloaded")
        time.sleep(3)
        # type a trivial query + submit
        for sel in ("textarea[placeholder*='Ask']", "textarea", "div[contenteditable='true']"):
            try:
                el = page.wait_for_selector(sel, timeout=3000, state="visible")
                if el:
                    page.click(sel)
                    page.keyboard.type("test 2+2", delay=20)
                    time.sleep(0.4)
                    page.keyboard.press("Enter")
                    break
            except Exception:
                continue
        time.sleep(args.wait)
        ctx.close()
        browser.close()

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(captured, indent=2, default=str))
    if captured:
        h = captured[0]["all_headers"]
        print("\n=== COMPLETE SSE ask POST headers (all_headers) ===")
        for k in sorted(h):
            print(f"  {k}: {h[k]}")
        print(f"\nKEY COUNT: {len(h)}")
    else:
        print("[done] No SSE ask POST captured (UI change / CF challenge?).", file=sys.stderr)


if __name__ == "__main__":
    main()
