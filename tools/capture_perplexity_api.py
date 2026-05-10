"""
Capture real Perplexity.ai network requests using Playwright (automated).

Loads existing cookies from ~/.local/share/perplexity-deep-research/cookies.json,
launches headed Chromium with that session, and submits a query for each mode.
Hooks every request and dumps any that contain "perplexity_ask" or "/sse/" or "/rest/"
into docs/perplexity-mcp-revert/captured.json.

Usage:
    .venv/bin/python tools/capture_perplexity_api.py [--headless] [--mode auto|pro|research|reasoning|all]
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright


COOKIES_FILE = Path.home() / ".local/share/perplexity-deep-research/cookies.json"
OUTPUT_DIR = Path("/Volumes/Data/Git/perlexity/docs/perplexity-mcp-revert")
OUTPUT_FILE = OUTPUT_DIR / "captured.json"


def load_cookies():
    data = json.loads(COOKIES_FILE.read_text())
    cookies = data["cookies"]
    out = [
        {
            "name": cookies["session_token_name"],
            "value": cookies["session_token"],
            "domain": ".perplexity.ai",
            "path": "/",
            "secure": True,
            "httpOnly": True,
            "sameSite": "Lax",
        }
    ]
    if "csrf_token" in cookies:
        out.append(
            {
                "name": cookies["csrf_token_name"],
                "value": cookies["csrf_token"],
                "domain": ".perplexity.ai",
                "path": "/",
                "secure": True,
                "httpOnly": False,
                "sameSite": "Lax",
            }
        )
    return out


def make_recorder(captured_list):
    def on_request(request):
        url = request.url
        if any(k in url for k in ("perplexity_ask", "/rest/sse/", "/sse/")):
            entry = {
                "ts": datetime.now().isoformat(),
                "method": request.method,
                "url": url,
                "headers": dict(request.headers),
                "post_data": None,
            }
            body = request.post_data
            if body:
                try:
                    entry["post_data"] = json.loads(body)
                except Exception:
                    entry["post_data"] = body
            captured_list.append(entry)
            print(f"[capture] {request.method} {url}", file=sys.stderr, flush=True)
            OUTPUT_FILE.write_text(json.dumps(captured_list, indent=2, default=str))
    return on_request


def submit_query(page, query: str, wait_seconds: int = 8):
    """Type a query into homepage textarea + submit (Enter)."""
    # Wait for textarea / contenteditable
    candidates = [
        "textarea[placeholder*='Ask']",
        "textarea[placeholder*='ask']",
        "textarea",
        "div[contenteditable='true']",
        "input[type='text']",
    ]
    found = None
    for sel in candidates:
        try:
            el = page.wait_for_selector(sel, timeout=3000, state="visible")
            if el:
                found = sel
                break
        except Exception:
            continue
    if not found:
        print("[err] No input found", file=sys.stderr)
        return False
    print(f"[info] Using selector: {found}", file=sys.stderr)
    page.click(found)
    page.fill(found, "") if "textarea" in found or "input" in found else page.keyboard.press("Control+A")
    page.keyboard.type(query, delay=20)
    time.sleep(0.5)
    page.keyboard.press("Enter")
    time.sleep(wait_seconds)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--mode", default="all", choices=["auto", "pro", "research", "reasoning", "all", "single"])
    parser.add_argument("--wait", type=int, default=10)
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    captured = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=args.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        context.add_cookies(load_cookies())
        page = context.new_page()
        page.on("request", make_recorder(captured))

        page.goto("https://www.perplexity.ai", wait_until="domcontentloaded")
        time.sleep(3)
        print("[info] Page loaded. URL:", page.url, file=sys.stderr)

        if args.mode == "single":
            submit_query(page, "What is the capital of France?", wait_seconds=args.wait)
        else:
            # For now, just submit a default mode query
            submit_query(page, "What is the capital of France?", wait_seconds=args.wait)

        OUTPUT_FILE.write_text(json.dumps(captured, indent=2, default=str))
        print(f"[done] Saved {len(captured)} requests to {OUTPUT_FILE}", file=sys.stderr)

        context.close()
        browser.close()


if __name__ == "__main__":
    main()
