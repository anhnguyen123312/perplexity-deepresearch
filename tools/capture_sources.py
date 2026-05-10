"""
Capture what `sources` array values Perplexity sends when user toggles each
connector in the UI. Submit one query per connector permutation we can detect,
or just snapshot the dropdown structure.
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

COOKIES_FILE = Path.home() / ".local/share/perplexity-deep-research/cookies.json"
OUT_DIR = Path("/Volumes/Data/Git/perlexity/docs/perplexity-mcp-revert")
OUT_FILE = OUT_DIR / "captured_sources.json"


def load_cookies():
    data = json.loads(COOKIES_FILE.read_text())
    c = data["cookies"]
    out = [{"name": c["session_token_name"], "value": c["session_token"], "domain": ".perplexity.ai", "path": "/", "secure": True, "httpOnly": True, "sameSite": "Lax"}]
    if "csrf_token" in c:
        out.append({"name": c["csrf_token_name"], "value": c["csrf_token"], "domain": ".perplexity.ai", "path": "/", "secure": True, "httpOnly": False, "sameSite": "Lax"})
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    captured = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        ctx.add_cookies(load_cookies())
        page = ctx.new_page()

        def on_request(req):
            if "perplexity_ask" in req.url:
                pd = None
                if req.post_data:
                    try:
                        pd = json.loads(req.post_data)
                    except Exception:
                        pd = req.post_data
                entry = {"ts": datetime.now().isoformat(), "url": req.url, "post_data": pd}
                captured.append(entry)
                params = pd.get("params") if isinstance(pd, dict) else None
                if isinstance(params, dict):
                    print(f"[capture] sources={params.get('sources')} search_focus={params.get('search_focus')}", file=sys.stderr, flush=True)
                OUT_FILE.write_text(json.dumps(captured, indent=2, default=str))

        page.on("request", on_request)
        page.goto("https://www.perplexity.ai", wait_until="domcontentloaded")
        time.sleep(3)

        # Click + button to open connectors panel, capture HTML
        try:
            page.click("button[aria-label='Add files or tools']", timeout=5000)
            time.sleep(2)
            (OUT_DIR / "connectors_panel.html").write_text(page.content())
            print("[info] saved connectors_panel.html", file=sys.stderr)

            # List menu items
            items = page.locator("[role='menuitem']").all()
            for it in items[:30]:
                try:
                    t = (it.inner_text() or "").strip().replace("\n", " | ")
                    print(f"  menuitem: {t!r}", file=sys.stderr)
                except Exception:
                    pass
        except Exception as e:
            print(f"[err] open connectors: {e}", file=sys.stderr)

        ctx.close()
        browser.close()


if __name__ == "__main__":
    main()
