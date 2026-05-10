"""
Submit a query that should pull from the GitHub connector and capture the
resulting POST /rest/sse/perplexity_ask payload, so we can confirm what the
`sources[]` array looks like when github_mcp_direct is engaged.

Account on this machine has github_mcp_direct connected=True.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright


COOKIES_FILE = Path.home() / ".local/share/perplexity-deep-research/cookies.json"
OUT_DIR = Path("/Volumes/Data/Git/perlexity/docs/perplexity-mcp-revert")
OUT = OUT_DIR / "github_query.json"


def load_cookies():
    data = json.loads(COOKIES_FILE.read_text())
    cookies = data["cookies"]
    return [
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


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    captured = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            viewport={"width": 1400, "height": 900},
        )
        ctx.add_cookies(load_cookies())
        page = ctx.new_page()

        def on_req(r):
            if "perplexity_ask" not in r.url or "reconnect" in r.url:
                return
            entry = {
                "ts": datetime.now().isoformat(),
                "method": r.method,
                "url": r.url,
                "headers": dict(r.headers),
                "post_data": None,
            }
            if r.post_data:
                try:
                    entry["post_data"] = json.loads(r.post_data)
                except Exception:
                    entry["post_data"] = r.post_data
            captured.append(entry)
            print(f"[net] {r.method} {r.url}", file=sys.stderr)

        page.on("request", on_req)

        page.goto("https://www.perplexity.ai", wait_until="domcontentloaded")
        time.sleep(3)

        # Open attach panel and try to enable GitHub source
        try:
            page.click('[aria-label="Add files or tools"]', timeout=4000)
            time.sleep(1.5)
        except Exception as e:
            print(f"[panel] open failed: {e}", file=sys.stderr)

        # Look for a row containing "GitHub" inside the panel and click its toggle.
        try:
            page.locator(
                'div:has-text("GitHub"), button:has-text("GitHub"), label:has-text("GitHub")'
            ).first.click(timeout=3000)
            time.sleep(1.5)
            print("[github] toggle clicked", file=sys.stderr)
        except Exception as e:
            print(f"[github] toggle click failed: {e}", file=sys.stderr)

        page.keyboard.press("Escape")
        time.sleep(0.8)

        # Submit a query that obviously needs GitHub
        for sel in ("textarea", "div[contenteditable='true']"):
            try:
                el = page.wait_for_selector(sel, timeout=3000, state="visible")
                if el:
                    page.click(sel)
                    page.keyboard.type(
                        "Show recent commits on python/cpython main branch", delay=20
                    )
                    time.sleep(0.5)
                    page.keyboard.press("Enter")
                    break
            except Exception:
                continue

        time.sleep(15)

        OUT.write_text(json.dumps(captured, indent=2, default=str))
        print(f"[done] {len(captured)} POSTs → {OUT}", file=sys.stderr)
        if captured:
            sources = captured[-1].get("post_data", {}).get("params", {}).get("sources")
            print(f"[sources] {sources}", file=sys.stderr)

        ctx.close()
        browser.close()


if __name__ == "__main__":
    main()
