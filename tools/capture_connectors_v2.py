"""
Capture Perplexity connectors via the homepage attach panel.

Strategy:
  1. Go to perplexity homepage.
  2. Click the paperclip ("Add files or tools") button so the
     "Connectors and sources" panel mounts.
  3. Wait for connector tiles to render (lazy hydration).
  4. Dump all visible buttons + record any /api/connector* and
     /rest/* network calls along the way.
  5. Submit a baseline query to capture the default payload.

Outputs (under docs/perplexity-mcp-revert/):
  - attach_panel.html / attach_panel_items.json
  - all_network.json    every recorded request (filterable by host)
  - default_query.json  POST /rest/sse/perplexity_ask body for "What is 2+2?"
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright


COOKIES_FILE = Path.home() / ".local/share/perplexity-deep-research/cookies.json"
OUT_DIR = Path("/Volumes/Data/Git/perlexity/docs/perplexity-mcp-revert")


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


def make_recorder(captured):
    def on_request(request):
        url = request.url
        if "perplexity.ai" not in url:
            return
        if any(skip in url for skip in (".js", ".css", ".woff", ".png", ".svg", ".jpg")):
            return
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
        captured.append(entry)
    return on_request


def dump_visible(page):
    return page.evaluate(
        """
        () => {
            const out = [];
            const seen = new Set();
            for (const el of document.querySelectorAll(
                'button, [role="button"], [role="option"], [role="menuitem"], a, label, h1, h2, h3, h4'
            )) {
                const r = el.getBoundingClientRect();
                if (!(r.width > 0 && r.height > 0)) continue;
                const text = (el.innerText || '').trim().split('\\n').slice(0, 2).join(' | ');
                const aria = el.getAttribute('aria-label') || '';
                const testid = el.getAttribute('data-testid') || '';
                const href = el.getAttribute('href') || '';
                const key = `${text}|${aria}|${href}`;
                if (!key.trim() || seen.has(key)) continue;
                seen.add(key);
                if (text || aria) out.push({ tag: el.tagName, text, aria, testid, href });
            }
            return out;
        }
        """
    )


def submit_query(page, query: str, wait_seconds: int = 12):
    for sel in [
        "textarea[placeholder*='Ask']",
        "textarea[placeholder*='ask']",
        "textarea",
        "div[contenteditable='true']",
    ]:
        try:
            el = page.wait_for_selector(sel, timeout=3000, state="visible")
            if el:
                page.click(sel)
                page.keyboard.type(query, delay=20)
                time.sleep(0.5)
                page.keyboard.press("Enter")
                time.sleep(wait_seconds)
                return True
        except Exception:
            continue
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--query", default="What is 2+2? Answer briefly.")
    ap.add_argument("--toggle-connector", default=None,
                    help="connector text to click before submitting (e.g. GitHub)")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    captured = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=args.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            viewport={"width": 1400, "height": 900},
        )
        ctx.add_cookies(load_cookies())
        page = ctx.new_page()
        page.on("request", make_recorder(captured))

        page.goto("https://www.perplexity.ai", wait_until="domcontentloaded")
        time.sleep(4)

        # Open attach panel
        try:
            page.click('[aria-label="Add files or tools"]', timeout=4000)
            time.sleep(2)
        except Exception as e:
            print(f"[attach] failed to open: {e}", file=sys.stderr)

        # Some UIs nest "Connectors and sources" deeper.
        try:
            page.click('text=Connectors and sources', timeout=2500)
            time.sleep(2)
        except Exception:
            pass

        # Allow lazy hydration of connector tiles
        time.sleep(3)
        # Scroll inside panel if scrollable
        try:
            page.mouse.wheel(0, 600)
            time.sleep(1)
            page.mouse.wheel(0, -600)
            time.sleep(0.5)
        except Exception:
            pass

        items = dump_visible(page)
        (OUT_DIR / "attach_panel.html").write_text(page.content())
        (OUT_DIR / "attach_panel_items.json").write_text(
            json.dumps(items, indent=2, ensure_ascii=False)
        )
        print(f"[attach] {len(items)} visible items", file=sys.stderr)

        # Find any items mentioning known connector names
        keys = ["github", "slack", "notion", "gmail", "drive", "dropbox", "asana"]
        hits = [
            i for i in items
            if any(k in (i.get("text", "") + " " + i.get("aria", "")).lower() for k in keys)
        ]
        print(f"[connectors] hits: {len(hits)}", file=sys.stderr)
        for h in hits:
            print(f"   - {h}", file=sys.stderr)

        # Optionally toggle a connector by visible text
        if args.toggle_connector:
            try:
                page.locator(f"text={args.toggle_connector}").first.click(timeout=3000)
                time.sleep(1.5)
                print(f"[toggle] clicked {args.toggle_connector}", file=sys.stderr)
            except Exception as e:
                print(f"[toggle] failed: {e}", file=sys.stderr)

        # Close panel + submit query
        page.keyboard.press("Escape")
        time.sleep(1)
        submit_query(page, args.query, wait_seconds=14)

        (OUT_DIR / "all_network.json").write_text(
            json.dumps(captured, indent=2, default=str)
        )

        # Extract just the perplexity_ask POST
        ask_posts = [
            c for c in captured
            if c["method"] == "POST" and "perplexity_ask" in c["url"]
            and "reconnect" not in c["url"]
        ]
        if ask_posts:
            (OUT_DIR / "default_query.json").write_text(
                json.dumps(ask_posts[-1], indent=2, default=str)
            )
            print(f"[ask] captured POST perplexity_ask payload", file=sys.stderr)
        else:
            print("[ask] no perplexity_ask POST recorded", file=sys.stderr)

        ctx.close()
        browser.close()


if __name__ == "__main__":
    main()
