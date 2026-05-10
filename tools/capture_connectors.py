"""
Capture Perplexity connectors / source list using Playwright.

Strategy:
  - Navigate directly to /account/connectors (or /settings/connectors).
  - Dump the rendered page (full HTML + visible button/link list).
  - Then on homepage open "Connectors and sources" panel via the
    "Add files or tools" attach button, dump that panel too.
  - Lastly toggle a connector (GitHub if present) and submit a query
    so we can capture the resulting POST payload.

Outputs (under docs/perplexity-mcp-revert/):
  - connectors_page.html / connectors_page_items.json   (settings page)
  - connectors_panel_open.html / connectors_panel_items.json   (homepage panel)
  - mode_pro_with_connector.json   (network payload after toggle + submit)
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
        if any(k in url for k in ("perplexity_ask", "/rest/sse/", "/rest/", "/api/")):
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
            print(f"[net] {request.method} {url}", file=sys.stderr, flush=True)

    return on_request


def dump_visible_items(page):
    return page.evaluate(
        """
        () => {
            const out = [];
            const seen = new Set();
            const sel = 'button, [role="button"], [role="option"], [role="menuitem"], a, h1, h2, h3, h4, label';
            for (const el of document.querySelectorAll(sel)) {
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 && rect.height === 0) continue;
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


def page_dump(page, basename: str):
    (OUT_DIR / f"{basename}.html").write_text(page.content())
    items = dump_visible_items(page)
    (OUT_DIR / f"{basename}_items.json").write_text(
        json.dumps(items, indent=2, ensure_ascii=False)
    )
    print(f"[dump] {basename}: {len(items)} items", file=sys.stderr)
    return items


def open_attach_panel(page):
    """Click the paperclip / Add files or tools button on homepage."""
    triggers = [
        'button[aria-label="Add files or tools"]',
        '[aria-label="Add files or tools"]',
    ]
    for sel in triggers:
        try:
            el = page.wait_for_selector(sel, timeout=4000, state="visible")
            if el:
                el.click()
                time.sleep(2)
                return True
        except Exception:
            pass
    return False


def click_connectors_section(page):
    """Inside the attach panel, click 'Connectors and sources' (if collapsed)."""
    for sel in [
        'text=Connectors and sources',
        '[role="menuitem"]:has-text("Connectors")',
    ]:
        try:
            el = page.wait_for_selector(sel, timeout=2500)
            if el:
                el.click()
                time.sleep(1.5)
                return True
        except Exception:
            pass
    return False


def submit_query(page, query: str, wait_seconds: int = 12):
    candidates = [
        "textarea[placeholder*='Ask']",
        "textarea[placeholder*='ask']",
        "textarea",
        "div[contenteditable='true']",
    ]
    for sel in candidates:
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


def find_github_button(items):
    return [
        i for i in items
        if "github" in (i.get("text", "") + " " + i.get("aria", "")).lower()
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--query", default="Latest commit on python/cpython main")
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

        # 1. Settings → connectors page (most authoritative source list)
        for url in (
            "https://www.perplexity.ai/account/connectors",
            "https://www.perplexity.ai/settings/connectors",
            "https://www.perplexity.ai/account/sources",
            "https://www.perplexity.ai/settings/sources",
        ):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                time.sleep(3)
                if "perplexity.ai" in page.url and "connectors" in page.url + page.content().lower():
                    items = page_dump(page, f"connectors_page_{url.rsplit('/',1)[-1]}")
                    print(f"[settings] {url} → loaded", file=sys.stderr)
                    break
            except Exception as e:
                print(f"[settings] {url} failed: {e}", file=sys.stderr)

        # 2. Homepage attach panel
        page.goto("https://www.perplexity.ai", wait_until="domcontentloaded")
        time.sleep(3)
        if open_attach_panel(page):
            time.sleep(1.5)
            click_connectors_section(page)
            items = page_dump(page, "connectors_panel_open")
            github_hits = find_github_button(items)
            print(f"[panel] github hits: {len(github_hits)}", file=sys.stderr)
            for h in github_hits:
                print(f"   - {h}", file=sys.stderr)

            # Try toggling first GitHub-related row
            clicked = False
            for sel in [
                'button:has-text("GitHub")',
                'div[role="option"]:has-text("GitHub")',
                'div[role="menuitem"]:has-text("GitHub")',
                'label:has-text("GitHub")',
            ]:
                try:
                    page.locator(sel).first.click(timeout=2500)
                    clicked = True
                    time.sleep(1.2)
                    break
                except Exception:
                    pass
            print(f"[panel] github toggle clicked={clicked}", file=sys.stderr)

        # 3. Close panel + submit query
        page.keyboard.press("Escape")
        time.sleep(1)
        submit_query(page, args.query, wait_seconds=14)

        out_path = OUT_DIR / "mode_pro_with_connector.json"
        out_path.write_text(json.dumps(captured, indent=2, default=str))
        print(f"[done] saved {len(captured)} requests → {out_path}", file=sys.stderr)

        ctx.close()
        browser.close()


if __name__ == "__main__":
    main()
