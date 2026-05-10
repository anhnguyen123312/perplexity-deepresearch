"""
Open perplexity.ai model dropdown and dump all available model options + their data-* attrs.
Then submit a query in each detected mode to capture mode/model_preference combos.
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
MODELS_FILE = OUTPUT_DIR / "model_options.json"


def load_cookies():
    data = json.loads(COOKIES_FILE.read_text())
    cookies = data["cookies"]
    out = [{"name": cookies["session_token_name"], "value": cookies["session_token"],
            "domain": ".perplexity.ai", "path": "/", "secure": True, "httpOnly": True, "sameSite": "Lax"}]
    if "csrf_token" in cookies:
        out.append({"name": cookies["csrf_token_name"], "value": cookies["csrf_token"],
                    "domain": ".perplexity.ai", "path": "/", "secure": True, "httpOnly": False, "sameSite": "Lax"})
    return out


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    captured = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
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
                    "post_data": json.loads(req.post_data) if req.post_data else None,
                }
                captured.append(entry)
                p_ = entry["post_data"]["params"]
                print(f"[capture #{len(captured)}] mode={p_.get('mode')} model={p_.get('model_preference')}", file=sys.stderr, flush=True)
                OUTPUT_FILE.write_text(json.dumps(captured, indent=2, default=str))

        page.on("request", on_request)
        page.goto("https://www.perplexity.ai", wait_until="domcontentloaded")
        time.sleep(3)

        # Click on Model button to open dropdown
        try:
            page.click("button[aria-label='Model']", timeout=5000)
            time.sleep(2)
            # Snapshot popup
            popup_html = page.content()
            (OUTPUT_DIR / "model_popup.html").write_text(popup_html)
            print("[info] Saved model popup HTML", file=sys.stderr)

            # Try to enumerate option items in popup
            options = page.locator("[role='menuitem'], [role='option'], button").all()
            extracted = []
            for opt in options:
                try:
                    txt = (opt.inner_text() or "").strip()
                    aria = opt.get_attribute("aria-label") or ""
                    dts = opt.get_attribute("data-testid") or ""
                    if txt and len(txt) < 100 and any(k in (txt + aria + dts).lower() for k in ["best", "auto", "fast", "pro", "research", "reasoning", "deep", "claude", "gpt", "sonar", "r1", "o1", "o3", "alpha"]):
                        extracted.append({"text": txt, "aria": aria, "dts": dts})
                except Exception:
                    pass
            MODELS_FILE.write_text(json.dumps(extracted, indent=2))
            print(f"[info] Found {len(extracted)} model-like options", file=sys.stderr)
            for e in extracted:
                print(f"  - {e}", file=sys.stderr)
        except Exception as e:
            print(f"[err] open model: {e}", file=sys.stderr)

        # Try clicking each option then submitting a query
        # First close the popup if any
        try:
            page.keyboard.press("Escape")
            time.sleep(1)
        except Exception:
            pass

        # Iterate over the model labels we found
        try:
            opts = json.loads(MODELS_FILE.read_text())
        except Exception:
            opts = []

        target_keywords = ["best", "fast", "research", "reasoning", "deep"]
        used = set()
        for opt in opts:
            text = opt["text"].lower()
            if any(k in text for k in target_keywords) and text not in used:
                used.add(text)
                print(f"[try] selecting model: {text}", file=sys.stderr)
                try:
                    # Open model dropdown
                    page.click("button[aria-label='Model']", timeout=3000)
                    time.sleep(1)
                    # Click the option by exact text
                    page.click(f"text=\"{opt['text']}\"", timeout=3000)
                    time.sleep(1)
                    # Submit query in contenteditable
                    page.click("[contenteditable='true']")
                    page.keyboard.type(f"What is 2+{len(used)}?", delay=20)
                    time.sleep(0.4)
                    page.keyboard.press("Enter")
                    time.sleep(8)
                    # Go back to homepage to reset
                    page.goto("https://www.perplexity.ai", wait_until="domcontentloaded")
                    time.sleep(3)
                except Exception as e:
                    print(f"[err] mode {text}: {e}", file=sys.stderr)
                    continue

        OUTPUT_FILE.write_text(json.dumps(captured, indent=2, default=str))
        print(f"[done] {len(captured)} captures", file=sys.stderr)
        context.close()
        browser.close()


if __name__ == "__main__":
    main()
