"""
Capture Perplexity API requests for multiple modes by clicking mode selector.

Submits queries with different modes (Auto/Pro/Reasoning/Deep Research)
and dumps each request payload into captured_modes.json.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright


COOKIES_FILE = Path.home() / ".local/share/perplexity-deep-research/cookies.json"
OUTPUT_DIR = Path("/Volumes/Data/Git/perlexity/docs/perplexity-mcp-revert")
OUTPUT_FILE = OUTPUT_DIR / "captured_modes.json"


def load_cookies():
    data = json.loads(COOKIES_FILE.read_text())
    cookies = data["cookies"]
    out = [
        {"name": cookies["session_token_name"], "value": cookies["session_token"],
         "domain": ".perplexity.ai", "path": "/", "secure": True, "httpOnly": True, "sameSite": "Lax"}
    ]
    if "csrf_token" in cookies:
        out.append({"name": cookies["csrf_token_name"], "value": cookies["csrf_token"],
                    "domain": ".perplexity.ai", "path": "/", "secure": True, "httpOnly": False, "sameSite": "Lax"})
    return out


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    captured = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        context.add_cookies(load_cookies())
        page = context.new_page()

        def on_request(req):
            if "perplexity_ask" in req.url:
                entry = {
                    "ts": datetime.now().isoformat(),
                    "method": req.method,
                    "url": req.url,
                    "headers": dict(req.headers),
                    "post_data": None,
                }
                if req.post_data:
                    try:
                        entry["post_data"] = json.loads(req.post_data)
                    except Exception:
                        entry["post_data"] = req.post_data
                captured.append(entry)
                print(f"[capture #{len(captured)}] mode={entry.get('post_data',{}).get('params',{}).get('mode','?')} model_preference={entry.get('post_data',{}).get('params',{}).get('model_preference','?')}", file=sys.stderr, flush=True)
                OUTPUT_FILE.write_text(json.dumps(captured, indent=2, default=str))

        page.on("request", on_request)
        page.goto("https://www.perplexity.ai", wait_until="domcontentloaded")
        time.sleep(4)

        # Snapshot the initial page to disk for selector inspection
        snapshot_html = OUTPUT_DIR / "homepage.html"
        snapshot_html.write_text(page.content())
        print(f"[info] Saved homepage HTML to {snapshot_html}", file=sys.stderr)

        # Submit a query in default mode first
        textarea_sel = "textarea"
        try:
            page.wait_for_selector(textarea_sel, timeout=8000, state="visible")
            page.click(textarea_sel)
            page.keyboard.type("ping default mode", delay=20)
            time.sleep(0.4)
            page.keyboard.press("Enter")
            time.sleep(8)
        except Exception as e:
            print(f"[err] default submit failed: {e}", file=sys.stderr)

        # Save full page HTML AFTER submission to find mode selector
        try:
            page2 = OUTPUT_DIR / "after_submit.html"
            page2.write_text(page.content())
        except Exception:
            pass

        # Print buttons / aria labels available
        try:
            btns = page.locator("button").all()[:80]
            for i, b in enumerate(btns):
                try:
                    txt = (b.inner_text() or "").strip()
                    aria = b.get_attribute("aria-label") or ""
                    if txt or aria:
                        print(f"[btn#{i}] text={txt!r} aria={aria!r}", file=sys.stderr)
                except Exception:
                    pass
        except Exception:
            pass

        time.sleep(3)
        OUTPUT_FILE.write_text(json.dumps(captured, indent=2, default=str))
        print(f"[done] {len(captured)} captures", file=sys.stderr)
        context.close()
        browser.close()


if __name__ == "__main__":
    main()
