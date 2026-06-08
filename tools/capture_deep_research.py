"""Capture the REAL Perplexity "Research" (Deep Research) request from the web UI.

Goal: prove what mode/model_preference the genuine Deep Research button sends —
NOT the Comet/computer-use agent (which sends query_source="computer"). We click
the Research toggle, submit a query, and record the /rest/sse/perplexity_ask POST
with request.all_headers() + the full body.

Usage:
    python tools/capture_deep_research.py [--headless] [--query "..."] [--wait 18]

Writes docs/perplexity-mcp-revert/captured_deep_research.json (cookie redacted)
and prints, for every captured ask, mode / model_preference / query_source so the
real Deep Research signature is unambiguous.
"""

import argparse
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

# Use the SAME cookies the MCP uses (config store / right profile), NOT the
# stale legacy cookies.json — verified they are different accounts.
from deep_research.cookies import get_cookies

OUT_DIR = Path("/Volumes/Data/Git/perlexity/docs/perplexity-mcp-revert")
OUT = OUT_DIR / "captured_deep_research.json"


def load_cookies():
    c = get_cookies()  # canonical resolver: config store -> copy-profile harvest
    out = [{"name": c["session_token_name"], "value": c["session_token"],
            "domain": ".perplexity.ai", "path": "/", "secure": True,
            "httpOnly": True, "sameSite": "Lax"}]
    if c.get("csrf_token"):
        out.append({"name": c["csrf_token_name"], "value": c["csrf_token"],
                    "domain": ".perplexity.ai", "path": "/", "secure": True,
                    "httpOnly": False, "sameSite": "Lax"})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--query", default="What are the main causes of inflation in 2025?")
    ap.add_argument("--wait", type=int, default=18)
    ap.add_argument("--no-research", action="store_true", help="skip Deep research selection (capture default Search)")
    args = ap.parse_args()

    captured = []

    def on_request(req):
        if "/rest/sse/perplexity_ask" in req.url and req.method == "POST":
            try:
                full = req.all_headers()
            except Exception as e:
                full = {"_err": str(e)}
            body = req.post_data
            try:
                body = json.loads(body) if body else None
            except Exception:
                pass
            captured.append({"url": req.url, "all_headers": full, "post_data": body})
            p = (body or {}).get("params", {}) if isinstance(body, dict) else {}
            print(f"[capture #{len(captured)}] mode={p.get('mode')!r} "
                  f"model_preference={p.get('model_preference')!r} "
                  f"query_source={p.get('query_source')!r}", file=sys.stderr, flush=True)

    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=args.headless,
                                args=["--disable-blink-features=AutomationControlled"])
        ctx = br.new_context(viewport={"width": 1360, "height": 950})
        ctx.add_cookies(load_cookies())
        page = ctx.new_page()
        page.on("request", on_request)
        page.goto("https://www.perplexity.ai", wait_until="domcontentloaded")
        time.sleep(4)

        # Diagnostic: are we logged in? Screenshot + look for sign-in markers.
        try:
            page.screenshot(path=str(OUT_DIR / "dr_capture_home.png"))
        except Exception:
            pass
        body_txt = ""
        try:
            body_txt = (page.locator("body").inner_text() or "")[:4000].lower()
        except Exception:
            pass
        logged_out = ("sign in" in body_txt or "log in" in body_txt) and "search anything" not in body_txt
        print(f"[info] logged_out_guess={logged_out} (markers: signin={'sign in' in body_txt})", file=sys.stderr)

        # Dismiss the cookie-policy banner (it overlays the input → blocks clicks).
        for label in ("Decline optional", "Got it", "Accept"):
            try:
                b = page.get_by_role("button", name=label)
                if b and b.first.is_visible():
                    b.first.click()
                    print(f"[info] dismissed cookie banner via {label!r}", file=sys.stderr)
                    time.sleep(0.5)
                    break
            except Exception:
                continue

        # 1) Open the mode menu (mode toggle / "Search" pill), then pick Research.
        clicked = False
        opened = False
        for opener in (() if args.no_research else
                       ("[data-testid='ask-input-mode-toggle-indicator']",
                        "button:has-text('Search')", "[aria-label='Mode']")):
            try:
                el = page.locator(opener).first
                if el and el.is_visible():
                    el.click()
                    opened = True
                    print(f"[info] opened mode menu via {opener!r}", file=sys.stderr)
                    time.sleep(1.5)
                    break
            except Exception:
                continue
        # Wait for the dropdown items to render (async), then screenshot + dump.
        time.sleep(2.5)
        try:
            page.screenshot(path=str(OUT_DIR / "dr_capture_menu.png"))
        except Exception:
            pass
        print("=== mode menu options ===", file=sys.stderr)
        try:
            items = page.locator("[role='menuitem'], [role='option'], button, [role='radio'], a, div[tabindex]").all()
            for it in items[:160]:
                try:
                    txt = (it.inner_text() or "").strip().replace("\n", " ")[:50]
                    if txt and any(k in txt.lower() for k in ("research", "search", "labs", "reason", "deep", "computer")):
                        print(f"  option: {txt!r}", file=sys.stderr)
                except Exception:
                    continue
        except Exception as e:
            print(f"[warn] menu scan failed: {e}", file=sys.stderr)
        # Click "Deep research" directly by text.
        for needle in (() if args.no_research else ("Deep research", "Deep Research", "Research")):
            try:
                t = page.get_by_text(needle, exact=False).first
                if t and t.is_visible():
                    t.click()
                    clicked = True
                    print(f"  >>> CLICKED text={needle!r}", file=sys.stderr)
                    time.sleep(1.2)
                    break
            except Exception:
                continue
        print(f"[info] mode menu opened={opened} research clicked={clicked}", file=sys.stderr)

        # 2) Type query + submit (menu just closed — re-focus the input).
        try:
            page.keyboard.press("Escape")  # ensure the mode menu is closed
        except Exception:
            pass
        time.sleep(1.5)
        typed = False
        for sel in ("div[contenteditable='true']", "textarea", "[role='textbox']"):
            try:
                el = page.wait_for_selector(sel, timeout=4000, state="visible")
                if el:
                    el.click(force=True)
                    time.sleep(0.3)
                    page.keyboard.type(args.query, delay=18)
                    typed = True
                    print(f"[info] typed query via {sel}", file=sys.stderr)
                    break
            except Exception:
                continue
        time.sleep(0.6)
        # Submit: Enter first, then fall back to a send button.
        page.keyboard.press("Enter")
        time.sleep(2)
        if not captured:
            for btn in ("button[aria-label='Submit']", "button[aria-label='Send']",
                        "[data-testid='submit-button']", "button[type='submit']"):
                try:
                    b = page.locator(btn).first
                    if b and b.is_visible():
                        b.click()
                        print(f"[info] clicked submit button {btn!r}", file=sys.stderr)
                        time.sleep(2)
                        break
                except Exception:
                    continue
        print(f"[info] typed={typed} captured_so_far={len(captured)}", file=sys.stderr)

        time.sleep(args.wait)
        ctx.close()
        br.close()

    # redact cookie before saving
    for e in captured:
        h = e.get("all_headers", {})
        if "cookie" in h:
            h["cookie"] = "<REDACTED>"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(captured, indent=2, default=str))

    print("\n=== SUMMARY: captured ask requests ===")
    for i, e in enumerate(captured):
        p = (e.get("post_data") or {}).get("params", {}) if isinstance(e.get("post_data"), dict) else {}
        print(f"[{i}] mode={p.get('mode')!r} model_preference={p.get('model_preference')!r} "
              f"query_source={p.get('query_source')!r} source={p.get('source')!r} "
              f"search_focus={p.get('search_focus')!r}")
    if not captured:
        print("  (none captured — UI changed or query didn't fire)")


if __name__ == "__main__":
    main()
